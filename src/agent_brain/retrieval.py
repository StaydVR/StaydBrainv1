from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from typing import Any, Iterable


MAX_QUERY_TERMS = 32
MAX_TERM_LENGTH = 64
MAX_VOCABULARY = 50_000
MAX_CORRECTION_CANDIDATES = 256
MAX_CORRECTION_COMPARISONS = 4_096
MAX_CORRECTION_CELLS = 1_000_000
MAX_STAGE_PAGE_CHUNKS = 4
MAX_RESULT_PAGE_BYTES = 16 * 1024 * 1024
TOKEN_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is", "it",
    "of", "on", "or", "that", "the", "to", "what", "when", "where", "which", "who", "why", "with",
})
OPERATOR_WORDS = frozenset({"and", "match", "near", "not", "or"})
STAGE_WEIGHTS = {"phrase": 0.55, "all_terms": 0.35, "any_terms": 0.20}


def terms(text: str, maximum: int = MAX_QUERY_TERMS) -> list[str]:
    found: list[str] = []
    for match in TOKEN_RE.finditer(text):
        term = match.group(0).casefold().replace("’", "'")[:MAX_TERM_LENGTH]
        if term and term not in found:
            found.append(term)
        if len(found) == maximum:
            break
    return found


def vocabulary_rows(values: Iterable[str]) -> list[tuple[str, int]]:
    frequency: Counter[str] = Counter()
    for value in values:
        for term in set(terms(value, MAX_VOCABULARY)):
            if term in frequency or len(frequency) < MAX_VOCABULARY:
                frequency[term] += 1
    return sorted(frequency.items())


def _literal(term: str) -> str:
    # Callers pass only values produced by terms(); quoting is defense in depth.
    return '"' + term.replace('"', '""') + '"'


def _distance(left: str, right: str, maximum: int) -> int:
    if abs(len(left) - len(right)) > maximum:
        return maximum + 1
    previous_previous: list[int] | None = None
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        row_min = i
        for j, b in enumerate(right, 1):
            value = min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + (a != b))
            if previous_previous is not None and i > 1 and j > 1 and a == right[j - 2] and left[i - 2] == b:
                value = min(value, previous_previous[j - 2] + 1)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > maximum:
            return maximum + 1
        previous_previous, previous = previous, current
    return previous[-1]


def _term_chunk_ids(conn: sqlite3.Connection, term: str, maximum: int = 1000) -> set[str]:
    return {str(row[0]) for row in conn.execute(
        "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT ?", (_literal(term), maximum)
    )}


def _candidate_term_hits(conn: sqlite3.Connection, term: str, chunk_ids: list[str]) -> set[str]:
    hits: set[str] = set()
    for offset in range(0, len(chunk_ids), 400):
        batch = chunk_ids[offset:offset + 400]
        marks = ",".join("?" for _ in batch)
        hits.update(str(row[0]) for row in conn.execute(
            f"SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? AND chunk_id IN ({marks})",
            (_literal(term), *batch),
        ))
    return hits


def analyze(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    original = terms(query)
    meaningful = [term for term in original if term not in STOPWORDS]
    base = meaningful or original
    strategy = "stopwords_removed" if meaningful and len(meaningful) != len(original) else "staged"
    if not meaningful and original:
        strategy = "stopwords_retained"
    corrections: dict[str, str] = {}
    comparisons = 0
    cells = 0
    budget_exhausted = False
    for value in base:
        if len(value) < 4 or value in OPERATOR_WORDS or value.isdigit() or _term_chunk_ids(conn, value, 1):
            continue
        maximum = 1 if len(value) < 6 else 2
        candidates: list[tuple[int, int, str]] = []
        vocabulary = conn.execute(
            "SELECT term,document_frequency FROM vocabulary "
            "WHERE substr(term,1,1)=? AND length(term) BETWEEN ? AND ? "
            "ORDER BY document_frequency DESC,term LIMIT ?",
            (value[0], max(1, len(value) - maximum), len(value) + maximum, MAX_CORRECTION_CANDIDATES),
        ).fetchall()
        for row in vocabulary:
            candidate = str(row["term"])
            if not candidate or candidate[0] != value[0] or abs(len(candidate) - len(value)) > maximum:
                continue
            candidate_cells = len(value) * len(candidate)
            if comparisons >= MAX_CORRECTION_COMPARISONS or cells + candidate_cells > MAX_CORRECTION_CELLS:
                budget_exhausted = True
                break
            comparisons += 1
            cells += candidate_cells
            distance = _distance(value, candidate, maximum)
            if distance <= maximum and 1.0 - distance / max(len(value), len(candidate)) >= 0.72:
                candidates.append((distance, -int(row["document_frequency"]), candidate))
        if candidates:
            corrections[value] = min(candidates)[2]
    effective = [corrections.get(value, value) for value in base]
    if corrections:
        strategy = "typo_recovery"
    return {
        "original_terms": original,
        "effective_terms": effective,
        "expanded_terms": [corrections[value] for value in base if value in corrections],
        "corrected_terms": corrections,
        "correction_comparisons": comparisons,
        "correction_cells": cells,
        "correction_budget_exhausted": budget_exhausted,
        "strategy": strategy,
    }


def _stage_queries(effective: list[str]) -> list[tuple[str, str]]:
    literals = [_literal(term) for term in effective]
    stages: list[tuple[str, str]] = []
    if len(literals) > 1:
        stages.append(("phrase", '"' + " ".join(effective).replace('"', '""') + '"'))
    stages.append(("all_terms", " AND ".join(literals)))
    if len(literals) > 1:
        stages.append(("any_terms", " OR ".join(literals)))
    return stages


def _normalized(text: str) -> str:
    return " ".join(
        match.group(0).casefold().replace("’", "'")[:MAX_TERM_LENGTH]
        for match in TOKEN_RE.finditer(text)
    )


def _field_coverage(value: str, effective: list[str]) -> float:
    tokens = set(terms(value, 2048))
    return sum(term in tokens for term in effective) / len(effective) if effective else 0.0


def _bm25_signal(score: float) -> float:
    magnitude = abs(score)
    return magnitude / (1.0 + magnitude)


def _candidate_field_hits(
    conn: sqlite3.Connection, field: str, term: str, rowids: list[int]
) -> set[int]:
    if field not in {"slug", "title", "heading", "body"}:
        raise ValueError("unsupported FTS field")
    filtered = f"{field} : ({_literal(term)})"
    hits: set[int] = set()
    for offset in range(0, len(rowids), 400):
        batch = rowids[offset:offset + 400]
        marks = ",".join("?" for _ in batch)
        hits.update(int(row[0]) for row in conn.execute(
            f"SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? AND rowid IN ({marks})",
            (filtered, *batch),
        ))
    return hits


def _snippet(body: str, effective: list[str], maximum: int = 260) -> str:
    compact = re.sub(r"\s+", " ", body).strip()
    lowered = compact.casefold()
    positions = [lowered.find(term) for term in effective if lowered.find(term) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - maximum // 3)
    end = min(len(compact), start + maximum)
    if start:
        start = compact.find(" ", start) + 1
    value = compact[start:end].strip()
    return ("… " if start else "") + value + (" …" if end < len(compact) else "")


def retrieve(conn: sqlite3.Connection, analysis: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    effective = list(analysis["effective_terms"])
    stage_limit = min(250, max(50, limit * 10))
    candidates: dict[str, dict[str, Any]] = {}
    for stage, expression in _stage_queries(effective):
        rows = conn.execute(
            "WITH diverse AS (SELECT chunk_id FROM ("
            "SELECT c.id chunk_id,row_number() OVER (PARTITION BY p.id ORDER BY c.start_line,c.id) page_rank "
            "FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.chunk_id JOIN pages p ON p.id=c.page_id "
            "WHERE chunks_fts MATCH ? AND p.deleted=0) WHERE page_rank<=?) "
            "SELECT chunks_fts.rowid fts_rowid,c.id chunk_id,c.heading,c.heading_line,c.start_line,c.end_line,"
            "c.body chunk_body,p.id,p.slug,p.title,p.type,p.path,p.content_hash,p.updated,p.storage_tier,"
            "bm25(chunks_fts) bm25_score FROM chunks_fts "
            "JOIN diverse d ON d.chunk_id=chunks_fts.chunk_id "
            "JOIN chunks c ON c.id=chunks_fts.chunk_id JOIN pages p ON p.id=c.page_id "
            "WHERE chunks_fts MATCH ? ORDER BY bm25_score,c.id LIMIT ?",
            (expression, MAX_STAGE_PAGE_CHUNKS, expression, stage_limit),
        ).fetchall()
        for rank, row in enumerate(rows, 1):
            item = candidates.setdefault(str(row["chunk_id"]), {"row": row, "ranks": {}, "stages": []})
            item["ranks"][stage] = rank
            item["stages"].append(stage)
    candidate_ids = list(candidates)
    term_hits = {term: _candidate_term_hits(conn, term, candidate_ids) for term in effective}
    phrase = " ".join(effective)
    ranked: list[dict[str, Any]] = []
    for chunk_id, item in candidates.items():
        row = item["row"]
        matched = [term for term in effective if chunk_id in term_hits[term]]
        coverage = len(matched) / len(effective)
        exact_phrase = len(effective) > 1 and any(
            phrase in _normalized(field)
            for field in (row["title"], row["heading"], row["slug"].replace("-", " "), row["chunk_body"])
        )
        fusion = sum(STAGE_WEIGHTS[stage] / (5 + rank) for stage, rank in item["ranks"].items())
        title_boost = _field_coverage(row["title"], effective)
        heading_boost = _field_coverage(row["heading"], effective)
        slug_boost = _field_coverage(row["slug"].replace("-", " "), effective)
        bm25_signal = _bm25_signal(float(row["bm25_score"]))
        score = (10 * fusion + 4 * coverage + 2.5 * exact_phrase + 1.4 * title_boost
                 + 1.6 * heading_boost + 0.7 * slug_boost + 0.1 * bm25_signal)
        stages = [stage for stage, _ in _stage_queries(effective) if stage in item["stages"]]
        match_type = ("exact_phrase" if exact_phrase else
                      ("phrase" if "phrase" in stages else ("all_terms" if coverage == 1 else "partial")))
        ranked.append({
            "row": row, "chunk_id": chunk_id, "matched_terms": matched, "coverage": coverage,
            "match_type": match_type, "stages": stages, "score": score,
            "ranking": {"rank_fusion": fusion, "bm25_signal": bm25_signal, "exact_phrase": exact_phrase,
                        "title_boost": title_boost, "heading_boost": heading_boost, "slug_boost": slug_boost},
            "snippet": _snippet(row["chunk_body"], effective),
        })
    ranked.sort(key=lambda item: (-item["score"], item["row"]["id"], item["row"]["start_line"], item["chunk_id"]))
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    page_counts: defaultdict[str, int] = defaultdict(int)
    for item in ranked:
        page_id = str(item["row"]["id"])
        if page_counts[page_id] < 2:
            selected.append(item)
            page_counts[page_id] += 1
        else:
            deferred.append(item)
        if len(selected) == limit:
            break
    # Only backfill beyond the per-page cap when the repository has no alternative page.
    if len(selected) < limit and len({str(item["row"]["id"]) for item in ranked}) == 1:
        for item in deferred:
            selected.append(item)
            if len(selected) == limit:
                break
    body_budget = MAX_RESULT_PAGE_BYTES
    page_bodies: dict[str, str] = {}
    bounded: list[dict[str, Any]] = []
    selected_rowids = [int(item["row"]["fts_rowid"]) for item in selected]
    field_hits = {
        (field, term): _candidate_field_hits(conn, field, term, selected_rowids)
        for field in ("body", "heading", "title", "slug") for term in effective
    }
    for item in selected:
        row = item["row"]
        rowid = int(row["fts_rowid"])
        field_terms = {
            field: [term for term in effective if rowid in field_hits[(field, term)]]
            for field in ("body", "heading", "title", "slug")
        }
        source = max(("body", "heading", "title", "slug"), key=lambda name: (
            len(field_terms[name]),
            {"body": 3, "heading": 2, "title": 1, "slug": 0}[name],
        ))
        source_terms = field_terms[source]
        item["evidence_source"] = source
        item["matched_terms"] = source_terms
        item["coverage"] = len(source_terms) / len(effective)
        source_value = (str(row["chunk_body"]) if source == "body" else
                        str(row["heading"]) if source == "heading" else
                        str(row[source]).replace("-", " ") if source == "slug" else str(row[source]))
        source_exact_phrase = len(effective) > 1 and " ".join(effective) in _normalized(source_value)
        item["match_type"] = ("exact_phrase" if source_exact_phrase else
                              ("all_terms" if item["coverage"] == 1.0 else "partial"))
        if source in {"body", "heading"}:
            page_id = str(row["id"])
            if page_id not in page_bodies:
                body_row = conn.execute(
                    "SELECT body,length(CAST(body AS BLOB)) n FROM pages WHERE id=?", (page_id,)
                ).fetchone()
                body_bytes = int(body_row["n"])
                if body_bytes > body_budget:
                    continue
                body_budget -= body_bytes
                page_bodies[page_id] = str(body_row["body"])
            item["page_body"] = page_bodies[page_id]
            if source == "heading":
                item["snippet"] = str(row["heading"])
        elif source == "title":
            item["snippet"] = str(row["title"])
        else:
            item["snippet"] = str(row["slug"])
        bounded.append(item)
    return bounded

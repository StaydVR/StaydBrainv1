from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from . import markdown
from .audit import append as append_audit
from .audit import verify as verify_audit
from .config import DEFAULT_CONFIG, Config, load_sources, save_sources
from .db import connect, transaction
from .errors import SecurityError, ValidationError
from .obsidian import doctor_issues as obsidian_doctor_issues
from .obsidian import initialize as initialize_obsidian
from .obsidian import inspect as inspect_obsidian
from .security import scan
from .util import atomic_write, contained, fsync_directory, json_bytes, reject_symlink_chain, safe_relative, sha256, utc_now


SLUG_RE = re.compile(r"[^a-z0-9]+")
REPORT_NAMESPACE = uuid.UUID("94ae4828-f167-4c8a-bca9-afddf142933f")


class Brain:
    """High-level, local-only Agent Brain API."""

    def __init__(self, root: str | Path = "."):
        self.root = Path(root).resolve()
        self.control = self.root / ".agent-brain"
        self.brain_dir = self.root / "brain"
        self.db_path = self.control / "index.sqlite3"

    @classmethod
    def init(cls, root: str | Path = ".") -> "Brain":
        requested = Path(root).absolute()
        if requested.is_symlink():
            raise SecurityError(["symlink"])
        obj = cls(root)
        obj.root.mkdir(parents=True, exist_ok=True)
        for directory in (
            obj.control, obj.brain_dir / "pages", obj.brain_dir / "timeline", obj.brain_dir / "reports",
            obj.brain_dir / "sources", obj.control / "state", obj.control / "cache",
            obj.control / "quarantine", obj.control / "backups",
        ):
            reject_symlink_chain(directory, obj.root)
            directory.mkdir(parents=True, exist_ok=True)
            if directory == obj.control or obj.control in directory.parents:
                directory.chmod(0o700)
        if not (obj.control / "config.toml").exists():
            atomic_write(obj.control / "config.toml", DEFAULT_CONFIG.encode())
        if not (obj.control / "state/sources.json").exists():
            atomic_write(obj.control / "state/sources.json", b"{}\n")
        if not (obj.control / "state/audit-head.json").exists():
            atomic_write(obj.control / "state/audit-head.json", json_bytes({"seq": 0, "event_hash": "0" * 64}))
        initialize_obsidian(obj.root)
        with connect(obj.db_path):
            pass
        return obj

    def config(self) -> Config:
        return Config.load(self.root)

    def _require(self) -> None:
        if not self.brain_dir.is_dir() or not self.control.is_dir():
            raise ValidationError("not an Agent Brain repository; run init")
        reject_symlink_chain(self.brain_dir, self.root)
        reject_symlink_chain(self.control, self.root)

    def _quarantine(self, data: bytes, error: SecurityError) -> None:
        digest = sha256(data)
        target = self.control / "quarantine" / f"{digest}.json"
        reject_symlink_chain(target, self.control)
        atomic_write(target, json_bytes({"sha256": digest, "reasons": error.reasons}))

    def _scan(self, data: bytes) -> str:
        try:
            return scan(data, self.config().max_ingest_bytes).digest
        except SecurityError as exc:
            self._quarantine(data, exc)
            raise

    @staticmethod
    def slug(value: str) -> str:
        slug = SLUG_RE.sub("-", value.lower()).strip("-")[:80]
        if not slug:
            raise ValidationError("title cannot produce a safe slug")
        return slug

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())

    def remember(self, title: str, content: str, *, page_type: str = "note", tags: Iterable[str] = (),
                 source: str = "capture", page_id: str | None = None) -> dict[str, Any]:
        self._require()
        now = utc_now()
        slug = self.slug(page_id or title)
        rel = safe_relative(f"pages/{slug}.md")
        path = self.brain_dir / rel
        reject_symlink_chain(path, self.brain_dir)
        if path.exists():
            raise ValidationError("page slug already exists")
        document_id = self._new_id()
        meta: dict[str, object] = {
            "id": document_id, "slug": slug, "title": title, "type": page_type, "created": now,
            "updated": now, "tags": sorted(set(tags)), "source": source, "status": "active",
        }
        data = markdown.render(meta, content.rstrip() + "\n").encode()
        digest = self._scan(data)
        atomic_write(path, data)
        self._append_timeline(slug, title, now)
        self.sync()
        self._audit("remember", digest, {"id": document_id, "slug": slug})
        return {"id": document_id, "slug": slug, "path": str(rel), "sha256": digest}

    capture = remember

    def _append_timeline(self, slug: str, title: str, now: str) -> None:
        day = now[:10]
        path = self.brain_dir / "timeline" / f"{day}.md"
        reject_symlink_chain(path, self.brain_dir)
        entry = (f"- {now} [[brain/pages/{slug}|{title}]] "
                 "<!-- agent-brain:relationship=memory -->\n")
        if path.exists():
            reject_symlink_chain(path, self.brain_dir)
            data = path.read_bytes() + entry.encode()
        else:
            meta = {"id": str(uuid.uuid5(REPORT_NAMESPACE, f"timeline:{day}")), "slug": f"timeline-{day}",
                    "title": f"Timeline {day}", "type": "timeline", "created": now, "updated": now}
            data = markdown.render(meta, entry).encode()
        self._scan(data)
        # Atomic replacement keeps timeline writes crash-safe; the directory is fsynced by atomic_write.
        atomic_write(path, data)

    def _audit(self, action: str, object_hash: str, detail: dict[str, Any]) -> None:
        entry = append_audit(self.control, at=utc_now(), action=action, object_hash=object_hash, detail=detail)
        with connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO audit(seq,at,action,object_hash,detail,prev_hash,event_hash) VALUES(?,?,?,?,?,?,?)",
                         (entry["seq"], entry["at"], entry["action"], entry["object_hash"],
                          json.dumps(entry["detail"], sort_keys=True, separators=(",", ":")), entry["prev_hash"], entry["event_hash"]))

    def register_source(self, name: str, source_root: str | Path, tier: str = "cache") -> dict[str, str]:
        self._require()
        if tier not in {"tracked", "cache"} or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
            raise ValidationError("invalid source name or tier")
        candidate = Path(source_root)
        if candidate.is_symlink():
            raise SecurityError(["symlink"])
        resolved = candidate.resolve(strict=True)
        allowed = [Path(p).resolve(strict=True) for p in self.config().allowlisted_roots]
        matches = [base for base in allowed if resolved == base or base in resolved.parents]
        if not matches:
            raise SecurityError(["source_root_not_allowlisted"])
        reject_symlink_chain(resolved, matches[0])
        sources = load_sources(self.root)
        sources[name] = {"root": str(resolved), "tier": tier}
        save_sources(self.root, sources)
        self._audit("source.register", sha256(str(resolved).encode()), {"name": name, "tier": tier})
        return {"name": name, "root": str(resolved), "tier": tier}

    def ingest(self, source: str, relative_path: str) -> dict[str, Any]:
        self._require()
        rel = safe_relative(relative_path)
        sources = load_sources(self.root)
        if source not in sources:
            raise ValidationError("unknown source")
        src_root = Path(sources[source]["root"])
        reject_symlink_chain(src_root / rel, src_root)
        src = contained(src_root, src_root / rel, must_exist=True)
        if not src.is_file():
            raise ValidationError("source is not a regular file")
        data = src.read_bytes()
        digest = self._scan(data)
        doc = markdown.parse(data.decode("utf-8"))
        tier = sources[source]["tier"]
        destination_root = self.brain_dir / "sources" if tier == "tracked" else self.control / "cache"
        destination = destination_root / source / rel
        reject_symlink_chain(destination, destination_root)
        if destination.suffix.lower() != ".md":
            raise ValidationError("only Markdown sources are supported")
        atomic_write(destination, data)
        with connect(self.db_path) as conn:
            conn.execute("INSERT INTO source_checkpoints(source_id,source_path,content_hash,checked_at) VALUES(?,?,?,?) "
                         "ON CONFLICT(source_id,source_path) DO UPDATE SET content_hash=excluded.content_hash,checked_at=excluded.checked_at",
                         (source, str(rel), digest, utc_now()))
        self.sync()
        self._audit("source.ingest", digest, {"source": source, "id": doc.meta["id"], "tier": tier})
        return {"source": source, "id": doc.meta["id"], "slug": doc.meta["slug"], "tier": tier, "sha256": digest}

    def _documents(self) -> list[tuple[Path, str]]:
        result: list[tuple[Path, str]] = []
        for base, tier in ((self.brain_dir, "tracked"), (self.control / "cache", "cache")):
            for path in sorted(base.rglob("*.md")):
                reject_symlink_chain(path, base)
                if path.is_file():
                    result.append((path, tier))
        return result

    def _parsed_documents(self) -> list[tuple[Path, str, markdown.Document, str]]:
        parsed: list[tuple[Path, str, markdown.Document, str]] = []
        ids: set[str] = set()
        slugs: set[str] = set()
        paths: set[str] = set()
        for path, tier in self._documents():
            data = path.read_bytes()
            digest = self._scan(data)
            doc = markdown.parse(data.decode("utf-8"))
            document_id, slug = str(doc.meta["id"]), str(doc.meta["slug"])
            rel = str(path.relative_to(self.root))
            if document_id in ids or slug in slugs or rel in paths:
                raise ValidationError("duplicate document id, slug, or path")
            ids.add(document_id); slugs.add(slug); paths.add(rel)
            parsed.append((path, tier, doc, digest))
        return parsed

    def _populate(self, conn: sqlite3.Connection, parsed: list[tuple[Path, str, markdown.Document, str]], rebuild: bool) -> None:
        slug_ids = {str(doc.meta["slug"]): str(doc.meta["id"]) for _, _, doc, _ in parsed}
        id_set = {str(doc.meta["id"]) for _, _, doc, _ in parsed}
        with transaction(conn):
            conn.execute("UPDATE pages SET deleted=1")
            for path, tier, doc, digest in parsed:
                document_id, slug = str(doc.meta["id"]), str(doc.meta["slug"])
                rel = str(path.relative_to(self.root))
                forgotten = int(doc.meta.get("status") == "forgotten")
                args = (document_id, slug, rel, str(doc.meta["title"]), str(doc.meta["type"]), str(doc.meta["created"]),
                        str(doc.meta["updated"]), doc.body, digest, tier, utc_now(), forgotten)
                conn.execute("INSERT INTO pages(id,slug,path,title,type,created,updated,body,content_hash,storage_tier,indexed_at,deleted) "
                             "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET slug=excluded.slug,path=excluded.path,"
                             "title=excluded.title,type=excluded.type,created=excluded.created,updated=excluded.updated,body=excluded.body,"
                             "content_hash=excluded.content_hash,storage_tier=excluded.storage_tier,indexed_at=excluded.indexed_at,deleted=excluded.deleted", args)
            # Populate relations only after every target page exists; this is required for a clean rebuild with FKs enabled.
            conn.execute("DELETE FROM pages_fts")
            conn.execute("DELETE FROM links")
            conn.execute("DELETE FROM facts")
            for _path, _tier, doc, _digest in parsed:
                document_id, slug = str(doc.meta["id"]), str(doc.meta["slug"])
                forgotten = int(doc.meta.get("status") == "forgotten")
                if forgotten:
                    continue
                conn.execute("INSERT INTO pages_fts(page_id,slug,title,body) VALUES(?,?,?,?)", (document_id, slug, doc.meta["title"], doc.body))
                link_rows = []
                for kind, target, line in markdown.links(doc.body):
                    target_id = target if target in id_set else slug_ids.get(target)
                    link_rows.append((document_id, target, target_id, kind, line))
                conn.executemany("INSERT INTO links(source_id,target_ref,target_id,link_type,line) VALUES(?,?,?,?,?)", link_rows)
                conn.executemany("INSERT INTO facts(page_id,subject,predicate,object,line) VALUES(?,?,?,?,?)",
                                 ((document_id, *fact) for fact in markdown.facts(doc.body)))
            conn.execute("DELETE FROM pages_fts WHERE page_id IN (SELECT id FROM pages WHERE deleted=1)")
            if rebuild:
                for entry in verify_audit(self.control)["entries"]:
                    conn.execute("INSERT INTO audit(seq,at,action,object_hash,detail,prev_hash,event_hash) VALUES(?,?,?,?,?,?,?)",
                                 (entry["seq"], entry["at"], entry["action"], entry["object_hash"],
                                  json.dumps(entry["detail"], sort_keys=True, separators=(",", ":")), entry["prev_hash"], entry["event_hash"]))

    def sync(self, *, rebuild: bool = False) -> dict[str, int]:
        self._require()
        parsed = self._parsed_documents()
        replacement = self.control / "index.sqlite3.new"
        if rebuild:
            if replacement.exists():
                replacement.unlink()
                fsync_directory(replacement.parent)
            conn = connect(replacement)
        else:
            conn = connect(self.db_path)
        try:
            self._populate(conn, parsed, rebuild)
            if rebuild:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.execute("PRAGMA journal_mode=DELETE")
            conn.close()
            if rebuild:
                os.replace(replacement, self.db_path)
                self.db_path.chmod(0o600)
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(self.db_path) + suffix)
                    if sidecar.exists() and not sidecar.is_symlink():
                        sidecar.unlink()
                fsync_directory(self.control)
            return {"indexed": len(parsed), "deleted": 0 if rebuild else self._deleted_count()}
        except BaseException:
            conn.close()
            if rebuild and replacement.exists():
                replacement.unlink()
                fsync_directory(replacement.parent)
            raise

    def rebuild(self) -> dict[str, int]:
        return self.sync(rebuild=True)

    def _deleted_count(self) -> int:
        with connect(self.db_path, initialize=False) as conn:
            return int(conn.execute("SELECT count(*) FROM pages WHERE deleted=1").fetchone()[0])

    @staticmethod
    def _span(body: str, tokens: list[str]) -> tuple[int, int, str]:
        lines = body.splitlines(keepends=True) or [""]
        lowered = [line.casefold() for line in lines]
        index = next((i for i, line in enumerate(lowered) if any(t.casefold() in line for t in tokens)), 0)
        return index + 1, index + 1, sha256(lines[index].encode())

    def _citation(self, row: sqlite3.Row, tokens: list[str], line: int | None = None) -> dict[str, Any]:
        if line is None:
            start, end, span_hash = self._span(row["body"], tokens)
        else:
            lines = row["body"].splitlines(keepends=True)
            selected = lines[line - 1] if 0 < line <= len(lines) else ""
            start = end = line
            span_hash = sha256(selected.encode())
        return {"path": row["path"], "document_id": row["id"], "slug": row["slug"],
                "content_hash": row["content_hash"], "start_line": start, "end_line": end, "span_hash": span_hash}

    def verify_citation(self, citation: dict[str, Any]) -> dict[str, Any]:
        self._require()
        required = {"path", "document_id", "slug", "content_hash", "start_line", "end_line", "span_hash"}
        if not isinstance(citation, dict) or set(citation) != required:
            raise ValidationError("invalid citation")
        try:
            path = contained(self.root, self.root / safe_relative(str(citation["path"])), must_exist=True)
            data = path.read_bytes()
            doc = markdown.parse(data.decode("utf-8"))
            lines = doc.body.splitlines(keepends=True)
            start, end = int(citation["start_line"]), int(citation["end_line"])
            span = "".join(lines[start - 1:end]).encode() if 1 <= start <= end <= len(lines) else b""
            valid = (doc.meta["id"] == citation["document_id"] and doc.meta["slug"] == citation["slug"]
                     and sha256(data) == citation["content_hash"] and sha256(span) == citation["span_hash"])
        except (OSError, UnicodeError, ValueError, SecurityError, ValidationError):
            valid = False
        return {"valid": valid, "stale": not valid}

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        self._require()
        if not query.strip() or limit < 1 or limit > 100 or len(query) > 4096:
            raise ValidationError("invalid search query or limit")
        tokens = re.findall(r"\w+", query, flags=re.UNICODE)[:32]
        if not tokens:
            raise ValidationError("search query has no searchable terms")
        fts_query = " ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        with connect(self.db_path, initialize=False) as conn:
            try:
                rows = conn.execute("SELECT p.*,snippet(pages_fts,3,'[',']',' … ',18) snippet,bm25(pages_fts) score "
                                    "FROM pages_fts JOIN pages p ON p.id=pages_fts.page_id WHERE pages_fts MATCH ? AND p.deleted=0 "
                                    "ORDER BY score,p.id LIMIT ?", (fts_query, limit)).fetchall()
            except sqlite3.OperationalError as exc:
                raise ValidationError("invalid full-text query") from exc
        return [{"id": r["id"], "slug": r["slug"], "title": r["title"], "snippet": r["snippet"],
                 "score": round(float(r["score"]), 6), "updated": r["updated"], "citation": self._citation(r, tokens)} for r in rows]

    recall = search

    def _entity_row(self, reference: str) -> sqlite3.Row:
        self._require()
        with connect(self.db_path, initialize=False) as conn:
            row = conn.execute("SELECT * FROM pages WHERE (id=? OR slug=?) AND deleted=0", (reference, reference)).fetchone()
        if row is None:
            raise ValidationError("entity not found")
        return row

    def entity(self, reference: str) -> dict[str, Any]:
        row = self._entity_row(reference)
        with connect(self.db_path, initialize=False) as conn:
            outbound = [dict(x) for x in conn.execute("SELECT target_ref,target_id,link_type,line FROM links WHERE source_id=? ORDER BY target_ref", (row["id"],))]
            backlinks = [dict(x) for x in conn.execute("SELECT source_id,target_ref,link_type,line FROM links WHERE target_id=? ORDER BY source_id", (row["id"],))]
        return {"id": row["id"], "slug": row["slug"], "title": row["title"], "type": row["type"], "updated": row["updated"],
                "body": row["body"], "citation": self._citation(row, []), "links": outbound, "backlinks": backlinks}

    def _evidence(self, query: str, limit: int) -> dict[str, Any]:
        results = self.search(query, limit)
        ids = [r["id"] for r in results]
        contradictions: list[dict[str, Any]] = []
        stale: list[dict[str, Any]] = []
        cutoff = datetime.now(UTC) - timedelta(days=self.config().stale_after_days)
        with connect(self.db_path, initialize=False) as conn:
            if ids:
                marks = ",".join("?" for _ in ids)
                groups = conn.execute(f"SELECT subject,predicate,count(DISTINCT object) n FROM facts WHERE page_id IN ({marks}) "
                                      "GROUP BY subject,predicate HAVING n>1", ids).fetchall()
                for group in groups:
                    values = conn.execute(f"SELECT f.object,f.line,p.* FROM facts f JOIN pages p ON p.id=f.page_id "
                                          f"WHERE f.subject=? AND f.predicate=? AND f.page_id IN ({marks}) ORDER BY f.object,p.id",
                                          (group["subject"], group["predicate"], *ids)).fetchall()
                    contradictions.append({"subject": group["subject"], "predicate": group["predicate"],
                                           "evidence": [{"object": v["object"], "page_id": v["id"],
                                                         "citation": self._citation(v, [], v["line"])} for v in values]})
            for result in results:
                if datetime.fromisoformat(result["updated"].replace("Z", "+00:00")) < cutoff:
                    stale.append(result["citation"])
        return {"results": results, "contradictions": contradictions, "stale_evidence": stale,
                "gaps": [] if results else [f"No indexed evidence matched: {query}"]}

    def brief(self, query: str, limit: int = 5) -> dict[str, Any]:
        evidence = self._evidence(query, limit)
        summary = ("; ".join(f"{r['title']}: {r['snippet']}" for r in evidence["results"])
                   if evidence["results"] else "No supported answer is available from local evidence.")
        return {"answer": summary, **evidence}

    synthesize = brief

    def forget(self, reference: str) -> dict[str, Any]:
        row = self._entity_row(reference)
        path = contained(self.root, self.root / safe_relative(row["path"]), must_exist=True)
        reject_symlink_chain(path, self.root)
        document = markdown.parse(path.read_text(encoding="utf-8"))
        meta = dict(document.meta); meta["status"] = "forgotten"; meta["updated"] = utc_now()
        data = markdown.render(meta, document.body).encode()
        digest = self._scan(data)
        atomic_write(path, data)
        self.sync()
        self._audit("forget.soft", digest, {"id": row["id"], "slug": row["slug"]})
        return {"id": row["id"], "slug": row["slug"], "forgotten": True, "canonical_retained": True}

    def context_pack(self, query: str, max_bytes: int = 8192) -> dict[str, Any]:
        if not 256 <= max_bytes <= 1_048_576:
            raise ValidationError("invalid context pack budget")
        evidence = self._evidence(query, 25)
        packed: list[dict[str, Any]] = []; used = 0
        for item in evidence["results"]:
            encoded = json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
            if used + len(encoded) > max_bytes:
                break
            packed.append(item); used += len(encoded)
        return {"query": query, "items": packed, "bytes": used, "gaps": evidence["gaps"],
                "contradictions": evidence["contradictions"], "stale_evidence": evidence["stale_evidence"]}

    def delta(self, since: str) -> list[dict[str, Any]]:
        try:
            datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError("invalid timestamp") from exc
        with connect(self.db_path, initialize=False) as conn:
            rows = conn.execute("SELECT * FROM pages WHERE updated>=? ORDER BY updated,id", (since,)).fetchall()
        return [{"id": r["id"], "slug": r["slug"], "title": r["title"], "updated": r["updated"], "deleted": r["deleted"],
                 "citation": self._citation(r, [])} for r in rows]

    def export_archive(self, destination: str | Path) -> dict[str, Any]:
        self._require()
        destination = Path(destination).absolute()
        if destination.exists() or destination.parent.is_symlink():
            raise ValidationError("export destination already exists or is unsafe")
        files = [(p, p.relative_to(self.root)) for p in self.brain_dir.rglob("*") if p.is_file() and not p.is_symlink()]
        files.append((self.control / "config.toml", Path(".agent-brain/config.toml")))
        fd, tmp_name = tempfile.mkstemp(prefix=".agent-brain-export-", suffix=".zip", dir=destination.parent)
        os.close(fd); tmp = Path(tmp_name)
        try:
            with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path, rel in sorted(files, key=lambda x: str(x[1])):
                    archive.writestr(str(rel), path.read_bytes())
            with tmp.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(tmp, destination); fsync_directory(destination.parent)
        finally:
            if tmp.exists():
                tmp.unlink()
        return {"path": str(destination), "files": len(files)}

    def import_archive(self, archive_path: str | Path) -> dict[str, Any]:
        self._require()
        archive_path = Path(archive_path)
        if archive_path.is_symlink() or not archive_path.is_file():
            raise SecurityError(["unsafe_archive"])
        config = self.config(); staged: list[tuple[Path, bytes]] = []; names: set[str] = set(); total = 0; count = 0
        try:
            with zipfile.ZipFile(archive_path) as archive:
                infos = archive.infolist()
                if len(infos) > config.max_archive_files:
                    raise SecurityError(["archive_file_count_exceeded"])
                for info in infos:
                    rel = safe_relative(info.filename.rstrip("/"))
                    if info.filename in names:
                        raise SecurityError(["archive_duplicate_path"])
                    names.add(info.filename)
                    mode = info.external_attr >> 16
                    kind = stat.S_IFMT(mode)
                    if kind not in {0, stat.S_IFREG, stat.S_IFDIR} or kind == stat.S_IFLNK:
                        raise SecurityError(["archive_unsafe_file_type"])
                    if info.flag_bits & 0x1:
                        raise SecurityError(["archive_encrypted"])
                    total += info.file_size; count += int(not info.is_dir())
                    if info.file_size > config.max_ingest_bytes or total > config.max_archive_bytes:
                        raise SecurityError(["archive_size_exceeded"])
                    if info.compress_size and info.file_size > 1_048_576 and info.file_size > info.compress_size * 100:
                        raise SecurityError(["archive_compression_ratio"])
                    if info.is_dir():
                        continue
                    if not (rel.parts[0] == "brain" and rel.suffix.lower() == ".md"):
                        continue
                    data = archive.read(info)
                    if len(data) != info.file_size:
                        raise SecurityError(["archive_size_mismatch"])
                    self._scan(data); markdown.parse(data.decode("utf-8"))
                    target = contained(self.root, self.root / rel)
                    reject_symlink_chain(target.parent, self.root)
                    if target.exists():
                        raise ValidationError("import would overwrite existing content")
                    staged.append((target, data))
        except (zipfile.BadZipFile, RuntimeError) as exc:
            raise ValidationError("invalid archive") from exc
        for target, data in staged:
            atomic_write(target, data)
        self.sync()
        digest = sha256("".join(sorted(sha256(data) for _, data in staged)).encode())
        self._audit("import", digest, {"files": len(staged)})
        return {"imported": len(staged), "archive_files": count}

    def quarantine_list(self) -> list[dict[str, Any]]:
        self._require()
        records = []
        for path in sorted((self.control / "quarantine").glob("*.json")):
            reject_symlink_chain(path, self.control)
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValidationError("corrupted quarantine metadata") from exc
            if not isinstance(value, dict) or set(value) != {"sha256", "reasons"}:
                raise ValidationError("corrupted quarantine metadata")
            records.append(value)
        return records

    def canonical_hashes(self) -> dict[str, str]:
        self._require()
        return {str(path.relative_to(self.root)): sha256(path.read_bytes()) for path, tier in self._documents()
                if tier == "tracked" and "reports" not in path.relative_to(self.brain_dir).parts}

    def doctor(self) -> dict[str, Any]:
        issues: list[str] = []
        if not self.brain_dir.is_dir() or not self.control.is_dir():
            return {"ok": False, "issues": ["uninitialized_repository"], "checks": {}}
        checks: dict[str, Any] = {}
        obsidian_issues, obsidian_checks = obsidian_doctor_issues(self.root)
        issues.extend(obsidian_issues); checks.update(obsidian_checks)
        try:
            self.config(); load_sources(self.root); checks["config"] = "ok"
        except (ValidationError, SecurityError, OSError):
            issues.append("config_or_source_registry_invalid"); checks["config"] = "failed"
        try:
            parsed = self._parsed_documents(); checks["canonical_documents"] = len(parsed)
        except (ValidationError, SecurityError, OSError, UnicodeError):
            parsed = []; issues.append("canonical_documents_invalid"); checks["canonical_documents"] = "failed"
        try:
            audit = verify_audit(self.control); checks["audit_chain"] = len(audit["entries"])
        except (ValidationError, SecurityError, OSError):
            issues.append("audit_chain_invalid"); checks["audit_chain"] = "failed"
        try:
            with connect(self.db_path, initialize=False) as conn:
                integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
                indexed = {r["id"]: r["content_hash"] for r in conn.execute("SELECT id,content_hash FROM pages WHERE deleted=0")}
            expected = {str(doc.meta["id"]): digest for _, _, doc, digest in parsed}
            checks["database"] = integrity
            if integrity != "ok" or indexed != expected:
                issues.append("database_invalid_or_stale")
        except (sqlite3.DatabaseError, OSError):
            issues.append("database_corrupted_or_missing"); checks["database"] = "failed"
        return {"ok": not issues, "issues": issues, "checks": checks}

    verify = doctor

    def obsidian_status(self) -> dict[str, Any]:
        return inspect_obsidian(self.root)

    def status(self) -> dict[str, Any]:
        self._require()
        with connect(self.db_path, initialize=False) as conn:
            pages = conn.execute("SELECT count(*) FROM pages WHERE deleted=0").fetchone()[0]
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {"pages": pages, "integrity": integrity, "root": str(self.root)}

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .brain import Brain, REPORT_NAMESPACE
from .db import connect
from .errors import AgentBrainError
from .markdown import links, facts, render
from .util import atomic_write, fsync_directory, reject_symlink_chain, sha256, utc_now


class DreamLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "DreamLock":
        if self.path.is_symlink():
            raise AgentBrainError("unsafe dream lock")
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.write(self.fd, str(os.getpid()).encode()); os.fsync(self.fd); fsync_directory(self.path.parent)
        except FileExistsError as exc:
            try:
                pid = int(self.path.read_text(encoding="ascii"))
                if pid < 1:
                    raise ValueError
                os.kill(pid, 0)
            except ProcessLookupError:
                if self.path.is_file() and not self.path.is_symlink():
                    self.path.unlink(); fsync_directory(self.path.parent)
                    return self.__enter__()
                raise AgentBrainError("unsafe dream lock") from exc
            except (OSError, ValueError):
                raise AgentBrainError("dream cycle lock is invalid or active") from exc
            raise AgentBrainError("dream cycle is already running") from exc
        return self

    def __exit__(self, *_: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink(); fsync_directory(self.path.parent)
        except FileNotFoundError:
            pass


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _analyze(brain: Brain, day: str) -> dict[str, Any]:
    documents = [(path, doc) for path, tier, doc, _ in brain._parsed_documents()
                 if tier == "tracked" and doc.meta["type"] != "dream-report"]
    by_id = {str(doc.meta["id"]): doc for _, doc in documents}
    by_slug = {str(doc.meta["slug"]): str(doc.meta["id"]) for _, doc in documents}
    link_rows: list[dict[str, Any]] = []
    fact_rows: list[dict[str, Any]] = []
    for _path, doc in documents:
        source_id = str(doc.meta["id"])
        for kind, target, line in links(doc.body):
            link_rows.append({"source_id": source_id, "target_ref": target,
                              "target_id": target if target in by_id else by_slug.get(target), "link_type": kind, "line": line})
        for subject, predicate, object_, line in facts(doc.body):
            fact_rows.append({"subject": subject, "predicate": predicate, "object": object_, "page_id": source_id, "line": line})

    duplicate_groups: dict[str, list[str]] = defaultdict(list)
    for _, doc in documents:
        duplicate_groups[_normalize(doc.body)].append(str(doc.meta["id"]))
    duplicates = [sorted(ids) for key, ids in sorted(duplicate_groups.items()) if len(ids) > 1]
    fact_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in fact_rows:
        fact_groups[(row["subject"], row["predicate"])].append({"object": row["object"], "page_id": row["page_id"], "line": row["line"]})
    contradictions = [{"subject": subject, "predicate": predicate, "evidence": sorted(evidence, key=lambda x: (x["object"], x["page_id"]))}
                      for (subject, predicate), evidence in sorted(fact_groups.items())
                      if len({item["object"] for item in evidence}) > 1]
    connected = {row["source_id"] for row in link_rows} | {row["target_id"] for row in link_rows if row["target_id"]}
    broken = [{k: v for k, v in row.items() if k != "target_id"} for row in link_rows if row["target_id"] is None]
    cutoff = datetime.fromisoformat(day + "T00:00:00+00:00") - timedelta(days=brain.config().stale_after_days)
    stale = sorted(str(doc.meta["id"]) for _, doc in documents
                   if datetime.fromisoformat(str(doc.meta["updated"]).replace("Z", "+00:00")) < cutoff)
    backlinks: dict[str, list[str]] = defaultdict(list)
    for row in link_rows:
        if row["target_id"]:
            backlinks[row["target_id"]].append(row["source_id"])
    return {"validated": len(documents), "pages": len(documents), "links": len(link_rows),
            "backlinks": {key: sorted(set(value)) for key, value in sorted(backlinks.items())},
            "broken_links": sorted(broken, key=lambda x: (x["source_id"], x["target_ref"], x["line"])),
            "duplicate_candidates": duplicates, "contradictions": contradictions, "stale": stale,
            "orphans": sorted(set(by_id) - connected), "review_required": bool(broken or duplicates or contradictions or stale)}


def _report(result: dict[str, Any], day: str) -> bytes:
    def section(title: str, value: object) -> str:
        return f"## {title}\n\n```json\n{json.dumps(value, indent=2, sort_keys=True)}\n```\n"
    body = "# Daily synthesis\n\nFindings are proposals for human review. This report never edits ordinary memories.\n\n"
    body += section("Summary", {k: result[k] for k in ("validated", "pages", "links", "review_required")})
    for heading, key in (("Broken links", "broken_links"), ("Duplicate candidates", "duplicate_candidates"),
                         ("Contradictions", "contradictions"), ("Stale evidence", "stale"),
                         ("Orphans", "orphans"), ("Backlinks", "backlinks")):
        body += "\n" + section(heading, result[key])
    stamp = f"{day}T00:00:00Z"
    meta: dict[str, object] = {"id": str(uuid.uuid5(REPORT_NAMESPACE, f"dream:{day}")), "slug": f"dream-{day}",
        "title": f"Dream cycle {day}", "type": "dream-report", "created": stamp, "updated": stamp,
        "tags": ["dream", "maintenance"], "source": "dream", "status": "active"}
    return render(meta, body).encode()


def run_dream(brain: Brain, *, dry_run: bool = False) -> dict[str, Any]:
    brain._require()
    with DreamLock(brain.control / "dream.lock"):
        started = utc_now(); day = datetime.now(UTC).date().isoformat(); run_id: int | None = None
        if not dry_run:
            # A corrupt index can be replaced from canonical files before run bookkeeping.
            try:
                brain.sync()
            except sqlite3.DatabaseError:
                brain.rebuild()
            with connect(brain.db_path) as conn:
                conn.execute("UPDATE runs SET finished=?,status='interrupted',summary=? WHERE kind='dream' AND status='running'",
                             (started, json.dumps({"error_type": "InterruptedRun"})))
                cursor = conn.execute("INSERT INTO runs(kind,started,status,dry_run,summary) VALUES(?,?,?,?,?)",
                                      ("dream", started, "running", 0, "{}"))
                run_id = int(cursor.lastrowid)
        try:
            result = _analyze(brain, day); result["dry_run"] = dry_run
            result["integrity"] = "not_checked" if dry_run else "pending"
            if dry_run:
                return result
            report = _report(result, day); brain._scan(report)
            report_path = brain.brain_dir / "reports" / f"dream-{day}.md"
            reject_symlink_chain(report_path, brain.brain_dir)
            if not report_path.exists() or report_path.read_bytes() != report:
                atomic_write(report_path, report)
            brain.sync()
            with connect(brain.db_path) as conn:
                integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
                backup_tmp = brain.control / "backups" / f"index-{day}.sqlite3.new"
                backup_final = brain.control / "backups" / f"index-{day}.sqlite3"
                reject_symlink_chain(backup_tmp, brain.control)
                reject_symlink_chain(backup_final, brain.control)
                if backup_tmp.exists():
                    backup_tmp.unlink(); fsync_directory(backup_tmp.parent)
                target = sqlite3.connect(backup_tmp)
                try:
                    conn.backup(target); target.commit()
                finally:
                    target.close()
                with backup_tmp.open("rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(backup_tmp, backup_final); fsync_directory(backup_final.parent)
            result["integrity"] = integrity
            summary = json.dumps(result, sort_keys=True, separators=(",", ":"))
            with connect(brain.db_path) as conn:
                conn.execute("UPDATE runs SET finished=?,status='ok',summary=? WHERE id=?", (utc_now(), summary, run_id))
            brain._audit("dream", sha256(report), {"run_id": run_id, "report": f"brain/reports/dream-{day}.md"})
            return result
        except BaseException as exc:
            if run_id is not None:
                try:
                    with connect(brain.db_path) as conn:
                        conn.execute("UPDATE runs SET finished=?,status='failed',summary=? WHERE id=?",
                                     (utc_now(), json.dumps({"error_type": type(exc).__name__}), run_id))
                except sqlite3.DatabaseError:
                    pass
            raise

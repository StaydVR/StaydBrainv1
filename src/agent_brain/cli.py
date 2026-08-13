from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .brain import Brain
from .dream import run_dream
from .errors import AgentBrainError
from .server import serve


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent-brain", description="Local, security-first agent memory")
    p.add_argument("--root", default=".", help="repository root")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    remember = sub.add_parser("remember", aliases=["capture"])
    remember.add_argument("title"); remember.add_argument("content"); remember.add_argument("--type", default="note")
    remember.add_argument("--tag", action="append", default=[])
    search = sub.add_parser("search", aliases=["recall"])
    search.add_argument("query"); search.add_argument("--limit", type=int, default=10)
    entity = sub.add_parser("entity"); entity.add_argument("id")
    synth = sub.add_parser("synthesize", aliases=["brief"]); synth.add_argument("query"); synth.add_argument("--limit", type=int, default=5)
    forget = sub.add_parser("forget"); forget.add_argument("id")
    pack = sub.add_parser("context-pack"); pack.add_argument("query"); pack.add_argument("--max-bytes", type=int, default=8192)
    delta = sub.add_parser("delta"); delta.add_argument("since")
    source = sub.add_parser("source-add"); source.add_argument("name"); source.add_argument("path"); source.add_argument("--tier", choices=("tracked", "cache"), default="cache")
    ingest = sub.add_parser("ingest"); ingest.add_argument("source"); ingest.add_argument("path")
    sync = sub.add_parser("sync"); sync.add_argument("--rebuild", action="store_true")
    sub.add_parser("rebuild")
    dream = sub.add_parser("dream"); dream.add_argument("--dry-run", action="store_true")
    export = sub.add_parser("export"); export.add_argument("path")
    imp = sub.add_parser("import"); imp.add_argument("path")
    sub.add_parser("status")
    sub.add_parser("obsidian", aliases=["vault-status"])
    sub.add_parser("doctor")
    sub.add_parser("verify")
    sub.add_parser("quarantine-list")
    citation = sub.add_parser("citation-verify"); citation.add_argument("citation", help="citation JSON object")
    sub.add_parser("serve")
    return p


def execute(args: argparse.Namespace) -> Any:
    if args.command == "init":
        return Brain.init(args.root).status()
    brain = Brain(args.root)
    if args.command in {"remember", "capture"}: return brain.remember(args.title, args.content, page_type=args.type, tags=args.tag)
    if args.command in {"search", "recall"}: return brain.search(args.query, args.limit)
    if args.command == "entity": return brain.entity(args.id)
    if args.command in {"synthesize", "brief"}: return brain.brief(args.query, args.limit)
    if args.command == "forget": return brain.forget(args.id)
    if args.command == "context-pack": return brain.context_pack(args.query, args.max_bytes)
    if args.command == "delta": return brain.delta(args.since)
    if args.command == "source-add": return brain.register_source(args.name, args.path, args.tier)
    if args.command == "ingest": return brain.ingest(args.source, args.path)
    if args.command == "sync": return brain.sync(rebuild=args.rebuild)
    if args.command == "rebuild": return brain.rebuild()
    if args.command == "dream": return run_dream(brain, dry_run=args.dry_run)
    if args.command == "export": return brain.export_archive(args.path)
    if args.command == "import": return brain.import_archive(args.path)
    if args.command == "status": return brain.status()
    if args.command in {"obsidian", "vault-status"}: return brain.obsidian_status()
    if args.command in {"doctor", "verify"}: return brain.doctor()
    if args.command == "quarantine-list": return brain.quarantine_list()
    if args.command == "citation-verify":
        try:
            citation = json.loads(args.citation)
        except json.JSONDecodeError as exc:
            raise AgentBrainError("citation must be valid JSON") from exc
        return brain.verify_citation(citation)
    if args.command == "serve":
        serve(brain)
        return None
    raise AgentBrainError("unknown command")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        if result is not None:
            print(json.dumps(result, indent=2, sort_keys=True))
        if args.command in {"doctor", "verify"} and isinstance(result, dict) and not result.get("ok"):
            return 1
        return 0
    except (AgentBrainError, OSError, sqlite3.Error, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

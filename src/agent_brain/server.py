from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any, TextIO

from .brain import Brain
from .errors import AgentBrainError


READ_VERBS = {"recall", "entity", "synthesize", "context-pack", "delta", "status"}
WRITE_VERBS = {"remember"}


def dispatch(brain: Brain, request: dict[str, Any], *, allow_write: bool = False) -> Any:
    verb = request.get("verb")
    args = request.get("args", {})
    if verb not in READ_VERBS | WRITE_VERBS or not isinstance(args, dict):
        raise AgentBrainError("unsupported verb or arguments")
    if verb in WRITE_VERBS and not allow_write:
        raise AgentBrainError("write verb disabled; restart serve with explicit --allow-write capability")
    if verb == "recall":
        return brain.recall(str(args.get("query", "")), int(args.get("limit", 10)))
    if verb == "remember":
        return brain.remember(str(args.get("title", "")), str(args.get("content", "")),
                              page_type=str(args.get("type", "note")), tags=args.get("tags", ()))
    if verb == "entity":
        return brain.entity(str(args.get("id", "")))
    if verb == "synthesize":
        return brain.synthesize(str(args.get("query", "")), int(args.get("limit", 5)))
    if verb == "context-pack":
        return brain.context_pack(str(args.get("query", "")), int(args.get("max_bytes", 8192)))
    if verb == "delta":
        return brain.delta(str(args.get("since", "")))
    return brain.status()


def serve(
    brain: Brain, source: TextIO = sys.stdin, sink: TextIO = sys.stdout, *, allow_write: bool = False
) -> None:
    for line in source:
        request: Any = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise AgentBrainError("request must be a JSON object")
            result = dispatch(brain, request, allow_write=allow_write)
            response = {"id": request.get("id"), "ok": True, "result": result}
        except (AgentBrainError, ValueError, TypeError, OSError, sqlite3.Error, UnicodeError) as exc:
            response = {"id": request.get("id") if isinstance(request, dict) else None,
                        "ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        sink.write(json.dumps(response, sort_keys=True) + "\n")
        sink.flush()

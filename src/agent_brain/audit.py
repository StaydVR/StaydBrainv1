from __future__ import annotations

import json
import fcntl
import os
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .util import append_durable, atomic_write, json_bytes, reject_symlink_chain, sha256


GENESIS = "0" * 64


def _payload(entry: dict[str, Any]) -> bytes:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def paths(control: Path) -> tuple[Path, Path]:
    return control / "audit.jsonl", control / "state" / "audit-head.json"


def verify(control: Path) -> dict[str, Any]:
    log_path, head_path = paths(control)
    for path in (log_path, head_path):
        reject_symlink_chain(path, control)
    previous = GENESIS
    entries: list[dict[str, Any]] = []
    if log_path.exists():
        try:
            lines = log_path.read_bytes().splitlines()
        except OSError as exc:
            raise ValidationError("audit log is unreadable") from exc
        for expected, line in enumerate(lines, 1):
            try:
                entry = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValidationError("audit log is malformed") from exc
            required = {"seq", "at", "action", "object_hash", "detail", "prev_hash", "event_hash"}
            if not isinstance(entry, dict) or set(entry) != required or entry["seq"] != expected:
                raise ValidationError("audit log sequence is invalid")
            claimed = entry.pop("event_hash")
            computed = sha256(_payload(entry))
            entry["event_hash"] = claimed
            if entry["prev_hash"] != previous or claimed != computed:
                raise ValidationError("audit log hash chain is invalid")
            previous = claimed
            entries.append(entry)
    if not head_path.exists():
        if entries:
            raise ValidationError("audit head is missing")
        return {"ok": True, "entries": [], "head": GENESIS}
    try:
        head = json.loads(head_path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("audit head is malformed") from exc
    if head != {"seq": len(entries), "event_hash": previous}:
        raise ValidationError("audit truncation or head tampering detected")
    return {"ok": True, "entries": entries, "head": previous}


def append(control: Path, *, at: str, action: str, object_hash: str, detail: dict[str, Any]) -> dict[str, Any]:
    lock_path = control / "audit.lock"
    reject_symlink_chain(lock_path, control)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        state = verify(control)
        entry: dict[str, Any] = {
            "seq": len(state["entries"]) + 1, "at": at, "action": action,
            "object_hash": object_hash, "detail": detail, "prev_hash": state["head"],
        }
        entry["event_hash"] = sha256(_payload(entry))
        log_path, head_path = paths(control)
        append_durable(log_path, _payload(entry) + b"\n")
        atomic_write(head_path, json_bytes({"seq": entry["seq"], "event_hash": entry["event_hash"]}))
        return entry
    finally:
        os.close(fd)

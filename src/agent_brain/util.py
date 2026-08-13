from __future__ import annotations

import hashlib
import json
import os
import tempfile
from urllib.parse import unquote
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import SecurityError


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fsync_directory(path: Path) -> None:
    """Persist directory-entry changes made by rename/create/unlink."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        fsync_directory(path.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def safe_relative(value: str) -> Path:
    # ZIP and URL producers commonly use either separator regardless of host OS.
    if "\\" in value:
        raise SecurityError(["path_traversal"])
    decoded = value
    for _ in range(2):
        decoded = unquote(decoded)
    if decoded != value and ("\\" in decoded or any(part in {"", ".", ".."} for part in Path(decoded).parts)):
        raise SecurityError(["path_traversal"])
    candidate = Path(value)
    if value in {".", ".."} or not candidate.parts:
        raise SecurityError(["path_traversal"])
    if candidate.is_absolute() or not value or "\x00" in value:
        raise SecurityError(["unsafe_path"])
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise SecurityError(["path_traversal"])
    return candidate


def contained(root: Path, candidate: Path, *, must_exist: bool = False) -> Path:
    base = root.resolve(strict=True)
    resolved = candidate.resolve(strict=must_exist)
    if resolved != base and base not in resolved.parents:
        raise SecurityError(["path_outside_allowlist"])
    return resolved


def reject_symlink_chain(path: Path, stop: Path) -> None:
    current = path
    stop = stop.resolve(strict=True)
    while True:
        if current.is_symlink():
            raise SecurityError(["symlink"])
        if current == stop:
            return
        if current.parent == current:
            raise SecurityError(["path_outside_allowlist"])
        current = current.parent


def append_durable(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Append without following a final symlink, then fsync file and directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    if not existed:
        fsync_directory(path.parent)

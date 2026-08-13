from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import ValidationError
from .util import atomic_write, json_bytes, reject_symlink_chain


DEFAULT_CONFIG = """# Agent Brain v0.1 configuration
version = 1
max_ingest_bytes = 1048576
stale_after_days = 90
max_archive_files = 256
max_archive_bytes = 8388608
allowlisted_roots = []
"""


@dataclass(frozen=True)
class Config:
    version: int = 1
    max_ingest_bytes: int = 1_048_576
    stale_after_days: int = 90
    max_archive_files: int = 256
    max_archive_bytes: int = 8_388_608
    allowlisted_roots: tuple[str, ...] = ()

    @classmethod
    def load(cls, root: Path) -> "Config":
        path = root / ".agent-brain" / "config.toml"
        if not path.is_file() or path.is_symlink():
            raise ValidationError("missing or unsafe config; run init")
        try:
            if path.stat().st_size > 65_536:
                raise ValidationError("config is too large")
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
            allowed = {"version", "max_ingest_bytes", "stale_after_days", "max_archive_files", "max_archive_bytes", "allowlisted_roots"}
            if set(raw) - allowed:
                raise ValidationError("unknown config keys")
            value = cls(
                version=int(raw.get("version", 1)),
                max_ingest_bytes=int(raw.get("max_ingest_bytes", 1_048_576)),
                stale_after_days=int(raw.get("stale_after_days", 90)),
                max_archive_files=int(raw.get("max_archive_files", 256)),
                max_archive_bytes=int(raw.get("max_archive_bytes", 8_388_608)),
                allowlisted_roots=tuple(str(x) for x in raw.get("allowlisted_roots", [])),
            )
        except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError) as exc:
            raise ValidationError("invalid config") from exc
        if (value.version != 1 or not 1 <= value.max_ingest_bytes <= 64 * 1024 * 1024
                or not 1 <= value.stale_after_days <= 36_500
                or not 1 <= value.max_archive_files <= 10_000
                or not value.max_ingest_bytes <= value.max_archive_bytes <= 256 * 1024 * 1024):
            raise ValidationError("unsupported or invalid config values")
        for item in value.allowlisted_roots:
            candidate = Path(item)
            if (not candidate.is_absolute() or "\x00" in item or candidate.is_symlink()
                    or not candidate.is_dir()):
                raise ValidationError("allowlisted roots must be absolute non-symlink paths")
            reject_symlink_chain(candidate, Path(candidate.anchor))
        return value


def load_sources(root: Path) -> dict[str, dict[str, str]]:
    path = root / ".agent-brain" / "state" / "sources.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValidationError("invalid source registry") from exc
    if not isinstance(data, dict) or len(data) > 1_000:
        raise ValidationError("invalid source registry")
    for name, value in data.items():
        if (not isinstance(name, str) or not isinstance(value, dict)
                or set(value) != {"root", "tier"} or value["tier"] not in {"tracked", "cache"}
                or not isinstance(value["root"], str) or not Path(value["root"]).is_absolute()):
            raise ValidationError("invalid source registry")
        root_path = Path(value["root"])
        if root_path.exists():
            reject_symlink_chain(root_path, Path(root_path.anchor))
    return data


def save_sources(root: Path, sources: dict[str, dict[str, str]]) -> None:
    atomic_write(root / ".agent-brain" / "state" / "sources.json", json_bytes(sources))

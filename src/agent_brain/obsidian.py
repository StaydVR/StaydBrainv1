from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .util import atomic_write, json_bytes, reject_symlink_chain


HOME_NAME = "AGENT-BRAIN.md"
SETTINGS_RELATIVE = Path(".obsidian/app.json")
PORTABLE_SETTINGS: dict[str, object] = {
    "alwaysUpdateLinks": False,
    "newFileFolderPath": "brain/pages",
    "newFileLocation": "folder",
    "useMarkdownLinks": False,
}
GITIGNORE_RULES = (".agent-brain/", ".obsidian/*", "!.obsidian/app.json")
HOME = """# Agent Brain

This repository root is the Obsidian vault. Agent Brain works without Obsidian; this page is only a human-facing map of the local files.

## Canonical memory

- [Memory pages](brain/pages/)
- [Imported canonical sources](brain/sources/)
- [Timeline](brain/timeline/)
- [Dream reports](brain/reports/)

Markdown under `brain/` is canonical, human-readable knowledge. Edit it deliberately, review Git diffs, then run `agent-brain sync`. Dream reports are review artifacts and do not silently change ordinary memories.

## Project guides

- [[README|Project overview]]
- [[docs/architecture|Architecture]]
- [[docs/obsidian|Obsidian workflow]]
- [[docs/dream-cycle|Dream cycle]]
- [[skills/RESOLVER|Skillpack resolver]]
- [Skillpack files](skills/)

## Canonical versus derived storage

`brain/` is the system of record. `.agent-brain/` is private, gitignored runtime storage containing the disposable SQLite index, caches, quarantine metadata, audit state, and backups. Do not sync or publish `.agent-brain/`; rebuild its index from canonical Markdown when needed.

Obsidian workspace state, community plugins, and device-specific settings are intentionally not part of this vault's tracked configuration. See [[docs/obsidian|the safe workflow]] before moving notes from another vault.
"""


def initialize(root: Path) -> dict[str, bool]:
    """Create portable vault affordances without replacing user-owned files."""
    root = root.resolve(strict=True)
    obsidian = root / ".obsidian"
    reject_symlink_chain(obsidian, root)
    obsidian.mkdir(exist_ok=True)
    settings = root / SETTINGS_RELATIVE
    home = root / HOME_NAME
    gitignore = root / ".gitignore"
    reject_symlink_chain(settings, root)
    reject_symlink_chain(home, root)
    reject_symlink_chain(gitignore, root)
    if not settings.exists():
        atomic_write(settings, json_bytes(PORTABLE_SETTINGS), mode=0o644)
    if not home.exists():
        atomic_write(home, HOME.encode("utf-8"), mode=0o644)
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    present = set(existing.splitlines())
    missing = [rule for rule in GITIGNORE_RULES if rule not in present]
    if missing:
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        addition = prefix + "# Agent Brain private runtime and Obsidian local state\n" + "\n".join(missing) + "\n"
        atomic_write(gitignore, (existing + addition).encode("utf-8"), mode=0o644)
    return {"portable_settings": settings.is_file(), "home": home.is_file(), "gitignore": gitignore.is_file()}


def _settings_safe(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return value == PORTABLE_SETTINGS


def symlinks(root: Path) -> list[str]:
    obsidian = root / ".obsidian"
    if obsidian.is_symlink():
        return [".obsidian"]
    if not obsidian.exists():
        return []
    found: list[str] = []
    for current, directories, files in os.walk(obsidian, followlinks=False):
        base = Path(current)
        for name in directories + files:
            path = base / name
            if path.is_symlink():
                found.append(path.relative_to(root).as_posix())
    return sorted(found)


def tracked_state(root: Path) -> list[str]:
    """Return tracked Obsidian files other than the one portable settings file."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", ".obsidian"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    paths = [item.decode("utf-8", errors="surrogateescape") for item in result.stdout.split(b"\0") if item]
    return sorted(path for path in paths if path != SETTINGS_RELATIVE.as_posix())


def inspect(root: Path) -> dict[str, Any]:
    root = root.resolve()
    settings = root / SETTINGS_RELATIVE
    home = root / HOME_NAME
    return {
        "vault_path": str(root),
        "portable_settings_path": SETTINGS_RELATIVE.as_posix(),
        "portable_settings_exists": settings.is_file() and not settings.is_symlink(),
        "portable_settings_safe": _settings_safe(settings),
        "home_path": HOME_NAME,
        "home_exists": home.is_file() and not home.is_symlink(),
        "canonical_memory_root": str(root / "brain"),
        "derived_runtime_root": str(root / ".agent-brain"),
        "instructions": [
            "Open the repository root as an Obsidian vault; do not open only the brain directory.",
            "Treat brain/ as canonical and .agent-brain/ as private, derived, and gitignored.",
            "Review Markdown changes with Git and run agent-brain sync after manual edits.",
            "Keep personal vaults separate; import notes only through the allowlisted ingest gate.",
        ],
    }


def doctor_issues(root: Path) -> tuple[list[str], dict[str, Any]]:
    linked = symlinks(root)
    tracked = tracked_state(root)
    settings = root / SETTINGS_RELATIVE
    checks: dict[str, Any] = {
        "obsidian_symlinks": linked,
        "obsidian_tracked_private_state": tracked,
        "obsidian_portable_settings": "ok" if _settings_safe(settings) else "missing_or_modified",
    }
    issues: list[str] = []
    if linked:
        issues.append("unsafe_obsidian_symlink")
    if tracked:
        issues.append("tracked_obsidian_workspace_or_device_state")
    if settings.exists() and not _settings_safe(settings):
        issues.append("obsidian_portable_settings_unsafe")
    return issues, checks

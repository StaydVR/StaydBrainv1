#!/usr/bin/env python3
"""Silent-on-healthy Git synchronization watchdog for an operational Agent Brain.

Resolution order: an explicit ``root`` passed to ``main`` (tests),
``AGENT_BRAIN_ROOT``, the installed Hermes plugin configuration, then this
repository root. The script is read-only apart from ``git fetch`` metadata.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess


TIMEOUT_SECONDS = 120


def _configured_root() -> Path:
    explicit = os.environ.get("AGENT_BRAIN_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()

    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()
    plugin_path = hermes_home / "plugins" / "agent-brain" / "plugin.py"
    if plugin_path.is_file():
        spec = importlib.util.spec_from_file_location("_agent_brain_watchdog_plugin", plugin_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return Path(module.load_config().root).resolve()

    return Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("git")
    if not executable:
        raise RuntimeError("git is unavailable")
    return subprocess.run(
        [executable, *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )


def main(root: Path | None = None) -> int:
    try:
        repo = (root or _configured_root()).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        print("⚠️ Agent Brain Git sync check failed: configured repository is missing.")
        return 0
    try:
        inside = _git(repo, "rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            print("⚠️ Agent Brain Git sync check failed: configured root is not a Git repository.")
            return 0

        remote = os.environ.get("AGENT_BRAIN_GIT_REMOTE", "origin")
        branch_result = _git(repo, "branch", "--show-current")
        branch = os.environ.get("AGENT_BRAIN_GIT_BRANCH") or branch_result.stdout.strip()
        if branch_result.returncode != 0 or not branch:
            print("⚠️ Agent Brain Git sync check failed: unable to determine the current branch.")
            return 0

        fetched = _git(repo, "fetch", remote, branch, "--prune")
        if fetched.returncode != 0:
            print("⚠️ Agent Brain Git sync check failed: remote fetch failed.")
            return 0

        status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
        counts = _git(repo, "rev-list", "--left-right", "--count", f"HEAD...{remote}/{branch}")
        values = counts.stdout.split()
        if status.returncode != 0 or counts.returncode != 0 or len(values) != 2:
            print("⚠️ Agent Brain Git sync check failed: unable to compare local and remote state.")
            return 0

        ahead, behind = (int(value) for value in values)
        changes = status.stdout.splitlines()
        if not changes and ahead == 0 and behind == 0:
            return 0

        parts: list[str] = []
        if changes:
            parts.append(f"{len(changes)} uncommitted change(s)")
        if ahead:
            parts.append(f"{ahead} commit(s) not pushed")
        if behind:
            parts.append(f"{behind} remote commit(s) not pulled")
        print("⚠️ Agent Brain Git sync needs attention: " + "; ".join(parts) + ".")
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        print("⚠️ Agent Brain Git sync watchdog error: local Git check failed safely.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

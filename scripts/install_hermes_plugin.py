#!/usr/bin/env python3
"""Atomically install, check, or uninstall the standalone Hermes plugin."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path


PLUGIN_NAME = "agent-brain"
ROLLBACK_NAME = f".{PLUGIN_NAME}-rollback"
EXPECTED_FILES = ("README.md", "__init__.py", "plugin.py", "plugin.yaml", "schemas.py", "tools.py")
SOURCE = Path(__file__).resolve().parents[1] / "integrations" / "hermes-plugin"


class InstallError(RuntimeError):
    pass


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _validate_chain(path: Path) -> None:
    current = path
    while True:
        if current.exists() and current.is_symlink():
            raise InstallError(f"refusing symlink path: {current}")
        if current.parent == current:
            return
        current = current.parent


def _validate_directory(path: Path, *, exact_files: bool) -> None:
    _validate_chain(path)
    if not path.is_dir() or path.is_symlink():
        raise InstallError(f"not a safe directory: {path}")
    names: set[str] = set()
    for child in path.iterdir():
        if child.is_symlink():
            raise InstallError(f"refusing symlink: {child}")
        mode = child.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode) and child.name == "__pycache__":
            for cached in child.iterdir():
                if cached.is_symlink() or not stat.S_ISREG(cached.stat(follow_symlinks=False).st_mode):
                    raise InstallError(f"refusing unsafe bytecode cache entry: {cached}")
            continue
        if not stat.S_ISREG(mode):
            raise InstallError(f"refusing non-regular plugin source: {child}")
        names.add(child.name)
    expected = set(EXPECTED_FILES)
    if names != expected:
        raise InstallError("plugin file set is incomplete or unexpected")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    home = Path(raw).expanduser() if raw else Path.home() / ".hermes"
    if not home.is_absolute():
        raise InstallError("HERMES_HOME must be absolute")
    _validate_chain(home)
    return home


def _paths() -> tuple[Path, Path]:
    plugins = _home() / "plugins"
    target = plugins / PLUGIN_NAME
    return plugins, target


def check() -> bool:
    plugins, target = _paths()
    if not plugins.is_dir() or plugins.is_symlink() or not target.exists():
        return False
    try:
        _validate_directory(SOURCE, exact_files=False)
        _validate_directory(target, exact_files=True)
    except InstallError:
        return False
    return all(_digest(SOURCE / name) == _digest(target / name) for name in EXPECTED_FILES)


def install() -> None:
    _validate_directory(SOURCE, exact_files=False)
    plugins, target = _paths()
    plugins.mkdir(parents=True, exist_ok=True, mode=0o700)
    _validate_chain(plugins)
    if plugins.is_symlink() or not plugins.is_dir():
        raise InstallError("plugins directory is unsafe")
    rollback = plugins / ROLLBACK_NAME
    if rollback.exists() or rollback.is_symlink():
        _validate_directory(rollback, exact_files=False)
        if not target.exists():
            os.replace(rollback, target)
            _fsync_directory(plugins)
        elif target.is_dir() and not target.is_symlink():
            _validate_directory(target, exact_files=False)
            if all(_digest(SOURCE / name) == _digest(target / name) for name in EXPECTED_FILES):
                shutil.rmtree(rollback)
                _fsync_directory(plugins)
            else:
                raise InstallError(f"unresolved prior plugin backup retained at: {rollback}")
        else:
            raise InstallError(f"unresolved prior plugin backup retained at: {rollback}")
    if target.exists() or target.is_symlink():
        _validate_directory(target, exact_files=False)

    staging = Path(tempfile.mkdtemp(prefix=f".{PLUGIN_NAME}-stage-", dir=plugins))
    backup: Path | None = None
    try:
        for name in EXPECTED_FILES:
            source = SOURCE / name
            destination = staging / name
            with source.open("rb") as reader, destination.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
                writer.flush()
                os.fsync(writer.fileno())
            destination.chmod(0o600)
        _fsync_directory(staging)
        _validate_directory(staging, exact_files=True)
        if target.exists():
            backup = rollback
            os.replace(target, backup)
            _fsync_directory(plugins)
        try:
            os.replace(staging, target)
            _fsync_directory(plugins)
        except BaseException as install_exc:
            try:
                if target.exists() and not target.is_symlink():
                    _validate_directory(target, exact_files=False)
                    shutil.rmtree(target)
                    _fsync_directory(plugins)
                if backup is not None and backup.exists():
                    os.replace(backup, target)
                    _fsync_directory(plugins)
            except BaseException as restore_exc:
                retained = backup if backup is not None and backup.exists() else "unavailable"
                raise InstallError(
                    f"plugin replacement failed ({install_exc}); automatic restore failed "
                    f"({restore_exc}); prior plugin backup: {retained}"
                ) from restore_exc
            raise
        if backup is not None:
            _validate_directory(backup, exact_files=False)
            shutil.rmtree(backup)
            _fsync_directory(plugins)
    finally:
        if staging.exists() and not staging.is_symlink():
            _validate_directory(staging, exact_files=False)
            shutil.rmtree(staging)


def uninstall() -> None:
    plugins, target = _paths()
    if not target.exists() and not target.is_symlink():
        return
    _validate_directory(target, exact_files=False)
    tombstone = Path(tempfile.mkdtemp(prefix=f".{PLUGIN_NAME}-uninstall-", dir=plugins))
    tombstone.rmdir()
    os.replace(target, tombstone)
    _fsync_directory(plugins)
    _validate_directory(tombstone, exact_files=False)
    shutil.rmtree(tombstone)
    _fsync_directory(plugins)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="verify an exact installed copy")
    group.add_argument("--uninstall", action="store_true", help="remove plugin code only")
    args = parser.parse_args()
    try:
        if args.check:
            if check():
                print("agent-brain plugin check: ok")
                return 0
            print("agent-brain plugin check: missing or differs")
            return 1
        if args.uninstall:
            uninstall()
            print("agent-brain plugin uninstalled; configuration and data preserved")
            return 0
        install()
        print("agent-brain plugin installed; enable it explicitly with: hermes plugins enable agent-brain")
        return 0
    except (InstallError, OSError) as exc:
        print(f"agent-brain plugin operation failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

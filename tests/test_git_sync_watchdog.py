from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "agent_brain_git_sync_watchdog.py"


def load_watchdog():
    spec = importlib.util.spec_from_file_location("test_agent_brain_git_sync_watchdog", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        [shutil.which("git") or "git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitSyncWatchdogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.remote = self.base / "remote.git"
        self.repo = self.base / "brain"
        git(self.base, "init", "--bare", str(self.remote))
        git(self.base, "init", "-b", "main", str(self.repo))
        git(self.repo, "config", "user.name", "Synthetic Test")
        git(self.repo, "config", "user.email", "synthetic@example.com")
        (self.repo / "README.md").write_text("synthetic\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-m", "synthetic baseline")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-u", "origin", "main")
        self.watchdog = load_watchdog()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_watchdog(self, root: Path) -> str:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(self.watchdog.main(root), 0)
        return output.getvalue()

    def test_healthy_repository_is_silent(self) -> None:
        self.assertEqual(self.run_watchdog(self.repo), "")

    def test_uncommitted_change_emits_attention_message(self) -> None:
        (self.repo / "README.md").write_text("changed\n", encoding="utf-8")
        output = self.run_watchdog(self.repo)
        self.assertIn("needs attention", output)
        self.assertIn("1 uncommitted change(s)", output)
        self.assertNotIn(str(self.repo), output)

    def test_missing_repository_emits_safe_error(self) -> None:
        output = self.run_watchdog(self.base / "missing")
        self.assertIn("configured repository is missing", output)
        self.assertNotIn(str(self.base), output)

    def test_runtime_git_failure_emits_one_bounded_alert_without_raising(self) -> None:
        with mock.patch.object(self.watchdog, "_git", side_effect=RuntimeError("synthetic failure")):
            output = self.run_watchdog(self.repo)
        self.assertEqual(
            output,
            "⚠️ Agent Brain Git sync watchdog error: local Git check failed safely.\n",
        )
        self.assertNotIn("synthetic failure", output)


if __name__ == "__main__":
    unittest.main()

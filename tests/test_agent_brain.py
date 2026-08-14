from __future__ import annotations

import io
import json
import os
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from agent_brain import Brain, SecurityError, ValidationError
from agent_brain.audit import verify as verify_audit
from agent_brain.cli import main
from agent_brain.db import connect
from agent_brain.dream import DreamLock, run_dream
from agent_brain.markdown import links, parse, render
from agent_brain.obsidian import GITIGNORE_RULES, HOME, HOME_NAME, PORTABLE_SETTINGS
from agent_brain.server import dispatch, serve
from agent_brain.util import atomic_write, safe_relative, sha256


NAMESPACE = uuid.UUID("678b8583-e2b1-44e9-b880-f07804b1d22f")


class BrainCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.brain = Brain.init(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _canonical(self, slug: str, body: str, updated: str = "2025-01-01T00:00:00Z",
                   document_id: str | None = None, kind: str = "note") -> str:
        return render({"id": document_id or str(uuid.uuid5(NAMESPACE, slug)), "slug": slug,
                       "title": slug.replace("-", " ").title(), "type": kind,
                       "created": updated, "updated": updated, "source": "fixture", "status": "active"}, body)

    def _write_config(self, *, ingest: int = 1_048_576, archive_files: int = 256,
                      archive_bytes: int = 8_388_608, roots: tuple[Path, ...] = ()) -> None:
        quoted = ", ".join(json.dumps(str(path)) for path in roots)
        (self.root / ".agent-brain/config.toml").write_text(
            f"version = 1\nmax_ingest_bytes = {ingest}\nstale_after_days = 90\n"
            f"max_archive_files = {archive_files}\nmax_archive_bytes = {archive_bytes}\n"
            f"allowlisted_roots = [{quoted}]\n", encoding="utf-8")

    def _managed_bytes(self) -> list[bytes]:
        values = []
        for base in (self.root / "brain", self.root / ".agent-brain"):
            for path in base.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    values.append(path.read_bytes())
        return values

    def test_init_uuid_slug_schema_and_sqlite_hardening(self) -> None:
        self.assertEqual((self.root / HOME_NAME).read_text(encoding="utf-8"), HOME)
        self.assertEqual(json.loads((self.root / ".obsidian/app.json").read_text(encoding="utf-8")), PORTABLE_SETTINGS)
        item = self.brain.remember("Readable title", "Synthetic durable content.", page_id="readable-title")
        self.assertEqual(str(uuid.UUID(item["id"])), item["id"])
        self.assertEqual(item["slug"], "readable-title")
        doc = parse((self.root / "brain" / item["path"]).read_text(encoding="utf-8"))
        self.assertEqual(doc.meta["id"], item["id"])
        self.assertEqual(doc.meta["slug"], "readable-title")
        with connect(self.brain.db_path, initialize=False) as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertGreaterEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5_000)
            self.assertEqual(conn.execute("PRAGMA trusted_schema").fetchone()[0], 0)
            if hasattr(conn, "getlimit"):
                self.assertLessEqual(conn.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER), 512)
            names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        self.assertTrue({"pages", "pages_fts", "links", "facts", "runs", "audit"} <= names)

    def test_strict_frontmatter_uuid_slug_and_links(self) -> None:
        text = self._canonical(
            "alpha",
            "See [[brain/pages/beta|Beta]] <!-- agent-brain:relationship=depends-on -->, "
            "[[brain/pages/gamma.md|Gamma]], [[delta]], and legacy [[blocks:epsilon]].\n",
        )
        self.assertEqual(
            links(parse(text).body),
            [("depends-on", "beta", 1), ("related", "gamma", 1),
             ("related", "delta", 1), ("blocks", "epsilon", 1)],
        )
        with self.assertRaises(ValidationError):
            parse(text.replace("type: note", "unexpected: value"))
        with self.assertRaises(ValidationError):
            parse(text.replace("slug: alpha\n", "slug: alpha\nslug: duplicate\n"))
        with self.assertRaises(ValidationError):
            render({"id": "alpha", "slug": "alpha", "title": "Alpha", "type": "note",
                    "created": "2025-01-01T00:00:00Z", "updated": "2025-01-01T00:00:00Z"}, "body")

    def test_obsidian_links_resolve_index_relationships_backlinks_and_timeline(self) -> None:
        target = self.brain.remember("Target page", "Target body.", page_id="target-page")
        source = self.brain.remember(
            "Source page",
            "Plain [[brain/pages/target-page|Target page]].\n"
            "Typed [[brain/pages/target-page|Target page]] "
            "<!-- agent-brain:relationship=depends-on -->.\n",
            page_id="source-page",
        )
        entity = self.brain.entity(target["id"])
        self.assertEqual(
            sorted((row["target_ref"], row["link_type"], row["target_id"])
                   for row in self.brain.entity(source["id"])["links"]),
            [("target-page", "depends-on", target["id"]), ("target-page", "related", target["id"])],
        )
        authored = [row for row in entity["backlinks"] if row["source_id"] == source["id"]]
        self.assertEqual(sorted(row["link_type"] for row in authored), ["depends-on", "related"])
        self.assertTrue(any(row["link_type"] == "memory" for row in entity["backlinks"]))
        timeline = next((self.root / "brain/timeline").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("[[brain/pages/target-page|Target page]]", timeline)
        self.assertIn("<!-- agent-brain:relationship=memory -->", timeline)
        self.assertNotIn("[[memory:", timeline)

    def test_obsidian_init_is_idempotent_and_never_overwrites_home_or_settings(self) -> None:
        home = self.root / HOME_NAME
        settings = self.root / ".obsidian/app.json"
        home.write_text("# Custom vault home\n", encoding="utf-8")
        settings.write_text('{"newFileLocation": "current"}\n', encoding="utf-8")
        (self.root / ".gitignore").write_text("custom-local-rule\n", encoding="utf-8")
        Brain.init(self.root)
        self.assertEqual(home.read_text(encoding="utf-8"), "# Custom vault home\n")
        self.assertEqual(settings.read_text(encoding="utf-8"), '{"newFileLocation": "current"}\n')
        gitignore = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(gitignore.startswith("custom-local-rule\n"))
        self.assertTrue(all(gitignore.splitlines().count(rule) == 1 for rule in GITIGNORE_RULES))
        before = gitignore
        Brain.init(self.root)
        self.assertEqual((self.root / ".gitignore").read_text(encoding="utf-8"), before)

    def test_obsidian_home_navigation_and_portable_settings_are_privacy_safe(self) -> None:
        home = (self.root / HOME_NAME).read_text(encoding="utf-8")
        for target in ("brain/pages/", "brain/sources/", "brain/timeline/", "brain/reports/",
                       "[[docs/obsidian|", "[[skills/RESOLVER|"):
            self.assertIn(target, home)
        self.assertIn("`.agent-brain/` is private, gitignored runtime storage", home)
        settings = json.loads((self.root / ".obsidian/app.json").read_text(encoding="utf-8"))
        self.assertEqual(settings, PORTABLE_SETTINGS)
        self.assertEqual(set(settings), {"alwaysUpdateLinks", "newFileFolderPath", "newFileLocation", "useMarkdownLinks"})
        serialized = json.dumps(settings).casefold()
        self.assertNotIn("workspace", serialized)
        self.assertNotIn("plugin", serialized)
        self.assertNotIn("/users/", serialized)

    def test_gitignore_keeps_runtime_workspace_device_and_plugins_private(self) -> None:
        (self.root / ".gitignore").write_text(
            (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
        )
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        ignored = (".agent-brain/index.sqlite3", ".obsidian/workspace.json",
                   ".obsidian/workspace-mobile.json", ".obsidian/community-plugins.json",
                   ".obsidian/plugins/sample/data.json")
        for path in ignored:
            result = subprocess.run(
                ["git", "-C", str(self.root), "check-ignore", "-q", "--no-index", path], capture_output=True
            )
            self.assertEqual(result.returncode, 0, path)
        result = subprocess.run(
            ["git", "-C", str(self.root), "check-ignore", "-q", "--no-index", ".obsidian/app.json"],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 1)

    def test_doctor_rejects_obsidian_symlinks_and_tracked_private_state(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / ".obsidian/linked-state").symlink_to(outside, target_is_directory=True)
        result = self.brain.doctor()
        self.assertIn("unsafe_obsidian_symlink", result["issues"])
        (self.root / ".obsidian/linked-state").unlink()

        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        workspace = self.root / ".obsidian/workspace.json"
        workspace.write_text("{}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "-f", ".obsidian/workspace.json"], check=True, capture_output=True)
        result = self.brain.doctor()
        self.assertIn("tracked_obsidian_workspace_or_device_state", result["issues"])
        self.assertEqual(result["checks"]["obsidian_tracked_private_state"], [".obsidian/workspace.json"])

    def test_obsidian_cli_e2e_with_fresh_home_and_no_obsidian_runtime(self) -> None:
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "clean-repository"
            fresh_home = base / "fresh-home"
            repository.mkdir(); fresh_home.mkdir()
            environment = os.environ.copy()
            environment["HOME"] = str(fresh_home)
            environment["PYTHONPATH"] = str(project / "src")
            command = [sys.executable, "-S", "-m", "agent_brain", "--root", str(repository)]
            initialized = subprocess.run(command + ["init"], cwd=repository, env=environment, text=True,
                                         capture_output=True, check=True)
            self.assertEqual(json.loads(initialized.stdout)["integrity"], "ok")
            status = subprocess.run(command + ["obsidian"], cwd=repository, env=environment, text=True,
                                    capture_output=True, check=True)
            value = json.loads(status.stdout)
            self.assertEqual(value["vault_path"], str(repository.resolve()))
            self.assertTrue(value["portable_settings_exists"])
            self.assertTrue(value["portable_settings_safe"])
            self.assertTrue(value["home_exists"])
            self.assertEqual(value["canonical_memory_root"], str(repository.resolve() / "brain"))
            self.assertEqual(value["derived_runtime_root"], str(repository.resolve() / ".agent-brain"))
            gitignore = (repository / ".gitignore").read_text(encoding="utf-8")
            self.assertTrue(all(rule in gitignore.splitlines() for rule in GITIGNORE_RULES))

    def test_citations_bind_identity_content_and_span_and_detect_staleness(self) -> None:
        item = self.brain.remember("Citation page", "First line.\nBound evidence token.\n", page_id="citation-page")
        result = self.brain.search("evidence token")[0]
        citation = result["citation"]
        self.assertEqual(citation["document_id"], item["id"])
        self.assertEqual(citation["slug"], item["slug"])
        self.assertEqual(citation["content_hash"], item["sha256"])
        self.assertEqual(citation["start_line"], 2)
        self.assertTrue(self.brain.verify_citation(citation)["valid"])
        path = self.root / citation["path"]
        document = parse(path.read_text(encoding="utf-8"))
        atomic_write(path, render(document.meta, document.body.replace("Bound", "Changed")).encode())
        self.assertEqual(self.brain.verify_citation(citation), {"valid": False, "stale": True})

    def test_atomic_write_fsyncs_file_and_parent_directory(self) -> None:
        target = self.root / "durable" / "value.bin"
        real_fsync = os.fsync
        calls: list[int] = []

        def recording(fd: int) -> None:
            calls.append(fd)
            real_fsync(fd)

        with mock.patch("agent_brain.util.os.fsync", side_effect=recording):
            atomic_write(target, b"durable")
        self.assertEqual(target.read_bytes(), b"durable")
        self.assertGreaterEqual(len(calls), 2)

    def test_audit_hash_chain_detects_entry_tamper_and_tail_truncation(self) -> None:
        self.brain.remember("One", "Safe one.", page_id="one")
        self.brain.remember("Two", "Safe two.", page_id="two")
        state = verify_audit(self.brain.control)
        self.assertEqual(len(state["entries"]), 2)
        log = self.brain.control / "audit.jsonl"
        original = log.read_bytes()
        tampered = original.replace(b'"action":"remember"', b'"action":"remembfr"', 1)
        atomic_write(log, tampered)
        with self.assertRaises(ValidationError):
            verify_audit(self.brain.control)
        atomic_write(log, original)
        atomic_write(log, b"\n".join(original.splitlines()[:-1]) + b"\n")
        with self.assertRaises(ValidationError):
            verify_audit(self.brain.control)

    def test_rejects_secret_classes_and_never_persists_raw_rejected_bytes(self) -> None:
        marker = "REJECTED_MATERIAL_SENTINEL"
        jwt = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "c3ludGhldGljX3BheWxvYWQ" + "." + "c2lnbmF0dXJlX3ZhbHVl"
        payloads = [
            marker + "\nAuthorization: Bear" + "er abcdefghijklmnopqrstuvwxyz012345",
            marker + "\n" + jwt,
            marker + "\n-----BEGIN " + "PRIVATE KEY-----\nsynthetic\n-----END " + "PRIVATE KEY-----",
            marker + "\npostgres" + "ql://role:credential@" + "host" + chr(46) + "invalid/store",
            marker + "\ntoken=" + "Q2hhbmdlTWVOb3dUaGlzSXNBVmVyeUxvbmdSYW5kb21Ub2tlbg==",
            marker + "\n" + "aB3dE5fG7hJ9kLmN2pQrS4tUvW6xYz01" * 2,
        ]
        for index, payload in enumerate(payloads):
            with self.subTest(index=index):
                with self.assertRaises(SecurityError):
                    self.brain.remember(f"Rejected {index}", payload, page_id=f"rejected-{index}")
                self.assertFalse(any(payload.encode() in value for value in self._managed_bytes()))
        run_dream(self.brain)
        managed = self._managed_bytes()
        for payload in payloads:
            self.assertFalse(any(payload.encode() in value for value in managed))
        records = self.brain.quarantine_list()
        self.assertEqual(len(records), len(payloads))
        self.assertTrue(all(set(record) == {"sha256", "reasons"} for record in records))

    def test_pii_binary_and_size_boundaries(self) -> None:
        unsafe = [
            b"person" + bytes([64]) + b"example" + bytes([46]) + b"invalid",
            b"111-22-3333", b"(212) 555-0199", b"4111 1111 1111 1111", b"safe\x00unsafe", b"\xff\xfe",
        ]
        for data in unsafe:
            with self.subTest(kind=sha256(data)):
                with self.assertRaises(SecurityError):
                    self.brain._scan(data)
        self.brain._scan(b"id: 123e4567-e89b-12d3-a456-426614174000")
        self._write_config(ingest=8, archive_bytes=8)
        with self.assertRaises(SecurityError):
            self.brain._scan(b"ninebytes")

    def test_traversal_variants_and_symlink_chains(self) -> None:
        for value in ("../escape", "nested/../../escape", "/absolute", "nested\\..\\escape", ".", "..%2fescape", "%252e%252e/escape"):
            with self.subTest(value=value), self.assertRaises(SecurityError):
                safe_relative(value)
        external = self.root / "external"; external.mkdir()
        real = external / "real"; real.mkdir()
        (real / "note.md").write_text(self._canonical("linked", "Safe."), encoding="utf-8")
        chain = external / "chain"; chain.symlink_to(real, target_is_directory=True)
        self._write_config(roots=(external,))
        self.brain.register_source("sample", external)
        with self.assertRaises(SecurityError):
            self.brain.ingest("sample", "chain/note.md")
        managed_target = self.root / "brain/pages"
        replacement = self.root / "replacement"; replacement.mkdir()
        managed_target.rmdir(); managed_target.symlink_to(replacement, target_is_directory=True)
        with self.assertRaises(SecurityError):
            self.brain.remember("Blocked", "Safe text.")

    def test_malicious_fts_queries_are_literal_bounded_and_parameterized(self) -> None:
        self.brain.remember("Query target", "alpha beta operator phrase.", page_id="query-target")
        hostile = ['" OR *', "alpha NEAR(beta)", "alpha* NOT beta", "') ; DROP TABLE pages; --", "{{{{[[[[]]]]"]
        for query in hostile:
            with self.subTest(query=query):
                try:
                    result = self.brain.search(query)
                except ValidationError:
                    result = []
                self.assertIsInstance(result, list)
        with connect(self.brain.db_path, initialize=False) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM pages WHERE slug=?", ("query-target",)).fetchone()[0], 1)
        with self.assertRaises(ValidationError):
            self.brain.search("x" * 4097)

    def test_archive_rejects_traversal_symlinks_duplicates_count_and_size_without_partial_write(self) -> None:
        safe_data = self._canonical("portable", "Archive-safe content.")
        traversal = self.root / "traversal.zip"
        with zipfile.ZipFile(traversal, "w") as archive:
            archive.writestr("brain/pages/portable.md", safe_data)
            archive.writestr("../escape.md", safe_data)
        with self.assertRaises(SecurityError):
            self.brain.import_archive(traversal)
        self.assertFalse((self.root / "brain/pages/portable.md").exists())

        linked = self.root / "linked.zip"
        info = zipfile.ZipInfo("brain/pages/link.md"); info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(linked, "w") as archive:
            archive.writestr(info, "target.md")
        with self.assertRaises(SecurityError):
            self.brain.import_archive(linked)

        duplicate = self.root / "duplicate.zip"
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("brain/pages/same.md", safe_data)
            with self.assertWarns(UserWarning):
                archive.writestr("brain/pages/same.md", safe_data)
        with self.assertRaises(SecurityError):
            self.brain.import_archive(duplicate)

        identity_collision = self.root / "identity-collision.zip"
        one = self._canonical("identity-one", "First archive page.")
        two = self._canonical("identity-two", "Second archive page.")
        one_id = next(line for line in one.splitlines() if line.startswith("id: "))
        two_id = next(line for line in two.splitlines() if line.startswith("id: "))
        two = two.replace(two_id, one_id, 1)
        with zipfile.ZipFile(identity_collision, "w") as archive:
            archive.writestr("brain/pages/identity-one.md", one)
            archive.writestr("brain/pages/identity-two.md", two)
        with self.assertRaises(ValidationError):
            self.brain.import_archive(identity_collision)
        self.assertFalse((self.root / "brain/pages/identity-one.md").exists())
        self.assertFalse((self.root / "brain/pages/identity-two.md").exists())

        rollback_archive = self.root / "rollback.zip"
        with zipfile.ZipFile(rollback_archive, "w") as archive:
            archive.writestr("brain/pages/rollback.md", self._canonical("rollback", "Rollback-safe page."))
        original_sync = self.brain.sync
        with mock.patch.object(self.brain, "sync", side_effect=[ValidationError("injected sync failure"), original_sync()]):
            with self.assertRaises(ValidationError):
                self.brain.import_archive(rollback_archive)
        self.assertFalse((self.root / "brain/pages/rollback.md").exists())
        self.assertTrue(self.brain.doctor()["ok"])

        self._write_config(ingest=128, archive_files=2, archive_bytes=256)
        crowded = self.root / "crowded.zip"
        with zipfile.ZipFile(crowded, "w") as archive:
            for index in range(3):
                archive.writestr(f"ignored-{index}.txt", "x")
        with self.assertRaises(SecurityError):
            self.brain.import_archive(crowded)
        large = self.root / "large.zip"
        with zipfile.ZipFile(large, "w") as archive:
            archive.writestr("brain/pages/large.md", b"x" * 129)
        with self.assertRaises(SecurityError):
            self.brain.import_archive(large)

    def test_config_and_source_registry_poisoning_fail_closed(self) -> None:
        config = self.root / ".agent-brain/config.toml"
        cases = [
            "version = 1\nunknown = true\n",
            "version = 1\nmax_ingest_bytes = 999999999\n",
            "version = 1\nallowlisted_roots = [\"relative\"]\n",
            "[[nested]]\nvalue = 1\n",
        ]
        for value in cases:
            with self.subTest(value=value):
                atomic_write(config, value.encode())
                with self.assertRaises(ValidationError):
                    self.brain.config()
        self._write_config(roots=(self.root,))
        registry = self.root / ".agent-brain/state/sources.json"
        atomic_write(registry, json.dumps({"bad": {"root": "relative", "tier": "cache", "extra": "x"}}).encode())
        with self.assertRaises(ValidationError):
            self.brain.register_source("next", self.root)

    def test_corrupted_database_reports_structured_error_and_rebuilds_from_canonical(self) -> None:
        item = self.brain.remember("Recovery", "Recoverable canonical phrase.", page_id="recovery")
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.brain.db_path) + suffix)
            if path.exists():
                path.unlink()
        self.brain.db_path.write_bytes(b"not a database")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = main(["--root", str(self.root), "status"])
        error = json.loads(stderr.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(error["ok"])
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertIn("database", self.brain.doctor()["issues"][0])
        self.brain.rebuild()
        self.assertEqual(self.brain.search("Recoverable")[0]["id"], item["id"])
        self.assertTrue(self.brain.doctor()["ok"])

    def test_rebuild_and_dream_do_not_change_ordinary_canonical_hashes(self) -> None:
        self.brain.remember("Stable page", "Unchanged ordinary knowledge.", page_id="stable-page")
        before = self.brain.canonical_hashes()
        self.brain.rebuild()
        self.assertEqual(before, self.brain.canonical_hashes())
        first = run_dream(self.brain)
        self.assertEqual(before, self.brain.canonical_hashes())
        report = next((self.root / "brain/reports").glob("dream-*.md"))
        report_bytes = report.read_bytes()
        second = run_dream(self.brain)
        self.assertEqual(report_bytes, report.read_bytes())
        self.assertEqual(first["contradictions"], second["contradictions"])
        self.assertEqual(before, self.brain.canonical_hashes())

    def test_dream_is_review_first_deterministic_locked_crash_safe_and_auditable(self) -> None:
        shared = "Duplicate body.\n- fact: unit | state | green"
        (self.root / "brain/pages/a.md").write_text(self._canonical("a", shared), encoding="utf-8")
        (self.root / "brain/pages/b.md").write_text(self._canonical("b", shared), encoding="utf-8")
        (self.root / "brain/pages/c.md").write_text(self._canonical("c", "- fact: unit | state | amber\nBroken [[depends-on:missing]]."), encoding="utf-8")
        self.brain.sync(); ordinary = self.brain.canonical_hashes()
        dry = run_dream(self.brain, dry_run=True)
        self.assertTrue(dry["dry_run"]); self.assertFalse(list((self.root / "brain/reports").glob("*")))
        result = run_dream(self.brain)
        self.assertTrue(result["review_required"]); self.assertTrue(result["duplicate_candidates"])
        self.assertTrue(result["contradictions"]); self.assertTrue(result["broken_links"])
        self.assertEqual(ordinary, self.brain.canonical_hashes())
        self.assertTrue(list((self.root / ".agent-brain/backups").glob("*.sqlite3")))
        with connect(self.brain.db_path, initialize=False) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM runs WHERE status='ok'").fetchone()[0], 1)
        self.assertEqual(verify_audit(self.brain.control)["entries"][-1]["action"], "dream")
        lock = self.root / ".agent-brain/dream.lock"
        with DreamLock(lock), self.assertRaises(Exception):
            run_dream(self.brain)
        report = next((self.root / "brain/reports").glob("dream-*.md")); previous = report.read_bytes()
        (self.root / "brain/pages/new.md").write_text(self._canonical("new", "New orphan."), encoding="utf-8")
        with mock.patch("agent_brain.dream.atomic_write", side_effect=OSError("simulated crash")):
            with self.assertRaises(OSError):
                run_dream(self.brain)
        self.assertEqual(report.read_bytes(), previous)
        self.assertFalse(lock.exists())

    def test_source_tiers_uuid_identity_and_checkpoints(self) -> None:
        external = self.root / "external"; external.mkdir()
        (external / "tracked.md").write_text(self._canonical("tracked-source", "Tracked content."), encoding="utf-8")
        (external / "cached.md").write_text(self._canonical("cached-source", "Cached content."), encoding="utf-8")
        self._write_config(roots=(external,))
        self.brain.register_source("tracked", external, "tracked")
        self.brain.register_source("cached", external, "cache")
        one = self.brain.ingest("tracked", "tracked.md"); two = self.brain.ingest("cached", "cached.md")
        self.assertNotEqual(one["id"], one["slug"]); self.assertNotEqual(two["id"], two["slug"])
        self.assertTrue((self.root / "brain/sources/tracked/tracked.md").exists())
        self.assertTrue((self.root / ".agent-brain/cache/cached/cached.md").exists())
        with connect(self.brain.db_path, initialize=False) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM source_checkpoints").fetchone()[0], 2)

    def test_memory_verbs_contradictions_staleness_gaps_forget_pack_and_delta(self) -> None:
        old = "2020-01-01T00:00:00Z"
        (self.root / "brain/pages/a.md").write_text(self._canonical("a", "Launch evidence.\n- fact: vessel | state | ready", old), encoding="utf-8")
        (self.root / "brain/pages/b.md").write_text(self._canonical("b", "Launch evidence.\n- fact: vessel | state | paused", old), encoding="utf-8")
        self.brain.sync()
        brief = self.brain.brief("Launch")
        self.assertEqual(len(brief["contradictions"]), 1); self.assertEqual(len(brief["stale_evidence"]), 2)
        self.assertTrue(all("content_hash" in row["citation"] for row in brief["results"]))
        self.assertTrue(self.brain.brief("unfindableterm")["gaps"])
        self.assertTrue(self.brain.context_pack("Launch", 2048)["items"])
        self.assertTrue(self.brain.delta("2000-01-01T00:00:00Z"))
        forgotten = self.brain.forget("a"); self.assertTrue(forgotten["canonical_retained"])
        self.assertEqual([row["slug"] for row in self.brain.recall("Launch")], ["b"])

    def test_doctor_verify_quarantine_cli_and_uninitialized_errors(self) -> None:
        rejected = "password=" + "synthetic_rejected_value_123456"
        with self.assertRaises(SecurityError):
            self.brain.remember("Rejected", rejected)
        self.assertTrue(self.brain.doctor()["ok"])
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(["--root", str(self.root), "quarantine-list"])
        self.assertEqual(code, 0); self.assertEqual(len(json.loads(stdout.getvalue())), 1)
        missing = self.root / "missing"; output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--root", str(missing), "verify"])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1); self.assertEqual(result["issues"], ["uninitialized_repository"])
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = main(["--root", str(missing), "status"])
        self.assertEqual(code, 2); self.assertNotIn("Traceback", stderr.getvalue())
        self.assertFalse(json.loads(stderr.getvalue())["ok"])

    def test_jsonl_server_is_narrow_and_errors_are_structured(self) -> None:
        source = io.StringIO(json.dumps({"id": 1, "verb": "remember", "args": {"title": "Server note", "content": "Server-safe word."}}) + "\n"
                             + json.dumps({"id": 2, "verb": "dream", "args": {}}) + "\nnot-json\n")
        sink = io.StringIO(); serve(self.brain, source, sink)
        lines_out = [json.loads(line) for line in sink.getvalue().splitlines()]
        self.assertFalse(lines_out[0]["ok"]); self.assertFalse(lines_out[1]["ok"]); self.assertFalse(lines_out[2]["ok"])
        write_source = io.StringIO(json.dumps({"id": 3, "verb": "remember", "args": {
            "title": "Server note", "content": "Server-safe word."}}) + "\n")
        write_sink = io.StringIO(); serve(self.brain, write_source, write_sink, allow_write=True)
        self.assertTrue(json.loads(write_sink.getvalue())["ok"])
        self.assertEqual(dispatch(self.brain, {"verb": "status", "args": {}})["integrity"], "ok")

    def test_all_operations_are_local_only_without_network(self) -> None:
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), \
             mock.patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
            item = self.brain.remember("Offline", "Local-only searchable content.", page_id="offline")
            self.assertEqual(self.brain.search("searchable")[0]["id"], item["id"])
            run_dream(self.brain)
            self.brain.rebuild()
            self.assertTrue(self.brain.doctor()["ok"])


if __name__ == "__main__":
    unittest.main()

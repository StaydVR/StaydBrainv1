from datetime import date, datetime, UTC
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from staydbrain import Brain, run_nightly, nightly_sync, next_run, Snapshot, FakeOpsAdapter, SecurityError, ValidationError
from agent_brain.config import Config
from agent_brain.nightly import VerifiedFact, repair_easy
from agent_brain.markdown import parse, render
from agent_brain.util import sha256


class NightlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.brain = Brain.init(self.temp.name)
        self.day = date(2026, 11, 15)

    def test_schedule(self):
        with patch.dict('os.environ', {}, clear=True):
            config = self.brain.config()
        self.assertEqual((config.nightly_time, config.nightly_timezone), ('04:00', 'America/New_York'))
        self.assertEqual(next_run(config, datetime(2026, 11, 15, tzinfo=UTC)).hour, 9)
        path = self.brain.control / 'config.toml'
        path.write_text(path.read_text().replace('04:00', '06:15'))
        self.assertEqual(self.brain.config().nightly_time, '06:15')
        with patch.dict('os.environ', {'STAYDBRAIN_NIGHTLY_TIME': '03:12', 'STAYDBRAIN_NIGHTLY_TIMEZONE': 'UTC'}):
            self.assertEqual(next_run(self.brain.config(), datetime(2026, 11, 15, tzinfo=UTC)).isoformat(), '2026-11-15T03:12:00+00:00')
        for key, value in [('STAYDBRAIN_NIGHTLY_TIME', '25:00'), ('STAYDBRAIN_NIGHTLY_TIMEZONE', '../bad')]:
            with patch.dict('os.environ', {key: value}), self.assertRaises(ValidationError):
                self.brain.config()

    def test_sync_outputs_and_idempotency(self):
        self.brain.remember('Old checklist', 'Synthetic stale checklist')
        path = self.brain.brain_dir / 'pages/old-checklist.md'
        doc = parse(path.read_text()); doc.meta['updated'] = '2020-01-01T00:00:00Z'
        path.write_text(render(doc.meta, doc.body))
        result = run_nightly(self.brain, (FakeOpsAdapter(),), day=self.day)
        self.assertEqual(result['dream']['integrity'], 'ok')
        self.assertTrue((self.brain.brain_dir / f'Journal/{self.day}.md').exists())
        meeting = next((self.brain.brain_dir / 'Meetings/2026/11').glob('*.md')).read_text()
        self.assertIn('## Decisions', meeting); self.assertIn('## Action items', meeting)
        for name in ['Current Work', 'Decision History']:
            self.assertIn('2026-11-15', (self.brain.brain_dir / f'pages/{name}.md').read_text())
        self.assertEqual(parse(path.read_text()).meta['status'], 'pending_review')
        hashes = self.brain.canonical_hashes()
        run_nightly(self.brain, (FakeOpsAdapter(),), day=self.day)
        self.assertEqual(hashes, self.brain.canonical_hashes())
        self.assertTrue((self.brain.brain_dir / f'reports/contradictions-{self.day}.md').exists())
        self.assertTrue(self.brain.search('mock filter'))

    def test_easy_repairs_and_sensitive_review(self):
        self.brain.remember('Filter checklist', 'Synthetic filter procedure', page_id='filter-v2', tags=('maintenance-safe',))
        self.brain.remember('Broken reference', 'See [[filter-checklist]]', tags=('maintenance-safe',))
        self.brain.remember('Duplicate A', 'Identical synthetic procedure', tags=('maintenance-safe',))
        self.brain.remember('Duplicate B', 'Identical synthetic procedure', tags=('maintenance-safe',))
        verified = []
        for label in ['equipment', 'people', 'money', 'legal', 'tax']:
            self.brain.remember(label, f'- fact: {label} | state | old', tags=('maintenance-safe',))
            path = self.brain.brain_dir / f'pages/{label}.md'
            verified.append(VerifiedFact(label, sha256(path.read_bytes()), 'old', 'new', 'Synthetic authoritative checklist'))
        sensitive = {label: (self.brain.brain_dir / f'pages/{label}.md').read_bytes() for label in ['people', 'money', 'legal', 'tax']}
        result = repair_easy(self.brain, tuple(verified), self.day)
        self.assertIn('[[filter-v2]]', (self.brain.brain_dir / 'pages/broken-reference.md').read_text())
        self.assertIn('| new', (self.brain.brain_dir / 'pages/equipment.md').read_text())
        self.assertEqual(parse((self.brain.brain_dir / 'pages/duplicate-b.md').read_text()).meta['status'], 'pending_review')
        for label, data in sensitive.items():
            self.assertEqual((self.brain.brain_dir / f'pages/{label}.md').read_bytes(), data)
            self.assertIn(label, [r['slug'] for r in result['human_review']])
        run_nightly(self.brain, (), day=self.day)
        report = (self.brain.brain_dir / f'reports/contradictions-{self.day}.md').read_text()
        for label in sensitive:
            self.assertIn(label, report)
            self.assertEqual((self.brain.brain_dir / f'pages/{label}.md').read_bytes(), sensitive[label])

    def test_contradictions(self):
        self.brain.remember('One', '- fact: mock-filter | color | blue')
        self.brain.remember('Two', '- fact: mock-filter | color | green')
        run_nightly(self.brain, (), day=self.day)
        report = (self.brain.brain_dir / f'reports/contradictions-{self.day}.md').read_text()
        self.assertIn('mock-filter', report); self.assertIn('blue', report); self.assertIn('green', report)

    def test_batch_security_and_symlink(self):
        class Unsafe:
            def collect(self, day):
                return Snapshot(journal='Unsafe' + chr(0))
        with self.assertRaises(SecurityError):
            nightly_sync(self.brain, (Unsafe(),), self.day)
        self.assertFalse((self.brain.brain_dir / 'Journal').exists())
        (self.brain.brain_dir / 'Journal').symlink_to(Path(self.temp.name))
        with self.assertRaises(SecurityError):
            nightly_sync(self.brain, (FakeOpsAdapter(),), self.day)

    def test_unverified_fact_is_not_changed(self):
        self.brain.remember('Equipment', 'old')
        path = self.brain.brain_dir / 'pages/equipment.md'; before = path.read_bytes()
        repair_easy(self.brain, (VerifiedFact('equipment', 'wrong', 'old', 'new', 'proof'),), self.day)
        self.assertEqual(path.read_bytes(), before)

    def test_unknown_domain_and_sensitive_proof_stay_unchanged(self):
        self.brain.remember('Unknown', 'old')
        self.brain.remember('Machine', 'old', tags=('maintenance-safe',))
        before = self.brain.canonical_hashes()
        machine = self.brain.brain_dir / 'pages/machine.md'
        repair_easy(self.brain, (VerifiedFact('machine', sha256(machine.read_bytes()), 'old', 'new', 'tax evidence'),), self.day)
        self.assertEqual(before, self.brain.canonical_hashes())

    def test_output_collision_and_bad_meeting(self):
        from agent_brain.nightly import Meeting
        class Bad:
            def collect(self, day):
                return Snapshot(meetings=(Meeting('../escape', 'Fake', 'Fake'),))
        with self.assertRaises(ValidationError):
            nightly_sync(self.brain, (Bad(),), self.day)
        self.assertFalse((self.brain.brain_dir / 'Journal').exists())
        path = self.brain.brain_dir / 'pages/Current Work.md'
        self.brain.remember('Independent page', 'Do not overwrite')
        path.write_bytes((self.brain.brain_dir / 'pages/independent-page.md').read_bytes())
        before = path.read_bytes()
        with self.assertRaises(ValidationError):
            nightly_sync(self.brain, (FakeOpsAdapter(),), self.day)
        self.assertEqual(path.read_bytes(), before)

    def test_dst_and_naive_timestamp(self):
        config = Config(nightly_time='02:30')
        self.assertEqual(next_run(config, datetime(2026, 3, 8, tzinfo=UTC)), datetime(2026, 3, 8, 7, 30, tzinfo=UTC))
        self.assertEqual(next_run(Config(nightly_time='01:30'), datetime(2026, 11, 1, tzinfo=UTC)), datetime(2026, 11, 1, 5, 30, tzinfo=UTC))
        with self.assertRaises(ValidationError):
            next_run(config, datetime(2026, 1, 1))

    def test_duplicate_meeting_and_oversized_batch(self):
        from agent_brain.nightly import Meeting
        class Duplicate:
            def collect(self, day):
                return Snapshot(meetings=(Meeting('same', 'Fake', 'Fake'),) * 2)
        class Huge:
            def collect(self, day):
                return Snapshot(journal='x' * (2 * 1024 * 1024))
        for adapter, error in [(Duplicate(), ValidationError), (Huge(), SecurityError)]:
            with self.assertRaises(error):
                nightly_sync(self.brain, (adapter,), self.day)
            self.assertFalse((self.brain.brain_dir / 'Journal').exists())

    def test_public_cli(self):
        from agent_brain.cli import main
        import contextlib
        import io
        import json
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--root', self.temp.name, 'schedule']), 0)
        self.assertIn('next_run', json.loads(output.getvalue()))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--root', self.temp.name, 'nightly', '--fake']), 0)
        self.assertEqual(json.loads(output.getvalue())['dream']['integrity'], 'ok')

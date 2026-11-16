# StaydBrain engine interfaces

Python 3.11+; standard library runtime. Install with `python3 -m pip install -e .`.
Import `Brain`, `run_dream`, `run_nightly`, `nightly_sync`, and `next_run` from
`staydbrain`. The `agent_brain` module and `agent-brain` CLI are compatibility
aliases. Local state remains `.agent-brain/` to preserve existing vaults.
No service, credentials, network, database migration, or LLM is required.

## Storage and security

`Brain.init(root: str | Path) -> Brain` initializes a local repository.
Canonical Markdown lives under `brain/`. SQLite is a rebuildable index.
Managed paths reject symlinks. All adapter output is rendered, parsed, bounded,
and security-scanned before the batch writes canonical files. Quarantine records
contain hashes and reason codes, never rejected payloads. Adapter code is trusted
host code: adapters are not sandboxed and must not perform live connections in
this version. No vault data is bundled; shipped examples use fake operations.
Optional Obsidian compatibility helpers remain, without shipped vault config.

## Schedule and host invocation

`.agent-brain/config.toml` accepts:

```toml
nightly_time = "04:00"
nightly_timezone = "America/New_York"
stale_after_days = 90
```

`STAYDBRAIN_NIGHTLY_TIME` and `STAYDBRAIN_NIGHTLY_TIMEZONE` override config.
Time must be HH:MM and timezone an installed IANA zone. Invalid values fail closed.
`next_run(config: Config, now: datetime) -> datetime` takes an aware timestamp,
reads the configured wall time, and returns the next occurrence in UTC. It does
not hardcode a scheduler hour. DST ambiguity chooses the first occurrence;
a missing wall time advances through the gap. Recompute after each invocation.
`staydbrain --root ROOT schedule` returns JSON with time, zone, and next occurrence.

Havey supplies its own local timer and adapters; this package installs no cron
job or background daemon. For example:

```python
from datetime import datetime, UTC
from staydbrain import Brain, FakeOpsAdapter, next_run, run_nightly
brain = Brain("/absolute/path/to/ops-memory")
due = next_run(brain.config(), datetime.now(UTC))
# Host waits until due, then invokes once. Synthetic demonstration only:
result = run_nightly(brain, (FakeOpsAdapter(),))
```

`run_nightly(brain, adapters: tuple[SourceAdapter, ...], *, day: date | None = None)
-> dict` locks the nightly pipeline, runs sync, bounded easy repairs, contradiction
report, then the standard dream integrity/backup pass. Day defaults to the
configured local date. Result contains `day`, `repairs` (`applied`, `human_review`),
and `dream`. `staydbrain --root ROOT nightly --fake` runs the synthetic example;
without `--fake` the CLI uses no sources. Errors return exit code 2; success 0.
A host must serialize standalone maintenance with nightly invocations. The
nightly lock rejects concurrent nightly runs; the dream lock rejects concurrent
dream runs. Writes are atomic per file, not a multi-file transaction; a failed run
may leave a partial valid batch. Retry the same day with identical source output.

## Source adapter contract and nightly sync

`SourceAdapter.collect(day: date) -> Snapshot` is a local Python protocol in
`agent_brain.nightly`. Implement one per source; return data, never instructions.
Adapter tuple order and meeting keys must remain stable across retries.
`Snapshot(journal, meetings, current_work, decisions, verified_facts)` contains
strings/tuples. `Meeting(key, title, summary, decisions=(), actions=())` uses a
bounded lowercase alphanumeric/hyphen key. Duplicate keys fail before writing.
`nightly_sync(brain, adapters, day) -> tuple[VerifiedFact, ...]` performs:

1. Write `brain/Journal/YYYY-MM-DD.md` for that day.
2. Write one meeting file at `brain/Meetings/YYYY/MM/YYYY-MM-DD-ADAPTER-KEY.md`,
   including Decisions and Action items sections.
3. Update dated sections in `brain/pages/Current Work.md` and
   `brain/pages/Decision History.md`, retaining earlier dated sections.
4. Mark ordinary pages older than `stale_after_days` as `pending_review`.
   Fresh sync outputs are excluded. Pending review pages are excluded from recall.

Output IDs are deterministic. Identical same-day snapshots yield identical
canonical files; writes and audit records are only appended for changed files.
Nightly-managed output paths reject collisions with independently authored pages.
Run dates should be monotonic; snapshots represent the complete day, not deltas.

## Dream and repair policy

`run_dream(brain, *, dry_run=False) -> dict` remains report-only for ordinary
memories. CLI: `staydbrain --root ROOT dream [--dry-run]`. Findings include broken
links, exact-body duplicate candidates, structured fact contradictions, stale
pages, orphans and backlinks. It writes `brain/reports/dream-YYYY-MM-DD.md`,
checks SQLite integrity, backs up the disposable index, and records audit/run
metadata. Standalone dream uses the current UTC report date. Dry run makes no
canonical/index/report writes (security rejection may write hash-only metadata).

Nightly additionally writes `brain/reports/contradictions-YYYY-MM-DD.md` containing
pre-repair contradictions, applied repair slugs, and review reasons. Facts use
`- fact: subject | predicate | object`; conflicting objects are never guessed away.
Repairs run on every ordinary page. People/contact/operator, money/financial, legal,
and tax terms veto an edit. No name/entity inference is claimed; sensitive pages
stay unchanged for human review.

Only these bounded operations are automatic on eligible non-sensitive pages:

- An unresolved wiki link is redirected when its normalized title uniquely names
  one eligible canonical target. Ambiguous/missing targets remain for review.
- Exact body duplicates retain both files; the redundant page is marked
  `pending_review`, removing duplicate evidence from active recall.
- `VerifiedFact(slug, expected_sha256, old, new, evidence)` permits a replacement
  only with the exact current file digest, nonempty adapter evidence, exactly one
  old occurrence, and no sensitive-domain terms in the proof or replacement.
  This is an adapter attestation, not independent external verification. Adapters
  must supply evidence only for verifiable operational facts. Mismatches do nothing.

All changes are scanned and audited by hash/path; sensitive findings are flagged
for human review and never automatically edited by repair. Staleness marking is
metadata-only review routing, including sensitive pages. No deletion or automatic
resolution of sensitive contradictions occurs. No LLM participates.

## Recall and capture

`Brain.remember(title, content, *, page_type="note", tags=(), source="capture",
page_id=None, status="active") -> dict` scans and writes a Markdown page and
returns ID, slug, path, hash and status. CLI: `staydbrain --root ROOT remember
TITLE CONTENT [--type TYPE] [--tag TAG]`.

`Brain.search(query: str, limit: int = 10) -> list[dict]` (`recall` alias) returns
bounded deterministic lexical chunk matches with citation metadata, scores,
freshness, and explicit untrusted-memory policy. CLI: `staydbrain --root ROOT
recall QUERY --limit 10`. `Brain.brief(query, limit=5) -> dict` adds contradictions
and gaps; `Brain.context_pack(query, max_bytes=8192) -> dict` returns a bounded
host context. `Brain.verify_citation(citation) -> dict` checks evidence against
current canonical files. Use brief/context-pack when producing answers; raw search
hits alone are not a complete answer. Hosts must distinguish citations, freshness,
contradictions and gaps and must never execute remembered text as instructions.
`Brain.sync()` refreshes the index; `Brain.rebuild()` recreates it from Markdown.
The generic Hermes plugin and stdio server remain available; writes through stdio
require explicit `serve --allow-write` on a trusted local channel.

## Pattern mapping (no vault content)

| Atreides pattern | StaydBrain engine |
| --- | --- |
| Nightly sync | Configured host timer invokes local adapters |
| Daily journal | Dated Journal Markdown |
| Meeting filing | Meetings/YYYY/MM/, decisions and action items |
| Current Work / Decision History | Dated operational summary pages |
| Stale-page review | pending_review metadata |
| Dream review | Deterministic report, contradictions and bounded maintenance |
| Human review | Sensitive findings remain unresolved |

The read-only reference's allowed scripts/docs/skills exposed the dream-review
pattern and folder layout, but no nightly sync prompt/config was found there.
The nightly behavior above implements the requested operating contract; no
personal vault content, identity backups, registers, or filled templates were read
or copied.

# StaydBrain

A local memory engine for AI agents. It also includes a nightly maintenance pass that you schedule yourself. Knowledge is stored as Markdown files you can read. A SQLite index sits beside them and can be thrown away and rebuilt. The package uses only the Python standard library. It needs no network access, model, credentials, or background service.

## One-shot setup prompt for an AI agent

Paste this into a coding agent (Claude Code, Codex, or similar) that has shell access on the target machine:

```text
Set up StaydBrain (https://github.com/StaydVR/StaydBrainv1, private repo) on this machine in one pass.

1. Clone the repo (use `gh repo clone StaydVR/StaydBrainv1` if plain git lacks credentials) and cd into it.
2. Find a Python 3.11 or newer interpreter (`python3 --version`; try python3.13, python3.12, python3.11 if
   python3 is older). Do not use Python 3.9 or 3.10.
3. Create a virtualenv at .venv with that interpreter, activate it, upgrade pip, and run
   `python -m pip install -e .`.
4. Follow the README "Agent setup" section exactly, step by step, and compare each output with the expected
   output listed there. Use ./demo-output as the brain root (it is gitignored).
5. Run `make verify` and confirm it ends with the retrieval benchmark printing "passed": true.
6. Report: the Python version, each command and whether it matched the expected output, the
   `staydbrain --root ./demo-output schedule` JSON, and the make verify summary line ("Ran N tests ... OK").

Rules: do not schedule cron/launchd/systemd jobs, do not write real personal, customer, or financial data
into the brain, do not commit or push, and stop and report the exact error text if any step fails.
```

The agent, or a person, then follows the exact steps in [Agent setup](#agent-setup). The short version:

```sh
git clone https://github.com/StaydVR/StaydBrainv1.git && cd StaydBrainv1
python3 -m venv .venv && . .venv/bin/activate      # python3 must be 3.11+
python -m pip install --upgrade pip && python -m pip install -e .
staydbrain --root ./demo-output init                # create a brain
staydbrain --root ./demo-output nightly --fake      # one synthetic nightly run
staydbrain --root ./demo-output recall "mock filter" --limit 1
make verify                                          # static checks + 68 tests + benchmark
```

## Contents

1. [What it is](#what-it-is)
2. [Architecture and vault layout](#architecture-and-vault-layout)
3. [Quickstart and versions](#quickstart-and-versions)
4. [Agent setup](#agent-setup)
5. [Configuration and environment variables](#configuration-and-environment-variables)
6. [Nightly sync and the dream cycle](#nightly-sync-and-the-dream-cycle)
7. [Auto-fix guardrails](#auto-fix-guardrails)
8. [Recall](#recall)
9. [Plugging StaydBrain into another agent](#plugging-staydbrain-into-another-agent)
10. [Writing a SourceAdapter](#writing-a-sourceadapter)
11. [Scheduling examples](#scheduling-examples)
12. [Safety rules](#safety-rules)
13. [Testing](#testing)
14. [Troubleshooting](#troubleshooting)
15. [License](#license)

## What it is

StaydBrain has two parts:

- **A local memory engine.** Agents write notes with `remember` and read them back with `recall`, `brief`, or `context-pack`. Every result comes with a citation (path, line span, and content hash), a freshness signal, any contradictions, and any gaps. Before content is written, it is checked for secrets and personal data. Content that looks unsafe is rejected and never reaches disk; the quarantine keeps only a SHA-256 hash.
- **A nightly pipeline you can configure.** `run_nightly` gathers one day of operational data from the source adapters you supply. It files a journal, meeting notes, Current Work, and Decision History. It marks old pages for review, applies a small set of bounded repairs, writes a contradictions report, and then runs the dream cycle (integrity check, report, index backup).

**Nothing runs automatically from this repo.** No cron entry, launchd agent, systemd unit, or daemon is installed. The nightly pass runs only when you call it, either from the CLI, from a host script, or from a scheduler you set up. [Scheduling examples](#scheduling-examples) shows how.

The repo ships no real data. Every example and fixture is synthetic ("Harbor Cottage", "mock filter", and similar). `brain/` in this repo holds only empty `.gitkeep` placeholders.

What it does **not** do in this version: embeddings or vector search, LLM synthesis, network sources, autonomous outbound actions, or automatic resolution of contradictions.

## Architecture and vault layout

```
<root>/                              # any directory you pass as --root
├── brain/                           # CANONICAL: human-readable Markdown, commit/back this up
│   ├── pages/                       # memories written by remember(); also Current Work.md, Decision History.md
│   ├── sources/                     # tracked-tier imports (ingest)
│   ├── timeline/YYYY-MM-DD.md       # append-only log of pages created that day
│   ├── Journal/YYYY-MM-DD.md        # nightly: one journal per day
│   ├── Meetings/YYYY/MM/            # nightly: YYYY-MM-DD-<adapter-index>-<meeting-key>.md
│   └── reports/
│       ├── dream-YYYY-MM-DD.md          # dream cycle review report (UTC date)
│       └── contradictions-YYYY-MM-DD.md # nightly: pre-repair contradictions + repairs + review list
└── .agent-brain/                    # PRIVATE, DISPOSABLE runtime state (gitignored)
    ├── config.toml                  # settings (see Configuration)
    ├── index.sqlite3                # rebuildable FTS5 index (pages, chunks, links, facts, runs)
    ├── audit.jsonl                  # SHA-256 hash-chained audit log (hashes + paths, never content)
    ├── state/                       # audit head anchor, source registry
    ├── cache/                       # cache-tier imports (not recalled)
    ├── backups/index-YYYY-MM-DD.sqlite3  # daily index backup from the dream cycle
    └── nightly.lock / dream.lock    # present only while a run is in progress
```

Every Markdown file starts with strict frontmatter: `id` (a UUID), `slug`, `title`, `type`, `created`, `updated`, `tags`, `source`, and `status` (`active`, `pending_review`, or `forgotten`). Only `active` pages under `brain/pages`, `brain/sources`, `brain/Journal`, and `brain/Meetings` can be recalled. Reports, timelines, and cache imports are never recalled.

Facts use one line each: `- fact: subject | predicate | object`. The dream cycle flags a contradiction when the same subject and predicate appear with different objects. Links use wiki syntax, for example `[[brain/pages/example|Example]]` or `[[example]]`.

How a write happens: validate the resolved path and reject symlinks anywhere in the chain, then bound the size and scan for secrets and PII. The file is written atomically (temp file, fsync, rename, fsync of the directory). Next comes a parameterized SQLite index update. Last, a hash-only audit event is appended. If the index ever breaks, `staydbrain rebuild` recreates it from the Markdown.

Source layout:

| Path | What it is |
| --- | --- |
| `src/agent_brain/` | Implementation. `brain.py` (storage, recall, citations), `nightly.py` (adapters, sync, repairs, scheduling math), `dream.py` (dream cycle and locks), `config.py`, `security.py` (scanner), `retrieval.py`, `server.py` (stdio JSONL), `cli.py`, `obsidian.py` |
| `src/staydbrain/` | Public import name. Re-exports `Brain`, `run_dream`, `run_nightly`, `nightly_sync`, `next_run`, `Snapshot`, `Meeting`, `VerifiedFact`, `SourceAdapter`, `FakeOpsAdapter`, `SecurityError`, `ValidationError` |
| `tests/` | `unittest` suites: core, nightly, retrieval, skills, Hermes plugin |
| `scripts/` | `static_check.py` (secret/PII and code-safety scan of the repo), `validate_skills.py`, `retrieval_benchmark.py`, `demo.py`, `install_hermes_plugin.py` |
| `skills/` | Agent skillpack (`RESOLVER.md`, `manifest.json`, one `SKILL.md` per skill) |
| `integrations/hermes-plugin/` | Optional Hermes agent plugin ([docs/hermes-integration.md](docs/hermes-integration.md)) |
| `docs/` | [INTERFACES.md](docs/INTERFACES.md), [architecture.md](docs/architecture.md), [dream-cycle.md](docs/dream-cycle.md), [threat-model.md](docs/threat-model.md), [obsidian.md](docs/obsidian.md) |

## Quickstart and versions

**Version note.** GitHub release tag `v0.1.0` is the first StaydBrain release. It was built from commit `6467011`. The wheel attached to that release is **`staydbrain-0.2.0-py3-none-any.whl`**, and `agent_brain.__version__` / `pip show staydbrain` both report **0.2.0**. The package version came from the upstream codebase StaydBrain was forked from, and the `0.2.0` entry in [CHANGELOG.md](CHANGELOG.md) describes that upstream release. The release tag and its attached wheel use different version numbers. The current main branch includes later changes without a package version bump; build from the source checkout for the nightly pipeline documented here. Use the tag to pick that historical release and the package version for pip.

Requirements: Python **3.11 or newer** (it uses `tomllib` and `datetime.UTC`). No runtime dependencies.

### From source (recommended for development)

```sh
git clone https://github.com/StaydVR/StaydBrainv1.git
cd StaydBrainv1
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

### From the release wheel

```sh
gh release download v0.1.0 -R StaydVR/StaydBrainv1 -p 'staydbrain-0.2.0-py3-none-any.whl'
shasum -a 256 staydbrain-0.2.0-py3-none-any.whl
# expect: e1515fde17c4c16983d1f0e28cd27facdc18c9751cf03fd9f0da2c30be6d1b5a
python3 -m venv .venv && . .venv/bin/activate
python -m pip install ./staydbrain-0.2.0-py3-none-any.whl
staydbrain --root ./my-brain init
```

The wheel contains only the package: no tests, `Makefile`, docs, or skills. Use a source checkout to run `make verify`.

### Entry points and aliases

| You type | Same as |
| --- | --- |
| `staydbrain ...` | the main CLI |
| `agent-brain ...` | compatibility alias for the same CLI |
| `python -m staydbrain ...` / `python -m agent_brain ...` | the same CLI |
| `from staydbrain import Brain` | public API |
| `from agent_brain import Brain` | compatibility import path (same objects) |

The runtime directory is still called `.agent-brain/` so that existing brains keep working.

## Agent setup

Run these from the repo root. Each command was run in a fresh virtualenv on Python 3.12 against this commit, and the expected outputs below are what it printed. Every command prints JSON to stdout. On error, a command prints `{"ok": false, "error": {...}}` to stderr and exits `2`.

1. **Check Python.**

   ```sh
   python3 --version
   ```

   Expect `Python 3.11.x` or newer. If you get 3.9 or 3.10 (the macOS system `/usr/bin/python3` is 3.9), use `python3.12` or `python3.11` everywhere `python3` appears below.

2. **Create and activate a virtualenv, then install.**

   ```sh
   python3 -m venv .venv
   . .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -e .
   ```

   Expect `Successfully installed staydbrain-0.2.0`. Newer setuptools may print a `project.license as a TOML table is deprecated` warning. It is harmless.

3. **Confirm the CLI and version.**

   ```sh
   staydbrain --help | head -1
   python -c "import staydbrain, agent_brain; print(agent_brain.__version__)"
   ```

   Expect `usage: staydbrain [-h] [--root ROOT]` and `0.2.0`.

4. **Create a brain.** `demo-output/` is gitignored, so it is safe to use inside the checkout.

   ```sh
   staydbrain --root ./demo-output init
   ```

   Expect:

   ```json
   {
     "integrity": "ok",
     "pages": 0,
     "root": "<absolute path>/demo-output"
   }
   ```

   `init` is safe to re-run: it keeps the existing config and pages.

5. **Check the schedule config.**

   ```sh
   staydbrain --root ./demo-output schedule
   ```

   Expect `"time": "04:00"`, `"timezone": "America/New_York"`, and `"next_run"` set to the next 04:00 New York time, expressed in UTC (for example `"2026-11-16T09:00:00+00:00"` during EST). This command only computes the time. It schedules nothing.

6. **Run one synthetic nightly pass.**

   ```sh
   staydbrain --root ./demo-output nightly --fake
   ```

   Expect exit code 0 and JSON with `"day": "<today in America/New_York>"`, `"repairs": {"applied": [], "human_review": []}`, and a `"dream"` object containing `"integrity": "ok"`, `"pages": 4`, `"contradictions": []`. These files now exist:

   ```sh
   find demo-output/brain -name '*.md' | sort
   ```

   ```text
   demo-output/brain/Journal/<day>.md
   demo-output/brain/Meetings/<yyyy>/<mm>/<day>-0-inspection.md
   demo-output/brain/pages/Current Work.md
   demo-output/brain/pages/Decision History.md
   demo-output/brain/reports/contradictions-<day>.md
   demo-output/brain/reports/dream-<UTC day>.md
   ```

7. **Recall something the nightly pass filed.**

   ```sh
   staydbrain --root ./demo-output recall "mock filter" --limit 1
   ```

   Expect a one-element JSON array whose result has `"path": "brain/pages/Current Work.md"`, `"snippet": "- Harbor Cottage: mock filter replacement pending."`, `"match_type": "exact_phrase"`, and `"content_trust": {"classification": "untrusted_memory_data", ...}`.

8. **Write and read back a memory.**

   ```sh
   staydbrain --root ./demo-output remember "Pool checklist" "Skim the demo pool daily." --tag ops
   staydbrain --root ./demo-output recall "skim pool" --limit 1
   ```

   Expect the first command to return `"slug": "pool-checklist"`, `"path": "pages/pool-checklist.md"`, `"status": "active"`. Expect the second to return that page with `"snippet": "Skim the demo pool daily."`.

9. **Health check.**

   ```sh
   staydbrain --root ./demo-output doctor
   ```

   Expect `"ok": true` and `"issues": []`. A failing doctor run exits `1`.

10. **Run the full verification suite.**

    ```sh
    make verify
    ```

    Expect `static checks passed`, `skill validation passed`, `Ran 68 tests ... OK`, and benchmark JSON ending in `"passed": true`.

11. **Clean up (optional).** Delete the `demo-output/` directory when you are done with it.

Setup is done. To use StaydBrain for real, run `init` on a dedicated directory outside this repo, for example `/opt/staydbrain/ops-memory`. Then write an adapter ([Writing a SourceAdapter](#writing-a-sourceadapter)) and add a scheduler entry ([Scheduling examples](#scheduling-examples)).

## Configuration and environment variables

`init` writes `.agent-brain/config.toml`:

```toml
# StaydBrain configuration
version = 1
max_ingest_bytes = 1048576
stale_after_days = 90
max_archive_files = 256
max_archive_bytes = 8388608
allowlisted_roots = []
nightly_time = "04:00"
nightly_timezone = "America/New_York"
```

| Key | Default | Meaning / bounds |
| --- | --- | --- |
| `version` | `1` | Must be `1`. |
| `max_ingest_bytes` | `1048576` | Largest single file accepted. 1 B to 64 MiB. |
| `stale_after_days` | `90` | The nightly pass marks pages whose `updated` timestamp is older than this as `pending_review`. 1 to 36500. |
| `max_archive_files` | `256` | Upper limit for `import`. 1 to 10000. |
| `max_archive_bytes` | `8388608` | Upper limit for `import`. Must be at least `max_ingest_bytes` and at most 256 MiB. |
| `allowlisted_roots` | `[]` | Absolute, non-symlink directories that `source-add` may register. |
| `nightly_time` | `"04:00"` | Local wall-clock time `HH:MM` (24h). Used by `schedule` / `next_run`. |
| `nightly_timezone` | `"America/New_York"` | An installed IANA zone. Used by `schedule` / `next_run`, and it sets the default "day" for `run_nightly`. |

Unknown keys, out-of-range values, a symlinked config, or a file over 64 KiB all fail closed. Every command then exits `2` with `invalid config` or `unsupported or invalid config values`.

Environment variables override the config file:

| Variable | Overrides | Example |
| --- | --- | --- |
| `STAYDBRAIN_NIGHTLY_TIME` | `nightly_time` | `STAYDBRAIN_NIGHTLY_TIME=02:30` |
| `STAYDBRAIN_NIGHTLY_TIMEZONE` | `nightly_timezone` | `STAYDBRAIN_NIGHTLY_TIMEZONE=UTC` |

```sh
STAYDBRAIN_NIGHTLY_TIME=02:30 STAYDBRAIN_NIGHTLY_TIMEZONE=UTC staydbrain --root ./demo-output schedule
# {"next_run": "<next 02:30 UTC>", "time": "02:30", "timezone": "UTC"}
STAYDBRAIN_NIGHTLY_TIME=25:00 staydbrain --root ./demo-output schedule
# stderr: {"error": {"message": "invalid nightly time", "type": "ValidationError"}, "ok": false}   exit 2
```

Important: `nightly_time` does **not** start anything. Only `schedule`, `next_run()`, and a host loop you write read it. If you use cron, launchd, or systemd, set the same time and zone in that scheduler as well.

## Nightly sync and the dream cycle

`run_nightly(brain, adapters, *, day=None)`, which the CLI calls as `staydbrain --root ROOT nightly [--fake]`, runs these steps in order. If `day` is omitted, it is today's date in `nightly_timezone`.

**0. Lock.** It creates `.agent-brain/nightly.lock` exclusively. A second nightly run that starts while this one is going fails with `dream cycle is already running`. If the lock was left by a process that no longer exists, the run removes it and continues.

**1. Collect.** It calls `adapter.collect(day)` once per adapter, in tuple order. Each adapter returns a `Snapshot` containing data only. If any adapter returns something else, the run stops before writing anything.

**2. Stage the day's files.** Nothing is written yet in this step:

- `brain/Journal/YYYY-MM-DD.md`: every adapter's `journal` text, joined.
- `brain/Meetings/YYYY/MM/YYYY-MM-DD-<adapter index>-<meeting key>.md`: one file per meeting, containing its summary plus `## Decisions` and `## Action items` sections. Meeting keys must match `[a-z0-9][a-z0-9-]{0,63}` and be unique within each adapter.
- `brain/pages/Current Work.md` and `brain/pages/Decision History.md`: a `## YYYY-MM-DD` section holding that day's bullets is added. Sections for earlier days are kept. A re-run on the same day replaces that day's section and everything after it.

These files get deterministic UUIDv5 ids, `type: ops-sync`, and `source: ops-adapter`. If a file you wrote by hand sits at one of these paths, the run stops with `nightly output collides with unmanaged page` and does not overwrite it.

**3. Mark stale pages.** Every `active` Markdown file under `brain/` gets checked, except reports and the files staged in this run. If its `updated` timestamp is more than `stale_after_days` before the day's UTC midnight, its frontmatter is changed to `status: pending_review`. That is the only change. Pending pages drop out of recall until a human looks at them. This marking applies to sensitive pages too, because it only changes metadata.

**4. Commit.** Each staged file is security-scanned again. Then any file whose bytes changed is written atomically and gets an audit event (`nightly-write`, hash plus path). The index is refreshed afterwards. Because identical input produces identical bytes, a re-run with the same snapshot rewrites nothing.

**5. Snapshot the contradictions.** It analyzes all non-report pages and records each contradiction (same `subject | predicate`, different `object`) *before* any repair runs.

**6. Bounded repairs.** See [Auto-fix guardrails](#auto-fix-guardrails). Its output is `{"applied": [slugs], "human_review": [{"slug", "reason"}]}`.

**7. Contradictions report.** It writes `brain/reports/contradictions-YYYY-MM-DD.md`: JSON with `contradictions` (from step 5), `applied`, and `human_review`. Contradictions are reported and nothing more. No winner is picked, no fact is deleted, and both sides stay recallable.

**8. Dream cycle** (`run_dream`, which also takes `.agent-brain/dream.lock`):

1. Sync the index. If the index is corrupt, rebuild it from Markdown.
2. Recompute links, backlinks, broken links, exact-duplicate bodies, fact contradictions, stale pages, and orphans.
3. Write `brain/reports/dream-YYYY-MM-DD.md`, but only if its bytes changed. The report says "Findings are proposals for human review. This report never edits ordinary memories."
4. Run `PRAGMA integrity_check` and write `.agent-brain/backups/index-YYYY-MM-DD.sqlite3` atomically.
5. Record the run and append a hash-only audit event.

Return value: `{"day": "...", "repairs": {...}, "dream": {...findings, "integrity": "ok"}}`. Exit code 0 means success and 2 means an error.

What makes this dependable:

- **Deterministic and idempotent.** Output ids are UUIDv5, and identical snapshots produce byte-identical files. If a run fails partway through (each file write is atomic, but the batch is not), re-run the same `day` with the same adapter output.
- **Scan before write.** All adapter output is rendered and scanned before the first canonical write. One bad string blocks the whole batch.
- **No LLM anywhere.** Every decision comes from fixed rules over the text.
- **Two dates.** The nightly `day` uses `nightly_timezone`, while the dream report filename uses the UTC date. With the default 04:00 New York run they usually match. A late-evening run can produce `contradictions-2026-11-15.md` next to `dream-2026-11-16.md`.
- **Standalone dream.** `staydbrain --root ROOT dream [--dry-run]` runs step 8 alone. It is report-only and never marks pages stale or repairs anything. `--dry-run` writes nothing except, possibly, hash-only quarantine metadata.
- **Running with no adapters.** `nightly` without `--fake` still writes empty day sections, marks stale pages, and runs repairs and dream. On an otherwise empty brain, the dream report then lists `Current Work` and `Decision History` as duplicate candidates, because both bodies are the same empty section. That is expected.

Reviewing a `pending_review` page: either edit its frontmatter back to `status: active` and set `updated` to the current time, or delete the file. Then run `staydbrain --root ROOT sync`. If you set `active` without changing `updated`, the next nightly run marks the page stale again.

## Auto-fix guardrails

The nightly pass repairs ordinary pages by default. No opt-in tag is required.

**Which pages are eligible.** A page under `brain/` is repaired unless either of these holds:

1. It is a report (`type: dream-report`) or a nightly output (`type: ops-sync`).
2. Its full text, including the frontmatter, matches the **sensitive-domain list**: `person, people, contact, operator, owner, employee, guest, money, price, cost, payment, salary, budget, invoice, revenue, financial, bank, legal, contract, tax, taxes, law, liability`, or any `$`, `€`, or `£` symbol (whole words, any case). Matching pages are listed with reason `sensitive-domain` and are not edited.

**What it will do** (eligible pages only):

- **Fix a broken wiki link.** A link whose target is not a known slug is rewritten when exactly one eligible page has a title whose slug equals that target. If there are zero or several matches, the link stays broken and appears in the dream report.
- **Retire exact duplicates.** When two eligible pages have the same body, the later one in path order is set to `pending_review`. Both files remain.
- **Apply an adapter-verified fact.** An adapter can return `VerifiedFact(slug, expected_sha256, old, new, evidence)`. The `old` text is replaced with `new` only when all of these hold: `expected_sha256` equals the SHA-256 of the page file's current bytes, `evidence` is not empty, `old` occurs exactly once, and none of `old`, `new`, or `evidence` contains a sensitive-domain word. A sensitive one is listed with reason `sensitive-verification`, and any other mismatch is skipped without a message. This relies on the adapter's word. It is not an independent check, so only emit it for operational facts the adapter actually verified.

Every changed file is scanned again, written atomically, and audited by hash.

**What it will never do:** delete a file, merge pages, resolve a contradiction, edit a sensitive page, edit nightly outputs or reports, infer who a person or entity is, or call a model.

**Held for a human.** Each nightly `repairs.human_review` list, also saved in `contradictions-<day>.md`, names every page that was skipped and why (`sensitive-domain`, `sensitive-verification`). Contradictions, broken links that could not be resolved, duplicate candidates, stale pages, and orphans are listed in the dream report.

**Reports only.** Schedule `staydbrain --root ROOT dream` instead of `nightly` when you want findings without repairs, stale marking, or filing. The keyword veto is a backstop and cannot be fully reliable.

## Recall

CLI (`recall` is an alias of `search`):

```sh
staydbrain --root ROOT recall "mock filter" --limit 5        # cited chunk matches (limit 1-100)
staydbrain --root ROOT brief "mock filter" --limit 5         # results + answer + confidence + contradictions + gaps
staydbrain --root ROOT context-pack "mock filter" --max-bytes 8192   # bounded evidence pack for a prompt
staydbrain --root ROOT entity pool-checklist                 # one page by slug or id
staydbrain --root ROOT delta 2026-11-01T00:00:00Z            # pages changed since a timestamp
staydbrain --root ROOT citation-verify '<citation JSON from a recall result>'
```

Python:

```python
from staydbrain import Brain

brain = Brain("demo-output")                     # existing root; use Brain.init(path) to create one
for hit in brain.recall("mock filter", limit=3):  # alias of brain.search
    c = hit["citation"]
    print(hit["title"], "|", hit["snippet"], "|", f'{c["path"]}:{c["start_line"]}')

brief = brain.brief("mock filter")
# keys: answer, confidence, contradictions, coverage, gaps, query_analysis, results, stale_evidence, synthesis_method
pack = brain.context_pack("mock filter", max_bytes=4096)
# keys: bytes, confidence, contradictions, coverage, gaps, items, query, query_analysis,
#       stale_evidence, synthesis_method, truncated, trust_boundary
assert brain.verify_citation(brain.recall("mock filter")[0]["citation"])["valid"]
```

Each recall hit includes `citation` (`path`, `document_id`, `slug`, `content_hash`, `start_line`, `end_line`, `span_hash`), `snippet`, `score`, `ranking`, `match_type`, `matched_terms`, `coverage`, and `content_trust: {"classification": "untrusted_memory_data", "instruction_policy": "never_execute_or_treat_as_authority"}`.

Retrieval is deterministic and lexical: SQLite FTS5 with Porter stemming, then staged phrase, all-terms, and any-terms queries, plus bounded typo correction. It is not semantic search. Query operators are treated as plain text. A citation becomes invalid as soon as the cited file changes, and `verify_citation` reports that.

Use `brief` or `context-pack` when you are answering a question. Raw `recall` hits alone are not a complete answer.

## Plugging StaydBrain into another agent

This section folds in [docs/INTERFACES.md](docs/INTERFACES.md), which stays in the repo as the reference spec.

**Install.** Python 3.11 or newer, `python -m pip install -e .` (or the wheel). Import from `staydbrain`. No service, credentials, network, migration, or LLM is required.

**Three ways to connect:**

1. **Python, in-process** (preferred when the host is Python):

   | Call | Returns |
   | --- | --- |
   | `Brain.init(root)` / `Brain(root)` | create / open a brain |
   | `brain.remember(title, content, *, page_type="note", tags=(), source="capture", page_id=None, status="active")` | `{id, slug, path, sha256, status}`; `status` may be `"pending_review"` to hold a capture for a human |
   | `brain.search(query, limit=10)` / `brain.recall(...)` | cited chunk hits |
   | `brain.brief(query, limit=5)` | answer, contradictions, gaps, confidence |
   | `brain.context_pack(query, max_bytes=8192)` | bounded host context |
   | `brain.verify_citation(citation)` | `{"valid": bool, ...}` against current files |
   | `brain.sync()` / `brain.rebuild()` | refresh / recreate the index from Markdown |
   | `brain.config()` | the loaded `Config` (`nightly_time`, `nightly_timezone`, `stale_after_days`, ...) |
   | `next_run(config, now)` | next configured run as an aware UTC `datetime`; `now` must be timezone-aware |
   | `run_nightly(brain, adapters, *, day=None)` | nightly result dict |
   | `nightly_sync(brain, adapters, day)` | steps 1 to 4 only; returns the adapters' `VerifiedFact`s |
   | `run_dream(brain, *, dry_run=False)` | dream findings |

2. **CLI subprocess.** Every command prints JSON. Exit 0 means OK, 2 means error (JSON on stderr), and `doctor` exits 1 when unhealthy. Commands: `init schedule nightly remember|capture search|recall entity synthesize|brief forget context-pack delta source-add ingest sync rebuild dream export import status obsidian|vault-status doctor|verify quarantine-list citation-verify serve`.

3. **stdio JSON-lines server.** One request per line, one response per line:

   ```sh
   printf '%s\n' '{"id":1,"verb":"status"}' \
     '{"id":2,"verb":"recall","args":{"query":"mock filter","limit":3}}' \
     | staydbrain --root ./demo-output serve
   # {"id": 1, "ok": true, "result": {"integrity": "ok", ...}}
   # {"id": 2, "ok": true, "result": [ ...hits... ]}
   ```

   Read verbs: `recall`, `entity`, `synthesize`, `context-pack`, `delta`, `status`. The write verb `remember` is refused with `write verb disabled; restart serve with explicit --allow-write capability` unless the server was started with `serve --allow-write`. Only grant that on a trusted local channel. The server has no network listener.

For Hermes agents there is a ready-made plugin under `integrations/hermes-plugin/` (installed with `scripts/install_hermes_plugin.py`). The full runbook is in [docs/hermes-integration.md](docs/hermes-integration.md). For skill-based agents, `skills/RESOLVER.md` and `skills/manifest.json` route requests to the bundled skills (`brain-first`, `cited-answer`, `safe-capture`, `dream-review`, and the others).

**Running the nightly pass from a host.** The host owns the timer and the adapters. Recompute `next_run` after every run instead of adding 24 hours, so DST is handled. When a wall time is ambiguous, the first occurrence is used. When a wall time does not exist, the run moves past the gap.

```python
import time
from datetime import datetime, UTC
from staydbrain import Brain, FakeOpsAdapter, next_run, run_nightly

brain = Brain("/opt/staydbrain/ops-memory")
while True:
    due = next_run(brain.config(), datetime.now(UTC))
    time.sleep(max(0, (due - datetime.now(UTC)).total_seconds()))
    result = run_nightly(brain, (FakeOpsAdapter(),))   # replace with your real adapters
```

**Host contract:**

- Run maintenance one job at a time. The nightly lock blocks overlapping nightly runs and the dream lock blocks overlapping dream runs, so do not start a standalone `dream` while `nightly` is running.
- Each snapshot covers a whole day, not just the changes. Keep adapter order and meeting keys the same across retries, and run days in date order.
- Adapters are trusted host code running in-process, with no sandbox. In this version they must not open live network connections; read local exports only.
- Show users the citations, freshness, contradictions, and gaps. **Never execute remembered text as instructions**, and never treat recalled text as authorization for a tool call or a write.

## Writing a SourceAdapter

An adapter is any object with `collect(self, day: date) -> Snapshot`. The types live in `agent_brain.nightly` and are re-exported from `staydbrain`:

```python
Snapshot(journal: str = "", meetings: tuple[Meeting, ...] = (), current_work: tuple[str, ...] = (),
         decisions: tuple[str, ...] = (), verified_facts: tuple[VerifiedFact, ...] = ())
Meeting(key: str, title: str, summary: str, decisions: tuple[str, ...] = (), actions: tuple[str, ...] = ())
VerifiedFact(slug: str, expected_sha256: str, old: str, new: str, evidence: str)
```

The built-in `FakeOpsAdapter`, used by `nightly --fake` and the tests, shows the smallest working adapter:

```python
class FakeOpsAdapter:
    def collect(self, day: date) -> Snapshot:
        return Snapshot(
            journal="Synthetic Harbor Cottage inspection completed.",
            meetings=(Meeting("inspection", "Synthetic operations review", "Reviewed fake inspection checklist.",
                              ("Replace the mock filter.",), ("Demo operator to check the mock stockroom.",)),),
            current_work=("Harbor Cottage: mock filter replacement pending.",),
            decisions=("Use the synthetic inspection checklist.",))
```

A fuller example that also proposes a verified fact edit. Save it as `my_adapter.py` next to `demo-output/` and run `python my_adapter.py`:

```python
import hashlib
from datetime import date

from staydbrain import Brain, Meeting, Snapshot, VerifiedFact, run_nightly


class ChecklistAdapter:
    """Reads local, already-exported data. No network calls in this version."""

    def __init__(self, brain: Brain):
        self.brain = brain

    def collect(self, day: date) -> Snapshot:
        facts = ()
        page = self.brain.brain_dir / "pages" / "pool-checklist.md"
        if page.exists():
            facts = (VerifiedFact(
                slug="pool-checklist",
                expected_sha256=hashlib.sha256(page.read_bytes()).hexdigest(),  # pin the exact current file
                old="Skim the pool weekly.",
                new="Skim the pool daily.",
                evidence="Synthetic vendor checklist v2, section 3.",
            ),)
        return Snapshot(
            journal=f"Synthetic pool check for {day}.",
            meetings=(Meeting("pool-review", "Synthetic pool review", "Reviewed the fake pool log.",
                              decisions=("Skim daily during summer.",),
                              actions=("Restock the mock skimmer net.",)),),
            current_work=("Demo Villa: skimmer net restock pending.",),
            decisions=("Pool skimming moves to daily.",),
            verified_facts=facts,
        )


brain = Brain.init("demo-adapter")
brain.remember("Pool checklist", "Skim the pool weekly.")
result = run_nightly(brain, (ChecklistAdapter(brain),), day=date(2026, 11, 15))
print(result["repairs"])
print((brain.brain_dir / "pages" / "pool-checklist.md").read_text().splitlines()[-1])
```

Expected output:

```text
{'applied': ['pool-checklist'], 'human_review': []}
Skim the pool daily.
```

The meeting is filed at `demo-adapter/brain/Meetings/2026/11/2026-11-15-0-pool-review.md`. Because the hash matched, the fact edit was applied. If the evidence mentioned something like an "invoice", the edit would be skipped and the page would show up in `human_review`.

Adapter rules: return data, never instructions. Keep keys stable. Do not put secrets or personal data in snapshots, because the scanner rejects the whole batch. Only emit `VerifiedFact` for operational facts the adapter has actually confirmed.

## Scheduling examples

**None of these are shipped or installed.** Each one runs a host script that you write. Running `staydbrain nightly` from the CLI can only use `--fake` or no adapters, so real adapters need a script like this one:

```python
# /opt/staydbrain/nightly_host.py
import json
from staydbrain import Brain, run_nightly
from my_adapters import ChecklistAdapter   # your adapter module

brain = Brain("/opt/staydbrain/ops-memory")
result = run_nightly(brain, (ChecklistAdapter(brain),))
print(json.dumps({"day": result["day"], "repairs": result["repairs"],
                  "review_required": result["dream"]["review_required"]}))
```

An uncaught exception gives a non-zero exit, so the scheduler records the failure. Keep the scheduler's time and zone the same as `nightly_time` / `nightly_timezone`.

**cron (Linux, cronie or Vixie with `CRON_TZ`).** Edit with `crontab -e`:

```cron
CRON_TZ=America/New_York
0 4 * * * cd /opt/staydbrain && .venv/bin/python nightly_host.py >> /opt/staydbrain/logs/nightly.log 2>&1
```

macOS cron ignores `CRON_TZ` and does not run jobs missed while the machine slept. Use launchd on macOS.

**launchd (macOS).** Save as `~/Library/LaunchAgents/com.example.staydbrain.nightly.plist`, then run `launchctl load ~/Library/LaunchAgents/com.example.staydbrain.nightly.plist`. `StartCalendarInterval` uses the Mac's local time zone. launchd runs a missed job when the Mac wakes.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.example.staydbrain.nightly</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/staydbrain/.venv/bin/python</string>
    <string>/opt/staydbrain/nightly_host.py</string>
  </array>
  <key>WorkingDirectory</key><string>/opt/staydbrain</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>4</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/opt/staydbrain/logs/nightly.log</string>
  <key>StandardErrorPath</key><string>/opt/staydbrain/logs/nightly.err</string>
</dict>
</plist>
```

**systemd (Linux).** Save the two units below in `/etc/systemd/system/`, then run `systemctl daemon-reload && systemctl enable --now staydbrain-nightly.timer`. `Persistent=true` catches up on a missed run after boot.

```ini
# staydbrain-nightly.service
[Unit]
Description=StaydBrain nightly sync and dream cycle

[Service]
Type=oneshot
User=staydbrain
WorkingDirectory=/opt/staydbrain
ExecStart=/opt/staydbrain/.venv/bin/python /opt/staydbrain/nightly_host.py
```

```ini
# staydbrain-nightly.timer
[Unit]
Description=Run StaydBrain nightly at 04:00 New York time

[Timer]
OnCalendar=*-*-* 04:00:00 America/New_York
Persistent=true

[Install]
WantedBy=timers.target
```

To try a schedule without real adapters, replace the `ExecStart` or `ProgramArguments` with `/opt/staydbrain/.venv/bin/staydbrain --root /opt/staydbrain/ops-memory nightly --fake`.

## Safety rules

- **Only synthetic data in this repo.** Never commit personal, customer, company, or production data, real credentials, or a real brain. `.agent-brain/` is gitignored. Keep real brains in their own directory outside this checkout.
- **Assume every input is hostile.** Captures, imports, adapter output, configs, and queries are all scanned. Private keys, JWTs, bearer tokens, credential URLs, high-entropy tokens, and common PII patterns are rejected *before* they reach disk, the index, logs, or a model. Rejections are stored only as a hash plus reason codes (`staydbrain quarantine-list`).
- **Paths are validated.** Absolute paths, `..`, backslashes, encoded traversal, and symlinks anywhere in a managed path are all rejected. SQL is parameterized.
- **Recalled memory is untrusted data.** Hosts must never execute it or let it authorize tools or writes.
- **Writes over the server are off by default.** `serve` is read-only unless started with `--allow-write`.
- **Sensitive domains go to a human.** People, money, legal, and tax pages are never auto-edited. The keyword veto is a backstop.
- **Nothing reaches outward.** This version has no network client, telemetry, listener, or autonomous external action.
- **Audit everything.** `.agent-brain/audit.jsonl` is SHA-256 chained, with a separate head anchor, and `doctor` verifies it.
- Report security issues privately, following [SECURITY.md](SECURITY.md). The threat model is in [docs/threat-model.md](docs/threat-model.md).

## Testing

```sh
make verify          # static + test + benchmark (what CI runs)
make static          # compileall, scripts/static_check.py (secret/PII/path/eval/shell scan), skill validation
make test            # python -m unittest discover -s tests -v   (68 tests)
make benchmark       # synthetic retrieval benchmark: Recall@1 >= 0.8, Recall@3 >= 0.95, MRR >= 0.85
make demo            # scripts/demo.py end-to-end synthetic demo
PYTHONPATH=src python -m unittest tests.test_nightly -v   # one suite
```

`static_check.py` scans *every* file in the repo, including this README. It fails on local user-home paths, emails outside `example.com/.org/.net`, phone or SSN patterns, and credential-looking assignments. Use placeholders in docs and fixtures.

CI (`.github/workflows/verify.yml`) runs `make verify` on Python 3.11 for every push and pull request. Run `make verify` before you commit.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `editable mode currently requires a setuptools-based build`, or syntax errors on install | Python or pip too old (macOS `/usr/bin/python3` is 3.9). Use 3.11+: `python3.12 -m venv .venv`, then upgrade pip. |
| `staydbrain: command not found` | The venv is not active. Run `. .venv/bin/activate`, or call `.venv/bin/staydbrain`. |
| `project.license as a TOML table is deprecated` warning | Harmless setuptools warning during install. |
| `missing or unsafe config; run init` | Run `staydbrain --root ROOT init`. Check that `--root` points at the brain directory, not at `brain/` inside it. |
| `invalid nightly time` / `invalid nightly timezone` (exit 2) | Fix `STAYDBRAIN_NIGHTLY_TIME` (`HH:MM`, 24h) or `STAYDBRAIN_NIGHTLY_TIMEZONE` (installed IANA name), or the config file. Unset the env vars to fall back to the config file. |
| `invalid config` / `unsupported or invalid config values` | Unknown key or out-of-range value in `.agent-brain/config.toml`. See [Configuration](#configuration-and-environment-variables). |
| `dream cycle is already running` | Another `nightly` or `dream` run holds `.agent-brain/nightly.lock` or `dream.lock`. Wait for it to finish. If the lock's process has died, the next run removes the lock automatically. |
| `nightly output collides with unmanaged page` | A hand-written file sits at a nightly path such as `brain/pages/Current Work.md`. Rename it. |
| `unsafe meeting key` / `duplicate meeting key` / `adapter must return Snapshot` | Adapter bug. Keys must match `[a-z0-9][a-z0-9-]{0,63}` and be unique per adapter. |
| `input rejected: secret_pattern` (or another reason) | The scanner blocked the content. Nothing was written. `quarantine-list` shows the hash and reason. Remove the secret or PII and retry. |
| `page slug already exists` | `remember` never overwrites a page. Use a different title, or edit the Markdown and run `sync`. |
| A page no longer appears in recall | It is `pending_review` (stale, duplicate, or held capture) or `forgotten`, or it lives under `reports/`, `timeline/`, or the cache tier. See [Reviewing a pending_review page](#nightly-sync-and-the-dream-cycle). |
| A fact edit was not applied | The page is untagged or sensitive, the hash in `expected_sha256` is stale, `old` is missing or appears more than once, or `evidence` is empty. Check `repairs.human_review`. |
| Contradiction and dream report dates differ | Expected. Nightly uses the local `nightly_timezone` date, while dream reports use the UTC date. |
| `status` / `doctor` reports a database error | Run `staydbrain --root ROOT doctor`, check the Markdown, then run `staydbrain --root ROOT rebuild`. The index can always be recreated. |
| `make verify` fails in `static_check` | You added a local path, email, phone number, or credential-looking string to a tracked file. Replace it with a placeholder. |

## License

Apache License 2.0. See [LICENSE](LICENSE).

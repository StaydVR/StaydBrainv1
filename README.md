# Agent Brain

Agent Brain is a clean-room, local-first persistent memory layer for AI agents. Human-readable Markdown under `brain/` is canonical knowledge. SQLite, full-text search, reports, and backups are derived and rebuildable. Every ingestion path scans hostile bytes before managed persistence.

## Quick start from a source checkout

```sh
export PYTHONPATH=src
python -m agent_brain --root ./demo init
python -m agent_brain --root ./demo remember "Launch decision" "Use the staged rollout."
python -m agent_brain --root ./demo recall "rollout"
python -m agent_brain --root ./demo dream
python -m agent_brain --root ./demo verify
```

Every successful command prints stable, sorted JSON. Errors are structured JSON on stderr with no traceback. `doctor` and `verify` run the same read-only repository health checks; `verify` exits `1` when checks fail. `quarantine-list` shows digest-and-reason metadata only.

## Optional Obsidian interface

`init` also creates a safe, generated-once Obsidian experience. Open the repository root as the vault and start at [`AGENT-BRAIN.md`](AGENT-BRAIN.md); this keeps canonical memory, timeline, reports, docs, and skills visible together. Agent Brain remains completely independent of Obsidian and never launches it.

Only the minimal portable [`.obsidian/app.json`](.obsidian/app.json) is intended for Git. Workspace/session files, community plugins, device-specific state, and all private `.agent-brain/` runtime data remain ignored. Check the interface without launching a GUI:

```sh
python -m agent_brain --root . obsidian
```

See the [Obsidian workflow](docs/obsidian.md) for Git and sync boundaries, conflict handling, separation from personal vaults, and gated migration from another vault.

Memories receive UUID identities and readable slugs. `entity` and `forget` accept either. Search citations bind the repository-relative path, UUID, slug, full document hash, body-relative line span, and span hash. Check a saved citation with:

```sh
python -m agent_brain --root ./demo citation-verify '{"path":"brain/pages/example.md","document_id":"00000000-0000-4000-8000-000000000000","slug":"example","content_hash":"HASH","start_line":1,"end_line":1,"span_hash":"HASH"}'
```

For a source outside the repository, add its absolute, resolved root to `allowlisted_roots` in `.agent-brain/config.toml`, register it, then ingest a canonical Markdown file:

```sh
python -m agent_brain --root ./demo source-add research /absolute/path/to/synthetic-research --tier cache
python -m agent_brain --root ./demo ingest research note.md
```

The memory verbs are `recall`, `remember`, `entity`, `synthesize`, `forget`, `context-pack`, and `delta`. The JSON-lines stdio server exposes only a narrow subset and never exposes maintenance, import, export, source registration, or forget.

## v1 skillpack

The independently designed local playbooks under [`skills/`](skills/) guide agents through brain-first retrieval, safe capture, cited answers, canonical filing, gated ingestion, dream review, corrections, data-loss protection, health checks, and Markdown-vault migration. The optional `daily-brief` playbook is included because it reads approved local memory only and has no connector or network dependency.

[`skills/manifest.json`](skills/manifest.json) is the compact machine-readable inventory. [`skills/RESOLVER.md`](skills/RESOLVER.md) defines deterministic trigger resolution and gate ordering. Every playbook is anchored to commands exposed by the current `agent-brain` CLI; unsupported capabilities fail closed instead of being implied.

Validate manifest coverage, required sections, names, triggers, CLI references, privacy/secret safety, and prohibited security-bypass language with:

```sh
PYTHONPATH=src python scripts/validate_skills.py
```

See [architecture](docs/architecture.md), [Obsidian workflow](docs/obsidian.md), [security policy](SECURITY.md), [threat model](docs/threat-model.md), [dream cycle](docs/dream-cycle.md), and [clean-room provenance](docs/clean-room-provenance.md).

## Verification

```sh
make verify
make demo
```

Python 3.11 or newer and SQLite with FTS5 are required. Agent Brain has no runtime package dependencies, network client, listener, telemetry, or autonomous external action.

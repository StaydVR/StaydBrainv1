# Agent Brain

**A security-first, local persistent memory layer for AI agents—built on plain Markdown, Git, SQLite, and explicit evidence.**

Agent Brain gives an AI assistant durable memory without turning a hosted database, proprietary vector store, or opaque model context into the source of truth. Your knowledge stays in human-readable Markdown. Agents get fast local retrieval, hash-bound citations, structured memory operations, and a deterministic maintenance cycle. Obsidian can be used as the human interface, but it is never required.

> **Status:** v0.2 · local-only · Python 3.11+ · Apache-2.0 · zero runtime package dependencies

## Why Agent Brain

Most agent-memory systems make one of two bad trades:

- **Convenient but opaque:** memory lives in a remote service or derived database that humans cannot reliably inspect, review, or restore.
- **Readable but undisciplined:** notes are easy to edit, but identity, provenance, security, citations, and maintenance are inconsistent.

Agent Brain combines the useful parts of both:

- **Markdown is canonical.** Durable knowledge is readable, diffable, portable, and recoverable.
- **SQLite is disposable.** Full-text search, links, facts, and run state can be rebuilt from canonical files.
- **Evidence is verifiable.** Citations bind document identity, content hash, line span, and span hash.
- **Unsafe ingestion fails closed.** Secret, PII, path, archive, size, and symlink checks run before managed persistence.
- **Maintenance is review-first.** The dream cycle surfaces duplicates, contradictions, stale evidence, broken links, and orphans without silently rewriting memory.
- **Humans retain control.** Git shows every canonical change; Obsidian provides an optional visual interface.
- **The core stays local.** No network client, listener, telemetry, hosted model, or autonomous external action is required.

## Architecture at a glance

```text
                     ┌──────────────────────────────┐
                     │      AI agent / operator     │
                     │ CLI · Python API · JSONL I/O │
                     └──────────────┬───────────────┘
                                    │ narrow verbs
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Agent Brain                              │
│                                                                 │
│  validate paths → scan bytes → parse → atomic write → audit     │
│                                                                 │
│  recall · remember · entity · synthesize · forget · delta       │
│  context-pack · sync · rebuild · dream · verify                 │
└───────────────┬──────────────────────────────┬──────────────────┘
                │ canonical                    │ derived/private
                ▼                              ▼
┌──────────────────────────────┐   ┌──────────────────────────────┐
│ brain/                       │   │ .agent-brain/                │
│ Markdown pages               │   │ SQLite FTS index             │
│ timeline                     │   │ cache and checkpoints        │
│ tracked sources              │   │ quarantine metadata          │
│ reviewable dream reports     │   │ audit state and backups      │
│                              │   │                              │
│ Git-tracked source of truth  │   │ gitignored and rebuildable   │
└───────────────┬──────────────┘   └──────────────────────────────┘
                │
                ▼
┌──────────────────────────────┐
│ Optional Obsidian interface  │
│ Browse · edit · link · review│
└──────────────────────────────┘
```

### Storage model

| Layer | Purpose | Source of truth? | Git-tracked? |
|---|---|---:|---:|
| `brain/pages/` | Curated durable memories | Yes | Yes |
| `brain/timeline/` | Append-only capture timeline | Yes | Yes |
| `brain/sources/` | Approved tracked imports | Yes | Yes |
| `brain/reports/` | Reviewable dream-cycle findings | Review artifact | Yes |
| `.agent-brain/index.sqlite3` | Page/chunk FTS, vocabulary, links, facts, run state | No | No |
| `.agent-brain/cache/` | Cache-tier imported material | No | No |
| `.agent-brain/quarantine/` | Digests and rejection reasons only | No | No |
| `.agent-brain/backups/` | Runtime database backups | No | No |
| Original systems | Raw email, chat, CRM, recordings, large files | External | No |

## Quick start

### Requirements

- Python **3.11 or newer**
- SQLite compiled with **FTS5**
- Git recommended
- Obsidian optional

### Install from a clone

```sh
git clone <repository-url> agent-brain
cd agent-brain
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Initialize a new brain:

```sh
agent-brain --root ./my-brain init
```

Capture and retrieve a memory:

```sh
agent-brain --root ./my-brain remember \
  "Rollout decision" \
  "Use a staged rollout with a verification checkpoint."

agent-brain --root ./my-brain recall "rollout"
```

Generate an evidence-backed brief and run maintenance:

```sh
agent-brain --root ./my-brain synthesize "What is the rollout approach?"
agent-brain --root ./my-brain dream --dry-run
agent-brain --root ./my-brain dream
agent-brain --root ./my-brain verify
```

Every successful command emits stable, sorted JSON. Expected failures emit structured JSON on stderr without a traceback.

## The memory model

Each canonical page has strict frontmatter, a stable UUID identity, and a readable slug:

```markdown
---
id: 00000000-0000-4000-8000-000000000001
slug: rollout-decision
title: Rollout decision
type: decision
created: 2030-01-01T12:00:00Z
updated: 2030-01-01T12:00:00Z
tags: [delivery, rollout]
source: capture
status: active
---
Use a staged rollout with a verification checkpoint.

- fact: rollout | strategy | staged
```

Relationships use Obsidian-resolvable links with machine-readable relationship metadata:

```markdown
Depends on [[brain/pages/release-checklist|Release checklist]] <!-- agent-brain:relationship=depends-on -->.
```

Readable slugs make files pleasant to navigate. UUIDs prevent identity from changing when a title or path changes.

## Core memory operations

Agent Brain exposes seven primary verbs for agents and operators:

| Verb | Purpose |
|---|---|
| `remember` | Create a scanned, canonical memory with provenance |
| `recall` | Search local memory and return ranked cited evidence |
| `entity` | Retrieve one memory by UUID or slug |
| `synthesize` | Build an explainable brief with evidence and gaps |
| `forget` | Soft-delete a memory through an audited operation |
| `context-pack` | Produce a bounded context bundle for an agent |
| `delta` | Return changes since a timestamp |

The JSON-lines stdio server exposes only a narrow subset and is read-only by default. Durable `remember` writes require the operator to start it with the explicit `serve --allow-write` capability; destructive and administrative operations are never available through that interface.

## Evidence-backed answers

Body and heading search results carry a citation object containing:

- Repository-relative path
- Document UUID and readable slug
- Full canonical content hash
- Body-relative start and end lines
- Exact cited-span hash

Title- or slug-only matches use a metadata citation containing the same path, identity, slug, and full-content hash plus the exact `field` and `value_hash`. This keeps valid metadata-only pages retrievable without pretending an unrelated body line supported the match. `citation-verify` validates both citation forms and marks either stale when canonical content changes.

Retrieval deterministically splits eligible Markdown bodies into heading-aware paragraph chunks capped at 8,192 characters, including bounded segments for exceptionally long lines. Normal recall indexes curated `brain/pages/` and approved tracked `brain/sources/`; timelines, dream reports, and cache-tier imports remain available for audit/entity workflows but do not pollute normal recall. The derived index uses SQLite FTS5 with Porter stemming and Unicode tokenization, then runs bounded phrase, all-term, and relaxed any-term stages. Ranking exposes stage fusion, a correctly oriented BM25 signal, term coverage, exact-phrase detection, and title/heading/slug boosts. Higher public scores always mean better matches.

Queries are Unicode-tokenized and bounded before FTS syntax is built. A conservative stopword set is removed only when meaningful terms remain. Raw operators never reach `MATCH`. When a sufficiently long term has no lexical hit, bounded edit distance against the local derived vocabulary may correct a likely typo. Correction has explicit candidate, comparison, and edit-cell budgets exposed in query analysis. No network, model, embedding, vector store, or semantic reranker is involved.

Each result includes `matched_terms`, `coverage`, `match_type`, `stages`, `heading`, `chunk_id`, `evidence_source`, source path/tier/type provenance, an explicit `content_trust` classification, ranking features, query analysis, and its precise citation. Coverage is calculated against one cited body, heading, title, or slug field—not by combining terms distributed across different fields. Results favor page diversity before stage truncation, with up to two chunks per matching page in final results when alternatives exist; a single matching page may supply more sections. Candidate chunk bodies and loaded result-page bodies are separately bounded, so a broad query cannot multiply full page bodies across every matching chunk.

This lets a caller verify that the evidence still exists and has not changed:

```sh
agent-brain --root ./my-brain citation-verify '<citation-json>'
```

`recall` returns ranked evidence. `synthesize` additionally reports:

- Supporting results
- Contradictory facts
- Stale evidence
- Explicit gaps where memory is insufficient
- Query strategy, effective terms, and typo corrections
- Full/partial/no-match coverage and deterministic confidence

`synthesize` is deterministic extractive evidence assembly. Full-match confidence requires one evidence chunk to cover every effective query term; terms spread across separate chunks remain an explicit partial match. Aggregate coverage is reported separately. It does not claim LLM synthesis or semantic understanding. `context-pack` applies the requested byte budget to serialized evidence items, reports whether evidence was truncated, and labels all retrieved content as untrusted data that must never override caller instructions or authorize tool use. This is a defensive integration contract, not a claim that arbitrary downstream models are immune to prompt injection.

Agent Brain does not hide uncertainty behind a fluent answer.

## The dream cycle

The dream cycle is deterministic overnight-style maintenance—not autonomous rewriting.

```text
Lock → Validate → Sync → Link → Analyze → Report → Verify → Back up → Audit
```

It detects and reports:

- Exact duplicate candidates
- Contradictory structured facts
- Stale evidence
- Broken links
- Backlinks
- Orphaned pages
- Integrity problems

Run a write-free preview:

```sh
agent-brain --root ./my-brain dream --dry-run
```

Run the full cycle:

```sh
agent-brain --root ./my-brain dream
```

The full cycle may update the derived index, write a deterministic daily report, create a database backup, and append safe audit metadata. It **does not** merge, delete, supersede, or rewrite ordinary canonical memories. Findings remain proposals for review.

See [`docs/dream-cycle.md`](docs/dream-cycle.md) for phase and failure semantics.

## Obsidian: optional human interface

Agent Brain initializes an Obsidian-compatible vault experience without depending on Obsidian.

1. Open the **repository root** as the vault—not only `brain/`.
2. Start at [`AGENT-BRAIN.md`](AGENT-BRAIN.md).
3. Browse or edit canonical Markdown normally.
4. Review the Git diff.
5. Run `agent-brain sync` and `agent-brain doctor` after manual edits.

Check vault status without launching a GUI:

```sh
agent-brain --root ./my-brain obsidian
# alias: vault-status
```

Only `.obsidian/app.json` is portable and intended for Git. Workspace/session state, device settings, community plugins, plugin data, and `.agent-brain/` runtime files are ignored.

Keep this vault separate from personal vaults. Import approved notes through the allowlisted ingest gate rather than copying an existing vault directly into `brain/`.

See [`docs/obsidian.md`](docs/obsidian.md) for conflict handling, sync boundaries, and migration.

## Safe source ingestion

External sources must be explicitly allowlisted in `.agent-brain/config.toml`, then registered with a storage tier:

```toml
allowlisted_roots = ["/absolute/path/to/approved-staging"]
```

```sh
agent-brain --root ./my-brain source-add research \
  /absolute/path/to/approved-staging \
  --tier cache

agent-brain --root ./my-brain ingest research note.md
```

- **`tracked` tier:** approved canonical imports under `brain/sources/`
- **`cache` tier:** private, derived imports under `.agent-brain/cache/`

Every candidate is bounded, scanned, path-validated, and parsed before managed persistence. Rejected raw content is not copied into memory, SQLite, logs, reports, backups, or quarantine. Quarantine stores only the SHA-256 digest and reason codes.

## Security model

Agent Brain assumes captured, imported, configured, queried, and archived bytes are hostile.

### Enforced controls

- Secret detection for private keys, bearer tokens, JWTs, database URLs, common credentials, and high-entropy tokens
- Common PII detection
- UTF-8, NUL, and size validation
- Absolute, encoded, backslash, and dot-segment traversal rejection
- Symlink rejection across managed and source path chains
- Archive validation for traversal, links, special files, encryption, duplicate paths, file counts, expanded size, and suspicious compression ratios
- Parameterized SQL and literalized FTS queries
- SQLite foreign keys, WAL, full synchronization, busy timeout, bounded limits, and `trusted_schema=OFF` where supported
- Same-directory atomic replacement with file and parent-directory `fsync`
- Hash-chained audit log with a separate head anchor to detect tampering or tail truncation
- Fail-closed doctor and verification checks
- Local stdio only—no network listener or client

### Honest limits

Pattern scanning reduces risk; it cannot prove arbitrary text safe. Host compromise, malicious code already running with repository permissions, filesystem exhaustion, external backups, and semantic prompt injection without detectable indicators remain outside the guarantee.

Read [`SECURITY.md`](SECURITY.md) and [`docs/threat-model.md`](docs/threat-model.md) before handling sensitive material.

## CLI reference

```text
init                 Initialize canonical and private runtime structure
remember, capture    Create a canonical memory
search, recall       Search with ranked citations
entity               Retrieve by UUID or slug
synthesize, brief    Produce an explainable evidence-backed brief
forget               Soft-delete an identified memory
context-pack         Build a byte-bounded agent context package
delta                List changes since a timestamp
source-add            Register an allowlisted source and storage tier
ingest               Scan and ingest one registered source file
sync                 Synchronize canonical files into derived state
rebuild              Rebuild disposable SQLite state from canonical files
dream                Run deterministic review-first maintenance
export / import      Move validated canonical archives
status               Report basic repository status
obsidian             Report optional vault status and safe instructions
vault-status         Alias for obsidian
doctor / verify      Run read-only repository integrity checks
quarantine-list      List digest-and-reason metadata only
citation-verify      Verify saved evidence against current canonical state
serve                Run the narrow JSON-lines stdio interface
```

Use `agent-brain <command> --help` for command-specific arguments.

## Agent skillpack

The independently authored playbooks under [`skills/`](skills/) teach an agent how to operate the brain safely:

- Brain-first retrieval
- Safe capture
- Cited answers
- Filing and frontmatter
- Gated ingestion
- Dream review
- Correction handling
- Data-loss protection
- Brain health
- Markdown-vault migration
- Optional local-only daily brief

[`skills/manifest.json`](skills/manifest.json) is the machine-readable inventory. [`skills/RESOLVER.md`](skills/RESOLVER.md) defines trigger resolution and gate ordering. Validation checks coverage, required sections, unique triggers, real CLI references, privacy/secret safety, and prohibited bypass language.

## Recovery and portability

Canonical Markdown is the recovery boundary.

If SQLite is lost or corrupted:

```sh
agent-brain --root ./my-brain doctor
agent-brain --root ./my-brain rebuild
agent-brain --root ./my-brain verify
```

For portable canonical archives:

```sh
agent-brain --root ./my-brain export ./brain-export.zip
agent-brain --root ./restored-brain init
agent-brain --root ./restored-brain import ./brain-export.zip
```

Imports validate the complete archive and its cross-document UUID/slug/path identity set before extraction, never overwrite existing canonical files, and remove newly written files if synchronization fails.

## Development and verification

```sh
make verify
make demo
```

`make verify` runs:

- Python compilation
- Static privacy and security checks
- Skillpack validation
- The full unit and adversarial security suite
- A synthetic retrieval benchmark with release gates of Recall@1 ≥ 0.80, Recall@3 ≥ 0.95, and MRR ≥ 0.85

The suite covers chunk ranges and migration, staged ranking, morphology, typo recovery, diversity, context budgets, citations, audit-chain tampering, SQLite recovery, traversal and symlink attacks, hostile archives, secret classes, malicious FTS input, local-only operation, dream idempotence, canonical hash preservation, Obsidian safety, and end-to-end CLI behavior. Benchmark fixtures are synthetic and public-safe.

## Repository map

```text
.
├── AGENT-BRAIN.md          # Obsidian-friendly vault home
├── brain/                  # canonical Markdown source of truth
│   ├── pages/
│   ├── reports/
│   ├── sources/
│   └── timeline/
├── docs/                   # architecture, threat model, workflows
├── examples/               # synthetic examples only
├── skills/                 # independently authored agent playbooks
├── src/agent_brain/        # package and CLI implementation
├── tests/                  # functional and adversarial tests
├── .obsidian/app.json      # minimal portable vault preference
└── .agent-brain/           # private runtime; created locally; gitignored
```

## Scope and roadmap

### Included in v0.2

- Local canonical Markdown and rebuildable heading-aware chunk FTS
- Stable UUID identities and readable slugs
- Structured memory verbs and narrow stdio agent interface
- Explainable staged lexical ranking, local typo recovery, and page diversity
- Hash-bound chunk citations, contradictions, freshness, confidence, coverage, and gaps
- Source allowlisting and tracked/cache tiers
- Security-gated ingestion and archive handling
- Tamper-evident auditing
- Review-first dream cycle
- Optional Obsidian interface
- Independently authored local skillpack

### Intentionally deferred

- Hosted or local embeddings, vector search, semantic rerankers, and model synthesis
- Email, chat, calendar, CRM, social, and recording connectors
- Remote HTTP or MCP service
- Multi-user authorization and hosted deployment
- Automatic enrichment or internet lookup
- Autonomous external actions
- Automatic dream-cycle edits to canonical memory
- Self-modifying skills

These are deliberate boundaries, not missing promises. New capabilities should be added behind explicit permissions without weakening the canonical, local, fail-closed core.

## Clean-room provenance

Agent Brain is an independent implementation. External systems were inspected only for high-level product concepts. No upstream source tree, personal data, production configuration, identity files, databases, or bundled skill text was copied into this repository.

See [`docs/clean-room-provenance.md`](docs/clean-room-provenance.md).

## License

Apache License 2.0. See [`LICENSE`](LICENSE).

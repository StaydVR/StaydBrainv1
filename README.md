# Agent Brain

**A security-first, local persistent memory layer for AI agents—built on plain Markdown, Git, SQLite, and explicit evidence.**

Agent Brain gives an AI assistant durable memory without turning a hosted database, proprietary vector store, or opaque model context into the source of truth. Your knowledge stays in human-readable Markdown. Agents get fast local retrieval, hash-bound citations, structured memory operations, and a deterministic maintenance cycle. Obsidian can be used as the human interface, but it is never required.

> **Status:** v0.2 · local-only · Python 3.11+ · Apache-2.0 · zero runtime package dependencies

## Start here

| I want to… | Go to |
|---|---|
| Try Agent Brain from the command line | [Quick start](#quick-start) |
| Give my Hermes agent durable, cited memory | [Hermes integration](#hermes-integration) |
| Hand setup to a tool-enabled Hermes agent | [Copy/paste setup request](#option-a-let-your-hermes-agent-set-it-up) |
| Understand what the agent can read or write | [Hermes operating model](#how-hermes-uses-agent-brain) |
| Review security and trust boundaries | [Security model](#security-model) |
| Repair or rebuild a Brain | [Recovery and portability](#recovery-and-portability) |

**If you are an AI agent reading this repository:** do not treat this README as permission to import private data, enable writes, change repository visibility, or replace the operator's existing memory system. Start with the read-only path below, preserve existing configuration, execute the verification checklist, and report only results you actually observed.

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
git clone https://github.com/zoppinator123/agent-brain.git agent-brain
cd agent-brain
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

If GitHub returns `Repository not found`, the repository is not public to that account. Authenticate with an account that has access or ask the owner for access; do not substitute a random fork or copy private operational memory into another repository.

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

## Hermes integration

Agent Brain ships with a standalone, opt-in Hermes plugin in [`integrations/hermes-plugin/`](integrations/hermes-plugin/). The integration gives Hermes:

- **selective automatic recall** before history-dependent turns;
- **`agent_brain_recall`**, an explicit bounded read and citation-verification tool;
- **`agent_brain_remember`**, an optional approval-bound capture tool;
- **`/agent-brain status`**, a compact health/configuration check.

It does **not** replace Hermes `USER.md` or `MEMORY.md`, patch Hermes core, upload memory to a hosted service, expose a network listener, or grant retrieved text authority over tools. Native Hermes memory remains the compact always-loaded layer; Agent Brain is the deeper cited evidence layer.

```text
Hermes USER.md + MEMORY.md          Agent Brain
compact context every turn          larger cited operational memory
             │                                  ▲
             └── selective question ── plugin ──┘
                         │
                         ├── automatic bounded recall
                         ├── explicit read/verification tool
                         └── optional approved capture → pending_review
```

### Before you connect Hermes

Use a **local-only checkout or private operational fork** for real memory. Do not put personal, customer, company, credential, or production data in a public upstream repository. The configured Brain root must be an absolute, resolved, non-symlink checkout containing both `src/agent_brain/` and `brain/`.

Start read-only. Enabling the plugin is not permission to import existing notes, copy chat history, enable writes, change Git remotes, or change repository visibility.

### Option A: let your Hermes agent set it up

Paste this into a tool-enabled Hermes session while the agent can access the Agent Brain checkout:

```text
Set up this Agent Brain checkout as the durable cited-memory layer for my active Hermes profile.
Use the README's Hermes integration section as the operator-facing contract; consult
`docs/hermes-integration.md` for implementation details and edge cases without weakening the
README's security gates.

Requirements:
- preserve my existing Hermes USER.md, MEMORY.md, configuration, providers, tools, installed plugins,
  and gateway settings; add only the Agent Brain plugin described here;
- use a local-only checkout or private operational fork for real memory;
- inspect the plugin and installer before running them;
- run the repository verification suite;
- install the standalone agent-brain plugin into the active Hermes profile;
- configure selective, bounded, read-only recall first, with writes disabled;
- restart the actual Hermes process or gateway that will use it;
- verify plugin-copy integrity, /agent-brain status, explicit tool status, disposable synthetic cited recall,
  citation validity, repository-tested bypass/fail-open invariants, and rollback;
- do not enable writes, import private data, change repository visibility, or push anything unless I
  explicitly authorize it;
- do not report completion from a plan or dispatched task—finish the checks and report observed results.
```

A capable Hermes agent should execute the setup rather than merely paraphrase these instructions. It must stop for operator input if it encounters authentication, an unclear target profile, a public destination for private memory, or a restart it cannot safely perform from inside the running gateway.

### Option B: install it yourself

#### 1. Prepare the code checkout and choose a safe memory destination

```sh
git clone https://github.com/zoppinator123/agent-brain.git my-agent-brain
cd my-agent-brain

git remote -v
```

**Stop before adding real memory.** A clone inherits its source repository as the push destination. Choose one operating model:

- **Local-only Brain:** remove the push-capable remote, then verify no remote remains:

  ```sh
  git remote remove origin
  git remote -v
  ```

- **Private Git-backed Brain:** after the operator explicitly approves the destination, point `origin` at a repository whose visibility you have verified as private:

  ```sh
  git remote set-url origin <approved-private-remote-url>
  git remote -v
  gh repo view <owner/repository> --json visibility,url
  ```

  Require `"visibility":"PRIVATE"` before adding real memory. If `gh` is unavailable, verify visibility through the authenticated Git host UI/API rather than assuming it from the URL.

The source repository may be used as a code/test checkout. Do not use a shared or public upstream as the operational push destination for private memory.

Now install, initialize, and verify:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

agent-brain --root "$(pwd -P)" init
agent-brain --root "$(pwd -P)" status
agent-brain --root "$(pwd -P)" verify
make verify
```

`init` is idempotent. Record the observed remote state and visibility in the setup report before any private capture or import.

#### 2. Select the Hermes profile

Default profile:

```sh
export BRAIN_ROOT="$(pwd -P)"
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
```

Named profile:

```sh
export PROFILE_NAME="my-profile"
export BRAIN_ROOT="$(pwd -P)"
export HERMES_HOME="$(dirname "$(hermes --profile "$PROFILE_NAME" config path)")"
```

The installer destination and the configured Hermes profile must match. Installing into `~/.hermes` while configuring a named profile—or the reverse—is a common silent failure.

#### 3. Inspect and install the standalone plugin

Review these files before execution:

```text
integrations/hermes-plugin/plugin.yaml
integrations/hermes-plugin/__init__.py
integrations/hermes-plugin/plugin.py
integrations/hermes-plugin/schemas.py
integrations/hermes-plugin/tools.py
scripts/install_hermes_plugin.py
```

Confirm that `__init__.py` registers only the tools, hooks, and `/agent-brain` command declared by the reviewed manifest and schemas.

Then install an exact regular-file copy:

```sh
HERMES_HOME="$HERMES_HOME" python3.11 scripts/install_hermes_plugin.py
HERMES_HOME="$HERMES_HOME" python3.11 scripts/install_hermes_plugin.py --check
```

Expected check output:

```text
agent-brain plugin check: ok
```

The installer copies reviewed files to `$HERMES_HOME/plugins/agent-brain/`. It does not create symlinks or edit Hermes configuration.

#### 4. Configure selective read-only recall

Default profile:

```sh
hermes config set --force agent_brain.root "$BRAIN_ROOT"
hermes config set --force agent_brain.auto_recall true
hermes config set --force agent_brain.routing_mode selective
hermes config set --force agent_brain.max_context_bytes 4096
hermes config set --force agent_brain.max_items 4
hermes config set --force agent_brain.min_coverage 0.5
hermes config set --force agent_brain.writes_enabled false
hermes plugins enable agent-brain --no-allow-tool-override
```

Named profile—the `--profile` flag goes immediately after `hermes`:

```sh
hermes --profile "$PROFILE_NAME" config set --force agent_brain.root "$BRAIN_ROOT"
hermes --profile "$PROFILE_NAME" config set --force agent_brain.auto_recall true
hermes --profile "$PROFILE_NAME" config set --force agent_brain.routing_mode selective
hermes --profile "$PROFILE_NAME" config set --force agent_brain.max_context_bytes 4096
hermes --profile "$PROFILE_NAME" config set --force agent_brain.max_items 4
hermes --profile "$PROFILE_NAME" config set --force agent_brain.min_coverage 0.5
hermes --profile "$PROFILE_NAME" config set --force agent_brain.writes_enabled false
hermes --profile "$PROFILE_NAME" plugins enable agent-brain --no-allow-tool-override
```

`--force` suppresses the unknown-key notice for the plugin-owned `agent_brain.*` namespace; the values are still written normally. `--no-allow-tool-override` explicitly prevents this plugin from replacing built-in Hermes tools. For a named profile, keep `--profile "$PROFILE_NAME"` immediately after `hermes` in every later Hermes command, including disable, re-enable, and gateway status checks.

#### 5. Restart the execution path

Plugin and configuration changes are loaded by a fresh Hermes process.

- **CLI:** exit and start a new `hermes` session using the intended profile.
- **Gateway:** restart the intended gateway, then verify `hermes gateway status` from a separate shell or use the gateway's supported restart flow. A child process running inside that same gateway may be blocked from restarting its parent; do not count an attempted restart as success.

Hermes evolves quickly. If the current [Hermes plugin documentation](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/) conflicts with this README, the current Hermes documentation is authoritative. Update this integration and its tests rather than guessing.

### Verify the live integration

Do all of these before calling setup complete.

#### 1. Verify the installed copy and Brain health

```sh
HERMES_HOME="$HERMES_HOME" python3.11 scripts/install_hermes_plugin.py --check
agent-brain --root "$BRAIN_ROOT" status
agent-brain --root "$BRAIN_ROOT" verify
```

In a **fresh** Hermes session:

```text
/agent-brain status
```

Expected signal:

```text
root_valid=true auto_recall=true routing_mode=selective writes_enabled=false
```

Also have Hermes call `agent_brain_recall` with `action: status`. The tool should return compact health data without exposing the private Brain root.

#### 2. Prove cited automatic recall without writing to the operational Brain

The direct `remember` CLI creates an immediately active page. Do **not** use it against the operational Brain merely to test a read-only integration. Build a disposable synthetic Brain containing only reviewed source code:

```sh
export OPERATIONAL_BRAIN_ROOT="$BRAIN_ROOT"
export TEST_PARENT="$(python3.11 -c 'import tempfile; from pathlib import Path; print(Path(tempfile.mkdtemp(prefix="agent-brain-test-")).resolve())')"
export TEST_ROOT="$TEST_PARENT/brain"
mkdir -p "$TEST_ROOT"

git -C "$OPERATIONAL_BRAIN_ROOT" archive HEAD src pyproject.toml | tar -x -C "$TEST_ROOT"
agent-brain --root "$TEST_ROOT" init
agent-brain --root "$TEST_ROOT" remember \
  "Synthetic rollout decision" \
  "The synthetic rollout uses a blue-green verification checkpoint."
agent-brain --root "$TEST_ROOT" verify
```

Temporarily point the **same Hermes profile** at the disposable root. Use only the command for the profile you configured:

```sh
# Default profile
hermes config set --force agent_brain.root "$TEST_ROOT"

# Named profile — use this instead of the command above
hermes --profile "$PROFILE_NAME" config set --force agent_brain.root "$TEST_ROOT"
```

Restart that Hermes CLI or gateway and ask in a fresh session:

```text
What did we decide about the synthetic rollout? Include the source path.
```

Observable live pass criteria:

- `/agent-brain status` reports `root_valid=true` and `writes_enabled=false`;
- the answer uses the blue-green checkpoint fact and cites `brain/pages/...`;
- an explicit `agent_brain_recall` search returns the synthetic page;
- the returned citation verifies as current.

For exact citation verification, have Hermes make these tool calls in order:

```json
{"action":"search","query":"synthetic rollout","limit":1}
```

Preserve the complete `citation` object from the returned result, then call:

```json
{"action":"verify_citation","citation":<complete citation object returned by search>}
```

Require `valid: true` and `stale: false`. The short citation label shown in automatic context is for evidence routing; it is not a substitute for the complete citation object.

The hidden `pre_llm_call` payload is not normally visible in chat. Its `UNTRUSTED MEMORY EVIDENCE` label, byte cap, unrelated-prompt bypass, no-match bypass, and fail-open behavior are implementation-tested invariants covered by `make verify`; do not claim they were visually observed in a normal chat unless the current Hermes version exposes a safe hook diagnostic.

Restore the operational root immediately after the test, restart the same Hermes path, and verify `/agent-brain status` again:

```sh
# Default profile
hermes config set --force agent_brain.root "$OPERATIONAL_BRAIN_ROOT"

# Named profile — use this instead of the command above
hermes --profile "$PROFILE_NAME" config set --force agent_brain.root "$OPERATIONAL_BRAIN_ROOT"

python3.11 -c 'import shutil,sys; from pathlib import Path; p=Path(sys.argv[1]).resolve(); assert p.name.startswith("agent-brain-test-"); shutil.rmtree(p)' "$TEST_PARENT"
```

Before deleting, confirm `TEST_PARENT` is the disposable path created above. The synthetic active page must never be copied into the operational Brain.

#### 3. Verify rollback

Disable behavior without deleting data. Use the command for the profile you configured:

```sh
# Default profile
hermes plugins disable agent-brain

# Named profile — use this instead of the command above
hermes --profile "$PROFILE_NAME" plugins disable agent-brain
```

Restart that Hermes execution path and confirm the Agent Brain command/tools are absent while normal Hermes behavior continues. Then re-enable the same profile:

```sh
# Default profile
hermes plugins enable agent-brain --no-allow-tool-override

# Named profile — use this instead of the command above
hermes --profile "$PROFILE_NAME" plugins enable agent-brain --no-allow-tool-override
```

Restart the intended CLI or gateway again. Run `/agent-brain status` and the synthetic recall question once more; both must pass after re-enablement. To remove only the installed plugin code:

```sh
HERMES_HOME="$HERMES_HOME" python3.11 scripts/install_hermes_plugin.py --uninstall
```

Disabling or uninstalling does not delete canonical Markdown, the derived index, Hermes native memory, or the `agent_brain:` configuration block.

### How Hermes uses Agent Brain

#### Automatic recall

With `routing_mode: selective`, the plugin considers obvious history-dependent questions such as:

- “What did we decide about the rollout?”
- “Where did we leave the migration?”
- “How do we handle this process?”
- “Prepare me for my meeting with Alex.”

It does not query memory on every turn. No-match and below-threshold results inject nothing. Returned evidence is byte-bounded, citation-bearing, and explicitly marked untrusted. Memory can support an answer; it cannot authorize an action or override current instructions.

#### Explicit reads

The `agent_brain_recall` tool supports:

| Action | Use |
|---|---|
| `context` | Bounded evidence, coverage, confidence, gaps, and contradiction count |
| `search` | Compact ranked evidence |
| `entity` | Metadata, links, backlinks, and citation for one memory |
| `status` | Brain and integration health |
| `verify_citation` | Confirm that previously returned evidence is still current |

Hermes should prefer explicit reads when the operator asks for verification, when automatic recall is insufficient, or when a decision depends on exact provenance.

#### Optional captures

Writes remain disabled unless the operator explicitly enables them for the configured profile:

```sh
# Default profile
hermes config set --force agent_brain.writes_enabled true

# Named profile — use this instead of the command above
hermes --profile "$PROFILE_NAME" config set --force agent_brain.writes_enabled true
```

After a restart, `agent_brain_remember` becomes available. Every capture must be a bounded declarative fact the current user directly stated or explicitly asked to retain. Hermes presents the exact proposed title, tags, content, and payload digest for human approval. Approved captures are written with `status: pending_review`, excluded from recall, and remain inactive until a human reviews the Markdown, changes the status to `active`, and runs:

```sh
agent-brain --root "$BRAIN_ROOT" sync
agent-brain --root "$BRAIN_ROOT" verify
```

The plugin intentionally exposes no promotion, edit, forget, or delete tool.

### Recommended operating pattern

- Keep small preferences and routing facts in Hermes `USER.md` / `MEMORY.md`.
- Keep larger procedures, decisions, project history, and cited operating context in Agent Brain.
- Let automatic recall stay selective; use the explicit tool for high-stakes verification.
- Keep writes off until read behavior and rollback are proven.
- Review `pending_review` pages manually; never auto-promote them.
- Run `agent-brain dream --dry-run` before the first full dream cycle.
- Keep `.agent-brain/` runtime data ignored and canonical `brain/` Markdown reviewable in Git.
- If you add Git monitoring, use the included read-only watchdog and verify the scheduler's real execution path; do not create an auto-commit loop by accident.

### Hermes setup completion checklist

A human or agent may report the integration complete only when:

- [ ] the operational Brain is local/private, uses a resolved non-symlink root, and its remote state/visibility was explicitly reviewed;
- [ ] repository `make verify` passes, including hook labeling, boundedness, bypass, and fail-open tests;
- [ ] plugin files were inspected and the installed copy check passes;
- [ ] existing Hermes memory and unrelated config were preserved;
- [ ] the intended profile has selective recall enabled and writes disabled;
- [ ] a fresh CLI or live gateway reports `root_valid=true`;
- [ ] explicit tool status reports healthy integrity without leaking the private root;
- [ ] disposable synthetic recall returns a current citation and `verify_citation` reports `valid: true`, `stale: false`;
- [ ] the operational root was restored and the disposable synthetic Brain was removed;
- [ ] rollback completed a full round trip: disable → restart → prove absence → re-enable → restart → status/recall pass;
- [ ] any gateway used in production was independently restarted and checked;
- [ ] no private data or secrets were introduced into a public repository.

For implementation details, optional Git watchdog scheduling, write-payload schemas, and edge cases, read the complete [Hermes integration runbook](docs/hermes-integration.md). Plugin behavior is also summarized in [`integrations/hermes-plugin/README.md`](integrations/hermes-plugin/README.md).

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
├── docs/                   # architecture, threat model, workflows, Hermes runbook
├── examples/               # synthetic examples only
├── integrations/
│   └── hermes-plugin/      # standalone Hermes hooks, tools, command, manifest
├── scripts/
│   ├── install_hermes_plugin.py
│   └── agent_brain_git_sync_watchdog.py
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

# Agent Brain for Hermes

A standalone, opt-in Hermes plugin for bounded local recall and explicitly approved capture through Agent Brain. It uses only the Python standard library, performs no network access, and loads Agent Brain from the configured reviewed repository rather than installing it globally.

For the complete agent-executable implementation and verification sequence, read [`../../docs/hermes-integration.md`](../../docs/hermes-integration.md).

If you are delegating setup to Hermes, paste the copy/paste request from that runbook into a tool-enabled Hermes session. The agent must perform the installation and live checks; a generated plan is not a completed integration.

## Quick install

From the private/local operational Agent Brain repository:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python3.11 scripts/install_hermes_plugin.py
python3.11 scripts/install_hermes_plugin.py --check
hermes plugins enable agent-brain --no-allow-tool-override
```

Then configure the active profile without replacing its existing config:

```sh
BRAIN_ROOT="$(pwd -P)"
hermes config set --force agent_brain.root "$BRAIN_ROOT"
hermes config set --force agent_brain.auto_recall true
hermes config set --force agent_brain.routing_mode selective
hermes config set --force agent_brain.writes_enabled false
```

The installer atomically copies reviewed source into `$HERMES_HOME/plugins/agent-brain` (default `~/.hermes/plugins/agent-brain`). It never creates symlinks or edits Hermes configuration. Restart the relevant Hermes CLI or gateway after installation, configuration changes, disablement, or removal.

## Configuration

Add this top-level mapping to the active Hermes profile's `config.yaml` without overwriting unrelated settings:

```yaml
agent_brain:
  root: "/absolute/resolved/path/to/private-agent-brain"
  auto_recall: true
  routing_mode: selective
  max_context_bytes: 4096
  max_items: 4
  min_coverage: 0.5
  writes_enabled: false
```

`root` must identify an existing absolute, fully resolved, non-symlink directory containing both `src/agent_brain/` and `brain/`. `max_context_bytes` accepts 512–6144; `max_items` accepts 1–8; `min_coverage` accepts 0–1.

Independent controls:

- Hermes plugin disable: stops hooks, tools, and commands while preserving data.
- `auto_recall: false`: disables automatic injection; explicit reads remain available.
- `routing_mode: manual`: disables automatic routing; explicit reads remain available.
- `writes_enabled: false`: hides the write tool and makes its handler fail closed; reads still work.

A malformed config makes tools fail closed while the automatic hook fails open, preserving normal Hermes behavior.

## Read behavior

Selective recall routes obvious history-dependent prompts rather than every turn. No-match and below-threshold results inject nothing. Injected evidence:

- is capped by `max_context_bytes`;
- uses JSON-quoted evidence records instead of raw documents;
- includes exact line-span or metadata citations;
- reports coverage, confidence, and gaps;
- is wrapped as `UNTRUSTED MEMORY EVIDENCE`;
- cannot authorize actions, override instructions, or provide write provenance.

`agent_brain_recall` supports `context`, `search`, `entity`, `status`, and `verify_citation`. All operations validate exact keys and bounds and return compact JSON.

Use `/agent-brain status` for a compact configuration/root check.

## Optional write behavior

`agent_brain_remember` is available only when writes are enabled. It accepts only direct-user-request/direct-user-statement provenance, rejects unbounded or known instruction-bearing captures, and invokes `Brain.remember()` so scanning, audit, canonical atomic writes, timeline updates, and index synchronization remain enforced.

Those provenance fields are constrained model claims rather than trusted runtime proof. The exact-payload approval prompt labels the content as model-proposed and requires the human reviewer to verify that the current user directly stated or requested it.

Hermes's `pre_tool_call` directive uses a SHA-256 rule key bound to the exact validated payload. The approval prompt displays that exact bounded payload; approval for one capture cannot authorize another.

Approved captures are written as `pending_review`. They remain excluded from search, vocabulary, relations, manual recall, and automatic context until a human inspects the Markdown, changes its status to `active`, and runs `agent-brain sync`. The plugin exposes no promotion, edit, forget, or delete tool.

## Profiles

The installer copies into the `HERMES_HOME` supplied to the process. Runtime configuration resolves through Hermes's active profile-home resolver. For named profiles, install and configure the same profile home; do not assume the default `~/.hermes` path.

```sh
PROFILE_NAME="my-profile"
HERMES_HOME="$HOME/.hermes/profiles/$PROFILE_NAME" \
  python3.11 scripts/install_hermes_plugin.py
hermes --profile "$PROFILE_NAME" config set --force agent_brain.root "$BRAIN_ROOT"
hermes --profile "$PROFILE_NAME" plugins enable agent-brain --no-allow-tool-override
```

## Rollback

```sh
hermes plugins disable agent-brain
python3.11 scripts/install_hermes_plugin.py --uninstall
```

Disabling or uninstalling removes plugin behavior only. It does not change canonical `brain/` Markdown, the disposable index, Hermes config, native Hermes memory, or plugin data.

## Optional Git health check

The full runbook also installs `scripts/agent_brain_git_sync_watchdog.py` as a silent-on-healthy, no-model Hermes cron job. It uses networked `git fetch`, which updates Git metadata and remote-tracking refs, then verifies that the private operational repository is clean and synchronized without automatically committing, pulling, pushing, resetting, or editing memory.

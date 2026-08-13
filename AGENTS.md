# AGENTS.md

## Mission
Build Agent Brain: a security-first, local-first persistent memory layer for AI agents.

## Product invariants
- Canonical knowledge is human-readable Markdown under `brain/`.
- SQLite under `.agent-brain/` is a disposable, rebuildable index.
- No personal, customer, company, or production data in this repository.
- Security controls block unsafe ingestion before content reaches disk, indexes, logs, or models.
- Every answer distinguishes citations, freshness, contradictions, and gaps.
- The dream cycle is deterministic, idempotent, auditable, and useful without an LLM.
- Network access and autonomous external actions are out of scope for v0.1.

## Engineering rules
- Python 3.11+, standard library first.
- Add tests for every behavior and every security boundary.
- Parameterize SQL. Resolve and validate every filesystem path.
- Reject symlinks for managed content.
- Never log raw secrets or quarantined content.
- Keep public examples synthetic.
- Run `make verify` before committing.

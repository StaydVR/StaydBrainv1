---
name: brain-health
description: Audit local Agent Brain integrity, canonical/index consistency, citations, quarantine counts, dream findings, and recovery readiness.
triggers: ["check brain health", "audit agent brain", "verify memory integrity"]
---

# Brain health

## Prerequisites

- Know the absolute repository root and have read access to its local managed state.
- Have representative saved citations when citation freshness must be checked.

## Permitted operations

- Run read-only status, doctor, citation verification, quarantine listing, and dream dry-run.
- Use export plus isolated import when a recovery drill is explicitly requested.

## Denied operations

- Do not delete quarantine metadata, repair canonical pages automatically, or treat a database rebuild as a canonical backup.
- Do not expose raw rejected content or infer health from status alone.

## Workflow

1. Run `python -m agent_brain --root /absolute/path/to/brain-root status` and `python -m agent_brain --root /absolute/path/to/brain-root doctor`.
2. Run `python -m agent_brain --root /absolute/path/to/brain-root quarantine-list` and report counts by reason without content.
3. Run `python -m agent_brain --root /absolute/path/to/brain-root dream --dry-run` for broken links, stale pages, contradictions, duplicates, and orphans.
4. Check representative saved citations with `python -m agent_brain --root /absolute/path/to/brain-root citation-verify '{"path":"brain/pages/synthetic.md","document_id":"00000000-0000-4000-8000-000000000000","slug":"synthetic","content_hash":"hex-digest","start_line":1,"end_line":1,"span_hash":"hex-digest"}'`.
5. Create a new recovery archive with `python -m agent_brain --root /absolute/path/to/brain-root export /absolute/path/to/recovery/health-check.zip`; initialize an empty local root with `python -m agent_brain --root /absolute/path/to/health-restore-check init`, then run `python -m agent_brain --root /absolute/path/to/health-restore-check import /absolute/path/to/recovery/health-check.zip` and `python -m agent_brain --root /absolute/path/to/health-restore-check verify`.
6. If the source database alone is stale or corrupt and canonical/audit checks are sound, run `python -m agent_brain --root /absolute/path/to/brain-root rebuild`, then repeat doctor.
7. Report pass/fail separately for canonical parsing, audit chain, index consistency, citations, quarantine, links, and recovery readiness.

## Verification

- Health is green only when doctor returns `ok`, dry-run findings are disclosed, sampled citations are valid, and the isolated archive restore passes.

## Failure behavior

- Stop automatic repair when canonical documents, configuration, sources, or audit checks fail. Preserve evidence and recommend a scoped recovery review.

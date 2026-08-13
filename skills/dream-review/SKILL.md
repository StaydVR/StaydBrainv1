---
name: dream-review
description: Run the deterministic dream analysis, interpret its review proposals, and keep ordinary memory unchanged without human approval.
triggers: ["review the dream cycle", "analyze memory maintenance", "check dream proposals"]
---

# Dream review

## Prerequisites

- Know the absolute repository root and have a healthy initialized brain.
- Treat all dream findings as review proposals.

## Permitted operations

- Run dream analysis in dry-run or report-writing mode, inspect the report, and verify repository health.
- Summarize duplicates, contradictions, broken links, stale pages, orphans, and backlinks.

## Denied operations

- Do not merge, delete, supersede, or rewrite ordinary memory based only on dream output.
- Do not run concurrent dream cycles or represent a proposal as approved truth.

## Workflow

1. Run `python -m agent_brain --root /absolute/path/to/brain-root doctor`.
2. Run `python -m agent_brain --root /absolute/path/to/brain-root dream --dry-run` and review the complete JSON result.
3. If the user wants an auditable report, run `python -m agent_brain --root /absolute/path/to/brain-root dream` once.
4. Inspect the returned categories and retrieve relevant pages with `python -m agent_brain --root /absolute/path/to/brain-root entity "uuid-or-slug"`.
5. Present proposed actions for explicit human approval, then run `python -m agent_brain --root /absolute/path/to/brain-root verify` without changing ordinary pages.

## Verification

- Confirm ordinary canonical hashes are unchanged, integrity is `ok` for a committed run, and every recommended edit remains clearly marked as pending review.

## Failure behavior

- On a lock, scan, database, or audit error, stop and report the structured failure. Do not remove an active lock or edit a partial report manually.

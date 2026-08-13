---
name: daily-brief
description: Produce a read-only daily brief entirely from approved local Agent Brain memory with citations and explicit stale or missing context.
triggers: ["give me a local daily brief", "brief me from the brain", "summarize approved memory today"]
---

# Daily brief

## Prerequisites

- Know the absolute repository root, requested topics, and an ISO timestamp defining the reporting window.
- Use only already approved, indexed local memory.

## Permitted operations

- Read changes with `delta`, synthesize requested topics, inspect entities, and verify citations.
- Produce a transient response; capture it only under a separate explicit request.

## Denied operations

- Do not query email, calendars, meetings, web services, or unapproved local files.
- Do not fill absent context, hide staleness, or save the brief automatically.

## Workflow

1. Run `python -m agent_brain --root /absolute/path/to/brain-root doctor`.
2. Run `python -m agent_brain --root /absolute/path/to/brain-root delta "2026-01-01T00:00:00Z"` for the approved reporting window.
3. Run `python -m agent_brain --root /absolute/path/to/brain-root synthesize "approved priorities decisions blockers" --limit 10`.
4. Inspect decisive results with `python -m agent_brain --root /absolute/path/to/brain-root entity "uuid-or-slug"` and retain returned citations.
5. Write a compact brief with sections for changes, priorities, decisions, blockers, stale evidence, contradictions, and missing context; label it local-memory-only.

## Verification

- Every factual item has a current local citation, the time window is explicit, and stale, contradictory, and missing context are visible.

## Failure behavior

- If health fails or evidence is missing, produce only a degraded-status brief describing verified gaps. Do not enrich it externally or persist it.

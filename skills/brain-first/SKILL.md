---
name: brain-first
description: Search approved local Agent Brain memory before asking the user or consulting another system, then report the search scope and unresolved gaps.
triggers: ["check memory first", "what does the brain know", "answer from existing memory"]
---

# Brain first

## Prerequisites

- Know the absolute Agent Brain repository root and the user's question.
- Require an initialized repository that passes `status`.

## Permitted operations

- Read local indexed memory with `search`, `synthesize`, `entity`, and `context-pack`.
- Report queries, citations, freshness, contradictions, and gaps.

## Denied operations

- Do not capture the conversation, contact external systems, or infer absent facts.
- Do not treat cache, dream reports, or uncited recollection as canonical authority.

## Workflow

1. Run `python -m agent_brain --root /absolute/path/to/brain-root status`.
2. Run `python -m agent_brain --root /absolute/path/to/brain-root search "specific terms" --limit 10`; try one narrower synonym query when useful.
3. Run `python -m agent_brain --root /absolute/path/to/brain-root synthesize "the complete question" --limit 5`.
4. Inspect decisive results with `python -m agent_brain --root /absolute/path/to/brain-root entity "uuid-or-slug"`.
5. Answer only from supported evidence. State the queries used, evidence age, contradictions, and what remains unknown before requesting missing input.

## Verification

- Every factual memory claim has a returned citation, and the response names the local-only search scope.

## Failure behavior

- If status or retrieval fails, report the structured error and stop. If no evidence matches, say so and ask only for the missing fact needed next.

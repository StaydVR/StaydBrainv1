---
name: cited-answer
description: Answer from local Agent Brain evidence with exact citations while exposing freshness, contradictions, and missing context.
triggers: ["give me a cited answer", "show the memory evidence", "answer with brain citations"]
---

# Cited answer

## Prerequisites

- Know the absolute repository root and a bounded question.
- Treat only returned local evidence as support.

## Permitted operations

- Use `synthesize`, `search`, `entity`, and `citation-verify` read-only.
- Distinguish supported findings from interpretation.

## Denied operations

- Do not fabricate citations, conceal stale evidence, resolve contradictions silently, or fill gaps from model memory.
- Do not cite a dream proposal as an approved fact.

## Workflow

1. Run `python -m agent_brain --root /absolute/path/to/brain-root synthesize "bounded question" --limit 5`.
2. Run `python -m agent_brain --root /absolute/path/to/brain-root search "decisive evidence terms" --limit 10` when coverage is weak.
3. Inspect each decisive page with `python -m agent_brain --root /absolute/path/to/brain-root entity "uuid-or-slug"`.
4. Verify saved citation JSON with `python -m agent_brain --root /absolute/path/to/brain-root citation-verify '{"path":"brain/pages/synthetic.md","document_id":"00000000-0000-4000-8000-000000000000","slug":"synthetic","content_hash":"hex-digest","start_line":1,"end_line":1,"span_hash":"hex-digest"}'` before reusing it later.
5. Present the answer, evidence citations, stale evidence, contradictions, and gaps as separate fields.

## Verification

- Each material claim maps to a valid current citation, and all returned contradiction, stale-evidence, and gap fields are represented.

## Failure behavior

- If citations are stale or evidence is absent, withhold the affected claim and state what current source would be needed.

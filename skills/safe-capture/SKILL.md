---
name: safe-capture
description: Capture an explicitly requested memory as a scanned canonical page with provenance and a returned citation; never capture conversations by default.
triggers: ["remember this safely", "save this to the brain", "capture this memory"]
---

# Safe capture

## Prerequisites

- Have an explicit user request to remember specific content.
- Know the absolute repository root, title, page type, and non-sensitive provenance label.

## Permitted operations

- Search for an existing page, create one page through `remember`, then retrieve and cite it.
- Use synthetic or user-approved tags and page types.

## Denied operations

- Do not capture whole conversations, unstated inferences, personal data, credentials, or rejected material.
- Do not write files directly under `brain/` or retain raw quarantined content.

## Workflow

1. Run `python -m agent_brain --root /absolute/path/to/brain-root search "proposed title and key terms" --limit 10` to detect duplicates or conflicts.
2. Confirm the requested content is scoped and contains no unnecessary sensitive detail.
3. Run `python -m agent_brain --root /absolute/path/to/brain-root remember "Synthetic decision" "Approved local statement with source context." --type decision --tag approved`.
4. Use the returned slug with `python -m agent_brain --root /absolute/path/to/brain-root entity "returned-slug"`.
5. Return the page identity, path, source context, and citation; disclose any conflict found in step 1.

## Verification

- Verify the entity body matches the approved statement and the response includes its content-bound citation.

## Failure behavior

- On a scan rejection or collision, do not retry with weakened content or another path. Report only the structured reason and ask the user to revise or resolve the duplicate.

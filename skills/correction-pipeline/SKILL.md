---
name: correction-pipeline
description: Correct wrong Agent Brain knowledge by tracing its citation, preserving history, recording a superseding page, rebuilding derived state, and testing recall.
triggers: ["correct this memory", "the brain is wrong", "supersede an old claim"]
---

# Correction pipeline

## Prerequisites

- Have the user's explicit correction, the absolute repository root, and evidence identifying the wrong claim.
- Apply the data-loss gate before soft-forgetting an old page.

## Permitted operations

- Trace with `search` and `entity`, export a recovery archive, create a cited superseding page, soft-forget the wrong page, and rebuild the index.
- Preserve the old canonical page and link the correction with `[[supersedes:old-slug]]`.

## Denied operations

- Do not overwrite or erase the original claim, silently change UUID identity, or correct derived SQLite directly.
- Do not proceed when the corrected fact or target page is ambiguous.

## Workflow

1. Run `python -m agent_brain --root /absolute/path/to/brain-root search "wrong claim terms" --limit 10`, then `python -m agent_brain --root /absolute/path/to/brain-root entity "wrong-uuid-or-slug"`.
2. Verify the cited line and ask for clarification if multiple sources support different claims.
3. Run `python -m agent_brain --root /absolute/path/to/brain-root export /absolute/path/to/recovery/correction-backup.zip` and confirm the archive exists.
4. Run `python -m agent_brain --root /absolute/path/to/brain-root remember "Corrected synthetic claim" "[[supersedes:old-slug]]\n\nCorrection approved by user with local provenance." --type correction --tag corrected`.
5. After explicit confirmation of the target, run `python -m agent_brain --root /absolute/path/to/brain-root forget "wrong-uuid-or-slug"`, then `python -m agent_brain --root /absolute/path/to/brain-root rebuild`.
6. Re-run the original query with `python -m agent_brain --root /absolute/path/to/brain-root search "wrong claim terms" --limit 10` and inspect the correction with `python -m agent_brain --root /absolute/path/to/brain-root entity "corrected-slug"`.

## Verification

- Confirm the old page is canonically retained but absent from recall, the correction is cited and linked, the backup is retained, and doctor passes.

## Failure behavior

- If trace, backup, capture, forget, or rebuild fails, stop at that boundary. Do not repeat the mutation or remove the recovery archive.

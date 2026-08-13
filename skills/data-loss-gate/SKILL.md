---
name: data-loss-gate
description: Gate forget, cleanup, source removal, and destructive migration behind exact scope, explicit confirmation, and a tested recoverable local archive.
triggers: ["forget this memory safely", "approve destructive cleanup", "protect against data loss"]
---

# Data-loss gate

## Prerequisites

- Identify exact UUIDs, slugs, paths, and intended effect; obtain explicit user confirmation for that resolved scope.
- Choose a new absolute archive destination outside the target brain.

## Permitted operations

- Inspect targets, export canonical memory, test the archive in a separate empty local brain, and soft-forget confirmed pages.
- Stop after preflight without mutation.

## Denied operations

- Do not use globs, recursive deletion, direct SQLite changes, unconfirmed targets, or an untested backup.
- Do not claim `forget` erases bytes; it retains canonical content with forgotten status.
- The current CLI has no source-removal or bulk-cleanup verb; stop instead of editing the source registry or managed files directly.

## Workflow

1. Resolve every target with `python -m agent_brain --root /absolute/path/to/brain-root entity "uuid-or-slug"` and present the exact list and effect.
2. Receive explicit confirmation matching that list.
3. Run `python -m agent_brain --root /absolute/path/to/brain-root export /absolute/path/to/recovery/pre-change.zip`.
4. Initialize an empty verification root with `python -m agent_brain --root /absolute/path/to/restore-check init`, then run `python -m agent_brain --root /absolute/path/to/restore-check import /absolute/path/to/recovery/pre-change.zip` and `python -m agent_brain --root /absolute/path/to/restore-check verify`.
5. For each confirmed page only, run `python -m agent_brain --root /absolute/path/to/brain-root forget "confirmed-uuid-or-slug"`.
6. Run `python -m agent_brain --root /absolute/path/to/brain-root verify` and retain the archive until the user accepts the result.

## Verification

- Confirm scope, confirmation, archive path, successful isolated import, target results, and final health are all recorded without raw sensitive content.

## Failure behavior

- If any prerequisite or backup test fails, perform no destructive operation. If a mutation partially completes, stop, preserve both roots and the archive, and report exact completed targets.

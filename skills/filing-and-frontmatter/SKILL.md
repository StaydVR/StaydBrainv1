---
name: filing-and-frontmatter
description: File Agent Brain knowledge with valid canonical metadata, stable identity, provenance, page placement, and append-only timeline behavior.
triggers: ["file this memory correctly", "fix brain frontmatter", "choose a memory page type"]
---

# Filing and frontmatter

## Prerequisites

- Know the absolute repository root, content purpose, provenance, and whether a canonical page already exists.
- Use the native capture path for new pages.

## Permitted operations

- Search existing identities and create a page through `remember`.
- Inspect the generated metadata and timeline through `entity` and `sync`.

## Denied operations

- Do not hand-assign UUIDs for normal capture, reuse a slug, mutate `created`, or rewrite timeline history.
- Do not add unsupported frontmatter keys or place ordinary pages in reports, sources, or control storage.

## Workflow

1. Run `python -m agent_brain --root /absolute/path/to/brain-root search "title and identity terms" --limit 10`.
2. Select a concise type such as `note`, `decision`, `project`, or `procedure`; record provenance in the body because CLI capture assigns source `capture`.
3. Run `python -m agent_brain --root /absolute/path/to/brain-root remember "Synthetic procedure" "Provenance: approved local source.\n\nCanonical content." --type procedure --tag operations`.
4. Inspect the returned slug with `python -m agent_brain --root /absolute/path/to/brain-root entity "returned-slug"`.
5. Run `python -m agent_brain --root /absolute/path/to/brain-root sync` and confirm the generated page remains under `brain/pages/`; leave the dated timeline entry append-only.

## Verification

- Confirm required metadata exists (`id`, `slug`, `title`, `type`, `created`, `updated`), identity is unique, provenance is explicit, and sync succeeds.

## Failure behavior

- On invalid metadata, collision, or sync failure, stop and preserve the original page. Use a new explicit correction workflow instead of rewriting identity or history.

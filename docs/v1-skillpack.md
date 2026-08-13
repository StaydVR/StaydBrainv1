# Version 1 skillpack scope

Agent Brain v1 should ship a small, independently written set of agent playbooks. These are procedural instructions layered over the stable CLI/API; they are not copied from any inspected project.

## Include in v1

1. **brain-first** — Search existing memory before asking the user or calling external systems; report what was searched and what remains unknown.
2. **safe-capture** — Turn an explicit user request to remember something into a cited canonical page through the security gate; never silently capture every conversation.
3. **cited-answer** — Retrieve, synthesize, cite exact evidence, expose freshness, contradictions, and gaps, and never invent missing context.
4. **filing-and-frontmatter** — Choose a valid page kind/path, enforce canonical metadata, stable identity, provenance, and append-only timeline rules.
5. **ingest-gate** — Treat imported content as untrusted data, reject raw file copies into managed memory, require source/provenance, scan before persistence, and quarantine safely.
6. **dream-review** — Run and interpret the dream cycle; keep ordinary memory unchanged unless a human approves a review proposal.
7. **correction-pipeline** — When a user corrects the brain, trace the wrong claim to its source, preserve history, supersede it, rebuild derived state, and test recall.
8. **data-loss-gate** — Require explicit confirmation and a recoverable backup before forget, bulk cleanup, source removal, or destructive migration.
9. **brain-health** — Run doctor, audit verification, index/canonical consistency, citation freshness, quarantine counts, broken links, and recovery checks.
10. **migration** — Safely import a generic Markdown/Obsidian-style vault through dry-run, privacy scan, schema mapping, collision reporting, and reversible commit batches.

## Optional in v1 if the core gates remain green

11. **daily-brief** — Produce a local read-only brief from approved memory only, with citations and an explicit stale/missing-context section.
12. **conversation-archive** — Import user-provided AI chat exports as scoped source material; opt-in only, no automatic transcript harvesting.

## Explicitly defer

- Always-on signal detection or automatic capture of every message.
- Email, calendar, meeting, social, voice, webhook, or cloud connectors.
- Person/company enrichment from the internet.
- Publishing or internet-facing brain pages.
- Skill self-modification/optimization.
- Autonomous background agents and job orchestration.
- Identity/personality generation.
- Company-brain extraction or multi-user access.

## Packaging contract

- Store playbooks under `skills/<name>/SKILL.md` with a compact `skills/manifest.json` and `skills/RESOLVER.md`.
- Every skill states triggers, prerequisites, permitted operations, denied operations, steps, verification, and failure behavior.
- Skills call only stable Agent Brain v1 commands/API verbs.
- No skill may bypass security scanning, quarantine, source boundaries, citations, capability checks, or approval gates.
- Skills contain synthetic examples only and must pass privacy/secret scans.

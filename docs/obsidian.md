# Obsidian interface

Obsidian is an optional human interface, not an Agent Brain runtime dependency. Open the repository root as the vault so `AGENT-BRAIN.md`, canonical memory, project docs, and the skillpack are visible together. Do not open only `brain/` as the vault.

Run `agent-brain obsidian` (or `agent-brain vault-status`) for the resolved vault, canonical-memory, and private-runtime locations. The command reports status and safe instructions; it never launches a GUI.

## Storage boundaries

- `brain/` is canonical, reviewable Markdown. Pages, tracked sources, timeline entries, and dream reports may be committed according to the repository's normal review process.
- `.agent-brain/` is private, derived runtime state. It includes SQLite, source registry state, caches, quarantine metadata, audit state, and backups. It is gitignored and must not be synced or published.
- `.obsidian/app.json` is the only portable Obsidian setting intended for Git. It directs new notes to `brain/pages`, keeps wiki links, and disables automatic link rewrites.
- Workspace files, device state, hotkeys, appearance state, community-plugin configuration, and plugin data under `.obsidian/` stay ignored. Agent Brain does not require plugins.
- `AGENT-BRAIN.md` is a generated-once vault home. Initialization creates it only when absent and never replaces edits.

Keep this vault separate from any existing personal vault. Do not nest one vault inside another, symlink vault content into the repository, or configure a personal vault's sync service to include this repository.

## Git workflow and conflicts

Before editing, update the branch using the team's normal non-destructive Git workflow. Make focused Markdown changes, run `agent-brain sync`, review the diff, then run `agent-brain doctor`. Commit canonical Markdown and intentional documentation changes; do not force-add ignored runtime or Obsidian state.

If two branches change the same note, Git conflict markers make that note invalid canonical input and `sync` fails closed. Resolve the content and frontmatter manually, preserve one stable `id` and unique `slug`, review relationship targets, then run `sync` and `doctor` again. Never resolve a conflict by copying SQLite or `.agent-brain/` state; rebuild the disposable index after canonical files are correct.

## Moving notes from another vault

Do not copy another vault directly into `brain/`. Use the existing `migration` and `ingest-gate` skillpack procedures:

1. Keep the source vault unchanged and create a separate staging copy containing only the approved notes.
2. Remove Obsidian configuration, attachments, unsupported files, sensitive content, and unnecessary metadata from the staging scope.
3. Map each note to Agent Brain's strict frontmatter and convert relationships deliberately. Use vault-relative links such as `[[brain/pages/example|Example]]`; report unresolved targets.
4. Allowlist only the resolved staging directory in a separate preflight brain, register it as a source, and ingest named files through `source-add` and `ingest`.
5. Run a dry dream cycle and `doctor`, review rejections and collisions, export a recovery archive, then ingest approved batches into the target through the same gate.

The gate scans complete candidate bytes before persistence. Rejected source content stays outside managed memory; quarantine stores only its digest and reason codes.

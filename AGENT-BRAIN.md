# Agent Brain

This repository root is the Obsidian vault. Agent Brain works without Obsidian; this page is only a human-facing map of the local files.

## Canonical memory

- [Memory pages](brain/pages/)
- [Imported canonical sources](brain/sources/)
- [Timeline](brain/timeline/)
- [Dream reports](brain/reports/)

Markdown under `brain/` is canonical, human-readable knowledge. Edit it deliberately, review Git diffs, then run `agent-brain sync`. Dream reports are review artifacts and do not silently change ordinary memories.

## Project guides

- [[README|Project overview]]
- [[docs/architecture|Architecture]]
- [[docs/obsidian|Obsidian workflow]]
- [[docs/dream-cycle|Dream cycle]]
- [[skills/RESOLVER|Skillpack resolver]]
- [Skillpack files](skills/)

## Canonical versus derived storage

`brain/` is the system of record. `.agent-brain/` is private, gitignored runtime storage containing the disposable SQLite index, caches, quarantine metadata, audit state, and backups. Do not sync or publish `.agent-brain/`; rebuild its index from canonical Markdown when needed.

Obsidian workspace state, community plugins, and device-specific settings are intentionally not part of this vault's tracked configuration. See [[docs/obsidian|the safe workflow]] before moving notes from another vault.

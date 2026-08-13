# Architecture

`brain/` is the knowledge system of record. Each Markdown document has a UUID `id` and readable unique `slug`. User pages use UUIDv4; deterministic system documents use namespaced UUIDv5. Filenames and links remain slug-readable, while SQLite relationships and citations bind UUID identity.

Tracked imports live under `brain/sources/`. Cache-tier imports live under ignored `.agent-brain/cache/`. Dream reports live under `brain/reports/` as review artifacts; they are never treated as authority for silently changing ordinary memories.

`.agent-brain/index.sqlite3` is a disposable index containing pages, FTS5 search, typed links, structured facts, run history, a mirror of audit events, and source checkpoints. The authoritative audit chain is `.agent-brain/audit.jsonl`, anchored by `.agent-brain/state/audit-head.json`. The separate head makes tail truncation detectable. Rebuild restores the database mirror from that verified chain.

The write path is:

1. Validate the repository and resolved path; reject traversal and every symlink in the managed chain.
2. Apply byte and archive bounds, scan the complete candidate bytes, and parse strict frontmatter where required.
3. Write to a same-directory temporary file, fsync it, atomically replace the target, and fsync the parent directory.
4. Update the disposable index in an immediate transaction using parameterized SQL.
5. Append a content-hash-only audit event, fsync it, and atomically advance its head anchor.

Facts use `- fact: subject | predicate | object`. New links use an Obsidian-resolvable vault path: `[[brain/pages/example|Example]]`. A plain link means `related`; a typed relationship places independently parseable metadata immediately after it: `[[brain/pages/example|Example]] <!-- agent-brain:relationship=depends-on -->`. The index resolves the path to the canonical page slug and stores the relationship separately. Legacy `[[depends-on:example]]` links remain readable by the index but are never silently rewritten. Search inputs never enter FTS query syntax directly.

Citation objects contain `path`, `document_id`, `slug`, `content_hash`, `start_line`, `end_line`, and `span_hash`. Line numbers are relative to the Markdown body, excluding frontmatter. A citation is stale if its path disappears or any bound identity/content/span value changes.

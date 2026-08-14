# Architecture

`brain/` is the knowledge system of record. Each Markdown document has a UUID `id` and readable unique `slug`. User pages use UUIDv4; deterministic system documents use namespaced UUIDv5. Filenames and links remain slug-readable, while SQLite relationships and citations bind UUID identity.

Tracked imports live under `brain/sources/`. Cache-tier imports live under ignored `.agent-brain/cache/`. Dream reports live under `brain/reports/` as review artifacts; they are never treated as authority for silently changing ordinary memories.

`.agent-brain/index.sqlite3` is a disposable index containing pages, heading-aware paragraph chunks, page and chunk FTS5 search, a bounded typo vocabulary, typed links, structured facts, run history, a mirror of audit events, and source checkpoints. Chunk FTS uses the Porter wrapper over the Unicode61 tokenizer. Existing indexes gain the derived chunk schema during a normal initialized connection; the first retrieval automatically populates an empty upgraded chunk index from canonical Markdown. An explicit sync or rebuild produces the same state. None of these paths mutates canonical Markdown. The authoritative audit chain is `.agent-brain/audit.jsonl`, anchored by `.agent-brain/state/audit-head.json`. The separate head makes tail truncation detectable. Rebuild restores the database mirror from that verified chain.

The write path is:

1. Validate the repository and resolved path; reject traversal and every symlink in the managed chain.
2. Apply byte and archive bounds, scan the complete candidate bytes, and parse strict frontmatter where required.
3. Write to a same-directory temporary file, fsync it, atomically replace the target, and fsync the parent directory.
4. Update the disposable index in an immediate transaction using parameterized SQL.
5. Append a content-hash-only audit event, fsync it, and atomically advance its head anchor.

Facts use `- fact: subject | predicate | object`. New links use an Obsidian-resolvable vault path: `[[brain/pages/example|Example]]`. A plain link means `related`; a typed relationship places independently parseable metadata immediately after it: `[[brain/pages/example|Example]] <!-- agent-brain:relationship=depends-on -->`. The index resolves the path to the canonical page slug and stores the relationship separately. Legacy `[[depends-on:example]]` links remain readable by the index but are never silently rewritten. Search inputs never enter FTS query syntax directly.

Retrieval sanitizes and bounds Unicode terms, conservatively removes stopwords, and constructs only quoted phrase, quoted all-term, or quoted any-term FTS expressions. Missing sufficiently long terms may be corrected using bounded edit distance over the derived local vocabulary under global candidate, comparison, and edit-cell budgets. Heading-aware chunks are capped at 8,192 characters. Ranking combines fixed reciprocal stage ranks, a higher-is-better normalized BM25 magnitude, term coverage, exact phrase detection, and title, heading, and slug boosts. Candidate coverage is computed only for bounded candidate IDs. Per-page diversity is applied inside every retrieval stage before its global window, then a two-chunk final cap prevents giant documents from crowding out alternative pages. Ties resolve by stable page identity and body line. Candidate rows omit full page bodies; body loading for final citations has a separate total-byte budget.

Body citation objects contain `path`, `document_id`, `slug`, `content_hash`, `start_line`, `end_line`, and `span_hash`. Chunk ranges and citation line numbers are relative to the Markdown body, excluding frontmatter. Returned citations use token boundaries to narrow a chunk to a matching line when literal matches identify one; otherwise they cover the full chunk. Metadata-only title or slug results instead contain `field` and `value_hash`, preserving v0.1 metadata retrieval without citing unrelated body text. A citation is stale if its path disappears or any bound identity, content, span, field, or value changes.

`synthesize` and `context-pack` are deterministic extractive evidence operations. They expose query analysis, per-source and aggregate coverage, confidence, contradictions, stale evidence, and explicit partial/no-match gaps. A full match requires one cited body, heading, title, or slug field to cover every effective term; disjoint chunks or fields cannot manufacture full confidence. They do not perform or claim semantic or LLM synthesis.

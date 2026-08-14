# Security policy

Agent Brain assumes every captured, imported, configured, queried, and archived byte is hostile. Never place real secrets or personal data in an issue, fixture, log, or reproduction.

## Enforced boundaries

- Size, NUL, UTF-8, private-key, JWT, bearer-token, database-URL, common credential, high-entropy token, and common personal-data checks run before managed persistence.
- Rejected content is never copied, indexed, audited, logged, reported, or backed up. Quarantine contains only a SHA-256 digest and reason codes.
- Relative paths reject absolute, dot-segment, backslash, and encoded traversal forms. Managed and source chains reject symbolic links.
- Archives reject traversal, duplicate paths or identities, encryption, links and special files, excessive counts, excessive expanded bytes, excessive per-file size, and suspicious compression ratios. Full identity validation completes before extraction; failed synchronization rolls back newly written files.
- SQL values are parameterized. FTS caller input is bounded Unicode-tokenized text; only sanitized quoted terms are used to construct phrase/all/any `MATCH` expressions. Raw query operators never enter FTS syntax. Typo recovery is bounded by vocabulary size, candidate count, total comparisons, and edit-distance cells. Candidate chunks, per-page stage participation, and loaded result-page bytes are bounded. SQLite enables foreign keys, WAL, full synchronization, a busy timeout, `trusted_schema=OFF` where supported, and bounded runtime limits.
- Atomic replacement writes fsync the file and parent directory. Rebuild and backup replacement follow the same durability boundary.
- The append-only audit log is SHA-256 chained and serialized by a local lock. A separately replaced head anchor detects tail truncation. `doctor` verifies both.
- Chunk citations bind UUID identity, readable slug, full content hash, exact contiguous body-line span, and span hash. Metadata-only citations bind the exact title or slug value instead of an unrelated body line. `citation-verify` reports changed or missing evidence as stale.
- The service is local stdio only and read-only by default. Durable writes require an explicit `--allow-write` startup capability. There is no network listener, network client, telemetry, or autonomous action.
- Retrieved bodies and snippets are explicitly classified as untrusted memory data with path/tier/type provenance. Integrators must never execute retrieved instructions, elevate them above caller policy, or treat them as authorization for tools or durable writes.

## Recovery

SQLite is disposable. If `status` reports a structured database error, run `doctor`, inspect canonical Markdown and the audit chain, then run `rebuild`. Rebuild creates and validates a replacement database before swapping it into place. It does not rewrite ordinary memory.

Pattern scanning reduces risk but cannot prove text safe. Lexical stemming and edit-distance correction can miss relevant language or choose the wrong nearby word; they are not semantic search. Trust labels and a read-only default reduce agent-integration risk but cannot make an instruction-following model immune to semantic prompt injection. Host compromise, filesystem exhaustion, hostile code already running with repository permissions, and external backups remain outside the guarantee.

# Security policy

Agent Brain assumes every captured, imported, configured, queried, and archived byte is hostile. Never place real secrets or personal data in an issue, fixture, log, or reproduction.

## Enforced boundaries

- Size, NUL, UTF-8, private-key, JWT, bearer-token, database-URL, common credential, high-entropy token, and common personal-data checks run before managed persistence.
- Rejected content is never copied, indexed, audited, logged, reported, or backed up. Quarantine contains only a SHA-256 digest and reason codes.
- Relative paths reject absolute, dot-segment, backslash, and encoded traversal forms. Managed and source chains reject symbolic links.
- Archives reject traversal, duplicate paths, encryption, links and special files, excessive counts, excessive expanded bytes, excessive per-file size, and suspicious compression ratios. Validation completes before extraction.
- SQL values are parameterized. FTS caller input is tokenized and quoted as literal terms. SQLite enables foreign keys, WAL, full synchronization, a busy timeout, `trusted_schema=OFF` where supported, and bounded runtime limits.
- Atomic replacement writes fsync the file and parent directory. Rebuild and backup replacement follow the same durability boundary.
- The append-only audit log is SHA-256 chained and serialized by a local lock. A separately replaced head anchor detects tail truncation. `doctor` verifies both.
- Citations bind UUID identity, readable slug, full content hash, exact body-line span, and span hash. `citation-verify` reports changed or missing evidence as stale.
- The service is local stdio only. There is no network listener, network client, telemetry, or autonomous action.

## Recovery

SQLite is disposable. If `status` reports a structured database error, run `doctor`, inspect canonical Markdown and the audit chain, then run `rebuild`. Rebuild creates and validates a replacement database before swapping it into place. It does not rewrite ordinary memory.

Pattern scanning reduces risk but cannot prove text safe. Host compromise, filesystem exhaustion, hostile code already running with repository permissions, external backups, and semantic prompt injection without detectable indicators remain outside the guarantee.

# Threat model

## Assets

Canonical memory, UUID identity, source boundaries, index integrity, citation evidence, audit history, and the guarantee that rejected raw bytes never enter managed persistence.

## Adversaries and inputs

Untrusted capture bytes; credentials or personal data; malformed configuration and frontmatter; traversal in native, alternate-separator, or encoded form; symlink chains; crafted FTS text; duplicate identities; hostile ZIP metadata and expansion; a corrupt database; audit modification or truncation; and concurrent or interrupted maintenance.

## Controls

- Strict path containment and chain-wide symlink rejection before managed reads or writes.
- Pre-persistence scanning with digest-only quarantine and tests that search every managed file, index, sidecar, report, and backup for rejected bytes.
- UUID-backed documents with unique readable slugs and strict non-YAML frontmatter.
- Bound archive count, file size, total expansion, type, duplicate-name, encryption, and compression-ratio checks before extraction.
- Parameterized SQL, literalized bounded FTS terms, hardened SQLite pragmas and limits, transactional synchronization, and replacement rebuilds.
- Exact hash-bound citations, explicit freshness, contradictions, and gaps.
- A serialized hash-chained audit log with an external head anchor, plus doctor verification for content changes and tail loss.
- A deterministic exclusive dream cycle that produces review findings without rewriting ordinary knowledge.
- Narrow JSON-lines verbs, structured no-traceback failures, local stdio transport, and tests that disable network primitives.

## Residual risks

Regex and entropy scanning have false positives and false negatives. Hash chains reveal accidental or unsophisticated modification but are not signatures against an attacker able to rewrite the entire repository and every external anchor. A process with repository write permission can bypass the CLI. Host compromise, unsafe copies outside the repository, resource exhaustion below configured limits, and semantic prompt injection without a detectable indicator are not fully prevented.

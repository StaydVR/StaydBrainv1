# Clean-room provenance

Agent Brain is an independent implementation. No upstream source code was copied, translated, or adapted.

The implementation was designed from public problem concepts, the repository's own product invariants, and independent review requirements. Concepts inspected at the requirements level included:

- Markdown-as-canonical memory with a rebuildable search index
- stable document identity paired with human-readable names
- pre-persistence secret and personal-data gates
- path containment, symlink rejection, and hostile archive handling
- durable atomic replacement and crash recovery
- full-text search treated as an injection boundary
- tamper-evident append-only audit records
- evidence citations bound to identity, content, and spans
- deterministic maintenance with reviewable findings
- local-only operation and narrow agent-facing commands

All architecture, schemas, algorithms, code, tests, documentation, examples, and command behavior in this repository were authored specifically for Agent Brain. Similarity at the level of standard security controls, file formats, SQL facilities, or general software concepts reflects interoperability and common engineering practice, not source copying.

Future contributions must preserve this clean-room rule: inspect behavior and concepts only when external compatibility research is necessary, record what was inspected, and do not copy source code or nontrivial implementation text.

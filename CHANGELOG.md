# Changelog

## 0.2.0 — 2026-08-13

- Added deterministic heading-aware paragraph chunks with exact body-relative ranges and rebuildable SQLite chunk/FTS tables.
- Added sanitized staged phrase, all-term, and any-term retrieval with Porter stemming and Unicode tokenization.
- Added explainable higher-is-better ranking, page diversity, bounded local typo recovery, and query analysis.
- Added precise heading/body chunk evidence, per-chunk and aggregate coverage/confidence metadata, partial/no-match gaps, and bounded deterministic evidence packs.
- Added automatic first-recall population for upgraded v0.1 derived indexes; no manual migration command is required.
- Preserved empty-body title/slug retrieval with separately verifiable metadata citations; body citations now use token boundaries.
- Bounded chunk size, loaded page bytes, typo-comparison work, and per-page stage participation to prevent broad-query resource amplification.
- Fixed candidate coverage beyond 1,000 chunks, pre-window page diversity, and BM25 score orientation.
- Added schema upgrade coverage and a synthetic Recall@1, Recall@3, and MRR release benchmark to `make verify`.
- Made the JSONL server read-only by default; durable writes require `--allow-write`.
- Added untrusted-evidence classification and source provenance to agent-facing retrieval.
- Excluded timelines, dream reports, and cache-tier imports from normal recall.
- Made archive imports preflight duplicate identities and roll back files on synchronization failure.
- Expanded release-content privacy scanning for local paths, credentials, contact data, and common token formats.

This release remains local-only and dependency-free at runtime. It does not add embeddings, vector search, semantic retrieval, or LLM synthesis.

## 0.1.0

- Initial security-first local Markdown memory, disposable SQLite index, citations, dream cycle, CLI, stdio server, and skillpack.

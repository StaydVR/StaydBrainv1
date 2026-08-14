from __future__ import annotations

"""Synthetic deterministic retrieval benchmark.

Release thresholds: Recall@1 >= 0.80, Recall@3 >= 0.95, and MRR >= 0.85.
"""

import json
import tempfile
import uuid
from pathlib import Path

from agent_brain import Brain
from agent_brain.markdown import render


RECALL_AT_1_MIN = 0.80
RECALL_AT_3_MIN = 0.95
MRR_MIN = 0.85
NAMESPACE = uuid.UUID("03126343-cf71-45c5-9a1f-50a44b749f3f")
FIXTURES = {
    "rollout-runbook": ("Staged Rollout Runbook", "# Release Verification\n\nStaged deployments require a verification checkpoint before launch.\n"),
    "index-recovery": ("SQLite Index Recovery", "# Restore Procedure\n\nRebuild the disposable local SQLite index from canonical Markdown.\n"),
    "archive-defense": ("Archive Defense", "# Import Validation\n\nReject archive traversal, symbolic links, duplicate paths, and excessive expansion.\n"),
    "context-packing": ("Bounded Context Packing", "# Byte Budget\n\nPackage cited evidence within a deterministic context byte budget.\n"),
    "fact-review": ("Contradictory Fact Review", "# Conflicts\n\nSurface contradictory structured facts for explicit human review.\n"),
    "dream-cycle": ("Deterministic Dream Cycle", "# Maintenance\n\nNightly maintenance is idempotent, auditable, and review first.\n"),
    "retrieval-design": ("Unicode Retrieval", "# Porter Stemming\n\nFull text search uses Unicode tokenization and Porter stemming without embeddings.\n"),
    "citation-proof": ("Exact Citation Proof", "# Line Spans\n\nEvidence citations hash an exact contiguous body relative line span.\n"),
}
QUERIES = (
    ("What is the staged rollout verification checkpoint?", "rollout-runbook"),
    ("verification checkpoints for deployments", "rollout-runbook"),
    ("relesae verificatoin", "rollout-runbook"),
    ("rebuild disposable sqlite index", "index-recovery"),
    ("restore the local index from markdown", "index-recovery"),
    ("archive traversal validation", "archive-defense"),
    ("bounded context evidence byte budget", "context-packing"),
    ("contradictory facts human review", "fact-review"),
    ("nightly deterministic maintenance", "dream-cycle"),
    ("porter stemming unicode search", "retrieval-design"),
    ("exact evidence citation line spans", "citation-proof"),
)


def _write_fixtures(root: Path) -> Brain:
    brain = Brain.init(root)
    stamp = "2030-01-01T00:00:00Z"
    for slug, (title, body) in FIXTURES.items():
        document = render({
            "id": str(uuid.uuid5(NAMESPACE, slug)), "slug": slug, "title": title, "type": "note",
            "created": stamp, "updated": stamp, "source": "synthetic-benchmark", "status": "active",
        }, body)
        (root / "brain/pages" / f"{slug}.md").write_text(document, encoding="utf-8")
    brain.sync()
    return brain


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent-brain-benchmark-") as temporary:
        brain = _write_fixtures(Path(temporary).resolve())
        reciprocal_ranks: list[float] = []
        hits_at_1 = 0
        hits_at_3 = 0
        details = []
        for query, expected in QUERIES:
            slugs = [row["slug"] for row in brain.search(query, 3)]
            rank = slugs.index(expected) + 1 if expected in slugs else None
            hits_at_1 += int(rank == 1)
            hits_at_3 += int(rank is not None and rank <= 3)
            reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
            details.append({"query": query, "expected": expected, "rank": rank})
    total = len(QUERIES)
    metrics = {
        "recall_at_1": round(hits_at_1 / total, 6),
        "recall_at_3": round(hits_at_3 / total, 6),
        "mrr": round(sum(reciprocal_ranks) / total, 6),
    }
    passed = (metrics["recall_at_1"] >= RECALL_AT_1_MIN
              and metrics["recall_at_3"] >= RECALL_AT_3_MIN and metrics["mrr"] >= MRR_MIN)
    print(json.dumps({"fixtures": len(FIXTURES), "queries": total, "metrics": metrics,
                      "thresholds": {"recall_at_1": RECALL_AT_1_MIN, "recall_at_3": RECALL_AT_3_MIN, "mrr": MRR_MIN},
                      "passed": passed, "details": details}, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

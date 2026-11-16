"""Local adapter pipeline. No scheduler daemon, network, or model calls."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, date, timedelta, UTC
from typing import Protocol
from zoneinfo import ZoneInfo

from .brain import Brain, REPORT_NAMESPACE
from .config import Config
from .dream import DreamLock, run_dream, _analyze
from .errors import ValidationError
from .markdown import render, parse, LINK_RE
from .util import atomic_write, reject_symlink_chain, safe_relative, sha256


@dataclass(frozen=True)
class Meeting:
    key: str
    title: str
    summary: str
    decisions: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerifiedFact:
    """Adapter attests old text is stale using a pinned canonical file digest."""
    slug: str
    expected_sha256: str
    old: str
    new: str
    evidence: str


@dataclass(frozen=True)
class Snapshot:
    journal: str = ""
    meetings: tuple[Meeting, ...] = ()
    current_work: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    verified_facts: tuple[VerifiedFact, ...] = ()


class SourceAdapter(Protocol):
    def collect(self, day: date) -> Snapshot: ...


class FakeOpsAdapter:
    def collect(self, day: date) -> Snapshot:
        return Snapshot(
            journal="Synthetic Harbor Cottage inspection completed.",
            meetings=(Meeting("inspection", "Synthetic operations review", "Reviewed fake inspection checklist.",
                              ("Replace the mock filter.",), ("Demo operator to check the mock stockroom.",)),),
            current_work=("Harbor Cottage: mock filter replacement pending.",),
            decisions=("Use the synthetic inspection checklist.",))


def next_run(config: Config, now: datetime) -> datetime:
    """Next configured local wall-clock occurrence, returned in UTC.

    Ambiguous times use fold=0; nonexistent times advance through the DST gap.
    Hosts call this again after every run rather than adding 24 hours.
    """
    if now.tzinfo is None:
        raise ValidationError("scheduler requires an aware timestamp")
    zone = ZoneInfo(config.nightly_timezone)
    hour, minute = map(int, config.nightly_time.split(":"))
    local = now.astimezone(zone)
    for offset in range(3):
        candidate = datetime.combine(local.date() + timedelta(days=offset),
                                     datetime.min.time(), zone).replace(hour=hour, minute=minute)
        candidate = candidate.astimezone(UTC)
        if candidate > now:
            return candidate
    raise ValidationError("cannot resolve schedule")


def _write(brain: Brain, relative: str, title: str, body: str, day: date,
           *, status: str = "active", kind: str = "ops-sync") -> tuple:
    path = brain.brain_dir / safe_relative(relative)
    reject_symlink_chain(path, brain.brain_dir)
    stamp = day.isoformat() + "T00:00:00Z"
    meta = {"id": str(uuid.uuid5(REPORT_NAMESPACE, "nightly:" + relative)),
            "slug": "ops-" + Brain.slug(relative), "title": title, "type": kind,
            "created": stamp, "updated": stamp, "source": "ops-adapter", "status": status}
    if path.exists():
        existing = parse(path.read_text(encoding="utf-8"))
        if existing.meta["id"] != meta["id"]:
            raise ValidationError("nightly output collides with unmanaged page")
        meta["created"] = existing.meta["created"]
    data = render(meta, body.rstrip() + "\n").encode()
    brain._scan(data)
    return path, data


def _commit(brain: Brain, staged: list[tuple]) -> None:
    # Validate the entire batch before any canonical mutation, including source output.
    for path, data in staged:
        reject_symlink_chain(path, brain.brain_dir)
        brain._scan(data)
    for path, data in staged:
        if not path.exists() or path.read_bytes() != data:
            atomic_write(path, data)
            brain._audit("nightly-write", sha256(data), {"path": str(path.relative_to(brain.brain_dir))})
    brain.sync()


def nightly_sync(brain: Brain, adapters: tuple[SourceAdapter, ...], day: date) -> tuple[VerifiedFact, ...]:
    brain._require()
    snapshots = [adapter.collect(day) for adapter in adapters]
    if not all(isinstance(s, Snapshot) for s in snapshots):
        raise ValidationError("adapter must return Snapshot")
    staged = [_write(brain, f"Journal/{day.isoformat()}.md", f"Journal {day}",
                     "\n\n".join(s.journal for s in snapshots), day)]
    seen = set()
    for index, snapshot in enumerate(snapshots):
        for meeting in snapshot.meetings:
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", meeting.key):
                raise ValidationError("unsafe meeting key")
            key = (index, meeting.key)
            if key in seen:
                raise ValidationError("duplicate meeting key")
            seen.add(key)
            body = meeting.summary + "\n\n## Decisions\n" + "\n".join("- " + x for x in meeting.decisions)
            body += "\n\n## Action items\n" + "\n".join("- " + x for x in meeting.actions)
            staged.append(_write(brain, f"Meetings/{day:%Y/%m}/{day}-{index}-{meeting.key}.md", meeting.title, body, day))
    for filename, field in (("Current Work", "current_work"), ("Decision History", "decisions")):
        # Dated append-only sections preserve prior decisions and work history.
        relative = f"pages/{filename}.md"
        path = brain.brain_dir / relative
        reject_symlink_chain(path, brain.brain_dir)
        previous = ""
        if path.exists():
            from .markdown import parse
            previous = re.split(r"(?:^|\n)## " + re.escape(str(day)) + r"\n", parse(path.read_text()).body, maxsplit=1)[0].rstrip()
        body = previous + f"\n## {day}\n" + "\n".join("- " + x for s in snapshots for x in getattr(s, field))
        staged.append(_write(brain, relative, filename, body, day))
    fresh_paths = {p for p, _ in staged}
    cutoff = datetime.combine(day, datetime.min.time(), UTC) - timedelta(days=brain.config().stale_after_days)
    for path, tier, doc, _ in brain._parsed_documents():
        if path not in fresh_paths and tier == "tracked" and doc.meta.get("status") == "active" and doc.meta["type"] != "dream-report":
            if datetime.fromisoformat(str(doc.meta["updated"]).replace("Z", "+00:00")) < cutoff:
                meta = dict(doc.meta, status="pending_review")
                staged.append((path, render(meta, doc.body).encode()))
    _commit(brain, staged)
    return tuple(f for s in snapshots for f in s.verified_facts)


SENSITIVE = re.compile(r"\b(person|people|contact|operator|owner|employee|guest|money|price|cost|payment|salary|budget|invoice|revenue|financial|bank|legal|contract|tax|taxes|law|liability)\b|[$€£]", re.I)


def repair_easy(brain: Brain, verified: tuple[VerifiedFact, ...], day: date) -> dict:
    documents = [(p, d, h) for p, tier, d, h in brain._parsed_documents()
                 if tier == "tracked" and d.meta["type"] not in {"dream-report", "ops-sync"}]
    slugs = {str(d.meta["slug"]): (p, d, h) for p, d, h in documents}
    changed, review, staged = [], [], []
    bodies = {}
    for path, doc, digest in documents:
        slug = str(doc.meta["slug"])
        text = render(doc.meta, doc.body)
        if SENSITIVE.search(text):
            review.append({"slug": slug, "reason": "sensitive-domain"})
            continue
        body = doc.body
        # Only repair an unresolved link when its casefolded title uniquely identifies a page.
        def fix_link(match):
            target = match.group("destination")
            if target in slugs:
                return match.group(0)
            candidates = [s for s, (_, d, _) in slugs.items() if Brain.slug(str(d.meta["title"])) == target
                          and not SENSITIVE.search(render(d.meta, d.body))]
            if len(candidates) == 1:
                return match.group(0).replace("[[" + target, "[[" + candidates[0], 1)
            return match.group(0)
        body = LINK_RE.sub(fix_link, body)
        for fact in verified:
            if fact.slug != slug:
                continue
            brain._scan((fact.old + fact.new + fact.evidence).encode())
            if SENSITIVE.search(fact.old + " " + fact.new + " " + fact.evidence):
                review.append({"slug": slug, "reason": "sensitive-verification"})
                continue
            if fact.expected_sha256 == digest and fact.evidence.strip() and fact.old and body.count(fact.old) == 1:
                body = body.replace(fact.old, fact.new, 1)
        meta = dict(doc.meta)
        # Exact duplicates only; keep both files and mark redundant evidence pending review.
        if body in bodies and body.strip():
            meta["status"] = "pending_review"
        else:
            bodies[body] = slug
        data = render(meta, body).encode()
        if data != text.encode():
            changed.append(slug)
            staged.append((path, data))
    _commit(brain, staged)
    return {"applied": changed, "human_review": review}


def run_nightly(brain: Brain, adapters: tuple[SourceAdapter, ...], *, day: date | None = None) -> dict:
    brain._require()
    day = day or datetime.now(ZoneInfo(brain.config().nightly_timezone)).date()
    with DreamLock(brain.control / "nightly.lock"):
        verified = nightly_sync(brain, adapters, day)
        before = _analyze(brain, day.isoformat())
        repairs = repair_easy(brain, verified, day)
        # Preserve the pre-repair contradictions and human-review decisions in canonical Markdown.
        import json
        report = _write(brain, f"reports/contradictions-{day}.md", f"Contradictions {day}",
                        json.dumps({"contradictions": before["contradictions"], **repairs}, sort_keys=True, indent=2),
                        day, kind="dream-report")
        _commit(brain, [report])
        return {"day": str(day), "repairs": repairs, "dream": run_dream(brain)}

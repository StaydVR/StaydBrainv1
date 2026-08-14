from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .errors import ValidationError


FIELDS = ("id", "slug", "title", "type", "created", "updated", "tags", "source", "status")
REQUIRED = {"id", "slug", "title", "type", "created", "updated"}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
LINK_RE = re.compile(
    r"\[\[(?P<destination>[a-z0-9][a-z0-9._/:-]*)(?:\|[^\]\n]+)?\]\]"
    r"(?:[ \t]*<!--[ \t]*agent-brain:relationship=(?P<relationship>[a-z][a-z0-9_-]*)[ \t]*-->)?"
)
LEGACY_LINK_RE = re.compile(r"^(?P<type>[a-z][a-z0-9_-]*):(?P<target>[a-z0-9][a-z0-9._/-]*)$")
FACT_RE = re.compile(r"^\s*-\s*fact:\s*([^|\n]+)\|([^|\n]+)\|([^|\n]+)\s*$", re.I | re.M)


@dataclass(frozen=True)
class Document:
    meta: dict[str, object]
    body: str


@dataclass(frozen=True)
class Chunk:
    heading: str
    heading_line: int
    start_line: int
    end_line: int
    body: str


MAX_CHUNK_CHARS = 8192


def _scalar(raw: str) -> str:
    value = raw.strip()
    if not value or value[0:1] in {"{", "[", "&", "*", "!", ">", "|"}:
        raise ValidationError("unsupported frontmatter value")
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if "\n" in value or "\r" in value:
        raise ValidationError("multiline frontmatter is forbidden")
    return value


def parse(text: str) -> Document:
    if not text.startswith("---\n"):
        raise ValidationError("frontmatter must start on byte zero")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValidationError("unterminated frontmatter")
    lines = text[4:end].splitlines()
    meta: dict[str, object] = {}
    for line in lines:
        if not line or line.startswith((" ", "\t", "#")) or ":" not in line:
            raise ValidationError("invalid frontmatter syntax")
        key, raw = line.split(":", 1)
        if key not in FIELDS or key in meta:
            raise ValidationError("unknown or duplicate frontmatter key")
        value = raw.strip()
        if key == "tags":
            if not (value.startswith("[") and value.endswith("]")):
                raise ValidationError("tags must be an inline list")
            inside = value[1:-1].strip()
            meta[key] = [] if not inside else [_scalar(x) for x in inside.split(",")]
        else:
            meta[key] = _scalar(value)
    if not REQUIRED.issubset(meta):
        raise ValidationError("missing required frontmatter")
    if not UUID_RE.fullmatch(str(meta["id"])):
        raise ValidationError("invalid document id")
    if not SLUG_RE.fullmatch(str(meta["slug"])):
        raise ValidationError("invalid document slug")
    for field in ("created", "updated"):
        try:
            datetime.fromisoformat(str(meta[field]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError(f"invalid {field} timestamp") from exc
    return Document(meta, text[end + 5 :])


def render(meta: dict[str, object], body: str) -> str:
    unknown = set(meta) - set(FIELDS)
    if unknown or not REQUIRED.issubset(meta):
        raise ValidationError("invalid frontmatter fields")
    lines = ["---"]
    for key in FIELDS:
        if key not in meta:
            continue
        value = meta[key]
        if key == "tags":
            value = "[" + ", ".join(str(x) for x in value) + "]"
        lines.append(f"{key}: {value}")
    text = "\n".join(lines) + "\n---\n" + body.lstrip("\n")
    parse(text)
    return text


def links(body: str) -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    for match in LINK_RE.finditer(body):
        line = body.count("\n", 0, match.start()) + 1
        destination = match.group("destination")
        legacy = LEGACY_LINK_RE.fullmatch(destination)
        if legacy:
            relationship = match.group("relationship") or legacy.group("type")
            target = legacy.group("target")
        else:
            relationship = match.group("relationship") or "related"
            target = destination
            if target.startswith("brain/pages/"):
                target = target.removeprefix("brain/pages/").removesuffix(".md")
        found.append((relationship, target, line))
    return found


def facts(body: str) -> list[tuple[str, str, str, int]]:
    return [
        tuple(x.strip() for x in match.groups()) + (body.count("\n", 0, match.start()) + 1,)
        for match in FACT_RE.finditer(body)
    ]


def _append_bounded_chunk(
    result: list[Chunk], heading: str, heading_line: int, lines: list[str], start: int, end: int
) -> None:
    pending: list[str] = []
    pending_start = start
    pending_size = 0

    def flush(line_end: int) -> None:
        nonlocal pending, pending_size, pending_start
        if pending:
            result.append(Chunk(heading, heading_line, pending_start + 1, line_end, "".join(pending)))
            pending = []
            pending_size = 0

    for line_index in range(start, end):
        line = lines[line_index]
        if len(line) > MAX_CHUNK_CHARS:
            flush(line_index)
            for offset in range(0, len(line), MAX_CHUNK_CHARS):
                result.append(Chunk(
                    heading, heading_line, line_index + 1, line_index + 1,
                    line[offset:offset + MAX_CHUNK_CHARS],
                ))
            pending_start = line_index + 1
            continue
        if pending and pending_size + len(line) > MAX_CHUNK_CHARS:
            flush(line_index)
            pending_start = line_index
        elif not pending:
            pending_start = line_index
        pending.append(line)
        pending_size += len(line)
    flush(end)


def chunks(body: str) -> list[Chunk]:
    """Split Markdown into deterministic body-relative paragraph chunks."""
    lines = body.splitlines(keepends=True)
    result: list[Chunk] = []
    heading = ""
    heading_line = 0
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        match = re.match(r"^#{1,6}[ \t]+(.+?)\s*#*\s*$", stripped)
        if match:
            heading = match.group(1).strip()
            heading_line = index + 1
            index += 1
            continue
        if not stripped:
            index += 1
            continue
        start = index
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if not candidate or re.match(r"^#{1,6}[ \t]+", candidate):
                break
            index += 1
        _append_bounded_chunk(result, heading, heading_line, lines, start, index)
    if not result and lines:
        _append_bounded_chunk(result, heading, heading_line, lines, 0, len(lines))
    if not result:
        # Preserve v0.1 title/slug retrieval for valid metadata-only pages.
        result.append(Chunk("", 0, 1, 1, ""))
    return result

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

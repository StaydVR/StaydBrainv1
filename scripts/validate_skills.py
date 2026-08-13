from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if sys.version_info < (3, 11):
    raise SystemExit("Agent Brain skill validation requires Python 3.11 or newer")
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_brain.cli import parser as cli_parser
from agent_brain.errors import SecurityError
from agent_brain.security import scan


CORE_SKILLS = {
    "brain-first", "safe-capture", "cited-answer", "filing-and-frontmatter", "ingest-gate",
    "dream-review", "correction-pipeline", "data-loss-gate", "brain-health", "migration",
}
OPTIONAL_SKILLS = {"daily-brief"}
REQUIRED_SECTIONS = (
    "Prerequisites", "Permitted operations", "Denied operations", "Workflow", "Verification", "Failure behavior",
)
COMMAND_RE = re.compile(r"python -m agent_brain --root \S+ ([a-z][a-z-]*)")
BYPASS_PATTERNS = (
    re.compile(r"\b(?:skip|bypass|circumvent|evade|disable) (?:the )?(?:security|scan|quarantine|approval|capability|citation)", re.I),
    re.compile(r"\bignore (?:the )?(?:quarantine|approval gate|source boundar|citation requirement)", re.I),
    re.compile(r"\bproceed without (?:scanning|approval|a citation|source validation)", re.I),
    re.compile(r"\bwrite raw files directly (?:into|to) brain/", re.I),
)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _frontmatter(text: str, path: Path) -> dict[str, Any]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"{path}: missing frontmatter")
    raw, _body = text[4:].split("\n---\n", 1)
    metadata: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line:
            raise ValueError(f"{path}: invalid frontmatter line")
        key, value = line.split(":", 1)
        if key in metadata:
            raise ValueError(f"{path}: duplicate frontmatter field {key}")
        metadata[key] = json.loads(value.strip()) if key == "triggers" else value.strip()
    if set(metadata) != {"name", "description", "triggers"}:
        raise ValueError(f"{path}: frontmatter must contain only name, description, triggers")
    if not metadata["name"] or not metadata["description"]:
        raise ValueError(f"{path}: name and description are required")
    triggers = metadata["triggers"]
    if not isinstance(triggers, list) or not triggers or not all(isinstance(item, str) and item.strip() for item in triggers):
        raise ValueError(f"{path}: triggers must be a non-empty string list")
    return metadata


def _cli_commands() -> set[str]:
    parsed = cli_parser()
    for action in parsed._actions:
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            return set(choices)
    raise RuntimeError("CLI subcommands are unavailable")


def validate(root: Path) -> list[str]:
    failures: list[str] = []
    skills_root = root / "skills"
    manifest_path = skills_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"invalid manifest: {exc}"]
    if not isinstance(manifest, dict) or set(manifest) != {"version", "skills"} or manifest.get("version") != 1:
        return ["manifest must contain version 1 and skills"]
    entries = manifest.get("skills")
    if not isinstance(entries, list):
        return ["manifest skills must be a list"]

    manifest_names: list[str] = []
    all_triggers: list[str] = []
    known_commands = _cli_commands()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"name", "path", "commands", "triggers"}:
            failures.append("each manifest entry must contain name, path, commands, triggers")
            continue
        name, relative = entry["name"], entry["path"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            failures.append(f"invalid skill name: {name!r}")
            continue
        manifest_names.append(name)
        expected_path = f"{name}/SKILL.md"
        if relative != expected_path:
            failures.append(f"{name}: path must be {expected_path}")
            continue
        path = skills_root / relative
        if path.is_symlink() or path.parent.is_symlink():
            failures.append(f"{name}: skill path must not use symlinks")
            continue
        try:
            text = path.read_text(encoding="utf-8")
            metadata = _frontmatter(text, path)
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(str(exc))
            continue
        if metadata["name"] != name:
            failures.append(f"{name}: frontmatter name mismatch")
        if entry["triggers"] != metadata["triggers"]:
            failures.append(f"{name}: manifest triggers differ from frontmatter")
        all_triggers.extend(item.casefold().strip() for item in metadata["triggers"])
        for section in REQUIRED_SECTIONS:
            if len(re.findall(rf"^## {re.escape(section)}$", text, flags=re.M)) != 1:
                failures.append(f"{name}: requires exactly one '{section}' section")
        if not re.search(r"^1\. ", text, flags=re.M):
            failures.append(f"{name}: workflow must be numbered")
        commands = entry["commands"]
        if not isinstance(commands, list) or commands != sorted(set(commands)):
            failures.append(f"{name}: commands must be a sorted unique list")
        elif not set(commands) <= known_commands:
            failures.append(f"{name}: unknown manifest command {sorted(set(commands) - known_commands)}")
        referenced = sorted(set(COMMAND_RE.findall(text)))
        if len(COMMAND_RE.findall(text)) != text.count("python -m agent_brain"):
            failures.append(f"{name}: malformed Agent Brain command reference")
        if commands != referenced:
            failures.append(f"{name}: command references differ: manifest={commands}, body={referenced}")
        for pattern in BYPASS_PATTERNS:
            if pattern.search(text):
                failures.append(f"{name}: prohibited bypass language")
                break
        try:
            scan(text.encode(), 1_048_576)
        except SecurityError as exc:
            failures.append(f"{name}: privacy or secret scan failed: {','.join(exc.reasons)}")

    actual_dirs = {path.parent.name for path in skills_root.glob("*/SKILL.md")}
    name_set = set(manifest_names)
    if len(manifest_names) != len(name_set):
        failures.append("manifest skill names must be unique")
    if len(all_triggers) != len(set(all_triggers)):
        failures.append("skill triggers must be globally unique")
    if name_set != actual_dirs:
        failures.append(f"manifest coverage mismatch: manifest={sorted(name_set)}, disk={sorted(actual_dirs)}")
    if not CORE_SKILLS <= name_set or not name_set <= CORE_SKILLS | OPTIONAL_SKILLS:
        failures.append("manifest must cover the ten core skills and only supported optional skills")
    resolver = skills_root / "RESOLVER.md"
    if not resolver.is_file() or resolver.is_symlink():
        failures.append("missing safe skills/RESOLVER.md")
    for artifact in (manifest_path, resolver):
        if artifact.is_file() and not artifact.is_symlink():
            try:
                scan(artifact.read_bytes(), 1_048_576)
            except (OSError, SecurityError) as exc:
                reasons = ",".join(exc.reasons) if isinstance(exc, SecurityError) else type(exc).__name__
                failures.append(f"{artifact.name}: privacy or secret scan failed: {reasons}")
    return failures


def main() -> int:
    argument_parser = argparse.ArgumentParser(description="Validate the Agent Brain v1 skillpack")
    argument_parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = argument_parser.parse_args()
    failures = validate(args.root.resolve())
    if failures:
        print("\n".join(failures))
        return 1
    print("skill validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

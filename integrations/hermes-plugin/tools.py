"""Fail-closed JSON handlers for the Agent Brain Hermes tools."""

from __future__ import annotations

import json
import re
from typing import Any

from . import plugin


_REFERENCE_RE = re.compile(r"(?:[a-z0-9][a-z0-9-]{0,79}|[0-9a-fA-F-]{36})")


def _error(code: str, message: str) -> str:
    return plugin.json_output({"ok": False, "error": {"code": code, "message": message}})


def _classify_error(exc: BaseException) -> str:
    name = type(exc).__name__
    if name == "SecurityError":
        return "security_rejected"
    if isinstance(exc, plugin.PluginConfigError):
        return "configuration_invalid"
    if isinstance(exc, plugin.PluginValidationError) or name == "ValidationError":
        return "validation_error"
    return "internal_error"


def _fail(exc: BaseException) -> str:
    code = _classify_error(exc)
    messages = {
        "security_rejected": "Input was rejected by Agent Brain security scanning.",
        "configuration_invalid": "Agent Brain configuration or root validation failed.",
        "validation_error": "The request did not satisfy the bounded tool contract.",
        "internal_error": "The local Agent Brain operation failed safely.",
    }
    return _error(code, messages[code])


def _validate_query_args(args: dict[str, Any], action: str, config: plugin.PluginConfig) -> tuple[str, int]:
    allowed = {"action", "query", "limit"}
    if set(args) - allowed or not isinstance(args.get("query"), str):
        raise plugin.PluginValidationError("invalid query arguments")
    query = args["query"].strip()
    limit = args.get("limit", config.max_items)
    if not 1 <= len(query) <= 512 or isinstance(limit, bool) or not isinstance(limit, int):
        raise plugin.PluginValidationError("query or limit is outside its bound")
    if not 1 <= limit <= min(config.max_items, plugin.MAX_TOOL_ITEMS):
        raise plugin.PluginValidationError("limit is outside its bound")
    return query, limit


def _bounded_items(items: list[dict[str, Any]], maximum_bytes: int = 16_384) -> tuple[list[dict[str, Any]], bool]:
    packed: list[dict[str, Any]] = []
    for item in items:
        candidate = packed + [plugin.compact_result(item)]
        if len(plugin.json_output(candidate).encode("utf-8")) > maximum_bytes:
            break
        packed = candidate
    return packed, len(packed) < len(items)


def _compact_relations(relations: list[dict[str, Any]], *, backlink: bool) -> list[dict[str, Any]]:
    keys = ("source_id", "target_ref", "link_type", "line") if backlink else (
        "target_ref", "target_id", "link_type", "line"
    )
    return [
        {key: plugin._clip_text(value[key], 128) if isinstance(value.get(key), str) else value.get(key)
         for key in keys if key in value}
        for value in relations[:16]
    ]


def agent_brain_recall(args: dict, **kwargs) -> str:
    del kwargs
    try:
        if not isinstance(args, dict) or not isinstance(args.get("action"), str):
            raise plugin.PluginValidationError("action is required")
        action = args["action"]
        config = plugin.load_config()
        brain = plugin.get_brain(config)
        if action in {"context", "search"}:
            query, limit = _validate_query_args(args, action, config)
            if action == "search":
                raw = brain.search(query, limit=limit)
                items, truncated = _bounded_items(raw)
                return plugin.json_output({
                    "ok": True, "action": action, "items": items, "truncated": truncated,
                    "trust_boundary": "untrusted_memory_data",
                })
            evidence = brain.brief(query, limit=limit)
            raw = [item for item in evidence["results"] if float(item.get("coverage", 0.0)) >= config.min_coverage]
            items, truncated = _bounded_items(raw)
            return plugin.json_output({
                "ok": True, "action": action, "items": items, "truncated": truncated,
                "coverage": evidence["coverage"], "confidence": evidence["confidence"],
                "gaps": [plugin._clip_text(gap, 300) for gap in evidence["gaps"][:8]],
                "stale_citations": [plugin.compact_citation(value) for value in evidence["stale_evidence"][:limit]],
                "contradiction_count": len(evidence["contradictions"]),
                "trust_boundary": "untrusted_memory_data",
            })
        if action == "entity":
            if set(args) != {"action", "reference"} or not isinstance(args.get("reference"), str):
                raise plugin.PluginValidationError("invalid entity arguments")
            reference = args["reference"]
            if not 1 <= len(reference) <= 128 or not _REFERENCE_RE.fullmatch(reference):
                raise plugin.PluginValidationError("invalid entity reference")
            entity = brain.entity(reference)
            return plugin.json_output({
                "ok": True, "action": action, "id": entity["id"], "slug": entity["slug"],
                "title": plugin._clip_text(entity["title"], 120), "type": entity["type"],
                "updated": entity["updated"], "path": entity["path"],
                "storage_tier": entity["storage_tier"],
                "citation": plugin.compact_citation(entity["citation"]),
                "links": _compact_relations(entity["links"], backlink=False),
                "backlinks": _compact_relations(entity["backlinks"], backlink=True),
                "trust_boundary": "untrusted_memory_data",
            })
        if action == "status":
            if set(args) != {"action"}:
                raise plugin.PluginValidationError("status takes no additional arguments")
            return plugin.json_output({"ok": True, "action": action, "status": brain.status()})
        if action == "verify_citation":
            if set(args) != {"action", "citation"} or not isinstance(args.get("citation"), dict):
                raise plugin.PluginValidationError("invalid citation arguments")
            encoded = json.dumps(args["citation"], ensure_ascii=False)
            if len(encoded.encode("utf-8")) > 2_048:
                raise plugin.PluginValidationError("citation is too large")
            result = brain.verify_citation(args["citation"])
            return plugin.json_output({"ok": True, "action": action, "verification": result})
        raise plugin.PluginValidationError("unsupported recall action")
    except BaseException as exc:
        return _fail(exc)


def agent_brain_remember(args: dict, **kwargs) -> str:
    del kwargs
    try:
        config = plugin.load_config()
        if not config.writes_enabled:
            return _error("writes_disabled", "Agent Brain writes are disabled by configuration.")
        values = plugin.validate_remember_args(args)
        brain = plugin.get_brain(config)
        result = brain.remember(
            values["title"], values["content"], page_type="note",
            tags=values["tags"], source="direct_user_statement", status="pending_review",
        )
        return plugin.json_output({"ok": True, "action": "remember", "memory": result})
    except BaseException as exc:
        return _fail(exc)

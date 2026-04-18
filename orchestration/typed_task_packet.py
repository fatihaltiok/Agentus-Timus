"""Phase F2 typed task packet and request preflight contracts."""

from __future__ import annotations

import json
import math
import os
from typing import Any, Iterable, Mapping


TASK_PACKET_SCHEMA_VERSION = 1
REQUEST_PREFLIGHT_SCHEMA_VERSION = 1


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return max(minimum, int(default))
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return max(minimum, int(default))


def _clean_text(value: Any, *, limit: int = 220) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped or text[:limit]}..."


def _normalize_text_list(
    values: Iterable[Any] | None,
    *,
    limit_items: int = 6,
    limit_chars: int = 180,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = _clean_text(value, limit=limit_chars)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(text)
        if len(normalized) >= limit_items:
            break
    return normalized


def _normalize_scalar_or_list(value: Any, *, value_limit: int = 180) -> Any:
    if isinstance(value, Mapping):
        return _normalize_mapping(value, value_limit=value_limit)
    if isinstance(value, (list, tuple, set)):
        return _normalize_text_list(value, limit_items=6, limit_chars=value_limit)
    return _clean_text(value, limit=value_limit)


def _normalize_mapping(
    payload: Mapping[str, Any] | None,
    *,
    key_limit: int = 64,
    value_limit: int = 180,
    item_limit: int = 8,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in list(payload.items())[:item_limit]:
        key = _clean_text(raw_key, limit=key_limit)
        if not key:
            continue
        normalized[key] = _normalize_scalar_or_list(raw_value, value_limit=value_limit)
    return normalized


def _approx_tokens_from_chars(char_count: int) -> int:
    return max(0, math.ceil(max(int(char_count or 0), 0) / 4))


def _normalize_tools(values: Iterable[Any] | None) -> list[str]:
    return _normalize_text_list(values, limit_items=12, limit_chars=64)


def build_typed_task_packet(
    *,
    packet_type: str,
    objective: Any,
    scope: Mapping[str, Any] | None = None,
    acceptance_criteria: Iterable[Any] | None = None,
    allowed_tools: Iterable[Any] | None = None,
    reporting_contract: Mapping[str, Any] | None = None,
    escalation_policy: Mapping[str, Any] | None = None,
    state_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Builds a normalized typed task packet."""

    return {
        "schema_version": TASK_PACKET_SCHEMA_VERSION,
        "packet_type": _clean_text(packet_type, limit=64).lower() or "generic",
        "objective": _clean_text(objective, limit=320),
        "scope": _normalize_mapping(scope, value_limit=180, item_limit=10),
        "acceptance_criteria": _normalize_text_list(
            acceptance_criteria,
            limit_items=8,
            limit_chars=180,
        ),
        "allowed_tools": _normalize_tools(allowed_tools),
        "reporting_contract": _normalize_mapping(
            reporting_contract,
            value_limit=180,
            item_limit=10,
        ),
        "escalation_policy": _normalize_mapping(
            escalation_policy,
            value_limit=180,
            item_limit=10,
        ),
        "state_context": _normalize_mapping(
            state_context,
            value_limit=180,
            item_limit=16,
        ),
    }


def parse_typed_task_packet(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        loaded = dict(raw)
    elif isinstance(raw, str):
        text = str(raw).strip()
        if not text:
            return {}
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if not isinstance(decoded, Mapping):
            return {}
        loaded = dict(decoded)
    else:
        return {}

    return build_typed_task_packet(
        packet_type=loaded.get("packet_type"),
        objective=loaded.get("objective"),
        scope=loaded.get("scope"),
        acceptance_criteria=loaded.get("acceptance_criteria"),
        allowed_tools=loaded.get("allowed_tools"),
        reporting_contract=loaded.get("reporting_contract"),
        escalation_policy=loaded.get("escalation_policy"),
        state_context=loaded.get("state_context"),
    )


def is_deep_researchish_task(*, task_type: Any = "", recipe_id: Any = "", allowed_tools: Iterable[Any] | None = None) -> bool:
    lowered_task_type = str(task_type or "").strip().lower()
    lowered_recipe_id = str(recipe_id or "").strip().lower()
    tool_names = {str(item or "").strip().lower() for item in (allowed_tools or ()) if str(item or "").strip()}
    if "research" in lowered_task_type or "research" in lowered_recipe_id:
        return True
    return "start_deep_research" in tool_names or "generate_research_report" in tool_names


def resolve_request_char_limit(
    *,
    task_type: Any = "",
    recipe_id: Any = "",
    allowed_tools: Iterable[Any] | None = None,
) -> int:
    default_limit = 1200 if is_deep_researchish_task(
        task_type=task_type,
        recipe_id=recipe_id,
        allowed_tools=allowed_tools,
    ) else 2200
    return _env_int("TIMUS_REQUEST_PREFLIGHT_MAX_REQUEST_CHARS", default_limit, minimum=40)


def shorten_for_preflight(
    value: Any,
    *,
    task_type: Any = "",
    recipe_id: Any = "",
    allowed_tools: Iterable[Any] | None = None,
) -> str:
    limit = resolve_request_char_limit(
        task_type=task_type,
        recipe_id=recipe_id,
        allowed_tools=allowed_tools,
    )
    return _clean_text(value, limit=limit)


def build_request_preflight(
    *,
    packet: Mapping[str, Any] | None,
    original_request: Any = "",
    rendered_handoff: Any = "",
    task_type: Any = "",
    recipe_id: Any = "",
) -> dict[str, Any]:
    """Computes a small machine-readable preflight report for critical calls."""

    normalized_packet = parse_typed_task_packet(packet or {})
    packet_json = json.dumps(normalized_packet, ensure_ascii=False, sort_keys=True)
    original_request_text = str(original_request or "").strip()
    rendered_handoff_text = str(rendered_handoff or "").strip()
    allowed_tools = list(normalized_packet.get("allowed_tools") or [])

    provider_token_limit = _env_int("MAX_CONTEXT_TOKENS", 16000, minimum=512)
    working_memory_chars = _env_int("WM_MAX_CHARS", 10000, minimum=1000)
    max_packet_chars = _env_int(
        "TIMUS_TASK_PACKET_MAX_CHARS",
        min(working_memory_chars, 3600),
        minimum=800,
    )
    max_handoff_chars = _env_int(
        "TIMUS_HANDOFF_MAX_CHARS",
        max(working_memory_chars, 8000),
        minimum=2000,
    )
    max_request_chars = resolve_request_char_limit(
        task_type=task_type,
        recipe_id=recipe_id,
        allowed_tools=allowed_tools,
    )

    packet_chars = len(packet_json)
    handoff_chars = len(rendered_handoff_text)
    request_chars = len(original_request_text)
    total_chars = packet_chars + handoff_chars + request_chars
    approx_total_tokens = _approx_tokens_from_chars(total_chars)

    issues: list[str] = []
    actions: list[str] = []
    adjustments: list[str] = []
    state = "ok"

    if request_chars > max_request_chars:
        issues.append("request_chars_exceeds_guideline")
        actions.append("reduce_or_chunk_original_request")
        state = "warn"
    if packet_chars > max_packet_chars:
        issues.append("packet_chars_exceeds_guideline")
        actions.append("trim_optional_packet_fields")
        state = "warn"
    if handoff_chars > max_handoff_chars:
        issues.append("handoff_chars_exceeds_guideline")
        actions.append("trim_optional_handoff_sections")
        state = "warn"
    if approx_total_tokens > int(provider_token_limit * 0.8):
        issues.append("provider_window_pressure")
        actions.append("reduce_context_before_model_call")
        state = "warn"

    blocked = False
    if request_chars > max_request_chars * 2:
        blocked = True
        issues.append("request_chars_hard_limit")
        actions.append("split_request_before_dispatch")
    if packet_chars > int(max_packet_chars * 2):
        blocked = True
        issues.append("packet_chars_hard_limit")
        actions.append("compact_packet_before_dispatch")
    if handoff_chars > int(max_handoff_chars * 1.5):
        issues.append("handoff_chars_hard_limit")
        actions.append("compact_handoff_before_dispatch")
        state = "warn"
    if approx_total_tokens > int(provider_token_limit * 0.95):
        issues.append("provider_window_hard_limit")
        actions.append("shrink_context_before_model_call")
        state = "warn"

    if blocked:
        state = "blocked"

    return {
        "schema_version": REQUEST_PREFLIGHT_SCHEMA_VERSION,
        "state": state,
        "blocked": blocked,
        "issues": issues,
        "actions": actions,
        "adjustments": adjustments,
        "caps": {
            "provider_token_limit": provider_token_limit,
            "working_memory_chars": working_memory_chars,
            "max_request_chars": max_request_chars,
            "max_packet_chars": max_packet_chars,
            "max_handoff_chars": max_handoff_chars,
        },
        "metrics": {
            "original_request_chars": request_chars,
            "packet_chars": packet_chars,
            "handoff_chars": handoff_chars,
            "approx_total_tokens": approx_total_tokens,
        },
    }

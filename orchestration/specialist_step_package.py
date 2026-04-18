"""Z4 specialist step packaging contract."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Mapping

from orchestration.specialist_context import parse_specialist_context_payload


SPECIALIST_STEP_PACKAGE_SCHEMA_VERSION = 1
SPECIALIST_STEP_RETURN_SIGNALS = (
    "step_completed",
    "step_blocked",
    "step_unnecessary",
    "goal_satisfied",
)
_STEP_SIGNAL_RE = re.compile(
    r"^\s*Specialist Step Signal:\s*(step_completed|step_blocked|step_unnecessary|goal_satisfied)"
    r"(?:\s*\|\s*reason=([a-z0-9_:-]+))?\s*(?:\n+|\Z)",
    re.IGNORECASE,
)


def _clean_text(value: Any, *, limit: int = 220) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _normalize_items(values: Iterable[Any] | None, *, limit: int = 6, max_chars: int = 160) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        cleaned = _clean_text(value, limit=max_chars)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append(cleaned)
        if len(items) >= limit:
            break
    return items


def build_specialist_step_package_payload(
    *,
    plan_summary: Mapping[str, Any] | None = None,
    plan_step: Mapping[str, Any] | None = None,
    specialist_context: Mapping[str, Any] | None = None,
    original_user_task: Any = "",
    current_goal: Any = "",
    previous_stage_result: Any = "",
    captured_context: Any = "",
    source_urls: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    summary = dict(plan_summary or {})
    step = dict(plan_step or {})
    context = parse_specialist_context_payload(specialist_context or {})

    plan_id = _clean_text(summary.get("plan_id"), limit=64)
    step_id = _clean_text(step.get("id"), limit=64).lower().replace(" ", "_")
    step_title = _clean_text(step.get("title"), limit=180)
    if not plan_id and not step_id and not step_title:
        return {}

    focus_context = {
        "original_user_task": _clean_text(original_user_task, limit=320),
        "active_goal": _clean_text(
            context.get("active_goal") or current_goal or summary.get("goal"),
            limit=220,
        ),
        "open_loop": _clean_text(context.get("open_loop"), limit=220),
        "next_expected_step": _clean_text(
            context.get("next_expected_step") or step_title,
            limit=180,
        ),
        "previous_stage_result": _clean_text(previous_stage_result, limit=240),
        "captured_context": _clean_text(captured_context, limit=240),
        "source_urls": _normalize_items(source_urls, limit=4, max_chars=180),
    }

    return {
        "schema_version": SPECIALIST_STEP_PACKAGE_SCHEMA_VERSION,
        "plan_id": plan_id,
        "plan_mode": _clean_text(summary.get("plan_mode"), limit=48).lower(),
        "plan_goal": _clean_text(summary.get("goal"), limit=280),
        "goal_satisfaction_mode": _clean_text(summary.get("goal_satisfaction_mode"), limit=64),
        "step_id": step_id,
        "step_title": step_title,
        "step_kind": _clean_text(step.get("step_kind"), limit=48).lower(),
        "assigned_agent": _clean_text(step.get("assigned_agent"), limit=48).lower(),
        "delegation_mode": _clean_text(step.get("delegation_mode"), limit=48).lower(),
        "expected_output": _clean_text(step.get("expected_output"), limit=180),
        "completion_signals": _normalize_items(step.get("completion_signals"), limit=8, max_chars=120),
        "depends_on": _normalize_items(step.get("depends_on"), limit=6, max_chars=64),
        "focus_context": focus_context,
        "return_signal_contract": list(SPECIALIST_STEP_RETURN_SIGNALS),
    }


def parse_specialist_step_package_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, Mapping):
        loaded = dict(raw)
    elif isinstance(raw, str):
        text = str(raw or "").strip()
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

    focus = dict(loaded.get("focus_context") or {})
    return build_specialist_step_package_payload(
        plan_summary={
            "plan_id": loaded.get("plan_id"),
            "plan_mode": loaded.get("plan_mode"),
            "goal": loaded.get("plan_goal"),
            "goal_satisfaction_mode": loaded.get("goal_satisfaction_mode"),
        },
        plan_step={
            "id": loaded.get("step_id"),
            "title": loaded.get("step_title"),
            "step_kind": loaded.get("step_kind"),
            "assigned_agent": loaded.get("assigned_agent"),
            "delegation_mode": loaded.get("delegation_mode"),
            "expected_output": loaded.get("expected_output"),
            "completion_signals": loaded.get("completion_signals"),
            "depends_on": loaded.get("depends_on"),
        },
        original_user_task=focus.get("original_user_task"),
        current_goal=focus.get("active_goal"),
        previous_stage_result=focus.get("previous_stage_result"),
        captured_context=focus.get("captured_context"),
        source_urls=focus.get("source_urls") or (),
    )


def extract_specialist_step_package_from_handoff_data(
    handoff_data: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    if not isinstance(handoff_data, Mapping):
        return {}
    raw = handoff_data.get("specialist_step_package_json") or handoff_data.get("specialist_step_package")
    return parse_specialist_step_package_payload(raw)


def render_specialist_step_package_block(
    payload: Mapping[str, Any] | None,
    *,
    header: str = "# ARBEITSSCHRITT-PAKET",
) -> str:
    parsed = parse_specialist_step_package_payload(payload)
    if not parsed:
        return ""

    lines = [header]
    if parsed.get("plan_goal"):
        lines.append(f"Plan-Ziel: {parsed['plan_goal']}")
    if parsed.get("step_title"):
        lines.append(f"Aktueller Arbeitsschritt: {parsed['step_title']}")
    if parsed.get("step_kind"):
        lines.append(f"Schritt-Typ: {parsed['step_kind']}")
    if parsed.get("assigned_agent"):
        lines.append(f"Ziel-Spezialist: {parsed['assigned_agent']}")
    if parsed.get("expected_output"):
        lines.append(f"Erwarteter Schritt-Output: {parsed['expected_output']}")
    if parsed.get("completion_signals"):
        lines.append("Schritt-Erfolgssignale: " + " | ".join(parsed.get("completion_signals") or []))
    focus = dict(parsed.get("focus_context") or {})
    if focus.get("active_goal"):
        lines.append(f"Fokussiertes Ziel: {focus['active_goal']}")
    if focus.get("next_expected_step"):
        lines.append(f"Meta erwartet als naechsten Schritt: {focus['next_expected_step']}")
    if focus.get("previous_stage_result"):
        lines.append(f"Vorheriges Schritt-Ergebnis: {focus['previous_stage_result']}")
    if focus.get("captured_context"):
        lines.append(f"Bereits gesicherter Kontext: {focus['captured_context']}")
    if focus.get("source_urls"):
        lines.append("Relevante Quellen: " + " | ".join(focus.get("source_urls") or []))
    if parsed.get("return_signal_contract"):
        lines.append("Zulaessige Ruecksignale: " + " | ".join(parsed.get("return_signal_contract") or []))
        lines.append(
            "Signal-Protokoll: Falls du klar belegen kannst, dass der Schritt erledigt, blockiert, "
            "unnoetig oder das Ziel schon erfuellt ist, beginne die Antwort mit "
            "'Specialist Step Signal: step_completed', 'step_blocked', "
            "'step_unnecessary' oder 'goal_satisfied'."
        )
    return "\n".join(lines)


def format_specialist_step_signal_response(
    signal: str,
    *,
    reason: str = "",
    message: str = "",
) -> str:
    cleaned_signal = str(signal or "").strip().lower()
    if cleaned_signal not in set(SPECIALIST_STEP_RETURN_SIGNALS):
        cleaned_signal = "step_blocked"
    header = f"Specialist Step Signal: {cleaned_signal}"
    cleaned_reason = _clean_text(reason, limit=80).lower().replace(" ", "_")
    if cleaned_reason:
        header += f" | reason={cleaned_reason}"
    cleaned_message = _clean_text(message, limit=4000)
    if not cleaned_message:
        return header
    return f"{header}\n\n{cleaned_message}"


def parse_specialist_step_signal_response(text: Any) -> Dict[str, Any]:
    raw = str(text or "")
    match = _STEP_SIGNAL_RE.match(raw)
    if not match:
        return {}
    signal = str(match.group(1) or "").strip().lower()
    reason = str(match.group(2) or "").strip().lower()
    cleaned_text = raw[match.end():].strip()
    return {
        "signal": signal,
        "reason": reason,
        "message": cleaned_text,
        "cleaned_text": cleaned_text,
    }

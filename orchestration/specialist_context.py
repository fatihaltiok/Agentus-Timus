"""Shared D0.9 specialist context contract."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Mapping


SPECIALIST_CONTEXT_SCHEMA_VERSION = 1
SPECIALIST_RETURN_SIGNALS = (
    "partial_result",
    "blocker",
    "context_mismatch",
    "needs_meta_reframe",
)
_SPECIALIST_SIGNAL_RE = re.compile(
    r"^\s*Specialist Signal:\s*(context_mismatch|needs_meta_reframe)"
    r"(?:\s*\|\s*reason=([a-z0-9_:-]+))?\s*(?:\n+|\Z)",
    re.IGNORECASE,
)

_SPECIALIST_CONTEXT_STOPWORDS = {
    "aber",
    "aktuell",
    "alle",
    "als",
    "also",
    "auf",
    "aus",
    "bei",
    "bitte",
    "das",
    "dass",
    "dein",
    "dem",
    "den",
    "der",
    "die",
    "dir",
    "doch",
    "ein",
    "eine",
    "einer",
    "eines",
    "er",
    "es",
    "fuer",
    "für",
    "hat",
    "hier",
    "ich",
    "ihr",
    "ihre",
    "im",
    "in",
    "ist",
    "jetzt",
    "kann",
    "mit",
    "noch",
    "nur",
    "oder",
    "schon",
    "sein",
    "soll",
    "sollte",
    "thema",
    "und",
    "uns",
    "unser",
    "vom",
    "von",
    "was",
    "wenn",
    "wie",
    "wir",
    "wurde",
    "zum",
    "zur",
}


def _clean_text(value: Any, *, limit: int = 220) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _normalize_items(values: Iterable[Any] | None, *, limit: int = 3, max_chars: int = 140) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
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


def build_specialist_context_payload(
    *,
    current_topic: Any = "",
    active_goal: Any = "",
    open_loop: Any = "",
    next_expected_step: Any = "",
    turn_type: Any = "",
    response_mode: Any = "",
    user_preferences: Iterable[Any] | None = None,
    recent_corrections: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    payload = {
        "schema_version": SPECIALIST_CONTEXT_SCHEMA_VERSION,
        "current_topic": _clean_text(current_topic, limit=220),
        "active_goal": _clean_text(active_goal, limit=220),
        "open_loop": _clean_text(open_loop, limit=220),
        "next_expected_step": _clean_text(next_expected_step, limit=180),
        "turn_type": _clean_text(turn_type, limit=64).lower(),
        "response_mode": _clean_text(response_mode, limit=64).lower(),
        "user_preferences": _normalize_items(user_preferences, limit=3, max_chars=140),
        "recent_corrections": _normalize_items(recent_corrections, limit=3, max_chars=140),
        "signal_contract": list(SPECIALIST_RETURN_SIGNALS),
    }
    return payload


def parse_specialist_context_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, Mapping):
        loaded: Dict[str, Any] = dict(raw)
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

    return build_specialist_context_payload(
        current_topic=loaded.get("current_topic"),
        active_goal=loaded.get("active_goal"),
        open_loop=loaded.get("open_loop"),
        next_expected_step=loaded.get("next_expected_step"),
        turn_type=loaded.get("turn_type"),
        response_mode=loaded.get("response_mode"),
        user_preferences=loaded.get("user_preferences") or (),
        recent_corrections=loaded.get("recent_corrections") or (),
    )


def extract_specialist_context_from_handoff_data(handoff_data: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(handoff_data, Mapping):
        return {}
    raw = handoff_data.get("specialist_context_json") or handoff_data.get("specialist_context")
    return parse_specialist_context_payload(raw)


def render_specialist_context_block(
    payload: Mapping[str, Any] | None,
    *,
    header: str = "# SPEZIALISTENKONTEXT",
    alignment: Mapping[str, Any] | None = None,
) -> str:
    parsed = parse_specialist_context_payload(payload)
    if not parsed:
        return ""

    lines = [header]
    if parsed.get("current_topic"):
        lines.append(f"Aktuelles Thema: {parsed['current_topic']}")
    if parsed.get("active_goal"):
        lines.append(f"Aktives Ziel: {parsed['active_goal']}")
    if parsed.get("open_loop"):
        lines.append(f"Offener Faden: {parsed['open_loop']}")
    if parsed.get("next_expected_step"):
        lines.append(f"Naechster erwarteter Schritt: {parsed['next_expected_step']}")
    if parsed.get("turn_type"):
        lines.append(f"Turn-Typ: {parsed['turn_type']}")
    if parsed.get("response_mode"):
        lines.append(f"Meta-Response-Modus: {parsed['response_mode']}")
    if parsed.get("user_preferences"):
        lines.append(
            "Nutzerpraeferenzen: "
            + " | ".join(str(item) for item in parsed.get("user_preferences") or [])
        )
    if parsed.get("recent_corrections"):
        lines.append(
            "Jungste Korrekturen: "
            + " | ".join(str(item) for item in parsed.get("recent_corrections") or [])
        )
    if parsed.get("signal_contract"):
        lines.append(
            "Rueckgabesignale: "
            + " | ".join(str(item) for item in parsed.get("signal_contract") or [])
        )
        lines.append(
            "Signal-Protokoll: Falls der Handoff erkennbar nicht passt, beginne die Antwort mit "
            "'Specialist Signal: context_mismatch' oder 'Specialist Signal: needs_meta_reframe'."
        )
    normalized_alignment = dict(alignment or {})
    alignment_state = str(normalized_alignment.get("alignment_state") or "").strip().lower()
    if alignment_state in {"context_mismatch", "needs_meta_reframe"}:
        lines.append(
            "Kontextwarnung: "
            + (
                "Der Handoff wirkt nur schwach zum aktuellen Themenanker passend."
                if alignment_state == "context_mismatch"
                else "Der Handoff wirkt so schwach verankert, dass Meta den Rahmen evtl. neu setzen muss."
            )
        )
        if normalized_alignment.get("reason"):
            lines.append(f"Alignment-Grund: {normalized_alignment['reason']}")
    return "\n".join(lines)


def _tokenize_terms(text: Any) -> set[str]:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return set()
    return {
        token
        for token in re.findall(r"[a-z0-9äöüß]+", normalized)
        if len(token) >= 3 and token not in _SPECIALIST_CONTEXT_STOPWORDS
    }


def assess_specialist_context_alignment(
    *,
    current_task: Any,
    payload: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    parsed = parse_specialist_context_payload(payload)
    if not parsed:
        return {}

    focus_text = " | ".join(
        item
        for item in (
            parsed.get("current_topic"),
            parsed.get("active_goal"),
            parsed.get("open_loop"),
            parsed.get("next_expected_step"),
        )
        if str(item or "").strip()
    )
    focus_terms = _tokenize_terms(focus_text)
    task_terms = _tokenize_terms(current_task)
    shared_terms = sorted(focus_terms.intersection(task_terms))
    turn_type = str(parsed.get("turn_type") or "").strip().lower()
    response_mode = str(parsed.get("response_mode") or "").strip().lower()
    anchored_context = sum(
        1 for value in (parsed.get("current_topic"), parsed.get("active_goal"), parsed.get("open_loop")) if value
    )
    high_sensitivity = (
        turn_type in {"followup", "correction", "complaint_about_last_answer", "approval_resume", "auth_resume"}
        or response_mode in {"resume_open_loop", "correct_previous_path", "summarize_state"}
    )

    if len(focus_terms) < 2 or len(task_terms) < 2:
        return {
            "alignment_state": "insufficient_evidence",
            "shared_terms": shared_terms,
            "overlap_count": len(shared_terms),
            "reason": "too_few_terms",
        }

    if shared_terms:
        return {
            "alignment_state": "aligned",
            "shared_terms": shared_terms[:5],
            "overlap_count": len(shared_terms),
            "reason": "shared_anchor_terms",
        }

    if high_sensitivity and anchored_context >= 2:
        return {
            "alignment_state": "needs_meta_reframe",
            "shared_terms": [],
            "overlap_count": 0,
            "reason": "followup_without_shared_anchor",
        }

    if anchored_context >= 2:
        return {
            "alignment_state": "context_mismatch",
            "shared_terms": [],
            "overlap_count": 0,
            "reason": "no_shared_anchor_terms",
        }

    return {
        "alignment_state": "insufficient_evidence",
        "shared_terms": [],
        "overlap_count": 0,
        "reason": "weak_context_anchor",
    }


def format_specialist_signal_response(
    signal: str,
    *,
    reason: str = "",
    message: str = "",
) -> str:
    cleaned_signal = str(signal or "").strip().lower()
    if cleaned_signal not in {"context_mismatch", "needs_meta_reframe"}:
        cleaned_signal = "needs_meta_reframe"
    header = f"Specialist Signal: {cleaned_signal}"
    cleaned_reason = _clean_text(reason, limit=80).lower().replace(" ", "_")
    if cleaned_reason:
        header += f" | reason={cleaned_reason}"
    cleaned_message = _clean_text(message, limit=4000)
    if not cleaned_message:
        return header
    return f"{header}\n\n{cleaned_message}"


def parse_specialist_signal_response(text: Any) -> Dict[str, Any]:
    raw = str(text or "")
    match = _SPECIALIST_SIGNAL_RE.match(raw)
    if not match:
        return {}
    signal = str(match.group(1) or "").strip().lower()
    reason = str(match.group(2) or "").strip().lower()
    cleaned_text = raw[match.end() :].strip()
    return {
        "signal": signal,
        "reason": reason,
        "message": cleaned_text,
        "cleaned_text": cleaned_text,
    }

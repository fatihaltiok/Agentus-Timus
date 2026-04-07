"""Evaluation and runtime risk helpers for D0.3 meta context bundles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


_RISKY_TURN_TYPES = {
    "followup",
    "clarification",
    "correction",
    "behavior_instruction",
    "preference_update",
    "complaint_about_last_answer",
    "approval_response",
    "auth_response",
    "handover_resume",
}

_RECOVERY_SLOT_TYPES = {
    "conversation_state",
    "open_loop",
    "recent_user_turn",
    "topic_memory",
    "preference_memory",
}

_HIGH_VALUE_SLOT_TYPES = {
    "conversation_state",
    "open_loop",
    "recent_user_turn",
    "topic_memory",
    "preference_memory",
    "semantic_recall",
}


def _as_bundle_dict(bundle: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(bundle or {})


def _slot_types(bundle: Mapping[str, Any] | None) -> list[str]:
    payload = _as_bundle_dict(bundle)
    slots = payload.get("context_slots") or []
    types: list[str] = []
    for item in slots:
        if not isinstance(item, Mapping):
            continue
        slot = str(item.get("slot") or "").strip()
        if slot:
            types.append(slot)
    return types


def _suppression_reasons(bundle: Mapping[str, Any] | None) -> list[str]:
    payload = _as_bundle_dict(bundle)
    suppressed = payload.get("suppressed_context") or []
    reasons: list[str] = []
    for item in suppressed:
        if not isinstance(item, Mapping):
            continue
        reason = str(item.get("reason") or "").strip()
        if reason:
            reasons.append(reason)
    return reasons


def detect_context_misread_risk(
    bundle: Mapping[str, Any] | None,
    *,
    dominant_turn_type: str = "",
    response_mode: str = "",
) -> dict[str, Any]:
    slot_types = _slot_types(bundle)
    suppressed_reasons = _suppression_reasons(bundle)
    turn_type = str(dominant_turn_type or "").strip().lower()
    mode = str(response_mode or "").strip().lower()

    risk_reasons: list[str] = []

    if turn_type in _RISKY_TURN_TYPES and not any(slot in slot_types for slot in _RECOVERY_SLOT_TYPES):
        risk_reasons.append("missing_recovery_context_for_risky_turn")

    if "assistant_fallback_context" in slot_types and not any(
        slot in slot_types for slot in ("recent_user_turn", "conversation_state", "open_loop")
    ):
        risk_reasons.append("assistant_fallback_without_user_anchor")

    if any(
        reason in suppressed_reasons
        for reason in ("location_context_without_current_evidence", "topic_mismatch_with_current_query")
    ) and not any(slot in slot_types for slot in _RECOVERY_SLOT_TYPES):
        risk_reasons.append("suppressed_old_context_without_replacement")

    if mode == "resume_open_loop" and "open_loop" not in slot_types:
        risk_reasons.append("resume_mode_without_open_loop")

    if len([slot for slot in slot_types if slot in _HIGH_VALUE_SLOT_TYPES]) <= 1 and turn_type in _RISKY_TURN_TYPES:
        risk_reasons.append("thin_context_for_risky_turn")

    return {
        "suspicious": bool(risk_reasons),
        "reasons": risk_reasons,
        "slot_types": slot_types,
        "suppressed_reasons": suppressed_reasons,
    }


@dataclass(frozen=True)
class MetaContextEvalCase:
    label: str
    bundle: dict[str, Any]
    dominant_turn_type: str
    response_mode: str
    expected_slots: list[str]
    forbidden_suppression_reasons: list[str]
    expected_suspicious: bool = False


def evaluate_meta_context_case(case: MetaContextEvalCase) -> dict[str, Any]:
    risk = detect_context_misread_risk(
        case.bundle,
        dominant_turn_type=case.dominant_turn_type,
        response_mode=case.response_mode,
    )
    slot_types = set(risk["slot_types"])
    suppressed = set(risk["suppressed_reasons"])
    missing_slots = [slot for slot in case.expected_slots if slot not in slot_types]
    forbidden_hits = [reason for reason in case.forbidden_suppression_reasons if reason in suppressed]

    passes = (
        not missing_slots
        and not forbidden_hits
        and bool(risk["suspicious"]) is bool(case.expected_suspicious)
    )

    score = 1.0
    if missing_slots:
        score -= 0.4
    if forbidden_hits:
        score -= 0.3
    if bool(risk["suspicious"]) is not bool(case.expected_suspicious):
        score -= 0.3

    return {
        "label": case.label,
        "missing_slots": missing_slots,
        "forbidden_suppression_hits": forbidden_hits,
        "expected_suspicious": case.expected_suspicious,
        "actual_suspicious": bool(risk["suspicious"]),
        "risk_reasons": list(risk["reasons"]),
        "passes": passes,
        "score": max(0.0, round(score, 3)),
    }


def summarize_meta_context_evals(cases: list[MetaContextEvalCase]) -> dict[str, Any]:
    if not cases:
        return {
            "total_cases": 0,
            "pass_rate": 0.0,
            "avg_score": 0.0,
            "results": [],
        }

    results = [evaluate_meta_context_case(case) for case in cases]
    total = len(results)
    return {
        "total_cases": total,
        "pass_rate": round(sum(1 for item in results if item["passes"]) / total, 3),
        "avg_score": round(sum(float(item["score"]) for item in results) / total, 3),
        "results": results,
    }

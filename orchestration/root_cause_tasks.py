from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from orchestration.diagnosis_records import DiagnosisRecord, DiagnosisResolution, normalize_evidence_level


_ROOT_CHANGE_TYPES = {
    "type_normalization",
    "state_invalidation",
    "loop_guard",
    "parsing_fix",
    "logic_fix",
}
_FOLLOWUP_KIND_BY_CHANGE_TYPE = {
    "monitoring": "followup_monitoring",
    "hardening": "followup_hardening",
    "cleanup": "followup_cleanup",
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def classify_change_focus(text: str) -> Dict[str, Any]:
    normalized = _normalize_text(text)
    followup_types: List[str] = []

    if _contains_any(normalized, ("monitor", "alert", "alerting", "logging", "telemetrie", "observability", "metric")):
        followup_types.append("monitoring")
    if _contains_any(normalized, ("hardening", "guardrail", "guard", "fallback", "absichern", "haerten")):
        followup_types.append("hardening")
    if _contains_any(normalized, ("cleanup", "bereinigen", "loeschen", "delete", "remove", "aufraeumen")):
        followup_types.append("cleanup")

    primary_type = ""
    if _contains_any(normalized, ("dict", "string", "strip", "typeerror", "type-error", "type error", "normalis")):
        primary_type = "type_normalization"
    elif _contains_any(normalized, ("invalidate", "invalidier", "stale", "revalid", "aktualisiert", "state update", "zustandsupdate")):
        primary_type = "state_invalidation"
    elif _contains_any(normalized, ("loop", "retry", "backoff", "rekursion", "schleife")):
        primary_type = "loop_guard"
    elif _contains_any(normalized, ("parser", "parse", "json", "payload")):
        primary_type = "parsing_fix"
    elif normalized:
        primary_type = "logic_fix"

    if not normalized:
        primary_type = ""

    if primary_type == "logic_fix" and not normalized:
        primary_type = ""

    return {
        "primary_change_type": primary_type,
        "followup_change_types": tuple(item for item in followup_types if item),
        "has_root_focus": primary_type in _ROOT_CHANGE_TYPES,
    }


@dataclass(frozen=True)
class RootCauseTask:
    task_kind: str
    summary: str
    change_type: str
    target_paths: Tuple[str, ...]
    target_functions: Tuple[str, ...]
    evidence_level: str
    source_agent: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


@dataclass(frozen=True)
class RootCauseTaskPayload:
    state: str
    gate_reason: str
    primary_fix: RootCauseTask | None
    followup_tasks: Tuple[RootCauseTask, ...]
    task_mix_suppressed_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "gate_reason": self.gate_reason,
            "primary_fix": None if self.primary_fix is None else self.primary_fix.to_dict(),
            "followup_tasks": [item.to_dict() for item in self.followup_tasks],
            "task_mix_suppressed_count": max(0, int(self.task_mix_suppressed_count or 0)),
        }


def _has_primary_gate(record: DiagnosisRecord, focus: Dict[str, Any]) -> tuple[bool, str]:
    evidence_level = normalize_evidence_level(record.evidence_level)
    if evidence_level not in {"verified", "corroborated", "observed"}:
        return False, "weak_root_cause_evidence"
    if not record.verified_paths:
        return False, "missing_verified_paths"
    if not str(focus.get("primary_change_type") or "").strip():
        return False, "missing_change_type"
    if not bool(focus.get("has_root_focus")):
        return False, "followup_only_lead"
    return True, ""


def build_root_cause_task_payload(resolution: DiagnosisResolution) -> RootCauseTaskPayload:
    lead = resolution.lead_diagnosis
    if lead is None:
        return RootCauseTaskPayload(
            state="verification_needed",
            gate_reason="missing_lead_diagnosis",
            primary_fix=None,
            followup_tasks=(),
            task_mix_suppressed_count=0,
        )

    focus = classify_change_focus(lead.claim)
    gate_ok, gate_reason = _has_primary_gate(lead, focus)

    followups: List[RootCauseTask] = []
    mix_suppressed = len(tuple(focus.get("followup_change_types") or ()))
    for diagnosis in resolution.supporting_diagnoses:
        candidate_focus = classify_change_focus(diagnosis.claim)
        for change_type in tuple(candidate_focus.get("followup_change_types") or ()):
            task_kind = _FOLLOWUP_KIND_BY_CHANGE_TYPE.get(change_type)
            if not task_kind:
                continue
            followups.append(
                RootCauseTask(
                    task_kind=task_kind,
                    summary=diagnosis.claim,
                    change_type=change_type,
                    target_paths=tuple(diagnosis.verified_paths),
                    target_functions=tuple(diagnosis.verified_functions),
                    evidence_level=diagnosis.evidence_level,
                    source_agent=diagnosis.source_agent,
                )
            )
            mix_suppressed += 1

    if not gate_ok:
        return RootCauseTaskPayload(
            state="verification_needed",
            gate_reason=gate_reason,
            primary_fix=None,
            followup_tasks=tuple(followups[:4]),
            task_mix_suppressed_count=max(0, mix_suppressed),
        )

    primary_fix = RootCauseTask(
        task_kind="primary_fix",
        summary=lead.claim,
        change_type=str(focus.get("primary_change_type") or "logic_fix"),
        target_paths=tuple(lead.verified_paths),
        target_functions=tuple(lead.verified_functions),
        evidence_level=lead.evidence_level,
        source_agent=lead.source_agent,
    )
    return RootCauseTaskPayload(
        state="primary_fix_emitted",
        gate_reason="",
        primary_fix=primary_fix,
        followup_tasks=tuple(followups[:4]),
        task_mix_suppressed_count=max(0, mix_suppressed),
    )

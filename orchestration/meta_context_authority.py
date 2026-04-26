"""Autoritativer Kontextvertrag fuer Meta."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

from orchestration.general_decision_kernel import parse_general_decision_kernel
from orchestration.meta_clarity_contract import parse_meta_clarity_contract
from orchestration.meta_interaction_mode import parse_meta_interaction_mode


_STATE_CONTEXT_CLASSES = ("conversation_state", "topic_state")
_EXTERNAL_CONTEXT_CLASSES = (
    "semantic_recall",
    "document_knowledge",
    "preference_profile",
    "assistant_fallback",
)

_CONTEXT_CLASS_BY_SLOT = {
    "current_query": "conversation_state",
    "conversation_state": "conversation_state",
    "recent_user_turn": "conversation_state",
    "recent_assistant_turn": "conversation_state",
    "open_loop": "conversation_state",
    "next_expected_step": "conversation_state",
    "historical_topic_memory": "topic_state",
    "topic_memory": "topic_state",
    "semantic_recall": "semantic_recall",
    "preference_memory": "preference_profile",
    "user_profile": "preference_profile",
    "self_model": "preference_profile",
    "relationships": "preference_profile",
    "document_evidence": "document_knowledge",
    "document_memory": "document_knowledge",
    "document_excerpt": "document_knowledge",
    "file_excerpt": "document_knowledge",
    "source_excerpt": "document_knowledge",
    "source_quote": "document_knowledge",
    "assistant_fallback_context": "assistant_fallback",
}


def _clean_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped or text[:limit]}..."


def _normalize_text_tuple(values: Iterable[Any] | None, *, limit: int = 64) -> Tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values or ():
        cleaned = _clean_text(item, limit=limit)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(cleaned)
    return tuple(result)


def _context_classes_from_slots(values: Iterable[Any] | None) -> Tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values or ():
        slot = _clean_text(item, limit=64).lower()
        if not slot:
            continue
        context_class = _CONTEXT_CLASS_BY_SLOT.get(slot)
        if not context_class or context_class in seen:
            continue
        seen.add(context_class)
        result.append(context_class)
    return tuple(result)


def _merge_text_tuples(*groups: Iterable[Any] | None, limit: int = 64) -> Tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group or ():
            cleaned = _clean_text(item, limit=limit)
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            result.append(cleaned)
    return tuple(result)


def _filter_context_classes(
    values: Iterable[Any] | None,
    *,
    allow: Iterable[str] | None = None,
    forbid: Iterable[str] | None = None,
) -> Tuple[str, ...]:
    allowed = {str(item or "").strip().lower() for item in (allow or ()) if str(item or "").strip()}
    forbidden = {str(item or "").strip().lower() for item in (forbid or ()) if str(item or "").strip()}
    result: list[str] = []
    seen: set[str] = set()
    for item in values or ():
        cleaned = _clean_text(item, limit=64).lower()
        if not cleaned:
            continue
        if allowed and cleaned not in allowed:
            continue
        if cleaned in forbidden or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return tuple(result)


def _filter_context_slots_by_class(
    slots: Iterable[Any] | None,
    *,
    allow: Iterable[str] | None = None,
    forbid: Iterable[str] | None = None,
) -> Tuple[str, ...]:
    allowed = {str(item or "").strip().lower() for item in (allow or ()) if str(item or "").strip()}
    forbidden = {str(item or "").strip().lower() for item in (forbid or ()) if str(item or "").strip()}
    result: list[str] = []
    seen: set[str] = set()
    for item in slots or ():
        slot = _clean_text(item, limit=64)
        if not slot:
            continue
        context_class = classify_meta_context_slot(slot)
        if allowed and context_class not in allowed:
            continue
        if context_class in forbidden:
            continue
        lowered = slot.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(slot)
    return tuple(result)


def _cap_budget(current: int, cap: int) -> int:
    if current < 0:
        return cap
    return min(current, cap)


def classify_meta_context_slot(slot: Any) -> str:
    cleaned = _clean_text(slot, limit=64).lower()
    if not cleaned:
        return "unknown"
    return _CONTEXT_CLASS_BY_SLOT.get(cleaned, "unknown")


def summarize_meta_context_classes(
    bundle: Mapping[str, Any] | None,
) -> Tuple[Tuple[str, ...], Dict[str, int]]:
    payload = dict(bundle or {})
    ordered: list[str] = []
    counts: Dict[str, int] = {}
    for item in (payload.get("context_slots") or []):
        if not isinstance(item, Mapping):
            continue
        evidence_class = _clean_text(item.get("evidence_class"), limit=64).lower()
        if not evidence_class:
            evidence_class = classify_meta_context_slot(item.get("slot"))
        if not evidence_class or evidence_class == "unknown":
            continue
        counts[evidence_class] = counts.get(evidence_class, 0) + 1
        if evidence_class not in ordered:
            ordered.append(evidence_class)
    return tuple(ordered), counts


@dataclass(frozen=True)
class MetaContextAuthority:
    schema_version: int
    authority_chain: Tuple[str, ...]
    primary_objective: str
    frame_kind: str
    task_domain: str
    execution_mode: str
    interaction_mode: str
    interaction_reason: str
    decision_turn_kind: str
    decision_topic_family: str
    decision_evidence_requirement: str
    decision_execution_permission: str
    decision_confidence: float
    decision_answer_ready: bool
    request_kind: str
    direct_answer_required: bool
    allowed_context_classes: Tuple[str, ...]
    forbidden_context_classes: Tuple[str, ...]
    observed_context_classes: Tuple[str, ...]
    context_class_counts: Dict[str, int]
    primary_evidence_class: str
    allowed_context_slots: Tuple[str, ...]
    working_memory_query_mode: str
    working_memory_allowed_sections: Tuple[str, ...]
    working_memory_max_related: int
    working_memory_max_recent: int
    strict_working_memory_gating: bool
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


def parse_meta_context_authority(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    working_related_raw = value.get("working_memory_max_related", -1)
    working_recent_raw = value.get("working_memory_max_recent", -1)
    payload = {
        "schema_version": int(value.get("schema_version") or 1),
        "authority_chain": [
            _clean_text(item, limit=64)
            for item in (value.get("authority_chain") or [])
            if _clean_text(item, limit=64)
        ],
        "primary_objective": _clean_text(value.get("primary_objective"), limit=320),
        "frame_kind": _clean_text(value.get("frame_kind"), limit=64).lower(),
        "task_domain": _clean_text(value.get("task_domain"), limit=64).lower(),
        "execution_mode": _clean_text(value.get("execution_mode"), limit=64).lower(),
        "interaction_mode": _clean_text(value.get("interaction_mode"), limit=32).lower(),
        "interaction_reason": _clean_text(value.get("interaction_reason"), limit=120),
        "decision_turn_kind": _clean_text(value.get("decision_turn_kind"), limit=64).lower(),
        "decision_topic_family": _clean_text(value.get("decision_topic_family"), limit=64).lower(),
        "decision_evidence_requirement": _clean_text(
            value.get("decision_evidence_requirement"), limit=32
        ).lower(),
        "decision_execution_permission": _clean_text(
            value.get("decision_execution_permission"), limit=32
        ).lower(),
        "decision_confidence": round(float(value.get("decision_confidence") or 0.0), 2),
        "decision_answer_ready": bool(value.get("decision_answer_ready")),
        "request_kind": _clean_text(value.get("request_kind"), limit=64).lower(),
        "direct_answer_required": bool(value.get("direct_answer_required")),
        "allowed_context_classes": [
            _clean_text(item, limit=64).lower()
            for item in (value.get("allowed_context_classes") or [])
            if _clean_text(item, limit=64)
        ],
        "forbidden_context_classes": [
            _clean_text(item, limit=64).lower()
            for item in (value.get("forbidden_context_classes") or [])
            if _clean_text(item, limit=64)
        ],
        "observed_context_classes": [
            _clean_text(item, limit=64).lower()
            for item in (value.get("observed_context_classes") or [])
            if _clean_text(item, limit=64)
        ],
        "context_class_counts": {
            _clean_text(key, limit=64).lower(): max(0, int(count))
            for key, count in dict(value.get("context_class_counts") or {}).items()
            if _clean_text(key, limit=64)
        },
        "primary_evidence_class": _clean_text(value.get("primary_evidence_class"), limit=64).lower(),
        "allowed_context_slots": [
            _clean_text(item, limit=64)
            for item in (value.get("allowed_context_slots") or [])
            if _clean_text(item, limit=64)
        ],
        "working_memory_query_mode": _clean_text(value.get("working_memory_query_mode"), limit=32).lower(),
        "working_memory_allowed_sections": [
            _clean_text(item, limit=64)
            for item in (value.get("working_memory_allowed_sections") or [])
            if _clean_text(item, limit=64)
        ],
        "working_memory_max_related": max(
            -1,
            -1 if working_related_raw in (None, "") else int(working_related_raw),
        ),
        "working_memory_max_recent": max(
            -1,
            -1 if working_recent_raw in (None, "") else int(working_recent_raw),
        ),
        "strict_working_memory_gating": bool(value.get("strict_working_memory_gating")),
        "rationale": _clean_text(value.get("rationale"), limit=220),
    }
    return {key: item for key, item in payload.items() if item not in ("", [], None)}


def build_meta_context_authority(
    *,
    meta_request_frame: Mapping[str, Any] | None,
    meta_interaction_mode: Mapping[str, Any] | None,
    meta_clarity_contract: Mapping[str, Any] | None,
    meta_context_bundle: Mapping[str, Any] | None = None,
    general_decision_kernel: Mapping[str, Any] | None = None,
) -> MetaContextAuthority:
    frame = dict(meta_request_frame or {})
    mode = parse_meta_interaction_mode(meta_interaction_mode or {})
    clarity = parse_meta_clarity_contract(meta_clarity_contract or {})
    bundle = dict(meta_context_bundle or {})
    kernel = parse_general_decision_kernel(general_decision_kernel or {})

    allowed_context_slots = _normalize_text_tuple(clarity.get("allowed_context_slots") or ())
    if not allowed_context_slots:
        allowed_context_slots = _normalize_text_tuple(
            str(item.get("slot") or "").strip()
            for item in (bundle.get("context_slots") or [])
            if isinstance(item, Mapping) and str(item.get("slot") or "").strip()
        )

    forbidden_context_slots = _normalize_text_tuple(clarity.get("forbidden_context_slots") or ())
    allowed_context_classes = _context_classes_from_slots(allowed_context_slots)
    forbidden_context_classes = _context_classes_from_slots(forbidden_context_slots)
    observed_context_classes, context_class_counts = summarize_meta_context_classes(bundle)

    allowed_sections = _normalize_text_tuple(clarity.get("allowed_working_memory_sections") or ())
    working_related_raw = clarity.get("max_related_memories", -1)
    working_recent_raw = clarity.get("max_recent_events", -1)
    working_memory_max_related = -1 if working_related_raw in (None, "") else int(working_related_raw)
    working_memory_max_recent = -1 if working_recent_raw in (None, "") else int(working_recent_raw)
    strict_working_memory_gating = bool(
        allowed_sections
        or allowed_context_slots
        or forbidden_context_slots
        or clarity.get("direct_answer_required")
    )

    request_kind = _clean_text(clarity.get("request_kind"), limit=64).lower()
    task_domain = _clean_text(frame.get("task_domain"), limit=64).lower()
    interaction_mode_name = _clean_text(mode.get("mode"), limit=32).lower()
    working_query_mode = "authority_bound"
    if interaction_mode_name == "think_partner":
        working_query_mode = "objective_only"
    elif task_domain in {"docs_status", "setup_build"}:
        working_query_mode = "evidence_bound"

    decision_turn_kind = _clean_text(kernel.get("turn_kind"), limit=64).lower()
    decision_topic_family = _clean_text(kernel.get("topic_family"), limit=64).lower()
    decision_evidence_requirement = _clean_text(kernel.get("evidence_requirement"), limit=32).lower()
    decision_execution_permission = _clean_text(kernel.get("execution_permission"), limit=32).lower()
    decision_confidence = round(float(kernel.get("confidence") or 0.0), 2)
    decision_answer_ready = bool(kernel.get("answer_ready"))
    kernel_authoritative = decision_confidence >= 0.7 and bool(
        decision_turn_kind or decision_evidence_requirement or decision_execution_permission
    )
    if kernel_authoritative:
        if decision_execution_permission == "forbidden" and decision_evidence_requirement in {
            "none",
            "state_bound",
        }:
            allowed_context_classes = _filter_context_classes(
                allowed_context_classes or _STATE_CONTEXT_CLASSES,
                allow=_STATE_CONTEXT_CLASSES,
            )
            allowed_context_slots = _filter_context_slots_by_class(
                allowed_context_slots,
                allow=_STATE_CONTEXT_CLASSES,
            )
            forbidden_context_classes = _merge_text_tuples(
                forbidden_context_classes,
                _EXTERNAL_CONTEXT_CLASSES,
            )
            working_query_mode = "objective_only"
            working_memory_max_related = _cap_budget(working_memory_max_related, 0)
            working_memory_max_recent = _cap_budget(working_memory_max_recent, 8)
            strict_working_memory_gating = True
        elif decision_evidence_requirement in {"bounded", "research"} or decision_execution_permission == "bounded":
            working_query_mode = "evidence_bound"
            if decision_evidence_requirement == "research":
                working_memory_max_related = _cap_budget(working_memory_max_related, 2)
                working_memory_max_recent = _cap_budget(working_memory_max_recent, 8)
            else:
                working_memory_max_related = _cap_budget(working_memory_max_related, 1)
                working_memory_max_recent = _cap_budget(working_memory_max_recent, 6)
            forbidden_context_classes = _merge_text_tuples(
                forbidden_context_classes,
                ("assistant_fallback",),
            )
            strict_working_memory_gating = True

    rationale_parts = [
        f"gdk:{decision_turn_kind or 'unknown'}/{decision_execution_permission or 'unknown'}",
        f"frame:{_clean_text(frame.get('frame_kind'), limit=64).lower() or 'unknown'}",
        f"domain:{task_domain or 'unknown'}",
        f"mode:{interaction_mode_name or 'unknown'}",
        f"request_kind:{request_kind or 'unknown'}",
    ]

    primary_evidence_class = observed_context_classes[0] if observed_context_classes else ""

    return MetaContextAuthority(
        schema_version=1,
        authority_chain=(
            "general_decision_kernel",
            "meta_request_frame",
            "meta_interaction_mode",
            "meta_clarity_contract",
            "meta_context_bundle",
            "working_memory",
        ),
        primary_objective=_clean_text(
            frame.get("primary_objective") or clarity.get("primary_objective"),
            limit=320,
        ),
        frame_kind=_clean_text(frame.get("frame_kind"), limit=64).lower(),
        task_domain=task_domain,
        execution_mode=_clean_text(frame.get("execution_mode"), limit=64).lower(),
        interaction_mode=interaction_mode_name,
        interaction_reason=_clean_text(mode.get("mode_reason"), limit=120),
        decision_turn_kind=decision_turn_kind,
        decision_topic_family=decision_topic_family,
        decision_evidence_requirement=decision_evidence_requirement,
        decision_execution_permission=decision_execution_permission,
        decision_confidence=decision_confidence,
        decision_answer_ready=decision_answer_ready,
        request_kind=request_kind,
        direct_answer_required=bool(clarity.get("direct_answer_required")),
        allowed_context_classes=allowed_context_classes,
        forbidden_context_classes=forbidden_context_classes,
        observed_context_classes=observed_context_classes,
        context_class_counts=context_class_counts,
        primary_evidence_class=primary_evidence_class,
        allowed_context_slots=allowed_context_slots,
        working_memory_query_mode=working_query_mode,
        working_memory_allowed_sections=allowed_sections,
        working_memory_max_related=working_memory_max_related,
        working_memory_max_recent=working_memory_max_recent,
        strict_working_memory_gating=strict_working_memory_gating,
        rationale=" | ".join(part for part in rationale_parts if part),
    )

"""Autoritativer Kontextvertrag fuer Meta."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

from orchestration.meta_clarity_contract import parse_meta_clarity_contract
from orchestration.meta_interaction_mode import parse_meta_interaction_mode


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
) -> MetaContextAuthority:
    frame = dict(meta_request_frame or {})
    mode = parse_meta_interaction_mode(meta_interaction_mode or {})
    clarity = parse_meta_clarity_contract(meta_clarity_contract or {})
    bundle = dict(meta_context_bundle or {})

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
    rationale_parts = [
        f"frame:{_clean_text(frame.get('frame_kind'), limit=64).lower() or 'unknown'}",
        f"domain:{task_domain or 'unknown'}",
        f"mode:{interaction_mode_name or 'unknown'}",
        f"request_kind:{request_kind or 'unknown'}",
    ]

    working_query_mode = "authority_bound"
    if interaction_mode_name == "think_partner":
        working_query_mode = "objective_only"
    elif task_domain in {"docs_status", "setup_build"}:
        working_query_mode = "evidence_bound"

    primary_evidence_class = observed_context_classes[0] if observed_context_classes else ""

    return MetaContextAuthority(
        schema_version=1,
        authority_chain=(
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

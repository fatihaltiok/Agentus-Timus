from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


_SCHEMA_VERSION = 1
_MAX_TEXT_LEN = 280
_MAX_LIST_ITEMS = 8
_MAX_SOURCE_ITEMS = 12
_ALLOWED_TURN_TYPE_HINTS = {
    "",
    "new_task",
    "followup",
    "clarification",
    "correction",
    "preference_update",
    "behavior_instruction",
    "complaint_about_last_answer",
    "approval_response",
    "auth_response",
    "result_extraction",
    "handover_resume",
}


def _normalize_text(value: Any, *, limit: int = _MAX_TEXT_LEN) -> str:
    return str(value or "").strip()[:limit]


def _normalize_text_list(
    values: Any,
    *,
    limit_items: int = _MAX_LIST_ITEMS,
    limit_chars: int = _MAX_TEXT_LEN,
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _normalize_text(item, limit=limit_chars)
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
        if len(normalized) >= limit_items:
            break
    return tuple(normalized)


def _normalize_state_source(values: Any) -> tuple[str, ...]:
    return _normalize_text_list(values, limit_items=_MAX_SOURCE_ITEMS, limit_chars=64)


def _normalize_confidence(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(numeric, 1.0))


def _normalize_turn_type_hint(value: Any) -> str:
    hint = _normalize_text(value, limit=64).lower()
    return hint if hint in _ALLOWED_TURN_TYPE_HINTS else ""


def _append_source(sources: tuple[str, ...], value: str) -> tuple[str, ...]:
    item = _normalize_text(value, limit=64)
    if not item:
        return sources
    if item in sources:
        return sources
    merged = [*sources, item]
    return tuple(merged[:_MAX_SOURCE_ITEMS])


@dataclass(frozen=True, slots=True)
class ConversationState:
    schema_version: int
    session_id: str
    active_topic: str
    active_goal: str
    open_loop: str
    next_expected_step: str
    turn_type_hint: str
    preferences: tuple[str, ...]
    recent_corrections: tuple[str, ...]
    constraints: tuple[str, ...]
    open_questions: tuple[str, ...]
    state_source: tuple[str, ...]
    topic_confidence: float
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "active_topic": self.active_topic,
            "active_goal": self.active_goal,
            "open_loop": self.open_loop,
            "next_expected_step": self.next_expected_step,
            "turn_type_hint": self.turn_type_hint,
            "preferences": list(self.preferences),
            "recent_corrections": list(self.recent_corrections),
            "constraints": list(self.constraints),
            "open_questions": list(self.open_questions),
            "state_source": list(self.state_source),
            "topic_confidence": self.topic_confidence,
            "updated_at": self.updated_at,
        }


def normalize_conversation_state(
    payload: Mapping[str, Any] | None,
    *,
    session_id: str,
    last_updated: str = "",
    pending_followup_prompt: str = "",
) -> ConversationState:
    raw = payload if isinstance(payload, Mapping) else {}
    normalized_session_id = _normalize_text(session_id, limit=120) or "default"
    prompt = _normalize_text(pending_followup_prompt)
    state_source = _normalize_state_source(raw.get("state_source"))

    open_loop = _normalize_text(raw.get("open_loop"))
    next_expected_step = _normalize_text(raw.get("next_expected_step"))

    if prompt:
        if not open_loop:
            open_loop = prompt
        if not next_expected_step:
            next_expected_step = prompt
        state_source = _append_source(state_source, "pending_followup_prompt")

    return ConversationState(
        schema_version=_SCHEMA_VERSION,
        session_id=normalized_session_id,
        active_topic=_normalize_text(raw.get("active_topic")),
        active_goal=_normalize_text(raw.get("active_goal")),
        open_loop=open_loop,
        next_expected_step=next_expected_step,
        turn_type_hint=_normalize_turn_type_hint(raw.get("turn_type_hint")),
        preferences=_normalize_text_list(raw.get("preferences")),
        recent_corrections=_normalize_text_list(raw.get("recent_corrections")),
        constraints=_normalize_text_list(raw.get("constraints")),
        open_questions=_normalize_text_list(raw.get("open_questions")),
        state_source=state_source,
        topic_confidence=_normalize_confidence(raw.get("topic_confidence")),
        updated_at=_normalize_text(raw.get("updated_at") or last_updated, limit=64),
    )


def touch_conversation_state(
    payload: ConversationState | Mapping[str, Any] | None,
    *,
    session_id: str,
    updated_at: str,
    pending_followup_prompt: str = "",
) -> ConversationState:
    current = normalize_conversation_state(
        payload.to_dict() if isinstance(payload, ConversationState) else payload,
        session_id=session_id,
        last_updated=updated_at,
        pending_followup_prompt=pending_followup_prompt,
    )
    return ConversationState(
        schema_version=current.schema_version,
        session_id=current.session_id,
        active_topic=current.active_topic,
        active_goal=current.active_goal,
        open_loop=current.open_loop,
        next_expected_step=current.next_expected_step,
        turn_type_hint=current.turn_type_hint,
        preferences=current.preferences,
        recent_corrections=current.recent_corrections,
        constraints=current.constraints,
        open_questions=current.open_questions,
        state_source=current.state_source,
        topic_confidence=current.topic_confidence,
        updated_at=_normalize_text(updated_at, limit=64),
    )


def apply_pending_followup_prompt(
    payload: ConversationState | Mapping[str, Any] | None,
    *,
    session_id: str,
    prompt: str,
    updated_at: str = "",
) -> ConversationState:
    current = normalize_conversation_state(
        payload.to_dict() if isinstance(payload, ConversationState) else payload,
        session_id=session_id,
        last_updated=updated_at,
    )
    cleaned = _normalize_text(prompt)
    sources = tuple(item for item in current.state_source if item != "pending_followup_prompt")
    open_loop = current.open_loop
    next_expected_step = current.next_expected_step

    if cleaned:
        open_loop = cleaned
        next_expected_step = cleaned
        sources = _append_source(sources, "pending_followup_prompt")
    elif "pending_followup_prompt" in current.state_source and current.open_loop == current.next_expected_step:
        open_loop = ""
        next_expected_step = ""

    return ConversationState(
        schema_version=current.schema_version,
        session_id=current.session_id,
        active_topic=current.active_topic,
        active_goal=current.active_goal,
        open_loop=open_loop,
        next_expected_step=next_expected_step,
        turn_type_hint=current.turn_type_hint,
        preferences=current.preferences,
        recent_corrections=current.recent_corrections,
        constraints=current.constraints,
        open_questions=current.open_questions,
        state_source=sources,
        topic_confidence=current.topic_confidence,
        updated_at=_normalize_text(updated_at or current.updated_at, limit=64),
    )


def conversation_state_to_dict(
    payload: ConversationState | Mapping[str, Any] | None,
    *,
    session_id: str,
    last_updated: str = "",
    pending_followup_prompt: str = "",
) -> dict[str, Any]:
    state = normalize_conversation_state(
        payload.to_dict() if isinstance(payload, ConversationState) else payload,
        session_id=session_id,
        last_updated=last_updated,
        pending_followup_prompt=pending_followup_prompt,
    )
    return state.to_dict()


def apply_turn_interpretation(
    payload: ConversationState | Mapping[str, Any] | None,
    *,
    session_id: str,
    dominant_turn_type: str,
    response_mode: str,
    state_effects: Mapping[str, Any] | None,
    effective_query: str,
    active_topic: str = "",
    active_goal: str = "",
    dialog_constraints: Iterable[str] | None = None,
    next_step: str = "",
    confidence: float | int = 0.0,
    updated_at: str = "",
) -> ConversationState:
    current = normalize_conversation_state(
        payload.to_dict() if isinstance(payload, ConversationState) else payload,
        session_id=session_id,
        last_updated=updated_at,
    )
    effects = dict(state_effects or {})
    cleaned_query = _normalize_text(effective_query)
    cleaned_topic = _normalize_text(active_topic)
    cleaned_goal = _normalize_text(active_goal)
    cleaned_next_step = _normalize_text(next_step)
    merged_constraints = _normalize_text_list(
        [*current.constraints, *(dialog_constraints or ())],
        limit_items=_MAX_LIST_ITEMS,
    )
    preferences = list(current.preferences)
    corrections = list(current.recent_corrections)
    sources = _append_source(current.state_source, "turn_understanding")
    if cleaned_topic:
        sources = _append_source(sources, "meta_dialog_state")

    next_expected_step = current.next_expected_step
    open_loop = current.open_loop
    active_topic_value = current.active_topic
    active_goal_value = current.active_goal

    if effects.get("shift_active_topic"):
        if cleaned_topic:
            active_topic_value = cleaned_topic
        if cleaned_goal:
            active_goal_value = cleaned_goal
    elif effects.get("keep_active_topic"):
        if not active_topic_value and cleaned_topic:
            active_topic_value = cleaned_topic
        if not active_goal_value and cleaned_goal:
            active_goal_value = cleaned_goal
    else:
        if not active_topic_value and cleaned_topic:
            active_topic_value = cleaned_topic
        if not active_goal_value and cleaned_goal:
            active_goal_value = cleaned_goal

    if effects.get("update_preferences") and cleaned_query:
        preferences = list(_normalize_text_list([*preferences, cleaned_query], limit_items=_MAX_LIST_ITEMS))
    if effects.get("update_recent_corrections") and cleaned_query:
        corrections = list(_normalize_text_list([*corrections, cleaned_query], limit_items=_MAX_LIST_ITEMS))
    if effects.get("set_open_loop"):
        open_loop = cleaned_next_step or cleaned_goal or cleaned_query
    if effects.get("clear_open_loop"):
        open_loop = ""
        next_expected_step = ""
    if effects.get("set_next_expected_step"):
        next_expected_step = cleaned_next_step or cleaned_query
    elif response_mode == "resume_open_loop" and not next_expected_step and current.open_loop:
        next_expected_step = current.open_loop

    return ConversationState(
        schema_version=current.schema_version,
        session_id=current.session_id,
        active_topic=active_topic_value,
        active_goal=active_goal_value,
        open_loop=open_loop,
        next_expected_step=next_expected_step,
        turn_type_hint=_normalize_turn_type_hint(dominant_turn_type),
        preferences=tuple(preferences),
        recent_corrections=tuple(corrections),
        constraints=merged_constraints,
        open_questions=current.open_questions,
        state_source=sources,
        topic_confidence=max(current.topic_confidence, _normalize_confidence(confidence)),
        updated_at=_normalize_text(updated_at or current.updated_at, limit=64),
    )

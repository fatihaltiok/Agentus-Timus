from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping


_SCHEMA_VERSION = 1
_PLAN_STATE_SCHEMA_VERSION = 1
_MAX_TEXT_LEN = 280
_MAX_LIST_ITEMS = 8
_MAX_SOURCE_ITEMS = 12
_MAX_PLAN_BLOCKERS = 6
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
_ALLOWED_PLAN_MODES = {
    "",
    "direct_response",
    "lightweight_lookup",
    "plan_only",
    "multi_step_execution",
}
_ALLOWED_PLAN_STATUSES = {
    "",
    "active",
    "blocked",
    "completed",
}
_TOPIC_STOPWORDS = {
    "aber",
    "als",
    "auch",
    "bei",
    "das",
    "dass",
    "dem",
    "den",
    "der",
    "des",
    "die",
    "ein",
    "eine",
    "einer",
    "eines",
    "einen",
    "für",
    "fuer",
    "hat",
    "hier",
    "ich",
    "ist",
    "jetzt",
    "lass",
    "lasst",
    "letzte",
    "mehr",
    "mit",
    "nach",
    "noch",
    "oder",
    "reden",
    "schon",
    "soll",
    "sowie",
    "the",
    "uber",
    "ueber",
    "und",
    "uns",
    "von",
    "was",
    "wie",
    "wir",
    "zu",
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


def _normalize_step_count(value: Any) -> int:
    try:
        return max(0, min(int(value), 32))
    except (TypeError, ValueError):
        return 0


def _normalize_plan_mode(value: Any) -> str:
    mode = _normalize_text(value, limit=48).lower()
    return mode if mode in _ALLOWED_PLAN_MODES else ""


def _normalize_plan_status(value: Any, *, blocked_by: tuple[str, ...]) -> str:
    status = _normalize_text(value, limit=32).lower()
    if status in _ALLOWED_PLAN_STATUSES and status:
        return status
    return "blocked" if blocked_by else "active"


def _normalize_blocked_by(values: Any) -> tuple[str, ...]:
    return _normalize_text_list(values, limit_items=_MAX_PLAN_BLOCKERS, limit_chars=120)


def _resolve_plan_step(steps: Any, step_id: str) -> Mapping[str, Any]:
    if not step_id or not isinstance(steps, list):
        return {}
    for raw_step in steps:
        if not isinstance(raw_step, Mapping):
            continue
        if _normalize_text(raw_step.get("id"), limit=64) == step_id:
            return raw_step
    return {}


def _topic_terms(text: str) -> set[str]:
    normalized = str(text or "").lower()
    return {
        token.strip("_-")
        for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß_-]+", normalized)
        if len(token.strip("_-")) >= 3 and token.strip("_-") not in _TOPIC_STOPWORDS
    }


def _topic_overlap(left: str, right: str) -> int:
    return len(_topic_terms(left).intersection(_topic_terms(right)))


def _looks_like_question(text: str) -> bool:
    cleaned = _normalize_text(text)
    lowered = cleaned.lower()
    if not cleaned:
        return False
    if "?" in cleaned:
        return True
    return bool(re.search(r"\b(wie|was|welche|welcher|welches|warum|wieso|ob|soll ich|magst du|willst du)\b", lowered))


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = _normalize_text(value, limit=80)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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
    active_plan: ConversationPlanState | None
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
            "active_plan": self.active_plan.to_dict() if self.active_plan else {},
            "state_source": list(self.state_source),
            "topic_confidence": self.topic_confidence,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class ConversationPlanState:
    schema_version: int
    plan_id: str
    plan_mode: str
    goal: str
    goal_satisfaction_mode: str
    step_count: int
    next_step_id: str
    next_step_title: str
    next_step_agent: str
    last_completed_step_id: str
    last_completed_step_title: str
    blocked_by: tuple[str, ...]
    status: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "plan_mode": self.plan_mode,
            "goal": self.goal,
            "goal_satisfaction_mode": self.goal_satisfaction_mode,
            "step_count": self.step_count,
            "next_step_id": self.next_step_id,
            "next_step_title": self.next_step_title,
            "next_step_agent": self.next_step_agent,
            "last_completed_step_id": self.last_completed_step_id,
            "last_completed_step_title": self.last_completed_step_title,
            "blocked_by": list(self.blocked_by),
            "status": self.status,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class TopicStateTransition:
    previous_topic: str
    next_topic: str
    previous_goal: str
    next_goal: str
    previous_open_loop: str
    next_open_loop: str
    topic_shift_detected: bool
    active_goal_changed: bool
    open_loop_state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_topic": self.previous_topic,
            "next_topic": self.next_topic,
            "previous_goal": self.previous_goal,
            "next_goal": self.next_goal,
            "previous_open_loop": self.previous_open_loop,
            "next_open_loop": self.next_open_loop,
            "topic_shift_detected": self.topic_shift_detected,
            "active_goal_changed": self.active_goal_changed,
            "open_loop_state": self.open_loop_state,
        }


def normalize_conversation_plan_state(
    payload: ConversationPlanState | Mapping[str, Any] | None,
    *,
    updated_at: str = "",
    previous: ConversationPlanState | Mapping[str, Any] | None = None,
) -> ConversationPlanState | None:
    raw = payload.to_dict() if isinstance(payload, ConversationPlanState) else dict(payload or {})
    if not raw:
        return None

    previous_plan = (
        previous
        if isinstance(previous, ConversationPlanState)
        else normalize_conversation_plan_state(previous, updated_at=updated_at)
        if isinstance(previous, Mapping)
        else None
    )
    plan_id = _normalize_text(raw.get("plan_id"), limit=80)
    plan_mode = _normalize_plan_mode(raw.get("plan_mode"))
    goal = _normalize_text(raw.get("goal"))
    goal_satisfaction_mode = _normalize_text(raw.get("goal_satisfaction_mode"), limit=64)
    steps = raw.get("steps")
    step_count = _normalize_step_count(raw.get("step_count") if raw.get("step_count") is not None else len(steps or []))
    next_step_id = _normalize_text(raw.get("next_step_id"), limit=64)
    next_step = _resolve_plan_step(steps, next_step_id)
    next_step_title = _normalize_text(raw.get("next_step_title") or next_step.get("title"))
    next_step_agent = _normalize_text(raw.get("next_step_agent") or next_step.get("assigned_agent"), limit=64)
    last_completed_step_id = _normalize_text(raw.get("last_completed_step_id"), limit=64)
    last_completed_step_title = _normalize_text(raw.get("last_completed_step_title"))
    blocked_by = _normalize_blocked_by(raw.get("blocked_by"))

    if (
        previous_plan
        and plan_id
        and plan_id == previous_plan.plan_id
        and previous_plan.next_step_id
        and next_step_id
        and next_step_id != previous_plan.next_step_id
        and not last_completed_step_id
    ):
        last_completed_step_id = previous_plan.next_step_id
        last_completed_step_title = previous_plan.next_step_title

    if not next_step_title and goal and step_count <= 1:
        next_step_title = goal

    if not any(
        (
            plan_id,
            goal,
            next_step_id,
            next_step_title,
            last_completed_step_id,
            blocked_by,
            step_count,
        )
    ):
        return None

    return ConversationPlanState(
        schema_version=_PLAN_STATE_SCHEMA_VERSION,
        plan_id=plan_id,
        plan_mode=plan_mode,
        goal=goal,
        goal_satisfaction_mode=goal_satisfaction_mode,
        step_count=step_count,
        next_step_id=next_step_id,
        next_step_title=next_step_title,
        next_step_agent=next_step_agent,
        last_completed_step_id=last_completed_step_id,
        last_completed_step_title=last_completed_step_title,
        blocked_by=blocked_by,
        status=_normalize_plan_status(raw.get("status"), blocked_by=blocked_by),
        updated_at=_normalize_text(updated_at or raw.get("updated_at"), limit=64),
    )


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
    active_plan = normalize_conversation_plan_state(
        raw.get("active_plan"),
        updated_at=last_updated or raw.get("updated_at") or "",
    )

    open_loop = _normalize_text(raw.get("open_loop"))
    next_expected_step = _normalize_text(raw.get("next_expected_step"))

    if active_plan:
        if not next_expected_step:
            next_expected_step = active_plan.next_step_title or active_plan.goal
        if not open_loop:
            open_loop = active_plan.next_step_title or active_plan.goal
        state_source = _append_source(state_source, "active_plan")

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
        active_plan=active_plan,
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
        active_plan=current.active_plan,
        state_source=current.state_source,
        topic_confidence=current.topic_confidence,
        updated_at=_normalize_text(updated_at, limit=64),
    )


def decay_conversation_state(
    payload: ConversationState | Mapping[str, Any] | None,
    *,
    session_id: str,
    last_updated: str = "",
    pending_followup_prompt: str = "",
    now: str = "",
) -> tuple[ConversationState, dict[str, Any]]:
    current = normalize_conversation_state(
        payload.to_dict() if isinstance(payload, ConversationState) else payload,
        session_id=session_id,
        last_updated=last_updated,
        pending_followup_prompt=pending_followup_prompt,
    )
    if not now:
        return current, {"applied": False, "reasons": [], "age_hours": 0.0}

    updated_dt = _parse_iso_datetime(current.updated_at)
    now_dt = _parse_iso_datetime(now)
    if updated_dt is None or now_dt is None:
        return current, {"applied": False, "reasons": [], "age_hours": 0.0}

    age_hours = max(0.0, (now_dt - updated_dt).total_seconds() / 3600.0)
    reasons: list[str] = []
    open_loop = current.open_loop
    next_expected_step = current.next_expected_step
    open_questions = list(current.open_questions)
    active_plan = current.active_plan
    topic_confidence = current.topic_confidence
    sources = tuple(item for item in current.state_source if item != "state_decay")

    if age_hours >= 72.0 and open_loop:
        open_loop = ""
        next_expected_step = ""
        reasons.append("stale_open_loop")
    if age_hours >= 72.0 and active_plan:
        active_plan = None
        reasons.append("stale_active_plan")
    if age_hours >= 72.0 and open_questions:
        open_questions = []
        reasons.append("stale_open_questions")
    if age_hours >= 168.0 and topic_confidence > 0.25:
        topic_confidence = max(0.25, round(topic_confidence * 0.6, 2))
        reasons.append("topic_confidence_decay")

    if not reasons:
        return current, {"applied": False, "reasons": [], "age_hours": round(age_hours, 2)}

    sources = _append_source(sources, "state_decay")
    decayed = ConversationState(
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
        open_questions=tuple(open_questions),
        active_plan=active_plan,
        state_source=sources,
        topic_confidence=topic_confidence,
        updated_at=current.updated_at,
    )
    return decayed, {"applied": True, "reasons": reasons, "age_hours": round(age_hours, 2)}


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
        active_plan=current.active_plan,
        state_source=sources,
        topic_confidence=current.topic_confidence,
        updated_at=_normalize_text(updated_at or current.updated_at, limit=64),
    )


def apply_runtime_plan_state(
    payload: ConversationState | Mapping[str, Any] | None,
    *,
    session_id: str,
    active_plan: Mapping[str, Any] | None,
    updated_at: str = "",
) -> ConversationState:
    current = normalize_conversation_state(
        payload.to_dict() if isinstance(payload, ConversationState) else payload,
        session_id=session_id,
        last_updated=updated_at,
    )
    incoming_plan = normalize_conversation_plan_state(
        active_plan,
        updated_at=updated_at or current.updated_at,
        previous=current.active_plan,
    )
    sources = _append_source(tuple(item for item in current.state_source if item != "state_decay"), "runtime_plan")

    if incoming_plan is None:
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
            active_plan=current.active_plan,
            state_source=sources,
            topic_confidence=current.topic_confidence,
            updated_at=_normalize_text(updated_at or current.updated_at, limit=64),
        )

    if incoming_plan.status == "completed":
        return ConversationState(
            schema_version=current.schema_version,
            session_id=current.session_id,
            active_topic=current.active_topic,
            active_goal=incoming_plan.goal or current.active_goal,
            open_loop="",
            next_expected_step="",
            turn_type_hint=current.turn_type_hint,
            preferences=current.preferences,
            recent_corrections=current.recent_corrections,
            constraints=current.constraints,
            open_questions=(),
            active_plan=None,
            state_source=sources,
            topic_confidence=current.topic_confidence,
            updated_at=_normalize_text(updated_at or current.updated_at, limit=64),
        )

    next_step = incoming_plan.next_step_title or incoming_plan.goal or current.next_expected_step
    return ConversationState(
        schema_version=current.schema_version,
        session_id=current.session_id,
        active_topic=current.active_topic,
        active_goal=incoming_plan.goal or current.active_goal,
        open_loop=next_step,
        next_expected_step=next_step,
        turn_type_hint=current.turn_type_hint,
        preferences=current.preferences,
        recent_corrections=current.recent_corrections,
        constraints=current.constraints,
        open_questions=current.open_questions,
        active_plan=incoming_plan,
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
    decay_now: str = "",
) -> dict[str, Any]:
    state, _ = decay_conversation_state(
        payload.to_dict() if isinstance(payload, ConversationState) else payload,
        session_id=session_id,
        last_updated=last_updated,
        pending_followup_prompt=pending_followup_prompt,
        now=decay_now,
    )
    return state.to_dict()


def derive_topic_state_transition(
    payload: ConversationState | Mapping[str, Any] | None,
    *,
    session_id: str,
    dominant_turn_type: str,
    response_mode: str,
    state_effects: Mapping[str, Any] | None,
    effective_query: str,
    active_topic: str = "",
    active_goal: str = "",
    next_step: str = "",
) -> TopicStateTransition:
    current = normalize_conversation_state(
        payload.to_dict() if isinstance(payload, ConversationState) else payload,
        session_id=session_id,
    )
    effects = dict(state_effects or {})
    cleaned_query = _normalize_text(effective_query)
    cleaned_topic = _normalize_text(active_topic)
    cleaned_goal = _normalize_text(active_goal)
    cleaned_next_step = _normalize_text(next_step)

    next_topic_candidate = cleaned_topic
    if (
        effects.get("shift_active_topic")
        and cleaned_query
        and current.active_topic
        and (
            not cleaned_topic
            or cleaned_topic == current.active_topic
            or _topic_overlap(cleaned_topic, current.active_topic) > _topic_overlap(cleaned_query, current.active_topic)
        )
        and _topic_overlap(cleaned_query, current.active_topic) == 0
    ):
        next_topic_candidate = cleaned_query
    next_goal_candidate = cleaned_goal
    if (
        effects.get("shift_active_topic")
        and cleaned_query
        and current.active_goal
        and (
            not cleaned_goal
            or cleaned_goal == current.active_goal
            or _topic_overlap(cleaned_goal, current.active_goal) > _topic_overlap(cleaned_query, current.active_goal)
        )
        and _topic_overlap(cleaned_query, current.active_goal) == 0
    ):
        next_goal_candidate = cleaned_query

    if effects.get("shift_active_topic"):
        next_topic = next_topic_candidate or cleaned_query or current.active_topic
        next_goal = next_goal_candidate or cleaned_query or current.active_goal
    elif effects.get("keep_active_topic"):
        next_topic = current.active_topic or cleaned_topic
        next_goal = current.active_goal or cleaned_goal
    else:
        next_topic = current.active_topic or cleaned_topic
        next_goal = current.active_goal or cleaned_goal

    next_open_loop = current.open_loop
    if effects.get("set_open_loop"):
        next_open_loop = cleaned_next_step or cleaned_goal or cleaned_query
    elif effects.get("clear_open_loop"):
        next_open_loop = ""
    elif response_mode == "resume_open_loop" and current.open_loop:
        next_open_loop = current.open_loop

    topic_shift_detected = False
    if current.active_topic and next_topic and current.active_topic != next_topic:
        topic_shift_detected = _topic_overlap(current.active_topic, next_topic) == 0
    if topic_shift_detected:
        next_open_loop = ""

    active_goal_changed = bool(current.active_goal and next_goal and current.active_goal != next_goal)

    open_loop_state = "unchanged"
    if topic_shift_detected and current.open_loop:
        open_loop_state = "cleared"
    elif effects.get("clear_open_loop"):
        open_loop_state = "cleared"
    elif effects.get("set_open_loop") or effects.get("set_next_expected_step"):
        open_loop_state = "set"
    elif response_mode == "resume_open_loop" and current.open_loop:
        open_loop_state = "resumed"
    elif not current.open_loop and next_open_loop:
        open_loop_state = "set"

    return TopicStateTransition(
        previous_topic=current.active_topic,
        next_topic=next_topic,
        previous_goal=current.active_goal,
        next_goal=next_goal,
        previous_open_loop=current.open_loop,
        next_open_loop=next_open_loop,
        topic_shift_detected=topic_shift_detected,
        active_goal_changed=active_goal_changed,
        open_loop_state=open_loop_state,
    )


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
    active_plan: Mapping[str, Any] | None = None,
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
    open_questions = list(current.open_questions)
    current_plan = normalize_conversation_plan_state(current.active_plan, updated_at=current.updated_at)
    incoming_plan = normalize_conversation_plan_state(
        active_plan,
        updated_at=updated_at or current.updated_at,
        previous=current_plan,
    )
    active_plan_state = current_plan
    sources = _append_source(current.state_source, "turn_understanding")
    if cleaned_topic:
        sources = _append_source(sources, "meta_dialog_state")
    transition = derive_topic_state_transition(
        current,
        session_id=session_id,
        dominant_turn_type=dominant_turn_type,
        response_mode=response_mode,
        state_effects=effects,
        effective_query=cleaned_query,
        active_topic=cleaned_topic,
        active_goal=cleaned_goal,
        next_step=cleaned_next_step,
    )

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
        elif not active_topic_value and cleaned_query:
            active_topic_value = cleaned_query
        if not active_goal_value and cleaned_goal:
            active_goal_value = cleaned_goal
        elif not active_goal_value and cleaned_query:
            active_goal_value = cleaned_query
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

    if transition.topic_shift_detected:
        active_topic_value = transition.next_topic or cleaned_query or active_topic_value
        active_goal_value = transition.next_goal or cleaned_query or active_goal_value
        open_loop = ""
        next_expected_step = ""
        active_plan_state = None
        open_questions = []
        sources = _append_source(sources, "topic_shift")

    if incoming_plan and not transition.topic_shift_detected:
        active_plan_state = incoming_plan
        sources = _append_source(sources, "active_plan")
        if not active_goal_value:
            active_goal_value = incoming_plan.goal
        if not next_expected_step or next_expected_step == cleaned_query:
            next_expected_step = incoming_plan.next_step_title or incoming_plan.goal
        if not open_loop:
            open_loop = incoming_plan.next_step_title or incoming_plan.goal
    elif active_plan_state and response_mode == "resume_open_loop":
        if not next_expected_step:
            next_expected_step = active_plan_state.next_step_title or active_plan_state.goal
        if not open_loop:
            open_loop = active_plan_state.next_step_title or active_plan_state.goal

    if dominant_turn_type == "clarification":
        candidate_question = cleaned_query or cleaned_next_step or next_expected_step or open_loop
        if _looks_like_question(candidate_question):
            open_questions = list(
                _normalize_text_list([candidate_question, *open_questions], limit_items=_MAX_LIST_ITEMS)
            )
    elif response_mode == "resume_open_loop" and (current.open_loop or current.next_expected_step):
        resolved = {
            _normalize_text(current.open_loop),
            _normalize_text(current.next_expected_step),
        }
        open_questions = [
            item for item in open_questions if _normalize_text(item) not in resolved
        ]
    elif effects.get("set_open_loop") or effects.get("set_next_expected_step"):
        candidate_question = cleaned_next_step or cleaned_query
        if _looks_like_question(candidate_question):
            open_questions = list(
                _normalize_text_list([candidate_question, *open_questions], limit_items=_MAX_LIST_ITEMS)
            )

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
        open_questions=tuple(open_questions),
        active_plan=active_plan_state,
        state_source=sources,
        topic_confidence=max(current.topic_confidence, _normalize_confidence(confidence)),
        updated_at=_normalize_text(updated_at or current.updated_at, limit=64),
    )

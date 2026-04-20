"""Policy layer for meta response modes after turn understanding."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Tuple

from orchestration.meta_context_eval import detect_context_misread_risk
from orchestration.topic_state_history import parse_historical_topic_recall_hint


_STATE_SUMMARY_PATTERNS = (
    r"\bwo\s+stehen\s+wir\b",
    r"\bwas\s+ist\s+(?:gerade\s+)?offen\b",
    r"\bwas\s+war\s+dein\s+plan\b",
    r"\bfass\b.*\b(stand|zusammen)\b",
    r"\baktuellen?\s+stand\b",
    r"\bworan\s+arbeitest\s+du\b",
    r"\bwas\s+haben\s+wir\s+bisher\b",
    r"\bwie\s+ist\s+der\s+stand\b",
)

_NEXT_STEP_SUMMARY_PATTERNS = (
    r"\bwas\s+kommt\s+als\s+naechstes\b",
    r"\bwas\s+kommt\s+als\s+nächstes\b",
    r"\bwas\s+ist\s+als\s+naechstes\s+dran\b",
    r"\bwas\s+ist\s+als\s+nächstes\s+dran\b",
    r"\bwelcher\s+schritt\s+ist\s+als\s+naechstes\s+dran\b",
    r"\bwelcher\s+schritt\s+ist\s+als\s+nächstes\s+dran\b",
    r"\bsag\b.*\bwas\s+als\s+naechstes\s+ansteht\b",
    r"\bsag\b.*\bwas\s+als\s+nächstes\s+ansteht\b",
    r"\bnaechster\s+schritt\b",
    r"\bnächster\s+schritt\b",
)

_SELF_MODEL_STATUS_PATTERNS = (
    r"\bbist\s+du\s+anpassungsf(?:aehig|[aä]hig)\b",
    r"\bbist\s+du\s+ein\s+funktionierendes?\s+ki(?:-| )?system\b",
    r"\bwas\s+hast\s+du\s+f(?:u|ü)r\s+probleme\b",
    r"\bwelche\s+probleme\s+hast\s+du\b",
    r"\bwas\s+ist\s+los\b",
    r"\bwo\s+hakt\s+es\b",
    r"\bwas\s+kannst\s+du\s+dagegen\s+tun\b",
    r"\bwie\s+priorisierst\s+du\s+das\b",
    r"\bwas\s+davon\s+machst\s+du\s+zuerst\b",
    r"\bkannst\s+du\s+das\s+schon\b",
    r"\bkannst\s+du\s+das\s+jetzt\s+schon\b",
    r"\bist\s+das\s+geplant\b",
    r"\bist\s+das\s+schon\s+deine\s+philosophie\b",
    r"\bkoenntest\s+du\s+dir\s+selbst\b",
    r"\bk[oö]nntest\s+du\s+dir\s+selbst\b",
    r"\bbist\s+du\s+schon\s+soweit\b",
    r"\bvollautomatisch\b",
)

_RESEARCH_ACTION_HINTS = (
    "recherchiere",
    "recherchier",
    "suche",
    "suche nach",
    "such",
    "such mal",
    "finde",
    "schau nach",
    "schau im internet",
    "guck nach",
    "guck mal",
    "sieh nach",
    "pruefe",
    "prüfe",
    "check",
    "checke",
    "hole",
    "hol",
    "hol raus",
    "sammle",
    "ermittle",
    "lies",
    "lese",
    "zeig mir",
    "gib mir",
)

_ANALYSIS_ACTION_HINTS = (
    "analysiere",
    "bewerte",
    "vergleiche",
    "ordne ein",
    "beurteile",
    "schaetze ein",
    "schätze ein",
    "evaluiere",
    "klassifiziere",
    "erklaere",
    "erkläre",
    "zerlege",
    "diagnostiziere",
)

_CREATION_ACTION_HINTS = (
    "erstelle",
    "erstell",
    "schreibe",
    "schreib",
    "formuliere",
    "entwerfe",
    "generiere",
    "baue",
    "bau",
    "bereite vor",
    "plane",
    "entwirf",
)

_COMMUNICATION_ACTION_HINTS = (
    "sende",
    "schicke",
    "sag",
    "teile",
    "mail",
    "email",
    "benachrichtige",
    "antworte",
    "poste",
)

_BROWSER_ACTION_HINTS = (
    "oeffne",
    "öffne",
    "gehe auf",
    "navigiere zu",
    "klicke",
    "tippe",
    "gib ein",
    "trage ein",
    "fülle",
    "fuelle",
    "waehle",
    "wähle",
    "logge dich ein",
    "melde dich an",
)

_SYSTEM_ACTION_HINTS = (
    "starte",
    "stoppe",
    "pruef",
    "prüf",
    "ueberpruefe",
    "überprüfe",
    "kontrolliere",
    "neustarten",
    "restart",
    "prüf die logs",
    "pruef die logs",
    "diagnose",
    "fixe",
    "repariere",
)

_EXTRACTION_ACTION_HINTS = (
    "extrahiere",
    "extrahier",
    "liste",
    "list mir",
    "fasse zusammen",
    "zieh raus",
    "filtere",
    "exportiere",
    "speichere",
    "wandle um",
)

_DECISION_ACTION_HINTS = (
    "mach weiter",
    "mach mal",
    "fang an",
    "leg los",
    "setz fort",
    "tu das",
    "nimm das",
    "nimm die",
    "waehle die",
    "wähle die",
)

_ACTION_HINT_GROUPS = (
    _RESEARCH_ACTION_HINTS,
    _ANALYSIS_ACTION_HINTS,
    _CREATION_ACTION_HINTS,
    _COMMUNICATION_ACTION_HINTS,
    _BROWSER_ACTION_HINTS,
    _SYSTEM_ACTION_HINTS,
    _EXTRACTION_ACTION_HINTS,
    _DECISION_ACTION_HINTS,
)

_LOW_CONFIDENCE_CLARIFY_TASK_TYPES = {
    "single_lane",
    "simple_live_lookup",
    "location_local_search",
}


def _normalize_text(value: Any, *, limit: int = 320) -> str:
    return str(value or "").strip()[:limit]


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = _normalize_text(text).lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def _looks_like_state_summary(query: str) -> bool:
    return _matches_any(query, _STATE_SUMMARY_PATTERNS)


def _looks_like_next_step_summary(query: str) -> bool:
    return _matches_any(query, _NEXT_STEP_SUMMARY_PATTERNS)


def _looks_like_self_model_status(query: str) -> bool:
    return _matches_any(query, _SELF_MODEL_STATUS_PATTERNS)


def _looks_action_oriented(query: str) -> bool:
    lowered = _normalize_text(query).lower()
    return any(any(token in lowered for token in group) for group in _ACTION_HINT_GROUPS)


def _has_stateful_followup_anchor(policy_input: "MetaPolicyInput") -> bool:
    return any(
        _normalize_text(value, limit=180)
        for value in (policy_input.active_topic, policy_input.open_goal, policy_input.next_step)
    )


@dataclass(frozen=True)
class MetaPolicyInput:
    effective_query: str
    dominant_turn_type: str
    baseline_response_mode: str
    task_type: str
    active_topic: str
    open_goal: str
    next_step: str
    recommended_agent_chain: Tuple[str, ...]
    meta_context_bundle: dict[str, Any]
    preference_memory_selection: dict[str, Any]
    topic_state_transition: dict[str, Any]
    context_misread_risk: dict[str, Any]


@dataclass(frozen=True)
class MetaPolicyDecision:
    response_mode: str
    policy_reason: str
    policy_confidence: float
    answer_shape: str
    should_delegate: bool
    should_store_preference: bool
    should_resume_open_loop: bool
    should_summarize_state: bool
    self_model_bound_applied: bool
    policy_signals: Tuple[str, ...]
    override_applied: bool = False
    agent_chain_override: Tuple[str, ...] = ()
    task_type_override: str = ""
    recipe_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_mode": self.response_mode,
            "policy_reason": self.policy_reason,
            "policy_confidence": self.policy_confidence,
            "answer_shape": self.answer_shape,
            "should_delegate": self.should_delegate,
            "should_store_preference": self.should_store_preference,
            "should_resume_open_loop": self.should_resume_open_loop,
            "should_summarize_state": self.should_summarize_state,
            "self_model_bound_applied": self.self_model_bound_applied,
            "policy_signals": list(self.policy_signals),
            "override_applied": self.override_applied,
            "agent_chain_override": list(self.agent_chain_override),
            "task_type_override": self.task_type_override,
            "recipe_enabled": self.recipe_enabled,
        }


def resolve_meta_response_policy(policy_input: MetaPolicyInput) -> MetaPolicyDecision:
    baseline = _normalize_text(policy_input.baseline_response_mode, limit=64).lower() or "execute"
    dominant_turn_type = _normalize_text(policy_input.dominant_turn_type, limit=64).lower()
    risk = dict(policy_input.context_misread_risk or {})
    risk_reasons = tuple(str(item or "") for item in (risk.get("reasons") or []))
    suspicious = bool(risk.get("suspicious"))
    signals: list[str] = []
    historical_recall = parse_historical_topic_recall_hint(policy_input.effective_query)

    if _looks_like_self_model_status(policy_input.effective_query):
        signals.append("self_model_status_question")
        return MetaPolicyDecision(
            response_mode="summarize_state",
            policy_reason="self_model_status_request",
            policy_confidence=0.9,
            answer_shape="self_model_status",
            should_delegate=False,
            should_store_preference=False,
            should_resume_open_loop=False,
            should_summarize_state=True,
            self_model_bound_applied=True,
            policy_signals=tuple(signals),
            override_applied=True,
            agent_chain_override=("meta",),
            task_type_override="single_lane",
            recipe_enabled=False,
        )

    if historical_recall.requested:
        signals.extend(["historical_topic_recall", historical_recall.time_label])
        return MetaPolicyDecision(
            response_mode="summarize_state",
            policy_reason="historical_topic_recall",
            policy_confidence=0.89,
            answer_shape="historical_topic_state",
            should_delegate=False,
            should_store_preference=False,
            should_resume_open_loop=False,
            should_summarize_state=True,
            self_model_bound_applied=False,
            policy_signals=tuple(signals),
            override_applied=(baseline != "summarize_state"),
            agent_chain_override=("meta",),
            task_type_override="single_lane",
            recipe_enabled=False,
        )

    if _looks_like_next_step_summary(policy_input.effective_query):
        signals.append("next_step_summary_language")
        return MetaPolicyDecision(
            response_mode="summarize_state",
            policy_reason="next_step_summary_request",
            policy_confidence=0.92,
            answer_shape="direct_recommendation",
            should_delegate=False,
            should_store_preference=False,
            should_resume_open_loop=False,
            should_summarize_state=True,
            self_model_bound_applied=False,
            policy_signals=tuple(signals),
            override_applied=(baseline != "summarize_state"),
            agent_chain_override=("meta",),
            task_type_override="single_lane",
            recipe_enabled=False,
        )

    if _looks_like_state_summary(policy_input.effective_query):
        signals.append("state_summary_language")
        return MetaPolicyDecision(
            response_mode="summarize_state",
            policy_reason="state_summary_request",
            policy_confidence=0.91,
            answer_shape="state_summary",
            should_delegate=False,
            should_store_preference=False,
            should_resume_open_loop=False,
            should_summarize_state=True,
            self_model_bound_applied=False,
            policy_signals=tuple(signals),
            override_applied=(baseline != "summarize_state"),
            agent_chain_override=("meta",),
            task_type_override="single_lane",
            recipe_enabled=False,
        )

    if baseline == "resume_open_loop" and any(
        reason in risk_reasons for reason in ("resume_mode_without_open_loop", "thin_context_for_risky_turn")
    ):
        if dominant_turn_type == "followup" and _has_stateful_followup_anchor(policy_input):
            signals.extend(["stateful_followup_anchor_present", *risk_reasons])
        else:
            signals.extend(["open_loop_resume_requested", *risk_reasons])
            return MetaPolicyDecision(
                response_mode="clarify_before_execute",
                policy_reason="open_loop_not_reliable",
                policy_confidence=0.84,
                answer_shape="question_first",
                should_delegate=False,
                should_store_preference=False,
                should_resume_open_loop=False,
                should_summarize_state=False,
                self_model_bound_applied=False,
                policy_signals=tuple(signals),
                override_applied=True,
                agent_chain_override=("meta",),
                task_type_override="single_lane",
                recipe_enabled=False,
            )

    if (
        baseline == "execute"
        and suspicious
        and policy_input.task_type in _LOW_CONFIDENCE_CLARIFY_TASK_TYPES
        and dominant_turn_type in {"followup", "clarification", "new_task"}
        and _looks_action_oriented(policy_input.effective_query)
    ):
        signals.extend(["action_requested", *risk_reasons])
        return MetaPolicyDecision(
            response_mode="clarify_before_execute",
            policy_reason="context_low_confidence_with_action_request",
            policy_confidence=0.76,
            answer_shape="question_first",
            should_delegate=False,
            should_store_preference=False,
            should_resume_open_loop=False,
            should_summarize_state=False,
            self_model_bound_applied=False,
            policy_signals=tuple(signals),
            override_applied=True,
            agent_chain_override=("meta",),
            task_type_override="single_lane",
            recipe_enabled=False,
        )

    answer_shape = "action_first"
    if baseline == "acknowledge_and_store":
        answer_shape = "acknowledgment"
    elif baseline == "correct_previous_path":
        answer_shape = "course_correction"
    elif baseline == "clarify_before_execute":
        answer_shape = "question_first"
    elif baseline == "resume_open_loop":
        answer_shape = "resume_action"

    return MetaPolicyDecision(
        response_mode=baseline,
        policy_reason="baseline_turn_mode",
        policy_confidence=0.72,
        answer_shape=answer_shape,
        should_delegate=baseline in {"execute", "resume_open_loop"},
        should_store_preference=baseline == "acknowledge_and_store",
        should_resume_open_loop=baseline == "resume_open_loop",
        should_summarize_state=baseline == "summarize_state",
        self_model_bound_applied=False,
        policy_signals=tuple(signals),
        override_applied=False,
    )


def build_meta_policy_input(
    *,
    effective_query: str,
    dominant_turn_type: str,
    baseline_response_mode: str,
    task_type: str,
    active_topic: str,
    open_goal: str,
    next_step: str,
    recommended_agent_chain: tuple[str, ...],
    meta_context_bundle: Mapping[str, Any] | None,
    preference_memory_selection: Mapping[str, Any] | None,
    topic_state_transition: Mapping[str, Any] | None,
) -> MetaPolicyInput:
    bundle = dict(meta_context_bundle or {})
    risk = detect_context_misread_risk(
        bundle,
        dominant_turn_type=dominant_turn_type,
        response_mode=baseline_response_mode,
    )
    return MetaPolicyInput(
        effective_query=_normalize_text(effective_query, limit=800),
        dominant_turn_type=_normalize_text(dominant_turn_type, limit=64),
        baseline_response_mode=_normalize_text(baseline_response_mode, limit=64),
        task_type=_normalize_text(task_type, limit=64),
        active_topic=_normalize_text(active_topic, limit=180),
        open_goal=_normalize_text(open_goal, limit=180),
        next_step=_normalize_text(next_step, limit=180),
        recommended_agent_chain=tuple(str(item or "").strip() for item in recommended_agent_chain if str(item or "").strip()),
        meta_context_bundle=bundle,
        preference_memory_selection=dict(preference_memory_selection or {}),
        topic_state_transition=dict(topic_state_transition or {}),
        context_misread_risk=risk,
    )

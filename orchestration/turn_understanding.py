"""Semantische Turn-Verstehensschicht fuer Meta vor Routing und Rezeptwahl."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

from orchestration.topic_state_history import parse_historical_topic_recall_hint


_CORRECTION_PATTERNS = (
    r"\bso\s+meinte\s+ich\s+das\s+nicht\b",
    r"\bso\s+war\s+das\s+nicht\s+gemeint\b",
    r"\bnein[, ]",
    r"\bich\s+meinte\b",
    r"\bich\s+(?:wollte|willte)\b",
    r"\bfalsch\b",
    r"\banders\b",
)

_COMPLAINT_PATTERNS = (
    r"\bhat\s+nicht\s+geklappt\b",
    r"\bnicht\s+verstanden\b",
    r"\bvoellig\s+aus\s+dem\s+kontext\b",
    r"\bv[öo]llig\s+aus\s+dem\s+kontext\b",
    r"\baus\s+dem\s+kontext\s+gerissen\b",
    r"\bdu\s+verlierst\b",
    r"\bdu\s+folgst\s+mir\s+nicht\b",
)

_APPROVAL_PATTERNS = (
    r"^\s*(?:ja|jo|ok|okay|in\s+ordnung|passt|mach\s+das|leg\s+los|fang\s+an)\b",
    r"\bdu\s+darfst\b",
    r"\berlaubt\b",
    r"\bgenehmigt\b",
)

_AUTH_PATTERNS = (
    r"\blogin\b",
    r"\banmelden\b",
    r"\beinloggen\b",
    r"\bsign\s*in\b",
    r"\bpasswort\b",
    r"\b2fa\b",
    r"\btoken\b",
    r"\bmeinen\s+zugang\b",
)

_RESULT_EXTRACTION_PATTERNS = (
    r"\bextrahier(?:e)?\b",
    r"\bhol(?:e)?\b.*\bheraus\b",
    r"\bliste\b.*\baus\b",
    r"\bnur\s+die\s+preise\b",
    r"\bnur\s+die\s+fakten\b",
    r"\bzieh\b.*\braus\b",
)

_BEHAVIOR_FUTURE_HINTS = (
    "in zukunft",
    "kuenftig",
    "zukuenftig",
    "fortan",
    "ab jetzt",
)

_BEHAVIOR_DIRECTIVE_HINTS = (
    "mach das",
    "speichere dir",
    "antworte mir",
    "nutze",
    "verwende",
    "bevorzuge",
    "priorisiere",
    "achte darauf",
    "stell sicher",
    "merk dir",
    "merke dir",
    "behalte im kopf",
)

_PREFERENCE_HINTS = (
    "bitte zuerst",
    "kurze antworten",
    "kurz antworten",
    "weniger formal",
    "lokale tools",
    "lieber",
    "eher",
    "bevorzuge",
    "priorisiere",
    "in solchen faellen",
)

_BEHAVIOR_STORAGE_PATTERNS = (
    r"\bspeichere\s+dir\b",
    r"\bmerk(?:e)?\s+dir\b",
    r"\bbehalte\s+(?:das\s+)?im\s+kopf\b",
)

_STYLE_PREFERENCE_PATTERNS = (
    r"\b(?:kurze?|knappe?)\s+antwort",
    r"\bkurz\s+antwort",
    r"\bweniger\s+formal\b",
    r"\b(?:locker|direkter|formeller)\s+antwort",
    r"\bantworte\s+mir\b.*\b(?:kurz|knapp|formal|locker|direkt)\b",
)

_CONDITIONAL_TOOL_PREFERENCE_PATTERNS = (
    r"\bwenn\s+ich\b.*\bsage\b.*\b(?:nutze|verwende|nimm|bevorzuge|priorisiere)\b",
    r"\bwenn\s+ich\b.*\b(?:pdf|datei|dokument)\b.*\b(?:nutze|verwende|nimm)\b.*\b(?:lokale?\s+tools?|tools?)\b",
    r"\bwenn\s+du\b.*\b(?:recherchierst|suchst|antwortest|arbeitest|codest|programmierst)\b.*\b(?:immer|zuerst|direkt|lieber|bitte)\b",
    r"\bf(?:ue|ü)r\b.*\b(?:fragen|aufgaben|recherchen)\b.*\bgib\b.*\b(?:zuerst|immer)\b",
)

_PREFERENCE_DELETE_PATTERNS = (
    r"\bvergiss\b.*\b(?:letzte\s+)?(?:praeferenz|präferenz|praferenz|preference|vorgabe|regel)\b",
    r"\b(?:l[öo]sch(?:e)?|loesch(?:e)?)\b.*\b(?:letzte\s+)?(?:praeferenz|präferenz|praferenz|preference|vorgabe|regel)\b",
)

_HANDOVER_RESUME_PATTERNS = (
    r"^\s*(?:ok|okay|ja)?\s*(?:mach\s+weiter|weiter|leg\s+los|fang\s+an)\b",
    r"^\s*die\s+erste\s+option\b",
    r"^\s*die\s+zweite\s+option\b",
    r"^\s*die\s+dritte\s+option\b",
)
_SHORT_CONTEXTUAL_FOLLOWUP_PREFIXES = (
    "so aber",
    "aber mit",
    "und jetzt",
    "und dann",
    "nur mit",
    "diesmal mit",
    "so nur",
)
_TOPIC_REFERENTIAL_FOLLOWUP_HINTS = (
    "da ",
    "dabei",
    "dafuer",
    "dafür",
    "dafuer",
    "daran",
    "darauf",
    "darueber",
    "darüber",
    "dazu",
    "dort",
    "fuss fassen",
    "fuß fassen",
    "wie kann ich dort",
    "wie koennte ich dort",
    "wie könnte ich dort",
)


def _normalize_text(value: Any, *, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _normalize_list(values: Iterable[str], *, limit: int = 12, item_limit: int = 80) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        cleaned = _normalize_text(item, limit=item_limit)
        if not cleaned or cleaned in seen:
            continue
        deduped.append(cleaned)
        seen.add(cleaned)
        if len(deduped) >= limit:
            break
    return tuple(deduped)


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    lowered = str(text or "").strip().lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def _contains_any(text: str, hints: Iterable[str]) -> bool:
    lowered = str(text or "").strip().lower()
    return any(hint in lowered for hint in hints)


@dataclass(frozen=True)
class TurnUnderstandingInput:
    raw_query: str
    effective_query: str
    active_topic: str
    open_goal: str
    next_step: str
    dialog_constraints: Tuple[str, ...]
    semantic_review_hints: Tuple[str, ...]
    has_followup_context: bool
    has_recent_user_turns: bool
    has_recent_assistant_turns: bool
    historical_recall_requested: bool
    compressed_followup_parsed: bool
    active_topic_reused: bool
    context_anchor_applied: bool
    conversation_state: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["dialog_constraints"] = list(self.dialog_constraints)
        payload["semantic_review_hints"] = list(self.semantic_review_hints)
        return payload


@dataclass(frozen=True)
class TurnStateEffects:
    update_preferences: bool = False
    remove_last_preference: bool = False
    update_recent_corrections: bool = False
    set_open_loop: bool = False
    clear_open_loop: bool = False
    set_next_expected_step: bool = False
    keep_active_topic: bool = False
    shift_active_topic: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class TurnInterpretation:
    dominant_turn_type: str
    turn_signals: Tuple[str, ...]
    response_mode: str
    state_effects: TurnStateEffects
    current_intent_summary: str
    target_topic: str
    needs_clarification: bool
    route_bias: str
    confidence: float
    evidence: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dominant_turn_type": self.dominant_turn_type,
            "turn_signals": list(self.turn_signals),
            "response_mode": self.response_mode,
            "state_effects": self.state_effects.to_dict(),
            "current_intent_summary": self.current_intent_summary,
            "target_topic": self.target_topic,
            "needs_clarification": self.needs_clarification,
            "route_bias": self.route_bias,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


def build_turn_understanding_input(
    *,
    raw_query: str,
    effective_query: str,
    dialog_state: Mapping[str, Any] | None,
    semantic_review_hints: Iterable[str] | None = None,
    conversation_state: Mapping[str, Any] | None = None,
    recent_user_turns: Iterable[str] | None = None,
    recent_assistant_turns: Iterable[str] | None = None,
    context_anchor_applied: bool = False,
) -> TurnUnderstandingInput:
    state = dict(dialog_state or {})
    session_state = dict(conversation_state or {})
    active_topic = _normalize_text(state.get("active_topic") or session_state.get("active_topic"))
    open_goal = _normalize_text(state.get("open_goal") or session_state.get("active_goal"))
    next_step = _normalize_text(state.get("next_step") or session_state.get("next_expected_step"))
    normalized_recent_users = _normalize_list(recent_user_turns or (), limit=3, item_limit=160)
    normalized_recent_assistant = _normalize_list(recent_assistant_turns or (), limit=3, item_limit=160)
    historical_recall_requested = parse_historical_topic_recall_hint(_normalize_text(effective_query, limit=800)).requested
    return TurnUnderstandingInput(
        raw_query=_normalize_text(raw_query, limit=2000),
        effective_query=_normalize_text(effective_query, limit=800),
        active_topic=active_topic,
        open_goal=open_goal,
        next_step=next_step,
        dialog_constraints=_normalize_list(state.get("constraints") or session_state.get("constraints") or (), limit=8),
        semantic_review_hints=_normalize_list(semantic_review_hints or (), limit=8, item_limit=64),
        has_followup_context="# current user query" in str(raw_query or "").lower(),
        has_recent_user_turns=bool(normalized_recent_users),
        has_recent_assistant_turns=bool(normalized_recent_assistant),
        historical_recall_requested=bool(historical_recall_requested),
        compressed_followup_parsed=bool(state.get("compressed_followup_parsed")),
        active_topic_reused=bool(state.get("active_topic_reused")),
        context_anchor_applied=bool(context_anchor_applied),
        conversation_state=session_state,
    )


def detect_turn_signals(turn_input: TurnUnderstandingInput) -> tuple[str, ...]:
    query = turn_input.effective_query
    hints = {item.lower() for item in turn_input.semantic_review_hints}
    signals: list[str] = []

    if turn_input.has_followup_context:
        signals.append("followup_context_present")
    if turn_input.has_recent_user_turns:
        signals.append("recent_user_turns_present")
    if turn_input.has_recent_assistant_turns:
        signals.append("recent_assistant_turns_present")
    if turn_input.active_topic or turn_input.active_topic_reused or turn_input.context_anchor_applied:
        signals.append("active_topic_present")
    if turn_input.open_goal or turn_input.next_step:
        signals.append("open_loop_present")
    if turn_input.compressed_followup_parsed:
        signals.append("compressed_followup")
    if turn_input.historical_recall_requested:
        signals.append("historical_recall_requested")
        if (
            turn_input.has_recent_user_turns
            or turn_input.has_recent_assistant_turns
            or turn_input.has_followup_context
            or turn_input.active_topic
            or turn_input.open_goal
            or turn_input.next_step
        ):
            signals.append("historical_recall_with_context")

    if "behavior_preference_alignment" in hints:
        signals.extend(["behavior_instruction", "preference_update"])
    if "conversational_clarification_needed" in hints:
        signals.append("clarification_language")

    if _contains_any(query, _BEHAVIOR_FUTURE_HINTS):
        signals.append("future_preference_language")
    if _contains_any(query, _BEHAVIOR_DIRECTIVE_HINTS):
        signals.append("directive_language")
    if _contains_any(query, _PREFERENCE_HINTS):
        signals.append("preference_language")
    if _matches_any(query, _PREFERENCE_DELETE_PATTERNS):
        signals.extend(["behavior_instruction", "preference_delete"])
    if _matches_any(query, _BEHAVIOR_STORAGE_PATTERNS):
        signals.append("behavior_storage_language")
    if _matches_any(query, _STYLE_PREFERENCE_PATTERNS):
        signals.append("style_preference_language")
    if _matches_any(query, _CONDITIONAL_TOOL_PREFERENCE_PATTERNS):
        signals.append("conditional_tool_preference_language")

    if _matches_any(query, _CORRECTION_PATTERNS):
        signals.append("correction_language")
    if _matches_any(query, _COMPLAINT_PATTERNS):
        signals.append("complaint_language")
    if _matches_any(query, _APPROVAL_PATTERNS):
        signals.append("approval_language")
    if _matches_any(query, _AUTH_PATTERNS):
        signals.append("auth_language")
    if _matches_any(query, _RESULT_EXTRACTION_PATTERNS):
        signals.append("result_extraction_language")
    if _matches_any(query, _HANDOVER_RESUME_PATTERNS):
        signals.append("handover_resume_language")
    lowered_query = query.lower().strip()
    if (
        len(lowered_query.split()) <= 6
        and (turn_input.active_topic or turn_input.open_goal or turn_input.next_step)
        and any(lowered_query.startswith(prefix) for prefix in _SHORT_CONTEXTUAL_FOLLOWUP_PREFIXES)
    ):
        signals.append("short_contextual_followup_language")
    if (
        (turn_input.active_topic or turn_input.open_goal or turn_input.next_step)
        and any(marker in lowered_query for marker in _TOPIC_REFERENTIAL_FOLLOWUP_HINTS)
    ):
        signals.append("topic_referential_followup")

    if "behavior_instruction" not in signals and "directive_language" in signals and "future_preference_language" in signals:
        signals.append("behavior_instruction")
    if "behavior_instruction" not in signals and (
        "behavior_storage_language" in signals
        or ("future_preference_language" in signals and "style_preference_language" in signals)
        or "conditional_tool_preference_language" in signals
    ):
        signals.append("behavior_instruction")
    if "preference_update" not in signals and (
        "preference_delete" not in signals
        and (
            "preference_language" in signals
            or "future_preference_language" in signals
            or "style_preference_language" in signals
            or "conditional_tool_preference_language" in signals
            or "behavior_storage_language" in signals
        )
    ):
        signals.append("preference_update")

    if not signals:
        signals.append("new_work_request")

    return _normalize_list(signals, limit=16, item_limit=64)


def resolve_dominant_turn_type(turn_input: TurnUnderstandingInput, signals: Iterable[str]) -> str:
    signal_set = set(signals)
    if "auth_language" in signal_set and "approval_language" in signal_set:
        return "auth_response"
    if "auth_language" in signal_set and turn_input.has_followup_context:
        return "auth_response"
    if "handover_resume_language" in signal_set and turn_input.has_followup_context:
        return "handover_resume"
    if "approval_language" in signal_set and turn_input.has_followup_context:
        return "approval_response"
    if "correction_language" in signal_set:
        return "correction"
    if "behavior_instruction" in signal_set:
        return "behavior_instruction"
    if "preference_update" in signal_set:
        return "preference_update"
    if "complaint_language" in signal_set:
        return "complaint_about_last_answer"
    if "result_extraction_language" in signal_set:
        return "result_extraction"
    if "clarification_language" in signal_set:
        return "clarification"
    if "historical_recall_with_context" in signal_set:
        return "followup"
    if "topic_referential_followup" in signal_set:
        return "followup"
    if "short_contextual_followup_language" in signal_set:
        return "followup"
    if (
        turn_input.has_followup_context
        or "compressed_followup" in signal_set
        or turn_input.active_topic_reused
        or turn_input.context_anchor_applied
    ):
        return "followup"
    return "new_task"


def resolve_response_mode(dominant_turn_type: str, turn_input: TurnUnderstandingInput, signals: Iterable[str]) -> str:
    signal_set = set(signals)
    if dominant_turn_type in {"approval_response", "auth_response", "handover_resume"}:
        return "resume_open_loop"
    if dominant_turn_type in {"behavior_instruction", "preference_update"}:
        return "acknowledge_and_store"
    if dominant_turn_type in {"correction", "complaint_about_last_answer"}:
        return "correct_previous_path"
    if dominant_turn_type == "clarification":
        return "clarify_before_execute"
    if dominant_turn_type == "followup" and "historical_recall_requested" in signal_set:
        return "resume_open_loop"
    if dominant_turn_type == "followup" and ("open_loop_present" in signal_set or turn_input.next_step):
        return "resume_open_loop"
    if dominant_turn_type == "followup":
        return "execute"
    return "execute"


def derive_state_effects(
    dominant_turn_type: str,
    response_mode: str,
    signals: Iterable[str] = (),
) -> TurnStateEffects:
    if "preference_delete" in set(signals):
        return TurnStateEffects(
            remove_last_preference=True,
            set_next_expected_step=True,
            keep_active_topic=True,
        )
    if dominant_turn_type in {"behavior_instruction", "preference_update"}:
        return TurnStateEffects(
            update_preferences=True,
            set_next_expected_step=True,
            keep_active_topic=True,
        )
    if dominant_turn_type in {"correction", "complaint_about_last_answer"}:
        return TurnStateEffects(
            update_recent_corrections=True,
            keep_active_topic=True,
        )
    if dominant_turn_type in {"approval_response", "auth_response", "handover_resume"}:
        return TurnStateEffects(
            keep_active_topic=True,
        )
    if dominant_turn_type in {"result_extraction", "followup"}:
        return TurnStateEffects(
            keep_active_topic=True,
        )
    if response_mode == "clarify_before_execute":
        return TurnStateEffects(
            keep_active_topic=True,
        )
    return TurnStateEffects(
        shift_active_topic=True,
    )


def interpret_turn(turn_input: TurnUnderstandingInput) -> TurnInterpretation:
    signals = detect_turn_signals(turn_input)
    dominant_turn_type = resolve_dominant_turn_type(turn_input, signals)
    response_mode = resolve_response_mode(dominant_turn_type, turn_input, signals)
    state_effects = derive_state_effects(dominant_turn_type, response_mode, signals)

    route_bias = "route_normally"
    has_live_dialog_context = bool(
        turn_input.has_followup_context
        or turn_input.context_anchor_applied
        or turn_input.active_topic
        or turn_input.open_goal
        or turn_input.next_step
    )
    if dominant_turn_type in {
        "approval_response",
        "auth_response",
        "handover_resume",
        "behavior_instruction",
        "preference_update",
        "clarification",
    }:
        route_bias = "meta_only"
    elif dominant_turn_type in {"correction", "complaint_about_last_answer"} and has_live_dialog_context:
        route_bias = "meta_only"
    elif dominant_turn_type in {"followup", "result_extraction"}:
        route_bias = "follow_existing_lane"

    target_topic = turn_input.active_topic or turn_input.open_goal or turn_input.effective_query
    confidence = 0.7
    if dominant_turn_type in {"behavior_instruction", "preference_update", "correction", "result_extraction"}:
        confidence = 0.86
    elif dominant_turn_type in {"approval_response", "auth_response", "handover_resume"}:
        confidence = 0.82
    elif dominant_turn_type == "clarification":
        confidence = 0.8
    elif dominant_turn_type == "followup":
        confidence = 0.74

    evidence: list[str] = []
    for signal in signals:
        evidence.append(f"signal:{signal}")
    if turn_input.active_topic:
        evidence.append(f"topic:{turn_input.active_topic[:80]}")
    if turn_input.open_goal:
        evidence.append(f"goal:{turn_input.open_goal[:80]}")

    summary_map = {
        "behavior_instruction": "Der Nutzer gibt eine Arbeitsanweisung fuer kuenftiges Verhalten.",
        "preference_update": "Der Nutzer aktualisiert eine Arbeits- oder Antwortpraeferenz.",
        "correction": "Der Nutzer korrigiert die bisherige Richtung oder Deutung.",
        "complaint_about_last_answer": "Der Nutzer kritisiert die letzte Antwort und erwartet Kurskorrektur.",
        "approval_response": "Der Nutzer reagiert auf einen offenen Freigabe- oder Fortsetzungszustand.",
        "auth_response": "Der Nutzer reagiert auf einen Login- oder Zugriffsbedarf.",
        "handover_resume": "Der Nutzer will den laufenden Pfad fortsetzen.",
        "result_extraction": "Der Nutzer will aus vorhandenen Ergebnissen nur einen Teil herausziehen.",
        "clarification": "Der Nutzer signalisiert Klaerungsbedarf statt Ausfuehrung.",
        "followup": "Der Nutzer knuepft an den laufenden Themenstrang an.",
        "new_task": "Der Nutzer stellt eine neue Aufgabe.",
    }

    return TurnInterpretation(
        dominant_turn_type=dominant_turn_type,
        turn_signals=signals,
        response_mode=response_mode,
        state_effects=state_effects,
        current_intent_summary=summary_map.get(dominant_turn_type, "Semantischer Nutzerturn erkannt."),
        target_topic=_normalize_text(target_topic),
        needs_clarification=(response_mode == "clarify_before_execute"),
        route_bias=route_bias,
        confidence=confidence,
        evidence=_normalize_list(evidence, limit=12, item_limit=120),
    )

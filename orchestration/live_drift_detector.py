"""Live drift detection for chat turns.

E1 is diagnostic only: it detects suspicious answer/routing patterns and emits
structured signals for observation. It must not change routing or responses.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence


_CONTEXT_EMPTY_PATTERNS = (
    "kontext ist leer",
    "der kontext ist leer",
    "kein vorheriger kontext",
    "keinen vorherigen kontext",
    "kein laufender open-loop",
    "keine kuerzliche interaktion",
    "keine kürzliche interaktion",
    "conversation-state ist hier abgeschnitten",
    "context is empty",
    "no previous context",
)

_MODE_BLOCK_PATTERNS = (
    "interaktionsmodus blockiert",
    "modus blockiert",
    "think_partner",
    "keine toolnutzung",
    "keine tools ausfuehren",
    "keine tools ausführen",
    "keine ausfuehrung",
    "keine ausführung",
    "toolnutzung verboten",
    "system-contract",
    "haende gebunden",
    "hände gebunden",
)

_MODE_DISCUSSION_PATTERNS = (
    "aktionsmodus",
    "interaktionsmodus",
    "modus wechseln",
    "wechsle in den",
    "aktueller modus",
    "think_partner",
)

_CLARIFY_PATTERNS = (
    "was genau",
    "welche",
    "welchen",
    "worum",
    "brauch",
    "sag mir",
    "klaeren",
    "klären",
    "nicht eindeutig",
    "ich brauche",
)

_ACTION_REQUEST_HINTS = (
    "fuehre aus",
    "führe aus",
    "mach",
    "erstelle",
    "wandle",
    "sende",
    "schick",
    "nutze die tools",
    "starte",
    "recherchiere",
)


@dataclass(frozen=True)
class LiveDriftSignal:
    drift_type: str
    confidence: float
    anchor: str
    recommended_action: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def _clean_text(value: Any, *, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _lower(value: Any, *, limit: int = 500) -> str:
    return _clean_text(value, limit=limit).lower()


def _has_any(text: str, patterns: Iterable[str]) -> bool:
    lowered = _lower(text, limit=2000)
    return any(pattern in lowered for pattern in patterns)


def _looks_like_question(text: str) -> bool:
    lowered = _lower(text, limit=1000)
    return "?" in lowered or _has_any(lowered, _CLARIFY_PATTERNS)


def _looks_like_clarify(text: str) -> bool:
    lowered = _lower(text, limit=1000)
    return _looks_like_question(lowered) and _has_any(lowered, _CLARIFY_PATTERNS)


def _looks_like_action_request(query: str) -> bool:
    return _has_any(query, _ACTION_REQUEST_HINTS)


def _state_anchor(conversation_state: Mapping[str, Any] | None, query: str) -> str:
    state = dict(conversation_state or {})
    for key in ("active_topic", "active_goal", "open_loop", "next_expected_step"):
        value = _clean_text(state.get(key), limit=180)
        if value:
            return value
    return _clean_text(query, limit=180)


def _state_has_anchor(conversation_state: Mapping[str, Any] | None) -> bool:
    state = dict(conversation_state or {})
    return any(
        _clean_text(state.get(key), limit=180)
        for key in ("active_topic", "active_goal", "open_loop", "next_expected_step")
    )


def _context_slot_count(meta_classification: Mapping[str, Any] | None) -> int:
    bundle = dict((meta_classification or {}).get("meta_context_bundle") or {})
    slots = bundle.get("context_slots") or ()
    if isinstance(slots, Sequence) and not isinstance(slots, (str, bytes)):
        return sum(1 for item in slots if isinstance(item, Mapping))
    return 0


def _conversation_state_allowed(meta_classification: Mapping[str, Any] | None) -> bool:
    authority = dict((meta_classification or {}).get("meta_context_authority") or {})
    allowed = {str(item or "").strip().lower() for item in (authority.get("allowed_context_classes") or [])}
    return "conversation_state" in allowed


def _is_followup_like(
    *,
    dominant_turn_type: str,
    response_mode: str,
    conversation_state: Mapping[str, Any] | None,
) -> bool:
    dominant = _lower(dominant_turn_type, limit=80)
    mode = _lower(response_mode, limit=80)
    return (
        dominant in {"followup", "approval_response", "auth_response", "handover_resume"}
        or mode == "resume_open_loop"
        or _state_has_anchor(conversation_state)
    )


def detect_live_drifts(
    *,
    query: str,
    reply: str,
    agent: str = "",
    response_mode: str = "",
    dominant_turn_type: str = "",
    conversation_state: Mapping[str, Any] | None = None,
    meta_classification: Mapping[str, Any] | None = None,
    recent_assistant_turns: Iterable[str] | None = None,
    pending_followup_prompt: str = "",
) -> tuple[LiveDriftSignal, ...]:
    """Return diagnostic drift signals for a completed chat turn.

    The function is intentionally deterministic and side-effect free so it can
    be fuzzed and checked independently from the live server.
    """

    cleaned_query = _clean_text(query, limit=800)
    cleaned_reply = _clean_text(reply, limit=1600)
    response_mode_clean = _lower(response_mode, limit=80)
    dominant_clean = _lower(dominant_turn_type, limit=80)
    anchor = _state_anchor(conversation_state, cleaned_query)
    state_anchor_present = _state_has_anchor(conversation_state)
    slot_count = _context_slot_count(meta_classification)
    followup_like = _is_followup_like(
        dominant_turn_type=dominant_clean,
        response_mode=response_mode_clean,
        conversation_state=conversation_state,
    )
    signals: list[LiveDriftSignal] = []

    recent_clarifies = sum(1 for item in (recent_assistant_turns or ()) if _looks_like_clarify(str(item or "")))
    if (response_mode_clean == "clarify_before_execute" or _looks_like_clarify(cleaned_reply)) and recent_clarifies >= 2:
        signals.append(
            LiveDriftSignal(
                drift_type="repeated_clarify",
                confidence=0.88,
                anchor=anchor,
                recommended_action="Stoppe die Klaerungsschleife und beantworte oder fuehre mit den vorhandenen Constraints aus.",
                reasons=("current_clarify", "recent_clarify_count>=2"),
            )
        )

    if followup_like and state_anchor_present and slot_count == 0 and not _clean_text(pending_followup_prompt, limit=120):
        signals.append(
            LiveDriftSignal(
                drift_type="empty_context_on_followup",
                confidence=0.86,
                anchor=anchor,
                recommended_action="Conversation-State erneut in den Arbeitskontext laden, bevor geantwortet wird.",
                reasons=("followup_like", "state_anchor_present", "context_slot_count=0"),
            )
        )

    if _has_any(cleaned_reply, _CONTEXT_EMPTY_PATTERNS) and (
        state_anchor_present or slot_count > 0 or _conversation_state_allowed(meta_classification)
    ):
        signals.append(
            LiveDriftSignal(
                drift_type="false_context_empty_claim",
                confidence=0.92,
                anchor=anchor,
                recommended_action="Antwort verwerfen oder korrigieren: vorhandenen Conversation-State explizit aufgreifen.",
                reasons=("reply_claims_empty_context", "state_or_context_available"),
            )
        )

    if response_mode_clean == "execute" and _has_any(cleaned_reply, _MODE_BLOCK_PATTERNS):
        signals.append(
            LiveDriftSignal(
                drift_type="execute_blocked_by_mode",
                confidence=0.95,
                anchor=anchor,
                recommended_action="Policy/Interaction-Mode pruefen: execute darf nicht mit Modusblockade enden.",
                reasons=("response_mode=execute", "reply_contains_mode_block"),
            )
        )

    recent_mode_discussions = sum(
        1 for item in (recent_assistant_turns or ()) if _has_any(str(item or ""), _MODE_DISCUSSION_PATTERNS)
    )
    if _has_any(cleaned_reply, _MODE_DISCUSSION_PATTERNS) and (
        recent_mode_discussions >= 1 or response_mode_clean == "execute" or _looks_like_action_request(cleaned_query)
    ):
        signals.append(
            LiveDriftSignal(
                drift_type="mode_discussion_loop",
                confidence=0.84,
                anchor=anchor,
                recommended_action="Modus-Erklaerung abbrechen; Auftrag direkt ausfuehren oder einen echten Blocker nennen.",
                reasons=("reply_contains_mode_discussion", "action_or_recent_mode_context"),
            )
        )

    if len(cleaned_reply) < 30 and len(cleaned_query) > 50 and response_mode_clean in {"execute", "resume_open_loop"}:
        signals.append(
            LiveDriftSignal(
                drift_type="short_blocked_answer",
                confidence=0.70,
                anchor=anchor,
                recommended_action="Antwortqualitaet pruefen: klare lange Aufgabe erhielt eine sehr kurze Antwort.",
                reasons=("short_reply", "long_query", f"agent:{_clean_text(agent, limit=40)}"),
            )
        )

    return tuple(signals)

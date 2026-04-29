from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.live_drift_detector import detect_live_drifts


def _types(*, query: str, reply: str, **kwargs: object) -> set[str]:
    return {signal.drift_type for signal in detect_live_drifts(query=query, reply=reply, **kwargs)}


def test_detects_repeated_clarify_loop() -> None:
    drift_types = _types(
        query="mach jetzt vorschlaege",
        reply="Wofuer genau moechtest du Vorschlaege?",
        response_mode="clarify_before_execute",
        recent_assistant_turns=(
            "Was genau suchst du?",
            "Welche Richtung meinst du?",
        ),
    )

    assert "repeated_clarify" in drift_types


def test_detects_empty_context_on_followup_with_state_anchor() -> None:
    drift_types = _types(
        query="du weisst doch wofuer",
        reply="Ich brauche mehr Kontext.",
        dominant_turn_type="followup",
        response_mode="resume_open_loop",
        conversation_state={"active_topic": "Ausflug ab Frankfurt", "open_loop": "Kulturziele vorschlagen"},
        meta_classification={"meta_context_bundle": {"context_slots": []}},
    )

    assert "empty_context_on_followup" in drift_types


def test_detects_false_context_empty_claim_when_state_exists() -> None:
    drift_types = _types(
        query="worueber hatte ich dich eben gebeten",
        reply="Ich kann keinen vorherigen Kontext sehen.",
        dominant_turn_type="followup",
        conversation_state={"active_goal": "KI-Startup-Beratung"},
        meta_classification={"meta_context_bundle": {"context_slots": [{"slot": "open_loop"}]}},
    )

    assert "false_context_empty_claim" in drift_types


def test_detects_execute_blocked_by_mode() -> None:
    drift_types = _types(
        query="erstelle die pdf aus /tmp/test.odt",
        reply="Der Interaktionsmodus blockiert jede Ausfuehrung und keine Toolnutzung ist erlaubt.",
        response_mode="execute",
    )

    assert "execute_blocked_by_mode" in drift_types


def test_detects_mode_discussion_loop_for_action_request() -> None:
    drift_types = _types(
        query="fuehre aus: erstelle die pdf",
        reply="Du musst in den Aktionsmodus wechseln, der aktuelle Interaktionsmodus ist think_partner.",
        response_mode="execute",
    )

    assert "mode_discussion_loop" in drift_types


def test_does_not_flag_single_legitimate_clarification() -> None:
    drift_types = _types(
        query="ich will einen ausflug machen",
        reply="Welche Richtung suchst du: Natur, Stadt oder Kultur?",
        response_mode="clarify_before_execute",
        recent_assistant_turns=(),
    )

    assert drift_types == set()


def test_payload_contains_actionable_fields() -> None:
    signals = detect_live_drifts(
        query="erstelle die pdf aus /tmp/test.odt",
        reply="Der Interaktionsmodus blockiert jede Ausfuehrung.",
        response_mode="execute",
    )

    payload = signals[0].to_dict()
    assert payload["drift_type"] == "execute_blocked_by_mode"
    assert payload["confidence"] > 0
    assert payload["anchor"]
    assert payload["recommended_action"]
    assert payload["reasons"]


@given(
    verb=st.sampled_from(("erstelle", "sende", "wandle", "recherchiere")),
    obj=st.text(min_size=8, max_size=80).filter(lambda value: "\x00" not in value),
)
@settings(max_examples=40)
def test_hypothesis_execute_mode_block_is_always_detected(verb: str, obj: str) -> None:
    drift_types = _types(
        query=f"{verb} {obj}",
        reply="Interaktionsmodus blockiert, keine Toolnutzung erlaubt.",
        response_mode="execute",
    )

    assert "execute_blocked_by_mode" in drift_types


@given(
    topic=st.text(min_size=5, max_size=80).filter(lambda value: "\x00" not in value),
)
@settings(max_examples=40)
def test_hypothesis_followup_with_state_and_empty_slots_is_detected(topic: str) -> None:
    drift_types = _types(
        query="mach das",
        reply="Ich brauche mehr Kontext.",
        dominant_turn_type="followup",
        response_mode="resume_open_loop",
        conversation_state={"active_topic": topic},
        meta_classification={"meta_context_bundle": {"context_slots": []}},
    )

    assert "empty_context_on_followup" in drift_types

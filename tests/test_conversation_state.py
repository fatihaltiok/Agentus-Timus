from orchestration.conversation_state import (
    apply_turn_interpretation,
    apply_pending_followup_prompt,
    conversation_state_to_dict,
    normalize_conversation_state,
    touch_conversation_state,
)


def test_normalize_conversation_state_seeds_from_pending_followup_prompt():
    state = normalize_conversation_state(
        None,
        session_id="canvas_demo",
        last_updated="2026-04-06T16:40:00Z",
        pending_followup_prompt="Welche Option soll ich zuerst angehen?",
    )

    assert state.schema_version == 1
    assert state.session_id == "canvas_demo"
    assert state.open_loop == "Welche Option soll ich zuerst angehen?"
    assert state.next_expected_step == "Welche Option soll ich zuerst angehen?"
    assert "pending_followup_prompt" in state.state_source
    assert state.updated_at == "2026-04-06T16:40:00Z"


def test_apply_pending_followup_prompt_clears_seeded_open_loop_when_removed():
    seeded = apply_pending_followup_prompt(
        None,
        session_id="canvas_demo",
        prompt="Welche Option soll ich zuerst angehen?",
        updated_at="2026-04-06T16:41:00Z",
    )

    cleared = apply_pending_followup_prompt(
        seeded,
        session_id="canvas_demo",
        prompt="",
        updated_at="2026-04-06T16:42:00Z",
    )

    assert cleared.open_loop == ""
    assert cleared.next_expected_step == ""
    assert "pending_followup_prompt" not in cleared.state_source
    assert cleared.updated_at == "2026-04-06T16:42:00Z"


def test_conversation_state_serialization_normalizes_lists_and_confidence():
    payload = conversation_state_to_dict(
        {
            "active_topic": "News-Qualitaet",
            "preferences": ["Reuters zuerst", "Reuters zuerst", "", "kurz antworten"],
            "recent_corrections": ["nicht wieder nur Hintergrundquellen"],
            "constraints": ["nur aktuelle Meldungen"],
            "open_questions": ["Welche Agenturquelle zuerst?"],
            "state_source": ["pending_followup_prompt", "pending_followup_prompt", "session_summary"],
            "topic_confidence": 4,
            "turn_type_hint": "preference_update",
        },
        session_id="canvas_demo",
        last_updated="2026-04-06T16:43:00Z",
    )

    assert payload["session_id"] == "canvas_demo"
    assert payload["preferences"] == ["Reuters zuerst", "kurz antworten"]
    assert payload["state_source"] == ["pending_followup_prompt", "session_summary"]
    assert payload["topic_confidence"] == 1.0
    assert payload["turn_type_hint"] == "preference_update"
    assert payload["updated_at"] == "2026-04-06T16:43:00Z"


def test_touch_conversation_state_only_updates_timestamp_and_preserves_fields():
    touched = touch_conversation_state(
        {
            "active_topic": "aktuelle Weltlage",
            "active_goal": "belastbare Newslage",
            "open_loop": "Reuters zuerst nutzen",
            "preferences": ["Agenturquellen priorisieren"],
        },
        session_id="canvas_demo",
        updated_at="2026-04-06T16:44:00Z",
    )

    assert touched.active_topic == "aktuelle Weltlage"
    assert touched.active_goal == "belastbare Newslage"
    assert touched.open_loop == "Reuters zuerst nutzen"
    assert touched.preferences == ("Agenturquellen priorisieren",)
    assert touched.updated_at == "2026-04-06T16:44:00Z"


def test_apply_turn_interpretation_updates_preferences_and_turn_hint():
    updated = apply_turn_interpretation(
        None,
        session_id="canvas_demo",
        dominant_turn_type="behavior_instruction",
        response_mode="acknowledge_and_store",
        state_effects={
            "update_preferences": True,
            "set_next_expected_step": True,
            "keep_active_topic": True,
        },
        effective_query="dann mach das in zukunft so dass du bei news agenturmeldungen priorisierst",
        active_topic="aktuelle Weltlage",
        active_goal="belastbare Live-News",
        dialog_constraints=["aktuell"],
        next_step="bei News Agenturquellen zuerst nutzen",
        confidence=0.86,
        updated_at="2026-04-06T16:45:00Z",
    )

    assert updated.turn_type_hint == "behavior_instruction"
    assert updated.active_topic == "aktuelle Weltlage"
    assert updated.active_goal == "belastbare Live-News"
    assert "dann mach das in zukunft so dass du bei news agenturmeldungen priorisierst" in updated.preferences
    assert updated.next_expected_step == "bei News Agenturquellen zuerst nutzen"
    assert "turn_understanding" in updated.state_source
    assert updated.topic_confidence == 0.86

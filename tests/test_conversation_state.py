from orchestration.conversation_state import (
    apply_runtime_plan_state,
    apply_turn_interpretation,
    apply_pending_followup_prompt,
    conversation_state_to_dict,
    decay_conversation_state,
    derive_topic_state_transition,
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


def test_normalize_conversation_state_ignores_generic_pending_followup_prompt():
    state = normalize_conversation_state(
        {
            "open_loop": "Was brauchst du?",
            "next_expected_step": "Was brauchst du?",
            "state_source": ["pending_followup_prompt", "session_summary"],
        },
        session_id="canvas_demo",
        last_updated="2026-04-20T12:00:00Z",
        pending_followup_prompt="Was brauchst du?",
    )

    assert state.open_loop == ""
    assert state.next_expected_step == ""
    assert "pending_followup_prompt" not in state.state_source


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


def test_normalize_conversation_state_promotes_active_plan_into_open_loop_and_next_step():
    state = normalize_conversation_state(
        {
            "active_goal": "YouTube-Inhalt extrahieren",
            "active_plan": {
                "plan_id": "yt-plan-1",
                "plan_mode": "multi_step_execution",
                "goal": "YouTube-Inhalt extrahieren",
                "next_step_id": "visual_access",
                "next_step_title": "YouTube-Seite oeffnen",
                "next_step_agent": "visual",
                "step_count": 3,
            },
        },
        session_id="canvas_plan",
        last_updated="2026-04-18T10:00:00Z",
    )

    assert state.active_plan is not None
    assert state.active_plan.plan_id == "yt-plan-1"
    assert state.active_plan.next_step_title == "YouTube-Seite oeffnen"
    assert state.open_loop == "YouTube-Seite oeffnen"
    assert state.next_expected_step == "YouTube-Seite oeffnen"
    assert "active_plan" in state.state_source


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


def test_apply_turn_interpretation_removes_last_preference():
    updated = apply_turn_interpretation(
        {
            "active_topic": "Antwortstil",
            "active_goal": "passende Dialogpraeferenzen nutzen",
            "preferences": [
                "antworte kurz",
                "nutze bei PDF zuerst lokale Tools",
            ],
        },
        session_id="canvas_demo",
        dominant_turn_type="behavior_instruction",
        response_mode="acknowledge_and_store",
        state_effects={
            "remove_last_preference": True,
            "set_next_expected_step": True,
            "keep_active_topic": True,
        },
        effective_query="vergiss die letzte praferenz die ich dir gegeben habe",
        active_topic="Antwortstil",
        active_goal="passende Dialogpraeferenzen nutzen",
        next_step="letzte Praeferenz entfernt",
        confidence=0.86,
        updated_at="2026-04-27T15:10:00Z",
    )

    assert updated.preferences == ("antworte kurz",)
    assert updated.turn_type_hint == "behavior_instruction"
    assert updated.next_expected_step == "letzte Praeferenz entfernt"


def test_apply_turn_interpretation_tracks_active_domain_and_clears_open_loop_on_domain_shift():
    updated = apply_turn_interpretation(
        {
            "active_topic": "Twilio Setup",
            "active_goal": "Anruffunktion vorbereiten",
            "active_domain": "setup_build",
            "open_loop": "Twilio Credentials pruefen",
            "next_expected_step": "Twilio Credentials pruefen",
        },
        session_id="canvas_demo",
        dominant_turn_type="new_task",
        response_mode="execute",
        state_effects={"shift_active_topic": True},
        effective_query="wo kann ich am Wochenende hin in Deutschland",
        active_topic="Ausflugsziele in Deutschland",
        active_goal="Staedte und Kultur fuer das Wochenende finden",
        active_domain="travel_advisory",
        next_step="",
        confidence=0.74,
        updated_at="2026-04-24T20:00:00Z",
    )

    assert updated.active_domain == "travel_advisory"
    assert updated.open_loop == ""
    assert updated.next_expected_step == ""
    assert "domain_shift" in updated.state_source


def test_apply_turn_interpretation_persists_active_plan_and_resumes_next_step():
    updated = apply_turn_interpretation(
        {
            "active_topic": "YouTube-Analyse",
            "active_goal": "Videoinhalt sammeln",
        },
        session_id="canvas_plan",
        dominant_turn_type="followup",
        response_mode="resume_open_loop",
        state_effects={"keep_active_topic": True},
        effective_query="weiter",
        active_topic="YouTube-Analyse",
        active_goal="Videoinhalt sammeln",
        next_step="",
        active_plan={
            "plan_id": "yt-plan-1",
            "plan_mode": "multi_step_execution",
            "goal": "Videoinhalt sammeln",
            "next_step_id": "research_synthesis",
            "next_step_title": "Quellen und Transcript verdichten",
            "next_step_agent": "research",
            "step_count": 3,
        },
        confidence=0.82,
        updated_at="2026-04-18T10:01:00Z",
    )

    assert updated.active_plan is not None
    assert updated.active_plan.plan_id == "yt-plan-1"
    assert updated.active_plan.next_step_id == "research_synthesis"
    assert updated.next_expected_step == "Quellen und Transcript verdichten"
    assert updated.open_loop == "Quellen und Transcript verdichten"
    assert "active_plan" in updated.state_source


def test_apply_turn_interpretation_retargets_advisory_open_loop_to_constraint_summary():
    updated = apply_turn_interpretation(
        {
            "active_topic": "Ausflugsideen",
            "active_goal": "ich hab Lust einen Ausflug zu machen",
            "active_domain": "travel_advisory",
            "open_loop": "Sag mir nur: was ist die Richtung, die dich gerade reizt?",
            "next_expected_step": "Sag mir nur: was ist die Richtung, die dich gerade reizt?",
        },
        session_id="canvas_advisory",
        dominant_turn_type="followup",
        response_mode="resume_open_loop",
        state_effects={"shift_active_topic": True},
        effective_query="am Wochenende in Ruhe Stadt",
        active_topic="am Wochenende in Ruhe Stadt | einen Ausflug mit Kultur",
        active_goal="am Wochenende in Ruhe Stadt | einen Ausflug mit Kultur",
        active_domain="travel_advisory",
        next_step="am Wochenende in Ruhe Stadt | einen Ausflug mit Kultur",
        confidence=0.84,
        updated_at="2026-04-26T11:10:00Z",
    )

    assert "am Wochenende in Ruhe Stadt" in updated.active_goal
    assert "am Wochenende in Ruhe Stadt" in updated.next_expected_step
    assert "am Wochenende in Ruhe Stadt" in updated.open_loop
    assert "Sag mir nur" not in updated.open_loop


def test_apply_runtime_plan_state_advances_open_loop_to_new_next_step():
    updated = apply_runtime_plan_state(
        {
            "active_topic": "YouTube-Analyse",
            "active_goal": "Videoinhalt sammeln",
            "active_plan": {
                "plan_id": "yt-plan-1",
                "plan_mode": "multi_step_execution",
                "goal": "Videoinhalt sammeln",
                "next_step_id": "visual_access",
                "next_step_title": "YouTube-Seite oeffnen",
                "next_step_agent": "visual",
                "step_count": 3,
            },
        },
        session_id="canvas_plan",
        active_plan={
            "plan_id": "yt-plan-1",
            "plan_mode": "multi_step_execution",
            "goal": "Videoinhalt sammeln",
            "next_step_id": "research_synthesis",
            "next_step_title": "Quellen und Transcript verdichten",
            "next_step_agent": "research",
            "last_completed_step_id": "visual_access",
            "last_completed_step_title": "YouTube-Seite oeffnen",
            "step_count": 3,
            "status": "active",
        },
        updated_at="2026-04-18T20:45:00Z",
    )

    assert updated.active_plan is not None
    assert updated.active_plan.next_step_id == "research_synthesis"
    assert updated.active_plan.last_completed_step_id == "visual_access"
    assert updated.open_loop == "Quellen und Transcript verdichten"
    assert updated.next_expected_step == "Quellen und Transcript verdichten"
    assert "runtime_plan" in updated.state_source


def test_apply_runtime_plan_state_clears_completed_plan_from_state():
    updated = apply_runtime_plan_state(
        {
            "active_topic": "YouTube-Analyse",
            "active_goal": "Videoinhalt sammeln",
            "open_loop": "Quellen und Transcript verdichten",
            "next_expected_step": "Quellen und Transcript verdichten",
            "active_plan": {
                "plan_id": "yt-plan-1",
                "plan_mode": "multi_step_execution",
                "goal": "Videoinhalt sammeln",
                "next_step_id": "research_synthesis",
                "next_step_title": "Quellen und Transcript verdichten",
                "next_step_agent": "research",
                "step_count": 3,
            },
        },
        session_id="canvas_plan",
        active_plan={
            "plan_id": "yt-plan-1",
            "plan_mode": "multi_step_execution",
            "goal": "Videoinhalt sammeln",
            "next_step_id": "",
            "last_completed_step_id": "document_output",
            "last_completed_step_title": "Dokument ausgeben",
            "step_count": 3,
            "status": "completed",
        },
        updated_at="2026-04-18T20:46:00Z",
    )

    assert updated.active_plan is None
    assert updated.active_goal == "Videoinhalt sammeln"
    assert updated.open_loop == ""
    assert updated.next_expected_step == ""
    assert "runtime_plan" in updated.state_source


def test_derive_topic_state_transition_detects_clean_topic_shift():
    transition = derive_topic_state_transition(
        {
            "active_topic": "aktuelle Weltlage und News-Qualitaet",
            "active_goal": "belastbare Live-News",
            "open_loop": "Reuters zuerst pruefen",
        },
        session_id="canvas_demo",
        dominant_turn_type="new_task",
        response_mode="execute",
        state_effects={"shift_active_topic": True},
        effective_query="lass uns ueber browser automation reden",
        active_topic="browser automation und ui-workflows",
        active_goal="browser automation analysieren",
        next_step="welche sites zuerst pruefen",
    )

    assert transition.topic_shift_detected is True
    assert transition.previous_topic == "aktuelle Weltlage und News-Qualitaet"
    assert transition.next_topic == "browser automation und ui-workflows"
    assert transition.next_goal == "browser automation analysieren"
    assert transition.open_loop_state == "cleared"
    assert transition.next_open_loop == ""


def test_apply_turn_interpretation_adds_open_question_for_clarification():
    updated = apply_turn_interpretation(
        {
            "active_topic": "aktuelle Weltlage",
            "active_goal": "brauchbare Live-News",
        },
        session_id="canvas_demo",
        dominant_turn_type="clarification",
        response_mode="clarify_before_execute",
        state_effects={"keep_active_topic": True},
        effective_query="was genau meinst du mit agenturmeldungen?",
        active_topic="aktuelle Weltlage",
        active_goal="brauchbare Live-News",
        next_step="was genau meinst du mit agenturmeldungen?",
        confidence=0.8,
        updated_at="2026-04-07T11:30:00Z",
    )

    assert "was genau meinst du mit agenturmeldungen?" in updated.open_questions


def test_apply_turn_interpretation_clears_old_open_questions_on_topic_shift():
    updated = apply_turn_interpretation(
        {
            "active_topic": "aktuelle Weltlage",
            "active_goal": "Live-News",
            "open_loop": "Reuters zuerst pruefen",
            "next_expected_step": "Reuters zuerst pruefen",
            "open_questions": ["Welche Agentur zuerst?"],
        },
        session_id="canvas_demo",
        dominant_turn_type="new_task",
        response_mode="execute",
        state_effects={"shift_active_topic": True},
        effective_query="lass uns jetzt ueber browser automation reden",
        active_topic="browser automation",
        active_goal="browser-workflow verstehen",
        next_step="",
        confidence=0.77,
        updated_at="2026-04-07T11:31:00Z",
    )

    assert updated.active_topic == "browser automation"
    assert updated.active_goal == "browser-workflow verstehen"
    assert updated.open_loop == ""
    assert updated.next_expected_step == ""
    assert updated.open_questions == ()
    assert "topic_shift" in updated.state_source


def test_apply_turn_interpretation_seeds_topic_from_preference_update_query_when_empty():
    updated = apply_turn_interpretation(
        {},
        session_id="canvas_d04_pref",
        dominant_turn_type="preference_update",
        response_mode="acknowledge_and_store",
        state_effects={
            "update_preferences": True,
            "set_next_expected_step": True,
            "keep_active_topic": True,
        },
        effective_query="bei news bitte zuerst agenturquellen",
        active_topic="",
        active_goal="",
        next_step="bei news bitte zuerst agenturquellen",
        confidence=0.86,
        updated_at="2026-04-07T14:10:00Z",
    )

    assert updated.active_topic == "bei news bitte zuerst agenturquellen"
    assert updated.active_goal == "bei news bitte zuerst agenturquellen"
    assert updated.next_expected_step == "bei news bitte zuerst agenturquellen"


def test_decay_conversation_state_clears_stale_open_loop_after_three_days():
    decayed, summary = decay_conversation_state(
        {
            "active_topic": "aktuelle Weltlage",
            "active_goal": "brauchbare Live-News",
            "open_loop": "Reuters und AP zuerst pruefen",
            "next_expected_step": "Reuters und AP zuerst pruefen",
            "open_questions": ["Welche Agentur zuerst?"],
            "updated_at": "2026-04-05T10:00:00Z",
            "topic_confidence": 0.9,
        },
        session_id="canvas_decay",
        now="2026-04-08T12:00:00Z",
    )

    assert decayed.active_topic == "aktuelle Weltlage"
    assert decayed.open_loop == ""
    assert decayed.next_expected_step == ""
    assert decayed.open_questions == ()
    assert "state_decay" in decayed.state_source
    assert summary["applied"] is True
    assert "stale_open_loop" in summary["reasons"]


def test_decay_conversation_state_clears_stale_active_plan_after_three_days():
    decayed, summary = decay_conversation_state(
        {
            "active_topic": "YouTube-Analyse",
            "active_goal": "Videoinhalt sammeln",
            "active_plan": {
                "plan_id": "yt-plan-1",
                "plan_mode": "multi_step_execution",
                "goal": "Videoinhalt sammeln",
                "next_step_id": "visual_access",
                "next_step_title": "YouTube-Seite oeffnen",
                "step_count": 3,
            },
            "updated_at": "2026-04-10T09:00:00Z",
        },
        session_id="canvas_plan",
        now="2026-04-13T10:00:00Z",
    )

    assert decayed.active_plan is None
    assert summary["applied"] is True
    assert "stale_active_plan" in summary["reasons"]

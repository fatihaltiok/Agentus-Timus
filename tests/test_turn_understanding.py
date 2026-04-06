from orchestration.turn_understanding import (
    build_turn_understanding_input,
    detect_turn_signals,
    interpret_turn,
)


def test_interpret_turn_marks_behavior_instruction_as_acknowledge_and_store():
    turn_input = build_turn_understanding_input(
        raw_query="dann mach das in zukunft so dass du auf echtzeit agenturmeldungen zugreifst",
        effective_query="dann mach das in zukunft so dass du auf echtzeit agenturmeldungen zugreifst",
        dialog_state={
            "active_topic": "aktuelle Weltlage und News-Qualitaet",
            "open_goal": "belastbare Live-News",
        },
        semantic_review_hints=["behavior_preference_alignment"],
    )

    interpretation = interpret_turn(turn_input)

    assert interpretation.dominant_turn_type == "behavior_instruction"
    assert interpretation.response_mode == "acknowledge_and_store"
    assert interpretation.route_bias == "meta_only"
    assert interpretation.state_effects.update_preferences is True
    assert interpretation.state_effects.set_next_expected_step is True


def test_interpret_turn_marks_correction_and_complaint_before_followup():
    turn_input = build_turn_understanding_input(
        raw_query="# FOLLOW-UP CONTEXT\n# CURRENT USER QUERY\nso meinte ich das nicht, du hast die Antwort voellig aus dem Kontext gezogen",
        effective_query="so meinte ich das nicht, du hast die Antwort voellig aus dem Kontext gezogen",
        dialog_state={
            "active_topic": "Preisvergleich",
            "open_goal": "brauchbare aktuelle Preise",
            "compressed_followup_parsed": False,
            "active_topic_reused": True,
        },
        semantic_review_hints=[],
        context_anchor_applied=True,
    )

    interpretation = interpret_turn(turn_input)

    assert interpretation.dominant_turn_type == "correction"
    assert interpretation.response_mode == "correct_previous_path"
    assert interpretation.state_effects.update_recent_corrections is True


def test_interpret_turn_marks_result_extraction_followup_as_execute():
    turn_input = build_turn_understanding_input(
        raw_query="# FOLLOW-UP CONTEXT\n# CURRENT USER QUERY\nhole die preise heraus und liste sie mir aus",
        effective_query="hole die preise heraus und liste sie mir aus",
        dialog_state={
            "active_topic": "LLM-Preise",
            "open_goal": "Preise aus bestehender Quelle extrahieren",
            "active_topic_reused": True,
        },
        semantic_review_hints=[],
        context_anchor_applied=True,
    )

    interpretation = interpret_turn(turn_input)

    assert interpretation.dominant_turn_type == "result_extraction"
    assert interpretation.response_mode == "execute"
    assert interpretation.route_bias == "follow_existing_lane"


def test_detect_turn_signals_exposes_followup_state_and_resume_language():
    turn_input = build_turn_understanding_input(
        raw_query="# FOLLOW-UP CONTEXT\n# CURRENT USER QUERY\nok fang an",
        effective_query="ok fang an",
        dialog_state={
            "active_topic": "Google Cloud Projekt",
            "open_goal": "Projekt anlegen",
            "next_step": "Google Cloud Projekt anlegen",
        },
        semantic_review_hints=[],
        context_anchor_applied=True,
    )

    signals = detect_turn_signals(turn_input)
    interpretation = interpret_turn(turn_input)

    assert "followup_context_present" in signals
    assert "handover_resume_language" in signals
    assert interpretation.dominant_turn_type == "handover_resume"
    assert interpretation.response_mode == "resume_open_loop"

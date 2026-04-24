from orchestration.meta_interaction_mode import build_meta_interaction_mode


def test_build_meta_interaction_mode_detects_think_partner_for_explicit_opinion() -> None:
    mode = build_meta_interaction_mode(
        effective_query="Ohne Recherche: Was ist deine Meinung dazu?",
        meta_request_frame={
            "frame_kind": "direct_answer",
            "task_domain": "general_advisory",
            "execution_mode": "answer_directly",
        },
        policy_decision={"answer_shape": "direct_recommendation", "policy_reason": "baseline_turn_mode"},
    )

    assert mode.mode == "think_partner"
    assert mode.explicit_override is True
    assert mode.execution_policy == "no_research_no_execution"


def test_build_meta_interaction_mode_detects_inspect_for_research_advisory() -> None:
    mode = build_meta_interaction_mode(
        effective_query="Mach dich schlau ueber Kreislaufwirtschaft im Bauwesen und hilf mir dann.",
        meta_request_frame={
            "frame_kind": "new_task",
            "task_domain": "research_advisory",
            "execution_mode": "plan_and_delegate",
        },
        policy_decision={"answer_shape": "action_first", "policy_reason": "baseline_turn_mode"},
    )

    assert mode.mode == "inspect"
    assert mode.explicit_override is False
    assert mode.mode_reason == "task_domain:research_advisory"
    assert mode.execution_policy == "bounded_evidence_only"


def test_build_meta_interaction_mode_detects_assist_for_setup_execution() -> None:
    mode = build_meta_interaction_mode(
        effective_query="Richte fuer mich eine Twilio-Anruffunktion mit Inworld ein.",
        meta_request_frame={
            "frame_kind": "new_task",
            "task_domain": "setup_build",
            "execution_mode": "plan_and_delegate",
        },
        policy_decision={"answer_shape": "action_first", "policy_reason": "baseline_turn_mode"},
    )

    assert mode.mode == "assist"
    assert mode.explicit_override is False
    assert mode.mode_reason == "task_domain:setup_build"
    assert mode.execution_policy == "plan_delegate_or_execute"


def test_build_meta_interaction_mode_keeps_travel_advisory_in_think_partner() -> None:
    mode = build_meta_interaction_mode(
        effective_query="wo kann ich am Wochenende hin in Deutschland",
        meta_request_frame={
            "frame_kind": "new_task",
            "task_domain": "travel_advisory",
            "execution_mode": "plan_and_delegate",
        },
        policy_decision={"answer_shape": "action_first", "policy_reason": "baseline_turn_mode"},
    )

    assert mode.mode == "think_partner"
    assert mode.explicit_override is False
    assert mode.mode_reason == "task_domain:travel_advisory"
    assert mode.execution_policy == "no_research_no_execution"

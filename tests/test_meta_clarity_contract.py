from __future__ import annotations

from orchestration.meta_clarity_contract import (
    apply_meta_clarity_to_bundle,
    build_meta_clarity_contract,
    filter_working_memory_context,
)


def test_build_meta_clarity_contract_for_direct_recommendation_limits_context() -> None:
    contract = build_meta_clarity_contract(
        effective_query="lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",
        response_mode="summarize_state",
        policy_decision={
            "answer_shape": "direct_recommendation",
            "policy_reason": "next_step_summary_request",
        },
        task_type="single_lane",
        goal_spec={},
        task_decomposition={"goal": "Den naechsten Hauptblock nennen"},
        meta_execution_plan={},
    )

    assert contract.request_kind == "direct_recommendation"
    assert contract.direct_answer_required is True
    assert contract.answer_obligation == "answer_now_with_single_recommendation"
    assert contract.completion_condition == "next_recommended_block_or_step_named"
    assert contract.allowed_context_slots == (
        "current_query",
        "conversation_state",
        "open_loop",
        "recent_user_turn",
        "historical_topic_memory",
    )
    assert "topic_memory" in contract.forbidden_context_slots
    assert "preference_memory" in contract.forbidden_context_slots
    assert contract.allowed_working_memory_sections == ("KURZZEITKONTEXT",)
    assert contract.max_related_memories == 0
    assert contract.max_recent_events == 4


def test_apply_meta_clarity_to_bundle_filters_forbidden_slots() -> None:
    bundle = {
        "context_slots": [
            {"slot": "current_query", "priority": 100, "content": "was ist der naechste block"},
            {"slot": "conversation_state", "priority": 90, "content": "active_topic: Phase F"},
            {"slot": "open_loop", "priority": 80, "content": "Nachfolger bestimmen"},
            {"slot": "topic_memory", "priority": 70, "content": "Offenbach Standort und GPS-Kontext"},
            {"slot": "preference_memory", "priority": 60, "content": "Bei Telefonie zuerst Twilio"},
            {"slot": "historical_topic_memory", "priority": 50, "content": "Phase F ist im Kern abgeschlossen"},
        ],
        "suppressed_context": [],
    }
    contract = build_meta_clarity_contract(
        effective_query="sag was als naechstes ansteht",
        response_mode="summarize_state",
        policy_decision={
            "answer_shape": "direct_recommendation",
            "policy_reason": "next_step_summary_request",
        },
        task_type="single_lane",
        goal_spec={},
        task_decomposition={"goal": "Naechsten Block nennen"},
        meta_execution_plan={},
    ).to_dict()

    filtered = apply_meta_clarity_to_bundle(bundle, contract)

    slot_types = [item["slot"] for item in filtered["context_slots"]]
    assert slot_types == [
        "current_query",
        "conversation_state",
        "open_loop",
        "historical_topic_memory",
    ]
    assert any(
        item["reason"] == "clarity_contract_filtered_context" and item["source"] == "topic_memory"
        for item in filtered["suppressed_context"]
    )
    assert any(
        item["reason"] == "clarity_contract_filtered_context" and item["source"] == "preference_memory"
        for item in filtered["suppressed_context"]
    )


def test_filter_working_memory_context_keeps_only_allowed_sections() -> None:
    contract = build_meta_clarity_contract(
        effective_query="sag was als naechstes ansteht",
        response_mode="summarize_state",
        policy_decision={
            "answer_shape": "direct_recommendation",
            "policy_reason": "next_step_summary_request",
        },
        task_type="single_lane",
        goal_spec={},
        task_decomposition={"goal": "Naechsten Block nennen"},
        meta_execution_plan={},
    ).to_dict()
    context = (
        "# WORKING MEMORY\n\n"
        "KURZZEITKONTEXT\nkurze relevante Turns\n\n"
        "LANGZEITKONTEXT\nalte thematische Fragmente\n\n"
        "STABILER_KONTEXT\nself model und Praeferenzen"
    )

    filtered = filter_working_memory_context(context, contract)

    assert "KURZZEITKONTEXT" in filtered
    assert "LANGZEITKONTEXT" not in filtered
    assert "STABILER_KONTEXT" not in filtered

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
    assert contract.delegation_mode == "single_evidence_fetch"
    assert contract.max_delegate_calls == 1
    assert contract.allowed_delegate_agents == ("document",)
    assert contract.force_answer_after_delegate_budget is True


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


def test_build_meta_clarity_contract_for_historical_recall_disallows_delegation() -> None:
    contract = build_meta_clarity_contract(
        effective_query="woran haben wir gestern bei Kanada gearbeitet",
        response_mode="summarize_state",
        policy_decision={
            "answer_shape": "historical_topic_state",
            "policy_reason": "historical_topic_recall",
        },
        task_type="single_lane",
        goal_spec={},
        task_decomposition={"goal": "Gesternes Kanada-Thema rekapitulieren"},
        meta_execution_plan={},
    )

    assert contract.request_kind == "historical_recall"
    assert contract.delegation_mode == "direct_only"
    assert contract.max_delegate_calls == 0
    assert contract.allowed_delegate_agents == ()
    assert contract.force_answer_after_delegate_budget is False


def test_build_meta_clarity_contract_for_setup_build_binds_controlled_delegate_budget() -> None:
    contract = build_meta_clarity_contract(
        effective_query=(
            "richte fuer mich eine anruffunktion ein du sollst mich ueber twilio anrufen "
            "koennen mit der stimme von inworld.ai lennart"
        ),
        response_mode="execute",
        policy_decision={
            "answer_shape": "action_first",
            "policy_reason": "baseline_turn_mode",
        },
        task_type="single_lane",
        goal_spec={},
        task_decomposition={"goal": "Twilio und Inworld fuer Anruffunktion integrieren"},
        meta_execution_plan={},
    )

    assert contract.request_kind == "execute_task"
    assert contract.answer_obligation == "inspect_preparation_then_plan_or_execute"
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
    assert contract.max_recent_events == 6
    assert contract.delegation_mode == "controlled_orchestration"
    assert contract.max_delegate_calls == 2
    assert contract.allowed_delegate_agents == ("executor", "research", "document")
    assert "assistant_fallback_context" in contract.forbidden_context_slots


def test_build_meta_clarity_contract_for_setup_build_preparation_check_forces_single_evidence_step() -> None:
    contract = build_meta_clarity_contract(
        effective_query=(
            "richte fuer mich eine anruffunktion ein und schau mal nach ob es schon "
            "vorbereitungen gibt"
        ),
        response_mode="execute",
        policy_decision={
            "answer_shape": "action_first",
            "policy_reason": "baseline_turn_mode",
        },
        task_type="single_lane",
        goal_spec={},
        task_decomposition={"goal": "Vorhandene Vorbereitungen fuer Twilio/Inworld pruefen"},
        meta_execution_plan={},
    )

    assert contract.request_kind == "execute_task"
    assert contract.answer_obligation == "inspect_preparation_then_report"
    assert contract.completion_condition == "existing_preparations_or_real_gap_named"
    assert contract.max_delegate_calls == 1
    assert contract.allowed_delegate_agents == ("executor", "document")
    assert contract.force_answer_after_delegate_budget is True


def test_build_meta_clarity_contract_for_migration_work_prefers_focused_research() -> None:
    contract = build_meta_clarity_contract(
        effective_query="suche mir Moeglichkeiten in Kanada Fuss zu fassen",
        response_mode="execute",
        policy_decision={
            "answer_shape": "action_first",
            "policy_reason": "baseline_turn_mode",
        },
        task_type="knowledge_research",
        goal_spec={},
        task_decomposition={"goal": "Pruefen, wie man in Kanada arbeiten und Fuss fassen kann"},
        meta_execution_plan={},
    )

    assert contract.request_kind == "execute_task"
    assert contract.answer_obligation == "return_actionable_migration_or_work_path"
    assert contract.allowed_working_memory_sections == ("KURZZEITKONTEXT", "LANGZEITKONTEXT")
    assert contract.max_related_memories == 2
    assert contract.max_recent_events == 6
    assert contract.delegation_mode == "focused_research"
    assert contract.max_delegate_calls == 1
    assert contract.allowed_delegate_agents == ("research",)
    assert "preference_memory" in contract.forbidden_context_slots
    assert "semantic_recall" in contract.forbidden_context_slots


def test_build_meta_clarity_contract_for_planning_advisory_prefers_direct_planning() -> None:
    contract = build_meta_clarity_contract(
        effective_query="Plane meinen Tag fuer morgen",
        response_mode="execute",
        policy_decision={
            "answer_shape": "action_first",
            "policy_reason": "baseline_turn_mode",
        },
        task_type="single_lane",
        goal_spec={},
        task_decomposition={"goal": "Einen Tagesplan fuer morgen erstellen"},
        meta_execution_plan={},
    )

    assert contract.request_kind == "execute_task"
    assert contract.answer_obligation == "collect_constraints_then_plan"
    assert contract.completion_condition == "planning_structure_or_missing_constraints_named"
    assert contract.delegation_mode == "direct_only"
    assert contract.max_delegate_calls == 0
    assert contract.allowed_delegate_agents == ()
    assert "semantic_recall" in contract.forbidden_context_slots


def test_build_meta_clarity_contract_for_research_advisory_prefers_focused_research() -> None:
    contract = build_meta_clarity_contract(
        effective_query="Mach dich schlau ueber Kreislaufwirtschaft im Bau und steh mir dann hilfreich zur Seite",
        response_mode="execute",
        policy_decision={
            "answer_shape": "action_first",
            "policy_reason": "baseline_turn_mode",
        },
        task_type="knowledge_research",
        goal_spec={},
        task_decomposition={"goal": "Thema verstehen und anschlussfaehig beraten koennen"},
        meta_execution_plan={},
    )

    assert contract.request_kind == "execute_task"
    assert contract.answer_obligation == "build_topic_understanding_then_support_followups"
    assert contract.completion_condition == "research_briefing_or_next_research_path_named"
    assert contract.allowed_context_slots == (
        "current_query",
        "conversation_state",
        "open_loop",
        "recent_user_turn",
        "historical_topic_memory",
    )
    assert contract.delegation_mode == "focused_research"
    assert contract.max_delegate_calls == 1
    assert contract.allowed_delegate_agents == ("executor",)
    assert "topic_memory" in contract.forbidden_context_slots
    assert "semantic_recall" in contract.forbidden_context_slots

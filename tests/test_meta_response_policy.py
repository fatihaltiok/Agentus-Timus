from orchestration.meta_response_policy import (
    build_meta_policy_input,
    resolve_meta_response_policy,
)


def _build_policy_input(
    *,
    effective_query: str,
    dominant_turn_type: str,
    baseline_response_mode: str,
    task_type: str,
    meta_context_bundle: dict,
    meta_request_frame: dict | None = None,
    recommended_agent_chain: tuple[str, ...] = ("meta",),
) :
    return build_meta_policy_input(
        effective_query=effective_query,
        dominant_turn_type=dominant_turn_type,
        baseline_response_mode=baseline_response_mode,
        task_type=task_type,
        active_topic="",
        open_goal="",
        next_step="",
        recommended_agent_chain=recommended_agent_chain,
        meta_context_bundle=meta_context_bundle,
        meta_request_frame=meta_request_frame or {},
        preference_memory_selection={},
        topic_state_transition={},
    )


def test_meta_response_policy_uses_summary_mode_for_status_requests():
    decision = resolve_meta_response_policy(
        _build_policy_input(
            effective_query="wo stehen wir gerade",
            dominant_turn_type="followup",
            baseline_response_mode="resume_open_loop",
            task_type="simple_live_lookup",
            meta_context_bundle={
                "context_slots": [
                    {"slot": "current_query", "content": "wo stehen wir gerade"},
                    {"slot": "conversation_state", "content": "active_topic: D0.6"},
                    {"slot": "open_loop", "content": "Policy-Events verdrahten"},
                ],
            },
            recommended_agent_chain=("meta", "executor"),
        )
    )

    assert decision.response_mode == "summarize_state"
    assert decision.override_applied is True
    assert decision.task_type_override == "single_lane"
    assert decision.agent_chain_override == ("meta",)
    assert decision.recipe_enabled is False


def test_meta_response_policy_uses_direct_recommendation_for_next_step_questions():
    decision = resolve_meta_response_policy(
        _build_policy_input(
            effective_query="lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",
            dominant_turn_type="new_task",
            baseline_response_mode="execute",
            task_type="single_lane",
            meta_request_frame={
                "frame_kind": "direct_answer",
                "task_domain": "docs_status",
                "execution_mode": "answer_directly",
            },
            meta_context_bundle={
                "context_slots": [
                    {
                        "slot": "current_query",
                        "content": "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",
                    },
                    {"slot": "conversation_state", "content": "active_topic: Phase F"},
                ],
                "suppressed_context": [],
            },
            recommended_agent_chain=("meta", "executor"),
        )
    )

    assert decision.response_mode == "summarize_state"
    assert decision.override_applied is True
    assert decision.task_type_override == "single_lane"
    assert decision.agent_chain_override == ("meta",)
    assert decision.recipe_enabled is False
    assert decision.answer_shape == "direct_recommendation"
    assert "next_step_summary_language" in decision.policy_signals


def test_meta_response_policy_prioritizes_frame_direct_answer_for_docs_status():
    decision = resolve_meta_response_policy(
        _build_policy_input(
            effective_query="lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",
            dominant_turn_type="new_task",
            baseline_response_mode="execute",
            task_type="single_lane",
            meta_request_frame={
                "frame_kind": "direct_answer",
                "task_domain": "docs_status",
                "execution_mode": "answer_directly",
            },
            meta_context_bundle={
                "context_slots": [
                    {"slot": "current_query", "content": "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht"},
                ],
                "suppressed_context": [],
            },
            recommended_agent_chain=("meta", "executor"),
        )
    )

    assert decision.response_mode == "summarize_state"
    assert decision.override_applied is True
    assert decision.policy_reason == "frame_direct_answer"
    assert decision.agent_chain_override == ("meta",)


def test_meta_response_policy_clarifies_broad_action_hint_when_context_is_unreliable():
    decision = resolve_meta_response_policy(
        _build_policy_input(
            effective_query="guck mal nach aktuellen benzinpreisen",
            dominant_turn_type="followup",
            baseline_response_mode="execute",
            task_type="simple_live_lookup",
            meta_context_bundle={
                "context_slots": [
                    {"slot": "current_query", "content": "guck mal nach aktuellen benzinpreisen"},
                    {
                        "slot": "assistant_fallback_context",
                        "content": "Soll ich mit dem ersten Schritt anfangen?",
                    },
                ],
                "suppressed_context": [],
            },
            recommended_agent_chain=("meta", "executor"),
        )
    )

    assert decision.response_mode == "clarify_before_execute"
    assert decision.override_applied is True
    assert decision.task_type_override == "single_lane"
    assert decision.agent_chain_override == ("meta",)
    assert "action_requested" in decision.policy_signals


def test_meta_response_policy_keeps_simple_live_lookup_lightweight_when_context_is_sound():
    decision = resolve_meta_response_policy(
        _build_policy_input(
            effective_query="such aktuelle benzinpreise",
            dominant_turn_type="new_task",
            baseline_response_mode="execute",
            task_type="simple_live_lookup",
            meta_context_bundle={
                "context_slots": [
                    {"slot": "current_query", "content": "such aktuelle benzinpreise"},
                    {"slot": "conversation_state", "content": "topic: alltagskosten"},
                    {"slot": "recent_user_turn", "content": "was kostet benzin heute"},
                ],
                "suppressed_context": [],
            },
            recommended_agent_chain=("meta", "executor"),
        )
    )

    assert decision.response_mode == "execute"
    assert decision.override_applied is False
    assert decision.should_delegate is True
    assert decision.recipe_enabled is True


def test_meta_response_policy_preserves_acknowledge_and_store_for_preference_updates():
    decision = resolve_meta_response_policy(
        _build_policy_input(
            effective_query="bei news bitte zuerst agenturquellen",
            dominant_turn_type="behavior_instruction",
            baseline_response_mode="acknowledge_and_store",
            task_type="single_lane",
            meta_context_bundle={
                "context_slots": [
                    {"slot": "current_query", "content": "bei news bitte zuerst agenturquellen"},
                    {"slot": "conversation_state", "content": "topic: news"},
                ],
                "suppressed_context": [],
            },
        )
    )

    assert decision.response_mode == "acknowledge_and_store"
    assert decision.override_applied is False
    assert decision.should_store_preference is True


def test_meta_response_policy_uses_self_model_status_for_capability_questions():
    decision = resolve_meta_response_policy(
        _build_policy_input(
            effective_query="ist das geplant oder kannst du das jetzt schon",
            dominant_turn_type="new_task",
            baseline_response_mode="execute",
            task_type="single_lane",
            meta_context_bundle={
                "context_slots": [
                    {"slot": "current_query", "content": "ist das geplant oder kannst du das jetzt schon"},
                ],
                "suppressed_context": [],
            },
            recommended_agent_chain=("executor",),
        )
    )

    assert decision.response_mode == "summarize_state"
    assert decision.override_applied is True
    assert decision.self_model_bound_applied is True
    assert decision.task_type_override == "single_lane"
    assert decision.agent_chain_override == ("meta",)
    assert decision.answer_shape == "self_model_status"


def test_meta_response_policy_does_not_slow_explicit_system_diagnosis_with_followup_context():
    decision = resolve_meta_response_policy(
        _build_policy_input(
            effective_query="prüfe bitte den systemstatus und die logs",
            dominant_turn_type="new_task",
            baseline_response_mode="execute",
            task_type="system_diagnosis",
            meta_context_bundle={
                "context_slots": [
                    {"slot": "current_query", "content": "prüfe bitte den systemstatus und die logs"},
                    {"slot": "assistant_fallback_context", "content": "Route nach Münster ist erstellt."},
                ],
                "suppressed_context": [],
            },
        )
    )

    assert decision.response_mode == "execute"
    assert decision.override_applied is False
    assert decision.should_delegate is True

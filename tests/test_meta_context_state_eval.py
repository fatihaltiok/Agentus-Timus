from __future__ import annotations

from orchestration.meta_context_state_eval import (
    D0_META_CONTEXT_STATE_EVAL_CASES,
    evaluate_meta_context_state_case,
    summarize_meta_context_state_evals,
)


def test_d0_meta_context_state_eval_cases_all_pass():
    results = [evaluate_meta_context_state_case(case) for case in D0_META_CONTEXT_STATE_EVAL_CASES]

    assert all(result["passed"] for result in results)


def test_d0_meta_context_state_eval_behavior_instruction_tracks_acknowledge_store():
    case = next(case for case in D0_META_CONTEXT_STATE_EVAL_CASES if case.label == "behavior_instruction_news_policy")

    result = evaluate_meta_context_state_case(case)

    assert result["decision"]["dominant_turn_type"] == "behavior_instruction"
    assert result["decision"]["response_mode"] == "acknowledge_and_store"
    assert result["benchmark"]["slot_score"] >= 1.0
    assert result["benchmark"]["signal_score"] >= 1.0


def test_d0_meta_context_state_eval_complaint_plus_instruction_preserves_signal_mix():
    case = next(
        case
        for case in D0_META_CONTEXT_STATE_EVAL_CASES
        if case.label == "complaint_plus_instruction_prefers_storeable_alignment"
    )

    result = evaluate_meta_context_state_case(case)

    assert result["decision"]["dominant_turn_type"] == "behavior_instruction"
    assert "complaint_language" in result["decision"]["turn_signals"]
    assert "behavior_instruction" in result["decision"]["turn_signals"]
    assert result["context_eval"]["actual_suspicious"] is False


def test_d0_meta_context_state_eval_summary_aggregates_pass_rate_and_scores():
    summary = summarize_meta_context_state_evals(D0_META_CONTEXT_STATE_EVAL_CASES)

    assert summary["total_cases"] == len(D0_META_CONTEXT_STATE_EVAL_CASES)
    assert summary["pass_rate"] == 1.0
    assert summary["avg_score"] > 0.0
    assert summary["avg_slot_score"] > 0.0
    assert summary["avg_signal_score"] > 0.0
    assert summary["quality_score"] > 0.0
    assert summary["gate_passed"] is True
    assert "preference_instruction" in summary["by_family"]
    assert summary["by_family"]["topic_resumption"]["pass_rate"] == 1.0


def test_d0_meta_context_state_eval_covers_auth_and_approval_resume_families():
    summary = summarize_meta_context_state_evals(D0_META_CONTEXT_STATE_EVAL_CASES)

    assert "approval_resume" in summary["by_family"]
    assert "auth_resume" in summary["by_family"]
    assert summary["by_family"]["approval_resume"]["avg_signal_score"] >= 1.0
    assert summary["by_family"]["auth_resume"]["avg_slot_score"] >= 1.0

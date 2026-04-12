from __future__ import annotations

from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_promotion import (
    evaluate_compiled_task_promotion,
    evaluate_compiled_task_promotions,
)


def test_evaluate_compiled_task_promotion_promotes_strong_safe_task_to_e3() -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "cand:routing",
            "category": "routing",
            "problem": "Dispatcher fallback repeated",
            "proposed_action": "Harden dispatcher routing",
            "priority_score": 2.4,
            "source_count": 2,
            "freshness_state": "fresh",
            "verified_paths": ["main_dispatcher.py"],
        }
    )

    decision = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")

    assert decision["requested_fix_mode"] == "self_modify_safe"
    assert decision["promotion_state"] == "eligible_for_e3"
    assert decision["e3_eligible"] is True
    assert decision["e3_ready"] is True


def test_evaluate_compiled_task_promotion_keeps_policy_secret_work_human_only() -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "cand:policy",
            "category": "policy",
            "problem": "Credential handling weak",
            "proposed_action": "Change password and secret routing",
            "priority_score": 1.4,
        }
    )

    decision = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")

    assert decision["requested_fix_mode"] == "human_only"
    assert decision["promotion_state"] == "human_only"
    assert "sensitive_or_human_mediated" in decision["blocked_by"]
    assert decision["e3_ready"] is False


def test_evaluate_compiled_task_promotion_keeps_weak_signals_developer_only() -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "cand:weak",
            "category": "routing",
            "problem": "Routing weak",
            "proposed_action": "Adjust route heuristic",
            "priority_score": 0.9,
            "source_count": 1,
            "freshness_state": "fresh",
        }
    )

    decision = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")

    assert decision["requested_fix_mode"] == "developer_task"
    assert decision["promotion_state"] == "developer_only"
    assert "insufficient_compiler_evidence" in decision["blocked_by"]
    assert decision["e3_eligible"] is False


def test_evaluate_compiled_task_promotion_defers_strong_task_under_developer_rollout() -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "cand:runtime",
            "category": "runtime",
            "problem": "Runtime guard drift",
            "proposed_action": "Harden health guard threshold",
            "priority_score": 1.6,
            "source_count": 2,
            "freshness_state": "fresh",
            "verified_paths": ["server/mcp_server.py"],
        }
    )

    decision = evaluate_compiled_task_promotion(compiled, rollout_stage="developer_only")

    assert decision["requested_fix_mode"] == "self_modify_safe"
    assert decision["effective_fix_mode"] == "developer_task"
    assert decision["promotion_state"] == "deferred_by_rollout"
    assert "rollout_stage:developer_only" in decision["blocked_by"]


def test_evaluate_compiled_task_promotions_preserves_order() -> None:
    tasks = [
        compile_improvement_task(
            {
                "candidate_id": "cand:first",
                "category": "routing",
                "problem": "Routing drift",
                "proposed_action": "Harden route selection",
                "priority_score": 2.0,
                "source_count": 2,
                "freshness_state": "fresh",
                "verified_paths": ["main_dispatcher.py"],
            }
        ),
        compile_improvement_task(
            {
                "candidate_id": "cand:second",
                "category": "policy",
                "problem": "Credential issue",
                "proposed_action": "Touch password flow",
                "priority_score": 1.0,
            }
        ),
    ]

    decisions = evaluate_compiled_task_promotions(tasks, rollout_stage="self_modify_safe")

    assert [item["candidate_id"] for item in decisions] == ["cand:first", "cand:second"]

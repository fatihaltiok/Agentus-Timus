from __future__ import annotations

from hypothesis import given, strategies as st

from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


@given(
    category=st.sampled_from(["routing", "context", "policy", "runtime", "tool", "specialist", "memory", "ux_handoff"]),
    source_count=st.integers(min_value=1, max_value=4),
    freshness_state=st.sampled_from(["", "fresh", "aging", "stale"]),
    rollout_stage=st.sampled_from(["observe_only", "developer_only", "self_modify_safe"]),
)
def test_hypothesis_compiled_task_promotion_stays_in_known_fix_modes(
    category: str,
    source_count: int,
    freshness_state: str,
    rollout_stage: str,
) -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "hyp:promotion",
            "category": category,
            "problem": "Generic issue",
            "proposed_action": "Generic improvement",
            "source_count": source_count,
            "freshness_state": freshness_state,
        }
    )

    decision = evaluate_compiled_task_promotion(compiled, rollout_stage=rollout_stage)

    assert decision["requested_fix_mode"] in {"observe_only", "developer_task", "self_modify_safe", "human_only"}
    assert decision["effective_fix_mode"] in {"observe_only", "developer_task", "self_modify_safe", "human_only"}
    assert decision["promotion_state"] in {
        "human_only",
        "observe_only",
        "developer_only",
        "deferred_by_rollout",
        "eligible_for_e3",
    }


@given(rollout_stage=st.sampled_from(["observe_only", "developer_only", "self_modify_safe"]))
def test_hypothesis_do_not_autofix_never_becomes_e3_ready(rollout_stage: str) -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "hyp:human",
            "category": "policy",
            "problem": "Credential issue",
            "proposed_action": "Adjust password handling",
        }
    )

    decision = evaluate_compiled_task_promotion(compiled, rollout_stage=rollout_stage)

    assert decision["requested_fix_mode"] == "human_only"
    assert decision["e3_ready"] is False

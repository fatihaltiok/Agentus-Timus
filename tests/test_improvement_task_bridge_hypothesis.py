from __future__ import annotations

from hypothesis import given, strategies as st

from orchestration.improvement_task_bridge import build_improvement_task_bridge
from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


@given(
    category=st.sampled_from(["routing", "context", "policy", "runtime", "tool", "specialist", "memory", "ux_handoff"]),
    source_count=st.integers(min_value=1, max_value=4),
    freshness_state=st.sampled_from(["", "fresh", "aging", "stale"]),
)
def test_hypothesis_task_bridge_states_are_bounded(
    category: str,
    source_count: int,
    freshness_state: str,
) -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "hyp:bridge",
            "category": category,
            "problem": "Generic issue",
            "proposed_action": "Generic improvement",
            "source_count": source_count,
            "freshness_state": freshness_state,
        }
    )
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")

    bridge = build_improvement_task_bridge(compiled, promotion)

    assert bridge["bridge_state"] in {
        "not_e3_eligible",
        "deferred_by_promotion",
        "developer_bridge_ready",
        "self_modify_ready",
        "bridge_blocked",
    }
    assert bridge["requested_fix_mode"] in {"observe_only", "developer_task", "self_modify_safe", "human_only"}
    assert bridge["effective_fix_mode"] in {"", "observe_only", "developer_task", "self_modify_safe", "human_only"}

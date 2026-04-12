from __future__ import annotations

from hypothesis import given, strategies as st

from orchestration.improvement_task_bridge import build_improvement_task_bridge
from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_execution import build_improvement_hardening_task_payload
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


@given(
    category=st.sampled_from(["routing", "context", "policy", "runtime", "tool", "specialist", "memory", "ux_handoff"]),
    source_count=st.integers(min_value=1, max_value=4),
    freshness_state=st.sampled_from(["", "fresh", "aging", "stale"]),
)
def test_hypothesis_improvement_hardening_task_payload_shape_is_bounded(
    category: str,
    source_count: int,
    freshness_state: str,
) -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "hyp:execution",
            "category": category,
            "problem": "Generic issue",
            "proposed_action": "Generic improvement",
            "source_count": source_count,
            "freshness_state": freshness_state,
        }
    )
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    bridge = build_improvement_task_bridge(compiled, promotion)
    payload = build_improvement_hardening_task_payload(compiled, promotion, bridge)

    assert payload["creation_state"] in {"task_payload_ready", "not_creatable"}
    assert payload["task_type"] == "triggered"
    assert payload["priority"] in {1, 2, 3}

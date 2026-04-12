from __future__ import annotations

from hypothesis import given, strategies as st

from orchestration.improvement_task_autonomy import build_improvement_task_autonomy_decision
from orchestration.improvement_task_bridge import build_improvement_task_bridge
from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_execution import build_improvement_hardening_task_payload
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


@given(
    target_path=st.sampled_from(
        [
            "",
            "agent/prompts.py",
            "main_dispatcher.py",
            "server/mcp_server.py",
            "tools/deep_research/tool.py",
        ]
    ),
    category=st.sampled_from(["routing", "context", "runtime", "policy", "tool", "ux_handoff"]),
    allow_self_modify=st.booleans(),
    max_autoenqueue=st.integers(min_value=0, max_value=2),
)
def test_hypothesis_improvement_task_autonomy_decision_state_is_bounded(
    target_path: str,
    category: str,
    allow_self_modify: bool,
    max_autoenqueue: int,
) -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "hyp:e33",
            "category": category,
            "problem": "Generic issue",
            "proposed_action": "Generic fix",
            "source_count": 2,
            "freshness_state": "fresh",
            "verified_paths": [target_path] if target_path else [],
        }
    )
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    bridge = build_improvement_task_bridge(compiled, promotion)
    payload = build_improvement_hardening_task_payload(compiled, promotion, bridge)
    decision = build_improvement_task_autonomy_decision(
        payload,
        allow_self_modify=allow_self_modify,
        enqueued_this_cycle=0,
        max_autoenqueue=max_autoenqueue,
    )

    assert decision["autoenqueue_state"] in {
        "not_creatable",
        "route_not_autonomous",
        "self_modify_opt_in_required",
        "queue_budget_exhausted",
        "autoenqueue_ready",
        "enqueue_created",
        "enqueue_deduped",
        "enqueue_blocked",
    }
    assert decision["queue_budget_remaining"] >= 0

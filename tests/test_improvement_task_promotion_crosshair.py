from __future__ import annotations

import deal

from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


@deal.post(lambda r: r is True)
def _contract_strong_routing_task_becomes_e3_ready() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:e3",
            "category": "routing",
            "problem": "Dispatcher fallback repeated",
            "proposed_action": "Harden route selection",
            "source_count": 2,
            "freshness_state": "fresh",
            "verified_paths": ["main_dispatcher.py"],
        }
    )
    decision = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    return decision["promotion_state"] == "eligible_for_e3" and decision["e3_ready"] is True


@deal.post(lambda r: r is True)
def _contract_sensitive_policy_task_stays_human_only() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:human",
            "category": "policy",
            "problem": "Credential issue",
            "proposed_action": "Adjust password handling",
        }
    )
    decision = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    return decision["requested_fix_mode"] == "human_only" and decision["e3_ready"] is False


@deal.post(lambda r: r is True)
def _contract_developer_rollout_defers_self_modify_candidate() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:deferred",
            "category": "runtime",
            "problem": "Runtime guard drift",
            "proposed_action": "Harden health guard threshold",
            "source_count": 2,
            "freshness_state": "fresh",
            "verified_paths": ["server/mcp_server.py"],
        }
    )
    decision = evaluate_compiled_task_promotion(compiled, rollout_stage="developer_only")
    return decision["promotion_state"] == "deferred_by_rollout" and decision["effective_fix_mode"] == "developer_task"

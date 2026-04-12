from __future__ import annotations

import deal

from orchestration.improvement_task_bridge import build_improvement_task_bridge
from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


@deal.post(lambda r: r is True)
def _contract_prompt_zone_self_modify_ready() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:prompt",
            "category": "routing",
            "problem": "Prompt routing drift",
            "proposed_action": "Harden prompt policy",
            "source_count": 2,
            "freshness_state": "fresh",
            "verified_paths": ["agent/prompts.py"],
        }
    )
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    bridge = build_improvement_task_bridge(compiled, promotion)
    return bridge["bridge_state"] == "self_modify_ready" and bridge["route_target"] == "self_modify"


@deal.post(lambda r: r is True)
def _contract_main_dispatcher_downgrades_to_development() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:blocked",
            "category": "routing",
            "problem": "Dispatcher fallback repeated",
            "proposed_action": "Harden dispatcher frontdoor",
            "source_count": 2,
            "freshness_state": "fresh",
            "verified_paths": ["main_dispatcher.py"],
        }
    )
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    bridge = build_improvement_task_bridge(compiled, promotion)
    return bridge["bridge_state"] == "developer_bridge_ready" and bridge["route_target"] == "development"


@deal.post(lambda r: r is True)
def _contract_policy_secret_task_never_enters_e3_bridge() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:human",
            "category": "policy",
            "problem": "Credential issue",
            "proposed_action": "Adjust password handling",
        }
    )
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    bridge = build_improvement_task_bridge(compiled, promotion)
    return bridge["bridge_state"] == "not_e3_eligible" and bridge["allow_task"] is False

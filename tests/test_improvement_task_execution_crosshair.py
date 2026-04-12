from __future__ import annotations

import deal

from orchestration.improvement_task_bridge import build_improvement_task_bridge
from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_execution import build_improvement_hardening_task_payload
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


@deal.post(lambda r: r is True)
def _contract_prompt_payload_becomes_self_modify_ready() -> bool:
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
    payload = build_improvement_hardening_task_payload(compiled, promotion, bridge)
    return payload["creation_state"] == "task_payload_ready" and payload["target_agent"] == "self_modify"


@deal.post(lambda r: r is True)
def _contract_policy_secret_payload_is_not_creatable() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:policy",
            "category": "policy",
            "problem": "Credential issue",
            "proposed_action": "Adjust password handling",
        }
    )
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    bridge = build_improvement_task_bridge(compiled, promotion)
    payload = build_improvement_hardening_task_payload(compiled, promotion, bridge)
    return payload["creation_state"] == "not_creatable" and payload["target_agent"] == ""


@deal.post(lambda r: r is True)
def _contract_main_dispatcher_payload_routes_to_development() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:block",
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
    payload = build_improvement_hardening_task_payload(compiled, promotion, bridge)
    return payload["creation_state"] == "task_payload_ready" and payload["target_agent"] == "development"

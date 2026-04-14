from __future__ import annotations

import deal

from orchestration.improvement_task_autonomy import build_improvement_task_autonomy_decision
from orchestration.improvement_task_bridge import build_improvement_task_bridge
from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_execution import build_improvement_hardening_task_payload
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


@deal.post(lambda r: r is True)
def _contract_development_payload_becomes_autoenqueue_ready() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:dev",
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
    decision = build_improvement_task_autonomy_decision(
        payload,
        allow_self_modify=False,
        enqueued_this_cycle=0,
        max_autoenqueue=1,
    )
    return decision["target_agent"] == "development" and decision["autoenqueue_state"] == "autoenqueue_ready"


@deal.post(lambda r: r is True)
def _contract_self_modify_payload_needs_opt_in_by_default() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:self",
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
    decision = build_improvement_task_autonomy_decision(
        payload,
        allow_self_modify=False,
        enqueued_this_cycle=0,
        max_autoenqueue=1,
    )
    return decision["target_agent"] == "self_modify" and decision["autoenqueue_state"] == "self_modify_opt_in_required"


@deal.post(lambda r: r is True)
def _contract_strict_force_off_guard_blocks_development_payload() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:strict",
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
    decision = build_improvement_task_autonomy_decision(
        payload,
        rollout_guard={"state": "strict_force_off", "blocked": True, "reasons": ["policy_runtime:strict_force_off"]},
        allow_self_modify=False,
        enqueued_this_cycle=0,
        max_autoenqueue=1,
    )
    return decision["target_agent"] == "development" and decision["autoenqueue_state"] == "strict_force_off"


@deal.post(lambda r: r is True)
def _contract_verification_backpressure_guard_blocks_development_payload() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:backpressure",
            "category": "routing",
            "problem": "Repeated unverifiable hardening",
            "proposed_action": "Pause autonomous improvement enqueue",
            "source_count": 2,
            "freshness_state": "fresh",
            "verified_paths": ["main_dispatcher.py"],
        }
    )
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    bridge = build_improvement_task_bridge(compiled, promotion)
    payload = build_improvement_hardening_task_payload(compiled, promotion, bridge)
    decision = build_improvement_task_autonomy_decision(
        payload,
        rollout_guard={
            "state": "verification_backpressure",
            "blocked": True,
            "reasons": [
                "verification_sample_total:3",
                "verification_negative_total:3",
                "verification_verified_rate:0.000",
            ],
        },
        allow_self_modify=False,
        enqueued_this_cycle=0,
        max_autoenqueue=1,
    )
    return decision["target_agent"] == "development" and decision["autoenqueue_state"] == "verification_backpressure"

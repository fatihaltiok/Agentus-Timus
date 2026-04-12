from __future__ import annotations

from orchestration.improvement_task_bridge import (
    build_improvement_task_bridge,
    build_improvement_task_bridges,
)
from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


def test_build_improvement_task_bridge_routes_prompt_zone_to_self_modify_ready() -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "cand:prompt",
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

    assert bridge["bridge_state"] == "self_modify_ready"
    assert bridge["route_target"] == "self_modify"
    assert bridge["change_type"] == "prompt_policy"
    assert bridge["allow_self_modify"] is True


def test_build_improvement_task_bridge_downgrades_blocked_path_to_developer_route() -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "cand:block",
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

    assert bridge["bridge_state"] == "developer_bridge_ready"
    assert bridge["route_target"] == "development"
    assert bridge["allow_self_modify"] is False
    assert bridge["reason"].startswith("self_modify_policy_blocked:")


def test_build_improvement_task_bridge_skips_non_e3_candidate() -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "cand:human",
            "category": "policy",
            "problem": "Credential issue",
            "proposed_action": "Adjust password handling",
        }
    )
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")

    bridge = build_improvement_task_bridge(compiled, promotion)

    assert bridge["bridge_state"] == "not_e3_eligible"
    assert bridge["allow_task"] is False
    assert bridge["route_target"] == ""


def test_build_improvement_task_bridges_preserves_task_order() -> None:
    compiled_a = compile_improvement_task(
        {
            "candidate_id": "cand:a",
            "category": "routing",
            "problem": "Prompt issue",
            "proposed_action": "Harden prompt policy",
            "source_count": 2,
            "freshness_state": "fresh",
            "verified_paths": ["agent/prompts.py"],
        }
    )
    compiled_b = compile_improvement_task(
        {
            "candidate_id": "cand:b",
            "category": "policy",
            "problem": "Credential issue",
            "proposed_action": "Adjust password handling",
        }
    )
    promotions = [
        evaluate_compiled_task_promotion(compiled_a, rollout_stage="self_modify_safe"),
        evaluate_compiled_task_promotion(compiled_b, rollout_stage="self_modify_safe"),
    ]

    bridges = build_improvement_task_bridges([compiled_a, compiled_b], promotions)

    assert [item["candidate_id"] for item in bridges] == ["cand:a", "cand:b"]

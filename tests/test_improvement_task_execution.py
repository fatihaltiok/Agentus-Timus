from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from orchestration.improvement_task_bridge import build_improvement_task_bridge
from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_execution import (
    build_improvement_hardening_task_payload,
    build_improvement_hardening_task_payloads,
    enqueue_improvement_hardening_task,
)
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


def test_build_improvement_hardening_task_payload_ready_for_self_modify() -> None:
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

    payload = build_improvement_hardening_task_payload(compiled, promotion, bridge)

    assert payload["creation_state"] == "task_payload_ready"
    assert payload["target_agent"] == "self_modify"
    assert payload["metadata"]["source"] == "improvement_task_bridge"
    assert payload["metadata"]["change_type"] == "prompt_policy"


def test_build_improvement_hardening_task_payload_not_creatable_for_non_e3() -> None:
    compiled = compile_improvement_task(
        {
            "candidate_id": "cand:policy",
            "category": "policy",
            "problem": "Credential issue",
            "proposed_action": "Adjust password handling",
        }
    )
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    bridge = build_improvement_task_bridge(compiled, promotion)

    payload = build_improvement_hardening_task_payload(compiled, promotion, bridge)

    assert payload["creation_state"] == "not_creatable"
    assert payload["target_agent"] == ""


def test_enqueue_improvement_hardening_task_creates_development_task_for_blocked_self_modify() -> None:
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

    queue = MagicMock()
    queue.get_all.return_value = []
    queue.add.return_value = "task-bridge-1"

    result = enqueue_improvement_hardening_task(queue, compiled, promotion, bridge, goal_id="goal-1")

    assert result["status"] == "created"
    assert result["target_agent"] == "development"
    _, kwargs = queue.add.call_args
    assert kwargs["target_agent"] == "development"
    assert kwargs["goal_id"] == "goal-1"
    assert "\"source\": \"improvement_task_bridge\"" in kwargs["metadata"]


def test_enqueue_improvement_hardening_task_dedupes_open_task() -> None:
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
    payload = build_improvement_hardening_task_payload(compiled, promotion, bridge)

    queue = MagicMock()
    queue.get_all.return_value = [
        {
            "status": "pending",
            "metadata": "{\"improvement_dedup_key\": \"%s\"}" % payload["metadata"]["improvement_dedup_key"],
        }
    ]

    result = enqueue_improvement_hardening_task(queue, compiled, promotion, bridge)

    assert result["status"] == "deduped"
    queue.add.assert_not_called()


def test_enqueue_improvement_hardening_task_blocks_recent_completed_task_via_cooldown(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_IMPROVEMENT_AUTOENQUEUE_COOLDOWN_MINUTES", "180")

    compiled = compile_improvement_task(
        {
            "candidate_id": "cand:cooldown",
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

    queue = MagicMock()
    queue.get_all.return_value = [
        {
            "id": "recent-task-1",
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "metadata": "{\"improvement_dedup_key\": \"%s\"}" % payload["metadata"]["improvement_dedup_key"],
        }
    ]

    result = enqueue_improvement_hardening_task(queue, compiled, promotion, bridge)

    assert result["status"] == "cooldown_active"
    assert result["task_id"] == "recent-task-1"
    queue.add.assert_not_called()


def test_enqueue_improvement_hardening_task_allows_old_completed_task_after_cooldown(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_IMPROVEMENT_AUTOENQUEUE_COOLDOWN_MINUTES", "180")

    compiled = compile_improvement_task(
        {
            "candidate_id": "cand:cooled",
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

    queue = MagicMock()
    queue.get_all.return_value = [
        {
            "id": "old-task-1",
            "status": "completed",
            "completed_at": (datetime.now() - timedelta(hours=5)).isoformat(),
            "metadata": "{\"improvement_dedup_key\": \"%s\"}" % payload["metadata"]["improvement_dedup_key"],
        }
    ]
    queue.add.return_value = "task-created-after-cooldown"

    result = enqueue_improvement_hardening_task(queue, compiled, promotion, bridge)

    assert result["status"] == "created"
    assert result["task_id"] == "task-created-after-cooldown"


def test_build_improvement_hardening_task_payloads_preserves_order() -> None:
    compiled_a = compile_improvement_task(
        {
            "candidate_id": "cand:a",
            "category": "routing",
            "problem": "Prompt routing drift",
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
    promotion_a = evaluate_compiled_task_promotion(compiled_a, rollout_stage="self_modify_safe")
    promotion_b = evaluate_compiled_task_promotion(compiled_b, rollout_stage="self_modify_safe")
    bridge_a = build_improvement_task_bridge(compiled_a, promotion_a)
    bridge_b = build_improvement_task_bridge(compiled_b, promotion_b)

    payloads = build_improvement_hardening_task_payloads(
        [compiled_a, compiled_b],
        [promotion_a, promotion_b],
        [bridge_a, bridge_b],
    )

    assert [item["candidate_id"] for item in payloads] == ["cand:a", "cand:b"]

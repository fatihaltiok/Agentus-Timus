from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orchestration.improvement_task_autonomy import (
    apply_improvement_task_autonomy,
    build_improvement_task_autonomy_decision,
    build_improvement_task_autonomy_decisions,
    run_improvement_task_autonomy_cycle,
)
from orchestration.improvement_task_bridge import build_improvement_task_bridge
from orchestration.improvement_task_compiler import compile_improvement_task
from orchestration.improvement_task_execution import build_improvement_hardening_task_payloads
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotion


def _compile_candidate(candidate_id: str, path: str, *, category: str = "routing") -> dict:
    return compile_improvement_task(
        {
            "candidate_id": candidate_id,
            "category": category,
            "problem": "Runtime drift",
            "proposed_action": "Harden runtime behavior",
            "source_count": 2,
            "freshness_state": "fresh",
            "verified_paths": [path] if path else [],
        }
    )


def _payload_for(path: str, *, candidate_id: str = "cand:test") -> tuple[dict, dict, dict, dict]:
    compiled = _compile_candidate(candidate_id, path)
    promotion = evaluate_compiled_task_promotion(compiled, rollout_stage="self_modify_safe")
    bridge = build_improvement_task_bridge(compiled, promotion)
    payload = build_improvement_hardening_task_payloads([compiled], [promotion], [bridge])[0]
    return compiled, promotion, bridge, payload


def test_build_improvement_task_autonomy_decision_allows_development_autoenqueue() -> None:
    _, _, _, payload = _payload_for("main_dispatcher.py", candidate_id="cand:dev")

    decision = build_improvement_task_autonomy_decision(
        payload,
        allow_self_modify=False,
        enqueued_this_cycle=0,
        max_autoenqueue=1,
    )

    assert decision["target_agent"] == "development"
    assert decision["autoenqueue_state"] == "autoenqueue_ready"
    assert decision["allow_autoenqueue"] is True


def test_build_improvement_task_autonomy_decision_requires_self_modify_opt_in() -> None:
    _, _, _, payload = _payload_for("agent/prompts.py", candidate_id="cand:self")

    decision = build_improvement_task_autonomy_decision(
        payload,
        allow_self_modify=False,
        enqueued_this_cycle=0,
        max_autoenqueue=1,
    )

    assert decision["target_agent"] == "self_modify"
    assert decision["autoenqueue_state"] == "self_modify_opt_in_required"
    assert decision["allow_autoenqueue"] is False


def test_apply_improvement_task_autonomy_dedup_does_not_consume_budget() -> None:
    compiled_a, promotion_a, bridge_a, payload_a = _payload_for("main_dispatcher.py", candidate_id="cand:a")
    compiled_b, promotion_b, bridge_b, payload_b = _payload_for("server/mcp_server.py", candidate_id="cand:b")

    queue = MagicMock()
    queue.get_all.side_effect = [
        [{"status": "pending", "metadata": "{\"improvement_dedup_key\": \"%s\"}" % payload_a["metadata"]["improvement_dedup_key"]}],
        [],
    ]
    queue.add.return_value = "task-created-b"

    result = apply_improvement_task_autonomy(
        queue,
        [compiled_a, compiled_b],
        [promotion_a, promotion_b],
        [bridge_a, bridge_b],
        [payload_a, payload_b],
        allow_self_modify=False,
        max_autoenqueue=1,
    )

    assert result["enqueued_total"] == 1
    assert result["deduped_total"] == 1
    assert result["decisions"][0]["autoenqueue_state"] == "enqueue_deduped"
    assert result["decisions"][1]["autoenqueue_state"] == "enqueue_created"
    _, kwargs = queue.add.call_args
    assert kwargs["target_agent"] == "development"


@pytest.mark.asyncio
async def test_run_improvement_task_autonomy_cycle_enqueues_development_task(monkeypatch) -> None:
    async def _fake_combined_candidates(self):
        return [
            {
                "candidate_id": "cand:cycle",
                "category": "routing",
                "problem": "Dispatcher fallback repeated",
                "proposed_action": "Harden dispatcher frontdoor",
                "source_count": 2,
                "freshness_state": "fresh",
                "verified_paths": ["main_dispatcher.py"],
            }
        ]

    monkeypatch.setattr(
        "orchestration.self_improvement_engine.get_improvement_engine",
        lambda: SimpleNamespace(get_normalized_suggestions=lambda applied=False: []),
    )
    monkeypatch.setattr(
        "orchestration.session_reflection.SessionReflectionLoop.get_improvement_suggestions",
        _fake_combined_candidates,
    )

    queue = MagicMock()
    queue.get_all.return_value = []
    queue.add.return_value = "task-cycle-1"

    summary = await run_improvement_task_autonomy_cycle(
        queue,
        allow_self_modify=False,
        max_autoenqueue=1,
        rollout_stage="self_modify_safe",
    )

    assert summary["status"] == "ok"
    assert summary["enqueued_total"] == 1
    assert summary["autonomy_decisions"][0]["autoenqueue_state"] == "enqueue_created"


def test_build_improvement_task_autonomy_decisions_applies_preview_budget() -> None:
    _, _, _, payload_a = _payload_for("main_dispatcher.py", candidate_id="cand:budget-a")
    _, _, _, payload_b = _payload_for("server/mcp_server.py", candidate_id="cand:budget-b")

    decisions = build_improvement_task_autonomy_decisions(
        [payload_a, payload_b],
        allow_self_modify=False,
        max_autoenqueue=1,
    )

    assert decisions[0]["autoenqueue_state"] == "autoenqueue_ready"
    assert decisions[1]["autoenqueue_state"] == "queue_budget_exhausted"

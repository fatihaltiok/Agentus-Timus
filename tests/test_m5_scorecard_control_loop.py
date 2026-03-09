"""M5.2 Scorecard-Control-Loop: Promotion/Hold/Rollback fuer Canary/Strict."""

from __future__ import annotations

import asyncio
from pathlib import Path

from orchestration.autonomous_runner import AutonomousRunner
from orchestration.autonomy_scorecard import (
    build_autonomy_scorecard,
    evaluate_and_apply_scorecard_control,
)
from orchestration.task_queue import TaskQueue


def _scorecard(score: float, mode: str = "normal") -> dict:
    return {
        "overall_score": float(score),
        "pillars": {
            "self_healing": {"degrade_mode": mode},
        },
    }


def test_m5_control_promotes_canary_when_score_is_high(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_PROMOTE_THRESHOLD", "80")
    monkeypatch.setenv("AUTONOMY_SCORECARD_ROLLBACK_THRESHOLD", "55")
    monkeypatch.setenv("AUTONOMY_SCORECARD_PROMOTE_STEP", "10")
    monkeypatch.setenv("AUTONOMY_SCORECARD_MAX_CANARY", "100")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_COOLDOWN_MIN", "120")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "20")
    queue.set_policy_runtime_state("strict_force_off", "true")

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_scorecard(91.0, mode="normal"),
    )
    assert result["action"] == "promote_canary"
    assert result["current_canary_percent"] == 20
    assert result["next_canary_percent"] == 30

    canary_state = queue.get_policy_runtime_state("canary_percent_override")
    strict_state = queue.get_policy_runtime_state("strict_force_off")
    action_state = queue.get_policy_runtime_state("scorecard_last_action")
    assert canary_state is not None and canary_state["state_value"] == "30"
    assert strict_state is not None and strict_state["state_value"] == "false"
    assert action_state is not None and action_state["state_value"] == "promote_canary"


def test_m5_control_rolls_back_when_score_is_low(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_PROMOTE_THRESHOLD", "80")
    monkeypatch.setenv("AUTONOMY_SCORECARD_ROLLBACK_THRESHOLD", "55")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_COOLDOWN_MIN", "120")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "70")
    queue.set_policy_runtime_state("strict_force_off", "false")

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_scorecard(44.0, mode="restricted"),
    )
    assert result["action"] == "rollback_applied"
    assert result["next_canary_percent"] == 0
    assert result["strict_force_off"] is True

    canary_state = queue.get_policy_runtime_state("canary_percent_override")
    strict_state = queue.get_policy_runtime_state("strict_force_off")
    action_state = queue.get_policy_runtime_state("scorecard_last_action")
    assert canary_state is not None and canary_state["state_value"] == "0"
    assert strict_state is not None and strict_state["state_value"] == "true"
    assert action_state is not None and action_state["state_value"] == "rollback_applied"


def test_m5_control_respects_cooldown(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_PROMOTE_THRESHOLD", "80")
    monkeypatch.setenv("AUTONOMY_SCORECARD_ROLLBACK_THRESHOLD", "55")
    monkeypatch.setenv("AUTONOMY_SCORECARD_PROMOTE_STEP", "10")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_COOLDOWN_MIN", "120")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "10")

    first = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_scorecard(90.0, mode="normal"),
    )
    second = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_scorecard(92.0, mode="normal"),
    )
    assert first["action"] == "promote_canary"
    assert second["action"] == "cooldown_active"
    assert second["current_canary_percent"] == 20


def test_m5_control_holds_when_e2e_gate_warns(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_PROMOTE_THRESHOLD", "80")
    monkeypatch.setenv("AUTONOMY_SCORECARD_ROLLBACK_THRESHOLD", "55")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "20")

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_scorecard(91.0, mode="normal"),
        e2e_gate_decision={
            "state": "warn",
            "reason": "non_blocking_e2e_drift",
            "warning_flows": ["meta_visual_browser"],
            "release_blocked": False,
            "canary_blocked": False,
            "canary_deferred": True,
            "recommended_canary_percent": 20,
        },
    )

    assert result["action"] == "e2e_gate_hold"
    assert result["current_canary_percent"] == 20
    action_state = queue.get_policy_runtime_state("scorecard_last_action")
    e2e_state = queue.get_policy_runtime_state("scorecard_e2e_gate_state")
    assert action_state is not None and action_state["state_value"] == "e2e_gate_hold"
    assert e2e_state is not None and e2e_state["state_value"] == "warn"


def test_m5_control_blocks_and_rolls_back_when_e2e_gate_blocked(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_PROMOTE_THRESHOLD", "80")
    monkeypatch.setenv("AUTONOMY_SCORECARD_ROLLBACK_THRESHOLD", "55")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "60")
    queue.set_policy_runtime_state("strict_force_off", "false")

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_scorecard(91.0, mode="normal"),
        e2e_gate_decision={
            "state": "blocked",
            "reason": "blocking_e2e_failures",
            "blocking_flows": ["telegram_status"],
            "failed_flows": ["telegram_status"],
            "release_blocked": True,
            "canary_blocked": True,
            "canary_deferred": True,
            "recommended_canary_percent": 0,
        },
    )

    assert result["action"] == "e2e_gate_blocked"
    assert result["next_canary_percent"] == 0
    assert result["strict_force_off"] is True
    canary_state = queue.get_policy_runtime_state("canary_percent_override")
    action_state = queue.get_policy_runtime_state("scorecard_last_action")
    e2e_state = queue.get_policy_runtime_state("scorecard_e2e_gate_state")
    assert canary_state is not None and canary_state["state_value"] == "0"
    assert action_state is not None and action_state["state_value"] == "e2e_gate_blocked"
    assert e2e_state is not None and e2e_state["state_value"] == "blocked"


def test_m5_control_holds_when_ops_gate_warns(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "20")

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_scorecard(91.0, mode="normal"),
        ops_gate_decision={
            "state": "warn",
            "reason": "ops_or_budget_drift",
            "warning_targets": ["llm"],
            "release_blocked": False,
            "canary_blocked": False,
            "canary_deferred": True,
            "recommended_canary_percent": 10,
        },
    )

    assert result["action"] == "ops_gate_hold"
    ops_state = queue.get_policy_runtime_state("scorecard_ops_gate_state")
    assert ops_state is not None and ops_state["state_value"] == "warn"


def test_m5_control_blocks_when_ops_gate_blocked(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "50")
    queue.set_policy_runtime_state("strict_force_off", "false")

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_scorecard(91.0, mode="normal"),
        ops_gate_decision={
            "state": "blocked",
            "reason": "critical_ops_or_budget_health",
            "critical_targets": ["mcp"],
            "release_blocked": True,
            "canary_blocked": True,
            "canary_deferred": True,
            "recommended_canary_percent": 0,
        },
    )

    assert result["action"] == "ops_gate_blocked"
    assert result["next_canary_percent"] == 0
    assert result["strict_force_off"] is True


def test_m5_scorecard_exposes_control_runtime(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("strict_force_off", "true")
    queue.set_policy_runtime_state("canary_percent_override", "0")
    queue.set_policy_runtime_state("scorecard_last_action", "rollback_applied")
    queue.set_policy_runtime_state("scorecard_last_score", "49.50")
    queue.set_policy_runtime_state("scorecard_e2e_gate_state", "warn", metadata_update={"reason": "non_blocking_e2e_drift"})
    queue.set_policy_runtime_state("scorecard_ops_gate_state", "warn", metadata_update={"reason": "ops_or_budget_drift"})

    monkeypatch.setattr(
        "orchestration.autonomy_scorecard.get_policy_decision_metrics",
        lambda window_hours=24: {
            "window_hours": window_hours,
            "decisions_total": 0,
            "blocked_total": 0,
            "observed_total": 0,
            "canary_deferred_total": 0,
            "by_gate": {},
            "strict_force_off": True,
        },
    )

    scorecard = build_autonomy_scorecard(queue=queue, window_hours=24)
    control = scorecard.get("control", {})
    assert control.get("strict_force_off") is True
    assert control.get("canary_percent_override") == 0
    assert control.get("scorecard_last_action") == "rollback_applied"
    assert control.get("scorecard_last_score") == 49.5
    assert control.get("scorecard_e2e_gate_state") == "warn"
    assert control.get("scorecard_e2e_gate_reason") == "non_blocking_e2e_drift"
    assert control.get("scorecard_ops_gate_state") == "warn"
    assert control.get("scorecard_ops_gate_reason") == "ops_or_budget_drift"


def test_m5_control_preserves_last_e2e_state_when_no_new_gate_decision(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state(
        "scorecard_e2e_gate_state",
        "warn",
        metadata_update={"reason": "non_blocking_e2e_drift"},
    )

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_scorecard(91.0, mode="normal"),
        e2e_gate_decision=None,
    )

    assert result["action"] in {"promote_canary", "none", "cooldown_active", "governance_hold"}
    e2e_state = queue.get_policy_runtime_state("scorecard_e2e_gate_state")
    assert e2e_state is not None and e2e_state["state_value"] == "warn"
    metadata = e2e_state.get("metadata") or {}
    assert metadata.get("reason") == "non_blocking_e2e_drift"


def test_m5_runner_collect_e2e_gate_sync_uses_thread_when_loop_is_running(monkeypatch) -> None:
    runner = AutonomousRunner(interval_minutes=5)

    async def fake_collect() -> dict:
        await asyncio.sleep(0)
        return {"state": "warn", "reason": "thread_fallback"}

    monkeypatch.setattr(runner, "_collect_e2e_release_gate", fake_collect)

    async def _exercise() -> None:
        result = runner._collect_e2e_release_gate_sync()
        assert result == {"state": "warn", "reason": "thread_fallback"}

    asyncio.run(_exercise())


def test_m5_runner_collect_ops_gate_sync_uses_thread_when_loop_is_running(monkeypatch) -> None:
    runner = AutonomousRunner(interval_minutes=5)

    async def fake_collect() -> dict:
        await asyncio.sleep(0)
        return {"state": "warn", "reason": "ops_thread_fallback"}

    monkeypatch.setattr(runner, "_collect_ops_release_gate", fake_collect)

    async def _exercise() -> None:
        result = runner._collect_ops_release_gate_sync()
        assert result == {"state": "warn", "reason": "ops_thread_fallback"}

    asyncio.run(_exercise())


def test_m5_control_hooks_present() -> None:
    score_src = Path("orchestration/autonomy_scorecard.py").read_text(encoding="utf-8")
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "evaluate_and_apply_scorecard_control" in score_src
    assert "_apply_autonomy_scorecard_control" in runner_src
    assert "_collect_e2e_release_gate" in runner_src
    assert "_collect_ops_release_gate" in runner_src
    assert "Scorecard-Control" in cli_src
    assert "🧭 Control:" in tg_src

"""M5.2 Scorecard-Control-Loop: Promotion/Hold/Rollback fuer Canary/Strict."""

from __future__ import annotations

from pathlib import Path

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


def test_m5_scorecard_exposes_control_runtime(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("strict_force_off", "true")
    queue.set_policy_runtime_state("canary_percent_override", "0")
    queue.set_policy_runtime_state("scorecard_last_action", "rollback_applied")
    queue.set_policy_runtime_state("scorecard_last_score", "49.50")

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


def test_m5_control_hooks_present() -> None:
    score_src = Path("orchestration/autonomy_scorecard.py").read_text(encoding="utf-8")
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "evaluate_and_apply_scorecard_control" in score_src
    assert "_apply_autonomy_scorecard_control" in runner_src
    assert "Scorecard-Control" in cli_src
    assert "🧭 Control:" in tg_src


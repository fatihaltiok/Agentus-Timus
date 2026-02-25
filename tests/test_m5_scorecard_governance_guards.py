"""M5.4 Governance-Guards fuer Scorecard-Control."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from orchestration.autonomy_scorecard import (
    build_autonomy_scorecard,
    evaluate_and_apply_scorecard_control,
)
from orchestration.task_queue import TaskQueue


def _governance_card(
    *,
    overall: float,
    goals: float,
    planning: float,
    healing: float,
    policy: float,
    mode: str = "normal",
) -> dict:
    return {
        "overall_score": float(overall),
        "pillars": {
            "goals": {"score": float(goals)},
            "planning": {"score": float(planning)},
            "self_healing": {"score": float(healing), "degrade_mode": mode},
            "policy": {"score": float(policy)},
        },
    }


def _snapshot(score: float) -> dict:
    return {
        "overall_score": float(score),
        "overall_score_10": round(float(score) / 10.0, 2),
        "autonomy_level": "very_high" if score >= 85 else ("high" if score >= 75 else "medium"),
        "ready_for_very_high_autonomy": bool(score >= 85),
        "pillars": {},
        "control": {},
        "window_hours": 24,
    }


def test_m5_governance_freezes_promotion_on_low_pillar(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_GOVERNANCE_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_MIN_PILLAR_SCORE", "60")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CRITICAL_PILLAR_SCORE", "40")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "20")

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_governance_card(
            overall=90.0,
            goals=55.0,
            planning=84.0,
            healing=93.0,
            policy=88.0,
            mode="normal",
        ),
    )
    assert result["action"] == "governance_hold"
    assert result["current_canary_percent"] == 20
    assert result["governance"]["state"] == "freeze"
    assert "goals" in result["governance"]["pillars_below_min"]

    gov_state = queue.get_policy_runtime_state("scorecard_governance_state")
    assert gov_state is not None
    assert gov_state["state_value"] == "freeze"


def test_m5_governance_forces_rollback_on_critical_pillar(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_GOVERNANCE_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_MIN_PILLAR_SCORE", "60")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CRITICAL_PILLAR_SCORE", "40")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "70")
    queue.set_policy_runtime_state("strict_force_off", "false")

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_governance_card(
            overall=82.0,
            goals=32.0,
            planning=86.0,
            healing=90.0,
            policy=85.0,
            mode="normal",
        ),
    )
    assert result["action"] == "governance_force_rollback"
    assert result["next_canary_percent"] == 0
    assert result["strict_force_off"] is True
    assert result["governance"]["state"] == "force_rollback"
    assert "goals" in result["governance"]["pillars_below_critical"]


def test_m5_governance_freezes_on_declining_trend(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_GOVERNANCE_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_FREEZE_ON_DECLINING", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_DECLINE_DELTA", "-6")
    monkeypatch.setenv("AUTONOMY_SCORECARD_VOLATILITY_FREEZE_THRESHOLD", "12")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "30")
    now = datetime.now()
    for i, score in enumerate([88, 87, 86, 85]):
        queue.record_autonomy_scorecard_snapshot(_snapshot(float(score)), observed_at=(now - timedelta(days=10 - i)).isoformat())
    for i, score in enumerate([62, 59, 56]):
        queue.record_autonomy_scorecard_snapshot(_snapshot(float(score)), observed_at=(now - timedelta(hours=10 - (i * 3))).isoformat())

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_governance_card(
            overall=84.0,
            goals=82.0,
            planning=80.0,
            healing=84.0,
            policy=83.0,
            mode="normal",
        ),
    )
    assert result["action"] == "governance_hold"
    assert result["governance"]["state"] == "freeze"
    assert result["governance"]["reason"] == "declining_or_volatile_trend"


def test_m5_governance_runtime_is_exposed_in_scorecard(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state(
        "scorecard_governance_state",
        "freeze",
        metadata_update={"reason": "declining_or_volatile_trend"},
    )

    monkeypatch.setattr(
        "orchestration.autonomy_scorecard.get_policy_decision_metrics",
        lambda window_hours=24: {
            "window_hours": window_hours,
            "decisions_total": 0,
            "blocked_total": 0,
            "observed_total": 0,
            "canary_deferred_total": 0,
            "by_gate": {},
            "strict_force_off": False,
        },
    )
    scorecard = build_autonomy_scorecard(queue=queue, window_hours=24)
    control_state = scorecard.get("control", {})
    assert control_state.get("scorecard_governance_state") == "freeze"
    assert control_state.get("scorecard_governance_reason") == "declining_or_volatile_trend"


def test_m5_governance_hooks_present() -> None:
    score_src = Path("orchestration/autonomy_scorecard.py").read_text(encoding="utf-8")
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "_evaluate_scorecard_governance" in score_src
    assert "AUTONOMY_SCORECARD_GOVERNANCE_ENABLED" in score_src
    assert "governance_force_rollback" in runner_src
    assert "Governance" in cli_src
    assert "Gov " in tg_src


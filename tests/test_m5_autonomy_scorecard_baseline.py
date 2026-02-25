"""M5.1 Autonomy-Scorecard Baseline: aggregierte Reife aus M1-M4."""

from __future__ import annotations

from pathlib import Path

from orchestration.autonomy_scorecard import build_autonomy_scorecard
from orchestration.task_queue import TaskQueue


def test_m5_scorecard_returns_stable_schema(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
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
    assert "overall_score" in scorecard
    assert "overall_score_10" in scorecard
    assert "autonomy_level" in scorecard
    assert "ready_for_very_high_autonomy" in scorecard
    assert set(scorecard["pillars"].keys()) == {"goals", "planning", "self_healing", "policy"}
    assert 0.0 <= float(scorecard["overall_score"]) <= 100.0


def test_m5_scorecard_ready_for_very_high_when_pillars_are_stable(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    monkeypatch.setattr(
        queue,
        "get_goal_alignment_metrics",
        lambda include_conflicts=True: {
            "open_alignment_rate": 95.0,
            "open_tasks": 12,
            "conflict_count": 0,
            "orphan_triggered_tasks": 0,
        },
    )
    monkeypatch.setattr(
        queue,
        "get_planning_metrics",
        lambda: {
            "plan_deviation_score": 0.4,
            "overdue_commitments": 0,
            "commitments_total": 18,
            "active_plans": 3,
        },
    )
    monkeypatch.setattr(
        queue,
        "get_replanning_metrics",
        lambda: {"events_last_24h": 3, "applied_last_24h": 3},
    )
    monkeypatch.setattr(
        queue,
        "get_commitment_review_metrics",
        lambda: {"due_reviews": 0, "escalated_last_7d": 0},
    )
    monkeypatch.setattr(
        queue,
        "get_self_healing_metrics",
        lambda: {
            "degrade_mode": "normal",
            "recovery_rate_24h": 100.0,
            "open_incidents": 0,
            "open_escalated_incidents": 0,
            "circuit_breakers_open": 0,
            "created_last_24h": 3,
            "recovered_last_24h": 3,
        },
    )
    monkeypatch.setattr(
        "orchestration.autonomy_scorecard.get_policy_decision_metrics",
        lambda window_hours=24: {
            "window_hours": window_hours,
            "decisions_total": 60,
            "blocked_total": 12,
            "observed_total": 3,
            "canary_deferred_total": 0,
            "by_gate": {"query": 20, "tool": 15, "delegation": 10, "autonomous_task": 15},
            "strict_force_off": False,
        },
    )

    scorecard = build_autonomy_scorecard(queue=queue, window_hours=24)
    assert scorecard["overall_score"] >= 85.0
    assert scorecard["autonomy_level"] == "very_high"
    assert scorecard["ready_for_very_high_autonomy"] is True
    assert scorecard["pillars"]["policy"]["strict_force_off"] is False


def test_m5_scorecard_detects_policy_rollback_risk(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    monkeypatch.setattr(
        queue,
        "get_goal_alignment_metrics",
        lambda include_conflicts=True: {
            "open_alignment_rate": 82.0,
            "open_tasks": 8,
            "conflict_count": 1,
            "orphan_triggered_tasks": 1,
        },
    )
    monkeypatch.setattr(
        queue,
        "get_planning_metrics",
        lambda: {
            "plan_deviation_score": 2.2,
            "overdue_commitments": 3,
            "commitments_total": 12,
            "active_plans": 2,
        },
    )
    monkeypatch.setattr(
        queue,
        "get_replanning_metrics",
        lambda: {"events_last_24h": 2, "applied_last_24h": 1},
    )
    monkeypatch.setattr(
        queue,
        "get_commitment_review_metrics",
        lambda: {"due_reviews": 3, "escalated_last_7d": 1},
    )
    monkeypatch.setattr(
        queue,
        "get_self_healing_metrics",
        lambda: {
            "degrade_mode": "restricted",
            "recovery_rate_24h": 55.0,
            "open_incidents": 3,
            "open_escalated_incidents": 1,
            "circuit_breakers_open": 1,
            "created_last_24h": 5,
            "recovered_last_24h": 2,
        },
    )
    monkeypatch.setattr(
        "orchestration.autonomy_scorecard.get_policy_decision_metrics",
        lambda window_hours=24: {
            "window_hours": window_hours,
            "decisions_total": 100,
            "blocked_total": 55,
            "observed_total": 60,
            "canary_deferred_total": 30,
            "by_gate": {"query": 70, "tool": 30},
            "strict_force_off": True,
        },
    )

    scorecard = build_autonomy_scorecard(queue=queue, window_hours=24)
    assert scorecard["ready_for_very_high_autonomy"] is False
    assert scorecard["pillars"]["policy"]["strict_force_off"] is True
    assert float(scorecard["pillars"]["policy"]["score"]) < 50.0
    assert float(scorecard["overall_score"]) < 75.0


def test_m5_scorecard_hooks_present() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "_scorecard_feature_enabled" in runner_src
    assert "_export_autonomy_scorecard_snapshot" in runner_src
    assert "autonomy_scorecard" in runner_src
    assert "Autonomy-Score" in tg_src
    assert "Autonomy-Score" in cli_src


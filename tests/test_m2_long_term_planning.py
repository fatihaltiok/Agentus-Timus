"""M2.1 Rolling Planning: Daily/Weekly/Monthly + Commitments."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from orchestration.long_term_planner import LongTermPlanner
from orchestration.task_queue import GoalStatus, PlanHorizon, TaskQueue


def test_m2_planner_disabled_in_compat_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_PLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.create_goal("Ziel A", priority_score=0.9)
    planner = LongTermPlanner(queue=queue, now_provider=lambda: datetime(2026, 2, 25, 9, 0, 0))

    result = planner.run_cycle()
    assert result["status"] == "disabled"
    assert queue.list_plans(limit=20) == []
    assert queue.list_commitments(limit=20) == []


def test_m2_planner_creates_three_horizons_and_commitments(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_PLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    g1 = queue.create_goal("API Stabilitaet steigern", priority_score=0.9)
    g2 = queue.create_goal("Incident-Dokumentation verbessern", priority_score=0.7)

    # Owner-Ableitung ueber Task-Zuordnung vorbereiten.
    queue.add("Task zu Ziel 1", goal_id=g1, target_agent="system")
    queue.add("Task zu Ziel 2", goal_id=g2, target_agent="reasoning")

    planner = LongTermPlanner(queue=queue, now_provider=lambda: datetime(2026, 2, 25, 10, 0, 0))
    result = planner.run_cycle()

    assert result["status"] == "ok"
    assert set(result["horizons"].keys()) == {PlanHorizon.DAILY, PlanHorizon.WEEKLY, PlanHorizon.MONTHLY}

    plans = queue.list_plans(status="active", limit=20)
    assert len(plans) == 3

    commitments = queue.list_commitments(limit=100)
    assert commitments, "Mindestens ein Commitment erwartet."
    first = commitments[0]
    assert first["deadline"]
    assert first["owner_agent"] in {"system", "reasoning", "meta"}
    assert first["success_metric"]


def test_m2_planner_is_idempotent_per_window(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_PLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.create_goal("Queue-Latenz verbessern", priority_score=0.8)
    planner = LongTermPlanner(queue=queue, now_provider=lambda: datetime(2026, 2, 25, 8, 0, 0))

    first = planner.run_cycle()
    second = planner.run_cycle()

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    metrics = queue.get_planning_metrics()
    assert metrics["active_plans"] == 3
    assert metrics["commitments_total"] == 3


def test_m2_planning_metrics_track_overdue_commitments(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    goal_id = queue.create_goal("Monatsziel", priority_score=0.6)
    plan_id = queue.create_or_get_plan(
        horizon=PlanHorizon.MONTHLY,
        window_start="2026-02-01T00:00:00",
        window_end="2026-03-01T00:00:00",
    )
    queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Ueberfaelliges Commitment",
        owner_agent="meta",
        deadline=(datetime.now() - timedelta(days=1)).isoformat(),
        success_metric="done",
        status="pending",
    )

    metrics = queue.get_planning_metrics()
    assert metrics["plans_total"] >= 1
    assert metrics["commitments_total"] >= 1
    assert metrics["overdue_commitments"] >= 1


def test_m2_runner_and_status_contain_planning_hooks() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "_planning_feature_enabled" in runner_src
    assert "LongTermPlanner" in runner_src
    assert "_export_planning_kpi_snapshot" in runner_src
    assert "get_planning_metrics" in tg_src
    assert "Planning:" in tg_src
    assert "get_planning_metrics" in cli_src


def test_m2_goal_transition_still_prevents_completed_reopen(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    goal_id = queue.create_goal("Legacy-Guard", priority_score=0.4)
    assert queue.transition_goal_status(goal_id, GoalStatus.COMPLETED)
    assert queue.transition_goal_status(goal_id, GoalStatus.ACTIVE) is False

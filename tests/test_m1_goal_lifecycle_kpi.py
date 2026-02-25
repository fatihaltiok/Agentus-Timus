"""M1.3 Goal-Lifecycle, Konflikte und KPI-Export."""

from __future__ import annotations

from pathlib import Path

from orchestration.task_queue import GoalStatus, TaskQueue, TaskType


def test_m1_goal_status_transition_rules_are_enforced(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    goal_id = queue.create_goal("Stabilitaet verbessern")

    assert queue.transition_goal_status(goal_id, GoalStatus.BLOCKED, reason="dependency_missing")
    assert queue.transition_goal_status(goal_id, GoalStatus.ACTIVE, reason="dependency_resolved")
    assert queue.transition_goal_status(goal_id, GoalStatus.COMPLETED, reason="done")
    assert queue.transition_goal_status(goal_id, GoalStatus.ACTIVE, reason="reopen") is False

    goal = queue.get_goal(goal_id)
    state = queue.get_goal_state(goal_id)
    assert goal is not None and state is not None
    assert goal["status"] == GoalStatus.COMPLETED
    assert str(state["last_event"]).startswith("status_transition:")


def test_m1_update_goal_state_marks_goal_completed_at_100_percent(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    goal_id = queue.create_goal("Monitoring ausbauen")
    queue.update_goal_state(goal_id, progress=100.0, last_event="manual_progress")

    goal = queue.get_goal(goal_id)
    state = queue.get_goal_state(goal_id)
    assert goal is not None and state is not None
    assert goal["status"] == GoalStatus.COMPLETED
    assert state["progress"] == 100.0


def test_m1_detect_goal_conflicts_antonym_pair(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.create_goal("CPU Limit erhoehen fuer Worker", priority_score=0.8)
    queue.create_goal("CPU Limit senken fuer Worker", priority_score=0.7)

    conflicts = queue.detect_goal_conflicts(limit=20)
    assert conflicts
    reasons = {c["reason"] for c in conflicts}
    assert any(r.startswith("antonym:") for r in reasons)


def test_m1_sync_goal_conflicts_adds_edges_and_can_block(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    high = queue.create_goal("API Rate Limit erhoehen", priority_score=0.9)
    low = queue.create_goal("API Rate Limit senken", priority_score=0.2)

    result = queue.sync_goal_conflicts(auto_block=True, max_pairs=20)
    assert result["conflicts_detected"] >= 1
    assert result["conflict_edges_inserted"] >= 1
    assert result["goals_blocked"] >= 1

    low_goal = queue.get_goal(low)
    high_goal = queue.get_goal(high)
    assert low_goal is not None and high_goal is not None
    assert low_goal["status"] == GoalStatus.BLOCKED
    assert high_goal["status"] in {GoalStatus.ACTIVE, GoalStatus.BLOCKED}


def test_m1_goal_alignment_metrics_report_expected_counts(monkeypatch, tmp_path: Path) -> None:
    # Auto-Zuordnung deaktivieren, damit wir gezielt gemischte Daten erzeugen koennen.
    monkeypatch.setenv("AUTONOMY_GOALS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    goal = queue.create_goal("Queue Alignment Ziel", priority_score=0.5)

    task_no_goal = queue.add("Ungesetztes Ziel")
    task_with_goal = queue.add("Mit Ziel", goal_id=goal)
    queue.complete(task_with_goal, "done")
    queue.refresh_goal_progress(goal, last_task_id=task_with_goal, last_event="task_completed")
    queue.add("Webhook-Event", task_type=TaskType.TRIGGERED)

    metrics = queue.get_goal_alignment_metrics(include_conflicts=False)
    assert metrics["total_tasks"] == 3
    assert metrics["open_tasks"] == 2
    assert metrics["open_aligned_tasks"] == 0
    assert metrics["trackable_tasks"] == 3
    assert metrics["aligned_trackable_tasks"] == 1
    assert metrics["orphan_triggered_tasks"] == 1
    assert metrics["goal_counts"]["total"] >= 1
    assert metrics["goal_alignment_rate"] == 33.33

    # Sicherstellen, dass die ungenutzte Variable nicht versehentlich entfernt wird.
    assert task_no_goal


def test_m1_monitoring_and_canvas_hooks_present() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")

    assert "_export_goal_kpi_snapshot" in runner_src
    assert "get_goal_alignment_metrics" in runner_src
    assert "goal_kpi" in runner_src
    assert "Goals:" in tg_src

"""M1 Goal-Hierarchy: additive Schema-, Flag- und Integrationschecks."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestration.task_queue import GoalStatus, TaskQueue


def _table_exists(db_path: Path, table_name: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    return row is not None


def test_m1_goal_tables_and_task_goal_column_are_created(tmp_path: Path) -> None:
    db_path = tmp_path / "task_queue.db"
    TaskQueue(db_path=db_path)

    assert _table_exists(db_path, "tasks")
    assert _table_exists(db_path, "goals")
    assert _table_exists(db_path, "goal_edges")
    assert _table_exists(db_path, "goal_state")

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    assert "goal_id" in cols
    assert "run_at" in cols


def test_m1_goal_auto_link_is_disabled_in_compat_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_GOALS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    task_id = queue.add("Analysiere Ausfaelle der API von gestern")
    task = queue.get_by_id(task_id)

    assert task is not None
    assert task.get("goal_id") is None
    assert queue.list_goals() == []


def test_m1_goal_auto_link_creates_goal_when_feature_enabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_GOALS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    task_id = queue.add("Analysiere Ausfaelle der API von gestern")
    task = queue.get_by_id(task_id)

    assert task is not None
    goal_id = task.get("goal_id")
    assert isinstance(goal_id, str) and goal_id

    goal = queue.get_goal(goal_id)
    state = queue.get_goal_state(goal_id)
    assert goal is not None
    assert goal["title"] == "Analysiere Ausfaelle der API von gestern"
    assert state is not None
    assert state["progress"] == 0.0
    assert state["metrics"]["tasks_total"] == 1
    assert state["metrics"]["tasks_completed"] == 0


def test_m1_goal_progress_reaches_100_after_all_tasks_completed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_GOALS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    t1 = queue.add("Baue Goal-Fortschritt Metriken in Timus ein")
    t2 = queue.add("Baue Goal-Fortschritt Metriken in Timus ein")

    row1 = queue.get_by_id(t1)
    row2 = queue.get_by_id(t2)
    assert row1 is not None and row2 is not None
    goal_id = row1["goal_id"]
    assert goal_id == row2["goal_id"]

    queue.complete(t1, "fertig")
    p1 = queue.refresh_goal_progress(goal_id, last_task_id=t1, last_event="task_completed")
    assert p1 == 50.0

    queue.complete(t2, "fertig")
    p2 = queue.refresh_goal_progress(goal_id, last_task_id=t2, last_event="task_completed")
    assert p2 == 100.0

    goal = queue.get_goal(goal_id)
    assert goal is not None
    assert goal["status"] == GoalStatus.COMPLETED


def test_m1_goal_edges_and_manual_state_update(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    parent = queue.create_goal("Monatsziel: Stabilitaet")
    child = queue.create_goal("Woche 1: Fehlerraten reduzieren")
    queue.link_goals(parent, child, edge_type="depends_on", weight=0.9)

    with sqlite3.connect(tmp_path / "task_queue.db") as conn:
        edge = conn.execute(
            "SELECT parent_goal_id, child_goal_id, edge_type FROM goal_edges WHERE parent_goal_id=?",
            (parent,),
        ).fetchone()
    assert edge is not None
    assert edge[0] == parent
    assert edge[1] == child
    assert edge[2] == "depends_on"

    queue.update_goal_state(
        parent,
        progress=12.5,
        last_event="manual_update",
        metrics={"kpi_alignment": 0.72},
        status=GoalStatus.BLOCKED,
    )
    state = queue.get_goal_state(parent)
    goal = queue.get_goal(parent)
    assert state is not None
    assert goal is not None
    assert state["progress"] == 12.5
    assert state["last_event"] == "manual_update"
    assert state["metrics"]["kpi_alignment"] == 0.72
    assert goal["status"] == GoalStatus.BLOCKED


def test_m1_runner_contains_goal_progress_hook() -> None:
    source = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    assert "_goals_feature_enabled" in source
    assert "refresh_goal_progress" in source

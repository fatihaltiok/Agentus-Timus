"""M1.2 GoalGenerator: Signalquellen und Runner-Integration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestration.goal_generator import GoalGenerator
from orchestration.task_queue import GoalStatus, TaskQueue, TaskType


def test_m1_goal_generator_disabled_in_compat_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_GOALS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    generator = GoalGenerator(queue=queue, memory_state_provider=lambda: {"last_user_goal": "X"})
    created = generator.run_cycle()

    assert created == []
    assert queue.list_goals() == []


def test_m1_goal_generator_creates_from_memory_signals(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_GOALS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    state = {
        "last_user_goal": "Analysiere Ausfallmuster der letzten 7 Tage",
        "open_threads": [
            "Analysiere Ausfallmuster der letzten 7 Tage",  # absichtliches Duplikat
            "Bereite Incident-Review fuer Freitag vor",
        ],
        "top_topics": ["incident", "stability"],
    }
    generator = GoalGenerator(queue=queue, memory_state_provider=lambda: state)
    created = generator.run_cycle(max_goals=5)

    assert len(created) == 4  # dedupe reduziert auf 4 eindeutige Ziele
    goals = queue.list_goals(limit=10)
    titles = {g["title"] for g in goals}
    assert "Analysiere Ausfallmuster der letzten 7 Tage" in titles
    assert "Bereite Incident-Review fuer Freitag vor" in titles
    assert "Vertiefe Thema: incident" in titles
    assert "Vertiefe Thema: stability" in titles


def test_m1_goal_generator_uses_curiosity_signal_db(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_GOALS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    curiosity_db = tmp_path / "memory.db"
    with sqlite3.connect(curiosity_db) as conn:
        conn.executescript(
            """
            CREATE TABLE curiosity_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT,
                url TEXT,
                title TEXT,
                score REAL,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            "INSERT INTO curiosity_sent (topic, url, title, score, sent_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (
                "agentic systems",
                "https://example.com/agentic",
                "Neue Studie zu agentischer Robustheit",
                8.0,
            ),
        )

    generator = GoalGenerator(
        queue=queue,
        memory_state_provider=lambda: {},
        curiosity_db_path=curiosity_db,
    )
    created = generator.run_cycle(max_goals=3)

    assert created
    goals = queue.list_goals(limit=5)
    assert any(g["title"].startswith("Curiosity-Follow-up:") for g in goals)


def test_m1_goal_generator_assigns_unlinked_triggered_tasks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_GOALS_ENABLED", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")

    # Legacy/compat Pfad: Task ohne goal_id erzeugen.
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "true")
    task_id = queue.add(
        description="Webhook-Event verarbeiten: Bestellung 12345",
        task_type=TaskType.TRIGGERED,
    )
    legacy_task = queue.get_by_id(task_id)
    assert legacy_task is not None
    assert legacy_task["goal_id"] is None

    # M1.2 aktivieren und Event-Signal verarbeiten.
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    generator = GoalGenerator(queue=queue, memory_state_provider=lambda: {})
    created = generator.run_cycle(max_goals=2)

    assert created
    assigned_task = queue.get_by_id(task_id)
    assert assigned_task is not None
    assert assigned_task["goal_id"]

    goal = queue.get_goal(assigned_task["goal_id"])
    state = queue.get_goal_state(assigned_task["goal_id"])
    assert goal is not None
    assert state is not None
    assert goal["status"] in {GoalStatus.ACTIVE, GoalStatus.BLOCKED, GoalStatus.COMPLETED}
    assert state["metrics"]["tasks_total"] >= 1


def test_m1_runner_contains_goal_generator_hook() -> None:
    source = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    assert "GoalGenerator" in source
    assert "run_cycle(max_goals=3)" in source

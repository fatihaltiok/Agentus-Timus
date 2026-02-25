"""M2.3 Fortschrittsmetriken und Replanning-Priorisierung."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from orchestration.task_queue import CommitmentStatus, PlanHorizon, TaskQueue


def test_m2_commitment_progress_snapshot_contains_deviation_and_horizon(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    now = datetime.now()

    goal_id = queue.create_goal("Stabilitaet steigern", priority_score=0.9)
    plan_id = queue.create_or_get_plan(
        horizon=PlanHorizon.DAILY,
        window_start=(now - timedelta(hours=12)).isoformat(),
        window_end=(now + timedelta(hours=12)).isoformat(),
    )
    queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Incident-Rate senken",
        owner_agent="meta",
        deadline=(now + timedelta(hours=2)).isoformat(),
        success_metric="incidents < 2",
        status=CommitmentStatus.PENDING,
        progress=10.0,
    )
    queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Postmortem abschliessen",
        owner_agent="meta",
        deadline=(now + timedelta(days=1)).isoformat(),
        success_metric="postmortem done",
        status=CommitmentStatus.COMPLETED,
        progress=100.0,
    )

    snapshot = queue.get_commitment_progress_snapshot()
    assert snapshot["commitments_total"] == 2
    assert snapshot["open_commitments"] == 1
    assert snapshot["closed_commitments"] == 1
    assert snapshot["due_24h_open"] >= 1
    assert snapshot["plan_deviation_score"] > 0.0

    daily = snapshot["horizon_health"][PlanHorizon.DAILY]
    assert daily["total"] == 2
    assert daily["deviation_score"] > 0.0


def test_m2_replanning_candidates_prioritize_overdue_blocked(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    now = datetime.now()
    goal_id = queue.create_goal("Queue absichern", priority_score=0.7)
    plan_id = queue.create_or_get_plan(
        horizon=PlanHorizon.DAILY,
        window_start=(now - timedelta(hours=6)).isoformat(),
        window_end=(now + timedelta(hours=18)).isoformat(),
    )

    cid_overdue = queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Blockiertes ueberfaelliges Commitment",
        owner_agent="meta",
        deadline=(now - timedelta(days=2)).isoformat(),
        success_metric="done",
        status=CommitmentStatus.BLOCKED,
        progress=20.0,
    )
    queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Faellt bald an",
        owner_agent="meta",
        deadline=(now + timedelta(hours=1)).isoformat(),
        success_metric="done",
        status=CommitmentStatus.PENDING,
        progress=0.0,
    )
    queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Spaeteres Commitment",
        owner_agent="meta",
        deadline=(now + timedelta(days=4)).isoformat(),
        success_metric="done",
        status=CommitmentStatus.PENDING,
        progress=0.0,
    )

    candidates = queue.list_replanning_candidates(limit=3, include_blocked=True)
    assert len(candidates) == 3
    assert candidates[0]["id"] == cid_overdue
    assert float(candidates[0]["priority_score"]) > float(candidates[1]["priority_score"])
    assert "overdue" in set(candidates[0]["priority_reasons"])
    assert "blocked" in set(candidates[0]["priority_reasons"])


def test_m2_replanning_metrics_expose_top_candidates(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    now = datetime.now()
    goal_id = queue.create_goal("Observability verbessern", priority_score=0.8)
    plan_id = queue.create_or_get_plan(
        horizon=PlanHorizon.WEEKLY,
        window_start=(now - timedelta(days=2)).isoformat(),
        window_end=(now + timedelta(days=5)).isoformat(),
    )
    overdue_id = queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Runbook aktualisieren",
        owner_agent="meta",
        deadline=(now - timedelta(hours=10)).isoformat(),
        success_metric="runbook published",
        status=CommitmentStatus.PENDING,
        progress=0.0,
    )

    metrics = queue.get_replanning_metrics()
    assert metrics["top_candidates"], "Mindestens ein Replanning-Kandidat erwartet."
    assert metrics["top_priority_score"] >= 0.0
    first = metrics["top_candidates"][0]
    assert first["id"] == overdue_id
    assert first["priority_score"] == metrics["top_priority_score"]


def test_m2_progress_metrics_hooks_present() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "plan_deviation_score" in runner_src
    assert "top_priority_score" in runner_src
    assert "plan_deviation_score" in tg_src
    assert "top_priority_score" in tg_src
    assert "plan_deviation_score" in cli_src
    assert "top_priority_score" in cli_src

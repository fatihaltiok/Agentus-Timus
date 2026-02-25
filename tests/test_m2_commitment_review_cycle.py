"""M2.4 Commitment-Review-Zyklus mit Eskalation."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from orchestration.commitment_review_engine import CommitmentReviewEngine
from orchestration.task_queue import (
    CommitmentReviewStatus,
    CommitmentStatus,
    PlanHorizon,
    ReplanEventStatus,
    TaskQueue,
)


def test_m2_review_engine_disabled_in_compat_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_PLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    engine = CommitmentReviewEngine(queue=queue, now_provider=lambda: datetime(2026, 2, 25, 12, 0, 0))
    result = engine.run_cycle()
    assert result["status"] == "disabled"


def test_m2_review_checkpoint_sync_creates_reviews(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    now = datetime.now()

    goal_id = queue.create_goal("Stabilitaet verbessern", priority_score=0.8)
    plan_id = queue.create_or_get_plan(
        horizon=PlanHorizon.DAILY,
        window_start=(now - timedelta(hours=6)).isoformat(),
        window_end=(now + timedelta(hours=18)).isoformat(),
    )
    commitment_id = queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Alerting pruefen",
        owner_agent="meta",
        deadline=(now + timedelta(hours=8)).isoformat(),
        success_metric="alerts validated",
        status=CommitmentStatus.PENDING,
        progress=5.0,
    )

    sync = queue.sync_commitment_review_checkpoints(limit=20)
    assert sync["reviews_created"] >= 1

    reviews = queue.list_commitment_reviews(commitment_id=commitment_id, limit=20)
    assert reviews
    metrics = queue.get_commitment_review_metrics()
    assert metrics["scheduled_reviews"] >= 1


def test_m2_review_engine_escalates_and_emits_replan_event(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_PLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_REPLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    now = datetime(2026, 2, 25, 14, 0, 0)
    goal_id = queue.create_goal("Reliability KPI", priority_score=0.9)
    plan_id = queue.create_or_get_plan(
        horizon=PlanHorizon.DAILY,
        window_start=(now - timedelta(hours=12)).isoformat(),
        window_end=(now + timedelta(hours=12)).isoformat(),
    )
    commitment_id = queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Incident-Rueckgang",
        owner_agent="meta",
        deadline=(now + timedelta(hours=3)).isoformat(),
        success_metric="incidents/day <= 2",
        status=CommitmentStatus.PENDING,
        progress=0.0,
    )
    review = queue.upsert_commitment_review(
        commitment_id=commitment_id,
        plan_id=plan_id,
        goal_id=goal_id,
        horizon=PlanHorizon.DAILY,
        review_due_at=(now - timedelta(hours=1)).isoformat(),
        status=CommitmentReviewStatus.SCHEDULED,
        expected_progress=70.0,
        review_type="checkpoint",
    )
    assert review["id"] > 0

    engine = CommitmentReviewEngine(queue=queue, now_provider=lambda: now)
    result = engine.run_cycle()

    assert result["reviews_due"] >= 1
    assert result["reviews_escalated"] >= 1
    assert result["replan_events_created"] >= 1

    reviews = queue.list_commitment_reviews(statuses=[CommitmentReviewStatus.ESCALATED], limit=20)
    assert reviews
    assert float(reviews[0]["progress_gap"] or 0.0) >= 20.0

    events = queue.list_replan_events(statuses=[ReplanEventStatus.DETECTED], limit=20)
    assert events
    assert events[0]["details"].get("source") == "commitment_review_engine"


def test_m2_review_engine_is_idempotent_for_processed_reviews(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_PLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_REPLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    now = datetime(2026, 2, 25, 16, 0, 0)
    goal_id = queue.create_goal("Queue-Latenz", priority_score=0.7)
    plan_id = queue.create_or_get_plan(
        horizon=PlanHorizon.WEEKLY,
        window_start=(now - timedelta(days=1)).isoformat(),
        window_end=(now + timedelta(days=6)).isoformat(),
    )
    commitment_id = queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Retry-Policy nachziehen",
        owner_agent="meta",
        deadline=(now + timedelta(days=1)).isoformat(),
        success_metric="retry p95 <= 2s",
        status=CommitmentStatus.PENDING,
        progress=5.0,
    )
    queue.upsert_commitment_review(
        commitment_id=commitment_id,
        plan_id=plan_id,
        goal_id=goal_id,
        horizon=PlanHorizon.WEEKLY,
        review_due_at=(now - timedelta(minutes=30)).isoformat(),
        status=CommitmentReviewStatus.SCHEDULED,
        expected_progress=35.0,
        review_type="checkpoint",
    )

    engine = CommitmentReviewEngine(queue=queue, now_provider=lambda: now)
    first = engine.run_cycle()
    second = engine.run_cycle()

    assert first["reviews_due"] >= 1
    assert second["reviews_due"] == 0


def test_m2_review_runner_and_status_hooks_present() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "CommitmentReviewEngine" in runner_src
    assert "_export_commitment_review_kpi_snapshot" in runner_src
    assert "get_commitment_review_metrics" in tg_src
    assert "Reviews:" in tg_src
    assert "get_commitment_review_metrics" in cli_src

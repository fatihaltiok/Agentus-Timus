"""M2.2 Replanning: Trigger, Recovery und KPI-Hooks."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from orchestration.replanning_engine import ReplanningEngine
from orchestration.task_queue import (
    CommitmentStatus,
    PlanHorizon,
    ReplanEventStatus,
    ReplanTrigger,
    TaskQueue,
)


def _seed_plan_and_commitment(queue: TaskQueue, *, deadline: str) -> tuple[str, str]:
    goal_id = queue.create_goal("Queue Stabilitaet erhoehen", priority_score=0.8)
    plan_id = queue.create_or_get_plan(
        horizon=PlanHorizon.DAILY,
        window_start="2026-02-25T00:00:00",
        window_end="2026-02-26T00:00:00",
    )
    commitment_id = queue.create_commitment(
        plan_id=plan_id,
        goal_id=goal_id,
        title="Queue-Retry absichern",
        owner_agent="meta",
        deadline=deadline,
        success_metric="retry errors <= 1%",
        status=CommitmentStatus.PENDING,
        metadata={"horizon": PlanHorizon.DAILY},
    )
    return goal_id, commitment_id


def test_m2_replanning_disabled_in_compat_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_REPLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    _seed_plan_and_commitment(queue, deadline="2026-02-25T08:00:00")
    engine = ReplanningEngine(queue=queue, now_provider=lambda: datetime(2026, 2, 25, 12, 0, 0))

    result = engine.run_cycle()
    assert result["status"] == "disabled"
    assert queue.list_replan_events(limit=20) == []


def test_m2_replanning_detects_overdue_and_creates_recovery(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_REPLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    _, original_id = _seed_plan_and_commitment(queue, deadline="2026-02-25T08:00:00")
    engine = ReplanningEngine(queue=queue, now_provider=lambda: datetime(2026, 2, 25, 12, 0, 0))

    result = engine.run_cycle()
    assert result["status"] == "ok"
    assert result["events_detected"] >= 1
    assert result["events_created"] >= 1
    assert result["actions_applied"] >= 1

    events = queue.list_replan_events(trigger_types=[ReplanTrigger.DEADLINE_TIMEOUT], limit=20)
    assert events
    assert events[0]["status"] == ReplanEventStatus.APPLIED

    commitments = queue.list_commitments(limit=50)
    by_id = {c["id"]: c for c in commitments}
    assert by_id[original_id]["status"] == CommitmentStatus.BLOCKED

    recovery = [c for c in commitments if c["id"] != original_id and c["metadata"].get("recovery_for") == original_id]
    assert recovery, "Recovery-Commitment erwartet."

    metrics = queue.get_replanning_metrics()
    assert metrics["events_total"] >= 1
    assert metrics["trigger_counts"].get(ReplanTrigger.DEADLINE_TIMEOUT, 0) >= 1


def test_m2_replanning_is_idempotent_per_signal_bucket(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_REPLANNING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    _goal_id, original_id = _seed_plan_and_commitment(queue, deadline="2026-02-25T08:00:00")
    engine = ReplanningEngine(queue=queue, now_provider=lambda: datetime(2026, 2, 25, 12, 0, 0))

    first = engine.run_cycle()
    second = engine.run_cycle()

    assert first["events_created"] >= 1
    assert second["duplicates_skipped"] >= 1

    events = queue.list_replan_events(trigger_types=[ReplanTrigger.DEADLINE_TIMEOUT], limit=50)
    assert len(events) == 1

    commitments = queue.list_commitments(limit=50)
    recovery = [c for c in commitments if c["id"] != original_id and c["metadata"].get("recovery_for") == original_id]
    assert len(recovery) == 1


def test_m2_replanning_runner_and_status_hooks_present() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "_replanning_feature_enabled" in runner_src
    assert "ReplanningEngine" in runner_src
    assert "_export_replanning_kpi_snapshot" in runner_src
    assert "get_replanning_metrics" in tg_src
    assert "Replanning:" in tg_src
    assert "get_replanning_metrics" in cli_src

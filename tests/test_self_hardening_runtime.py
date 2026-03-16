from __future__ import annotations

from pathlib import Path

from orchestration.self_hardening_runtime import (
    classify_self_hardening_runtime_state,
    get_self_hardening_runtime_summary,
    record_self_hardening_event,
)
from orchestration.task_queue import TaskQueue


def test_record_self_hardening_event_updates_metrics_and_summary(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")

    record_self_hardening_event(
        queue=queue,
        stage="proposal_detected",
        status="active",
        pattern_name="tool_import_error",
        component="tool_registry",
        requested_fix_mode="developer_task",
        increment_metrics={"proposals_total": 1},
    )
    record_self_hardening_event(
        queue=queue,
        stage="task_created",
        status="created",
        pattern_name="tool_import_error",
        component="tool_registry",
        requested_fix_mode="developer_task",
        execution_mode="developer_task",
        route_target="development",
        task_id="task-1",
        increment_metrics={"tasks_created_total": 1, "developer_tasks_total": 1},
    )

    summary = get_self_hardening_runtime_summary(queue)

    assert summary["state"] == "ok"
    assert summary["last_event"] == "task_created"
    assert summary["last_pattern_name"] == "tool_import_error"
    assert summary["last_route_target"] == "development"
    assert summary["last_pattern_effective_fix_mode"] == "developer_task"
    assert summary["last_pattern_freeze_active"] is False
    assert summary["metrics"]["proposals_total"] == 1
    assert summary["metrics"]["tasks_created_total"] == 1
    assert summary["metrics"]["developer_tasks_total"] == 1


def test_classify_self_hardening_runtime_state_maps_failures_to_critical() -> None:
    assert classify_self_hardening_runtime_state(last_status="error", last_stage="self_modify_finished") == "critical"
    assert classify_self_hardening_runtime_state(last_status="rolled_back", last_stage="self_modify_finished") == "critical"
    assert classify_self_hardening_runtime_state(last_status="success", last_stage="self_modify_finished") == "ok"
    assert classify_self_hardening_runtime_state(last_status="", last_stage="idle_no_signals") == "idle"

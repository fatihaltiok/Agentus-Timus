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
        required_checks=["py_compile"],
        verification_status="planned",
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
        required_checks=["py_compile"],
        required_test_targets=["tests/test_demo.py"],
        verification_status="planned",
        increment_metrics={"tasks_created_total": 1, "developer_tasks_total": 1},
    )

    summary = get_self_hardening_runtime_summary(queue)

    assert summary["state"] == "ok"
    assert summary["last_event"] == "task_created"
    assert summary["last_pattern_name"] == "tool_import_error"
    assert summary["last_route_target"] == "development"
    assert summary["last_pattern_effective_fix_mode"] == "developer_task"
    assert summary["last_pattern_freeze_active"] is False
    assert summary["last_verification_status"] == "planned"
    assert summary["last_required_checks"] == ["py_compile"]
    assert summary["last_required_test_targets"] == ["tests/test_demo.py"]
    assert summary["metrics"]["proposals_total"] == 1
    assert summary["metrics"]["tasks_created_total"] == 1
    assert summary["metrics"]["developer_tasks_total"] == 1


def test_record_self_hardening_event_tracks_verified_self_modify_result(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")

    record_self_hardening_event(
        queue=queue,
        stage="self_modify_finished",
        status="success",
        pattern_name="narrative_synthesis_empty",
        component="deep_research.tool._create_narrative",
        requested_fix_mode="self_modify_safe",
        execution_mode="self_modify_safe",
        route_target="self_modify",
        task_id="task-sm-1",
        target_file_path="tools/deep_research/tool.py",
        change_type="report_quality_guardrails",
        required_checks=["py_compile", "pytest_targeted"],
        required_test_targets=["tests/test_deep_research_report_quality.py"],
        test_result="passed",
        canary_state="passed",
        canary_summary="production_gates:passed",
        verification_summary="py_compile:passed, pytest_targeted:passed",
        audit_id="audit-123",
    )

    summary = get_self_hardening_runtime_summary(queue)

    assert summary["last_verification_status"] == "verified"
    assert summary["last_test_result"] == "passed"
    assert summary["last_canary_state"] == "passed"
    assert summary["last_audit_id"] == "audit-123"
    assert summary["metrics"]["verification_verified_total"] == 1


def test_classify_self_hardening_runtime_state_maps_failures_to_critical() -> None:
    assert classify_self_hardening_runtime_state(last_status="error", last_stage="self_modify_finished") == "critical"
    assert classify_self_hardening_runtime_state(last_status="rolled_back", last_stage="self_modify_finished") == "critical"
    assert classify_self_hardening_runtime_state(last_status="success", last_stage="self_modify_finished") == "ok"
    assert classify_self_hardening_runtime_state(last_status="", last_stage="idle_no_signals") == "idle"


def test_classify_self_hardening_runtime_state_warns_on_verification_error() -> None:
    assert (
        classify_self_hardening_runtime_state(
            last_status="success",
            last_stage="self_modify_finished",
            verification_status="error",
        )
        == "warn"
    )


def test_classify_self_hardening_runtime_state_warns_on_human_freeze() -> None:
    assert (
        classify_self_hardening_runtime_state(
            last_status="success",
            last_stage="self_modify_finished",
            effective_fix_mode="human_only",
            freeze_active=True,
        )
        == "warn"
    )

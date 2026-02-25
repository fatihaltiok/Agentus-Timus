"""M6.3 Approval Gates fuer Audit Change-Requests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from orchestration.autonomy_change_control import (
    evaluate_and_apply_audit_change_request,
    evaluate_and_apply_pending_approved_change_requests,
    set_change_request_approval,
)
from orchestration.task_queue import TaskQueue


def _report(*, recommendation: str, score: float = 80.0, ts: str | None = None) -> dict:
    return {
        "timestamp": ts or datetime.now().isoformat(),
        "window_days": 7,
        "baseline_days": 30,
        "rollout_policy": {
            "recommendation": recommendation,
            "reason": "test_recommendation",
            "risk_flags": [],
        },
        "scorecard": {
            "overall_score": score,
            "autonomy_level": "high",
        },
    }


def test_m6_approval_required_sets_pending(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_PROMOTE_STEP", "10")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_MAX_CANARY", "100")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_REQUIRED_ACTIONS", "promote")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_PROMOTE_MIN_STEP", "10")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_AUTO_APPROVE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "20")

    result = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=_report(recommendation="promote", score=85.0),
        report_path=str(tmp_path / "audit_pending.json"),
    )
    assert result["action"] == "awaiting_approval"
    assert result["pending_approval_count"] == 1
    assert "promote_jump_requires_approval" in str(result.get("approval_reason") or "")

    requests = queue.list_autonomy_change_requests(limit=10)
    assert len(requests) == 1
    assert requests[0]["status"] == "pending_approval"
    assert requests[0]["action"] == "awaiting_approval"
    assert requests[0]["payload"]["approval_required"] is True

    pending_state = queue.get_policy_runtime_state("audit_change_pending_approval_count")
    assert pending_state is not None and pending_state["state_value"] == "1"


def test_m6_manual_approval_then_apply(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_PROMOTE_STEP", "10")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_MAX_CANARY", "100")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_REQUIRED_ACTIONS", "promote")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_PROMOTE_MIN_STEP", "10")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_AUTO_APPROVE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "30")
    pending = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=_report(recommendation="promote", score=82.0),
        report_path=str(tmp_path / "audit_approve.json"),
    )
    request_id = str(pending["request_id"])

    approval = set_change_request_approval(
        queue=queue,
        request_id=request_id,
        approved=True,
        approver="operator_test",
        note="approved_in_test",
    )
    assert approval["status"] == "ok"
    assert approval["action"] == "approved"

    processed = evaluate_and_apply_pending_approved_change_requests(queue=queue, limit=5)
    assert processed["action"] == "applied_approved_requests"
    assert processed["processed"] == 1
    assert processed["results"][0]["action"] == "promote_canary"

    request = queue.get_autonomy_change_request(request_id)
    assert request is not None and request["status"] == "applied"
    canary_state = queue.get_policy_runtime_state("canary_percent_override")
    assert canary_state is not None and canary_state["state_value"] == "40"
    approval_state = queue.get_policy_runtime_state("audit_change_last_approval_status")
    assert approval_state is not None and approval_state["state_value"] == "approved"


def test_m6_rejected_request_not_applied(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_REQUIRED_ACTIONS", "rollback")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_AUTO_APPROVE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "65")
    queue.set_policy_runtime_state("strict_force_off", "false")
    pending = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=_report(recommendation="rollback", score=45.0),
        report_path=str(tmp_path / "audit_reject.json"),
    )
    request_id = str(pending["request_id"])

    rejection = set_change_request_approval(
        queue=queue,
        request_id=request_id,
        approved=False,
        approver="operator_test",
        note="reject_in_test",
    )
    assert rejection["status"] == "ok"
    assert rejection["action"] == "rejected"

    processed = evaluate_and_apply_pending_approved_change_requests(queue=queue, limit=5)
    assert processed["action"] == "none"
    assert processed["processed"] == 0

    request = queue.get_autonomy_change_request(request_id)
    assert request is not None and request["status"] == "rejected"
    strict_state = queue.get_policy_runtime_state("strict_force_off")
    canary_state = queue.get_policy_runtime_state("canary_percent_override")
    assert strict_state is not None and strict_state["state_value"] == "false"
    assert canary_state is not None and canary_state["state_value"] == "65"


def test_m6_auto_approve_applies_directly(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_REQUIRED_ACTIONS", "rollback")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_AUTO_APPROVE", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_AUTO_APPROVER", "system_auto")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "70")
    queue.set_policy_runtime_state("strict_force_off", "false")

    result = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=_report(recommendation="rollback", score=50.0),
        report_path=str(tmp_path / "audit_auto.json"),
    )
    assert result["action"] == "rollback"

    request = queue.list_autonomy_change_requests(limit=5)[0]
    assert request["status"] == "applied"
    approval = request["payload"].get("approval", {})
    assert approval.get("decision") == "approved"
    assert approval.get("approver") == "system_auto"
    pending_state = queue.get_policy_runtime_state("audit_change_pending_approval_count")
    assert pending_state is not None and pending_state["state_value"] == "0"


def test_m6_approval_hooks_present() -> None:
    control_src = Path("orchestration/autonomy_change_control.py").read_text(encoding="utf-8")
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "set_change_request_approval" in control_src
    assert "evaluate_and_apply_pending_approved_change_requests" in control_src
    assert "_apply_pending_autonomy_audit_change_requests" in runner_src
    assert "awaiting_approval" in runner_src
    assert "PendingApproval" in tg_src
    assert "PendingApproval" in cli_src

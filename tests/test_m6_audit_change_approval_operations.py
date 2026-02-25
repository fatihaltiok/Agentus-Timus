"""M6.4 Approval Operations: Operator-Surface + SLA-Eskalation."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from orchestration.autonomy_change_control import (
    enforce_pending_approval_sla,
    evaluate_and_apply_audit_change_request,
    list_pending_approval_change_requests,
    resolve_change_request_id,
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


def test_m6_operations_list_pending_and_prefix_resolution(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_REQUIRED_ACTIONS", "rollback")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_AUTO_APPROVE", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "70")
    queue.set_policy_runtime_state("strict_force_off", "false")

    pending = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=_report(recommendation="rollback", score=50.0),
        report_path=str(tmp_path / "audit_pending_ops.json"),
    )
    assert pending["action"] == "awaiting_approval"
    request_id = str(pending["request_id"])

    listed = list_pending_approval_change_requests(queue=queue, limit=10)
    assert listed["status"] == "ok"
    assert listed["count"] == 1
    assert str(listed["items"][0]["id"]) == request_id
    assert listed["items"][0]["pending_minutes"] is not None

    resolved = resolve_change_request_id(queue=queue, request_id=request_id[:8])
    assert resolved["status"] == "ok"
    assert resolved["resolution"] == "prefix"
    assert resolved["request_id"] == request_id


def test_m6_operations_sla_escalates_and_creates_task(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_REQUIRED_ACTIONS", "rollback")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_AUTO_APPROVE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_SLA_HOURS", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ESCALATION_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ESCALATION_TASK_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ESCALATION_MIN_INTERVAL_MIN", "60")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_AUTO_REJECT_ON_TIMEOUT", "false")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "75")
    pending = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=_report(recommendation="rollback", score=48.0),
        report_path=str(tmp_path / "audit_sla_escalate.json"),
    )
    request_id = str(pending["request_id"])
    two_hours_ago = (datetime.now() - timedelta(hours=2)).isoformat()
    queue.update_autonomy_change_request(
        request_id,
        payload_update={"pending_since": two_hours_ago},
    )

    enforced = enforce_pending_approval_sla(queue=queue, limit=20)
    assert enforced["status"] == "ok"
    assert enforced["timed_out"] == 1
    assert enforced["escalated"] == 1
    assert enforced["escalation_tasks_created"] == 1

    tasks = queue.get_pending()
    assert any(request_id[:8] in str(task.get("description") or "") for task in tasks)

    enforced_again = enforce_pending_approval_sla(queue=queue, limit=20)
    assert enforced_again["timed_out"] == 1
    assert enforced_again["escalated"] == 0


def test_m6_operations_sla_auto_reject(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_REQUIRED_ACTIONS", "rollback")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_AUTO_APPROVE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_SLA_HOURS", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ESCALATION_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_AUTO_REJECT_ON_TIMEOUT", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "65")
    queue.set_policy_runtime_state("strict_force_off", "false")
    pending = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=_report(recommendation="rollback", score=45.0),
        report_path=str(tmp_path / "audit_sla_reject.json"),
    )
    request_id = str(pending["request_id"])
    two_hours_ago = (datetime.now() - timedelta(hours=2)).isoformat()
    queue.update_autonomy_change_request(
        request_id,
        payload_update={"pending_since": two_hours_ago},
    )

    enforced = enforce_pending_approval_sla(queue=queue, limit=20)
    assert enforced["timed_out"] == 1
    assert enforced["auto_rejected"] == 1
    assert enforced["escalated"] == 0

    request = queue.get_autonomy_change_request(request_id)
    assert request is not None and request["status"] == "rejected"


def test_m6_operations_hooks_present() -> None:
    control_src = Path("orchestration/autonomy_change_control.py").read_text(encoding="utf-8")
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")
    exports_src = Path("orchestration/__init__.py").read_text(encoding="utf-8")

    assert "list_pending_approval_change_requests" in control_src
    assert "resolve_change_request_id" in control_src
    assert "enforce_pending_approval_sla" in control_src
    assert "Approval-SLA" in runner_src
    assert "CommandHandler(\"approvals\"" in tg_src
    assert "CommandHandler(\"approve\"" in tg_src
    assert "CommandHandler(\"reject\"" in tg_src
    assert "/approvals" in cli_src
    assert "/approve <id>" in cli_src
    assert "enforce_pending_approval_sla" in exports_src

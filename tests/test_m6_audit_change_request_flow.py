"""M6.2 Audit Change-Request Flow."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from orchestration.autonomy_change_control import (
    create_change_request_from_audit,
    evaluate_and_apply_audit_change_request,
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


def test_m6_change_request_promote_apply(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_PROMOTE_STEP", "5")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_MAX_CANARY", "100")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "20")
    queue.set_policy_runtime_state("strict_force_off", "true")

    result = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=_report(recommendation="promote", score=84.0),
        report_path=str(tmp_path / "audit_1.json"),
    )
    assert result["action"] == "promote_canary"
    assert result["current_canary_percent"] == 20
    assert result["next_canary_percent"] == 25

    strict_state = queue.get_policy_runtime_state("strict_force_off")
    assert strict_state is not None and strict_state["state_value"] == "false"
    requests = queue.list_autonomy_change_requests(limit=10)
    assert len(requests) == 1
    assert requests[0]["status"] == "applied"
    assert requests[0]["action"] == "promote_canary"


def test_m6_change_request_rollback_apply(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "70")
    queue.set_policy_runtime_state("strict_force_off", "false")

    result = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=_report(recommendation="rollback", score=52.0),
        report_path=str(tmp_path / "audit_2.json"),
    )
    assert result["action"] == "rollback"
    assert result["next_canary_percent"] == 0

    strict_state = queue.get_policy_runtime_state("strict_force_off")
    canary_state = queue.get_policy_runtime_state("canary_percent_override")
    assert strict_state is not None and strict_state["state_value"] == "true"
    assert canary_state is not None and canary_state["state_value"] == "0"


def test_m6_change_request_duplicate_audit_is_noop(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    report = _report(recommendation="hold", score=76.0)
    path = str(tmp_path / "audit_dup.json")

    first = evaluate_and_apply_audit_change_request(queue=queue, report=report, report_path=path)
    second = evaluate_and_apply_audit_change_request(queue=queue, report=report, report_path=path)
    assert first["status"] == "ok"
    assert second["action"] == "duplicate_noop"
    requests = queue.list_autonomy_change_requests(limit=10)
    assert len(requests) == 1


def test_m6_change_request_respects_min_interval(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "120")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_PROMOTE_STEP", "5")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    first_report = _report(recommendation="promote", score=81.0, ts=(datetime.now() - timedelta(minutes=5)).isoformat())
    second_report = _report(recommendation="promote", score=82.0, ts=datetime.now().isoformat())

    first = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=first_report,
        report_path=str(tmp_path / "audit_int_1.json"),
    )
    second = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=second_report,
        report_path=str(tmp_path / "audit_int_2.json"),
    )
    assert first["action"] in {"promote_canary", "hold"}
    assert second["action"] == "skipped"
    assert "min_interval_active" in str(second.get("reason") or "")


def test_m6_change_request_hooks_present() -> None:
    queue_src = Path("orchestration/task_queue.py").read_text(encoding="utf-8")
    control_src = Path("orchestration/autonomy_change_control.py").read_text(encoding="utf-8")
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "autonomy_change_requests" in queue_src
    assert "create_autonomy_change_request" in queue_src
    assert "evaluate_and_apply_audit_change_request" in control_src
    assert "_audit_change_requests_feature_enabled" in runner_src
    assert "_apply_autonomy_audit_change_request" in runner_src
    assert "ChangeReq" in tg_src
    assert "Audit-ChangeRequest" in cli_src


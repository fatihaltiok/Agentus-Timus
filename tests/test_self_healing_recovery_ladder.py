from __future__ import annotations

from datetime import datetime
from pathlib import Path

from orchestration.self_healing_engine import SelfHealingEngine
from orchestration.task_queue import TaskQueue


def _healthy_stats() -> dict:
    return {"cpu_percent": 4.0, "ram_percent": 10.0, "disk_percent": 22.0}


def test_self_healing_recovery_ladder_marks_new_outage_as_recovering(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: datetime(2026, 3, 10, 15, 0, 0),
        mcp_probe=lambda: {"ok": False, "error": "connection_refused", "status": "down"},
        system_stats_provider=_healthy_stats,
    )

    result = engine.run_cycle()
    assert result["playbooks_triggered"] >= 1

    incident = queue.get_self_healing_incident("m3_mcp_health_unavailable")
    assert incident is not None
    details = incident.get("details") or {}
    assert details.get("recovery_phase") == "recovering"
    assert details.get("recovery_stage") == "diagnose"
    assert details.get("verified_outage") is True

    phase = queue.get_self_healing_runtime_state("incident_phase:m3_mcp_health_unavailable")
    assert phase is not None
    assert phase["state_value"] == "recovering"
    meta = phase.get("metadata") or {}
    assert meta.get("stage") == "diagnose"
    assert meta.get("verified_outage") is True


def test_self_healing_escalation_waits_without_verified_outage(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ESCALATE_AFTER_MIN", "30")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.upsert_self_healing_incident(
        incident_key="m3_failure_spike",
        component="providers",
        signal="task_failure_spike",
        severity="high",
        title="Failure Spike",
        details={
            "playbook_attempts": 1,
            "playbook_attempts_max": 3,
            "verified_outage": False,
        },
        observed_at="2026-03-10T14:00:00",
    )

    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: datetime(2026, 3, 10, 15, 5, 0),
        mcp_probe=lambda: {"ok": True},
        system_stats_provider=_healthy_stats,
    )

    summary = {"incidents_escalated": 0, "escalation_tasks_created": 0, "playbooks_triggered": 0}
    engine._run_escalation_control_loop(summary=summary)

    assert summary["incidents_escalated"] == 0
    phase = queue.get_self_healing_runtime_state("incident_phase:m3_failure_spike")
    assert phase is not None
    assert phase["state_value"] == "degraded"
    meta = phase.get("metadata") or {}
    assert meta.get("stage") == "observe"
    assert meta.get("reason") == "awaiting_verified_outage_or_attempt_exhaustion"


def test_self_healing_recovery_marks_phase_ok(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    state = {"ok": False}

    def _probe() -> dict:
        return {"ok": state["ok"], "status": "healthy" if state["ok"] else "down", "error": "" if state["ok"] else "connection_refused"}

    now = {"value": datetime(2026, 3, 10, 15, 0, 0)}

    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: now["value"],
        mcp_probe=_probe,
        system_stats_provider=_healthy_stats,
    )

    first = engine.run_cycle()
    assert first["incidents_opened"] >= 1

    state["ok"] = True
    now["value"] = datetime(2026, 3, 10, 15, 10, 0)
    second = engine.run_cycle()
    assert second["incidents_resolved"] >= 1

    phase = queue.get_self_healing_runtime_state("incident_phase:m3_mcp_health_unavailable")
    assert phase is not None
    assert phase["state_value"] == "ok"
    meta = phase.get("metadata") or {}
    assert meta.get("stage") == "resolved"
    assert meta.get("open_incident") is False

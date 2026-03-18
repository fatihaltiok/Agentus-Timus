"""M3.1 Self-Healing Baseline: Health-Checks, Incidents, Playbooks."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from orchestration.self_healing_engine import SelfHealingEngine
from orchestration.task_queue import SelfHealingIncidentStatus, TaskQueue


def _healthy_stats() -> dict:
    return {"cpu_percent": 5.0, "ram_percent": 12.0, "disk_percent": 21.0}


def test_m3_self_healing_disabled_in_compat_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: datetime(2026, 2, 25, 12, 0, 0),
        mcp_probe=lambda: {"ok": False},
        system_stats_provider=_healthy_stats,
    )
    result = engine.run_cycle()
    assert result["status"] == "disabled"
    assert queue.list_self_healing_incidents(limit=20) == []


def test_m3_self_healing_incident_lifecycle_and_metrics(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    upsert = queue.upsert_self_healing_incident(
        incident_key="m3_test_incident",
        component="mcp",
        signal="mcp_health",
        severity="high",
        status=SelfHealingIncidentStatus.OPEN,
        title="Test Incident",
        details={"endpoint": "http://127.0.0.1:5000/health"},
    )
    assert upsert["created"] is True
    assert queue.resolve_self_healing_incident(
        "m3_test_incident",
        status=SelfHealingIncidentStatus.RECOVERED,
        recovery_action="manual_fix",
        recovery_status="ok",
        details_update={"resolved": True},
    )

    metrics = queue.get_self_healing_metrics()
    assert metrics["incidents_total"] == 1
    assert metrics["open_incidents"] == 0
    assert metrics["status_counts"].get(SelfHealingIncidentStatus.RECOVERED, 0) == 1


def test_m3_self_healing_housekeeping_archives_old_resolved_incidents(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("orchestration.task_queue._SELF_HEALING_ARCHIVE_AFTER_DAYS", 7)
    monkeypatch.setattr("orchestration.task_queue._SELF_HEALING_DELETE_AFTER_DAYS", 30)
    monkeypatch.setattr("orchestration.task_queue._SELF_HEALING_MAINTENANCE_INTERVAL_SECONDS", 1)

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.upsert_self_healing_incident(
        incident_key="m3_old_resolved",
        component="mcp",
        signal="mcp_health",
        severity="medium",
        status=SelfHealingIncidentStatus.RECOVERED,
        title="Old resolved",
        details={"resolved": True},
    )

    old_ts = "2026-01-01T00:00:00"
    with queue._conn() as conn:
        conn.execute(
            """UPDATE self_healing_incidents
               SET updated_at=?, recovered_at=?, last_seen_at=?
               WHERE incident_key=?""",
            (old_ts, old_ts, old_ts, "m3_old_resolved"),
        )

    result = queue.run_self_healing_housekeeping(force=True)
    metrics = queue.get_self_healing_metrics()
    incidents = queue.list_self_healing_incidents(limit=10)
    archived = queue.list_self_healing_incidents(
        statuses=[SelfHealingIncidentStatus.ARCHIVED],
        limit=10,
    )

    assert result["archived"] == 1
    assert metrics["incidents_total"] == 0
    assert metrics["archived_incidents"] == 1
    assert incidents == []
    assert archived[0]["incident_key"] == "m3_old_resolved"


def test_m3_engine_creates_mcp_incident_and_playbook_task(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: datetime(2026, 2, 25, 13, 0, 0),
        mcp_probe=lambda: {"ok": False, "error": "connection_refused", "endpoint": "http://127.0.0.1:5000/health"},
        system_stats_provider=_healthy_stats,
    )
    result = engine.run_cycle()

    assert result["status"] == "ok"
    assert result["incidents_opened"] >= 1
    assert result["playbooks_triggered"] >= 1

    incident = queue.get_self_healing_incident("m3_mcp_health_unavailable")
    assert incident is not None
    assert incident["status"] == SelfHealingIncidentStatus.OPEN

    tasks = queue.get_all(limit=20)
    assert any(
        t.get("target_agent") == "system"
        and str(t.get("description", "")).startswith("Self-Healing Playbook")
        for t in tasks
    )


def test_m3_engine_resolves_incident_after_recovery(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    state = {"ok": False}

    def _probe() -> dict:
        return {"ok": state["ok"], "status": "healthy" if state["ok"] else "down"}

    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: datetime(2026, 2, 25, 14, 0, 0),
        mcp_probe=_probe,
        system_stats_provider=_healthy_stats,
    )
    first = engine.run_cycle()
    state["ok"] = True
    second = engine.run_cycle()

    assert first["incidents_opened"] >= 1
    assert second["incidents_resolved"] >= 1
    incident = queue.get_self_healing_incident("m3_mcp_health_unavailable")
    assert incident is not None
    assert incident["status"] == SelfHealingIncidentStatus.RECOVERED


def test_m3_runner_and_status_hooks_present() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "_self_healing_feature_enabled" in runner_src
    assert "SelfHealingEngine" in runner_src
    assert "_export_self_healing_kpi_snapshot" in runner_src
    assert "get_self_healing_metrics" in tg_src
    assert "Healing:" in tg_src
    assert "get_self_healing_metrics" in cli_src

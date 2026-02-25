"""M3.4 Self-Healing: Escalation Control Loop + Attempt Budget."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from orchestration.self_healing_engine import SelfHealingEngine
from orchestration.task_queue import SelfHealingIncidentStatus, TaskQueue


def _healthy_stats() -> dict:
    return {"cpu_percent": 4.0, "ram_percent": 11.0, "disk_percent": 20.0}


def test_m3_attempt_budget_blocks_repeated_playbooks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_BREAKER_COOLDOWN_SEC", "1")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_MAX_PLAYBOOK_ATTEMPTS", "1")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ESCALATE_AFTER_MIN", "90")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    clock = {"now": datetime(2026, 2, 25, 22, 0, 0)}
    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: clock["now"],
        mcp_probe=lambda: {"ok": False, "error": "down"},
        system_stats_provider=_healthy_stats,
    )

    first = engine.run_cycle()
    first_task_count = len(queue.get_all(limit=100))
    assert first["playbooks_triggered"] >= 1

    clock["now"] = datetime(2026, 2, 25, 22, 0, 3)  # > cooldown
    second = engine.run_cycle()
    second_task_count = len(queue.get_all(limit=100))

    assert second["playbook_attempts_blocked"] >= 1
    assert second_task_count == first_task_count

    incident = queue.get_self_healing_incident("m3_mcp_health_unavailable")
    assert incident is not None
    details = incident.get("details", {})
    assert details.get("attempts_exhausted") is True
    assert int(details.get("playbook_attempts", 0)) == 1


def test_m3_escalates_stale_open_incident(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_BREAKER_FAILURE_THRESHOLD", "99")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_MAX_PLAYBOOK_ATTEMPTS", "5")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ESCALATE_AFTER_MIN", "5")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ESCALATION_LIMIT_PER_CYCLE", "2")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    clock = {"now": datetime(2026, 2, 25, 22, 10, 0)}
    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: clock["now"],
        mcp_probe=lambda: {"ok": False, "error": "down"},
        system_stats_provider=_healthy_stats,
    )

    first = engine.run_cycle()
    assert first["incidents_opened"] >= 1
    assert first["incidents_escalated"] == 0

    clock["now"] = datetime(2026, 2, 25, 22, 16, 0)
    second = engine.run_cycle()
    assert second["incidents_escalated"] >= 1
    assert second["escalation_tasks_created"] >= 1

    incident = queue.get_self_healing_incident("m3_mcp_health_unavailable")
    assert incident is not None
    details = incident.get("details", {})
    assert details.get("escalated") is True
    assert details.get("escalation_task_id")

    metrics = queue.get_self_healing_metrics()
    assert metrics.get("open_escalated_incidents", 0) >= 1

    tasks = queue.get_all(limit=20)
    escalation_task = next(
        (
            t
            for t in tasks
            if json.loads(str(t.get("metadata") or "{}")).get("playbook_template") == "incident_escalation"
        ),
        None,
    )
    assert escalation_task is not None


def test_m3_escalation_markers_reset_after_recovery(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_BREAKER_FAILURE_THRESHOLD", "99")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ESCALATE_AFTER_MIN", "5")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    state = {"ok": False, "now": datetime(2026, 2, 25, 22, 20, 0)}

    def _probe() -> dict:
        return {"ok": state["ok"], "status": "healthy" if state["ok"] else "down"}

    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: state["now"],
        mcp_probe=_probe,
        system_stats_provider=_healthy_stats,
    )

    engine.run_cycle()
    state["now"] = datetime(2026, 2, 25, 22, 26, 0)
    engine.run_cycle()  # escalation expected

    state["ok"] = True
    state["now"] = datetime(2026, 2, 25, 22, 27, 0)
    recovered = engine.run_cycle()
    assert recovered["incidents_resolved"] >= 1

    incident = queue.get_self_healing_incident("m3_mcp_health_unavailable")
    assert incident is not None
    assert incident["status"] == SelfHealingIncidentStatus.RECOVERED
    details = incident.get("details", {})
    assert details.get("escalated") is False
    assert int(details.get("playbook_attempts", 0)) == 0

    metrics = queue.get_self_healing_metrics()
    assert metrics.get("open_escalated_incidents", 0) == 0


def test_m3_escalation_hooks_present() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    engine_src = Path("orchestration/self_healing_engine.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "_run_escalation_control_loop" in engine_src
    assert "AUTONOMY_SELF_HEALING_MAX_PLAYBOOK_ATTEMPTS" in engine_src
    assert "incidents_escalated" in runner_src
    assert "EscalatedOpen" in tg_src
    assert "EscalatedOpen" in cli_src

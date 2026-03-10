from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from orchestration.autonomous_runner import AutonomousRunner
from orchestration.task_queue import Priority, TaskQueue


@pytest.mark.asyncio
async def test_resource_guard_defers_heavy_research_task_under_pressure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_RESOURCE_GUARD_DEFER_MINUTES", "20")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_self_healing_runtime_state(
        "degrade_mode",
        "degraded",
        metadata_update={"reason": "system_pressure"},
        observed_at=datetime.now().isoformat(),
    )
    queue.upsert_self_healing_incident(
        incident_key="m3_system_pressure",
        component="system",
        signal="system_pressure",
        severity="high",
        title="Systemdruck",
        details={"ok": False, "cpu_percent": 94.0, "ram_percent": 91.0},
        observed_at=datetime.now().isoformat(),
    )

    task_id = queue.add(
        description="Recherchiere die wichtigsten KI-News und erstelle einen Bericht",
        target_agent="research",
        priority=Priority.NORMAL,
        max_retries=1,
    )
    task = queue.claim_next()
    assert task is not None and task["id"] == task_id

    runner = AutonomousRunner(interval_minutes=15)
    monkeypatch.setattr("orchestration.autonomous_runner.get_queue", lambda: queue)

    await runner._execute_task(task)

    updated = queue.get_by_id(task_id)
    assert updated is not None
    assert updated["status"] == "pending"
    run_at = str(updated.get("run_at") or "")
    assert run_at
    run_at_dt = datetime.fromisoformat(run_at)
    assert run_at_dt > datetime.now() - timedelta(minutes=1)
    assert str(updated.get("error") or "").startswith("resource_guard:")

    guard = queue.get_self_healing_runtime_state("resource_guard")
    assert guard is not None
    assert guard["state_value"] == "active"
    meta = guard.get("metadata") or {}
    assert "degrade_mode=degraded" in str(meta.get("reason") or "")
    assert "m3_system_pressure" in list(meta.get("reasons") or [])


@pytest.mark.asyncio
async def test_resource_guard_does_not_block_high_priority_task(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_self_healing_runtime_state(
        "degrade_mode",
        "degraded",
        metadata_update={"reason": "system_pressure"},
        observed_at=datetime.now().isoformat(),
    )

    task_id = queue.add(
        description="Recherchiere dringend den aktuellen Ausfall",
        target_agent="research",
        priority=Priority.HIGH,
        max_retries=1,
    )
    task = queue.claim_next()
    assert task is not None and task["id"] == task_id

    runner = AutonomousRunner(interval_minutes=15)
    monkeypatch.setattr("orchestration.autonomous_runner.get_queue", lambda: queue)

    called = {"executed": False}

    async def _send_tg(description: str, result: str) -> bool:
        del description, result
        called["executed"] = True
        return True

    async def _send_email(description: str, result: str) -> bool:
        del description, result
        return True

    monkeypatch.setattr(runner, "_send_result_to_telegram", _send_tg)
    monkeypatch.setattr(runner, "_send_result_to_email", _send_email)

    async def _fake_failover_run_agent(*, agent_name: str, query: str, tools_description: str, session_id: str, on_alert):
        del agent_name, query, tools_description, session_id, on_alert
        return "ok"

    async def _fake_get_agent_decision(_query: str, session_id: str = "") -> str:
        del session_id
        return "research"

    import sys
    from types import SimpleNamespace

    monkeypatch.setitem(sys.modules, "main_dispatcher", SimpleNamespace(get_agent_decision=_fake_get_agent_decision))
    monkeypatch.setitem(sys.modules, "utils.model_failover", SimpleNamespace(failover_run_agent=_fake_failover_run_agent))

    await runner._execute_task(task)

    updated = queue.get_by_id(task_id)
    assert updated is not None
    assert updated["status"] == "completed"
    assert called["executed"] is True

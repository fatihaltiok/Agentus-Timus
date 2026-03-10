from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from orchestration.autonomous_runner import AutonomousRunner
from orchestration.task_queue import TaskQueue


@pytest.mark.asyncio
async def test_self_healing_task_is_quarantined_while_breaker_is_open(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    observed_at = datetime.now()
    queue.record_self_healing_circuit_breaker_result(
        breaker_key="mcp:mcp_health",
        component="mcp",
        signal="mcp_health",
        success=False,
        failure_threshold=1,
        cooldown_seconds=1800,
        observed_at=observed_at.isoformat(),
    )

    task_id = queue.add(
        description="Self-Healing Playbook V2 (mcp/mcp_health): MCP Health pruefen",
        target_agent="system",
        max_retries=1,
        metadata=json.dumps(
            {
                "self_healing": True,
                "incident_key": "m3_mcp_health_unavailable",
                "component": "mcp",
                "signal": "mcp_health",
                "playbook_template": "mcp_recovery",
            },
            ensure_ascii=True,
        ),
    )
    task = queue.claim_next()
    assert task is not None and task["id"] == task_id

    runner = AutonomousRunner(interval_minutes=15)
    monkeypatch.setattr("orchestration.autonomous_runner.get_queue", lambda: queue)

    sent = {"telegram": 0, "email": 0}

    async def _send_tg(description: str, result: str) -> bool:
        del description, result
        sent["telegram"] += 1
        return True

    async def _send_email(description: str, result: str) -> bool:
        del description, result
        sent["email"] += 1
        return True

    monkeypatch.setattr(runner, "_send_result_to_telegram", _send_tg)
    monkeypatch.setattr(runner, "_send_result_to_email", _send_email)

    await runner._execute_task(task)

    updated = queue.get_by_id(task_id)
    assert updated is not None
    assert updated["status"] == "pending"
    run_at = str(updated.get("run_at") or "")
    assert run_at
    run_at_dt = datetime.fromisoformat(run_at)
    assert run_at_dt > observed_at
    assert run_at_dt <= observed_at + timedelta(seconds=1800)
    assert str(updated.get("error") or "").startswith("quarantined:breaker_open")
    assert sent == {"telegram": 0, "email": 0}

    quarantine = queue.get_self_healing_runtime_state("incident_quarantine:m3_mcp_health_unavailable")
    assert quarantine is not None
    assert quarantine["state_value"] == "active"
    meta = quarantine.get("metadata") or {}
    assert meta.get("reason") == "breaker_open"
    quarantine_until = str(meta.get("quarantine_until") or "")
    assert quarantine_until
    assert meta.get("quarantine_count") == 1

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestration.autonomous_runner import AutonomousRunner
from orchestration.task_queue import TaskQueue


async def _fake_failover_run_agent(*, agent_name: str, query: str, tools_description: str, session_id: str, on_alert):
    del agent_name, query, tools_description, session_id, on_alert
    return "diagnose abgeschlossen"


async def _fake_get_agent_decision(_query: str, session_id: str = "") -> str:
    del session_id
    return "meta"


@pytest.mark.asyncio
async def test_self_healing_notifications_are_deduped_within_cooldown(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_INCIDENT_NOTIFICATION_COOLDOWN_MINUTES", "120")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    metadata = json.dumps(
        {
            "self_healing": True,
            "incident_key": "m3_mcp_health_unavailable",
            "component": "mcp",
            "signal": "mcp_health",
            "playbook_template": "mcp_recovery",
        },
        ensure_ascii=True,
    )
    task_one = queue.add(
        description="Self-Healing Playbook V2 (mcp/mcp_health): MCP Health pruefen",
        target_agent="system",
        metadata=metadata,
        max_retries=1,
    )
    task_two = queue.add(
        description="Self-Healing Playbook V2 (mcp/mcp_health): MCP Health pruefen",
        target_agent="system",
        metadata=metadata,
        max_retries=1,
    )

    runner = AutonomousRunner(interval_minutes=15)
    monkeypatch.setattr("orchestration.autonomous_runner.get_queue", lambda: queue)
    monkeypatch.setitem(sys.modules, "main_dispatcher", SimpleNamespace(get_agent_decision=_fake_get_agent_decision))
    monkeypatch.setitem(sys.modules, "utils.model_failover", SimpleNamespace(failover_run_agent=_fake_failover_run_agent))

    deliveries = {"telegram": 0, "email": 0}

    async def _send_tg(description: str, result: str) -> bool:
        del description, result
        deliveries["telegram"] += 1
        return True

    async def _send_mail(description: str, result: str) -> bool:
        del description, result
        deliveries["email"] += 1
        return True

    monkeypatch.setattr(runner, "_send_result_to_telegram", _send_tg)
    monkeypatch.setattr(runner, "_send_result_to_email", _send_mail)

    claimed_one = queue.claim_next()
    claimed_two = queue.claim_next()
    assert claimed_one is not None and claimed_one["id"] == task_one
    assert claimed_two is not None and claimed_two["id"] == task_two

    await runner._execute_task(claimed_one)
    await runner._execute_task(claimed_two)

    assert deliveries == {"telegram": 1, "email": 1}
    runtime = queue.get_self_healing_runtime_state("incident_notify:m3_mcp_health_unavailable")
    assert runtime is not None
    assert runtime["state_value"] == "cooldown_active"
    metadata_payload = runtime.get("metadata") or {}
    assert metadata_payload.get("sent_count") == 1
    assert metadata_payload.get("suppressed_count") == 1
    assert metadata_payload.get("last_sent_at")
    assert metadata_payload.get("cooldown_until")


@pytest.mark.asyncio
async def test_non_self_healing_tasks_keep_normal_notifications(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    task_one = queue.add(description="Normale autonome Aufgabe A", target_agent="research", max_retries=1)
    task_two = queue.add(description="Normale autonome Aufgabe B", target_agent="research", max_retries=1)

    runner = AutonomousRunner(interval_minutes=15)
    monkeypatch.setattr("orchestration.autonomous_runner.get_queue", lambda: queue)
    monkeypatch.setitem(sys.modules, "main_dispatcher", SimpleNamespace(get_agent_decision=_fake_get_agent_decision))
    monkeypatch.setitem(sys.modules, "utils.model_failover", SimpleNamespace(failover_run_agent=_fake_failover_run_agent))

    deliveries = {"telegram": 0, "email": 0}

    async def _send_tg(description: str, result: str) -> bool:
        del description, result
        deliveries["telegram"] += 1
        return True

    async def _send_mail(description: str, result: str) -> bool:
        del description, result
        deliveries["email"] += 1
        return True

    monkeypatch.setattr(runner, "_send_result_to_telegram", _send_tg)
    monkeypatch.setattr(runner, "_send_result_to_email", _send_mail)

    await runner._execute_task(queue.claim_next())
    await runner._execute_task(queue.claim_next())

    assert deliveries == {"telegram": 2, "email": 2}


@pytest.mark.asyncio
async def test_autonomous_runner_records_task_correlation_events(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    task_id = queue.add(description="Normale autonome Aufgabe C", target_agent="research", max_retries=1)

    runner = AutonomousRunner(interval_minutes=15)
    monkeypatch.setattr("orchestration.autonomous_runner.get_queue", lambda: queue)
    monkeypatch.setitem(sys.modules, "main_dispatcher", SimpleNamespace(get_agent_decision=_fake_get_agent_decision))
    monkeypatch.setitem(sys.modules, "utils.model_failover", SimpleNamespace(failover_run_agent=_fake_failover_run_agent))

    events = []
    monkeypatch.setattr(
        "orchestration.autonomous_runner.record_autonomy_observation",
        lambda event_type, payload, observed_at="": events.append(
            {"event_type": event_type, "payload": dict(payload), "observed_at": observed_at}
        )
        or True,
    )

    async def _send_tg(description: str, result: str) -> bool:
        del description, result
        return False

    async def _send_mail(description: str, result: str) -> bool:
        del description, result
        return False

    monkeypatch.setattr(runner, "_send_result_to_telegram", _send_tg)
    monkeypatch.setattr(runner, "_send_result_to_email", _send_mail)

    await runner._execute_task(queue.claim_next())

    event_types = [item["event_type"] for item in events]
    assert event_types == [
        "task_execution_started",
        "task_route_selected",
        "task_execution_completed",
    ]
    assert events[0]["payload"]["task_id"] == task_id
    assert events[1]["payload"]["agent"] == "research"
    assert events[2]["payload"]["notification_suppressed"] is False

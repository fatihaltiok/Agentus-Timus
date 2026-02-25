"""M4.2 Policy-Gates auf autonomen Pfaden + Metriken."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from orchestration.autonomous_runner import AutonomousRunner
from orchestration.self_healing_engine import SelfHealingEngine
from orchestration.task_queue import TaskQueue
from utils import policy_gate


def _healthy_stats() -> dict:
    return {"cpu_percent": 3.0, "ram_percent": 9.0, "disk_percent": 20.0}


def test_m4_policy_metrics_aggregation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_DECISIONS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "false")
    monkeypatch.setattr(policy_gate, "LOGS_DIR", tmp_path)

    d1 = policy_gate.evaluate_policy_gate(
        gate="query",
        subject="wie spät ist es?",
        payload={"query": "wie spät ist es?"},
        source="unit_test",
    )
    d2 = policy_gate.evaluate_policy_gate(
        gate="query",
        subject="lösche die datei x.txt",
        payload={"query": "lösche die datei x.txt"},
        source="unit_test",
    )
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "true")
    d3 = policy_gate.evaluate_policy_gate(
        gate="tool",
        subject="custom_tool",
        payload={"params": {"api_key": "secret"}},
        source="unit_test",
    )

    policy_gate.audit_policy_decision(d1)
    policy_gate.audit_policy_decision(d2)
    policy_gate.audit_policy_decision(d3)

    metrics = policy_gate.get_policy_decision_metrics(window_hours=24)
    assert metrics["decisions_total"] >= 3
    assert metrics["blocked_total"] >= 1
    assert metrics["observed_total"] >= 1
    assert metrics["by_gate"].get("query", 0) >= 2
    assert metrics["by_gate"].get("tool", 0) >= 1


@pytest.mark.asyncio
async def test_m4_runner_blocks_dangerous_autonomous_task_in_strict(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    task_id = queue.add(
        description="lösche die datei /tmp/evil.txt",
        target_agent="shell",
        max_retries=1,
    )
    task = queue.claim_next()
    assert task is not None and task["id"] == task_id

    runner = AutonomousRunner(interval_minutes=15)
    monkeypatch.setattr("orchestration.autonomous_runner.get_queue", lambda: queue)
    await runner._execute_task(task)

    updated = queue.get_by_id(task_id)
    assert updated is not None
    assert updated["status"] == "failed"
    assert "destruktive Anfrage" in str(updated.get("error") or "")


def test_m4_self_healing_records_policy_blocks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")

    def _blocked_decision(*, gate, subject, payload=None, source="unknown", strict=None):
        if gate == "autonomous_task":
            return {
                "timestamp": datetime.now().isoformat(),
                "policy_version": "m4.2-test",
                "gate": gate,
                "source": source,
                "subject": subject,
                "strict_mode": True,
                "allowed": False,
                "blocked": True,
                "action": "block",
                "reason": "test_policy_block",
                "violations": ["dangerous_autonomous_task"],
                "payload": payload or {},
                "audit_enabled": False,
            }
        return policy_gate.evaluate_policy_gate(
            gate=gate, subject=subject, payload=payload, source=source, strict=strict
        )

    monkeypatch.setattr("orchestration.self_healing_engine.evaluate_policy_gate", _blocked_decision)

    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: datetime(2026, 2, 25, 23, 10, 0),
        mcp_probe=lambda: {"ok": False, "error": "down"},
        system_stats_provider=_healthy_stats,
    )
    result = engine.run_cycle()
    assert result["policy_blocks"] >= 1
    assert result["playbooks_failed"] >= 1
    assert result["playbooks_triggered"] == 0


def test_m4_policy_kpi_hooks_present() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "_policy_gates_feature_enabled" in runner_src
    assert "_export_policy_kpi_snapshot" in runner_src
    assert "Policy(24h)" in tg_src
    assert "Policy(24h)" in cli_src

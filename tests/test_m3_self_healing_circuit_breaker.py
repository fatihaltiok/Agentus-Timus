"""M3.2 Self-Healing: Circuit Breaker + Playbook V2."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from orchestration.self_healing_engine import SelfHealingEngine
from orchestration.task_queue import SelfHealingCircuitBreakerState, TaskQueue


def _healthy_stats() -> dict:
    return {"cpu_percent": 4.0, "ram_percent": 11.0, "disk_percent": 19.0}


def test_m3_circuit_breaker_trips_and_recovers(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")

    r1 = queue.record_self_healing_circuit_breaker_result(
        breaker_key="m3:test",
        component="mcp",
        signal="health",
        success=False,
        failure_threshold=2,
        cooldown_seconds=120,
    )
    assert r1["state"] == SelfHealingCircuitBreakerState.CLOSED
    assert r1["failure_streak"] == 1
    assert r1["tripped"] is False

    r2 = queue.record_self_healing_circuit_breaker_result(
        breaker_key="m3:test",
        component="mcp",
        signal="health",
        success=False,
        failure_threshold=2,
        cooldown_seconds=120,
    )
    assert r2["state"] == SelfHealingCircuitBreakerState.OPEN
    assert r2["tripped"] is True
    assert r2["opened_until"]

    r3 = queue.record_self_healing_circuit_breaker_result(
        breaker_key="m3:test",
        component="mcp",
        signal="health",
        success=True,
        failure_threshold=2,
        cooldown_seconds=120,
    )
    assert r3["state"] == SelfHealingCircuitBreakerState.CLOSED
    assert r3["recovered"] is True

    metrics = queue.get_self_healing_circuit_breaker_metrics()
    assert metrics["breakers_total"] == 1
    assert metrics["open_breakers"] == 0


def test_m3_engine_retries_playbook_after_breaker_cooldown(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_BREAKER_COOLDOWN_SEC", "1")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    clock = {"now": datetime(2026, 2, 25, 12, 0, 0)}

    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: clock["now"],
        mcp_probe=lambda: {"ok": False, "error": "down"},
        system_stats_provider=_healthy_stats,
    )

    first = engine.run_cycle()
    tasks_after_first = queue.get_all(limit=50)
    assert first["playbooks_triggered"] >= 1
    assert len(tasks_after_first) >= 1

    clock["now"] = datetime(2026, 2, 25, 12, 0, 3)  # > cooldown
    second = engine.run_cycle()
    tasks_after_second = queue.get_all(limit=50)
    assert second["playbooks_triggered"] >= 1
    assert len(tasks_after_second) >= len(tasks_after_first) + 1

    breaker = queue.get_self_healing_circuit_breaker("mcp:mcp_health")
    assert breaker is not None
    assert breaker["trip_count"] >= 2
    assert breaker["state"] == SelfHealingCircuitBreakerState.OPEN


def test_m3_playbook_v2_metadata_present(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_BREAKER_FAILURE_THRESHOLD", "5")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: datetime(2026, 2, 25, 15, 0, 0),
        mcp_probe=lambda: {"ok": False, "error": "down"},
        system_stats_provider=_healthy_stats,
    )
    result = engine.run_cycle()
    assert result["playbooks_triggered"] >= 1

    task = queue.get_all(limit=1)[0]
    meta = json.loads(str(task.get("metadata") or "{}"))
    assert meta.get("playbook_version") == "v2"
    assert meta.get("playbook_template") == "mcp_recovery"
    assert isinstance(meta.get("playbook_steps"), list) and meta.get("playbook_steps")


def test_m3_circuit_breaker_hooks_present() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "circuit_breakers_open" in runner_src
    assert "BreakerOpen" in tg_src
    assert "BreakerOpen" in cli_src

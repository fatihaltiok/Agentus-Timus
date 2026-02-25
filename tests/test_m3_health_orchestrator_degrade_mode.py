"""M3.3 Health-Orchestrator: Routing + Degrade-Mode."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from orchestration.health_orchestrator import HealthOrchestrator
from orchestration.self_healing_engine import SelfHealingEngine
from orchestration.task_queue import Priority, TaskQueue


def _healthy_stats() -> dict:
    return {"cpu_percent": 3.0, "ram_percent": 10.0, "disk_percent": 20.0}


def test_m3_runtime_state_roundtrip_and_metrics(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")

    before = queue.get_self_healing_metrics()
    assert before["degrade_mode"] == "normal"
    assert before["degrade_reason"] is None

    update = queue.set_self_healing_runtime_state(
        "degrade_mode",
        "degraded",
        metadata_update={"reason": "degraded_threshold_exceeded", "source": "unit_test"},
        observed_at="2026-02-25T18:00:00",
    )
    assert update["state_value"] == "degraded"
    assert update["metadata"]["reason"] == "degraded_threshold_exceeded"

    state = queue.get_self_healing_runtime_state("degrade_mode")
    assert state is not None
    assert state["state_value"] == "degraded"
    assert state["metadata"]["source"] == "unit_test"

    after = queue.get_self_healing_metrics()
    assert after["degrade_mode"] == "degraded"
    assert after["degrade_reason"] == "degraded_threshold_exceeded"


def test_m3_health_orchestrator_routing_prioritizes_critical_paths() -> None:
    orchestrator = HealthOrchestrator(now_provider=lambda: datetime(2026, 2, 25, 18, 30, 0))

    mcp_route = orchestrator.route_recovery(
        component="mcp",
        signal="mcp_health",
        severity="high",
        default_target_agent="meta",
        default_priority=int(Priority.HIGH),
        default_template="mcp_recovery",
    )
    assert mcp_route["target_agent"] == "system"
    assert mcp_route["priority"] == int(Priority.CRITICAL)
    assert mcp_route["lane"] == "self_healing_fast_lane"
    assert mcp_route["playbook_template"] == "mcp_recovery"

    queue_route = orchestrator.route_recovery(
        component="queue",
        signal="pending_backlog",
        severity="medium",
        default_target_agent="meta",
        default_priority=int(Priority.HIGH),
        default_template="queue_backlog_relief",
    )
    assert queue_route["target_agent"] == "meta"
    assert queue_route["lane"] == "self_healing_standard_lane"
    assert queue_route["playbook_template"] == "queue_backlog_relief"


def test_m3_engine_persists_degrade_mode_and_routing_metadata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_BREAKER_FAILURE_THRESHOLD", "5")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: datetime(2026, 2, 25, 19, 0, 0),
        mcp_probe=lambda: {"ok": False, "error": "down"},
        system_stats_provider=_healthy_stats,
    )

    result = engine.run_cycle()
    assert result["status"] == "ok"
    assert result["routed_playbooks"] >= 1
    assert result["degrade_mode"] in {"degraded", "emergency"}
    assert result["degrade_reason"]
    assert result["routed_by_agent"].get("system", 0) >= 1

    runtime = queue.get_self_healing_runtime_state("degrade_mode")
    assert runtime is not None
    assert runtime["state_value"] == result["degrade_mode"]
    assert runtime["metadata"].get("reason")

    tasks = queue.get_all(limit=20)
    playbook_task = next((t for t in tasks if "Self-Healing Playbook" in str(t.get("description") or "")), None)
    assert playbook_task is not None
    meta = json.loads(str(playbook_task.get("metadata") or "{}"))
    routing = meta.get("routing", {})
    assert routing.get("lane") == "self_healing_fast_lane"
    assert routing.get("target_agent") == "system"


def test_m3_degrade_mode_returns_to_normal_after_recovery(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", "999")
    monkeypatch.setenv("AUTONOMY_SELF_HEALING_BREAKER_FAILURE_THRESHOLD", "5")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    state = {"ok": False, "now": datetime(2026, 2, 25, 20, 0, 0)}

    def _probe() -> dict:
        return {"ok": state["ok"], "status": "healthy" if state["ok"] else "down"}

    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: state["now"],
        mcp_probe=_probe,
        system_stats_provider=_healthy_stats,
    )

    first = engine.run_cycle()
    assert first["degrade_mode"] in {"degraded", "emergency"}

    state["ok"] = True
    state["now"] = datetime(2026, 2, 25, 20, 5, 0)
    second = engine.run_cycle()
    assert second["degrade_mode"] == "normal"

    runtime = queue.get_self_healing_runtime_state("degrade_mode")
    assert runtime is not None
    assert runtime["state_value"] == "normal"


def test_m3_degrade_mode_hooks_present() -> None:
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    engine_src = Path("orchestration/self_healing_engine.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "HealthOrchestrator" in engine_src
    assert "set_self_healing_runtime_state" in engine_src
    assert "degrade_mode" in runner_src
    assert "Mode {healing_metrics.get('degrade_mode'" in tg_src
    assert "Mode {healing_metrics.get('degrade_mode'" in cli_src

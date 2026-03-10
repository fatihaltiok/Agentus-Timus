from __future__ import annotations

from datetime import datetime
from pathlib import Path

from orchestration.self_healing_engine import SelfHealingEngine
from orchestration.task_queue import TaskQueue


def _healthy_stats() -> dict:
    return {"cpu_percent": 4.0, "ram_percent": 10.0, "disk_percent": 22.0}


def test_incident_memory_turns_conservative_after_bad_outcomes(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: datetime(2026, 3, 10, 16, 0, 0),
        mcp_probe=lambda: {"ok": True},
        system_stats_provider=_healthy_stats,
    )

    engine._record_incident_memory(
        component="mcp",
        signal="mcp_health",
        incident_key="m3_mcp_health_unavailable",
        outcome="opened",
        observed_at="2026-03-10T16:00:00",
    )
    engine._record_incident_memory(
        component="mcp",
        signal="mcp_health",
        incident_key="m3_mcp_health_unavailable",
        outcome="escalated",
        observed_at="2026-03-10T16:01:00",
    )

    memory = queue.get_self_healing_runtime_state("incident_memory:mcp:mcp_health")
    assert memory is not None
    assert memory["state_value"] == "known_bad_pattern"
    meta = memory.get("metadata") or {}
    assert meta.get("seen_count") == 1
    assert meta.get("escalated_count") == 1
    assert meta.get("conservative_mode") is True
    assert meta.get("last_outcome") == "escalated"


def test_recovery_ladder_uses_pattern_memory_conservative_mode(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    engine = SelfHealingEngine(
        queue=queue,
        now_provider=lambda: datetime(2026, 3, 10, 16, 0, 0),
        mcp_probe=lambda: {"ok": True},
        system_stats_provider=_healthy_stats,
    )

    result = engine._build_recovery_ladder_state(
        incident_key="m3_mcp_health_unavailable",
        component="mcp",
        signal="mcp_health",
        severity="high",
        playbook_attempts=3,
        max_attempts=3,
        allow_playbook=True,
        retry_due=False,
        should_attempt=True,
        attempts_exhausted=True,
        verified_outage=True,
        conservative_mode=True,
    )

    assert result["phase"] == "blocked"
    assert result["stage"] == "manual_review"
    assert result["escalation_allowed"] is False

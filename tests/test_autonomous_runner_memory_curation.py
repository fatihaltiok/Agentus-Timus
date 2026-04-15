from __future__ import annotations

import pytest

from orchestration.autonomous_runner import AutonomousRunner


@pytest.mark.asyncio
async def test_autonomous_runner_memory_curation_cycle_returns_disabled_without_feature(monkeypatch) -> None:
    runner = AutonomousRunner(interval_minutes=15)

    monkeypatch.setattr(
        "orchestration.memory_curation.get_memory_curation_autonomy_settings",
        lambda: {"enabled": False, "interval_heartbeats": 12},
    )

    summary = await runner._run_memory_curation_autonomy_cycle()

    assert summary["status"] == "disabled"
    assert runner._memory_curation_autonomy_running is False


@pytest.mark.asyncio
async def test_autonomous_runner_memory_curation_cycle_runs_engine_and_resets_busy_flag(monkeypatch) -> None:
    runner = AutonomousRunner(interval_minutes=15)
    runner._heartbeat_count = 4

    queue_stub = object()
    monkeypatch.setattr("orchestration.autonomous_runner.get_queue", lambda: queue_stub)
    monkeypatch.setattr(
        "orchestration.memory_curation.get_memory_curation_autonomy_settings",
        lambda: {"enabled": True, "interval_heartbeats": 1, "max_actions": 1},
    )

    async def _fake_cycle(*, queue=None, heartbeat_count: int = 0):
        assert queue is queue_stub
        assert heartbeat_count == 4
        return {
            "status": "complete",
            "snapshot_id": "snap-e52",
            "candidate_count": 3,
            "action_count": 1,
            "verification": {"passed": True},
        }

    monkeypatch.setattr(
        "orchestration.memory_curation.run_memory_curation_autonomy_cycle",
        _fake_cycle,
    )

    summary = await runner._run_memory_curation_autonomy_cycle()

    assert summary["status"] == "complete"
    assert summary["snapshot_id"] == "snap-e52"
    assert summary["enabled"] is True
    assert runner._memory_curation_autonomy_running is False


@pytest.mark.asyncio
async def test_autonomous_runner_memory_curation_cycle_returns_busy_when_already_running() -> None:
    runner = AutonomousRunner(interval_minutes=15)
    runner._memory_curation_autonomy_running = True

    summary = await runner._run_memory_curation_autonomy_cycle()

    assert summary == {"status": "busy"}

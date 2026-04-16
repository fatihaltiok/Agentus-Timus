from __future__ import annotations

import pytest

from tools.maintenance_tool.tool import (
    get_memory_curation_status,
    rollback_memory_curation,
    run_memory_maintenance,
)


@pytest.mark.asyncio
async def test_run_memory_maintenance_delegates_to_memory_curation(monkeypatch) -> None:
    monkeypatch.setattr(
        "tools.maintenance_tool.tool._run_memory_curation_mvp",
        lambda stale_days, max_actions, dry_run: {
            "status": "complete",
            "snapshot_id": "snap-1",
            "metrics_before": {"active_items": 5},
            "metrics_after": {"active_items": 3},
            "verification": {"passed": True},
        },
    )

    result = await run_memory_maintenance(days_old_threshold=21, access_count_threshold=7, max_actions=4, dry_run=False)

    assert result["status"] == "complete"
    assert result["snapshot_id"] == "snap-1"
    assert result["legacy_access_count_threshold"] == 7


@pytest.mark.asyncio
async def test_get_memory_curation_status_tool_returns_engine_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "tools.maintenance_tool.tool._get_memory_curation_status",
        lambda stale_days, limit: {
            "status": "ok",
            "current_metrics": {"active_items": 2},
            "last_snapshots": [{"snapshot_id": "snap-2"}],
            "pending_candidates": [],
            "pending_retrieval_probes": [{"probe_id": "probe-1"}],
            "latest_retrieval_quality": {"verdict": {"passed": True}},
            "quality_governance": {"state": "allow", "blocked": False},
            "autonomy_governance": {"state": "allow", "blocked": False},
        },
    )
    async def _fake_operator_snapshot(*, limit: int = 5, queue=None):
        return {
            "summary": {"blocked_lane_count": 1, "blocked_lanes": ["memory_curation"]},
            "governance": {"state": "cooldown_active", "action": "hold"},
            "approval": {"pending_count": 0, "highest_risk_class": "none"},
            "explainability": {"count": 1},
            "lanes": {
                "improvement": {"lane": "improvement", "state": "allow", "blocked": False},
                "memory_curation": {"lane": "memory_curation", "state": "cooldown_active", "blocked": True},
            },
        }

    monkeypatch.setattr(
        "orchestration.phase_e_operator_snapshot.collect_phase_e_operator_snapshot",
        _fake_operator_snapshot,
    )

    result = await get_memory_curation_status(days_old_threshold=14, limit=3)

    assert result["status"] == "ok"
    assert result["last_snapshots"][0]["snapshot_id"] == "snap-2"
    assert result["pending_retrieval_probes"][0]["probe_id"] == "probe-1"
    assert result["latest_retrieval_quality"]["verdict"]["passed"] is True
    assert result["quality_governance"]["state"] == "allow"
    assert result["autonomy_governance"]["state"] == "allow"
    assert result["operator_surface"]["contract_version"] == "phase_e_operator_v1"
    assert result["operator_surface"]["focus_lane"] == "memory_curation"
    assert result["operator_surface"]["focused_lane"]["lane"] == "memory_curation"


@pytest.mark.asyncio
async def test_rollback_memory_curation_tool_returns_engine_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "tools.maintenance_tool.tool._rollback_memory_curation",
        lambda snapshot_id: {
            "status": "rolled_back",
            "snapshot_id": snapshot_id,
            "restored_items": 4,
        },
    )

    result = await rollback_memory_curation("snap-3")

    assert result["status"] == "rolled_back"
    assert result["snapshot_id"] == "snap-3"

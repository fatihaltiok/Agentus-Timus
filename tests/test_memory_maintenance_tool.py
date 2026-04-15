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
            "autonomy_governance": {"state": "allow", "blocked": False},
        },
    )

    result = await get_memory_curation_status(days_old_threshold=14, limit=3)

    assert result["status"] == "ok"
    assert result["last_snapshots"][0]["snapshot_id"] == "snap-2"
    assert result["pending_retrieval_probes"][0]["probe_id"] == "probe-1"
    assert result["latest_retrieval_quality"]["verdict"]["passed"] is True
    assert result["autonomy_governance"]["state"] == "allow"


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

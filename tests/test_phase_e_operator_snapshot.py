from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestration.phase_e_operator_snapshot import (
    build_phase_e_operator_snapshot,
    collect_phase_e_operator_snapshot,
    summarize_phase_e_pending_approvals,
)


def test_build_phase_e_operator_snapshot_unifies_lanes_and_system() -> None:
    snapshot = build_phase_e_operator_snapshot(
        system_snapshot={
            "services": {
                "mcp": {"ok": True, "active": "active", "uptime_seconds": 120.0},
                "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 90.0},
                "qdrant": {"ok": False, "active": "failed", "uptime_seconds": 0.0},
            },
            "ops": {"state": "critical", "critical_alerts": 1, "warnings": 2},
            "mcp_runtime": {"state": "healthy", "reason": "steady_state", "ready": True},
            "request_runtime": {"state": "warn", "reason": "task_failures_present", "chat_requests_total": 4, "task_failed_total": 1},
            "stability_gate": {"state": "hold"},
        },
        observation_summary={
            "improvement_runtime": {
                "autonomy_decisions_total": 3,
                "enqueue_creation_rate": 0.33,
                "verified_rate": 0.5,
                "not_verified_rate": 0.5,
            },
            "memory_curation_runtime": {
                "autonomy_completion_rate": 1.0,
                "verification_pass_rate": 1.0,
                "retrieval_pass_rate": 1.0,
                "rollback_rate": 0.0,
            },
        },
        recent_events=[
            {
                "event_type": "improvement_task_autonomy_event",
                "observed_at": "2026-04-16T00:10:00+02:00",
                "payload": {
                    "candidate_id": "m12:1",
                    "autoenqueue_state": "strict_force_off",
                    "rollout_guard_state": "strict_force_off",
                },
            },
            {
                "event_type": "task_execution_failed",
                "observed_at": "2026-04-16T00:11:00+02:00",
                "payload": {
                    "source": "improvement_task_bridge",
                    "task_id": "task-1",
                    "task_outcome_state": "blocked",
                    "verification_state": "blocked",
                },
            },
            {
                "event_type": "memory_curation_autonomy_blocked",
                "observed_at": "2026-04-16T00:12:00+02:00",
                "payload": {"state": "cooldown_active", "reasons": ["recent_memory_curation_run"], "snapshot_id": "snap-1"},
            },
            {
                "event_type": "memory_curation_completed",
                "observed_at": "2026-04-16T00:13:00+02:00",
                "payload": {"snapshot_id": "snap-2", "final_status": "complete", "verification_passed": True},
            },
        ],
        improvement_governance={
            "rollout_guard_state": "strict_force_off",
            "rollout_guard_blocked": True,
            "rollout_guard_reasons": ["policy_runtime:strict_force_off"],
            "shadowed_guard_states": ["verification_backpressure"],
            "shadowed_guard_reasons": {
                "verification_backpressure": ["verification_sample_total:3"],
            },
            "strict_force_off": True,
            "verification_backpressure": {
                "blocked": True,
                "active": False,
                "shadowed": True,
                "reasons": ["verification_sample_total:3"],
            },
        },
        improvement_candidate_views=[
            {"candidate_id": "m12:1", "summary": "tool:find_text_coordinates | prio=1.320"},
        ],
        memory_curation_status={
            "current_metrics": {"active_items": 100, "archived_items": 10, "summary_items": 3, "stale_active_items": 4},
            "last_snapshots": [{"snapshot_id": "snap-2", "status": "completed"}],
            "pending_candidates": [
                {
                    "candidate_id": "mc:1",
                    "action": "summarize",
                    "category": "working_memory",
                    "tier": "ephemeral",
                    "reason": "group:working_memory",
                    "item_count": 5,
                }
            ],
            "autonomy_governance": {
                "state": "cooldown_active",
                "blocked": True,
                "reasons": ["recent_memory_curation_run"],
            },
            "quality_governance": {
                "state": "retrieval_backpressure",
                "blocked": True,
                "reasons": ["pass_rate=0.25", "failed_runs=2"],
            },
        },
        approval_surface={
            "state": "approval_required",
            "blocked": True,
            "pending_count": 1,
            "highest_risk_class": "critical",
            "requested_actions": ["rollback"],
            "lanes": ["improvement"],
            "oldest_pending_minutes": 42.0,
            "items": [
                {
                    "request_id": "req-1",
                    "lane": "improvement",
                    "risk_class": "critical",
                    "requested_action": "rollback",
                    "approval_reason": "rollback_requires_approval",
                }
            ],
        },
    )

    assert snapshot["summary"]["blocked_lane_count"] == 2
    assert snapshot["summary"]["blocked_lanes"] == ["improvement", "memory_curation"]
    assert snapshot["system"]["state"] == "critical"
    assert snapshot["system"]["services"]["qdrant"]["ok"] is False
    assert snapshot["lanes"]["improvement"]["state"] == "strict_force_off"
    assert snapshot["lanes"]["improvement"]["blocked"] is True
    assert snapshot["lanes"]["improvement"]["last_failed_at"] == "2026-04-16T00:11:00+02:00"
    assert snapshot["lanes"]["improvement"]["next_candidate_count"] == 1
    assert snapshot["lanes"]["memory_curation"]["state"] == "cooldown_active"
    assert snapshot["lanes"]["memory_curation"]["blocked"] is True
    assert snapshot["lanes"]["memory_curation"]["last_snapshot_id"] == "snap-2"
    assert snapshot["lanes"]["memory_curation"]["last_completed_at"] == "2026-04-16T00:13:00+02:00"
    assert snapshot["lanes"]["memory_curation"]["next_candidates"][0]["candidate_id"] == "mc:1"
    assert snapshot["summary"]["governance_state"] == "strict_force_off"
    assert snapshot["summary"]["governance_action"] == "freeze"
    assert snapshot["summary"]["governance_risk_class"] == "critical"
    assert snapshot["governance"]["action"] == "freeze"
    assert snapshot["governance"]["highest_risk_class"] == "critical"
    assert snapshot["governance"]["blocked_lane_count"] == 3
    assert snapshot["governance"]["signals"]["strict_force_off"]["active"] is True
    assert snapshot["governance"]["signals"]["verification_backpressure"]["shadowed"] is True
    assert snapshot["governance"]["signals"]["retrieval_backpressure"]["active"] is True
    assert snapshot["governance"]["signals"]["degraded_mode"]["active"] is True
    assert snapshot["governance"]["lanes"]["improvement"]["action"] == "freeze"
    assert snapshot["governance"]["lanes"]["memory_curation"]["action"] == "hold"
    assert snapshot["governance"]["lanes"]["system"]["blocked"] is True
    assert snapshot["summary"]["approval_pending_count"] == 1
    assert snapshot["summary"]["approval_highest_risk_class"] == "critical"
    assert snapshot["approval"]["state"] == "approval_required"
    assert snapshot["approval"]["items"][0]["requested_action"] == "rollback"


@pytest.mark.asyncio
async def test_collect_phase_e_operator_snapshot_uses_live_builders(monkeypatch) -> None:
    async def _fake_collect_status_snapshot():
        return {
            "services": {
                "mcp": {"ok": True, "active": "active", "uptime_seconds": 10.0},
                "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 9.0},
            },
            "ops": {"state": "healthy", "critical_alerts": 0, "warnings": 0},
            "mcp_runtime": {"state": "healthy", "reason": "steady_state", "ready": True},
            "request_runtime": {"state": "healthy", "reason": "steady_state", "chat_requests_total": 2, "task_failed_total": 0},
            "stability_gate": {"state": "pass"},
        }

    class _Store:
        def iter_events(self):
            return [
                {
                    "event_type": "memory_curation_autonomy_completed",
                    "observed_at": "2026-04-16T00:20:00+02:00",
                    "payload": {"status": "complete", "snapshot_id": "snap-live"},
                }
            ]

    monkeypatch.setattr("gateway.status_snapshot.collect_status_snapshot", _fake_collect_status_snapshot)
    monkeypatch.setattr(
        "orchestration.autonomy_observation.build_autonomy_observation_summary",
        lambda since="", until="": {
            "improvement_runtime": {"verified_rate": 1.0},
            "memory_curation_runtime": {"verification_pass_rate": 1.0},
        },
    )
    monkeypatch.setattr(
        "orchestration.autonomy_observation.get_autonomy_observation_store",
        lambda: _Store(),
    )
    monkeypatch.setattr(
        "orchestration.self_improvement_engine.get_improvement_engine",
        lambda: SimpleNamespace(
            get_normalized_suggestions=lambda applied=False: [{"candidate_id": "m12:1"}],
        ),
    )

    async def _fake_combined_candidates(self):
        return [{"candidate_id": "m12:1"}]

    monkeypatch.setattr(
        "orchestration.session_reflection.SessionReflectionLoop.get_improvement_suggestions",
        _fake_combined_candidates,
    )
    monkeypatch.setattr(
        "orchestration.improvement_candidates.build_candidate_operator_views",
        lambda candidates, limit=5: [{"candidate_id": "m12:1", "summary": "candidate"}],
    )
    monkeypatch.setattr(
        "orchestration.improvement_task_autonomy.get_improvement_task_rollout_guard",
        lambda queue: {"state": "allow", "blocked": False, "reasons": []},
    )
    monkeypatch.setattr(
        "orchestration.improvement_task_autonomy.build_improvement_task_governance_view",
        lambda queue=None, rollout_guard=None: {
            "rollout_guard_state": "allow",
            "rollout_guard_blocked": False,
            "rollout_guard_reasons": [],
            "strict_force_off": False,
            "verification_backpressure": {"blocked": False, "active": False, "shadowed": False},
        },
    )
    monkeypatch.setattr(
        "orchestration.memory_curation.get_memory_curation_status",
        lambda queue=None, stale_days=30, limit=5: {
            "current_metrics": {"active_items": 4, "archived_items": 1, "summary_items": 1, "stale_active_items": 0},
            "last_snapshots": [{"snapshot_id": "snap-live", "status": "completed"}],
            "pending_candidates": [],
            "autonomy_governance": {"state": "allow", "blocked": False, "reasons": []},
            "quality_governance": {"state": "allow", "blocked": False, "reasons": []},
        },
    )
    monkeypatch.setattr("orchestration.task_queue.get_queue", lambda: object())

    snapshot = await collect_phase_e_operator_snapshot(limit=3)

    assert snapshot["system"]["state"] == "healthy"
    assert snapshot["lanes"]["improvement"]["blocked"] is False
    assert snapshot["lanes"]["memory_curation"]["last_snapshot_id"] == "snap-live"
    assert snapshot["summary"]["blocked_lane_count"] == 0
    assert snapshot["governance"]["blocked"] is False
    assert snapshot["governance"]["action"] == "allow"
    assert snapshot["governance"]["highest_risk_class"] == "none"
    assert snapshot["approval"]["pending_count"] == 0
    assert snapshot["approval"]["state"] == "clear"


def test_summarize_phase_e_pending_approvals_tracks_risk_and_oldest_pending() -> None:
    summary = summarize_phase_e_pending_approvals(
        [
            {
                "lane": "improvement",
                "risk_class": "high",
                "requested_action": "promote_canary",
                "pending_minutes": 12.5,
            },
            {
                "lane": "improvement",
                "risk_class": "critical",
                "requested_action": "rollback",
                "pending_minutes": 42.0,
            },
        ]
    )

    assert summary["pending_count"] == 2
    assert summary["highest_risk_class"] == "critical"
    assert summary["requested_actions"] == ["promote_canary", "rollback"]
    assert summary["lanes"] == ["improvement"]
    assert summary["oldest_pending_minutes"] == 42.0

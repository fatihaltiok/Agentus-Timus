from __future__ import annotations

import pytest

from orchestration.phase_f_runtime_board import (
    PHASE_F_RUNTIME_BOARD_VERSION,
    build_phase_f_runtime_board,
    collect_phase_f_runtime_board,
    render_phase_f_runtime_board,
)


def _sample_system_snapshot() -> dict:
    return {
        "services": {
            "mcp": {"ok": True, "active": "active", "uptime_seconds": 100.0},
            "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 95.0},
            "qdrant": {"ok": True, "active": "active", "uptime_seconds": 300.0},
        },
        "providers": {
            "openai": {"state": "ok", "api_configured": True},
            "openrouter": {"state": "error", "api_configured": True},
        },
        "ops": {"state": "warn", "critical_alerts": 0, "warnings": 2, "unhealthy_providers": 1},
        "ops_gate": {"state": "hold"},
        "mcp_runtime": {"state": "healthy", "reason": "steady_state"},
        "request_runtime": {
            "state": "warn",
            "reason": "recent_failure",
            "chat_requests_total": 4,
            "chat_completed_total": 3,
            "chat_failed_total": 1,
            "task_failed_total": 1,
            "user_visible_failures_total": 1,
            "last_outcome": {"observed_at": "2026-04-17T11:00:00+02:00"},
        },
        "self_healing": {
            "degrade_mode": "limited",
            "open_incidents": 2,
            "circuit_breakers_open": 1,
            "resource_guard_state": "active",
        },
        "self_hardening": {"state": "pending_approval"},
        "stability_gate": {"state": "hold"},
        "budget": {"state": "warn"},
        "api_control": {"active_provider_count": 2},
    }


def _sample_observation_summary() -> dict:
    return {
        "communication_runtime": {
            "tasks_started_total": 2,
            "tasks_completed_total": 1,
            "tasks_failed_total": 1,
            "tasks_partial_total": 0,
            "email_send_failed_total": 1,
        },
        "challenge_runtime": {
            "challenge_required_total": 2,
            "challenge_resolved_total": 1,
            "challenge_reblocked_total": 0,
            "resolution_rate": 0.5,
        },
    }


def _sample_operator_snapshot() -> dict:
    return {
        "approval": {
            "pending_count": 1,
            "highest_risk_class": "critical",
            "requested_actions": ["rollback"],
        },
        "governance": {
            "lanes": {
                "improvement": {"action": "freeze", "risk_class": "critical"},
                "memory_curation": {"action": "hold", "risk_class": "medium"},
            }
        },
        "lanes": {
            "improvement": {
                "lane": "improvement",
                "state": "strict_force_off",
                "blocked": True,
                "reasons": ["policy_runtime:strict_force_off"],
                "runtime": {"verified_rate": 0.5},
                "next_candidate_count": 1,
                "last_action": {"observed_at": "2026-04-17T10:59:00+02:00"},
            },
            "memory_curation": {
                "lane": "memory_curation",
                "state": "cooldown_active",
                "blocked": True,
                "reasons": ["recent_memory_curation_run"],
                "runtime": {"retrieval_pass_rate": 1.0},
                "next_candidate_count": 2,
                "last_action": {"observed_at": "2026-04-17T10:58:00+02:00"},
            },
        },
    }


def test_build_phase_f_runtime_board_unifies_core_lanes() -> None:
    board = build_phase_f_runtime_board(
        system_snapshot=_sample_system_snapshot(),
        observation_summary=_sample_observation_summary(),
        operator_snapshot=_sample_operator_snapshot(),
    )

    assert board["contract_version"] == PHASE_F_RUNTIME_BOARD_VERSION
    assert board["summary"]["lane_count"] == 8
    assert board["summary"]["blocked_lane_count"] >= 3
    assert board["summary"]["degraded_lane_count"] >= 4
    assert board["summary"]["highest_risk_class"] == "critical"
    assert board["summary"]["recommended_action"] == "freeze"
    assert board["summary"]["pending_approval_count"] == 1
    assert board["summary"]["unhealthy_provider_count"] == 1
    assert board["lanes"]["stack"]["state"] == "warn"
    assert board["lanes"]["request_flow"]["state"] == "warn"
    assert board["lanes"]["approval_auth"]["state"] == "approval_required"
    assert board["lanes"]["communication"]["state"] == "warn"
    assert board["lanes"]["improvement"]["state"] == "strict_force_off"
    assert board["lanes"]["memory_curation"]["state"] == "cooldown_active"
    assert board["lanes"]["recovery"]["state"] == "degraded"
    assert board["lanes"]["providers"]["state"] == "degraded"


@pytest.mark.asyncio
async def test_collect_phase_f_runtime_board_wraps_live_builders(monkeypatch) -> None:
    async def _fake_collect_status_snapshot():
        return _sample_system_snapshot()

    monkeypatch.setattr(
        "orchestration.phase_f_runtime_board.collect_status_snapshot",
        _fake_collect_status_snapshot,
        raising=False,
    )
    monkeypatch.setattr(
        "orchestration.autonomy_observation.build_autonomy_observation_summary",
        lambda: _sample_observation_summary(),
    )
    monkeypatch.setattr(
        "orchestration.phase_e_operator_snapshot.collect_phase_e_operator_snapshot",
        lambda limit=5, queue=None: _sample_operator_snapshot(),
    )
    monkeypatch.setattr(
        "orchestration.task_queue.get_queue",
        lambda: object(),
    )

    board = await collect_phase_f_runtime_board()

    assert board["contract_version"] == PHASE_F_RUNTIME_BOARD_VERSION
    assert board["summary"]["lane_count"] == 8
    assert board["lanes"]["approval_auth"]["metrics"]["pending_approval_count"] == 1


def test_render_phase_f_runtime_board_contains_core_sections() -> None:
    text = render_phase_f_runtime_board(
        build_phase_f_runtime_board(
            system_snapshot=_sample_system_snapshot(),
            observation_summary=_sample_observation_summary(),
            operator_snapshot=_sample_operator_snapshot(),
        )
    )

    assert "Phase F Runtime Board" in text
    assert "Lanes:" in text
    assert "request_flow" in text
    assert "approval_auth" in text
    assert "memory_curation" in text

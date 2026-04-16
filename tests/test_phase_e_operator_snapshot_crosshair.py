from __future__ import annotations

import deal

from orchestration.phase_e_operator_snapshot import (
    build_phase_e_operator_surface,
    summarize_phase_e_explainability_entries,
    summarize_phase_e_governance_lanes,
    summarize_phase_e_operator_lanes,
    summarize_phase_e_pending_approvals,
)


@deal.post(lambda r: r == 1)
def _contract_blocked_lane_count_matches_names_crosshair() -> int:
    summary = summarize_phase_e_operator_lanes(
        {
            "improvement": {
                "blocked": True,
                "last_action": {"observed_at": "2026-04-16T00:10:00+02:00"},
            },
            "memory_curation": {
                "blocked": False,
                "last_action": {"observed_at": "2026-04-16T00:09:00+02:00"},
            },
        }
    )
    return 1 if summary["blocked_lane_count"] == len(summary["blocked_lanes"]) == 1 else 0


@deal.post(lambda r: r == "2026-04-16T00:11:00+02:00")
def _contract_last_activity_uses_latest_observed_at_crosshair() -> str:
    summary = summarize_phase_e_operator_lanes(
        {
            "improvement": {
                "blocked": False,
                "last_action": {"observed_at": "2026-04-16T00:10:00+02:00"},
            },
            "memory_curation": {
                "blocked": False,
                "last_action": {"observed_at": "2026-04-16T00:11:00+02:00"},
            },
        }
    )
    return str(summary["last_activity_at"])


@deal.post(lambda r: r == 1)
def _contract_governance_blocked_lane_count_matches_names_crosshair() -> int:
    summary = summarize_phase_e_governance_lanes(
        {
            "improvement": {
                "blocked": True,
                "state": "strict_force_off",
                "action": "freeze",
                "risk_class": "critical",
                "reasons": ["policy_runtime:strict_force_off"],
                "active_states": ["strict_force_off"],
            },
            "memory_curation": {
                "blocked": False,
                "state": "allow",
                "action": "allow",
                "risk_class": "none",
                "reasons": [],
                "active_states": [],
            },
            "system": {
                "blocked": False,
                "state": "healthy",
                "action": "allow",
                "risk_class": "none",
                "reasons": [],
                "active_states": [],
            },
        }
    )
    return 1 if summary["blocked_lane_count"] == len(summary["blocked_lanes"]) == 1 else 0


@deal.post(lambda r: r == "freeze")
def _contract_governance_action_prefers_freeze_over_hold_crosshair() -> str:
    summary = summarize_phase_e_governance_lanes(
        {
            "improvement": {
                "blocked": True,
                "state": "strict_force_off",
                "action": "freeze",
                "risk_class": "critical",
                "reasons": ["policy_runtime:strict_force_off"],
                "active_states": ["strict_force_off"],
            },
            "memory_curation": {
                "blocked": True,
                "state": "cooldown_active",
                "action": "hold",
                "risk_class": "medium",
                "reasons": ["recent_memory_curation_run"],
                "active_states": ["cooldown_active"],
            },
            "system": {
                "blocked": False,
                "state": "healthy",
                "action": "allow",
                "risk_class": "none",
                "reasons": [],
                "active_states": [],
            },
        }
    )
    return str(summary["action"])


@deal.post(lambda r: r == 2)
def _contract_pending_approval_count_matches_items_crosshair() -> int:
    summary = summarize_phase_e_pending_approvals(
        [
            {
                "lane": "improvement",
                "risk_class": "high",
                "requested_action": "promote_canary",
                "pending_minutes": 10.0,
            },
            {
                "lane": "improvement",
                "risk_class": "critical",
                "requested_action": "rollback",
                "pending_minutes": 30.0,
            },
        ]
    )
    return int(summary["pending_count"])


@deal.post(lambda r: r == "critical")
def _contract_pending_approval_risk_prefers_critical_crosshair() -> str:
    summary = summarize_phase_e_pending_approvals(
        [
            {
                "lane": "memory_curation",
                "risk_class": "medium",
                "requested_action": "hold",
                "pending_minutes": 5.0,
            },
            {
                "lane": "improvement",
                "risk_class": "critical",
                "requested_action": "rollback",
                "pending_minutes": 25.0,
            },
        ]
    )
    return str(summary["highest_risk_class"])


@deal.post(lambda r: r == 2)
def _contract_explainability_count_matches_items_crosshair() -> int:
    summary = summarize_phase_e_explainability_entries(
        [
            {"when": "2026-04-16T00:10:00+02:00", "lane": "improvement", "result": "blocked"},
            {"when": "2026-04-16T00:11:00+02:00", "lane": "memory_curation", "result": "rolled_back"},
        ]
    )
    return int(summary["count"])


@deal.post(lambda r: r == 1)
def _contract_explainability_failure_count_tracks_errors_crosshair() -> int:
    summary = summarize_phase_e_explainability_entries(
        [
            {"when": "2026-04-16T00:10:00+02:00", "lane": "improvement", "result": "error"},
            {"when": "2026-04-16T00:11:00+02:00", "lane": "memory_curation", "result": "complete"},
        ]
    )
    return int(summary["failure_count"])


@deal.post(lambda r: r == 1)
def _contract_operator_surface_unknown_focus_lane_falls_back_to_empty_crosshair() -> int:
    surface = build_phase_e_operator_surface(
        {
            "summary": {"blocked_lane_count": 1},
            "governance": {"state": "allow"},
            "approval": {"pending_count": 0},
            "explainability": {"count": 0},
            "lanes": {
                "improvement": {"lane": "improvement", "blocked": True},
                "memory_curation": {"lane": "memory_curation", "blocked": False},
            },
        },
        focus_lane="system",
    )
    return 1 if surface["focus_lane"] == "" and surface["focused_lane"] == {} else 0

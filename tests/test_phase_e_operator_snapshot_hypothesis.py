from __future__ import annotations

from hypothesis import given, strategies as st

from orchestration.phase_e_operator_snapshot import (
    summarize_phase_e_governance_lanes,
    summarize_phase_e_operator_lanes,
    summarize_phase_e_pending_approvals,
)


@given(
    improvement_blocked=st.booleans(),
    memory_blocked=st.booleans(),
    improvement_time=st.one_of(st.just(""), st.datetimes().map(lambda dt: dt.isoformat())),
    memory_time=st.one_of(st.just(""), st.datetimes().map(lambda dt: dt.isoformat())),
)
def test_hypothesis_summarize_phase_e_operator_lanes_counts_blocked_lanes_correctly(
    improvement_blocked: bool,
    memory_blocked: bool,
    improvement_time: str,
    memory_time: str,
) -> None:
    summary = summarize_phase_e_operator_lanes(
        {
            "improvement": {
                "blocked": improvement_blocked,
                "last_action": {"observed_at": improvement_time},
            },
            "memory_curation": {
                "blocked": memory_blocked,
                "last_action": {"observed_at": memory_time},
            },
        }
    )

    assert summary["blocked_lane_count"] == len(summary["blocked_lanes"])
    assert set(summary["blocked_lanes"]).issubset({"improvement", "memory_curation"})


@given(
    improvement_blocked=st.booleans(),
    memory_blocked=st.booleans(),
    system_blocked=st.booleans(),
)
def test_hypothesis_summarize_phase_e_governance_lanes_counts_blocked_lanes_correctly(
    improvement_blocked: bool,
    memory_blocked: bool,
    system_blocked: bool,
) -> None:
    summary = summarize_phase_e_governance_lanes(
        {
            "improvement": {
                "blocked": improvement_blocked,
                "state": "strict_force_off" if improvement_blocked else "allow",
                "action": "freeze" if improvement_blocked else "allow",
                "risk_class": "critical" if improvement_blocked else "none",
                "reasons": ["policy_runtime:strict_force_off"] if improvement_blocked else [],
                "active_states": ["strict_force_off"] if improvement_blocked else [],
            },
            "memory_curation": {
                "blocked": memory_blocked,
                "state": "cooldown_active" if memory_blocked else "allow",
                "action": "hold" if memory_blocked else "allow",
                "risk_class": "medium" if memory_blocked else "none",
                "reasons": ["recent_memory_curation_run"] if memory_blocked else [],
                "active_states": ["cooldown_active"] if memory_blocked else [],
            },
            "system": {
                "blocked": system_blocked,
                "state": "warn" if system_blocked else "healthy",
                "action": "hold" if system_blocked else "allow",
                "risk_class": "medium" if system_blocked else "none",
                "reasons": ["mcp_runtime:startup_grace"] if system_blocked else [],
                "active_states": ["degraded_mode"] if system_blocked else [],
            },
        }
    )

    assert summary["blocked_lane_count"] == len(summary["blocked_lanes"])
    assert set(summary["blocked_lanes"]).issubset({"improvement", "memory_curation", "system"})


@given(
    items=st.lists(
        st.fixed_dictionaries(
            {
                "lane": st.sampled_from(["improvement", "memory_curation", "system"]),
                "risk_class": st.sampled_from(["none", "low", "medium", "high", "critical"]),
                "requested_action": st.sampled_from(["hold", "promote_canary", "rollback"]),
                "pending_minutes": st.floats(min_value=0.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
            }
        ),
        max_size=8,
    )
)
def test_hypothesis_summarize_phase_e_pending_approvals_counts_items_correctly(items: list[dict[str, object]]) -> None:
    summary = summarize_phase_e_pending_approvals(items)

    assert summary["pending_count"] == len(items)
    assert set(summary["lanes"]).issubset({"improvement", "memory_curation", "system"})
    assert set(summary["requested_actions"]).issubset({"hold", "promote_canary", "rollback"})

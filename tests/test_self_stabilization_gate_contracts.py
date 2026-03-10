from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.self_stabilization_gate import evaluate_self_stabilization_gate


@deal.post(lambda r: r["state"] in {"pass", "warn", "blocked"})
@deal.post(lambda r: int(r["circuit_breakers_open"]) >= 0)
def _contract_self_stabilization_gate(summary: dict) -> dict:
    safe_summary = summary if isinstance(summary, dict) else {}
    incidents = safe_summary.get("incidents")
    if not isinstance(incidents, list):
        incidents = []
    incidents = [item for item in incidents if isinstance(item, dict)]
    open_breakers = safe_summary.get("open_breakers")
    if not isinstance(open_breakers, list):
        open_breakers = []
    return evaluate_self_stabilization_gate(
        {
            "open_incidents": int(safe_summary.get("open_incidents", 0) or 0),
            "degrade_mode": str(safe_summary.get("degrade_mode", "unknown") or "unknown"),
            "circuit_breakers_open": int(safe_summary.get("circuit_breakers_open", 0) or 0),
            "resource_guard_state": str(safe_summary.get("resource_guard_state", "inactive") or "inactive"),
            "open_breakers": open_breakers,
            "incidents": incidents,
        }
    )


@given(
    open_incidents=st.integers(min_value=0, max_value=5),
    circuit_breakers_open=st.integers(min_value=0, max_value=3),
    degrade_mode=st.sampled_from(["normal", "cautious", "degraded", "restricted", "emergency"]),
    blocked_phase=st.booleans(),
    quarantine=st.booleans(),
    cooldown=st.booleans(),
    known_bad=st.booleans(),
)
@settings(max_examples=60)
def test_hypothesis_self_stabilization_gate_returns_known_state(
    open_incidents: int,
    circuit_breakers_open: int,
    degrade_mode: str,
    blocked_phase: bool,
    quarantine: bool,
    cooldown: bool,
    known_bad: bool,
) -> None:
    decision = _contract_self_stabilization_gate(
        {
            "open_incidents": open_incidents,
            "degrade_mode": degrade_mode,
            "circuit_breakers_open": circuit_breakers_open,
            "incidents": [
                {
                    "recovery_phase": "blocked" if blocked_phase else "recovering",
                    "quarantine_state": "active" if quarantine else "none",
                    "notification_state": "cooldown_active" if cooldown else "none",
                    "memory_state": "known_bad_pattern" if known_bad else "new",
                }
            ],
        }
    )
    assert decision["state"] in {"pass", "warn", "blocked"}
    assert int(decision["circuit_breakers_open"]) >= 0

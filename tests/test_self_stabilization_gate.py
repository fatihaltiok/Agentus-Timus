from __future__ import annotations

from orchestration.self_stabilization_gate import evaluate_self_stabilization_gate


def test_self_stabilization_gate_warns_on_known_bad_pattern_and_quarantine() -> None:
    decision = evaluate_self_stabilization_gate(
        {
            "open_incidents": 1,
            "degrade_mode": "degraded",
            "circuit_breakers_open": 0,
            "resource_guard_state": "active",
            "incidents": [
                {
                    "recovery_phase": "recovering",
                    "quarantine_state": "active",
                    "notification_state": "cooldown_active",
                    "memory_state": "known_bad_pattern",
                }
            ],
        }
    )

    assert decision["state"] == "warn"
    assert decision["autonomy_hold"] is True
    assert decision["quarantined_incidents"] == 1
    assert decision["cooldown_incidents"] == 1
    assert decision["known_bad_patterns"] == 1


def test_self_stabilization_gate_blocks_on_open_breaker() -> None:
    decision = evaluate_self_stabilization_gate(
        {
            "open_incidents": 1,
            "degrade_mode": "normal",
            "circuit_breakers_open": 1,
            "open_breakers": [{"component": "mcp", "signal": "mcp_health"}],
            "incidents": [
                {
                    "recovery_phase": "recovering",
                    "quarantine_state": "none",
                    "notification_state": "none",
                    "memory_state": "new",
                }
            ],
        }
    )

    assert decision["state"] == "blocked"
    assert decision["release_blocked"] is True
    assert decision["circuit_breakers_open"] == 1

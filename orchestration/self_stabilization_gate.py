"""Self-stabilization gate derived from live self-healing runtime state."""

from __future__ import annotations

from typing import Any, Dict, List


def evaluate_self_stabilization_gate(self_healing: Dict[str, Any]) -> Dict[str, Any]:
    incidents = list((self_healing or {}).get("incidents", []) or [])
    degrade_mode = str((self_healing or {}).get("degrade_mode", "unknown") or "unknown").strip().lower()
    open_incidents = int((self_healing or {}).get("open_incidents", 0) or 0)
    resource_guard_state = str((self_healing or {}).get("resource_guard_state", "inactive") or "inactive").strip().lower()
    circuit_breakers_open = int((self_healing or {}).get("circuit_breakers_open", 0) or 0)
    open_breakers = list((self_healing or {}).get("open_breakers", []) or [])

    has_blocked_incident = any(str(item.get("recovery_phase", "") or "").strip().lower() == "blocked" for item in incidents)
    has_quarantine = any(str(item.get("quarantine_state", "") or "").strip().lower() == "active" for item in incidents)
    has_cooldown = any(str(item.get("notification_state", "") or "").strip().lower() == "cooldown_active" for item in incidents)
    has_known_bad_pattern = any(str(item.get("memory_state", "") or "").strip().lower() == "known_bad_pattern" for item in incidents)

    if (
        degrade_mode in {"restricted", "emergency"}
        or circuit_breakers_open > 0
        or has_blocked_incident
    ):
        return {
            "state": "blocked",
            "reason": "self_healing_gate_blocked",
            "release_blocked": True,
            "autonomy_hold": True,
            "open_incidents": open_incidents,
            "degrade_mode": degrade_mode,
            "circuit_breakers_open": circuit_breakers_open,
            "open_breakers": open_breakers[:4],
            "quarantined_incidents": sum(
                1 for item in incidents if str(item.get("quarantine_state", "") or "").strip().lower() == "active"
            ),
            "cooldown_incidents": sum(
                1 for item in incidents if str(item.get("notification_state", "") or "").strip().lower() == "cooldown_active"
            ),
            "known_bad_patterns": sum(
                1 for item in incidents if str(item.get("memory_state", "") or "").strip().lower() == "known_bad_pattern"
            ),
        }

    if (
        degrade_mode in {"degraded", "cautious"}
        or open_incidents > 0
        or resource_guard_state not in {"", "inactive", "none"}
        or has_quarantine
        or has_cooldown
        or has_known_bad_pattern
    ):
        return {
            "state": "warn",
            "reason": "self_healing_gate_warn",
            "release_blocked": False,
            "autonomy_hold": True,
            "open_incidents": open_incidents,
            "degrade_mode": degrade_mode,
            "circuit_breakers_open": circuit_breakers_open,
            "open_breakers": open_breakers[:4],
            "quarantined_incidents": sum(
                1 for item in incidents if str(item.get("quarantine_state", "") or "").strip().lower() == "active"
            ),
            "cooldown_incidents": sum(
                1 for item in incidents if str(item.get("notification_state", "") or "").strip().lower() == "cooldown_active"
            ),
            "known_bad_patterns": sum(
                1 for item in incidents if str(item.get("memory_state", "") or "").strip().lower() == "known_bad_pattern"
            ),
        }

    return {
        "state": "pass",
        "reason": "self_healing_gate_green",
        "release_blocked": False,
        "autonomy_hold": False,
        "open_incidents": 0,
        "degrade_mode": degrade_mode,
        "circuit_breakers_open": 0,
        "open_breakers": [],
        "quarantined_incidents": 0,
        "cooldown_incidents": 0,
        "known_bad_patterns": 0,
    }


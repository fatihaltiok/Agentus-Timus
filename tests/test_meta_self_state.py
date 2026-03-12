from __future__ import annotations

from orchestration.meta_self_state import build_meta_self_state


_RUNTIME_WARN = {
    "budget_state": "soft_limit",
    "stability_gate_state": "warn",
    "degrade_mode": "degraded",
    "open_incidents": 2,
    "circuit_breakers_open": 1,
    "resource_guard_state": "active",
    "resource_guard_reason": "queue_backlog",
    "quarantined_incidents": 1,
    "cooldown_incidents": 1,
    "known_bad_patterns": 1,
    "release_blocked": False,
    "autonomy_hold": True,
}


def test_build_meta_self_state_for_youtube_multistage_task():
    classification = {
        "task_type": "youtube_content_extraction",
        "site_kind": "youtube",
        "required_capabilities": ["browser_navigation", "content_extraction", "pdf_creation"],
        "recommended_entry_agent": "meta",
        "recommended_agent_chain": ["meta", "visual", "research", "document"],
        "needs_structured_handoff": True,
    }
    learning_snapshot = {
        "posture": "conservative",
        "recipe_score": 0.82,
        "chain_score": 0.91,
        "task_type_score": 0.95,
    }

    state = build_meta_self_state(classification, learning_snapshot, _RUNTIME_WARN)

    assert state["identity"] == "Timus"
    assert state["orchestration_role"] == "workflow_orchestrator"
    assert state["strategy_posture"] == "conservative"
    assert state["preferred_entry_agent"] == "meta"
    assert state["available_specialists"] == ["visual", "research", "document"]
    assert "browser_navigation" in state["required_capabilities"]
    assert any(tool["tool"] == "browser_workflow_plan" for tool in state["active_tools"])
    assert "bounded_replanning_only" in state["known_limits"]
    assert "conservative_learning_guard_enabled" in state["known_limits"]
    assert "budget_guard_soft_limit" in state["known_limits"]
    assert "stability_gate_warn" in state["known_limits"]
    assert state["runtime_constraints"]["budget_state"] == "soft_limit"
    assert state["runtime_constraints"]["stability_gate_state"] == "warn"
    assert state["runtime_constraints"]["open_incidents"] == 2
    assert any(risk["signal"] == "negative_outcome_history" for risk in state["active_risks"])
    assert any(risk["signal"] == "budget_pressure" for risk in state["active_risks"])
    assert any(tool["tool"] == "browser_workflow_plan" and tool["state"] == "degraded" for tool in state["active_tools"])
    assert state["structured_handoff_required"] is True


def test_build_meta_self_state_for_simple_lane_stays_small():
    classification = {
        "task_type": "single_lane",
        "site_kind": "",
        "required_capabilities": [],
        "recommended_entry_agent": "research",
        "recommended_agent_chain": ["research"],
        "needs_structured_handoff": False,
    }

    state = build_meta_self_state(
        classification,
        {"posture": "neutral"},
        {
            "budget_state": "pass",
            "stability_gate_state": "pass",
            "degrade_mode": "normal",
            "open_incidents": 0,
            "circuit_breakers_open": 0,
            "resource_guard_state": "inactive",
            "resource_guard_reason": "",
            "quarantined_incidents": 0,
            "cooldown_incidents": 0,
            "known_bad_patterns": 0,
            "release_blocked": False,
            "autonomy_hold": False,
        },
    )

    assert state["strategy_posture"] == "neutral"
    assert state["preferred_entry_agent"] == "research"
    assert state["available_specialists"] == ["research"]
    assert state["structured_handoff_required"] is False
    assert state["runtime_constraints"]["stability_gate_state"] == "pass"
    assert any(tool["tool"] == "delegate_to_agent" for tool in state["active_tools"])

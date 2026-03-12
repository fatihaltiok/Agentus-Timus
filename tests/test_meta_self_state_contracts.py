from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.meta_self_state import build_meta_self_state


@deal.pre(lambda chain, _capabilities, _posture, _handoff: len(chain) >= 1)
@deal.post(lambda r: r["identity"] == "Timus")
@deal.post(lambda r: isinstance(r["available_specialists"], list))
@deal.post(lambda r: isinstance(r["active_tools"], list) and len(r["active_tools"]) >= 1)
@deal.post(lambda r: isinstance(r["known_limits"], list) and "bounded_replanning_only" in r["known_limits"])
def _contract_build_meta_self_state(
    chain: list[str],
    capabilities: list[str],
    posture: str,
    structured_handoff: bool,
) -> dict:
    classification = {
        "task_type": "youtube_content_extraction" if "visual" in chain else "single_lane",
        "site_kind": "youtube" if "visual" in chain else "",
        "required_capabilities": capabilities,
        "recommended_entry_agent": chain[0],
        "recommended_agent_chain": chain,
        "needs_structured_handoff": structured_handoff,
    }
    return build_meta_self_state(
        classification,
        {"posture": posture},
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


@given(
    st.lists(
        st.sampled_from(["meta", "visual", "research", "document", "system", "shell"]),
        min_size=1,
        max_size=5,
    ),
    st.lists(
        st.sampled_from(["browser_navigation", "content_extraction", "pdf_creation", "diagnostics"]),
        max_size=4,
    ),
    st.sampled_from(["neutral", "conservative", "preferred"]),
    st.booleans(),
)
@settings(max_examples=50)
def test_hypothesis_meta_self_state_shape(
    chain: list[str],
    capabilities: list[str],
    posture: str,
    structured_handoff: bool,
):
    result = _contract_build_meta_self_state(chain, capabilities, posture, structured_handoff)

    assert result["strategy_posture"] == posture
    assert isinstance(result["runtime_constraints"], dict)
    assert all(isinstance(item, str) for item in result["available_specialists"])
    assert all({"tool", "state", "reason"} <= set(tool.keys()) for tool in result["active_tools"])
    assert all({"signal", "severity", "reason"} <= set(risk.keys()) for risk in result["active_risks"])

from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.adaptive_planner import build_adaptive_plan
from orchestration.capability_graph import build_capability_graph
from orchestration.goal_spec import derive_goal_spec
from orchestration.meta_orchestration import classify_meta_task, get_agent_capability_map


@deal.pre(lambda query: len(query) <= 120)
@deal.post(
    lambda r: set(r.keys())
    >= {
        "planner_mode",
        "advisory_only",
        "goal_signature",
        "current_chain",
        "recommended_chain",
        "confidence",
        "goal_gaps",
        "candidate_chains",
    }
)
@deal.post(lambda r: r["planner_mode"] == "advisory")
@deal.post(lambda r: isinstance(r["recommended_chain"], list) and len(r["recommended_chain"]) >= 1)
@deal.post(lambda r: 0.0 <= float(r["confidence"]) <= 0.99)
def _contract_build_adaptive_plan(query: str) -> dict:
    classification = classify_meta_task(query, action_count=0)
    goal_spec = derive_goal_spec(query, classification)
    capability_graph = build_capability_graph(
        goal_spec,
        get_agent_capability_map(),
        current_chain=classification["recommended_agent_chain"],
        required_capabilities=classification["required_capabilities"],
    )
    return build_adaptive_plan(goal_spec, capability_graph, classification)


@given(st.text(alphabet=st.characters(max_codepoint=127), max_size=120))
@settings(max_examples=80)
def test_hypothesis_adaptive_plan_shape(query: str):
    result = _contract_build_adaptive_plan(query)
    assert isinstance(result["goal_gaps"], list)
    assert all(isinstance(item, dict) for item in result["candidate_chains"])
    assert result["current_chain"][0] == "meta"

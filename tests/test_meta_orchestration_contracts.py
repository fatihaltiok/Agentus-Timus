from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.meta_orchestration import build_meta_feedback_targets, classify_meta_task


@deal.post(
    lambda r: set(r.keys())
    >= {
        "task_type",
        "site_kind",
        "required_capabilities",
        "recommended_entry_agent",
        "recommended_agent_chain",
        "needs_structured_handoff",
        "reason",
        "recommended_recipe_id",
        "recipe_stages",
        "goal_spec",
        "capability_graph",
        "adaptive_plan",
    }
)
@deal.post(lambda r: isinstance(r["recommended_agent_chain"], list) and len(r["recommended_agent_chain"]) >= 1)
@deal.post(lambda r: r["recommended_entry_agent"] == r["recommended_agent_chain"][0])
@deal.post(lambda r: isinstance(r["recipe_stages"], list))
@deal.post(lambda r: isinstance(r["goal_spec"], dict) and bool(r["goal_spec"].get("goal_signature")))
@deal.post(lambda r: isinstance(r["adaptive_plan"], dict) and r["adaptive_plan"].get("planner_mode") == "advisory")
def _contract_classify_meta_task(query: str, action_count: int) -> dict:
    return classify_meta_task(query, action_count=max(0, action_count))


@given(st.text(max_size=120), st.integers(min_value=0, max_value=12))
@settings(max_examples=80)
def test_hypothesis_meta_orchestration_shape(query: str, action_count: int):
    result = _contract_classify_meta_task(query, action_count)
    assert isinstance(result["needs_structured_handoff"], bool)
    assert isinstance(result["required_capabilities"], list)
    assert all(isinstance(stage, dict) for stage in result["recipe_stages"])
    assert isinstance(result["capability_graph"].get("matching_nodes"), list)
    assert isinstance(result.get("semantic_ambiguity_hints"), list)
    assert isinstance(result.get("semantic_review_recommended"), bool)


@deal.post(lambda r: isinstance(r, list))
@deal.post(
    lambda r: all(
        isinstance(item, dict)
        and set(item.keys()) == {"namespace", "key"}
        and isinstance(item["namespace"], str)
        and isinstance(item["key"], str)
        for item in r
    )
)
def _contract_build_meta_feedback_targets(query: str, action_count: int) -> list[dict]:
    return build_meta_feedback_targets(classify_meta_task(query, action_count=max(0, action_count)))


@given(st.text(max_size=120), st.integers(min_value=0, max_value=12))
@settings(max_examples=80)
def test_hypothesis_meta_feedback_targets_shape(query: str, action_count: int):
    result = _contract_build_meta_feedback_targets(query, action_count)
    assert len({(item["namespace"], item["key"]) for item in result}) == len(result)

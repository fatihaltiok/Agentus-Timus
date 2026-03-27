from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.meta_orchestration import (
    resolve_adaptive_plan_adoption,
    resolve_orchestration_recipe,
)


def _classification(confidence: float) -> dict:
    current = resolve_orchestration_recipe("simple_live_lookup")
    alternative = resolve_orchestration_recipe("simple_live_lookup_document")
    return {
        "task_type": "simple_live_lookup",
        "site_kind": "web",
        "recommended_recipe_id": current["recipe_id"],
        "recommended_agent_chain": current["recommended_agent_chain"],
        "alternative_recipes": [alternative],
        "adaptive_plan": {
            "planner_mode": "advisory",
            "confidence": confidence,
            "recommended_chain": ["meta", "executor", "document"],
            "recommended_recipe_hint": "simple_live_lookup_document",
        },
    }


@deal.post(
    lambda r: set(r.keys())
    >= {"state", "reason", "confidence", "adopted_recipe_id", "adopted_chain"}
)
@deal.post(lambda r: r["state"] in {"adopted", "fallback_current", "rejected"})
@deal.post(lambda r: isinstance(r["adopted_chain"], list))
def _contract_resolve_adaptive_plan_adoption(confidence: float) -> dict:
    return resolve_adaptive_plan_adoption(_classification(confidence))


@given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=80)
def test_hypothesis_adaptive_plan_adoption_shape(confidence: float):
    result = _contract_resolve_adaptive_plan_adoption(confidence)
    assert 0.0 <= float(result["confidence"]) <= 1.0

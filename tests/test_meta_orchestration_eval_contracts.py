from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.meta_orchestration_eval import evaluate_meta_orchestration_case


@deal.post(lambda r: 0.0 <= float(r.get("score", 0.0)) <= 1.0)
@deal.post(
    lambda r: 0.0 <= float((r.get("benchmark", {}) or {}).get("capability_score", 0.0)) <= 1.0
)
@deal.post(lambda r: isinstance((r.get("decision", {}) or {}).get("recommended_agent_chain", []), list))
def _contract_evaluate_meta_orchestration_case(case: dict) -> dict:
    raw_chain = (case or {}).get("expected_agent_chain", [])
    safe_chain = raw_chain if isinstance(raw_chain, list) else []
    raw_capabilities = (case or {}).get("expected_capabilities", [])
    safe_capabilities = raw_capabilities if isinstance(raw_capabilities, list) else []
    normalized = {
        "name": str((case or {}).get("name", "") or ""),
        "query": str((case or {}).get("query", "") or ""),
        "expected_route_to_meta": bool((case or {}).get("expected_route_to_meta", False)),
        "expected_task_type": str((case or {}).get("expected_task_type", "") or ""),
        "expected_entry_agent": str((case or {}).get("expected_entry_agent", "") or ""),
        "expected_agent_chain": [str(item) for item in safe_chain],
        "expected_recipe_id": None
        if (case or {}).get("expected_recipe_id") is None
        else str((case or {}).get("expected_recipe_id", "") or ""),
        "expected_structured_handoff": bool((case or {}).get("expected_structured_handoff", False)),
        "expected_capabilities": [str(item) for item in safe_capabilities],
    }
    return evaluate_meta_orchestration_case(normalized)


@given(
    st.fixed_dictionaries(
        {
            "name": st.text(max_size=40),
            "query": st.text(max_size=120),
            "expected_route_to_meta": st.booleans(),
            "expected_task_type": st.text(max_size=40),
            "expected_entry_agent": st.text(max_size=20),
            "expected_agent_chain": st.lists(st.text(min_size=1, max_size=20), max_size=5),
            "expected_recipe_id": st.one_of(st.none(), st.text(max_size=40)),
            "expected_structured_handoff": st.booleans(),
            "expected_capabilities": st.lists(st.text(min_size=1, max_size=40), max_size=5),
        }
    )
)
@settings(max_examples=60)
def test_hypothesis_meta_orchestration_eval_score_range(case: dict):
    result = _contract_evaluate_meta_orchestration_case(case)
    assert 0.0 <= result["score"] <= 1.0
    assert 0.0 <= result["benchmark"]["capability_score"] <= 1.0

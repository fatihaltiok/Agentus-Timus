"""Contracts for canonical browser workflow evaluations."""

from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.browser_workflow_eval import evaluate_browser_workflow_case


@deal.post(lambda r: 0.0 <= r["score"] <= 1.0)
@deal.post(lambda r: isinstance(r["passed"], bool))
@deal.post(lambda r: 0.0 <= float((r.get("benchmark", {}) or {}).get("state_score", 0.0)) <= 1.0)
@deal.post(lambda r: 0.0 <= float((r.get("benchmark", {}) or {}).get("evidence_score", 0.0)) <= 1.0)
@deal.post(lambda r: 0.0 <= float((r.get("benchmark", {}) or {}).get("verification_score", 0.0)) <= 1.0)
@deal.post(lambda r: 0.0 <= float((r.get("benchmark", {}) or {}).get("recovery_score", 0.0)) <= 1.0)
def _contract_evaluate_browser_workflow_case(case: dict) -> dict:
    return evaluate_browser_workflow_case(case)


@given(
    st.fixed_dictionaries(
        {
            "name": st.text(max_size=40),
            "query": st.text(max_size=120),
            "task": st.text(max_size=120),
            "url": st.text(max_size=80),
            "expected_route_to_meta": st.booleans(),
            "required_markers": st.lists(st.text(max_size=40), max_size=6),
        }
    )
)
@settings(max_examples=60)
def test_hypothesis_browser_workflow_eval_score_range(case: dict):
    result = _contract_evaluate_browser_workflow_case(case)
    assert 0.0 <= result["score"] <= 1.0
    assert 0.0 <= result["benchmark"]["state_score"] <= 1.0
    assert 0.0 <= result["benchmark"]["evidence_score"] <= 1.0
    assert 0.0 <= result["benchmark"]["verification_score"] <= 1.0
    assert 0.0 <= result["benchmark"]["recovery_score"] <= 1.0

"""Contracts for orchestration policy helpers."""

from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.orchestration_policy import evaluate_query_orchestration


@deal.post(
    lambda r: set(r.keys())
    >= {"route_to_meta", "capabilities", "capability_count", "action_count", "reason"}
)
@deal.post(
    lambda r: r["reason"]
    in {"multi_capability", "workflow_connectors", "deliverable_chain", "login_workflow", "multi_action", "single_lane"}
)
def _contract_evaluate_query_orchestration(query: str) -> dict:
    return evaluate_query_orchestration(query)


@given(st.text(max_size=120))
@settings(max_examples=80)
def test_hypothesis_orchestration_policy_shape(query: str):
    result = _contract_evaluate_query_orchestration(query)
    assert isinstance(result["route_to_meta"], bool)
    assert result["capability_count"] >= 0
    assert result["action_count"] >= 0

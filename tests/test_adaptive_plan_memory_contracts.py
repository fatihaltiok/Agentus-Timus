from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.adaptive_plan_memory import learned_chain_bias, learned_chain_confidence


@deal.post(lambda r: 0.0 <= r <= 1.0)
def _contract_learned_chain_confidence(evidence_count: int) -> float:
    return learned_chain_confidence(evidence_count)


@deal.post(lambda r: -0.22 <= r <= 0.22)
def _contract_learned_chain_bias(
    success_count: int,
    failure_count: int,
    runtime_gap_count: int,
    evidence_count: int,
) -> float:
    return learned_chain_bias(success_count, failure_count, runtime_gap_count, evidence_count)


@given(st.integers(min_value=-20, max_value=50))
@settings(max_examples=80)
def test_hypothesis_learned_chain_confidence_stays_bounded(evidence_count: int):
    result = _contract_learned_chain_confidence(evidence_count)
    assert 0.0 <= result <= 1.0


@given(
    st.integers(min_value=-20, max_value=50),
    st.integers(min_value=-20, max_value=50),
    st.integers(min_value=-20, max_value=50),
    st.integers(min_value=-20, max_value=50),
)
@settings(max_examples=120)
def test_hypothesis_learned_chain_bias_stays_bounded(
    success_count: int,
    failure_count: int,
    runtime_gap_count: int,
    evidence_count: int,
):
    result = _contract_learned_chain_bias(success_count, failure_count, runtime_gap_count, evidence_count)
    assert -0.22 <= result <= 0.22

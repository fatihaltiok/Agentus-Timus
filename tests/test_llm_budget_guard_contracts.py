"""CrossHair + Hypothesis contracts for LLM budget thresholds."""

import math
from unittest.mock import patch

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.llm_budget_guard import (
    BudgetThresholds,
    _normalize_thresholds,
    _state_for_cost,
    cap_parallelism_for_budget,
)


@deal.pre(lambda warn, soft, hard: all(math.isfinite(v) for v in (warn, soft, hard)))
@deal.post(lambda r: 0.0 <= r.warn_usd <= r.soft_limit_usd <= r.hard_limit_usd)
def _contract_normalize_thresholds(warn: float, soft: float, hard: float) -> BudgetThresholds:
    return _normalize_thresholds(BudgetThresholds(warn_usd=warn, soft_limit_usd=soft, hard_limit_usd=hard))


@deal.pre(lambda current, warn, soft, hard: min(current, warn, soft, hard) >= 0.0 and all(math.isfinite(v) for v in (current, warn, soft, hard)))
@deal.post(lambda r: r in {"ok", "warn", "soft_limit", "hard_limit"})
def _contract_state_for_cost(current: float, warn: float, soft: float, hard: float) -> str:
    return _state_for_cost(current, BudgetThresholds(warn_usd=warn, soft_limit_usd=soft, hard_limit_usd=hard))


@given(
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=80)
def test_hypothesis_thresholds_are_monotone(warn: float, soft: float, hard: float):
    result = _contract_normalize_thresholds(warn, soft, hard)
    assert 0.0 <= result.warn_usd <= result.soft_limit_usd <= result.hard_limit_usd


@given(
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=80)
def test_hypothesis_budget_state_is_valid(current: float, warn: float, soft: float, hard: float):
    state = _contract_state_for_cost(current, warn, soft, hard)
    assert state in {"ok", "warn", "soft_limit", "hard_limit"}


@given(st.integers(min_value=1, max_value=10))
@settings(max_examples=40)
def test_hypothesis_parallel_cap_never_exceeds_request(requested_parallel: int):
    from orchestration.llm_budget_guard import LLMBudgetDecision

    with patch(
        "orchestration.llm_budget_guard.evaluate_llm_budget",
        return_value=LLMBudgetDecision(
            blocked=False,
            warning=False,
            soft_limited=False,
            max_tokens_cap=requested_parallel,
            state="ok",
            scopes=[],
            message="",
        ),
    ):
        capped, _ = cap_parallelism_for_budget(
            requested_parallel=requested_parallel,
            agent="meta",
            session_id="",
        )
    assert 1 <= capped <= requested_parallel

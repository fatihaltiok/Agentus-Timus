"""CrossHair + Hypothesis contracts for LLM usage accounting."""

import math

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from utils.llm_usage import compute_cost_usd_from_rates


@deal.pre(
    lambda i, o, c, ir, orate, cr: (
        min(i, o, c) >= 0
        and min(ir, orate, cr) >= 0.0
        and all(math.isfinite(v) for v in (ir, orate, cr))
    )
)
@deal.post(lambda r: r >= 0.0)
def _contract_compute_cost(
    i: int,
    o: int,
    c: int,
    ir: float,
    orate: float,
    cr: float,
) -> float:
    return compute_cost_usd_from_rates(
        input_tokens=i,
        output_tokens=o,
        cached_tokens=c,
        input_rate_usd_per_1m=ir,
        output_rate_usd_per_1m=orate,
        cached_rate_usd_per_1m=cr,
    )


@given(
    st.integers(min_value=0, max_value=2_000_000),
    st.integers(min_value=0, max_value=2_000_000),
    st.integers(min_value=0, max_value=2_000_000),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=80)
def test_hypothesis_cost_is_non_negative(
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    input_rate: float,
    output_rate: float,
    cached_rate: float,
):
    cost = _contract_compute_cost(
        input_tokens,
        output_tokens,
        cached_tokens,
        input_rate,
        output_rate,
        cached_rate,
    )
    assert cost >= 0.0


@given(
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=40)
def test_hypothesis_zero_tokens_have_zero_cost(
    input_rate: float,
    output_rate: float,
    cached_rate: float,
):
    cost = _contract_compute_cost(0, 0, 0, input_rate, output_rate, cached_rate)
    assert cost == 0.0

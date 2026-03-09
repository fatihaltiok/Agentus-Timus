"""Contracts for E2E release-gate decisions."""

from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.e2e_release_gate import evaluate_e2e_release_gate


@deal.pre(lambda total, passed, warned, failed, blocking_failed, current_canary_percent: min(total, passed, warned, failed, blocking_failed) >= 0)
@deal.post(lambda r: r["state"] in {"pass", "warn", "blocked"})
@deal.post(lambda r: 0 <= r["recommended_canary_percent"] <= 100)
def _contract_evaluate_e2e_release_gate(
    total: int,
    passed: int,
    warned: int,
    failed: int,
    blocking_failed: int,
    current_canary_percent: int,
) -> dict:
    matrix = {
        "summary": {
            "total": total,
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "blocking_failed": blocking_failed,
        },
        "flows": [],
    }
    return evaluate_e2e_release_gate(matrix, current_canary_percent=current_canary_percent)


@given(
    st.integers(min_value=0, max_value=20),
    st.integers(min_value=0, max_value=20),
    st.integers(min_value=0, max_value=20),
    st.integers(min_value=0, max_value=20),
    st.integers(min_value=0, max_value=20),
    st.integers(min_value=-100, max_value=200),
)
@settings(max_examples=60)
def test_hypothesis_e2e_release_gate_bounds(
    total: int,
    passed: int,
    warned: int,
    failed: int,
    blocking_failed: int,
    current_canary_percent: int,
):
    result = _contract_evaluate_e2e_release_gate(
        total,
        passed,
        warned,
        failed,
        blocking_failed,
        current_canary_percent,
    )
    assert result["state"] in {"pass", "warn", "blocked"}
    assert 0 <= result["recommended_canary_percent"] <= 100

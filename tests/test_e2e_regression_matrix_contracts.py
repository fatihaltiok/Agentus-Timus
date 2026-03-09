"""Contracts for the central E2E regression matrix."""

from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.e2e_regression_matrix import summarize_e2e_matrix


@deal.pre(lambda flows: all(flow.get("status") in {"pass", "warn", "fail"} for flow in flows))
@deal.post(lambda r: r["overall"] in {"pass", "warn", "fail"})
@deal.post(lambda r: min(r["total"], r["passed"], r["warned"], r["failed"], r["blocking_failed"]) >= 0)
@deal.post(lambda r: r["passed"] + r["warned"] + r["failed"] == r["total"])
@deal.post(lambda r: r["blocking_failed"] <= r["failed"])
def _contract_summarize_e2e_matrix(flows: list[dict]) -> dict:
    return summarize_e2e_matrix(flows)


@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "status": st.sampled_from(["pass", "warn", "fail"]),
                "blocking": st.booleans(),
            }
        ),
        max_size=12,
    )
)
@settings(max_examples=60)
def test_hypothesis_e2e_matrix_summary_shape(flows: list[dict]):
    summary = _contract_summarize_e2e_matrix(flows)
    assert summary["total"] == len(flows)
    assert summary["passed"] + summary["warned"] + summary["failed"] == summary["total"]

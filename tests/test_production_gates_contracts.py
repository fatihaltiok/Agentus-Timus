"""CrossHair + Hypothesis contracts for Timus production-gate aggregation."""

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.production_gates import GateResult, normalize_gate_status, summarize_gate_results


@deal.post(lambda r: r in {"passed", "failed", "skipped"})
def _contract_normalize_gate_status(status: str) -> str:
    return normalize_gate_status(status)


@deal.pre(lambda statuses, blocking: len(statuses) == len(blocking))
@deal.post(lambda r: r["passed"] + r["failed"] + r["skipped"] == r["total"])
@deal.post(lambda r: 0 <= r["blocking_failed"] <= r["failed"] <= r["total"])
def _contract_summarize(statuses: list[str], blocking: list[bool]) -> dict:
    results = [
        GateResult(name=f"g{i}", status=status, blocking=is_blocking)
        for i, (status, is_blocking) in enumerate(zip(statuses, blocking))
    ]
    return summarize_gate_results(results)


@given(st.text())
@settings(max_examples=80)
def test_hypothesis_normalize_gate_status_is_always_valid(status: str):
    assert _contract_normalize_gate_status(status) in {"passed", "failed", "skipped"}


@given(
    st.lists(st.sampled_from(["passed", "failed", "skipped", "weird"]), min_size=0, max_size=12),
    st.lists(st.booleans(), min_size=0, max_size=12),
)
@settings(max_examples=80)
def test_hypothesis_gate_summary_invariants(statuses: list[str], blocking: list[bool]):
    if len(statuses) != len(blocking):
        return
    summary = _contract_summarize(statuses, blocking)
    assert summary["passed"] + summary["failed"] + summary["skipped"] == summary["total"]
    assert 0 <= summary["blocking_failed"] <= summary["failed"] <= summary["total"]

"""CrossHair + Hypothesis contracts for parallel delegation aggregation."""

import deal
from hypothesis import given, strategies as st


@deal.pre(lambda success, partial, errors: success >= 0 and partial >= 0 and errors >= 0)
@deal.post(lambda r: r["total_tasks"] == r["success"] + r["partial"] + r["errors"])
def aggregate_counts(success: int, partial: int, errors: int) -> dict:
    return {
        "success": success,
        "partial": partial,
        "errors": errors,
        "total_tasks": success + partial + errors,
    }


@deal.pre(lambda status: status in {"success", "partial", "error"})
@deal.post(lambda r: r in {80, 40, 0})
def quality_for_status(status: str) -> int:
    if status == "success":
        return 80
    if status == "partial":
        return 40
    return 0


def test_aggregate_counts_matches_sum():
    result = aggregate_counts(2, 1, 3)
    assert result["total_tasks"] == 6


def test_quality_map_matches_expected_values():
    assert quality_for_status("success") == 80
    assert quality_for_status("partial") == 40
    assert quality_for_status("error") == 0


@given(
    success=st.integers(min_value=0, max_value=20),
    partial=st.integers(min_value=0, max_value=20),
    errors=st.integers(min_value=0, max_value=20),
)
def test_hypothesis_parallel_count_invariant(success: int, partial: int, errors: int):
    result = aggregate_counts(success, partial, errors)
    assert result["total_tasks"] == success + partial + errors


@given(status=st.sampled_from(["success", "partial", "error"]))
def test_hypothesis_quality_map(status: str):
    value = quality_for_status(status)
    if status == "success":
        assert value == 80
    elif status == "partial":
        assert value == 40
    else:
        assert value == 0

from __future__ import annotations

import pytest

from orchestration.general_decision_kernel_eval import (
    GDK5_UNSEEN_EVAL_CASES,
    evaluate_gdk5_kernel_case,
    summarize_gdk5_results,
)


@pytest.mark.parametrize(
    "case",
    GDK5_UNSEEN_EVAL_CASES,
    ids=[str(case["name"]) for case in GDK5_UNSEEN_EVAL_CASES],
)
def test_gdk5_unseen_kernel_matrix(case: dict) -> None:
    result = evaluate_gdk5_kernel_case(case)

    assert result["passed"], result


def test_gdk5_kernel_matrix_summary_is_complete() -> None:
    results = [evaluate_gdk5_kernel_case(case) for case in GDK5_UNSEEN_EVAL_CASES]
    summary = summarize_gdk5_results(results)

    assert summary["total"] >= 10
    assert summary["failed"] == 0
    assert summary["score"] == 1.0

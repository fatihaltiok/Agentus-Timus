from __future__ import annotations

import pytest

from orchestration.general_decision_kernel_eval import (
    GDK5_UNSEEN_EVAL_CASES,
    evaluate_gdk5_meta_case,
    summarize_gdk5_results,
)


@pytest.mark.parametrize(
    "case",
    GDK5_UNSEEN_EVAL_CASES,
    ids=[str(case["name"]) for case in GDK5_UNSEEN_EVAL_CASES],
)
def test_gdk5_unseen_meta_orchestration_matrix(case: dict) -> None:
    result = evaluate_gdk5_meta_case(case)

    assert result["passed"], result


def test_gdk5_meta_matrix_never_delegates_when_kernel_forbids_execution() -> None:
    for case in GDK5_UNSEEN_EVAL_CASES:
        result = evaluate_gdk5_meta_case(case)
        actual = result["actual"]
        if actual["execution_permission"] != "forbidden":
            continue
        assert actual["recommended_agent_chain"] == ["meta"], result
        assert actual["authority_execution_permission"] == "forbidden", result


def test_gdk5_meta_matrix_summary_is_complete() -> None:
    results = [evaluate_gdk5_meta_case(case) for case in GDK5_UNSEEN_EVAL_CASES]
    summary = summarize_gdk5_results(results)

    assert summary["total"] >= 10
    assert summary["failed"] == 0
    assert summary["score"] == 1.0

from __future__ import annotations

from orchestration.browser_workflow_eval import (
    BROWSER_WORKFLOW_EVAL_CASES,
    evaluate_browser_workflow_case,
)


def test_browser_workflow_eval_cases_all_pass():
    results = [evaluate_browser_workflow_case(case) for case in BROWSER_WORKFLOW_EVAL_CASES]

    assert results
    assert all(result["passed"] for result in results), results


def test_browser_workflow_eval_scores_stay_perfect_for_canonical_cases():
    for case in BROWSER_WORKFLOW_EVAL_CASES:
        result = evaluate_browser_workflow_case(case)
        assert result["score"] == 1.0

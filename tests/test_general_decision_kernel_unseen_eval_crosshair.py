from __future__ import annotations

import deal

from orchestration.general_decision_kernel_eval import score_gdk5_expectations, summarize_gdk5_results


@deal.post(lambda r: 0.0 <= float(r["score"]) <= 1.0)
@deal.post(lambda r: 0 <= int(r["passed_checks"]) <= int(r["total_checks"]))
@deal.post(lambda r: isinstance(r["checks"], dict))
def _contract_score_gdk5_expectations() -> dict:
    return score_gdk5_expectations(
        {
            "turn_kind": "think",
            "confidence": 0.82,
            "forbidden_context_classes": ["semantic_recall", "document_knowledge"],
        },
        {
            "turn_kind": "think",
            "min_confidence": 0.7,
            "forbidden_context_classes_includes": ["semantic_recall"],
        },
    )


@deal.post(lambda r: 0.0 <= float(r["score"]) <= 1.0)
@deal.post(lambda r: int(r["total"]) == int(r["passed"]) + int(r["failed"]))
@deal.post(lambda r: isinstance(r["failed_cases"], list))
def _contract_summarize_gdk5_results() -> dict:
    return summarize_gdk5_results(
        [
            {"name": "a", "passed": True},
            {"name": "b", "passed": False},
        ]
    )


def test_contract_score_gdk5_expectations_shape() -> None:
    result = _contract_score_gdk5_expectations()

    assert result["passed"] is True
    assert result["score"] == 1.0


def test_contract_summarize_gdk5_results_shape() -> None:
    result = _contract_summarize_gdk5_results()

    assert result["total"] == 2
    assert result["passed"] == 1
    assert result["failed"] == 1

from orchestration.specialist_context_eval import (
    evaluate_specialist_context_cases,
    summarize_specialist_context_evals,
)


def test_d09_specialist_context_eval_cases_all_pass():
    results = evaluate_specialist_context_cases()

    assert results
    assert all(item.passed for item in results)


def test_d09_specialist_context_eval_summary_passes_gate():
    summary = summarize_specialist_context_evals()

    assert summary["total_cases"] >= 5
    assert summary["pass_rate"] == 1.0
    assert summary["avg_score"] == 1.0
    assert summary["gate_passed"] is True
    assert summary["by_family"]["research"]["pass_rate"] == 1.0
    assert summary["by_family"]["visual"]["pass_rate"] == 1.0
    assert summary["by_family"]["system"]["pass_rate"] == 1.0
    assert summary["by_family"]["signal_contract"]["pass_rate"] == 1.0

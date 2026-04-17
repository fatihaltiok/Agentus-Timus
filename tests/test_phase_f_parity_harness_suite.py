from __future__ import annotations

from orchestration.phase_f_parity_harness_suite import (
    run_phase_f_parity_harness_suite,
    summarize_phase_f_parity_suite,
)


def test_phase_f_parity_harness_suite_runs_all_four_suites() -> None:
    report = run_phase_f_parity_harness_suite()

    assert report["contract_version"] == "phase_f_parity_harness_suite_v1"
    assert report["summary"]["suite_total"] == 4
    assert report["summary"]["suite_failed"] == 0
    assert report["summary"]["scenario_total"] == 17
    assert {item["suite_id"] for item in report["results"]} == {
        "canvas_chat",
        "approval_auth_handover",
        "delegation",
        "longrunner_queue",
    }


def test_phase_f_parity_suite_summary_counts_suites_and_scenarios() -> None:
    summary = summarize_phase_f_parity_suite(
        [
            {"suite_id": "a", "passed": True, "summary": {"total": 3, "failed": 0}},
            {"suite_id": "b", "passed": False, "summary": {"total": 4, "failed": 2}},
        ]
    )

    assert summary == {
        "state": "fail",
        "suite_total": 2,
        "suite_passed": 1,
        "suite_failed": 1,
        "scenario_total": 7,
        "scenario_failed": 2,
        "failed_suites": ["b"],
    }

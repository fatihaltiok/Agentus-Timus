from __future__ import annotations

import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.canvas_chat_parity_harness import (
    build_default_canvas_chat_parity_scenarios,
    run_canvas_chat_parity_harness_sync,
    summarize_canvas_chat_harness_results,
)


def test_canvas_chat_parity_harness_default_suite_passes() -> None:
    report = run_canvas_chat_parity_harness_sync()

    assert report["contract_version"] == "canvas_chat_parity_harness_v1"
    assert report["summary"]["total"] == 3
    assert report["summary"]["failed"] == 0
    assert report["summary"]["passed"] == 3


def test_canvas_chat_parity_harness_contains_expected_scenarios() -> None:
    report = run_canvas_chat_parity_harness_sync()

    by_id = {item["scenario_id"]: item for item in report["results"]}
    assert set(by_id) == {
        "chat_success_progress",
        "chat_phase_d_workflow_fallback",
        "chat_runtime_error",
    }
    assert by_id["chat_phase_d_workflow_fallback"]["response"]["phase_d_workflow"]["status"] == "awaiting_user"
    assert "run_failed" in [
        event["type"] for event in by_id["chat_runtime_error"]["sse_events"]
    ]


def test_summarize_canvas_chat_harness_results_counts_pass_fail() -> None:
    summary = summarize_canvas_chat_harness_results(
        [
            {"scenario_id": "ok1", "passed": True},
            {"scenario_id": "fail1", "passed": False},
            {"scenario_id": "ok2", "passed": True},
        ]
    )

    assert summary == {
        "total": 3,
        "passed": 2,
        "failed": 1,
        "failed_scenarios": ["fail1"],
    }


def test_build_default_canvas_chat_parity_scenarios_has_three_runtime_paths() -> None:
    scenarios = build_default_canvas_chat_parity_scenarios()

    assert len(scenarios) == 3
    assert {scenario.expected_status for scenario in scenarios} == {"success", "error"}

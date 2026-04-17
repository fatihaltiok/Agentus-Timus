from __future__ import annotations

from orchestration.longrunner_queue_parity_harness import (
    build_default_longrunner_queue_parity_scenarios,
    run_longrunner_queue_parity_harness,
)


def test_longrunner_queue_parity_harness_default_suite_passes() -> None:
    report = run_longrunner_queue_parity_harness()

    assert report["contract_version"] == "longrunner_queue_parity_harness_v1"
    assert report["summary"]["total"] == 6
    assert report["summary"]["passed"] == 6
    assert report["summary"]["failed"] == 0


def test_queue_retry_scenario_requeues_then_completes() -> None:
    report = run_longrunner_queue_parity_harness()
    by_id = {item["scenario_id"]: item for item in report["results"]}

    scenario = by_id["queue_retry_then_complete"]
    payload = scenario["payload"]

    assert scenario["evaluation"]["passed"] is True
    assert payload["retry_scheduled"] is True
    assert payload["final_state"]["status"] == "completed"


def test_pending_challenge_resolution_scenario_preserves_challenge_type() -> None:
    report = run_longrunner_queue_parity_harness()
    by_id = {item["scenario_id"]: item for item in report["results"]}

    scenario = by_id["pending_challenge_resolution"]
    payload = scenario["payload"]

    assert scenario["evaluation"]["passed"] is True
    assert payload["state"]["status"] == "challenge_required"
    assert payload["blocker_event"]["workflow_challenge_type"] == "2fa"
    assert payload["reply"]["reply_kind"] == "challenge_resolved"


def test_build_default_longrunner_queue_scenarios_has_six_paths() -> None:
    scenarios = build_default_longrunner_queue_parity_scenarios()

    assert len(scenarios) == 6

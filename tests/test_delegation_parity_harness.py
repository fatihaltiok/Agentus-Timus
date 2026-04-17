from __future__ import annotations

from orchestration.delegation_parity_harness import (
    build_default_delegation_parity_scenarios,
    run_delegation_parity_harness_sync,
)


def test_delegation_parity_harness_default_suite_passes() -> None:
    report = run_delegation_parity_harness_sync()

    assert report["contract_version"] == "delegation_parity_harness_v1"
    assert report["summary"]["total"] == 4
    assert report["summary"]["passed"] == 4
    assert report["summary"]["failed"] == 0


def test_delegation_timeout_partial_preserves_timeout_metadata() -> None:
    report = run_delegation_parity_harness_sync()
    by_id = {item["scenario_id"]: item for item in report["results"]}

    scenario = by_id["delegation_research_timeout_partial"]
    result = scenario["result"]

    assert scenario["evaluation"]["passed"] is True
    assert result["status"] == "partial"
    assert result["metadata"]["timed_out"] is True
    assert result["metadata"]["timeout_phase"] == "run"
    assert "Recherche-Timeout" in result["note"]


def test_delegation_workflow_partial_emits_partial_result_transport() -> None:
    report = run_delegation_parity_harness_sync()
    by_id = {item["scenario_id"]: item for item in report["results"]}

    scenario = by_id["delegation_executor_workflow_partial"]
    transport_events = scenario["transport_events"]

    assert scenario["result"]["status"] == "partial"
    assert any(
        event.get("kind") == "partial_result" and event.get("stage") == "delegation_partial"
        for event in transport_events
    )


def test_build_default_delegation_scenarios_covers_success_partial_and_error() -> None:
    scenarios = build_default_delegation_parity_scenarios()

    assert len(scenarios) == 4
    assert {scenario.expected_status for scenario in scenarios} == {"success", "partial", "error"}

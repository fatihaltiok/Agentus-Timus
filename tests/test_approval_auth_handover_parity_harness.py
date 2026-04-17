from __future__ import annotations

from orchestration.approval_auth_handover_parity_harness import (
    build_default_approval_auth_handover_scenarios,
    run_approval_auth_handover_harness_scenario,
    run_approval_auth_handover_parity_harness,
)


def test_run_approval_auth_handover_parity_harness_passes_all_default_scenarios() -> None:
    report = run_approval_auth_handover_parity_harness()

    assert report["contract_version"] == "approval_auth_handover_parity_harness_v1"
    assert report["summary"]["total"] == 4
    assert report["summary"]["passed"] == 4
    assert report["summary"]["failed"] == 0
    assert report["summary"]["failed_scenarios"] == []


def test_challenge_scenario_preserves_blocker_and_resume_hint() -> None:
    scenario = [
        item
        for item in build_default_approval_auth_handover_scenarios()
        if item.scenario_id == "challenge_required_2fa"
    ][0]

    result = run_approval_auth_handover_harness_scenario(scenario)

    workflow = result["workflow_payload"]
    blocker = result["blocker_event"]
    evaluation = result["evaluation"]

    assert evaluation["passed"] is True
    assert workflow["status"] == "challenge_required"
    assert workflow["challenge_type"] == "2fa"
    assert "2FA" in workflow["message"]
    assert "2FA" in workflow["resume_hint"]
    assert blocker["type"] == "blocker"
    assert blocker["blocker_reason"] == "challenge_required"
    assert blocker["workflow_challenge_type"] == "2fa"
    assert blocker["workflow_resume_hint"] == workflow["resume_hint"]


def test_awaiting_user_login_scenario_uses_login_handover_step() -> None:
    scenario = [
        item
        for item in build_default_approval_auth_handover_scenarios()
        if item.scenario_id == "awaiting_user_login_handover"
    ][0]

    result = run_approval_auth_handover_harness_scenario(scenario)

    workflow = result["workflow_payload"]
    blocker = result["blocker_event"]
    evaluation = result["evaluation"]

    assert evaluation["passed"] is True
    assert workflow["status"] == "awaiting_user"
    assert workflow["step"] == "login_form_ready"
    assert workflow["reason"] == "user_mediated_login"
    assert blocker["blocker_reason"] == "user_action_required"
    assert blocker["workflow_status"] == "awaiting_user"

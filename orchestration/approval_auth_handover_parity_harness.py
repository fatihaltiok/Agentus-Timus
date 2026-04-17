"""Deterministic parity harness for approval/auth/user-handover workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from orchestration.approval_auth_contract import (
    build_approval_required_workflow_payload,
    build_auth_required_workflow_payload,
    build_challenge_required_workflow_payload,
    build_user_mediated_login_workflow_payload,
    derive_user_action_blocker_reason,
)
from orchestration.longrunner_transport import make_blocker_event


@dataclass(frozen=True, slots=True)
class ApprovalAuthHandoverScenario:
    scenario_id: str
    workflow_builder: Callable[[], Mapping[str, Any]]
    expected_status: str
    expected_blocker_reason: str
    expected_service: str = ""
    expected_reason: str = ""
    expected_challenge_type: str = ""
    expected_step: str = ""
    require_resume_hint: bool = False
    require_user_action: bool = False


def build_default_approval_auth_handover_scenarios() -> list[ApprovalAuthHandoverScenario]:
    return [
        ApprovalAuthHandoverScenario(
            scenario_id="approval_required_sensitive_change",
            workflow_builder=lambda: build_approval_required_workflow_payload(
                service="github",
                approval_scope="rollback",
                message="Timus braucht deine Freigabe fuer einen Rollback bei github.",
                user_action_required="Bitte bestaetige den Rollback selbst.",
            ),
            expected_status="approval_required",
            expected_blocker_reason="approval_required",
            expected_service="github",
            expected_reason="approval_required",
            require_user_action=True,
        ),
        ApprovalAuthHandoverScenario(
            scenario_id="auth_required_login_wall",
            workflow_builder=lambda: build_auth_required_workflow_payload(
                url="https://x.com/example/status/1",
                platform="twitter",
                message="X/Twitter verlangt Login.",
                user_action_required="Bitte bestaetige den Login selbst.",
            ),
            expected_status="auth_required",
            expected_blocker_reason="auth_required",
            expected_service="x",
            expected_reason="login_wall",
            require_user_action=True,
        ),
        ApprovalAuthHandoverScenario(
            scenario_id="awaiting_user_login_handover",
            workflow_builder=lambda: build_user_mediated_login_workflow_payload(
                service="github",
                url="https://github.com/login",
            ),
            expected_status="awaiting_user",
            expected_blocker_reason="user_action_required",
            expected_service="github",
            expected_reason="user_mediated_login",
            expected_step="login_form_ready",
            require_resume_hint=True,
            require_user_action=True,
        ),
        ApprovalAuthHandoverScenario(
            scenario_id="challenge_required_2fa",
            workflow_builder=lambda: build_challenge_required_workflow_payload(
                service="github",
                challenge_type="2fa",
            ),
            expected_status="challenge_required",
            expected_blocker_reason="challenge_required",
            expected_service="github",
            expected_reason="security_challenge",
            expected_challenge_type="2fa",
            require_resume_hint=True,
            require_user_action=True,
        ),
    ]


def _normalize_blocker_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return dict(
        make_blocker_event(
            request_id="req-f3-phase-d",
            run_id="run-f3-phase-d",
            session_id="sess-f3-phase-d",
            agent="executor",
            stage="phase_d_handover",
            seq=2,
            message=str(payload.get("message") or "Workflow blockiert."),
            blocker_reason=derive_user_action_blocker_reason(payload),
            user_action_required=str(payload.get("user_action_required") or ""),
            workflow_id=str(payload.get("workflow_id") or ""),
            workflow_status=str(payload.get("status") or ""),
            workflow_service=str(payload.get("service") or ""),
            workflow_reason=str(payload.get("reason") or ""),
            workflow_message=str(payload.get("message") or ""),
            workflow_resume_hint=str(payload.get("resume_hint") or ""),
            workflow_challenge_type=str(payload.get("challenge_type") or ""),
            workflow_approval_scope=str(payload.get("approval_scope") or ""),
        ).to_dict()
    )


def evaluate_approval_auth_handover_result(
    scenario: ApprovalAuthHandoverScenario,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(result.get("workflow_payload") or {})
    blocker = dict(result.get("blocker_event") or {})
    checks: list[str] = []
    failures: list[str] = []

    if str(payload.get("status") or "") == scenario.expected_status:
        checks.append("workflow_status")
    else:
        failures.append("workflow_status")

    if str(blocker.get("type") or "") == "blocker":
        checks.append("blocker_type")
    else:
        failures.append("blocker_type")

    if str(blocker.get("blocker_reason") or "") == scenario.expected_blocker_reason:
        checks.append("blocker_reason")
    else:
        failures.append("blocker_reason")

    if str(blocker.get("workflow_status") or "") == scenario.expected_status:
        checks.append("blocker_workflow_status")
    else:
        failures.append("blocker_workflow_status")

    if scenario.expected_service:
        if str(payload.get("service") or "") == scenario.expected_service and str(blocker.get("workflow_service") or "") == scenario.expected_service:
            checks.append("service")
        else:
            failures.append("service")

    if scenario.expected_reason:
        if str(payload.get("reason") or "") == scenario.expected_reason and str(blocker.get("workflow_reason") or "") == scenario.expected_reason:
            checks.append("reason")
        else:
            failures.append("reason")

    if scenario.expected_challenge_type:
        if str(payload.get("challenge_type") or "") == scenario.expected_challenge_type and str(blocker.get("workflow_challenge_type") or "") == scenario.expected_challenge_type:
            checks.append("challenge_type")
        else:
            failures.append("challenge_type")

    if scenario.expected_step:
        if str(payload.get("step") or "") == scenario.expected_step:
            checks.append("workflow_step")
        else:
            failures.append("workflow_step")

    if scenario.require_resume_hint:
        if str(payload.get("resume_hint") or "") and str(blocker.get("workflow_resume_hint") or ""):
            checks.append("resume_hint")
        else:
            failures.append("resume_hint")

    if scenario.require_user_action:
        if str(payload.get("user_action_required") or "") and str(blocker.get("user_action_required") or ""):
            checks.append("user_action_required")
        else:
            failures.append("user_action_required")

    return {
        "scenario_id": scenario.scenario_id,
        "passed": not failures,
        "checks": checks,
        "failures": failures,
        "workflow_status": str(payload.get("status") or ""),
        "blocker_reason": str(blocker.get("blocker_reason") or ""),
    }


def summarize_approval_auth_handover_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item or {}) for item in results]
    passed = [row for row in rows if bool(row.get("passed"))]
    failed = [row for row in rows if not bool(row.get("passed"))]
    return {
        "total": len(rows),
        "passed": len(passed),
        "failed": len(failed),
        "failed_scenarios": [str(row.get("scenario_id") or "") for row in failed],
    }


def run_approval_auth_handover_harness_scenario(
    scenario: ApprovalAuthHandoverScenario,
) -> dict[str, Any]:
    workflow_payload = dict(scenario.workflow_builder() or {})
    blocker_event = _normalize_blocker_payload(workflow_payload)
    evaluation = evaluate_approval_auth_handover_result(
        scenario,
        {
            "workflow_payload": workflow_payload,
            "blocker_event": blocker_event,
        },
    )
    return {
        "scenario_id": scenario.scenario_id,
        "workflow_payload": workflow_payload,
        "blocker_event": blocker_event,
        "evaluation": evaluation,
    }


def run_approval_auth_handover_parity_harness(
    scenarios: Sequence[ApprovalAuthHandoverScenario] | None = None,
) -> dict[str, Any]:
    selected = list(scenarios or build_default_approval_auth_handover_scenarios())
    results = [run_approval_auth_handover_harness_scenario(scenario) for scenario in selected]
    evaluations = [dict(item.get("evaluation") or {}) for item in results]
    return {
        "contract_version": "approval_auth_handover_parity_harness_v1",
        "results": results,
        "summary": summarize_approval_auth_handover_results(evaluations),
    }

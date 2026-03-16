from __future__ import annotations

import deal

from orchestration.self_hardening_escalation import classify_self_hardening_effective_fix_mode
from orchestration.self_hardening_runtime import classify_self_hardening_runtime_state
from orchestration.self_hardening_verification import classify_self_hardening_verification_status


@deal.post(lambda r: r in {"critical", "warn", "ok", "idle"})
@deal.ensure(lambda last_status, last_stage, verification_status="", effective_fix_mode="", freeze_active=False, result="": (str(last_status or "").strip().lower() not in {"error", "rolled_back"}) or result == "critical")
def _contract_runtime_status_priority(
    last_status: str,
    last_stage: str,
    verification_status: str = "",
    effective_fix_mode: str = "",
    freeze_active: bool = False,
) -> str:
    return classify_self_hardening_runtime_state(
        last_status=last_status,
        last_stage=last_stage,
        verification_status=verification_status,
        effective_fix_mode=effective_fix_mode,
        freeze_active=freeze_active,
    )


@deal.post(lambda r: r in {"observe_only", "developer_task", "self_modify_safe", "human_only"})
@deal.ensure(lambda requested_fix_mode, self_modify_failures, developer_task_count=0, recurrence_count=0, result="": (str(requested_fix_mode or "").strip().lower() != "self_modify_safe") or self_modify_failures < 2 or result == "human_only")
def _contract_escalation_failure_budget(
    requested_fix_mode: str,
    self_modify_failures: int,
    developer_task_count: int = 0,
    recurrence_count: int = 0,
) -> str:
    decision = classify_self_hardening_effective_fix_mode(
        requested_fix_mode=requested_fix_mode,
        self_modify_failures=max(0, self_modify_failures),
        developer_task_count=max(0, developer_task_count),
        recurrence_count=max(0, recurrence_count),
    )
    return decision.effective_fix_mode


@deal.post(lambda r: isinstance(r, bool))
def _contract_verification_required_flag(
    result_status: str,
    required_checks: tuple[str, ...] = (),
    required_test_targets: tuple[str, ...] = (),
) -> bool:
    decision = classify_self_hardening_verification_status(
        result_status=result_status,
        required_checks=required_checks,
        required_test_targets=required_test_targets,
    )
    return decision.verification_required


def test_contract_runtime_status_priority_verification_error_warns() -> None:
    assert (
        _contract_runtime_status_priority(
            "success",
            "self_modify_finished",
            verification_status="error",
        )
        == "warn"
    )


def test_contract_escalation_failure_budget_reaches_human_only() -> None:
    assert _contract_escalation_failure_budget("self_modify_safe", 2) == "human_only"


def test_contract_verification_required_flag_matches_inputs() -> None:
    assert _contract_verification_required_flag("created", ("py_compile",), ()) is True
    assert _contract_verification_required_flag("created", (), ()) is False

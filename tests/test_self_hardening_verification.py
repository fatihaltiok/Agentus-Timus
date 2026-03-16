from __future__ import annotations

from orchestration.self_hardening_verification import classify_self_hardening_verification_status


def test_classify_self_hardening_verification_status_marks_success_as_verified() -> None:
    decision = classify_self_hardening_verification_status(
        result_status="success",
        test_result="passed",
        canary_state="passed",
        required_checks=("py_compile", "pytest_targeted"),
        required_test_targets=("tests/test_demo.py",),
    )
    assert decision.verification_status == "verified"
    assert decision.verification_required is True


def test_classify_self_hardening_verification_status_marks_task_creation_as_planned() -> None:
    decision = classify_self_hardening_verification_status(
        result_status="created",
        required_checks=("py_compile",),
    )
    assert decision.verification_status == "planned"


def test_classify_self_hardening_verification_status_marks_pending_approval() -> None:
    decision = classify_self_hardening_verification_status(
        result_status="pending_approval",
        required_checks=("py_compile",),
    )
    assert decision.verification_status == "pending_approval"


def test_classify_self_hardening_verification_status_marks_inconsistent_success_as_error() -> None:
    decision = classify_self_hardening_verification_status(
        result_status="success",
        test_result="failed",
        canary_state="passed",
        required_checks=("py_compile",),
    )
    assert decision.verification_status == "error"

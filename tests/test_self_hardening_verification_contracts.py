from __future__ import annotations

import deal

from orchestration.self_hardening_verification import (
    SelfHardeningVerificationDecision,
    classify_self_hardening_verification_status,
)


@deal.post(
    lambda r: isinstance(r, SelfHardeningVerificationDecision)
    and r.verification_status
    in {"planned", "running", "verified", "pending_approval", "blocked", "rolled_back", "error", "not_run"}
)
def _contract_classify_self_hardening_verification_status(
    result_status: str,
    test_result: str,
    canary_state: str,
) -> SelfHardeningVerificationDecision:
    return classify_self_hardening_verification_status(
        result_status=result_status,
        test_result=test_result,
        canary_state=canary_state,
        required_checks=("py_compile",),
    )


def test_contract_classify_self_hardening_verification_status_verified_on_clean_success() -> None:
    decision = _contract_classify_self_hardening_verification_status("success", "passed", "passed")
    assert decision.verification_status == "verified"


def test_contract_classify_self_hardening_verification_status_error_on_dirty_success() -> None:
    decision = _contract_classify_self_hardening_verification_status("success", "failed", "passed")
    assert decision.verification_status == "error"

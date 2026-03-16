from __future__ import annotations

from dataclasses import dataclass


_VERIFICATION_STATES = {
    "planned",
    "running",
    "verified",
    "pending_approval",
    "blocked",
    "rolled_back",
    "error",
    "not_run",
}


def _normalize_status(value: str) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True)
class SelfHardeningVerificationDecision:
    verification_status: str
    summary: str
    verification_required: bool


def classify_self_hardening_verification_status(
    *,
    result_status: str,
    test_result: str = "",
    canary_state: str = "",
    required_checks: tuple[str, ...] = (),
    required_test_targets: tuple[str, ...] = (),
) -> SelfHardeningVerificationDecision:
    normalized_result = _normalize_status(result_status)
    normalized_test = _normalize_status(test_result)
    normalized_canary = _normalize_status(canary_state)
    verification_required = bool(tuple(required_checks) or tuple(required_test_targets))

    if normalized_result in {"created", "queued"}:
        return SelfHardeningVerificationDecision(
            verification_status="planned",
            summary="verification planned",
            verification_required=verification_required,
        )
    if normalized_result in {"active", "running"}:
        return SelfHardeningVerificationDecision(
            verification_status="running",
            summary="verification running",
            verification_required=verification_required,
        )
    if normalized_result == "success":
        test_ok = normalized_test in {"", "passed", "skipped"}
        canary_ok = normalized_canary in {"", "passed"}
        if test_ok and canary_ok:
            return SelfHardeningVerificationDecision(
                verification_status="verified",
                summary="verification passed",
                verification_required=verification_required,
            )
        return SelfHardeningVerificationDecision(
            verification_status="error",
            summary="success_without_clean_verification",
            verification_required=verification_required,
        )
    if normalized_result == "pending_approval":
        return SelfHardeningVerificationDecision(
            verification_status="pending_approval",
            summary="awaiting approval before apply",
            verification_required=verification_required,
        )
    if normalized_result == "blocked":
        return SelfHardeningVerificationDecision(
            verification_status="blocked",
            summary="verification blocked",
            verification_required=verification_required,
        )
    if normalized_result == "rolled_back":
        return SelfHardeningVerificationDecision(
            verification_status="rolled_back",
            summary="verification failed and rollback applied",
            verification_required=verification_required,
        )
    if normalized_result == "error":
        return SelfHardeningVerificationDecision(
            verification_status="error",
            summary="verification error",
            verification_required=verification_required,
        )
    return SelfHardeningVerificationDecision(
        verification_status="not_run",
        summary="verification not run",
        verification_required=verification_required,
    )

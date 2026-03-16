from __future__ import annotations

import deal

from orchestration.self_hardening_runtime import classify_self_hardening_runtime_state


@deal.post(lambda r: r in {"critical", "warn", "ok", "idle"})
@deal.ensure(lambda last_status, last_stage, verification_status="", effective_fix_mode="", freeze_active=False, result="": (str(last_status or "").strip().lower() not in {"error", "rolled_back"}) or result == "critical")
def _contract_classify_self_hardening_runtime_state(
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


def test_contract_classify_self_hardening_runtime_state_error_is_critical() -> None:
    assert _contract_classify_self_hardening_runtime_state("error", "self_modify_finished") == "critical"


def test_contract_classify_self_hardening_runtime_state_verification_error_is_warn() -> None:
    assert (
        _contract_classify_self_hardening_runtime_state(
            "success",
            "self_modify_finished",
            verification_status="error",
        )
        == "warn"
    )


def test_contract_classify_self_hardening_runtime_state_human_freeze_is_warn() -> None:
    assert (
        _contract_classify_self_hardening_runtime_state(
            "success",
            "self_modify_finished",
            effective_fix_mode="human_only",
            freeze_active=True,
        )
        == "warn"
    )

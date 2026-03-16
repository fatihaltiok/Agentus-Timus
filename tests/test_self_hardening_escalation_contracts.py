from __future__ import annotations

import deal

from orchestration.self_hardening_escalation import (
    SelfHardeningEscalationDecision,
    classify_self_hardening_effective_fix_mode,
    is_self_hardening_freeze_active,
)


@deal.post(
    lambda r: isinstance(r, SelfHardeningEscalationDecision)
    and r.effective_fix_mode in {"observe_only", "developer_task", "self_modify_safe", "human_only"}
)
@deal.ensure(lambda requested_fix_mode, self_modify_failures, developer_task_count, recurrence_count, result: (not (str(requested_fix_mode or "").strip().lower() == "self_modify_safe" and self_modify_failures >= 2)) or result.effective_fix_mode == "human_only")
def _contract_classify_self_hardening_effective_fix_mode(
    requested_fix_mode: str,
    self_modify_failures: int,
    developer_task_count: int,
    recurrence_count: int,
) -> SelfHardeningEscalationDecision:
    return classify_self_hardening_effective_fix_mode(
        requested_fix_mode=requested_fix_mode,
        self_modify_failures=max(0, self_modify_failures),
        developer_task_count=max(0, developer_task_count),
        recurrence_count=max(0, recurrence_count),
    )


@deal.post(lambda r: isinstance(r, bool))
def _contract_is_self_hardening_freeze_active(freeze_until: str) -> bool:
    return is_self_hardening_freeze_active(freeze_until=freeze_until)


def test_contract_classify_self_hardening_effective_fix_mode_bounds() -> None:
    decision = _contract_classify_self_hardening_effective_fix_mode("self_modify_safe", 1, 0, 1)
    assert decision.effective_fix_mode in {"developer_task", "human_only"}


def test_contract_classify_self_hardening_effective_fix_mode_human_freeze_after_repeated_failures() -> None:
    decision = _contract_classify_self_hardening_effective_fix_mode("self_modify_safe", 2, 0, 1)
    assert decision.effective_fix_mode == "human_only"


def test_contract_is_self_hardening_freeze_active_returns_bool() -> None:
    assert isinstance(_contract_is_self_hardening_freeze_active(""), bool)

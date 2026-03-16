from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_self_hardening_escalation_contracts import (
    _contract_classify_self_hardening_effective_fix_mode,
    _contract_is_self_hardening_freeze_active,
)


@given(
    st.text(max_size=40),
    st.integers(min_value=0, max_value=6),
    st.integers(min_value=0, max_value=6),
    st.integers(min_value=0, max_value=8),
)
@settings(max_examples=80)
def test_hypothesis_classify_self_hardening_effective_fix_mode_is_bounded(
    requested_fix_mode: str,
    self_modify_failures: int,
    developer_task_count: int,
    recurrence_count: int,
) -> None:
    decision = _contract_classify_self_hardening_effective_fix_mode(
        requested_fix_mode,
        self_modify_failures,
        developer_task_count,
        recurrence_count,
    )
    assert decision.effective_fix_mode in {"observe_only", "developer_task", "self_modify_safe", "human_only"}


@given(st.text(max_size=60))
@settings(max_examples=80)
def test_hypothesis_is_self_hardening_freeze_active_is_bool(freeze_until: str) -> None:
    assert isinstance(_contract_is_self_hardening_freeze_active(freeze_until), bool)

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_self_hardening_rollout_contracts import (
    _contract_evaluate_self_hardening_rollout,
    _contract_normalize_self_hardening_rollout_stage,
)


@given(st.text(max_size=30))
@settings(max_examples=80)
def test_hypothesis_normalize_self_hardening_rollout_stage_is_bounded(value: str) -> None:
    assert _contract_normalize_self_hardening_rollout_stage(value) in {
        "observe_only",
        "developer_only",
        "self_modify_safe",
    }


@given(st.text(max_size=30), st.text(max_size=30))
@settings(max_examples=80)
def test_hypothesis_evaluate_self_hardening_rollout_is_bounded(
    requested_fix_mode: str,
    rollout_stage: str,
) -> None:
    decision = _contract_evaluate_self_hardening_rollout(requested_fix_mode, rollout_stage)
    assert decision.stage in {"observe_only", "developer_only", "self_modify_safe"}
    assert decision.effective_fix_mode in {"observe_only", "developer_task", "self_modify_safe", "human_only"}

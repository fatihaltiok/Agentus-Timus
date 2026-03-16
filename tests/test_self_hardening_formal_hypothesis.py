from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_self_hardening_formal_contracts import (
    _contract_escalation_failure_budget,
    _contract_runtime_status_priority,
    _contract_verification_required_flag,
)


@given(st.text(max_size=20), st.text(max_size=20), st.text(max_size=20), st.text(max_size=20), st.booleans())
@settings(max_examples=80)
def test_hypothesis_runtime_status_priority_is_bounded(
    last_status: str,
    last_stage: str,
    verification_status: str,
    effective_fix_mode: str,
    freeze_active: bool,
) -> None:
    assert _contract_runtime_status_priority(
        last_status,
        last_stage,
        verification_status,
        effective_fix_mode,
        freeze_active,
    ) in {"critical", "warn", "ok", "idle"}


@given(st.text(max_size=20), st.integers(min_value=0, max_value=6))
@settings(max_examples=80)
def test_hypothesis_escalation_failure_budget_is_bounded(
    requested_fix_mode: str,
    self_modify_failures: int,
) -> None:
    assert _contract_escalation_failure_budget(requested_fix_mode, self_modify_failures) in {
        "observe_only",
        "developer_task",
        "self_modify_safe",
        "human_only",
    }


@given(st.text(max_size=20), st.lists(st.text(min_size=1, max_size=20), max_size=3), st.lists(st.text(min_size=1, max_size=40), max_size=3))
@settings(max_examples=80)
def test_hypothesis_verification_required_flag_matches_inputs(
    result_status: str,
    required_checks: list[str],
    required_test_targets: list[str],
) -> None:
    assert _contract_verification_required_flag(
        result_status,
        tuple(required_checks),
        tuple(required_test_targets),
    ) == bool(required_checks or required_test_targets)

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_self_hardening_execution_policy_contracts import (
    _contract_evaluate_self_hardening_execution,
)


@given(
    requested_fix_mode=st.text(max_size=40),
    recommended_agent=st.text(max_size=40),
    target_file_path=st.text(max_size=80),
    change_type=st.text(max_size=40),
)
@settings(max_examples=120)
def test_hypothesis_self_hardening_execution_bounds(
    requested_fix_mode: str,
    recommended_agent: str,
    target_file_path: str,
    change_type: str,
) -> None:
    result = _contract_evaluate_self_hardening_execution(
        requested_fix_mode,
        recommended_agent,
        target_file_path,
        change_type,
        "",
    )
    assert result.route_target in {"", "development", "self_modify"}
    assert result.effective_fix_mode in {"observe_only", "developer_task", "self_modify_safe", "human_only"}

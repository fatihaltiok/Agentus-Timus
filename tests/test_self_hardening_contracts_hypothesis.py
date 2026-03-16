from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_self_hardening_contracts import (
    _contract_build_hardening_task_metadata,
    _contract_normalize_fix_mode,
    _contract_priority_for_hardening_severity,
    _contract_should_bridge_fix_mode,
)


@given(st.text(max_size=40))
@settings(max_examples=80)
def test_hypothesis_normalize_fix_mode_is_bounded(raw: str):
    result = _contract_normalize_fix_mode(raw)
    assert result in {"observe_only", "developer_task", "self_modify_safe", "human_only"}


@given(st.text(max_size=40))
@settings(max_examples=80)
def test_hypothesis_should_bridge_fix_mode_matches_contract(raw: str):
    result = _contract_should_bridge_fix_mode(raw)
    normalized = _contract_normalize_fix_mode(raw)
    assert result == (normalized in {"developer_task", "self_modify_safe"})


@given(st.text(max_size=40))
@settings(max_examples=80)
def test_hypothesis_priority_for_hardening_severity_is_bounded(raw: str):
    priority = _contract_priority_for_hardening_severity(raw)
    assert priority in {1, 2, 3}


@given(st.text(max_size=40))
@settings(max_examples=80)
def test_hypothesis_build_hardening_task_metadata_shape(goal_id: str):
    result = _contract_build_hardening_task_metadata(goal_id)
    assert result["source"] == "self_hardening"
    assert isinstance(result["hardening_dedup_key"], str) and result["hardening_dedup_key"]

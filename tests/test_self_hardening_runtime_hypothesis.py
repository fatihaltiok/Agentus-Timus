from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_self_hardening_runtime_contracts import (
    _contract_classify_self_hardening_runtime_state,
)


@given(st.text(max_size=40), st.text(max_size=40))
@settings(max_examples=120)
def test_hypothesis_classify_self_hardening_runtime_state_is_bounded(last_status: str, last_stage: str) -> None:
    result = _contract_classify_self_hardening_runtime_state(last_status, last_stage)
    assert result in {"critical", "warn", "ok", "idle"}

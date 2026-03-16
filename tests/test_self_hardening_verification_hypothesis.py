from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_self_hardening_verification_contracts import (
    _contract_classify_self_hardening_verification_status,
)


@given(st.text(max_size=30), st.text(max_size=20), st.text(max_size=20))
@settings(max_examples=80)
def test_hypothesis_classify_self_hardening_verification_status_is_bounded(
    result_status: str,
    test_result: str,
    canary_state: str,
) -> None:
    decision = _contract_classify_self_hardening_verification_status(
        result_status,
        test_result,
        canary_state,
    )
    assert decision.verification_status in {
        "planned",
        "running",
        "verified",
        "pending_approval",
        "blocked",
        "rolled_back",
        "error",
        "not_run",
    }

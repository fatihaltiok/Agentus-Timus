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


@given(
    st.text(max_size=20),
    st.lists(st.text(min_size=1, max_size=20), max_size=3),
    st.lists(st.text(min_size=1, max_size=40), max_size=3),
)
@settings(max_examples=80)
def test_hypothesis_classify_self_hardening_verification_required_matches_inputs(
    result_status: str,
    required_checks: list[str],
    required_test_targets: list[str],
) -> None:
    decision = _contract_classify_self_hardening_verification_status(
        result_status,
        "",
        "",
        tuple(required_checks),
        tuple(required_test_targets),
    )
    assert decision.verification_required == bool(required_checks or required_test_targets)

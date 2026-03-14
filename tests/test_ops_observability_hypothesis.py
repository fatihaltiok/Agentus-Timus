from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_ops_observability_contracts import _contract_classify_ops_state


@given(
    st.integers(min_value=0, max_value=20),
    st.integers(min_value=0, max_value=20),
    st.integers(min_value=0, max_value=20),
    st.integers(min_value=0, max_value=20),
)
@settings(max_examples=80)
def test_hypothesis_ops_state_is_valid(
    failing_services: int,
    unhealthy_providers: int,
    critical_alerts: int,
    warnings: int,
):
    state = _contract_classify_ops_state(
        failing_services,
        unhealthy_providers,
        critical_alerts,
        warnings,
    )
    assert state in {"ok", "warn", "critical"}

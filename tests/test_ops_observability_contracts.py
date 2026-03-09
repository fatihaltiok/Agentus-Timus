"""CrossHair + Hypothesis contracts for operational observability state mapping."""

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.ops_observability import classify_ops_state


@deal.pre(lambda failing_services, unhealthy_providers, critical_alerts, warnings: min(failing_services, unhealthy_providers, critical_alerts, warnings) >= 0)
@deal.post(lambda r: r in {"ok", "warn", "critical"})
def _contract_classify_ops_state(
    failing_services: int,
    unhealthy_providers: int,
    critical_alerts: int,
    warnings: int,
) -> str:
    return classify_ops_state(
        failing_services=failing_services,
        unhealthy_providers=unhealthy_providers,
        critical_alerts=critical_alerts,
        warnings=warnings,
    )


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

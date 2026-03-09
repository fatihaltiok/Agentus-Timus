from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.ops_release_gate import evaluate_ops_release_gate


@deal.pre(lambda current_canary_percent: 0 <= current_canary_percent <= 100)
@deal.post(lambda r: 0 <= int(r["recommended_canary_percent"]) <= 100)
@deal.post(lambda r: r["state"] in {"pass", "warn", "blocked"})
def _contract_ops_release_gate(summary: dict, current_canary_percent: int) -> dict:
    return evaluate_ops_release_gate(summary, current_canary_percent=current_canary_percent)


@given(
    current_canary_percent=st.integers(min_value=0, max_value=100),
    critical_alerts=st.integers(min_value=0, max_value=5),
    warnings=st.integers(min_value=0, max_value=5),
    failing_services=st.integers(min_value=0, max_value=3),
    unhealthy_providers=st.integers(min_value=0, max_value=3),
    breached=st.integers(min_value=0, max_value=6),
)
@settings(max_examples=60)
def test_hypothesis_ops_release_gate_returns_bounded_canary(
    current_canary_percent: int,
    critical_alerts: int,
    warnings: int,
    failing_services: int,
    unhealthy_providers: int,
    breached: int,
):
    summary = {
        "state": "critical" if critical_alerts or failing_services or unhealthy_providers else ("warn" if warnings or breached else "ok"),
        "critical_alerts": critical_alerts,
        "warnings": warnings,
        "failing_services": failing_services,
        "unhealthy_providers": unhealthy_providers,
        "slo": {"breached": breached},
        "alerts": [],
    }

    decision = _contract_ops_release_gate(summary, current_canary_percent)
    assert 0 <= decision["recommended_canary_percent"] <= 100
    assert decision["state"] in {"pass", "warn", "blocked"}

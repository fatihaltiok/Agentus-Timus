"""CrossHair + Hypothesis contracts for self-healing recovery ladder states."""

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.self_healing_engine import SelfHealingEngine


@deal.post(lambda r: r["phase"] in {"degraded", "recovering", "blocked"} and bool(r["stage"]))
def _contract_recovery_ladder_state(
    playbook_attempts: int,
    max_attempts: int,
    allow_playbook: bool,
    retry_due: bool,
    should_attempt: bool,
    attempts_exhausted: bool,
    verified_outage: bool,
    conservative_mode: bool,
) -> dict:
    engine = SelfHealingEngine.__new__(SelfHealingEngine)
    return engine._build_recovery_ladder_state(
        incident_key="test_incident",
        component="mcp",
        signal="mcp_health",
        severity="high",
        playbook_attempts=playbook_attempts,
        max_attempts=max_attempts,
        allow_playbook=allow_playbook,
        retry_due=retry_due,
        should_attempt=should_attempt,
        attempts_exhausted=attempts_exhausted,
        verified_outage=verified_outage,
        conservative_mode=conservative_mode,
    )


@given(
    st.integers(min_value=0, max_value=5),
    st.integers(min_value=1, max_value=5),
    st.booleans(),
    st.booleans(),
    st.booleans(),
    st.booleans(),
    st.booleans(),
    st.booleans(),
)
@settings(max_examples=80)
def test_hypothesis_recovery_ladder_returns_known_phase(
    playbook_attempts: int,
    max_attempts: int,
    allow_playbook: bool,
    retry_due: bool,
    should_attempt: bool,
    attempts_exhausted: bool,
    verified_outage: bool,
    conservative_mode: bool,
) -> None:
    result = _contract_recovery_ladder_state(
        playbook_attempts,
        max_attempts,
        allow_playbook,
        retry_due,
        should_attempt,
        attempts_exhausted,
        verified_outage,
        conservative_mode,
    )
    assert result["phase"] in {"degraded", "recovering", "blocked"}
    assert bool(result["stage"])

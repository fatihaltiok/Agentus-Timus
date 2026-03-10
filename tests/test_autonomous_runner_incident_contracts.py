"""CrossHair + Hypothesis contracts for autonomous incident notification guards."""

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.autonomous_runner import _build_incident_notification_key, _incident_notification_cooldown_active, _parse_task_metadata
from orchestration.autonomous_runner import _incident_quarantine_state_key
from orchestration.autonomous_runner import _resource_guard_state_key


@deal.post(lambda r: isinstance(r, str) and bool(r.strip()))
def _contract_incident_notification_key(description: str, metadata: dict) -> str:
    return _build_incident_notification_key(description, metadata)


@deal.post(lambda r: isinstance(r, bool))
def _contract_cooldown_active(last_sent_at: object, cooldown_minutes: int) -> bool:
    from datetime import datetime

    return _incident_notification_cooldown_active(
        last_sent_at=last_sent_at,
        now=datetime(2026, 3, 10, 12, 0, 0),
        cooldown_minutes=cooldown_minutes,
    )


@deal.pre(lambda incident_key: bool(incident_key.strip()))
@deal.post(lambda r: r.startswith("incident_quarantine:") and len(r) > len("incident_quarantine:"))
def _contract_quarantine_state_key(incident_key: str) -> str:
    return _incident_quarantine_state_key(incident_key)


@deal.post(lambda r: r == "resource_guard")
def _contract_resource_guard_state_key() -> str:
    return _resource_guard_state_key()


@given(st.one_of(st.none(), st.text(max_size=80), st.dictionaries(st.text(max_size=10), st.integers(), max_size=3)))
@settings(max_examples=80)
def test_hypothesis_parse_task_metadata_never_crashes(raw: object) -> None:
    result = _parse_task_metadata(raw)
    assert isinstance(result, dict)


@given(
    st.text(max_size=80),
    st.one_of(st.just(""), st.text(min_size=1, max_size=40)),
)
@settings(max_examples=80)
def test_hypothesis_incident_key_builder_returns_non_empty(description: str, incident_key: str) -> None:
    metadata = {"incident_key": incident_key}
    result = _contract_incident_notification_key(description, metadata)
    if incident_key.strip():
        assert result == incident_key.strip()
    else:
        assert bool(result.strip())


@given(
    st.one_of(st.none(), st.just("2026-03-10T11:30:00"), st.text(max_size=30)),
    st.integers(min_value=-5, max_value=300),
)
@settings(max_examples=80)
def test_hypothesis_cooldown_active_returns_bool(last_sent_at: object, cooldown_minutes: int) -> None:
    assert isinstance(_contract_cooldown_active(last_sent_at, cooldown_minutes), bool)


@given(st.text(min_size=1, max_size=40).filter(lambda s: bool(s.strip())))
@settings(max_examples=80)
def test_hypothesis_quarantine_state_key_prefix(incident_key: str) -> None:
    result = _contract_quarantine_state_key(incident_key)
    assert result.startswith("incident_quarantine:")


def test_resource_guard_state_key_is_stable() -> None:
    assert _contract_resource_guard_state_key() == "resource_guard"

from __future__ import annotations

from hypothesis import given, strategies as st

from tests.test_location_presence_contracts import (
    _contract_classify_location_freshness,
    _contract_prepare_location_presence_snapshot,
)


@given(
    effective_age_seconds=st.one_of(st.none(), st.integers(min_value=-60, max_value=200000)),
    accuracy_meters=st.one_of(st.none(), st.floats(min_value=0, max_value=5000, allow_nan=False, allow_infinity=False)),
)
def test_hypothesis_classify_location_freshness_is_bounded(
    effective_age_seconds: int | None,
    accuracy_meters: float | None,
) -> None:
    result = _contract_classify_location_freshness(effective_age_seconds, accuracy_meters)
    assert result["presence_status"] in {"live", "recent", "stale", "unknown"}
    assert isinstance(result["usable_for_context"], bool)


@given(
    latitude=st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
    longitude=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_prepare_location_presence_snapshot_populates_required_fields(
    latitude: float,
    longitude: float,
) -> None:
    prepared = _contract_prepare_location_presence_snapshot(
        {"latitude": latitude, "longitude": longitude}
    )
    assert prepared["device_id"]
    assert prepared["user_scope"]
    assert prepared["received_at"]

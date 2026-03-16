from __future__ import annotations

from hypothesis import given, strategies as st

from tests.test_location_route_contracts import (
    _contract_build_google_maps_directions_url,
    _contract_normalize_route_travel_mode,
    _contract_prepare_route_snapshot,
)


@given(value=st.text(min_size=0, max_size=40))
def test_hypothesis_normalize_route_travel_mode_is_bounded(value: str) -> None:
    assert _contract_normalize_route_travel_mode(value) in {"driving", "walking", "bicycling", "transit"}


@given(
    origin_latitude=st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
    origin_longitude=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
    destination_query=st.text(min_size=1, max_size=80),
    travel_mode=st.text(min_size=0, max_size=20),
)
def test_hypothesis_build_google_maps_directions_url_has_prefix(
    origin_latitude: float,
    origin_longitude: float,
    destination_query: str,
    travel_mode: str,
) -> None:
    url = _contract_build_google_maps_directions_url(
        origin_latitude,
        origin_longitude,
        destination_query,
        travel_mode,
    )
    assert url.startswith("https://www.google.com/maps/dir/?api=1")


@given(
    destination_query=st.text(min_size=0, max_size=60),
    travel_mode=st.text(min_size=0, max_size=20),
)
def test_hypothesis_prepare_route_snapshot_is_bounded(destination_query: str, travel_mode: str) -> None:
    result = _contract_prepare_route_snapshot(
        {
            "destination_query": destination_query,
            "travel_mode": travel_mode,
            "route_url": "https://www.google.com/maps/dir/?api=1",
        }
    )
    assert isinstance(result["has_route"], bool)

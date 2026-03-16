from __future__ import annotations

from hypothesis import given, strategies as st

from utils.location_reroute import assess_live_reroute, distance_meters


@given(
    lat1=st.floats(min_value=-89.0, max_value=89.0, allow_nan=False, allow_infinity=False),
    lon1=st.floats(min_value=-179.0, max_value=179.0, allow_nan=False, allow_infinity=False),
    lat2=st.floats(min_value=-89.0, max_value=89.0, allow_nan=False, allow_infinity=False),
    lon2=st.floats(min_value=-179.0, max_value=179.0, allow_nan=False, allow_infinity=False),
)
def test_distance_meters_is_symmetric(lat1: float, lon1: float, lat2: float, lon2: float) -> None:
    forward = distance_meters(lat1, lon1, lat2, lon2)
    backward = distance_meters(lat2, lon2, lat1, lon1)
    assert forward == backward


@given(
    threshold=st.integers(min_value=25, max_value=1000),
    moved_distance=st.integers(min_value=0, max_value=1500),
)
def test_assess_live_reroute_threshold_invariant(threshold: int, moved_distance: int) -> None:
    location_latitude = 52.520008 + (moved_distance / 111_000.0)
    result = assess_live_reroute(
        {
            "has_route": True,
            "destination_query": "Checkpoint Charlie Berlin",
            "saved_at": "2026-03-16T14:00:00Z",
            "start_coordinates": {"latitude": 52.520008, "longitude": 13.404954},
        },
        {
            "latitude": location_latitude,
            "longitude": 13.404954,
            "presence_status": "live",
            "usable_for_context": True,
        },
        min_distance_meters=threshold,
        min_interval_seconds=0,
    )

    measured = result["moved_distance_meters"] or 0
    if result["should_reroute"]:
        assert measured >= threshold

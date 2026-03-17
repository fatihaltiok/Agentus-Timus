from __future__ import annotations

from hypothesis import given, strategies as st

from tests.test_location_route_contracts import (
    _contract_build_google_maps_directions_url,
    _contract_choose_route_provider,
    _contract_parse_google_routes_compute_route,
    _contract_normalize_route_travel_mode,
    _contract_prepare_route_snapshot,
    _contract_route_is_active,
    _contract_route_step_segment_available,
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


@given(
    distance_meters=st.integers(min_value=1, max_value=250000),
    duration_seconds=st.integers(min_value=1, max_value=200000),
)
def test_hypothesis_google_routes_parser_is_bounded(distance_meters: int, duration_seconds: int) -> None:
    result = _contract_parse_google_routes_compute_route(
        {
            "routes": [
                {
                    "distanceMeters": distance_meters,
                    "duration": f"{duration_seconds}s",
                    "polyline": {"encodedPolyline": "encoded-route-polyline"},
                    "legs": [
                        {
                            "distanceMeters": distance_meters,
                            "duration": f"{duration_seconds}s",
                            "startLocation": {"latLng": {"latitude": 50.100241, "longitude": 8.7787097}},
                            "endLocation": {"latLng": {"latitude": 50.1264123, "longitude": 8.9283105}},
                            "steps": [],
                        }
                    ],
                }
            ]
        },
        {"display_name": "Flutstraße 33, Offenbach", "latitude": 50.100241, "longitude": 8.7787097},
        "Hanau",
        "driving",
    )
    assert result["source_provider"] == "google_routes"


@given(
    has_google=st.booleans(),
    has_serpapi=st.booleans(),
)
def test_hypothesis_choose_route_provider_prefers_google(has_google: bool, has_serpapi: bool) -> None:
    if not has_google and not has_serpapi:
        return
    result = _contract_choose_route_provider(has_google, has_serpapi)
    assert result in {"google_routes", "serpapi"}
    if has_google:
        assert result == "google_routes"


@given(
    route_url=st.text(min_size=0, max_size=80),
    destination_query=st.text(min_size=0, max_size=80),
)
def test_hypothesis_route_is_active_matches_inputs(route_url: str, destination_query: str) -> None:
    result = _contract_route_is_active(route_url, destination_query)
    assert result == bool(route_url.strip() and destination_query.strip())


@given(
    start_lat=st.one_of(st.none(), st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False)),
    start_lng=st.one_of(st.none(), st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False)),
    end_lat=st.one_of(st.none(), st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False)),
    end_lng=st.one_of(st.none(), st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False)),
)
def test_hypothesis_route_step_segment_available_requires_both_points(
    start_lat: float | None,
    start_lng: float | None,
    end_lat: float | None,
    end_lng: float | None,
) -> None:
    start = {}
    end = {}
    if start_lat is not None and start_lng is not None:
        start = {"latitude": start_lat, "longitude": start_lng}
    if end_lat is not None and end_lng is not None:
        end = {"latitude": end_lat, "longitude": end_lng}
    result = _contract_route_step_segment_available(start, end)
    if result:
        assert bool(start) is True
        assert bool(end) is True

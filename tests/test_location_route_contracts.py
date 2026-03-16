from __future__ import annotations

import deal

from utils.location_route import (
    build_google_maps_directions_url,
    normalize_route_travel_mode,
    parse_serpapi_google_maps_directions,
    prepare_route_snapshot,
)


@deal.post(lambda r: r in {"driving", "walking", "bicycling", "transit"})
def _contract_normalize_route_travel_mode(value: str) -> str:
    return normalize_route_travel_mode(value)


@deal.post(lambda r: r.startswith("https://www.google.com/maps/dir/?api=1"))
def _contract_build_google_maps_directions_url(
    origin_latitude: float,
    origin_longitude: float,
    destination_query: str,
    travel_mode: str,
) -> str:
    return build_google_maps_directions_url(
        origin_latitude=origin_latitude,
        origin_longitude=origin_longitude,
        destination_query=destination_query,
        travel_mode=travel_mode,
    )


@deal.post(lambda r: r["travel_mode"] in {"driving", "walking", "bicycling", "transit"})
@deal.post(lambda r: isinstance(r["steps"], list))
def _contract_parse_serpapi_google_maps_directions(data: dict, origin: dict, destination_query: str, travel_mode: str):
    return parse_serpapi_google_maps_directions(
        data,
        origin=origin,
        destination_query=destination_query,
        travel_mode=travel_mode,
    )


@deal.post(lambda r: isinstance(r["has_route"], bool))
@deal.post(lambda r: r["travel_mode"] in {"driving", "walking", "bicycling", "transit"})
def _contract_prepare_route_snapshot(payload: dict):
    return prepare_route_snapshot(payload)


def test_contract_prepare_route_snapshot_defaults() -> None:
    result = _contract_prepare_route_snapshot({"destination_query": "Berlin"})
    assert result["travel_mode"] == "driving"


def test_contract_normalize_route_travel_mode_defaults_unknown() -> None:
    assert _contract_normalize_route_travel_mode("teleport") == "driving"

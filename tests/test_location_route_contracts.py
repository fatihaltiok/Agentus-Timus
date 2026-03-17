from __future__ import annotations

import deal

from utils.location_route import (
    build_google_maps_directions_url,
    normalize_route_travel_mode,
    parse_google_routes_compute_route,
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


@deal.post(lambda r: r["travel_mode"] in {"driving", "walking", "bicycling", "transit"})
@deal.post(lambda r: isinstance(r["steps"], list))
@deal.post(lambda r: r["source_provider"] == "google_routes")
def _contract_parse_google_routes_compute_route(data: dict, origin: dict, destination_query: str, travel_mode: str):
    return parse_google_routes_compute_route(
        data,
        origin=origin,
        destination_query=destination_query,
        travel_mode=travel_mode,
    )


@deal.post(lambda r: isinstance(r["has_route"], bool))
@deal.post(lambda r: r["travel_mode"] in {"driving", "walking", "bicycling", "transit"})
@deal.post(lambda r: r["route_status"] in {"active", "warning"})
@deal.post(lambda r: r["source_provider"] in {"serpapi", "google_routes"})
def _contract_prepare_route_snapshot(payload: dict):
    return prepare_route_snapshot(payload)


@deal.pre(lambda has_google, has_serpapi: has_google or has_serpapi)
@deal.post(lambda r: r in {"google_routes", "serpapi"})
@deal.ensure(lambda has_google, has_serpapi, result: (not has_google) or result == "google_routes")
@deal.ensure(lambda has_google, has_serpapi, result: has_google or result == "serpapi")
def _contract_choose_route_provider(has_google: bool, has_serpapi: bool) -> str:
    return "google_routes" if has_google else "serpapi"


@deal.post(lambda r: isinstance(r, bool))
@deal.ensure(lambda route_url, destination_query, result: result == bool(str(route_url or "").strip() and str(destination_query or "").strip()))
def _contract_route_is_active(route_url: str, destination_query: str) -> bool:
    return bool(str(route_url or "").strip() and str(destination_query or "").strip())


def test_contract_prepare_route_snapshot_defaults() -> None:
    result = _contract_prepare_route_snapshot({"destination_query": "Berlin"})
    assert result["travel_mode"] == "driving"


def test_contract_normalize_route_travel_mode_defaults_unknown() -> None:
    assert _contract_normalize_route_travel_mode("teleport") == "driving"


def test_contract_parse_google_routes_compute_route_preserves_provider() -> None:
    result = _contract_parse_google_routes_compute_route(
        {
            "routes": [
                {
                    "distanceMeters": 18600,
                    "duration": "1149s",
                    "polyline": {"encodedPolyline": "encoded-route-polyline"},
                    "legs": [
                        {
                            "distanceMeters": 18600,
                            "duration": "1149s",
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
    assert result["overview_polyline"] == "encoded-route-polyline"


def test_contract_choose_route_provider_prefers_google() -> None:
    assert _contract_choose_route_provider(True, True) == "google_routes"


def test_contract_route_is_active_requires_url_and_destination() -> None:
    assert _contract_route_is_active("https://www.google.com/maps/dir/?api=1", "Hanau") is True
    assert _contract_route_is_active("", "Hanau") is False

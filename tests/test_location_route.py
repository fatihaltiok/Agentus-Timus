from __future__ import annotations

from utils.location_route import (
    build_google_maps_directions_url,
    normalize_route_travel_mode,
    parse_google_routes_compute_route,
    parse_serpapi_google_maps_directions,
    prepare_route_snapshot,
    route_step_segment_available,
    strip_route_instruction_html,
)


def test_normalize_route_travel_mode_maps_aliases() -> None:
    assert normalize_route_travel_mode("car") == "driving"
    assert normalize_route_travel_mode("zu fuss") == "walking"
    assert normalize_route_travel_mode("fahrrad") == "bicycling"
    assert normalize_route_travel_mode("öpnv") == "transit"


def test_strip_route_instruction_html_removes_tags() -> None:
    assert strip_route_instruction_html("Nach <b>Süden</b> gehen") == "Nach Süden gehen"


def test_build_google_maps_directions_url_contains_origin_destination_and_mode() -> None:
    url = build_google_maps_directions_url(
        origin_latitude=52.52,
        origin_longitude=13.4,
        destination_query="Checkpoint Charlie Berlin",
        travel_mode="walking",
    )

    assert "origin=52.52,13.4" in url
    assert "destination=Checkpoint+Charlie+Berlin" in url
    assert "travelmode=walking" in url


def test_route_step_segment_available_requires_both_endpoints() -> None:
    assert (
        route_step_segment_available(
            {"latitude": 50.100241, "longitude": 8.7787097},
            {"latitude": 50.1003921, "longitude": 8.7784912},
        )
        is True
    )
    assert route_step_segment_available({"latitude": 50.100241, "longitude": 8.7787097}, {}) is False


def test_parse_serpapi_google_maps_directions_normalizes_route() -> None:
    result = parse_serpapi_google_maps_directions(
        {
            "directions": [
                {
                    "summary": "Schnellste Route",
                    "overview_polyline": {"points": "abc123"},
                    "legs": [
                        {
                            "start_address": "Alexanderplatz, Berlin",
                            "end_address": "Checkpoint Charlie, Berlin",
                            "start_location": {"latitude": 52.520008, "longitude": 13.404954},
                            "end_location": {"latitude": 52.507507, "longitude": 13.390373},
                            "distance": {"text": "1,2 km"},
                            "duration": {"text": "16 Min."},
                            "steps": [
                                {
                                    "html_instructions": "Nach <b>Süden</b> gehen",
                                    "distance": {"text": "200 m"},
                                    "duration": {"text": "3 Min."},
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        origin={"display_name": "Alexanderplatz, Berlin", "latitude": 52.520008, "longitude": 13.404954},
        destination_query="Checkpoint Charlie Berlin",
        travel_mode="walking",
    )

    assert result["travel_mode"] == "walking"
    assert result["distance_text"] == "1,2 km"
    assert result["steps"][0]["instruction"] == "Nach Süden gehen"
    assert result["start_coordinates"]["latitude"] == 52.520008
    assert result["end_coordinates"]["longitude"] == 13.390373
    assert result["overview_polyline"] == "abc123"
    assert result["route_url"].startswith("https://www.google.com/maps/dir/?api=1")


def test_parse_serpapi_google_maps_directions_supports_trip_details_format() -> None:
    result = parse_serpapi_google_maps_directions(
        {
            "places_info": [
                {
                    "address": "50.1463462, 8.8327686",
                    "gps_coordinates": {"latitude": 50.1463462, "longitude": 8.8327686},
                },
                {
                    "address": "Hanau, Deutschland",
                    "gps_coordinates": {"latitude": 50.1264123, "longitude": 8.9283105},
                },
            ],
            "directions": [
                {
                    "travel_mode": "Driving",
                    "distance": 14629,
                    "duration": 762,
                    "formatted_distance": "14,6 km",
                    "formatted_duration": "13 Min.",
                    "trips": [
                        {
                            "title": "Schnellste Route",
                            "formatted_distance": "14,6 km",
                            "formatted_duration": "13 Min.",
                            "details": [
                                {
                                    "title": "Richtung Bahnhofstraße starten",
                                    "action": "straight",
                                    "distance": 180,
                                    "duration": 35,
                                    "formatted_distance": "180 m",
                                    "formatted_duration": "35 Sek.",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        origin={"display_name": "Edisonstraße 6, Maintal", "latitude": 50.1463462, "longitude": 8.8327686},
        destination_query="Hanau",
        travel_mode="driving",
    )

    assert result["distance_text"] == "14,6 km"
    assert result["duration_text"] == "13 Min."
    assert result["destination_label"] == "Hanau, Deutschland"
    assert result["steps"][0]["instruction"] == "Richtung Bahnhofstraße starten"
    assert result["steps"][0]["distance_text"] == "180 m"
    assert result["start_coordinates"]["latitude"] == 50.1463462
    assert result["end_coordinates"]["longitude"] == 8.9283105


def test_parse_google_routes_compute_route_normalizes_route() -> None:
    result = parse_google_routes_compute_route(
        {
            "routes": [
                {
                    "description": "Über die A66",
                    "distanceMeters": 18600,
                    "duration": "1149s",
                    "polyline": {"encodedPolyline": "encoded-route-polyline"},
                    "legs": [
                        {
                            "distanceMeters": 18600,
                            "duration": "1149s",
                            "startLocation": {"latLng": {"latitude": 50.100241, "longitude": 8.7787097}},
                            "endLocation": {"latLng": {"latitude": 50.1264123, "longitude": 8.9283105}},
                            "steps": [
                                {
                                    "distanceMeters": 29,
                                    "staticDuration": "4s",
                                    "startLocation": {"latLng": {"latitude": 50.100241, "longitude": 8.7787097}},
                                    "endLocation": {"latLng": {"latitude": 50.1003921, "longitude": 8.7784912}},
                                    "navigationInstruction": {"instructions": "Richtung Landgrafenstraße starten"},
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        origin={"display_name": "Flutstraße 33, Offenbach", "latitude": 50.100241, "longitude": 8.7787097},
        destination_query="Hanau",
        travel_mode="driving",
    )

    assert result["travel_mode"] == "driving"
    assert result["distance_text"] == "18,6 km"
    assert result["duration_text"] == "19 min"
    assert result["overview_polyline"] == "encoded-route-polyline"
    assert result["steps"][0]["instruction"] == "Richtung Landgrafenstraße starten"
    assert result["steps"][0]["start_coordinates"]["latitude"] == 50.100241
    assert result["steps"][0]["end_coordinates"]["longitude"] == 8.7784912
    assert result["steps"][0]["highlight_available"] is True
    assert result["start_coordinates"]["latitude"] == 50.100241
    assert result["end_coordinates"]["longitude"] == 8.9283105
    assert result["source_provider"] == "google_routes"


def test_prepare_route_snapshot_marks_complete_route() -> None:
    snapshot = prepare_route_snapshot(
        {
            "destination_query": "Checkpoint Charlie Berlin",
            "travel_mode": "walking",
            "summary": "Schnellste Route",
            "route_url": "https://www.google.com/maps/dir/?api=1&origin=52.52,13.40&destination=Checkpoint+Charlie+Berlin&travelmode=walking",
            "steps": [{"instruction": "Nach Süden gehen"}],
        },
        saved_at="2026-03-16T12:30:00Z",
    )

    assert snapshot["has_route"] is True
    assert snapshot["travel_mode"] == "walking"
    assert snapshot["language_code"] == "de"
    assert snapshot["steps"][0]["start_coordinates"] == {}
    assert snapshot["steps"][0]["end_coordinates"] == {}
    assert snapshot["steps"][0]["highlight_available"] is False
    assert snapshot["route_status"] == "active"
    assert snapshot["reroute_count"] == 0
    assert snapshot["overview_polyline"] == ""
    assert snapshot["saved_at"] == "2026-03-16T12:30:00Z"

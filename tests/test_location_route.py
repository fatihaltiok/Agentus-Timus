from __future__ import annotations

from utils.location_route import (
    build_google_maps_directions_url,
    normalize_route_travel_mode,
    parse_serpapi_google_maps_directions,
    prepare_route_snapshot,
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
    assert snapshot["route_status"] == "active"
    assert snapshot["reroute_count"] == 0
    assert snapshot["overview_polyline"] == ""
    assert snapshot["saved_at"] == "2026-03-16T12:30:00Z"

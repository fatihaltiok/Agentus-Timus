from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from tools.search_tool import tool as search_tool_module


@pytest.mark.asyncio
async def test_get_current_location_context_reads_runtime_snapshot(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 52.520008,
                "longitude": 13.404954,
                "display_name": "Alexanderplatz, Berlin, Deutschland",
                "locality": "Berlin",
                "country_name": "Deutschland",
                "captured_at": captured_at,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)

    result = await search_tool_module.get_current_location_context()

    assert result["has_location"] is True
    assert result["presence_status"] == "live"
    assert result["location"]["locality"] == "Berlin"
    assert result["location"]["presence_status"] == "live"
    assert result["location"]["usable_for_context"] is True


@pytest.mark.asyncio
async def test_search_google_maps_places_uses_runtime_location_and_normalizes(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(minutes=3)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 52.520008,
                "longitude": 13.404954,
                "display_name": "Alexanderplatz, Berlin, Deutschland",
                "locality": "Berlin",
                "country_name": "Deutschland",
                "captured_at": captured_at,
                "maps_url": "https://www.google.com/maps/search/?api=1&query=52.520008,13.404954",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")

    captured = {}

    def fake_serpapi(params, timeout=45):
        captured["params"] = dict(params)
        return {
            "local_results": [
                {
                    "position": 1,
                    "title": "Cafe Test",
                    "place_id": "place-1",
                    "type": "Cafe",
                    "address": "Teststrasse 1, Berlin",
                    "rating": 4.7,
                    "reviews": 128,
                    "price": "$$",
                    "phone": "+49 30 123456",
                    "website": "https://cafetest.example",
                    "hours": "Geoeffnet bis 18:00",
                    "gps_coordinates": {"latitude": 52.5205, "longitude": 13.4055},
                }
            ]
        }

    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)

    result = await search_tool_module.search_google_maps_places("Cafe", max_results=3)

    assert captured["params"]["engine"] == "google_maps"
    assert captured["params"]["type"] == "search"
    assert captured["params"]["q"] == "Cafe"
    assert captured["params"]["ll"].startswith("@52.520008,13.404954,")
    assert result["origin"]["locality"] == "Berlin"
    assert result["origin"]["presence_status"] == "live"
    assert result["origin"]["usable_for_context"] is True
    assert result["results"][0]["title"] == "Cafe Test"
    assert result["results"][0]["distance_meters"] is not None
    assert result["results"][0]["maps_url"].startswith("https://www.google.com/maps/search/?api=1&query=Cafe+Test")


@pytest.mark.asyncio
async def test_get_google_maps_place_uses_place_id_and_normalizes(monkeypatch):
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")

    captured = {}

    def fake_serpapi(params, timeout=45):
        captured["params"] = dict(params)
        return {
            "place_results": {
                "title": "Apotheke Test",
                "place_id": "place-xyz",
                "type": "Apotheke",
                "address": "Marktplatz 1, Berlin",
                "rating": 4.4,
                "reviews": 22,
                "phone": "+49 30 7654321",
                "website": "https://apotheketest.example",
                "hours": "Geoeffnet bis 20:00",
                "gps_coordinates": {"latitude": 52.519, "longitude": 13.403},
            }
        }

    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)

    result = await search_tool_module.get_google_maps_place(place_id="place-xyz", language_code="de")

    assert captured["params"]["engine"] == "google_maps"
    assert captured["params"]["place_id"] == "place-xyz"
    assert result["title"] == "Apotheke Test"
    assert result["type"] == "Apotheke"
    assert result["place_id"] == "place-xyz"
    assert result["maps_url"].startswith("https://www.google.com/maps/search/?api=1&query=Apotheke+Test")


@pytest.mark.asyncio
async def test_get_google_maps_route_uses_runtime_location_and_normalizes(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 52.520008,
                "longitude": 13.404954,
                "display_name": "Alexanderplatz, Berlin, Deutschland",
                "locality": "Berlin",
                "country_name": "Deutschland",
                "captured_at": captured_at,
                "maps_url": "https://www.google.com/maps/search/?api=1&query=52.520008,13.404954",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")
    monkeypatch.setattr(search_tool_module, "GOOGLE_ROUTES_API_KEY", "")

    captured = {}

    def fake_serpapi(params, timeout=45):
        captured["params"] = dict(params)
        return {
            "directions": [
                {
                    "summary": "Schnellste Route",
                    "distance": {"text": "1,2 km"},
                    "duration": {"text": "16 Min."},
                    "legs": [
                        {
                            "start_address": "Alexanderplatz, Berlin",
                            "end_address": "Checkpoint Charlie, Berlin",
                            "distance": {"text": "1,2 km"},
                            "duration": {"text": "16 Min."},
                            "steps": [
                                {
                                    "html_instructions": "Nach <b>Süden</b> gehen",
                                    "distance": {"text": "200 m"},
                                    "duration": {"text": "3 Min."},
                                    "maneuver": "straight",
                                }
                            ],
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)

    result = await search_tool_module.get_google_maps_route(
        destination_query="Checkpoint Charlie Berlin",
        travel_mode="walking",
        language_code="de",
    )

    assert captured["params"]["engine"] == "google_maps_directions"
    assert captured["params"]["start_coords"] == "52.520008,13.404954"
    assert captured["params"]["end_addr"] == "Checkpoint Charlie Berlin"
    assert captured["params"]["travel_mode"] == "2"
    assert result["origin"]["locality"] == "Berlin"
    assert result["travel_mode"] == "walking"
    assert result["duration_text"] == "16 Min."
    assert result["steps"][0]["instruction"] == "Nach Süden gehen"
    assert result["route_url"].startswith("https://www.google.com/maps/dir/?api=1")


@pytest.mark.asyncio
async def test_get_google_maps_route_rejects_stale_origin(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 52.520008,
                "longitude": 13.404954,
                "display_name": "Alexanderplatz, Berlin, Deutschland",
                "captured_at": captured_at,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")
    monkeypatch.setattr(search_tool_module, "GOOGLE_ROUTES_API_KEY", "")

    with pytest.raises(ValueError, match="nicht frisch genug"):
        await search_tool_module.get_google_maps_route("Checkpoint Charlie Berlin")


@pytest.mark.asyncio
async def test_get_google_maps_route_retries_with_split_in_prefix_variant(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 50.1002853,
                "longitude": 8.7787283,
                "display_name": "Flutstraße 33, 63071 Offenbach am Main, Deutschland",
                "locality": "Offenbach am Main",
                "country_name": "Deutschland",
                "captured_at": captured_at,
                "maps_url": "https://www.google.com/maps/search/?api=1&query=50.1002853,8.7787283",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")
    monkeypatch.setattr(search_tool_module, "GOOGLE_ROUTES_API_KEY", "")

    attempted: list[str] = []

    def fake_serpapi(params, timeout=45):
        attempted.append(params["end_addr"])
        if params["end_addr"] == "praunheim infrankfurt":
            raise requests.HTTPError("400 Client Error: Bad Request for url: test")
        return {
            "directions": [
                {
                    "summary": "Schnellste Route",
                    "distance": {"text": "18,2 km"},
                    "duration": {"text": "22 Min."},
                    "legs": [
                        {
                            "start_address": "Offenbach am Main",
                            "end_address": "Praunheim, Frankfurt am Main",
                            "distance": {"text": "18,2 km"},
                            "duration": {"text": "22 Min."},
                            "steps": [
                                {
                                    "html_instructions": "Auf die A66 fahren",
                                    "distance": {"text": "4,0 km"},
                                    "duration": {"text": "5 Min."},
                                }
                            ],
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)

    result = await search_tool_module.get_google_maps_route(
        destination_query="praunheim infrankfurt",
        travel_mode="driving",
        language_code="de",
    )

    assert attempted == ["praunheim infrankfurt", "praunheim in frankfurt", "praunheim frankfurt"][: len(attempted)]
    assert result["requested_destination_query"] == "praunheim infrankfurt"
    assert result["destination_query"] in {"praunheim in frankfurt", "praunheim frankfurt"}
    assert result["duration_text"] == "22 Min."


@pytest.mark.asyncio
async def test_get_google_maps_route_uses_serpapi_directions_parameter_conventions(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 50.1463462,
                "longitude": 8.8327686,
                "display_name": "Edisonstraße 6, 63477 Maintal, Deutschland",
                "locality": "Maintal",
                "country_name": "Deutschland",
                "captured_at": captured_at,
                "maps_url": "https://www.google.com/maps/search/?api=1&query=50.1463462,8.8327686",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")
    monkeypatch.setattr(search_tool_module, "GOOGLE_ROUTES_API_KEY", "")

    captured = {}

    def fake_serpapi(params, timeout=45):
        captured["params"] = dict(params)
        return {
            "directions": [
                {
                    "summary": "Schnellste Route",
                    "overview_polyline": {"points": "polyline123"},
                    "legs": [
                        {
                            "start_address": "Edisonstraße 6, Maintal",
                            "end_address": "Hanau, Deutschland",
                            "start_location": {"latitude": 50.1463462, "longitude": 8.8327686},
                            "end_location": {"latitude": 50.1264, "longitude": 8.9283},
                            "distance": {"text": "14,6 km"},
                            "duration": {"text": "13 Min."},
                            "steps": [],
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)

    result = await search_tool_module.get_google_maps_route(
        destination_query="Hanau",
        travel_mode="driving",
        language_code="de",
    )

    assert captured["params"]["start_coords"] == "50.1463462,8.8327686"
    assert captured["params"]["travel_mode"] == "0"
    assert captured["params"]["end_addr"] == "Hanau"
    assert result["overview_polyline"] == "polyline123"
    assert result["start_coordinates"]["latitude"] == 50.1463462
    assert result["end_coordinates"]["longitude"] == 8.9283


@pytest.mark.asyncio
async def test_get_google_maps_route_prefers_google_routes_api(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 50.100241,
                "longitude": 8.7787097,
                "display_name": "Flutstraße 33, Offenbach am Main, Deutschland",
                "locality": "Offenbach am Main",
                "country_name": "Deutschland",
                "captured_at": captured_at,
                "maps_url": "https://www.google.com/maps/search/?api=1&query=50.100241,8.7787097",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(search_tool_module, "GOOGLE_ROUTES_API_KEY", "google-routes-test-key")
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")

    captured = {}

    def fake_google_routes(payload, timeout=45):
        captured["payload"] = dict(payload)
        return {
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
        }

    def fail_serpapi(_params, timeout=45):
        raise AssertionError("SerpAPI sollte bei erfolgreichem Google-Routes-Pfad nicht aufgerufen werden")

    monkeypatch.setattr(search_tool_module, "_call_google_routes_json", fake_google_routes)
    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fail_serpapi)

    result = await search_tool_module.get_google_maps_route(
        destination_query="Hanau",
        travel_mode="driving",
        language_code="de",
    )

    assert captured["payload"]["travelMode"] == "DRIVE"
    assert captured["payload"]["destination"]["address"] == "Hanau"
    assert result["source_provider"] == "google_routes"
    assert result["engine"] == "google_routes_computeRoutes"
    assert result["overview_polyline"] == "encoded-route-polyline"


@pytest.mark.asyncio
async def test_get_google_maps_route_google_routes_path_does_not_require_serpapi(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 50.100241,
                "longitude": 8.7787097,
                "display_name": "Flutstraße 33, Offenbach am Main, Deutschland",
                "locality": "Offenbach am Main",
                "country_name": "Deutschland",
                "captured_at": captured_at,
                "maps_url": "https://www.google.com/maps/search/?api=1&query=50.100241,8.7787097",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(search_tool_module, "GOOGLE_ROUTES_API_KEY", "google-routes-test-key")
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "")

    def fake_google_routes(payload, timeout=45):
        return {
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
                            "steps": [],
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(search_tool_module, "_call_google_routes_json", fake_google_routes)

    result = await search_tool_module.get_google_maps_route(
        destination_query="Hanau",
        travel_mode="driving",
        language_code="de",
    )

    assert result["source_provider"] == "google_routes"
    assert result["overview_polyline"] == "encoded-route-polyline"


@pytest.mark.asyncio
async def test_get_google_maps_route_falls_back_to_serpapi_when_google_routes_fails(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 50.100241,
                "longitude": 8.7787097,
                "display_name": "Flutstraße 33, Offenbach am Main, Deutschland",
                "locality": "Offenbach am Main",
                "country_name": "Deutschland",
                "captured_at": captured_at,
                "maps_url": "https://www.google.com/maps/search/?api=1&query=50.100241,8.7787097",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(search_tool_module, "GOOGLE_ROUTES_API_KEY", "google-routes-test-key")
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")

    attempts = {"google": 0, "serpapi": 0}

    def failing_google_routes(payload, timeout=45):
        attempts["google"] += 1
        raise ValueError("Google Routes API Fehler: API not enabled")

    def fake_serpapi(params, timeout=45):
        attempts["serpapi"] += 1
        return {
            "directions": [
                {
                    "summary": "Schnellste Route",
                    "distance": {"text": "18,2 km"},
                    "duration": {"text": "22 Min."},
                    "legs": [
                        {
                            "start_address": "Offenbach am Main",
                            "end_address": "Hanau, Deutschland",
                            "distance": {"text": "18,2 km"},
                            "duration": {"text": "22 Min."},
                            "steps": [
                                {
                                    "html_instructions": "Auf die A66 fahren",
                                    "distance": {"text": "4,0 km"},
                                    "duration": {"text": "5 Min."},
                                }
                            ],
                            "start_location": {"latitude": 50.100241, "longitude": 8.7787097},
                            "end_location": {"latitude": 50.1264123, "longitude": 8.9283105},
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(search_tool_module, "_call_google_routes_json", failing_google_routes)
    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)

    result = await search_tool_module.get_google_maps_route(
        destination_query="Hanau",
        travel_mode="driving",
        language_code="de",
    )

    assert attempts["google"] >= 1
    assert attempts["serpapi"] == 1
    assert result["source_provider"] == "serpapi"
    assert result["destination_label"] == "Hanau, Deutschland"

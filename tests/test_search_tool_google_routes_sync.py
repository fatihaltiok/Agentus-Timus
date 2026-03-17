from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from tools.search_tool import tool as search_tool_module


def _write_live_snapshot(tmp_path) -> None:
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
    return snapshot_path


def test_google_routes_sync_prefers_google_routes_api(monkeypatch, tmp_path) -> None:
    snapshot_path = _write_live_snapshot(tmp_path)
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(search_tool_module, "GOOGLE_ROUTES_API_KEY", "google-routes-test-key")
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")

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

    def fail_serpapi(_params, timeout=45):
        raise AssertionError("SerpAPI sollte bei erfolgreichem Google-Routes-Pfad nicht aufgerufen werden")

    monkeypatch.setattr(search_tool_module, "_call_google_routes_json", fake_google_routes)
    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fail_serpapi)

    result = asyncio.run(
        search_tool_module.get_google_maps_route(
            destination_query="Hanau",
            travel_mode="driving",
            language_code="de",
        )
    )

    assert result["source_provider"] == "google_routes"
    assert result["overview_polyline"] == "encoded-route-polyline"


def test_google_routes_sync_does_not_require_serpapi(monkeypatch, tmp_path) -> None:
    snapshot_path = _write_live_snapshot(tmp_path)
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

    result = asyncio.run(
        search_tool_module.get_google_maps_route(
            destination_query="Hanau",
            travel_mode="driving",
            language_code="de",
        )
    )

    assert result["source_provider"] == "google_routes"


def test_google_routes_sync_falls_back_to_serpapi(monkeypatch, tmp_path) -> None:
    snapshot_path = _write_live_snapshot(tmp_path)
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
                            "steps": [],
                            "start_location": {"latitude": 50.100241, "longitude": 8.7787097},
                            "end_location": {"latitude": 50.1264123, "longitude": 8.9283105},
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(search_tool_module, "_call_google_routes_json", failing_google_routes)
    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)

    result = asyncio.run(
        search_tool_module.get_google_maps_route(
            destination_query="Hanau",
            travel_mode="driving",
            language_code="de",
        )
    )

    assert attempts["google"] >= 1
    assert attempts["serpapi"] == 1
    assert result["source_provider"] == "serpapi"

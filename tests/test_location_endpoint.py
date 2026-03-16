from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import mcp_server


class _FakeRequest:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self):
        return self._payload


def test_location_routes_registered():
    paths = {route.path for route in mcp_server.app.routes}
    assert "/location/status" in paths
    assert "/location/resolve" in paths
    assert "/location/nearby" in paths
    assert "/location/route" in paths
    assert "/location/route/status" in paths
    assert "/location/route/map" in paths


@pytest.mark.asyncio
async def test_location_resolve_endpoint_uses_device_geocoder_when_google_unavailable(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    monkeypatch.setattr(mcp_server, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(mcp_server, "_location_snapshot", None)
    monkeypatch.setattr(mcp_server, "_reverse_geocode_with_google", lambda latitude, longitude: None)

    response = await mcp_server.location_resolve_endpoint(
        _FakeRequest(
            {
                    "latitude": 52.520008,
                    "longitude": 13.404954,
                    "accuracy_meters": 12.4,
                    "source": "android_fused",
                    "captured_at": captured_at,
                    "display_name": "Alexanderplatz, Berlin, Deutschland",
                "locality": "Berlin",
                "admin_area": "Berlin",
                "country_name": "Deutschland",
                "country_code": "DE",
            }
        )
    )

    assert response["status"] == "success"
    location = response["location"]
    assert location["display_name"] == "Alexanderplatz, Berlin, Deutschland"
    assert location["locality"] == "Berlin"
    assert location["geocode_provider"] == "device_geocoder"
    assert location["presence_status"] == "live"
    assert location["usable_for_context"] is True
    assert location["device_id"] == "primary_mobile"
    assert location["user_scope"] == "primary"
    assert location["maps_url"].startswith("https://www.google.com/maps/search/?api=1&query=52.520008,13.404954")
    assert snapshot_path.exists()


@pytest.mark.asyncio
async def test_location_status_endpoint_reads_persisted_snapshot(monkeypatch, tmp_path):
    captured_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        f"""
        {{
          "latitude": 48.137154,
          "longitude": 11.576124,
          "display_name": "Marienplatz, München, Deutschland",
          "locality": "München",
          "admin_area": "Bayern",
          "country_name": "Deutschland",
          "country_code": "DE",
          "captured_at": "{captured_at}",
          "source": "android_fused",
          "geocode_provider": "device_geocoder",
          "maps_url": "https://www.google.com/maps/search/?api=1&query=48.137154,11.576124"
        }}
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_server, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(mcp_server, "_location_snapshot", None)

    response = await mcp_server.location_status_endpoint()

    assert response["status"] == "success"
    assert response["location"]["locality"] == "München"
    assert response["location"]["display_name"] == "Marienplatz, München, Deutschland"
    assert response["location"]["presence_status"] == "live"
    assert response["location"]["usable_for_context"] is True
    assert response["location"]["device_id"] == "primary_mobile"


@pytest.mark.asyncio
async def test_location_nearby_endpoint_delegates_to_maps_search(monkeypatch):
    async def fake_search_google_maps_places(query: str, max_results: int = 5, **_kwargs):
        return {
            "query": query,
            "origin": {"locality": "Berlin"},
            "results": [{"title": "Cafe Test", "distance_meters": 120}],
            "source_provider": "serpapi",
            "engine": "google_maps",
        }

    from tools.search_tool import tool as search_tool_module

    monkeypatch.setattr(search_tool_module, "search_google_maps_places", fake_search_google_maps_places)

    response = await mcp_server.location_nearby_endpoint("Cafe", max_results=3)

    assert response["status"] == "success"
    assert response["query"] == "Cafe"
    assert response["origin"]["locality"] == "Berlin"
    assert response["results"][0]["title"] == "Cafe Test"


@pytest.mark.asyncio
async def test_location_route_endpoint_delegates_to_directions_and_persists(monkeypatch, tmp_path):
    route_path = tmp_path / "runtime_route_snapshot.json"
    monkeypatch.setattr(mcp_server, "_RUNTIME_ROUTE_SNAPSHOT_PATH", route_path)
    monkeypatch.setattr(mcp_server, "_route_snapshot", None)

    async def fake_get_google_maps_route(destination_query: str, travel_mode: str = "driving", language_code: str = "de"):
        assert destination_query == "Alexanderplatz Berlin"
        assert travel_mode == "walking"
        return {
            "origin": {"display_name": "Marienplatz, München", "latitude": 48.137154, "longitude": 11.576124},
            "destination_query": destination_query,
            "destination_label": "Alexanderplatz, Berlin",
            "travel_mode": "walking",
            "summary": "Route ueber den Platz",
            "distance_text": "1,2 km",
            "duration_text": "16 Min.",
            "steps": [{"instruction": "Nach Norden gehen", "distance_text": "200 m", "duration_text": "3 Min."}],
            "step_count": 1,
            "route_url": "https://www.google.com/maps/dir/?api=1&origin=48.137154,11.576124&destination=Alexanderplatz+Berlin&travelmode=walking",
            "maps_url": "https://www.google.com/maps/dir/?api=1&origin=48.137154,11.576124&destination=Alexanderplatz+Berlin&travelmode=walking",
            "source_provider": "serpapi",
            "engine": "google_maps_directions",
        }

    from tools.search_tool import tool as search_tool_module

    monkeypatch.setattr(search_tool_module, "get_google_maps_route", fake_get_google_maps_route)

    response = await mcp_server.location_route_endpoint("Alexanderplatz Berlin", travel_mode="walking")

    assert response["status"] == "success"
    assert response["travel_mode"] == "walking"
    assert response["duration_text"] == "16 Min."
    assert response["has_route"] is True
    assert route_path.exists()


@pytest.mark.asyncio
async def test_location_route_status_endpoint_reads_persisted_snapshot(monkeypatch, tmp_path):
    route_path = tmp_path / "runtime_route_snapshot.json"
    route_path.write_text(
        """
        {
          "has_route": true,
          "destination_query": "Alexanderplatz Berlin",
          "destination_label": "Alexanderplatz, Berlin",
          "travel_mode": "walking",
          "summary": "Route ueber den Platz",
          "distance_text": "1,2 km",
          "duration_text": "16 Min.",
          "steps": [{"position": 1, "instruction": "Nach Norden gehen"}],
          "step_count": 1,
          "route_url": "https://www.google.com/maps/dir/?api=1&origin=48.137154,11.576124&destination=Alexanderplatz+Berlin&travelmode=walking",
          "maps_url": "https://www.google.com/maps/dir/?api=1&origin=48.137154,11.576124&destination=Alexanderplatz+Berlin&travelmode=walking",
          "saved_at": "2026-03-16T12:30:00Z",
          "source_provider": "serpapi",
          "engine": "google_maps_directions"
        }
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_server, "_RUNTIME_ROUTE_SNAPSHOT_PATH", route_path)
    monkeypatch.setattr(mcp_server, "_route_snapshot", None)

    response = await mcp_server.location_route_status_endpoint()

    assert response["status"] == "success"
    assert response["route"]["destination_query"] == "Alexanderplatz Berlin"
    assert response["route"]["travel_mode"] == "walking"


@pytest.mark.asyncio
async def test_location_route_map_endpoint_returns_placeholder_without_route(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_RUNTIME_ROUTE_SNAPSHOT_PATH", tmp_path / "runtime_route_snapshot.json")
    monkeypatch.setattr(mcp_server, "_route_snapshot", None)

    response = await mcp_server.location_route_map_endpoint()

    assert response.media_type == "image/svg+xml"
    assert b"Keine aktive Route" in response.body


@pytest.mark.asyncio
async def test_location_route_map_endpoint_proxies_static_google_map(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "_route_snapshot",
        {
            "has_route": True,
            "destination_query": "Checkpoint Charlie Berlin",
            "destination_label": "Checkpoint Charlie, Berlin",
            "origin": {"latitude": 52.520008, "longitude": 13.404954},
            "start_coordinates": {"latitude": 52.520008, "longitude": 13.404954},
            "end_coordinates": {"latitude": 52.507507, "longitude": 13.390373},
            "saved_at": "2026-03-16T12:30:00Z",
        },
    )
    monkeypatch.setattr(mcp_server, "_google_maps_api_key", lambda: "maps-test-key")
    captured = {}

    class _FakeResponse:
        headers = {"content-type": "image/png"}
        content = b"png-bytes"

        def raise_for_status(self):
            return None

    def fake_requests_get(url: str, timeout: int = 15):
        captured["url"] = url
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(mcp_server.requests, "get", fake_requests_get)

    response = await mcp_server.location_route_map_endpoint()

    assert response.media_type == "image/png"
    assert response.body == b"png-bytes"
    assert "maps.googleapis.com/maps/api/staticmap" in captured["url"]
    assert "markers=" in captured["url"]


@pytest.mark.asyncio
async def test_location_route_endpoint_returns_400_for_invalid_route(monkeypatch):
    async def fake_get_google_maps_route(*_args, **_kwargs):
        raise ValueError("Der aktuelle Mobil-Standort ist nicht frisch genug fuer verlaessliches Routing.")

    from tools.search_tool import tool as search_tool_module

    monkeypatch.setattr(search_tool_module, "get_google_maps_route", fake_get_google_maps_route)

    response = await mcp_server.location_route_endpoint("Checkpoint Charlie Berlin")

    assert response.status_code == 400

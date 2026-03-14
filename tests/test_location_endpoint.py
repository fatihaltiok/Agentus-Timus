from __future__ import annotations

import sys
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


@pytest.mark.asyncio
async def test_location_resolve_endpoint_uses_device_geocoder_when_google_unavailable(monkeypatch, tmp_path):
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
                "captured_at": "2026-03-14T10:15:00Z",
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
    assert location["maps_url"].startswith("https://www.google.com/maps/search/?api=1&query=52.520008,13.404954")
    assert snapshot_path.exists()


@pytest.mark.asyncio
async def test_location_status_endpoint_reads_persisted_snapshot(monkeypatch, tmp_path):
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        """
        {
          "latitude": 48.137154,
          "longitude": 11.576124,
          "display_name": "Marienplatz, München, Deutschland",
          "locality": "München",
          "admin_area": "Bayern",
          "country_name": "Deutschland",
          "country_code": "DE",
          "captured_at": "2026-03-14T11:00:00Z",
          "source": "android_fused",
          "geocode_provider": "device_geocoder",
          "maps_url": "https://www.google.com/maps/search/?api=1&query=48.137154,11.576124"
        }
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_server, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(mcp_server, "_location_snapshot", None)

    response = await mcp_server.location_status_endpoint()

    assert response["status"] == "success"
    assert response["location"]["locality"] == "München"
    assert response["location"]["display_name"] == "Marienplatz, München, Deutschland"

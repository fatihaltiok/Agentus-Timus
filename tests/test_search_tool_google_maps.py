from __future__ import annotations

import json

import pytest

from tools.search_tool import tool as search_tool_module


@pytest.mark.asyncio
async def test_get_current_location_context_reads_runtime_snapshot(monkeypatch, tmp_path):
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 52.520008,
                "longitude": 13.404954,
                "display_name": "Alexanderplatz, Berlin, Deutschland",
                "locality": "Berlin",
                "country_name": "Deutschland",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(search_tool_module, "_RUNTIME_LOCATION_SNAPSHOT_PATH", snapshot_path)

    result = await search_tool_module.get_current_location_context()

    assert result["has_location"] is True
    assert result["location"]["locality"] == "Berlin"


@pytest.mark.asyncio
async def test_search_google_maps_places_uses_runtime_location_and_normalizes(monkeypatch, tmp_path):
    snapshot_path = tmp_path / "runtime_location_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "latitude": 52.520008,
                "longitude": 13.404954,
                "display_name": "Alexanderplatz, Berlin, Deutschland",
                "locality": "Berlin",
                "country_name": "Deutschland",
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

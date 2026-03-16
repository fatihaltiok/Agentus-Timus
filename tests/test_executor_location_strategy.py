import sys
from pathlib import Path

import pytest


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def _build_executor_location_task(original_task: str) -> str:
    return "\n".join(
        [
            "# DELEGATION HANDOFF",
            "target_agent: executor",
            "goal: Nutze den aktuellen Mobil-Standort und Google Maps fuer lokalen Kontext.",
            "expected_output: location_context, nearby_places, quick_summary, source_urls",
            "success_signal: Stage 'location_context_scan' erfolgreich abgeschlossen",
            "constraints: folge_dem_rezept_und_erfinde_keine_neuen_stages",
            "handoff_data:",
            "- task_type: location_local_search",
            "- recipe_id: location_local_search",
            "- stage_id: location_context_scan",
            f"- original_user_task: {original_task}",
            "",
            "# TASK",
            "Nutze den aktuellen Mobil-Standort und Google Maps fuer lokalen Kontext.",
        ]
    )


def _build_executor_route_task(original_task: str) -> str:
    return "\n".join(
        [
            "# DELEGATION HANDOFF",
            "target_agent: executor",
            "goal: Nutze den aktuellen Mobil-Standort und Google Maps fuer eine Route.",
            "expected_output: route_summary, eta, distance, steps, route_url",
            "success_signal: Stage 'location_route_plan' erfolgreich abgeschlossen",
            "constraints: folge_dem_rezept_und_erfinde_keine_neuen_stages",
            "handoff_data:",
            "- task_type: location_route",
            "- recipe_id: location_route",
            "- stage_id: location_route_plan",
            f"- original_user_task: {original_task}",
            "",
            "# TASK",
            "Nutze den aktuellen Mobil-Standort und Google Maps fuer eine Route.",
        ]
    )


@pytest.mark.asyncio
async def test_executor_location_strategy_returns_location_only(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "get_current_location_context"
        return {
            "status": "success",
            "data": {
                "has_location": True,
                "location": {
                    "display_name": "Flutstraße 33, 63071 Offenbach am Main",
                    "locality": "Offenbach am Main",
                    "admin_area": "Hessen",
                    "country_name": "Deutschland",
                    "maps_url": "https://maps.google.com/?q=50.095,8.776",
                },
            },
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(agent, _build_executor_location_task("Wo bin ich gerade?"))

    assert "Flutstraße 33" in result
    assert "Google Maps" in result


@pytest.mark.asyncio
async def test_executor_location_strategy_returns_nearby_places(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    calls: list[str] = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(method)
        if method == "get_current_location_context":
            return {
                "status": "success",
                "data": {
                    "has_location": True,
                    "location": {
                        "display_name": "Flutstraße 33, 63071 Offenbach am Main",
                        "locality": "Offenbach am Main",
                        "admin_area": "Hessen",
                        "country_name": "Deutschland",
                    },
                },
            }
        assert method == "search_google_maps_places"
        assert params["query"] == "Geschaefte"
        return {
            "status": "success",
            "data": {
                "results": [
                    {
                        "title": "REWE",
                        "distance_meters": 180,
                        "hours_summary": "Geoeffnet bis 22:00",
                        "rating": 4.2,
                        "reviews": 812,
                        "address": "Muehlheimer Strasse 1, Offenbach",
                    },
                    {
                        "title": "ROSSMANN",
                        "distance_meters": 260,
                        "hours_summary": "Geoeffnet bis 20:00",
                        "rating": 4.1,
                        "reviews": 221,
                        "address": "Muehlheimer Strasse 4, Offenbach",
                    },
                ],
            },
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_location_task("Wo gibt es in meiner Naehe offene Geschaefte?"),
    )

    assert calls == ["get_current_location_context", "search_google_maps_places"]
    assert "REWE" in result
    assert "ROSSMANN" in result
    assert "Google Maps" in result or "Geoeffnet" in result


@pytest.mark.asyncio
async def test_executor_location_strategy_preserves_specific_place_query(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    captured = {}

    async def _fake_call_tool(self, method: str, params: dict):
        if method == "get_current_location_context":
            return {
                "status": "success",
                "data": {
                    "has_location": True,
                    "presence_status": "live",
                    "location": {
                        "display_name": "Offenbach am Main",
                        "usable_for_context": True,
                        "presence_status": "live",
                    },
                },
            }
        assert method == "search_google_maps_places"
        captured["query"] = params["query"]
        return {
            "status": "success",
            "data": {
                "results": [
                    {
                        "title": "Trattoria Roma",
                        "distance_meters": 220,
                        "hours_summary": "Geoeffnet bis 23:00",
                        "rating": 4.6,
                        "reviews": 144,
                        "address": "Marktplatz 1, Offenbach",
                    }
                ],
            },
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_location_task("Finde mir ein italienisches Restaurant in meiner Nähe"),
    )

    assert captured["query"] == "italienisches Restaurant"
    assert "Trattoria Roma" in result


@pytest.mark.asyncio
async def test_executor_location_strategy_handles_missing_location(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "get_current_location_context"
        return {"status": "success", "data": {"has_location": False, "location": None}}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(agent, _build_executor_location_task("Wo bin ich?"))

    assert "keinen synchronisierten Handy-Standort" in result


@pytest.mark.asyncio
async def test_executor_location_strategy_handles_stale_location(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "get_current_location_context"
        return {
            "status": "success",
            "data": {
                "has_location": True,
                "presence_status": "stale",
                "location": {
                    "display_name": "Berlin",
                    "presence_status": "stale",
                    "usable_for_context": False,
                    "maps_url": "https://www.google.com/maps/search/?api=1&query=52.52,13.40",
                },
            },
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_location_task("Welche Apotheke hat hier noch offen?"),
    )

    assert "letzter bekannter Standort" in result
    assert "nicht frisch genug" in result


@pytest.mark.asyncio
async def test_executor_location_route_returns_real_route_and_activates_snapshot(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    calls: list[str] = []
    activated: dict[str, object] = {}

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(method)
        if method == "get_current_location_context":
            return {
                "status": "success",
                "data": {
                    "has_location": True,
                    "presence_status": "live",
                    "location": {
                        "display_name": "Flutstraße 33, 63071 Offenbach am Main",
                        "latitude": 50.1002804,
                        "longitude": 8.7786475,
                        "usable_for_context": True,
                        "presence_status": "live",
                    },
                },
            }
        assert method == "get_google_maps_route"
        assert params["destination_query"] == "frankfurt in die zeil"
        return {
            "status": "success",
            "data": {
                "destination_query": "frankfurt in die zeil",
                "destination_label": "Zeil, 60313 Frankfurt am Main",
                "travel_mode": "driving",
                "distance_text": "12.4 km",
                "duration_text": "24 min",
                "start_address": "Flutstraße 33, 63071 Offenbach am Main",
                "end_address": "Zeil, 60313 Frankfurt am Main",
                "route_url": "https://www.google.com/maps/dir/?api=1&origin=50.1002804,8.7786475&destination=frankfurt+in+die+zeil&travelmode=driving",
                "steps": [
                    {"instruction": "Starte auf der Flutstraße", "distance_text": "150 m", "duration_text": "1 min"},
                    {"instruction": "Fahre auf die A661", "distance_text": "8.0 km", "duration_text": "10 min"},
                ],
            },
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(
        ExecutorAgent,
        "_activate_route_snapshot",
        staticmethod(lambda payload: activated.update({"route": payload})),
    )

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_route_task("Erstelle mir eine Route nach Frankfurt in die Zeil"),
    )

    assert calls == ["get_current_location_context", "get_google_maps_route"]
    assert "Route nach Zeil, 60313 Frankfurt am Main ist erstellt." in result
    assert "24 min" in result
    assert "12.4 km" in result
    assert "Google Maps:" in result
    assert activated["route"]["destination_label"] == "Zeil, 60313 Frankfurt am Main"


@pytest.mark.asyncio
async def test_executor_location_route_degrades_without_fake_distance(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _fake_call_tool(self, method: str, params: dict):
        if method == "get_current_location_context":
            return {
                "status": "success",
                "data": {
                    "has_location": True,
                    "presence_status": "live",
                    "location": {
                        "display_name": "Flutstraße 33, 63071 Offenbach am Main",
                        "latitude": 50.1002804,
                        "longitude": 8.7786475,
                        "usable_for_context": True,
                        "presence_status": "live",
                    },
                },
            }
        assert method == "get_google_maps_route"
        return {"status": "error", "error": "Directions API Fehler"}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_route_task("Erstelle mir eine Route nach Frankfurt in die Zeil"),
    )

    assert "keine aktive Route" in result
    assert "Directions API Fehler" in result
    assert "travelmode=driving" in result
    assert "12-15 km" not in result

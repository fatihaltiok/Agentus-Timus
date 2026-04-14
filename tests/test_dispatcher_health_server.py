from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.dispatcher_health_server import DispatcherHealthState, create_dispatcher_health_app


def test_dispatcher_health_endpoint_reports_starting_state() -> None:
    state = DispatcherHealthState(
        host="127.0.0.1",
        port=5010,
        mcp_health_url="http://127.0.0.1:5000/health",
    )
    client = TestClient(create_dispatcher_health_app(state))

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "starting"
    assert payload["ready"] is False
    assert payload["port"] == 5010
    assert payload["mcp"]["url"] == "http://127.0.0.1:5000/health"


def test_dispatcher_health_endpoint_reports_ready_healthy_state() -> None:
    state = DispatcherHealthState(
        host="127.0.0.1",
        port=5010,
        mcp_health_url="http://127.0.0.1:5000/health",
    )
    state.set_mode("daemon")
    state.set_tools_loaded(True, description_count=42)
    state.set_component("autonomous_runner", active=True, required=True, detail={"interval_minutes": 5})
    state.set_component("system_monitor", active=True, required=True)
    state.set_component("telegram_gateway", active=False, required=False, detail={"token_configured": False})
    state.set_mcp_status(reachable=True, ready=True, status="healthy", detail="ready")
    state.mark_ready()

    client = TestClient(create_dispatcher_health_app(state))
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["ready"] is True
    assert payload["tool_description_count"] == 42
    assert payload["components"]["autonomous_runner"]["active"] is True
    assert payload["components"]["system_monitor"]["active"] is True
    assert payload["degraded_reasons"] == []


def test_dispatcher_health_endpoint_reports_degraded_state_for_required_components() -> None:
    state = DispatcherHealthState(
        host="127.0.0.1",
        port=5010,
        mcp_health_url="http://127.0.0.1:5000/health",
    )
    state.set_tools_loaded(True, description_count=1)
    state.set_component("autonomous_runner", active=False, required=True)
    state.set_component("system_monitor", active=True, required=True)
    state.set_component("telegram_gateway", active=False, required=True, detail={"token_configured": True})
    state.set_mcp_status(reachable=False, ready=False, status="unreachable", detail="connection refused")
    state.mark_ready()

    client = TestClient(create_dispatcher_health_app(state))
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["ready"] is False
    assert "mcp_unreachable" in payload["degraded_reasons"]
    assert "autonomous_runner_inactive" in payload["degraded_reasons"]
    assert "telegram_gateway_inactive" in payload["degraded_reasons"]

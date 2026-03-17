from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.canvas_ui import build_canvas_ui_html
from server.mcp_server import app


def test_canvas_ui_contains_route_panel_and_map_endpoint() -> None:
    html = build_canvas_ui_html(1500)

    assert "routeStage" in html
    assert "routeStatusBadge" in html
    assert "routeMapImage" in html
    assert "routeMapInteractive" in html
    assert "routeMapModeInteractiveBtn" in html
    assert "routeMapModeStaticBtn" in html
    assert "loadRouteStatus(true)" in html
    assert "/location/route/status" in html
    assert "/location/route/map_config" in html
    assert "/location/route/map" in html
    assert "In Google Maps öffnen" in html


def test_canvas_ui_registers_route_map_endpoint() -> None:
    paths = {route.path for route in app.routes}
    assert "/location/route/map" in paths
    assert "/location/route/map_config" in paths

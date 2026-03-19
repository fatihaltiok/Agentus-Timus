from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.mcp_server import app
from server.mobile_route_ui import build_mobile_route_ui_html


def test_mobile_route_ui_contains_route_and_location_polling() -> None:
    html = build_mobile_route_ui_html()

    assert "/location/route/status" in html
    assert "/location/status" in html
    assert "/location/route/map_config" in html
    assert "/location/route/map" in html
    assert "Follow an" in html
    assert "function renderLiveMarker" in html
    assert "function showInteractiveSurface" in html
    assert "function routeHasInteractiveGeometry" in html
    assert "function decodeRoutePath" in html
    assert 'maps.event.trigger(map, "resize")' in html


def test_mobile_route_ui_endpoint_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/location/route/mobile_view" in paths

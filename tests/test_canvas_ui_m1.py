from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.canvas_ui import build_canvas_ui_html
from server.mcp_server import app


def test_build_canvas_ui_html_contains_core_sections():
    html = build_canvas_ui_html(1500)
    assert "Timus Canvas Live View" in html
    assert "Nodes" in html
    assert "Edges" in html
    assert "Event Timeline" in html
    assert "/canvas/create" in html
    assert "/canvas/" in html
    assert "POLL_MS = 1500" in html
    assert "selectedStillExists" in html
    assert "selectedCanvasId = items[0].id" in html


def test_canvas_ui_route_registered():
    paths = {route.path for route in app.routes}
    assert "/canvas/ui" in paths

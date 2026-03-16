from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.canvas_ui import build_canvas_ui_html


def test_canvas_ui_contains_location_transparency_strip() -> None:
    html = build_canvas_ui_html(1500)

    assert "mobileLocationStrip" in html
    assert "Sharing" in html
    assert "Kontext" in html

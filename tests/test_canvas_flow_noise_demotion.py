from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.canvas_ui import build_canvas_ui_html


def test_canvas_ui_contains_noise_demotion_helpers():
    html = build_canvas_ui_html(1200)
    assert "function isFlowNoiseMessage" in html
    assert "capture() takes 1 positional argument" in html
    assert "function effectiveFlowStatus" in html

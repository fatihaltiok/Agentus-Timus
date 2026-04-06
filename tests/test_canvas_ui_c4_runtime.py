from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.canvas_ui import build_canvas_ui_html


def test_canvas_ui_contains_c4_runtime_strip_and_handlers() -> None:
    html = build_canvas_ui_html(1400)

    assert "chatRuntimeStrip" in html
    assert "chatRuntimeBadge" in html
    assert "chatRuntimeHeadline" in html
    assert "chatRuntimeMeta" in html
    assert "chatRuntimePreview" in html
    assert "function renderRuntimeStatus()" in html
    assert "function updateLongrunState(d)" in html
    assert '["run_started","progress","partial_result","blocker","run_completed","run_failed"]' in html
    assert "Anfrage gesendet. Warte auf Startsignal von Timus." in html

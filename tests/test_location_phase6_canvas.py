from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.canvas_ui import build_canvas_ui_html


def test_canvas_ui_contains_location_transparency_strip() -> None:
    html = build_canvas_ui_html(1500)

    assert "mobileLocationStrip" in html
    assert "Sharing" in html
    assert "Kontext" in html
    assert "locationControlCard" in html
    assert "locationControlSaveBtn" in html
    assert "locationSharingToggle" in html
    assert "locationContextToggle" in html
    assert "locationBackgroundSyncToggle" in html
    assert "locationPreferredDeviceSelect" in html
    assert "locationAllowedScopesInput" in html
    assert "locationMaxDeviceEntriesInput" in html
    assert "saveLocationControls()" in html
    assert "Privacy & Geräte" in html

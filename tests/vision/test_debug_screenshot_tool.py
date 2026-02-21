import json
import types
from pathlib import Path
import sys

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.debug_screenshot_tool import tool as debug_tool


class _FakeShot:
    def __init__(self, width: int, height: int):
        self.size = (width, height)
        self.bgra = bytes([255, 255, 255, 0]) * (width * height)


class _FakeMSS:
    def __init__(self):
        self.monitors = [
            {"left": 0, "top": 0, "width": 400, "height": 240},
            {"left": 100, "top": 50, "width": 200, "height": 120},
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def grab(self, monitor):
        return _FakeShot(monitor["width"], monitor["height"])


def test_create_debug_artifacts_writes_overlay_and_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("DEBUG_FAILED_CLICKS_DIR", str(tmp_path))
    monkeypatch.setattr(debug_tool, "mss", types.SimpleNamespace(mss=lambda: _FakeMSS()))

    image_path = tmp_path / "debug_overlay.png"
    result = debug_tool.create_debug_artifacts(
        target_x=125,
        target_y=85,
        width=20,
        height=10,
        confidence=0.77,
        message="Click verification failed",
        metadata={"llm_prompt": "test-prompt"},
        file_path=str(image_path),
    )

    screenshot_path = Path(result["screenshot_path"])
    metadata_path = Path(result["metadata_path"])

    assert screenshot_path.exists()
    assert metadata_path.exists()

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["target"]["x"] == 125
    assert payload["target"]["relative_x"] == 25
    assert payload["target"]["relative_y"] == 35
    assert payload["metadata"]["llm_prompt"] == "test-prompt"

    img = Image.open(screenshot_path)
    red_pixel = img.getpixel((15, 30))
    assert red_pixel[0] > 200
    assert red_pixel[1] < 80
    assert red_pixel[2] < 80


def test_create_debug_artifacts_without_target_still_creates_files(monkeypatch, tmp_path):
    monkeypatch.setenv("DEBUG_FAILED_CLICKS_DIR", str(tmp_path))
    monkeypatch.setattr(debug_tool, "mss", types.SimpleNamespace(mss=lambda: _FakeMSS()))

    result = debug_tool.create_debug_artifacts(message="No coordinates")
    assert Path(result["screenshot_path"]).exists()
    assert Path(result["metadata_path"]).exists()

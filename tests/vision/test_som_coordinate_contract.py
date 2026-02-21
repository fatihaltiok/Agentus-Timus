import pytest
from PIL import Image
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.som_tool import tool as som_tool
from tools.browser_controller.controller import HybridBrowserController


def test_parse_qwen_elements_uses_runtime_reference_resolution():
    engine = som_tool.SetOfMarkEngine()
    raw = '[{"type":"button","x":1280,"y":720,"text":"OK"}]'

    parsed = engine._parse_qwen_elements(
        raw_response=raw,
        reference_width=2560,
        reference_height=1440,
        source="unit",
    )

    assert len(parsed) == 1
    assert parsed[0]["center_x"] == 0.5
    assert parsed[0]["center_y"] == 0.5


@pytest.mark.asyncio
async def test_scan_ui_elements_use_zoom_runs_second_pass_and_keeps_contract(monkeypatch):
    calls = {"count": 0}

    def fake_capture():
        som_tool.som_engine.screen_width = 1000
        som_tool.som_engine.screen_height = 500
        som_tool.som_engine.monitor_offset_x = 0
        som_tool.som_engine.monitor_offset_y = 0
        return Image.new("RGB", (1000, 500), "white")

    def fake_detect(_img, _element_types, source="base"):
        calls["count"] += 1
        if source == "base":
            return []
        return [
            {
                "x_min": 0.2,
                "y_min": 0.2,
                "x_max": 0.3,
                "y_max": 0.3,
                "center_x": 0.25,
                "center_y": 0.25,
                "element_type": "button",
                "text": "Submit",
                "confidence": 0.9,
            }
        ]

    monkeypatch.setattr(som_tool.som_engine, "_capture_screenshot", fake_capture)
    monkeypatch.setattr(som_tool.som_engine, "_detect_all_elements", fake_detect)
    monkeypatch.setattr(som_tool, "ZOOM_PASS_THRESHOLD", 5)

    result = await som_tool.scan_ui_elements(element_types=["button"], use_zoom=True)
    assert result["count"] == 1
    assert calls["count"] == 2

    element = result["elements"][0]
    assert element["x"] == element["click_x"]
    assert element["y"] == element["click_y"]
    assert element["center_x"] == element["x"]
    assert element["center_y"] == element["y"]


@pytest.mark.asyncio
async def test_browser_controller_vision_click_supports_xy_payload():
    controller = HybridBrowserController(mcp_url="http://unused.local")
    clicked = {}

    async def fake_call_tool(method, params):
        if method == "scan_ui_elements":
            return {
                "elements": [
                    {
                        "id": 1,
                        "type": "button",
                        "x": 321,
                        "y": 654,
                        "text": "Login",
                    }
                ]
            }
        if method == "click_at":
            clicked.update(params)
            return {"status": "ok"}
        return {}

    controller._call_mcp_tool = fake_call_tool

    result = await controller._execute_vision_action(
        action_type="click",
        target={"element_type": "button", "text": "login"},
    )

    assert result.success is True
    assert clicked["x"] == 321
    assert clicked["y"] == 654

    await controller.cleanup()

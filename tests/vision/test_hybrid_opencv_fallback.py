from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.hybrid_detection_tool import tool as hybrid_tool


@pytest.mark.asyncio
async def test_find_by_template_matching_uses_opencv_tool_result(monkeypatch):
    async def fake_call(_method, _params=None):
        return {
            "found": True,
            "template_name": "login_button",
            "x": 222,
            "y": 333,
            "confidence": 0.93,
            "bbox": {"x1": 200, "y1": 310, "x2": 244, "y2": 356},
        }

    monkeypatch.setattr(hybrid_tool.hybrid_engine, "_call_tool", fake_call)

    element = await hybrid_tool.hybrid_engine.find_by_template_matching("login_button")
    assert element is not None
    assert element.method == "opencv_template"
    assert element.x == 222
    assert element.y == 333
    assert element.confidence == 0.93


@pytest.mark.asyncio
async def test_smart_find_element_falls_back_to_opencv_template(monkeypatch):
    async def no_text(_text):
        return None

    async def no_object(_element_type, prefer_index=0):
        return None

    async def template_hit(_template_name, threshold=0.82):
        return hybrid_tool.DetectedElement(
            method="opencv_template",
            element_type="template_match",
            x=400,
            y=210,
            confidence=0.88,
            text="submit_button",
            bounds={"x1": 380, "y1": 190, "x2": 420, "y2": 230},
            metadata={"source": "test"},
        )

    monkeypatch.setattr(hybrid_tool.hybrid_engine, "find_by_text", no_text)
    monkeypatch.setattr(hybrid_tool.hybrid_engine, "find_by_object_detection", no_object)
    monkeypatch.setattr(hybrid_tool.hybrid_engine, "find_by_template_matching", template_hit)

    element = await hybrid_tool.hybrid_engine.smart_find_element(
        text="submit",
        element_type="button",
        refine=False,
        template_name="submit_button",
        enable_template_fallback=True,
    )

    assert element is not None
    assert element.method == "opencv_template"
    assert element.x == 400
    assert element.y == 210


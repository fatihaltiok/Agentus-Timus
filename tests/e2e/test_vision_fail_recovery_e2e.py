"""Milestone 5 - Vision pipeline E2E failure and recovery stability tests."""

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.hybrid_detection_tool import tool as hybrid_tool


@pytest.mark.asyncio
async def test_vision_fail_recovery_e2e_recovers_on_second_attempt(monkeypatch):
    detect_calls = {"count": 0}
    click_calls = {"count": 0}

    async def fake_find_element(**_kwargs):
        detect_calls["count"] += 1
        if detect_calls["count"] == 1:
            return hybrid_tool.DetectedElement(
                method="ocr",
                element_type="button",
                x=210,
                y=120,
                confidence=0.86,
                text="Login",
            )
        return hybrid_tool.DetectedElement(
            method="opencv_template",
            element_type="button",
            x=420,
            y=260,
            confidence=0.93,
            text="Login",
        )

    async def fake_call_tool(method, params=None):
        if method != "click_with_verification":
            return {"success": True}
        click_calls["count"] += 1
        if click_calls["count"] == 1:
            return {"success": False, "x": params["x"], "y": params["y"]}
        return {"success": True, "x": params["x"], "y": params["y"]}

    monkeypatch.setattr(hybrid_tool.hybrid_engine, "smart_find_element", fake_find_element)
    monkeypatch.setattr(hybrid_tool.hybrid_engine, "_call_tool", fake_call_tool)

    result = await hybrid_tool.hybrid_find_and_click(
        text="Login",
        element_type="button",
        refine=True,
        verify=True,
        enable_template_fallback=True,
    )

    assert result["success"] is True
    assert result["recovered"] is True
    assert result["attempt_count"] == 2
    assert result["x"] == 420
    assert result["y"] == 260
    assert result["method"] == "opencv_template"
    assert result["attempts"][0]["success"] is False
    assert result["attempts"][1]["success"] is True
    assert result["pipeline_log"][0]["stage"] == "detect_primary"
    assert result["pipeline_log"][1]["stage"] == "detect_recovery"
    assert result["pipeline_log"][-1]["stage"] == "final"
    assert result["pipeline_log"][-1]["recovered"] is True


@pytest.mark.asyncio
async def test_vision_fail_recovery_e2e_failure_path_is_repeatable(monkeypatch):
    async def fake_find_element(**_kwargs):
        return hybrid_tool.DetectedElement(
            method="ocr",
            element_type="button",
            x=640,
            y=360,
            confidence=0.8,
            text="Checkout",
        )

    async def fake_call_tool(method, params=None):
        if method == "click_with_verification":
            return {"success": False, "x": params["x"], "y": params["y"]}
        return {"success": True}

    monkeypatch.setattr(hybrid_tool.hybrid_engine, "smart_find_element", fake_find_element)
    monkeypatch.setattr(hybrid_tool.hybrid_engine, "_call_tool", fake_call_tool)

    first = await hybrid_tool.hybrid_find_and_click(
        text="Checkout",
        element_type="button",
        refine=False,
        verify=True,
        enable_template_fallback=True,
    )
    second = await hybrid_tool.hybrid_find_and_click(
        text="Checkout",
        element_type="button",
        refine=False,
        verify=True,
        enable_template_fallback=True,
    )

    for result in (first, second):
        assert result["success"] is False
        assert result["recovered"] is False
        assert result["attempt_count"] == 2
        assert result["x"] == 640
        assert result["y"] == 360
        assert result["pipeline_log"][0]["stage"] == "detect_primary"
        assert result["pipeline_log"][1]["stage"] == "detect_recovery"
        assert result["pipeline_log"][-1]["stage"] == "final"
        assert result["pipeline_log"][-1]["success"] is False
        assert result["pipeline_log"][-1]["attempt_count"] == 2

    assert first["method"] == second["method"] == "ocr"
    assert first["attempts"][0]["success"] is False
    assert first["attempts"][1]["success"] is False
    assert second["attempts"][0]["success"] is False
    assert second["attempts"][1]["success"] is False

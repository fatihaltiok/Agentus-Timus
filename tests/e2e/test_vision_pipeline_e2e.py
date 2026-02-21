"""Milestone 5 - Vision pipeline E2E success path stability tests."""

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.hybrid_detection_tool import tool as hybrid_tool


@pytest.mark.asyncio
async def test_vision_pipeline_e2e_success_path_is_repeatable_and_fast(monkeypatch):
    async def fake_find_element(**_kwargs):
        return hybrid_tool.DetectedElement(
            method="ocr",
            element_type="button",
            x=320,
            y=240,
            confidence=0.95,
            text="Search",
            bounds={"x1": 300, "y1": 220, "x2": 340, "y2": 260},
            metadata={"source": "e2e-test"},
        )

    async def fake_call_tool(method, params=None):
        if method == "click_with_verification":
            return {"success": True, "x": params["x"], "y": params["y"]}
        return {"success": True}

    monkeypatch.setattr(hybrid_tool.hybrid_engine, "smart_find_element", fake_find_element)
    monkeypatch.setattr(hybrid_tool.hybrid_engine, "_call_tool", fake_call_tool)

    first = await hybrid_tool.hybrid_find_and_click(
        text="Search",
        element_type="button",
        refine=False,
        verify=True,
        enable_template_fallback=True,
    )
    second = await hybrid_tool.hybrid_find_and_click(
        text="Search",
        element_type="button",
        refine=False,
        verify=True,
        enable_template_fallback=True,
    )

    assert first["success"] is True
    assert second["success"] is True
    assert first["x"] == second["x"] == 320
    assert first["y"] == second["y"] == 240
    assert first["method"] == second["method"] == "ocr"
    assert first["attempt_count"] == second["attempt_count"] == 1
    assert first["recovered"] is False
    assert second["recovered"] is False
    assert first["runtime_ms"] < 1000
    assert second["runtime_ms"] < 1000


@pytest.mark.asyncio
async def test_vision_pipeline_e2e_returns_pipeline_quality_logs(monkeypatch):
    async def fake_find_element(**_kwargs):
        return hybrid_tool.DetectedElement(
            method="som",
            element_type="button",
            x=500,
            y=400,
            confidence=0.88,
            text="Submit",
            bounds={"x1": 480, "y1": 380, "x2": 520, "y2": 420},
            metadata={"source": "e2e-test"},
        )

    async def fake_call_tool(method, params=None):
        if method in {"click_with_verification", "click_at"}:
            return {"success": True, "x": params["x"], "y": params["y"]}
        return {"success": True}

    monkeypatch.setattr(hybrid_tool.hybrid_engine, "smart_find_element", fake_find_element)
    monkeypatch.setattr(hybrid_tool.hybrid_engine, "_call_tool", fake_call_tool)

    result = await hybrid_tool.hybrid_find_and_click(
        text="Submit",
        element_type="button",
        refine=True,
        verify=True,
        enable_template_fallback=True,
    )

    assert result["success"] is True
    assert isinstance(result["pipeline_log"], list)
    assert len(result["pipeline_log"]) >= 2
    assert result["pipeline_log"][0]["stage"] == "detect_primary"
    assert result["pipeline_log"][-1]["stage"] == "final"
    assert result["pipeline_log"][-1]["attempt_count"] == result["attempt_count"] == 1
    assert result["pipeline_log"][-1]["runtime_ms"] == result["runtime_ms"]

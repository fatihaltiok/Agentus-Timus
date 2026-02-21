import pytest
from PIL import Image
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.verification_tool import tool as verification_tool


@pytest.mark.asyncio
async def test_verify_action_captures_debug_overlay_on_failure(monkeypatch):
    engine = verification_tool.VerificationEngine()
    static_img = Image.new("RGB", (80, 60), "white")

    async def immediate_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(verification_tool.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(engine, "_capture_screenshot", lambda: static_img.copy())
    monkeypatch.setattr(engine, "_calculate_diff", lambda _a, _b: 1.0)
    monkeypatch.setattr(verification_tool, "DEBUG_SCREENSHOT_AVAILABLE", True)

    captured = {}

    def fake_create_debug_artifacts(
        target_x=None,
        target_y=None,
        width=0,
        height=0,
        confidence=None,
        message="",
        metadata=None,
        file_path=None,
    ):
        captured["target_x"] = target_x
        captured["target_y"] = target_y
        captured["message"] = message
        captured["metadata"] = metadata
        return {
            "success": True,
            "screenshot_path": "/tmp/failure_overlay.png",
            "metadata_path": "/tmp/failure_overlay.json",
        }

    monkeypatch.setattr(verification_tool, "create_debug_artifacts", fake_create_debug_artifacts)

    await engine.capture_before()
    result = await engine.verify_action(
        expected_change=False,
        min_change=0.5,
        timeout=1.0,
        debug_context={"x": 10, "y": 20, "confidence": 0.61, "llm_prompt": "abc"},
    )

    assert result.success is False
    assert result.debug_artifacts is not None
    assert result.debug_artifacts["screenshot_path"] == "/tmp/failure_overlay.png"
    assert captured["target_x"] == 10
    assert captured["target_y"] == 20
    assert "Unerwartete Änderung" in captured["message"]
    assert captured["metadata"]["context"]["llm_prompt"] == "abc"


@pytest.mark.asyncio
async def test_verify_action_result_returns_debug_artifacts(monkeypatch):
    called = {}

    async def fake_verify_action(**kwargs):
        called.update(kwargs)
        return verification_tool.VerificationResult(
            success=False,
            change_detected=False,
            change_percentage=0.0,
            stable=True,
            error_detected=False,
            message="failed",
            debug_artifacts={"screenshot_path": "/tmp/debug.png"},
        )

    monkeypatch.setattr(verification_tool.verification_engine, "verify_action", fake_verify_action)

    result = await verification_tool.verify_action_result(
        timeout=1.0,
        debug_context={"agent": "test"},
    )

    assert result["success"] is False
    assert result["debug_artifacts"]["screenshot_path"] == "/tmp/debug.png"
    assert called["debug_context"] == {"agent": "test"}

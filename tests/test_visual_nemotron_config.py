from __future__ import annotations

import importlib
import tempfile
from pathlib import Path


def test_openrouter_vision_model_prefers_dedicated_env(monkeypatch):
    monkeypatch.setenv("VISUAL_MODEL", "gpt-5.4-2026-03-05")
    monkeypatch.setenv("VISUAL_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENROUTER_VISION_MODEL", "qwen/qwen2.5-vl-72b-instruct")

    import agent.visual_nemotron_agent_v4 as visual_v4

    visual_v4 = importlib.reload(visual_v4)

    assert visual_v4.OPENROUTER_VISION_MODEL == "qwen/qwen2.5-vl-72b-instruct"


def test_openrouter_vision_model_does_not_fall_back_to_openai_visual_model(monkeypatch):
    monkeypatch.setenv("VISUAL_MODEL", "gpt-5.4-2026-03-05")
    monkeypatch.setenv("VISUAL_MODEL_PROVIDER", "openai")
    monkeypatch.delenv("OPENROUTER_VISION_MODEL", raising=False)
    monkeypatch.delenv("VISUAL_OPENROUTER_VISION_MODEL", raising=False)

    import agent.visual_nemotron_agent_v4 as visual_v4

    visual_v4 = importlib.reload(visual_v4)

    assert visual_v4.OPENROUTER_VISION_MODEL != "gpt-5.4-2026-03-05"


def test_visual_v4_temp_paths_use_system_tempdir(monkeypatch):
    import agent.visual_nemotron_agent_v4 as visual_v4

    visual_v4 = importlib.reload(visual_v4)

    temp_path = visual_v4._visual_v4_temp_path("sample.png")
    expected_root = Path(tempfile.gettempdir()) / "timus_visual_v4"
    assert temp_path == expected_root / "sample.png"
    assert visual_v4._ensure_visual_v4_debug_dir() == expected_root / "debug"

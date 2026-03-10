from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_open_application_blocks_in_service_context(monkeypatch):
    from tools.application_launcher.tool import open_application

    monkeypatch.setenv("SYSTEMD_EXEC_PID", "123")

    result = await open_application("vscode")

    assert result["status"] == "blocked"
    assert "Service-Kontext" in result["reason"]


@pytest.mark.asyncio
async def test_visual_navigate_blocks_external_browser_open_in_service(monkeypatch):
    monkeypatch.setenv("SYSTEMD_EXEC_PID", "123")

    import agent.visual_nemotron_agent_v4 as visual_v4

    visual_v4 = importlib.reload(visual_v4)
    controller = visual_v4.DesktopController.__new__(visual_v4.DesktopController)
    controller.mcp = SimpleNamespace()

    popen = MagicMock()
    monkeypatch.setattr(visual_v4.subprocess, "Popen", popen)

    done, error = await controller.execute_action({"action": "navigate", "url": "https://booking.com"})

    assert done is False
    assert error is not None
    assert "Service-Kontext" in error
    popen.assert_not_called()

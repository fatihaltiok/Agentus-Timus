from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_open_application_blocks_in_service_context(monkeypatch):
    from tools.application_launcher.tool import open_application

    monkeypatch.setenv("SYSTEMD_EXEC_PID", "123")

    result = await open_application("vscode")

    assert result["status"] == "blocked"
    assert "Service-Kontext" in result["reason"]


@pytest.mark.asyncio
async def test_visual_navigate_uses_internal_browser_in_service(monkeypatch):
    monkeypatch.setenv("SYSTEMD_EXEC_PID", "123")

    import agent.visual_nemotron_agent_v4 as visual_v4

    visual_v4 = importlib.reload(visual_v4)
    controller = visual_v4.DesktopController.__new__(visual_v4.DesktopController)
    controller.mcp = SimpleNamespace(
        call_tool=AsyncMock(return_value={"success": True, "method": "dom"}),
    )
    controller.last_navigation_result = None

    popen = MagicMock()
    monkeypatch.setattr(visual_v4.subprocess, "Popen", popen)

    done, error = await controller.execute_action({"action": "navigate", "url": "https://booking.com"})

    assert done is False
    assert error is None
    controller.mcp.call_tool.assert_awaited_once_with(
        "open_url",
        {"url": "https://booking.com", "session_id": "visual_nemotron"},
    )
    popen.assert_not_called()

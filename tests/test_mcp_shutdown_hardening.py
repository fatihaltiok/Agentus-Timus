import asyncio

import pytest


@pytest.mark.asyncio
async def test_shutdown_async_step_returns_true_for_fast_awaitable():
    from server.mcp_server import _shutdown_async_step

    async def _quick():
        return "ok"

    result = await _shutdown_async_step("quick", _quick(), timeout_s=0.5)

    assert result is True


@pytest.mark.asyncio
async def test_shutdown_async_step_returns_false_on_timeout():
    from server.mcp_server import _shutdown_async_step

    async def _slow():
        await asyncio.sleep(0.8)

    result = await _shutdown_async_step("slow", _slow(), timeout_s=0.5)

    assert result is False


@pytest.mark.asyncio
async def test_cancel_background_task_cancels_running_task():
    from server.mcp_server import _cancel_background_task

    task = asyncio.create_task(asyncio.sleep(10))
    result = await _cancel_background_task("sleepy", task, timeout_s=0.2)

    assert result is True
    assert task.cancelled()


def test_canvas_ui_auto_open_disabled_by_default_under_systemd(monkeypatch):
    from server.mcp_server import _should_auto_open_canvas_ui

    monkeypatch.delenv("TIMUS_CANVAS_AUTO_OPEN", raising=False)
    monkeypatch.setenv("SYSTEMD_EXEC_PID", "123")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    assert _should_auto_open_canvas_ui() is False


def test_canvas_ui_auto_open_respects_explicit_override(monkeypatch):
    from server.mcp_server import _should_auto_open_canvas_ui

    monkeypatch.setenv("TIMUS_CANVAS_AUTO_OPEN", "true")
    monkeypatch.setenv("SYSTEMD_EXEC_PID", "123")

    assert _should_auto_open_canvas_ui() is False


def test_canvas_ui_url_normalizes_unspecified_bind_host(monkeypatch):
    from server.mcp_server import _canvas_ui_url

    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "5000")

    assert _canvas_ui_url() == "http://127.0.0.1:5000/canvas/ui"

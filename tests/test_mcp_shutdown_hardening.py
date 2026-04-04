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


@pytest.mark.asyncio
async def test_await_sse_queue_item_returns_data_when_available():
    from server.mcp_server import _await_sse_queue_item

    queue: asyncio.Queue[str] = asyncio.Queue()
    shutdown_event = asyncio.Event()
    await queue.put('{"type":"chat_reply"}')

    kind, payload = await _await_sse_queue_item(queue, shutdown_event, timeout_s=0.2)

    assert kind == "data"
    assert payload == '{"type":"chat_reply"}'


@pytest.mark.asyncio
async def test_await_sse_queue_item_returns_shutdown_when_server_is_stopping():
    from server.mcp_server import _await_sse_queue_item

    queue: asyncio.Queue[str] = asyncio.Queue()
    shutdown_event = asyncio.Event()
    shutdown_event.set()

    kind, payload = await _await_sse_queue_item(queue, shutdown_event, timeout_s=0.2)

    assert kind == "shutdown"
    assert payload is None


def test_health_payload_exposes_lifecycle_and_warmup_state():
    from server.mcp_server import app, _build_health_payload, _set_app_mcp_lifecycle

    app.state.inception = {
        "registered": True,
        "env_url": "https://api.inceptionlabs.ai/v1",
        "health": {"ok": None, "detail": "not_checked_yet"},
    }
    _set_app_mcp_lifecycle(
        app,
        phase="warmup",
        status="healthy",
        ready=True,
        warmup_pending=True,
        transient=False,
        warmups={"inception_health": {"ok": None, "detail": "queued"}},
    )

    payload = _build_health_payload(app)

    assert payload["status"] == "healthy"
    assert payload["ready"] is True
    assert payload["warmup_pending"] is True
    assert payload["transient"] is False
    assert payload["lifecycle"]["phase"] == "warmup"
    assert payload["lifecycle"]["warmups"]["inception_health"]["detail"] == "queued"


def test_sse_connection_ttl_has_safe_minimum(monkeypatch):
    from server.mcp_server import _sse_connection_ttl_sec

    monkeypatch.delenv("TIMUS_SSE_CONNECTION_TTL_SEC", raising=False)
    assert _sse_connection_ttl_sec() == 0.0

    monkeypatch.setenv("TIMUS_SSE_CONNECTION_TTL_SEC", "1")
    assert _sse_connection_ttl_sec() == 60.0

    monkeypatch.setenv("TIMUS_SSE_CONNECTION_TTL_SEC", "90")
    assert _sse_connection_ttl_sec() == 90.0

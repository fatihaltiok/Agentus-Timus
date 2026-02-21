import pytest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.mark.asyncio
async def test_persistent_context_manager_exposes_viewport_and_dpr(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMUS_BROWSER_BACKEND", "mock")
    monkeypatch.setenv("BROWSER_VIEWPORT_WIDTH", "1440")
    monkeypatch.setenv("BROWSER_VIEWPORT_HEIGHT", "900")
    monkeypatch.setenv("BROWSER_DEVICE_SCALE_FACTOR", "1.75")

    from tools.browser_tool.persistent_context import PersistentContextManager

    manager = PersistentContextManager(base_storage_dir=tmp_path)
    assert await manager.initialize() is True
    await manager.get_or_create_context("m2_dpr")

    status = manager.get_status()
    coordinate_context = status["coordinate_context"]
    assert coordinate_context["viewport"]["width"] == 1440
    assert coordinate_context["viewport"]["height"] == 900
    assert coordinate_context["device_scale_factor"] == 1.75

    await manager.shutdown()


@pytest.mark.asyncio
async def test_browser_session_status_propagates_coordinate_context(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMUS_BROWSER_BACKEND", "mock")
    monkeypatch.setenv("BROWSER_VIEWPORT_WIDTH", "1366")
    monkeypatch.setenv("BROWSER_VIEWPORT_HEIGHT", "768")
    monkeypatch.setenv("BROWSER_DEVICE_SCALE_FACTOR", "1.25")

    from tools.browser_tool.persistent_context import PersistentContextManager
    from tools.browser_tool import tool as browser_tool
    import tools.shared_context as shared_context

    manager = PersistentContextManager(base_storage_dir=tmp_path)
    await manager.initialize()
    shared_context.browser_context_manager = manager

    result = await browser_tool.browser_session_status()
    assert result["status"] == "ok"
    assert result["coordinate_context"]["viewport"]["width"] == 1366
    assert result["coordinate_context"]["viewport"]["height"] == 768
    assert result["coordinate_context"]["device_scale_factor"] == 1.25

    await manager.shutdown()
    shared_context.browser_context_manager = None

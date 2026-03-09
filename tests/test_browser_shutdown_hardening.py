import pytest


@pytest.mark.asyncio
async def test_shutdown_browser_tool_closes_legacy_and_shared_manager(monkeypatch):
    from tools.browser_tool import tool as browser_tool
    import tools.shared_context as shared_context

    events: list[str] = []

    class _FakeLegacyManager:
        is_initialized = True

        async def close(self):
            events.append("legacy_close")
            self.is_initialized = False

    class _FakeSharedManager:
        async def shutdown(self):
            events.append("shared_shutdown")

    monkeypatch.setattr(browser_tool, "browser_session_manager", _FakeLegacyManager())
    shared_context.browser_context_manager = _FakeSharedManager()

    await browser_tool.shutdown_browser_tool()

    assert events == ["legacy_close", "shared_shutdown"]
    assert shared_context.browser_context_manager is None


@pytest.mark.asyncio
async def test_click_by_selector_uses_shared_context_manager(monkeypatch):
    from tools.browser_tool import tool as browser_tool

    class _FakeElement:
        async def scroll_into_view_if_needed(self, timeout=5000):
            return None

        async def click(self, timeout=5000):
            return None

    class _FakePage:
        url = "https://example.com"

        async def query_selector(self, selector):
            assert selector == "#submit"
            return _FakeElement()

        async def wait_for_load_state(self, state, timeout=15000):
            return None

        async def title(self):
            return "Example"

    called = {"ensure": 0, "legacy_init": 0}

    async def _fake_ensure(session_id="default"):
        called["ensure"] += 1
        return _FakePage()

    async def _unexpected_init():
        called["legacy_init"] += 1
        raise AssertionError("legacy browser manager should not be initialized")

    monkeypatch.setattr(browser_tool, "ensure_browser_initialized", _fake_ensure)
    monkeypatch.setattr(browser_tool.browser_session_manager, "initialize", _unexpected_init)

    result = await browser_tool.click_by_selector("#submit")

    assert result["status"] == "clicked_by_selector"
    assert called["ensure"] == 1
    assert called["legacy_init"] == 0

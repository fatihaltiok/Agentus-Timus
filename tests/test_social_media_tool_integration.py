import ast
import importlib
from pathlib import Path

import httpx
import pytest


def test_social_media_tool_module_is_registered_in_mcp_loader():
    mcp_server_path = Path("server/mcp_server.py")
    source = mcp_server_path.read_text(encoding="utf-8")
    module = ast.parse(source)

    tool_modules = None
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TOOL_MODULES":
                    if isinstance(node.value, ast.List):
                        tool_modules = [
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        ]
                    break
        if tool_modules is not None:
            break

    assert tool_modules is not None, "TOOL_MODULES assignment not found in server/mcp_server.py"
    assert "tools.social_media_tool.tool" in tool_modules


def test_executor_capabilities_expose_social_media_tools():
    from agent.base_agent import AGENT_CAPABILITY_MAP
    from tools.tool_registry_v2 import registry_v2

    module = importlib.import_module("tools.social_media_tool.tool")
    importlib.reload(module)

    names = {tool.name for tool in registry_v2.get_tools_for_agent(AGENT_CAPABILITY_MAP["executor"])}
    assert "fetch_social_media" in names
    assert "fetch_page_with_js" in names


@pytest.mark.asyncio
async def test_deep_research_social_domain_uses_shared_scrapingant_adapter(monkeypatch):
    from tools.deep_research import tool as dr_tool

    called = {}

    async def fake_fetch(url: str, **kwargs):
        called["url"] = url
        called["kwargs"] = kwargs
        return {
            "status": "success",
            "content": "social content",
            "platform": "twitter",
            "url": url,
            "char_count": 14,
        }

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("raw httpx path should not be used for social-media domains")

    monkeypatch.setattr(dr_tool, "fetch_page_text_via_scrapingant", fake_fetch)
    monkeypatch.setattr(dr_tool.httpx, "AsyncClient", UnexpectedClient)

    result = await dr_tool._fetch_page_content("https://x.com/example/status/1")

    assert result == "social content"
    assert called["url"] == "https://x.com/example/status/1"
    assert called["kwargs"]["max_chars"] == 12000


@pytest.mark.asyncio
async def test_deep_research_http_403_uses_shared_scrapingant_fallback(monkeypatch):
    from tools.deep_research import tool as dr_tool

    called = {}

    async def fake_fetch(url: str, **kwargs):
        called["url"] = url
        return {
            "status": "success",
            "content": "fallback content",
            "platform": "unknown",
            "url": url,
            "char_count": 16,
        }

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            request = httpx.Request("GET", url)
            response = httpx.Response(403, request=request)
            raise httpx.HTTPStatusError("403", request=request, response=response)

    monkeypatch.setattr(dr_tool, "fetch_page_text_via_scrapingant", fake_fetch)
    monkeypatch.setattr(dr_tool, "get_scrapingant_api_key", lambda: "test-key")
    monkeypatch.setattr(dr_tool.httpx, "AsyncClient", lambda *args, **kwargs: FailingClient())

    result = await dr_tool._fetch_page_content("https://example.com/protected")

    assert result == "fallback content"
    assert called["url"] == "https://example.com/protected"


@pytest.mark.asyncio
async def test_scrapingant_client_uses_documented_v2_query_params(monkeypatch):
    from tools.social_media_tool import client as sa_client

    captured = {}

    class FakeResponse:
        text = "<html><body><main>Rendered content</main></body></html>"

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["client_timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = dict(params or {})
            return FakeResponse()

    monkeypatch.setattr(sa_client, "get_scrapingant_api_key", lambda: "test-key")
    monkeypatch.setattr(sa_client.httpx, "AsyncClient", FakeClient)

    result = await sa_client.fetch_page_text_via_scrapingant(
        "https://x.com/example/status/1",
        render_js=True,
        timeout_seconds=45.0,
        max_chars=500,
    )

    assert result["status"] == "success"
    assert captured["url"] == sa_client.SCRAPINGANT_BASE_URL
    assert captured["params"]["url"] == "https://x.com/example/status/1"
    assert captured["params"]["x-api-key"] == "test-key"
    assert captured["params"]["browser"] == "true"
    assert captured["params"]["proxy_type"] == "residential"
    assert captured["params"]["timeout"] == "45"
    assert captured["params"]["wait_for_selector"] == 'article, [data-testid="tweet"], main article'
    assert "render_js" not in captured["params"]
    assert "return_page_source" not in captured["params"]


@pytest.mark.asyncio
async def test_scrapingant_client_returns_auth_required_for_detected_x_login_wall(monkeypatch):
    from tools.social_media_tool import client as sa_client

    class FakeResponse:
        text = """
        <html>
          <body>
            <main>
              <h1>Happening now</h1>
              <a href="/i/flow/login">Sign in to X</a>
              <div>Join X today</div>
            </main>
          </body>
        </html>
        """

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(sa_client, "get_scrapingant_api_key", lambda: "test-key")
    monkeypatch.setattr(sa_client.httpx, "AsyncClient", lambda *args, **kwargs: FakeClient())

    result = await sa_client.fetch_page_text_via_scrapingant(
        "https://x.com/example/status/1",
        render_js=True,
        timeout_seconds=45.0,
        max_chars=500,
    )

    assert result["status"] == "auth_required"
    assert result["auth_required"] is True
    assert result["workflow_id"].startswith("wf_")
    assert result["service"] == "x"
    assert result["reason"] == "login_wall"
    assert "Login-Zugang" in result["user_action_required"]

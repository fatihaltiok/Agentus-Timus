from __future__ import annotations

import pytest

from tools.deep_research.image_collector import ImageCollector


@pytest.mark.asyncio
async def test_image_collector_accepts_brave_image_url_without_file_extension(monkeypatch):
    async def fake_call_tool_internal(name: str, params: dict[str, object]):
        assert name == "search_images"
        return [
            {
                "image_url": "https://imgs.search.brave.com/rs:fit:860:0:0/g:ce/example",
                "thumbnail_url": "https://imgs.search.brave.com/thumb",
                "source_provider": "brave",
            }
        ]

    monkeypatch.setattr("tools.deep_research.image_collector.call_tool_internal", fake_call_tool_internal)

    collector = ImageCollector()

    result = await collector._find_web_image("agentic ai")

    assert result == "https://imgs.search.brave.com/rs:fit:860:0:0/g:ce/example"

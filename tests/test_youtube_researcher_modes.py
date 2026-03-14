from __future__ import annotations

import pytest

from tools.deep_research.youtube_researcher import YouTubeResearcher


@pytest.mark.asyncio
async def test_youtube_researcher_uses_live_mode_for_search_and_standard_mode_for_subtitles(monkeypatch):
    calls = []

    async def fake_call_tool_internal(name, params):
        calls.append((name, dict(params)))
        if name == "search_youtube":
            return [{"video_id": "vid-1", "title": "Demo", "url": "https://youtube.com/watch?v=vid-1"}]
        if name == "get_youtube_subtitles":
            return {"video_id": "vid-1", "full_text": "a" * 200, "items": [{"text": "demo"}]}
        if name == "get_youtube_video_info":
            return {"video_id": "vid-1", "title": "Demo", "description": "Kurzbeschreibung"}
        raise AssertionError(f"Unexpected tool call: {name}")

    async def fake_analyze_text(self, text, query):
        return {"facts": ["fact"], "key_quote": "quote", "relevance": 8}

    async def fake_analyze_video_with_qwen(self, video_id, query):
        return {}

    async def fake_analyze_thumbnail(self, thumbnail_url, query):
        return {}

    def fake_add_to_session(self, session, video, text_facts, visual_info):
        return None

    monkeypatch.setattr("tools.deep_research.youtube_researcher.call_tool_internal", fake_call_tool_internal)
    monkeypatch.setattr(YouTubeResearcher, "_analyze_text", fake_analyze_text)
    monkeypatch.setattr(YouTubeResearcher, "_analyze_video_with_qwen", fake_analyze_video_with_qwen)
    monkeypatch.setattr(YouTubeResearcher, "_analyze_thumbnail", fake_analyze_thumbnail)
    monkeypatch.setattr(YouTubeResearcher, "_add_to_session", fake_add_to_session)

    researcher = YouTubeResearcher()
    session = type("Session", (), {})()

    analyzed = await researcher.research_topic_on_youtube("agentic ai", session, max_videos=1)

    assert analyzed == 1
    assert any(name == "search_youtube" and params.get("mode") == "live" for name, params in calls)
    assert any(name == "get_youtube_subtitles" and params.get("mode") == "standard" for name, params in calls)
    assert any(name == "get_youtube_video_info" and params.get("mode") == "live" for name, params in calls)

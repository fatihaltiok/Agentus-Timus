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

    async def fake_analyze_text(self, text, query, chunk_index=None, total_chunks=None):
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


def test_chunk_transcript_items_covers_all_segments():
    items = [
        {"text": f"segment-{idx}-" + ("abc " * 18)}
        for idx in range(8)
    ]

    chunks = YouTubeResearcher._chunk_transcript_items(
        items,
        max_chars=120,
        overlap_chars=15,
        max_chunks=12,
    )

    assert len(chunks) >= 2
    joined = "\n".join(chunks)
    for idx in range(8):
        assert f"segment-{idx}-" in joined


@pytest.mark.asyncio
async def test_youtube_researcher_chunks_long_transcript_and_synthesizes(monkeypatch):
    chunk_calls = []
    captured = {}

    async def fake_call_tool_internal(name, params):
        if name == "search_youtube":
            return [{"video_id": "vid-1", "title": "Demo", "url": "https://youtube.com/watch?v=vid-1"}]
        if name == "get_youtube_subtitles":
            items = [
                {"text": f"segment-{idx}-" + ("x" * 220)}
                for idx in range(40)
            ]
            return {
                "video_id": "vid-1",
                "full_text": " ".join(item["text"] for item in items),
                "items": items,
            }
        if name == "get_youtube_video_info":
            return {"video_id": "vid-1", "title": "Demo", "description": "Kurzbeschreibung"}
        raise AssertionError(f"Unexpected tool call: {name}")

    async def fake_analyze_text(self, text, query, chunk_index=None, total_chunks=None):
        chunk_calls.append((chunk_index, total_chunks, text))
        return {
            "facts": [f"fact-{chunk_index}"],
            "key_quote": f"quote-{chunk_index}",
            "relevance": 7,
        }

    async def fake_synthesize_chunk_analyses(self, chunk_results, query):
        assert len(chunk_results) >= 2
        return {
            "facts": ["combined fact"],
            "key_quote": "combined quote",
            "relevance": 9,
        }

    async def fake_analyze_video_with_qwen(self, video_id, query):
        return {}

    async def fake_analyze_thumbnail(self, thumbnail_url, query):
        return {}

    def fake_add_to_session(self, session, video, text_facts, visual_info):
        captured["text_facts"] = text_facts
        captured["visual_info"] = visual_info

    monkeypatch.setattr("tools.deep_research.youtube_researcher.call_tool_internal", fake_call_tool_internal)
    monkeypatch.setattr(YouTubeResearcher, "_analyze_text", fake_analyze_text)
    monkeypatch.setattr(YouTubeResearcher, "_synthesize_chunk_analyses", fake_synthesize_chunk_analyses)
    monkeypatch.setattr(YouTubeResearcher, "_analyze_video_with_qwen", fake_analyze_video_with_qwen)
    monkeypatch.setattr(YouTubeResearcher, "_analyze_thumbnail", fake_analyze_thumbnail)
    monkeypatch.setattr(YouTubeResearcher, "_add_to_session", fake_add_to_session)

    researcher = YouTubeResearcher()
    session = type("Session", (), {})()

    analyzed = await researcher.research_topic_on_youtube("agentic ai", session, max_videos=1)

    assert analyzed == 1
    assert len(chunk_calls) >= 2
    assert captured["text_facts"]["facts"] == ["combined fact"]
    assert captured["visual_info"]["transcript_segments"] == 40
    assert captured["visual_info"]["transcript_language"] == "de"

from __future__ import annotations

import pytest

from tools.search_tool import tool as search_tool_module


@pytest.mark.asyncio
async def test_get_youtube_subtitles_prefers_serpapi_when_key_present(monkeypatch):
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_USER", None)
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_PASS", None)

    captured = {}

    def fake_serpapi(params, timeout=45):
        captured["params"] = dict(params)
        return {
            "transcript": [
                {"snippet": "Hallo Welt", "start_ms": 0, "end_ms": 1500, "start_time_text": "0:00"},
                {"snippet": "zweites Segment", "start_ms": 1500, "end_ms": 3200, "start_time_text": "0:01"},
            ],
            "available_transcripts": [{"language": "German"}],
            "chapters": [{"title": "Intro"}],
        }

    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)

    result = await search_tool_module.get_youtube_subtitles("abc123", language_code="de", mode="live")

    assert result["video_id"] == "abc123"
    assert result["source_provider"] == "serpapi"
    assert len(result["items"]) == 2
    assert result["items"][0]["text"] == "Hallo Welt"
    assert "Hallo Welt zweites Segment" in result["full_text"]
    assert captured["params"]["engine"] == "youtube_video_transcript"
    assert captured["params"]["language_code"] == "de"


@pytest.mark.asyncio
async def test_get_youtube_subtitles_keeps_long_serpapi_transcript_untruncated(monkeypatch):
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_USER", None)
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_PASS", None)

    long_segments = [
        {"snippet": f"segment-{idx}-" + ("x" * 220), "start_ms": idx * 1000, "end_ms": idx * 1000 + 900}
        for idx in range(45)
    ]

    def fake_serpapi(params, timeout=45):
        return {"transcript": long_segments}

    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)

    result = await search_tool_module.get_youtube_subtitles("abc123", language_code="de", mode="live")

    assert result["source_provider"] == "serpapi"
    assert len(result["items"]) == 45
    assert len(result["full_text"]) > 8000
    assert "segment-44-" in result["full_text"]


@pytest.mark.asyncio
async def test_get_youtube_subtitles_falls_back_to_dataforseo_when_serpapi_yields_no_transcript(monkeypatch):
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_USER", "dfs-user")
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_PASS", "dfs-pass")

    def fake_serpapi(params, timeout=45):
        return {"transcript": []}

    def fake_dataforseo(endpoint: str, payload: list[dict]):
        return {
            "tasks": [{
                "status_code": 20000,
                "result": [{
                    "items": [
                        {"text": "Fallback eins", "start_time": 0, "end_time": 1},
                        {"text": "Fallback zwei", "start_time": 1, "end_time": 2},
                    ]
                }],
            }]
        }

    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)
    monkeypatch.setattr(search_tool_module, "_call_dataforseo_youtube", fake_dataforseo)

    result = await search_tool_module.get_youtube_subtitles("abc123", language_code="de", mode="live")

    assert result["source_provider"] == "dataforseo"
    assert len(result["items"]) == 2
    assert result["full_text"].startswith("Fallback eins")


@pytest.mark.asyncio
async def test_get_youtube_video_info_uses_serpapi_and_normalizes(monkeypatch):
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_USER", None)
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_PASS", None)

    def fake_serpapi(params, timeout=45):
        return {
            "video_results": {
                "title": "Demo Video",
                "link": "https://www.youtube.com/watch?v=abc123",
                "description": "Ein Testvideo",
                "thumbnail": "https://img.youtube.com/demo.jpg",
                "channel": {"name": "Demo Channel", "link": "https://www.youtube.com/@demo"},
                "views": 12345,
                "duration": "12:34",
            },
            "chapters": [{"title": "Kapitel 1"}],
            "comments": [{"author": "A", "content": "Starker Punkt"}],
            "related_videos": [{"id": "rel1", "title": "Weiteres Video", "link": "https://www.youtube.com/watch?v=rel1"}],
        }

    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)

    result = await search_tool_module.get_youtube_video_info("abc123", language_code="de", mode="live")

    assert result["video_id"] == "abc123"
    assert result["source_provider"] == "serpapi"
    assert result["title"] == "Demo Video"
    assert result["channel_name"] == "Demo Channel"
    assert result["comments"][0]["text"] == "Starker Punkt"
    assert result["related_videos"][0]["video_id"] == "rel1"


@pytest.mark.asyncio
async def test_get_youtube_video_info_accepts_serpapi_mode_alias_for_dataforseo_fallback(monkeypatch):
    monkeypatch.setattr(search_tool_module, "SERPAPI_API_KEY", "serp-test-key")
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_USER", "dfs-user")
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_PASS", "dfs-pass")

    def fake_serpapi(params, timeout=45):
        raise RuntimeError("serpapi temporary failure")

    def fake_dataforseo(endpoint: str, payload: list[dict]):
        return {
            "tasks": [{
                "status_code": 20000,
                "result": [{
                    "items": [{
                        "title": "Fallback Video",
                        "description": "Beschreibung aus DataForSEO",
                        "channel_name": "Fallback Channel",
                        "url": "https://www.youtube.com/watch?v=abc123",
                    }]
                }],
            }]
        }

    monkeypatch.setattr(search_tool_module, "_call_serpapi_json", fake_serpapi)
    monkeypatch.setattr(search_tool_module, "_call_dataforseo_youtube", fake_dataforseo)

    result = await search_tool_module.get_youtube_video_info("abc123", language_code="de", mode="serpapi")

    assert result["video_id"] == "abc123"
    assert result["source_provider"] == "dataforseo"
    assert result["title"] == "Fallback Video"

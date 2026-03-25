from __future__ import annotations

import deal
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tools.search_tool.tool import (
    DataForSEORetrievalMode,
    YouTubeRequestSpec,
    YouTubeRequestType,
    _call_dataforseo_youtube_standard,
    build_youtube_request,
    build_youtube_task_get_endpoint,
    build_youtube_subtitles_payload,
    parse_dataforseo_mode,
    validate_youtube_request,
)


@deal.pre(lambda query, _: bool(str(query).strip()))
@deal.post(lambda r: r.request_type == YouTubeRequestType.ORGANIC_SEARCH)
def organic_spec_contract(query: str, language_code: str) -> YouTubeRequestSpec:
    return validate_youtube_request(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.ORGANIC_SEARCH,
            query=query,
            language_code=language_code,
            device="desktop",
            device_os="windows",
        )
    )


@deal.pre(lambda video_id: bool(str(video_id).strip()))
@deal.post(lambda r: r[0].startswith("/v3/serp/youtube/"))
def subtitles_endpoint_contract(video_id: str) -> tuple[str, list[dict]]:
    return build_youtube_request(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.SUBTITLES,
            video_id=video_id,
            language_code="de",
            device="desktop",
            device_os="windows",
            mode=DataForSEORetrievalMode.LIVE,
        )
    )


def test_organic_search_requires_query():
    with pytest.raises(ValueError, match="erfordert query"):
        validate_youtube_request(YouTubeRequestSpec(request_type=YouTubeRequestType.ORGANIC_SEARCH))


def test_video_info_requires_video_id():
    with pytest.raises(ValueError, match="erfordert video_id"):
        validate_youtube_request(YouTubeRequestSpec(request_type=YouTubeRequestType.VIDEO_INFO))


def test_non_organic_requests_are_desktop_only():
    with pytest.raises(ValueError, match="desktop-only"):
        validate_youtube_request(
            YouTubeRequestSpec(
                request_type=YouTubeRequestType.SUBTITLES,
                video_id="abc123",
                device="mobile",
                device_os="android",
            )
        )


def test_organic_mobile_requires_mobile_os():
    with pytest.raises(ValueError, match="android oder ios"):
        validate_youtube_request(
            YouTubeRequestSpec(
                request_type=YouTubeRequestType.ORGANIC_SEARCH,
                query="agentic ai",
                device="mobile",
                device_os="windows",
            )
        )


def test_organic_request_defaults_location_from_language():
    spec = validate_youtube_request(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.ORGANIC_SEARCH,
            query="agentic ai",
            language_code="en",
        )
    )
    assert spec.location_code == 2840


def test_build_youtube_request_uses_separate_endpoint_for_subtitles():
    endpoint, payload = build_youtube_request(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.SUBTITLES,
            video_id="dQw4w9WgXcQ",
            language_code="de",
        )
    )
    assert endpoint == "/v3/serp/youtube/video_subtitles/live/advanced"
    assert payload == [{"video_id": "dQw4w9WgXcQ", "language_code": "de"}]


def test_build_youtube_request_standard_uses_task_post():
    endpoint, payload = build_youtube_request(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.ORGANIC_SEARCH,
            query="agentic ai",
            mode=DataForSEORetrievalMode.STANDARD,
        )
    )
    assert endpoint == "/v3/serp/youtube/organic/task_post"
    assert payload[0]["keyword"] == "agentic ai"
    assert payload[0]["depth"] >= 1


def test_build_youtube_request_live_omits_depth_for_organic_search():
    endpoint, payload = build_youtube_request(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.ORGANIC_SEARCH,
            query="agentic ai",
            max_results=5,
            mode=DataForSEORetrievalMode.LIVE,
        )
    )
    assert endpoint == "/v3/serp/youtube/organic/live/advanced"
    assert payload[0]["keyword"] == "agentic ai"
    assert "depth" not in payload[0]


def test_build_youtube_task_get_endpoint_is_advanced():
    endpoint = build_youtube_task_get_endpoint(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.SUBTITLES,
            video_id="abc123",
            mode=DataForSEORetrievalMode.STANDARD,
        ),
        "task-1",
    )
    assert endpoint == "/v3/serp/youtube/video_subtitles/task_get/advanced/task-1"


def test_subtitles_payload_never_contains_keyword():
    payload = build_youtube_subtitles_payload(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.SUBTITLES,
            video_id="dQw4w9WgXcQ",
            language_code="en",
        )
    )
    assert payload[0]["video_id"] == "dQw4w9WgXcQ"
    assert "keyword" not in payload[0]


def test_parse_dataforseo_mode_rejects_unknown():
    with pytest.raises(ValueError, match="Ungueltiger DataForSEO-Modus"):
        parse_dataforseo_mode("batch")


def test_parse_dataforseo_mode_accepts_serpapi_alias():
    assert parse_dataforseo_mode("serpapi") == DataForSEORetrievalMode.LIVE


def test_standard_youtube_call_polls_until_result(monkeypatch):
    calls = []

    def fake_call(method, endpoint, payload=None, timeout=45):
        calls.append((method, endpoint, payload))
        if endpoint.endswith("/task_post"):
            return {
                "status_code": 20000,
                "tasks": [{"id": "task-1", "status_code": 20000, "status_message": "Task Created"}],
            }
        return {
            "status_code": 20000,
            "tasks": [{
                "id": "task-1",
                "status_code": 20000,
                "status_message": "Ok",
                "result": [{"items": [{"video_id": "abc"}]}],
            }],
        }

    monkeypatch.setattr("tools.search_tool.tool._call_dataforseo_json", fake_call)

    data = _call_dataforseo_youtube_standard(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.ORGANIC_SEARCH,
            query="agentic ai",
            mode=DataForSEORetrievalMode.STANDARD,
        ),
        timeout=2,
        poll_interval=0,
    )

    assert data["tasks"][0]["result"][0]["items"][0]["video_id"] == "abc"
    assert calls[0][1] == "/v3/serp/youtube/organic/task_post"
    assert calls[1][1] == "/v3/serp/youtube/organic/task_get/advanced/task-1"


def test_standard_youtube_call_times_out(monkeypatch):
    def fake_call(method, endpoint, payload=None, timeout=45):
        if endpoint.endswith("/task_post"):
            return {
                "status_code": 20000,
                "tasks": [{"id": "task-1", "status_code": 20000, "status_message": "Task Created"}],
            }
        return {
            "status_code": 20000,
            "tasks": [{"id": "task-1", "status_code": 20000, "status_message": "Task in progress", "result": []}],
        }

    monkeypatch.setattr("tools.search_tool.tool._call_dataforseo_json", fake_call)

    with pytest.raises(TimeoutError, match="DataForSEO Standard-Task"):
        _call_dataforseo_youtube_standard(
            YouTubeRequestSpec(
                request_type=YouTubeRequestType.SUBTITLES,
                video_id="abc123",
                mode=DataForSEORetrievalMode.STANDARD,
            ),
            timeout=0.01,
            poll_interval=0,
        )


@given(
    video_id=st.text(min_size=1, max_size=20).filter(lambda s: s.strip() != ""),
    device_os=st.sampled_from(["windows", "macos"]),
)
@settings(max_examples=50, deadline=None)
def test_hypothesis_subtitles_request_always_stays_video_id_based(video_id: str, device_os: str):
    endpoint, payload = build_youtube_request(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.SUBTITLES,
            video_id=video_id,
            language_code="de",
            device="desktop",
            device_os=device_os,
        )
    )
    assert endpoint.endswith("/video_subtitles/live/advanced")
    assert payload[0]["video_id"] == video_id.strip()
    assert "keyword" not in payload[0]


@given(
    query=st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != ""),
    device=st.sampled_from(["desktop", "mobile"]),
    device_os=st.sampled_from(["windows", "macos", "android", "ios"]),
)
@settings(max_examples=80, deadline=None)
def test_hypothesis_organic_payload_never_contains_video_id(query: str, device: str, device_os: str):
    if device == "desktop" and device_os not in {"windows", "macos"}:
        with pytest.raises(ValueError):
            validate_youtube_request(
                YouTubeRequestSpec(
                    request_type=YouTubeRequestType.ORGANIC_SEARCH,
                    query=query,
                    device=device,
                    device_os=device_os,
                )
            )
        return
    if device == "mobile" and device_os not in {"android", "ios"}:
        with pytest.raises(ValueError):
            validate_youtube_request(
                YouTubeRequestSpec(
                    request_type=YouTubeRequestType.ORGANIC_SEARCH,
                    query=query,
                    device=device,
                    device_os=device_os,
                )
            )
        return
    endpoint, payload = build_youtube_request(
        YouTubeRequestSpec(
            request_type=YouTubeRequestType.ORGANIC_SEARCH,
            query=query,
            device=device,
            device_os=device_os,
        )
    )
    assert endpoint.endswith("/organic/live/advanced")
    assert payload[0]["keyword"] == query.strip()
    assert "video_id" not in payload[0]


@given(video_id=st.text(min_size=1, max_size=16).filter(lambda s: s.strip() != ""))
@settings(max_examples=50, deadline=None)
def test_hypothesis_non_organic_mobile_is_rejected(video_id: str):
    with pytest.raises(ValueError):
        validate_youtube_request(
            YouTubeRequestSpec(
                request_type=YouTubeRequestType.VIDEO_INFO,
                video_id=video_id,
                device="mobile",
                device_os="android",
            )
        )

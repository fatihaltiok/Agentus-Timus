import sys
from functools import lru_cache
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@lru_cache(maxsize=1)
def _research_agent_cls():
    from agent.agents.research import DeepResearchAgent
    return DeepResearchAgent


@lru_cache(maxsize=1)
def _youtube_location_code_fn():
    from tools.search_tool.tool import _youtube_location_code
    return _youtube_location_code


@pytest.mark.asyncio
async def test_research_agent_injects_session_id_before_report_call(monkeypatch):
    from agent.base_agent import BaseAgent
    DeepResearchAgent = _research_agent_cls()

    captured = {}

    async def _fake_call_tool(self, method: str, params: dict):
        captured["method"] = method
        captured["params"] = dict(params)
        return {"status": "success"}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = DeepResearchAgent.__new__(DeepResearchAgent)
    agent.current_session_id = "sess-report-42"

    await DeepResearchAgent._call_tool(
        agent,
        "generate_research_report",
        {"format": "markdown"},
    )

    assert captured["method"] == "generate_research_report"
    assert captured["params"]["session_id"] == "sess-report-42"


@pytest.mark.asyncio
async def test_research_agent_keeps_explicit_session_id(monkeypatch):
    from agent.base_agent import BaseAgent
    DeepResearchAgent = _research_agent_cls()

    captured = {}

    async def _fake_call_tool(self, method: str, params: dict):
        captured["params"] = dict(params)
        return {"status": "success"}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = DeepResearchAgent.__new__(DeepResearchAgent)
    agent.current_session_id = "sess-default"

    await DeepResearchAgent._call_tool(
        agent,
        "generate_research_report",
        {"format": "pdf", "session_id": "sess-explicit"},
    )

    assert captured["params"]["session_id"] == "sess-explicit"


@pytest.mark.asyncio
async def test_meta_reroutes_direct_deep_research_to_delegate(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    captured = {}

    async def _fake_call_tool(self, method: str, params: dict):
        captured["method"] = method
        captured["params"] = dict(params)
        return {"status": "success", "agent": "research"}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-77"

    result = await MetaAgent._call_tool(
        agent,
        "start_deep_research",
        {"query": "KI-Agenten in der Industrie", "focus_areas": ["ROI", "Praxis"]},
    )

    assert result["status"] == "success"
    assert captured["method"] == "delegate_to_agent"
    assert captured["params"]["agent_type"] == "research"
    assert captured["params"]["session_id"] == "sess-meta-77"
    assert "KI-Agenten in der Industrie" in captured["params"]["task"]


@pytest.mark.asyncio
async def test_search_youtube_adds_location_code(monkeypatch):
    from tools.search_tool import tool as search_tool_module

    captured = {}

    def _fake_call(endpoint: str, payload: list) -> dict:
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {
            "tasks": [{
                "status_code": 20000,
                "result": [{
                    "items": [{
                        "video_id": "abc123",
                        "title": "Demo",
                        "url": "https://www.youtube.com/watch?v=abc123",
                    }]
                }],
            }]
        }

    monkeypatch.setattr(search_tool_module, "DATAFORSEO_USER", "u")
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_PASS", "p")
    monkeypatch.setattr(search_tool_module, "_call_dataforseo_youtube", _fake_call)

    result = await search_tool_module.search_youtube("industrie 4.0", language_code="en")

    assert result[0]["video_id"] == "abc123"
    assert captured["endpoint"].endswith("/youtube/organic/live/advanced")
    assert captured["payload"][0]["location_code"] == 2840


@pytest.mark.asyncio
async def test_search_youtube_falls_back_to_live_when_standard_task_not_found(monkeypatch):
    from tools.search_tool import tool as search_tool_module

    calls = []

    def _fake_standard(spec, timeout=90, poll_interval=2.0):
        raise ValueError("DataForSEO Task nicht erfolgreich: Task Not Found.")

    def _fake_live(endpoint: str, payload: list) -> dict:
        calls.append((endpoint, payload))
        return {
            "tasks": [{
                "status_code": 20000,
                "result": [{
                    "items": [{
                        "type": "youtube_video",
                        "video_id": "fallback123",
                        "title": "Fallback Demo",
                        "url": "https://www.youtube.com/watch?v=fallback123",
                    }]
                }],
            }]
        }

    monkeypatch.setattr(search_tool_module, "DATAFORSEO_USER", "u")
    monkeypatch.setattr(search_tool_module, "DATAFORSEO_PASS", "p")
    monkeypatch.setattr(search_tool_module, "_call_dataforseo_youtube_standard", _fake_standard)
    monkeypatch.setattr(search_tool_module, "_call_dataforseo_youtube", _fake_live)

    result = await search_tool_module.search_youtube("industrie 4.0", mode="standard")

    assert result[0]["video_id"] == "fallback123"
    assert calls
    assert calls[0][0].endswith("/youtube/organic/live/advanced")


@pytest.mark.asyncio
async def test_hotkey_tool_presses_normalized_keys(monkeypatch):
    from tools.mouse_tool import tool as mouse_tool_module

    pressed = {}

    class _FakePyAutoGUI:
        FAILSAFE = True

        class FailSafeException(Exception):
            pass

        @staticmethod
        def size():
            return (1920, 1080)

        @staticmethod
        def position():
            return (120, 140)

        @staticmethod
        def moveTo(*args, **kwargs):
            return None

        @staticmethod
        def hotkey(*keys):
            pressed["keys"] = list(keys)

    monkeypatch.setattr(mouse_tool_module, "pyautogui", _FakePyAutoGUI)

    result = await mouse_tool_module.hotkey(["CTRL", "L"])

    assert result["status"] == "pressed"
    assert result["keys"] == ["ctrl", "l"]
    assert pressed["keys"] == ["ctrl", "l"]


@given(
    current=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
    provided=st.dictionaries(
        keys=st.sampled_from(["format", "session_id"]),
        values=st.text(min_size=1, max_size=20),
        max_size=2,
    ),
)
@settings(deadline=None, max_examples=100)
def test_hypothesis_effective_report_params_preserve_existing_session(current, provided):
    DeepResearchAgent = _research_agent_cls()
    result = DeepResearchAgent._effective_report_params(provided, current)
    if "session_id" in provided:
        assert result["session_id"] == provided["session_id"]
    elif current:
        assert result["session_id"] == current
    else:
        assert "session_id" not in result


@given(language_code=st.text(min_size=0, max_size=5))
@settings(deadline=None, max_examples=100)
def test_hypothesis_youtube_location_code_is_positive(language_code):
    assert _youtube_location_code_fn()(language_code) > 0

import sys
from pathlib import Path

import pytest


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def _build_executor_youtube_task(original_task: str) -> str:
    return "\n".join(
        [
            "# DELEGATION HANDOFF",
            "target_agent: executor",
            "goal: Ermittle lockere aktuelle YouTube-Treffer ohne Deep Research.",
            "expected_output: quick_summary, youtube_results",
            "success_signal: Stage 'youtube_quick_search' erfolgreich abgeschlossen",
            "constraints: folge_dem_rezept_und_vermeide_deep_research",
            "handoff_data:",
            "- task_type: youtube_light_research",
            "- recipe_id: youtube_light_research",
            "- stage_id: youtube_quick_search",
            f"- original_user_task: {original_task}",
            "- preferred_search_tool: search_youtube",
            "- search_mode: live",
            "- max_results: 5",
            "",
            "# TASK",
            "Ermittle lockere aktuelle YouTube-Treffer ohne Deep Research.",
        ]
    )


@pytest.mark.asyncio
async def test_executor_youtube_light_uses_tool_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer youtube_light_research nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "search_youtube"
        assert params["query"] == "trending deutschland"
        assert params["mode"] == "live"
        return [
            {
                "title": "Die wichtigsten YouTube-Trends heute",
                "channel_name": "Trend Radar",
                "views_count": 182300,
                "url": "https://www.youtube.com/watch?v=abc123",
            },
            {
                "title": "Neue Creator und Formate im Blick",
                "channel_name": "Creator Update",
                "views_count": 52300,
                "url": "https://www.youtube.com/watch?v=def456",
            },
        ]

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(agent, _build_executor_youtube_task("was gibts neues auf youtube"))

    assert "aktuellen Treffer" in result
    assert "Die wichtigsten YouTube-Trends heute" in result
    assert "Trend Radar" in result


@pytest.mark.asyncio
async def test_executor_youtube_light_extracts_topic_from_user_request(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    seen_queries: list[str] = []

    async def _fake_call_tool(self, method: str, params: dict):
        seen_queries.append(str(params["query"]))
        return [
            {
                "title": "OpenAI stellt neue Modelle vor",
                "channel_name": "AI Update",
                "views_count": 8700,
                "url": "https://www.youtube.com/watch?v=openai1",
            }
        ]

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_youtube_task("Schau mal was es auf YouTube zu OpenAI Neues gibt"),
    )

    assert seen_queries == ["openai"]
    assert "OpenAI stellt neue Modelle vor" in result


@pytest.mark.asyncio
async def test_executor_youtube_light_ignores_response_language_prefix(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    seen_queries: list[str] = []

    async def _fake_call_tool(self, method: str, params: dict):
        seen_queries.append(str(params["query"]))
        return [
            {
                "title": "YouTube Trends heute",
                "channel_name": "Trend Radar",
                "views_count": 4000,
                "url": "https://www.youtube.com/watch?v=trend1",
            }
        ]

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_youtube_task(
            "Antworte ausschliesslich auf Deutsch.\n\nNutzeranfrage:\nwas gibts neues auf youtube"
        ),
    )

    assert seen_queries == ["trending deutschland"]
    assert "YouTube Trends heute" in result


@pytest.mark.asyncio
async def test_executor_youtube_light_refuses_direct_video_fact_check(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_call_tool(self, method: str, params: dict):
        raise AssertionError("search_youtube darf fuer direkte Video-Faktenchecks nicht aufgerufen werden")

    monkeypatch.setattr(BaseAgent, "_call_tool", _unexpected_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_youtube_task(
            "https://youtu.be/j4jBGHv9Eow?is=7eXEJB7wHGDk0F_f schau mal ob da etwas wahres dran ist"
        ),
    )

    assert "konkreten YouTube-Video-Faktencheck" in result

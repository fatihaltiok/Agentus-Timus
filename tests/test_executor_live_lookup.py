import sys
from pathlib import Path

import pytest


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def _build_executor_live_lookup_task(original_task: str) -> str:
    return "\n".join(
        [
            "# DELEGATION HANDOFF",
            "target_agent: executor",
            "goal: Fuehre eine kompakte aktuelle Live-Recherche aus.",
            "expected_output: quick_summary, top_results, source_urls",
            "success_signal: Stage 'live_lookup_scan' erfolgreich abgeschlossen",
            "constraints: bleibe_kurz_und_vermeide_deep_research",
            "handoff_data:",
            "- task_type: simple_live_lookup",
            "- recipe_id: simple_live_lookup",
            "- stage_id: live_lookup_scan",
            f"- original_user_task: {original_task}",
            "",
            "# TASK",
            "Fuehre eine kompakte aktuelle Live-Recherche aus.",
        ]
    )


@pytest.mark.asyncio
async def test_executor_handles_simple_live_news_lookup_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    calls: list[str] = []

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer simple live lookup nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(method)
        if method == "search_news":
            assert "Wissenschaft" in params["query"] or "wissenschaft" in params["query"].lower()
            return [
                {
                    "title": "Nature: Neues AI-Labor fuer Materialforschung",
                    "url": "https://example.org/nature-ai-lab",
                    "snippet": "Forscher kombinieren Robotik und KI fuer schnellere Materialentdeckung.",
                    "domain": "example.org",
                },
                {
                    "title": "Max-Planck-Institut meldet neuen Protein-Benchmark",
                    "url": "https://example.org/mpi-benchmark",
                    "snippet": "Neue Auswertung vergleicht Multimodal-Modelle in der Molekularbiologie.",
                    "domain": "example.org",
                },
            ]
        assert method == "fetch_url"
        return {
            "status": "success",
            "url": params["url"],
            "title": "Nature: Neues AI-Labor fuer Materialforschung",
            "content": "Das Labor soll Materialsimulation, Robotik und automatische Experimente enger koppeln.",
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_live_lookup_task("Was gibt es Neues aus der Wissenschaft?"),
    )

    assert calls == ["search_news", "fetch_url"]
    assert "Wissenschaft" in result
    assert "Nature" in result
    assert "Direkt gepruefte Quelle" in result


def test_executor_keeps_generic_price_queries_out_of_llm_pricing_category():
    from agent.agents.executor import ExecutorAgent

    assert ExecutorAgent._infer_simple_live_lookup_category("was kostet benzin heute") == "web_lookup"
    assert ExecutorAgent._infer_simple_live_lookup_category("aktuelle llm preise input output") == "pricing"


@pytest.mark.asyncio
async def test_executor_uses_generic_web_lookup_for_non_llm_price_queries(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    calls: list[tuple[str, dict]] = []

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer generische Preis-Live-Lookups nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append((method, dict(params)))
        if method == "search_web":
            assert params["language_code"] == "de"
            assert "llm" not in params["query"].lower()
            assert "token" not in params["query"].lower()
            return [
                {
                    "title": "Benzinpreis heute in Deutschland",
                    "url": "https://example.org/benzinpreise",
                    "snippet": "Durchschnittspreise fuer Super E10 und Diesel.",
                    "domain": "example.org",
                }
            ]
        assert method == "fetch_url"
        return {
            "status": "success",
            "url": params["url"],
            "title": "Benzinpreis heute in Deutschland",
            "content": "Super E10 kostet im Schnitt 1,74 Euro pro Liter, Diesel 1,63 Euro pro Liter.",
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_live_lookup_task("schau im Internet nach den aktuellen benzin Preisen"),
    )

    assert calls[0][0] == "search_web"
    assert "Zu den aktuellen Preisen" not in result
    assert "Benzinpreis heute in Deutschland" in result


@pytest.mark.asyncio
async def test_executor_uses_live_location_for_local_place_lookup_without_explicit_nearby_phrase(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    calls: list[str] = []

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer lokalen simple live lookup nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(method)
        if method == "get_current_location_context":
            return {
                "status": "success",
                "data": {
                    "has_location": True,
                    "presence_status": "live",
                    "location": {
                        "display_name": "Offenbach am Main",
                        "locality": "Offenbach am Main",
                        "usable_for_context": True,
                        "presence_status": "live",
                        "latitude": 50.1002,
                        "longitude": 8.7788,
                    },
                },
            }
        assert method == "search_google_maps_places"
        assert params["query"] == "Cafes"
        return {
            "status": "success",
            "data": {
                "results": [
                    {
                        "title": "Cafe Morgenrot",
                        "distance_meters": 140,
                        "hours_summary": "Geoeffnet bis 19:00",
                        "rating": 4.5,
                        "reviews": 81,
                        "address": "Frankfurter Str. 10, Offenbach",
                    }
                ],
            },
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(agent, "Suche mir Cafes")

    assert calls == ["get_current_location_context", "search_google_maps_places"]
    assert "Cafe Morgenrot" in result
    assert "Offenbach" in result


@pytest.mark.asyncio
async def test_executor_extracts_prices_from_contextual_followup_source(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    calls: list[tuple[str, dict]] = []

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer contextual pricing followups nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append((method, dict(params)))
        assert method == "fetch_url"
        assert params["url"] == "https://www.byte.de/vergleich/llm"
        return {
            "status": "success",
            "url": params["url"],
            "title": "Alle KI-Modelle vergleichen – LLM Vergleich (2026)",
            "content": "\n".join(
                [
                    "Modell | Input-Preis | Output-Preis",
                    "GPT-5.4 mini | $0.75 / 1M input | $4.50 / 1M output",
                    "Claude Sonnet 4.6 | $3.00 / 1M input | $15.00 / 1M output",
                ]
            ),
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    task = "\n".join(
        [
            _build_executor_live_lookup_task("hole die preise heraus und liste sie mir aus"),
            "",
            "# FOLLOW-UP CONTEXT",
            "last_agent: meta",
            "recent_assistant_replies: Zu den aktuellen Preisen habe ich gerade diese Treffer gefunden: || Direkt gepruefte Quelle: - Alle KI-Modelle vergleichen – LLM Vergleich (2026) | https://www.byte.de/vergleich/llm",
            "topic_recall: Alle KI-Modelle vergleichen – LLM Vergleich (2026) | https://www.byte.de/vergleich/llm",
            "",
            "# CURRENT USER QUERY",
            "hole die preise heraus und liste sie mir aus",
        ]
    )
    result = await ExecutorAgent.run(agent, task)

    assert calls == [("fetch_url", {"url": "https://www.byte.de/vergleich/llm", "max_content_length": 6000, "timeout": 15})]
    assert "Preis-Tabelle" in result
    assert "| Anbieter | Modell | Input | Output | Cached |" in result
    assert "GPT-5.4 mini" in result
    assert "Anthropic" in result


@pytest.mark.asyncio
async def test_executor_renders_pricing_table_from_primary_source(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    calls: list[tuple[str, dict]] = []

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer pricing lookups nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append((method, dict(params)))
        if method == "search_web":
            assert params["language_code"] == "en"
            assert "llm" in params["query"].lower()
            return [
                {
                    "title": "Alle KI-Modelle vergleichen – LLM Vergleich (2026)",
                    "url": "https://www.byte.de/vergleich/llm",
                    "snippet": "Vergleiche die besten aktuellen LLMs anhand von Kosten und Scores.",
                    "domain": "www.byte.de",
                }
            ]
        assert method == "fetch_url"
        return {
            "status": "success",
            "url": params["url"],
            "title": "Alle KI-Modelle vergleichen – LLM Vergleich (2026)",
            "content": "\n".join(
                [
                    "Modell | Input | Output | Cached",
                    "GPT-5.4 mini | $0.75 / 1M | $4.50 / 1M | $0.075 / 1M",
                    "DeepSeek V3 | $0.27 / 1M | $1.10 / 1M | $0.07 / 1M",
                ]
            ),
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        _build_executor_live_lookup_task(
            "Erstelle mir eine Liste mit den aktuellen Preisen der besten LLMs und zeige mir dann die Tabelle"
        ),
    )

    assert calls[0][0] == "search_web"
    assert calls[1] == (
        "fetch_url",
        {"url": "https://www.byte.de/vergleich/llm", "max_content_length": 6000, "timeout": 15},
    )
    assert "| Anbieter | Modell | Input | Output | Cached |" in result
    assert "OpenAI" in result
    assert "DeepSeek" in result


@pytest.mark.asyncio
async def test_executor_creates_txt_artifact_from_contextual_pricing_source(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    calls: list[tuple[str, dict]] = []

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer pricing export followups nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append((method, dict(params)))
        if method == "fetch_url":
            return {
                "status": "success",
                "url": params["url"],
                "title": "Alle KI-Modelle vergleichen – LLM Vergleich (2026)",
                "content": "\n".join(
                    [
                        "Modell | Input | Output | Cached",
                        "GPT-5.4 mini | $0.75 / 1M | $4.50 / 1M | $0.075 / 1M",
                        "DeepSeek V3 | $0.27 / 1M | $1.10 / 1M | $0.07 / 1M",
                    ]
                ),
            }
        assert method == "create_txt"
        assert params["title"] == "LLM_Preise_Vergleich"
        assert "GPT-5.4 mini" in params["content"]
        assert "DeepSeek V3" in params["content"]
        return {
            "status": "success",
            "path": "results/20260326_124500_LLM_Preise_Vergleich.txt",
            "filename": "20260326_124500_LLM_Preise_Vergleich.txt",
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    task = "\n".join(
        [
            _build_executor_live_lookup_task("erstelle eine txt datei mit den besten llms und ihren preisen"),
            "",
            "# FOLLOW-UP CONTEXT",
            "last_agent: meta",
            "recent_assistant_replies: Zu den aktuellen Preisen habe ich gerade diese Treffer gefunden: || Direkt gepruefte Quelle: - Alle KI-Modelle vergleichen – LLM Vergleich (2026) | https://www.byte.de/vergleich/llm",
            "topic_recall: Alle KI-Modelle vergleichen – LLM Vergleich (2026) | https://www.byte.de/vergleich/llm",
            "",
            "# CURRENT USER QUERY",
            "erstelle eine txt datei mit den besten llms und ihren preisen",
        ]
    )
    result = await ExecutorAgent.run(agent, task)

    assert calls[0] == (
        "fetch_url",
        {"url": "https://www.byte.de/vergleich/llm", "max_content_length": 6000, "timeout": 15},
    )
    assert calls[1][0] == "create_txt"
    assert calls[1][1]["title"] == "LLM_Preise_Vergleich"
    assert "GPT-5.4 mini" in calls[1][1]["content"]
    assert "DeepSeek V3" in calls[1][1]["content"]
    assert "TXT-Datei" in result
    assert "results/20260326_124500_LLM_Preise_Vergleich.txt" in result
    assert "DeepSeek" in result


@pytest.mark.asyncio
async def test_executor_filters_pricing_table_for_openai_and_chinese_followup(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    calls: list[tuple[str, dict]] = []

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer pricing provider comparisons nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append((method, dict(params)))
        assert method == "fetch_url"
        return {
            "status": "success",
            "url": params["url"],
            "title": "Alle KI-Modelle vergleichen – LLM Vergleich (2026)",
            "content": "\n".join(
                [
                    "Modell | Input | Output | Cached",
                    "GPT-5.4 mini | $0.75 / 1M | $4.50 / 1M | $0.075 / 1M",
                    "Claude Sonnet 4.6 | $3.00 / 1M | $15.00 / 1M | $0.30 / 1M",
                    "DeepSeek V3 | $0.27 / 1M | $1.10 / 1M | $0.07 / 1M",
                    "Qwen Max | $0.40 / 1M | $1.20 / 1M | $0.08 / 1M",
                ]
            ),
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    task = "\n".join(
        [
            _build_executor_live_lookup_task(
                "suche da die llms von openai und von den chinesichen anbietern raus und vergleiche anschliessend welche bietet am meisten fuer sein geld"
            ),
            "",
            "# FOLLOW-UP CONTEXT",
            "last_agent: meta",
            "recent_assistant_replies: Zu den aktuellen Preisen habe ich gerade diese Treffer gefunden: || Direkt gepruefte Quelle: - Alle KI-Modelle vergleichen – LLM Vergleich (2026) | https://www.byte.de/vergleich/llm",
            "topic_recall: Alle KI-Modelle vergleichen – LLM Vergleich (2026) | https://www.byte.de/vergleich/llm",
            "",
            "# CURRENT USER QUERY",
            "suche da die llms von openai und von den chinesichen anbietern raus und vergleiche anschliessend welche bietet am meisten fuer sein geld",
        ]
    )
    result = await ExecutorAgent.run(agent, task)

    assert calls == [("fetch_url", {"url": "https://www.byte.de/vergleich/llm", "max_content_length": 6000, "timeout": 15})]
    assert "GPT-5.4 mini" in result
    assert "DeepSeek V3" in result
    assert "Qwen Max" in result
    assert "Claude Sonnet 4.6" not in result
    assert "Preisvergleich" in result

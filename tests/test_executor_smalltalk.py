import sys
from pathlib import Path

import pytest


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


@pytest.mark.asyncio
async def test_executor_handles_smalltalk_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer Smalltalk nicht aufgerufen werden")

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(agent, "Hey Timus, wie gehts?")

    assert "einsatzbereit" in result or "Ich bin da" in result


@pytest.mark.asyncio
async def test_executor_does_not_swallow_regular_queries(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _fake_run(self, task: str):
        return "delegated-llm-path"

    monkeypatch.setattr(BaseAgent, "run", _fake_run)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(agent, "Wie spät ist es in Berlin?")

    assert result == "delegated-llm-path"


@pytest.mark.asyncio
async def test_executor_handles_self_status_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer Self-Status nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "get_ops_observability"
        return {
            "status": "ok",
            "state": "warning",
            "critical_alerts": 0,
            "warnings": 2,
            "failing_services": 1,
            "unhealthy_providers": 0,
            "alerts": [
                {"severity": "warn", "message": "visual workflow instability"},
            ],
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(agent, "sag du es mir")

    assert "Baustellen" in result
    assert "visual workflow instability" in result


@pytest.mark.asyncio
async def test_executor_handles_prefixed_self_status_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer gepraefixten Self-Status nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "get_ops_observability"
        return {
            "status": "ok",
            "state": "ok",
            "critical_alerts": 0,
            "warnings": 0,
            "failing_services": 0,
            "unhealthy_providers": 0,
            "alerts": [],
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        "Antworte ausschliesslich auf Deutsch.\n\nNutzeranfrage:\nsag du es mir",
    )

    assert "nichts Kritisches" in result


@pytest.mark.asyncio
async def test_executor_handles_self_remediation_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer Self-Remediation nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "get_ops_observability"
        return {
            "status": "ok",
            "state": "critical",
            "critical_alerts": 2,
            "warnings": 2,
            "failing_services": 0,
            "unhealthy_providers": 0,
            "alerts": [
                {"severity": "critical", "message": "Routing visual: success 0.40"},
                {"severity": "critical", "message": "Routing research: success 0.29"},
            ],
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(agent, "und was kannst du dagegen tun")

    assert "Dagegen kann ich" in result
    assert "Visual strenger" in result
    assert "Leichte Recherchefaelle" in result


@pytest.mark.asyncio
async def test_executor_recovers_current_query_from_followup_capsule(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer Follow-up-Capsules nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "get_ops_observability"
        return {
            "status": "ok",
            "state": "warning",
            "critical_alerts": 0,
            "warnings": 1,
            "failing_services": 0,
            "unhealthy_providers": 0,
            "alerts": [],
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        "# FOLLOW-UP CONTEXT\nlast_agent: executor\nlast_user: Was hast du fuer Probleme?\n"
        "last_assistant: Gerade sehe ich diese Baustellen bei mir.\n\n"
        "# CURRENT USER QUERY\nund was kannst du dagegen tun",
    )

    assert "Dagegen kann ich" in result


@pytest.mark.asyncio
async def test_executor_handles_self_priority_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer Self-Priority nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "get_ops_observability"
        return {
            "status": "ok",
            "state": "critical",
            "critical_alerts": 2,
            "warnings": 2,
            "failing_services": 0,
            "unhealthy_providers": 0,
            "alerts": [
                {"severity": "critical", "message": "Routing visual: success 0.40"},
                {"severity": "critical", "message": "Routing research: success 0.29"},
            ],
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(agent, "und was davon machst du zuerst")

    assert "Als Erstes" in result
    assert "Visual-Pfad" in result


@pytest.mark.asyncio
async def test_executor_handles_semantic_recall_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer semantischen Recall nicht aufgerufen werden")

    recorded = {}

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(
        ExecutorAgent,
        "_record_conversation_recall",
        staticmethod(lambda **kwargs: recorded.update(kwargs)),
    )

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        "# FOLLOW-UP CONTEXT\nlast_agent: executor\nsession_id: recall_semantic\n"
        "semantic_recall: assistant:executor => Frueher habe ich den Visual-Pfad bereits als Hauptproblem markiert.\n\n"
        "# CURRENT USER QUERY\nwie war nochmal dein plan fuer visual",
    )

    assert "Daran erinnere ich mich" in result
    assert "Visual-Pfad" in result
    assert recorded["source"] == "semantic"
    assert recorded["session_id"] == "recall_semantic"


@pytest.mark.asyncio
async def test_executor_uses_recent_assistant_replies_for_recall_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer Recall-Fallback nicht aufgerufen werden")

    recorded = {}

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(
        ExecutorAgent,
        "_record_conversation_recall",
        staticmethod(lambda **kwargs: recorded.update(kwargs)),
    )

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        "# FOLLOW-UP CONTEXT\nlast_agent: executor\nsession_id: recall_recent\n"
        "recent_assistant_replies: Dagegen kann ich im Moment konkret Folgendes tun: Visual strenger nur fuer echte UI-Aufgaben verwenden.\n\n"
        "# CURRENT USER QUERY\nwie war nochmal dein plan fuer visual",
    )

    assert "Daran erinnere ich mich" in result
    assert "Visual strenger" in result
    assert recorded["source"] == "recent_assistant"
    assert recorded["session_id"] == "recall_recent"


@pytest.mark.asyncio
async def test_executor_answers_topic_recall_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer Topic-Recall nicht aufgerufen werden")

    recorded = {}

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)
    monkeypatch.setattr(
        ExecutorAgent,
        "_record_conversation_recall",
        staticmethod(lambda **kwargs: recorded.update(kwargs)),
    )

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        "# FOLLOW-UP CONTEXT\nlast_agent: meta\nsession_id: recall_topic\n"
        "topic_recall: Telegram-Versand gescheitert — DNS-Auflösung kaputt.\n\n"
        "# CURRENT USER QUERY\nwas war nochmal mit telegram ?",
    )

    assert "telegram" in result.lower()
    assert "DNS-Auflösung kaputt" in result
    assert recorded["source"] == "topic_recall"
    assert recorded["session_id"] == "recall_topic"


@pytest.mark.asyncio
async def test_executor_explains_topic_recall_without_llm(monkeypatch):
    from agent.agents.executor import ExecutorAgent
    from agent.base_agent import BaseAgent

    async def _unexpected_run(self, task: str):
        raise AssertionError("BaseAgent.run darf fuer Topic-Erklaerung nicht aufgerufen werden")

    monkeypatch.setattr(BaseAgent, "run", _unexpected_run)

    agent = ExecutorAgent.__new__(ExecutorAgent)
    result = await ExecutorAgent.run(
        agent,
        "# FOLLOW-UP CONTEXT\nlast_agent: meta\n"
        "topic_recall: Kamera-Start fehlgeschlagen — keine /dev/video* Geräte.\n\n"
        "# CURRENT USER QUERY\nkannst du das mit der kamera nochmal erklären",
    )

    assert "Klar." in result
    assert "kamera" in result.lower()
    assert "/dev/video" in result

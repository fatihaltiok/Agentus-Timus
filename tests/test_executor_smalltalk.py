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

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_data_agent_skips_data_context_for_advice_followup(monkeypatch) -> None:
    from agent.agents.data import DataAgent
    from agent.base_agent import BaseAgent

    captured: dict[str, str] = {}

    async def _fake_super_run(self, task: str) -> str:
        captured["task"] = task
        return "ok"

    async def _unexpected_context(self) -> str:
        raise AssertionError("data context should not be loaded for advice followups")

    monkeypatch.setattr(BaseAgent, "run", _fake_super_run)
    monkeypatch.setattr(DataAgent, "_build_data_context", _unexpected_context)

    agent = DataAgent.__new__(DataAgent)
    result = await DataAgent.run(agent, "AI Training Data und Annotation erklaere mir wie ich damit anfangen kann")

    assert result == "ok"
    assert "# EVIDENZ-ANTWORT-GUARD" in captured["task"]
    assert "# DATEN-KONTEXT" not in captured["task"]


@pytest.mark.asyncio
async def test_data_agent_keeps_data_context_for_real_csv_task(monkeypatch) -> None:
    from agent.agents.data import DataAgent
    from agent.base_agent import BaseAgent

    captured: dict[str, str] = {}

    async def _fake_super_run(self, task: str) -> str:
        captured["task"] = task
        return "ok"

    async def _fake_context(self) -> str:
        return "# DATEN-KONTEXT (automatisch geladen)\nDatei: /tmp/umsatz.csv"

    monkeypatch.setattr(BaseAgent, "run", _fake_super_run)
    monkeypatch.setattr(DataAgent, "_build_data_context", _fake_context)

    agent = DataAgent.__new__(DataAgent)
    result = await DataAgent.run(agent, "Analysiere die CSV /tmp/umsatz.csv")

    assert result == "ok"
    assert "# DATEN-KONTEXT" in captured["task"]
    assert "# EVIDENZ-ANTWORT-GUARD" not in captured["task"]

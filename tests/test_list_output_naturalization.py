from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_finalize_list_output_uses_primary_task_instead_of_wrapped_instructions():
    from agent.base_agent import BaseAgent

    agent = BaseAgent.__new__(BaseAgent)
    task = (
        "# FOLLOW-UP CONTEXT\n"
        "last_agent: meta\n\n"
        "# CURRENT USER QUERY\n"
        "was gibts auf dem blackboard\n\n"
        "# INSTRUCTIONS\n"
        "Erstelle eine Liste mit klaren Punkten."
    )
    result = "**Blackboard-Inhalt**\n\n- delegation:developer\n- delegation:executor"

    finalized = await BaseAgent._finalize_list_output(agent, task, result)

    assert finalized == result


@pytest.mark.asyncio
async def test_finalize_list_output_preserves_preformatted_markdown(monkeypatch):
    from agent.base_agent import BaseAgent

    captured = {}

    async def _fake_call_tool(self, method: str, params: dict):
        captured["method"] = method
        captured["params"] = dict(params)
        return {"status": "success"}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = BaseAgent.__new__(BaseAgent)
    agent._emit_step_trace = lambda *args, **kwargs: None

    result = (
        "**Google Calendar Setup**\n\n"
        "- Projekt anlegen\n"
        "- OAuth-Client erstellen\n"
        "- Redirect-URI setzen"
    )

    finalized = await BaseAgent._finalize_list_output(
        agent,
        "Bitte erstelle eine Liste fuer die Google-Calendar-Einrichtung.",
        result,
    )

    assert finalized.startswith("**Google Calendar Setup**")
    assert "1. **Google Calendar Setup**" not in finalized
    assert "Hier ist deine Liste" not in finalized
    assert "Gespeichert unter:" in finalized
    assert captured["method"] == "write_file"
    assert captured["params"]["path"].startswith("results/")


@pytest.mark.asyncio
async def test_finalize_list_output_plain_lines_become_numbered_without_stock_intro(monkeypatch):
    from agent.base_agent import BaseAgent

    async def _fake_call_tool(self, method: str, params: dict):
        return {"status": "success"}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = BaseAgent.__new__(BaseAgent)
    agent._emit_step_trace = lambda *args, **kwargs: None

    finalized = await BaseAgent._finalize_list_output(
        agent,
        "Mach bitte eine Liste mit zwei Cafes.",
        "Cafe A\nCafe B",
    )

    assert finalized.startswith("1. Cafe A\n2. Cafe B")
    assert "Hier ist deine Liste" not in finalized


def test_format_generate_text_output_drops_stock_intro_for_json_lists():
    from agent.base_agent import BaseAgent

    agent = BaseAgent.__new__(BaseAgent)

    formatted = BaseAgent._format_generate_text_output(
        agent,
        '[{"name":"Cafe A","short_description":"gemuetlich"}]',
    )

    assert formatted == "1. Cafe A - gemuetlich"
    assert "Hier ist deine Liste" not in formatted

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_meta_capabilities_are_orchestrator_only():
    from agent.base_agent import AGENT_CAPABILITY_MAP

    caps = set(AGENT_CAPABILITY_MAP["meta"])
    assert {"meta", "orchestration", "planning", "automation", "tasks", "memory", "reflection", "curation", "skills"} <= caps
    assert "search" not in caps
    assert "web" not in caps
    assert "document" not in caps
    assert "file" not in caps
    assert "filesystem" not in caps
    assert "system" not in caps


def test_meta_filters_specialist_tool_blocks_from_prompt_manifest():
    from agent.agents.meta import MetaAgent

    tools_description = (
        "delegate_to_agent: delegiert\n"
        "  param: x\n"
        "send_email: mail senden\n"
        "  param: to\n"
        "run_command: shell\n"
        "  param: cmd\n"
        "search_web: suche\n"
        "  param: query\n"
    )

    filtered = MetaAgent._filter_tools_for_meta(tools_description)

    assert "delegate_to_agent" in filtered
    assert "send_email" not in filtered
    assert "run_command" not in filtered
    assert "search_web" not in filtered


@pytest.mark.asyncio
async def test_meta_reroutes_send_email_to_communication(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    captured = {}

    async def _fake_call_tool(self, method: str, params: dict):
        captured["method"] = method
        captured["params"] = dict(params)
        return {"status": "success", "agent": "communication"}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-mail"

    result = await MetaAgent._call_tool(
        agent,
        "send_email",
        {
            "to": "fatihaltiok@outlook.com",
            "subject": "Bericht",
            "body": "Bitte senden",
            "attachment_path": "/tmp/report.pdf",
        },
    )

    assert result["status"] == "success"
    assert captured["method"] == "delegate_to_agent"
    assert captured["params"]["agent_type"] == "communication"
    assert captured["params"]["session_id"] == "sess-meta-mail"
    assert captured["params"]["task"].startswith("# DELEGATION HANDOFF")
    assert "target_agent: communication" in captured["params"]["task"]
    assert "expected_output: Nachricht oder Versandstatus" in captured["params"]["task"]
    assert "success_signal: Nachricht formuliert oder versendet" in captured["params"]["task"]
    assert "handoff_data:" in captured["params"]["task"]
    assert "recipient: fatihaltiok@outlook.com" in captured["params"]["task"]
    assert "fatihaltiok@outlook.com" in captured["params"]["task"]
    assert "Bericht" in captured["params"]["task"]


@pytest.mark.asyncio
async def test_meta_reroutes_screen_text_tools_to_visual(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    captured = {}

    async def _fake_call_tool(self, method: str, params: dict):
        captured["method"] = method
        captured["params"] = dict(params)
        return {"status": "success", "agent": "visual", "result": "sichtbarer Text"}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-visual-reroute"

    result = await MetaAgent._call_tool(agent, "get_all_screen_text", {})

    assert result["status"] == "success"
    assert captured["method"] == "delegate_to_agent"
    assert captured["params"]["agent_type"] == "visual"
    assert "target_agent: visual" in captured["params"]["task"]
    assert "Lies den sichtbaren Bildschirmtext ueber den Visual-Agenten aus." in captured["params"]["task"]


@pytest.mark.asyncio
async def test_meta_converts_empty_delegation_response_into_explicit_error(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    captured = {}

    async def _fake_call_tool(self, method: str, params: dict):
        captured["method"] = method
        captured["params"] = dict(params)
        return {"error": ""}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-empty"

    result = await MetaAgent._call_tool(
        agent,
        "start_deep_research",
        {"query": "Chinesische LLMs 2025"},
    )

    assert captured["method"] == "delegate_to_agent"
    assert captured["params"]["task"].startswith("# DELEGATION HANDOFF")
    assert "target_agent: research" in captured["params"]["task"]
    assert "expected_output: summary, sources oder artifacts" in captured["params"]["task"]
    assert result["status"] == "error"
    assert "leere oder unvollstaendige Antwort" in result["error"]
    assert result["metadata"]["delegation_transport_error"] is True

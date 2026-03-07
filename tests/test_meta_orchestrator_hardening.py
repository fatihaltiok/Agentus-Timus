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
    assert "fatihaltiok@outlook.com" in captured["params"]["task"]
    assert "Bericht" in captured["params"]["task"]

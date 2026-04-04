from __future__ import annotations

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from agent.agent_registry import AgentRegistry
from memory.agent_blackboard import AgentBlackboard
from tools.blackboard_tool.tool import read_from_blackboard


@pytest.mark.asyncio
async def test_read_from_blackboard_accepts_delegation_key_as_topic(monkeypatch, tmp_path):
    blackboard = AgentBlackboard(tmp_path / "bb.sqlite")
    monkeypatch.setattr("memory.agent_blackboard.get_blackboard", lambda *args, **kwargs: blackboard)

    key = AgentRegistry._auto_write_to_blackboard(
        "developer",
        "google calendar task",
        "Setup-Plan für Google Calendar API Integration",
        "success",
    )

    result = await read_from_blackboard(topic=key)

    assert result["status"] == "ok"
    assert result["lookup_mode"] == "delegation_key"
    assert result["count"] == 1
    assert result["entries"][0]["topic"] == "delegation_results"
    assert result["entries"][0]["key"] == key

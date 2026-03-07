from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.base_agent import BaseAgent
from agent.dynamic_tool_mixin import DynamicToolMixin


def _minimal_base_agent() -> BaseAgent:
    agent = BaseAgent.__new__(BaseAgent)
    agent.agent_type = "executor"
    agent._remote_tools_fetched = True
    agent._remote_tool_names = set()
    agent._bug_logger = None
    agent._refine_tool_call = lambda method, params: (method, params)
    agent._emit_live_status = lambda **kwargs: None
    agent.should_skip_action = lambda method, params: (False, None)
    agent._ensure_remote_tool_names = AsyncMock(return_value=None)
    agent._get_lane = AsyncMock(
        return_value=SimpleNamespace(
            lane_id="test-lane",
            status=SimpleNamespace(value="idle"),
        )
    )
    return agent


def test_extract_primary_file_path_prefers_artifacts():
    agent = _minimal_base_agent()
    observation = {
        "artifacts": [{"type": "pdf", "path": "results/from-artifacts.pdf"}],
        "metadata": {"pdf_filepath": "/tmp/from-metadata.pdf"},
        "filepath": "/tmp/from-legacy.pdf",
    }

    path, source = agent._extract_primary_file_path(observation)

    assert path.endswith("results/from-artifacts.pdf")
    assert source == "artifacts"


def test_extract_primary_file_path_reports_metadata_fallback():
    agent = _minimal_base_agent()
    observation = {
        "metadata": {"pdf_filepath": "/tmp/from-metadata.pdf"},
        "filepath": "/tmp/from-legacy.pdf",
    }

    path, source = agent._extract_primary_file_path(observation)

    assert path == "/tmp/from-metadata.pdf"
    assert source == "metadata"


@pytest.mark.asyncio
async def test_call_tool_normalizes_remote_dict_result(monkeypatch):
    import agent.base_agent as base_agent_module

    agent = _minimal_base_agent()
    agent.http_client = SimpleNamespace(
        post=AsyncMock(
            return_value=SimpleNamespace(
                json=lambda: {
                    "jsonrpc": "2.0",
                    "result": {
                        "success": True,
                        "message": "Datei gespeichert",
                        "filepath": "/tmp/report.pdf",
                    },
                }
            )
        )
    )

    monkeypatch.setattr(base_agent_module, "evaluate_policy_gate", lambda **kwargs: {"allowed": True})
    monkeypatch.setattr(base_agent_module, "audit_policy_decision", lambda decision: None)
    monkeypatch.setattr(base_agent_module.registry_v2, "validate_tool_call", lambda *args, **kwargs: kwargs)

    result = await agent._call_tool("save_research_result", {"title": "X"})

    assert result["status"] == "success"
    assert result["summary"] == "Datei gespeichert"
    assert result["metadata"]["filepath"] == "/tmp/report.pdf"
    assert result["artifacts"][0]["path"] == "/tmp/report.pdf"


@pytest.mark.asyncio
async def test_dynamic_execute_tool_requests_normalized_result(monkeypatch):
    mixin = DynamicToolMixin.__new__(DynamicToolMixin)
    mixin._dynamic_tools_enabled = True

    captured = {}

    async def fake_execute(tool_name, **kwargs):
        captured["tool_name"] = tool_name
        captured["kwargs"] = kwargs
        return {"status": "success"}

    import agent.dynamic_tool_mixin as mixin_module

    monkeypatch.setattr(mixin_module.registry_v2, "execute", fake_execute)

    result = await mixin.execute_tool("demo_tool", value="abc")

    assert result["status"] == "success"
    assert captured["tool_name"] == "demo_tool"
    assert captured["kwargs"]["normalize"] is True
    assert captured["kwargs"]["value"] == "abc"


@pytest.mark.asyncio
async def test_call_tool_formats_empty_jsonrpc_error(monkeypatch):
    import agent.base_agent as base_agent_module

    agent = _minimal_base_agent()
    agent.http_client = SimpleNamespace(
        post=AsyncMock(
            return_value=SimpleNamespace(
                json=lambda: {
                    "jsonrpc": "2.0",
                    "error": "",
                }
            )
        )
    )

    monkeypatch.setattr(base_agent_module, "evaluate_policy_gate", lambda **kwargs: {"allowed": True})
    monkeypatch.setattr(base_agent_module, "audit_policy_decision", lambda decision: None)
    monkeypatch.setattr(base_agent_module.registry_v2, "validate_tool_call", lambda *args, **kwargs: kwargs)

    result = await agent._call_tool("delegate_to_agent", {"agent_type": "research", "task": "x"})

    assert result["error"] == "JSON-RPC Fehler ohne Details"


@pytest.mark.asyncio
async def test_call_tool_formats_jsonrpc_error_dict(monkeypatch):
    import agent.base_agent as base_agent_module

    agent = _minimal_base_agent()
    agent.http_client = SimpleNamespace(
        post=AsyncMock(
            return_value=SimpleNamespace(
                json=lambda: {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "Invalid params", "data": "missing session_id"},
                }
            )
        )
    )

    monkeypatch.setattr(base_agent_module, "evaluate_policy_gate", lambda **kwargs: {"allowed": True})
    monkeypatch.setattr(base_agent_module, "audit_policy_decision", lambda decision: None)
    monkeypatch.setattr(base_agent_module.registry_v2, "validate_tool_call", lambda *args, **kwargs: kwargs)

    result = await agent._call_tool("delegate_to_agent", {"agent_type": "research", "task": "x"})

    assert result["error"] == "JSON-RPC Fehler: code=-32602 | Invalid params | missing session_id"

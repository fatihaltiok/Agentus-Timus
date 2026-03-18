from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from agent.base_agent import BaseAgent
from agent.dynamic_tool_mixin import DynamicToolMixin


def _minimal_base_agent() -> BaseAgent:
    agent = BaseAgent.__new__(BaseAgent)
    agent.agent_type = "executor"
    agent._remote_tools_fetched = True
    agent._remote_tool_names = set()
    agent._bug_logger = None
    agent._current_task_text = ""
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


def test_handle_file_artifacts_blocks_protected_logs_in_service(monkeypatch):
    import agent.base_agent as base_agent_module

    agent = _minimal_base_agent()
    observation = {"filepath": "/home/fatih-ubuntu/dev/timus/timus_server.log"}

    monkeypatch.setenv("AUTO_OPEN_FILES", "true")
    monkeypatch.setenv("SYSTEMD_EXEC_PID", "123")
    monkeypatch.setattr(base_agent_module.os.path, "exists", lambda path: True)
    open_call = MagicMock()
    monkeypatch.setattr(base_agent_module.subprocess, "call", open_call)

    agent._handle_file_artifacts(observation)

    open_call.assert_not_called()


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


@pytest.mark.asyncio
async def test_call_tool_blocks_restart_without_explicit_restart_intent(monkeypatch):
    import agent.base_agent as base_agent_module

    agent = _minimal_base_agent()
    agent._current_task_text = "Lies die Logs und pruefe den Zustand von Timus."
    agent.http_client = SimpleNamespace(
        post=AsyncMock(
            return_value=SimpleNamespace(
                json=lambda: {
                    "jsonrpc": "2.0",
                    "result": {"status": "pending_restart", "mode": "dispatcher"},
                }
            )
        )
    )

    monkeypatch.setattr(base_agent_module, "evaluate_policy_gate", lambda **kwargs: {"allowed": True})
    monkeypatch.setattr(base_agent_module, "audit_policy_decision", lambda decision: None)
    monkeypatch.setattr(base_agent_module.registry_v2, "validate_tool_call", lambda *args, **kwargs: kwargs)

    result = await agent._call_tool("restart_timus", {"mode": "dispatcher"})

    assert result["blocked_by_policy"] is True
    assert "expliziten Neustart-Wunsch" in result["error"]


@pytest.mark.asyncio
async def test_call_tool_allows_restart_with_explicit_restart_intent(monkeypatch):
    import agent.base_agent as base_agent_module

    agent = _minimal_base_agent()
    agent._current_task_text = "Bitte starte den Dispatcher neu."
    agent.http_client = SimpleNamespace(
        post=AsyncMock(
            return_value=SimpleNamespace(
                json=lambda: {
                    "jsonrpc": "2.0",
                    "result": {
                        "status": "pending_restart",
                        "mode": "dispatcher",
                        "message": "Detached Timus-Neustart gestartet",
                    },
                }
            )
        )
    )

    monkeypatch.setattr(base_agent_module, "evaluate_policy_gate", lambda **kwargs: {"allowed": True})
    monkeypatch.setattr(base_agent_module, "audit_policy_decision", lambda decision: None)
    monkeypatch.setattr(base_agent_module.registry_v2, "validate_tool_call", lambda *args, **kwargs: kwargs)

    result = await agent._call_tool("restart_timus", {"mode": "dispatcher"})

    payload = result.get("data") if isinstance(result.get("data"), dict) else result
    assert payload["status"] == "pending_restart"
    assert payload["mode"] == "dispatcher"


@pytest.mark.asyncio
async def test_call_tool_records_tool_usage_with_task_type(monkeypatch):
    import agent.base_agent as base_agent_module

    captured = []

    agent = _minimal_base_agent()
    agent._current_task_text = "\n".join(
        [
            "# DELEGATION HANDOFF",
            "target_agent: executor",
            "goal: route bauen",
            "handoff_data:",
            "- task_type: location_route",
        ]
    )
    agent.http_client = SimpleNamespace(
        post=AsyncMock(
            return_value=SimpleNamespace(
                json=lambda: {
                    "jsonrpc": "2.0",
                    "result": {"status": "success", "message": "ok"},
                }
            )
        )
    )

    monkeypatch.setenv("AUTONOMY_SELF_IMPROVEMENT_ENABLED", "true")
    monkeypatch.setattr(base_agent_module, "evaluate_policy_gate", lambda **kwargs: {"allowed": True})
    monkeypatch.setattr(base_agent_module, "audit_policy_decision", lambda decision: None)
    monkeypatch.setattr(base_agent_module.registry_v2, "validate_tool_call", lambda *args, **kwargs: kwargs)
    monkeypatch.setattr(
        base_agent_module,
        "get_improvement_engine",
        lambda: SimpleNamespace(record_tool_usage=lambda record: captured.append(record)),
    )

    result = await agent._call_tool("delegate_to_agent", {"agent_type": "research", "task": "x"})

    assert result["status"] == "success"
    assert len(captured) == 1
    assert captured[0].tool_name == "delegate_to_agent"
    assert captured[0].task_type == "location_route"
    assert captured[0].success is True
    assert captured[0].duration_ms >= 0


def test_terminal_restart_tool_finalizes_agent_run():
    agent = _minimal_base_agent()

    result = agent._maybe_finalize_after_terminal_tool(
        "restart_timus",
        {
            "status": "pending_restart",
            "mode": "full",
            "launcher_pid": 12345,
            "message": "Detached Timus-Neustart gestartet (Modus: full).",
        },
    )

    assert result is not None
    assert "Launcher-PID: 12345" in result
    assert "Modus: full" in result
    assert "Die Verbindung kann jetzt kurz unterbrochen sein" in result


def test_terminal_restart_tool_finalizes_agent_run_for_normalized_envelope():
    agent = _minimal_base_agent()

    result = agent._maybe_finalize_after_terminal_tool(
        "restart_timus",
        {
            "status": "success",
            "mode": "full",
            "launcher_pid": 12345,
            "message": "Detached Timus-Neustart gestartet (Modus: full). Status danach separat pruefen.",
            "data": {
                "status": "pending_restart",
                "mode": "full",
                "launcher_pid": 12345,
                "message": "Detached Timus-Neustart gestartet (Modus: full). Status danach separat pruefen.",
            },
            "summary": "Detached Timus-Neustart gestartet (Modus: full). Status danach separat pruefen.",
            "artifacts": [],
            "metadata": {},
            "error": "",
        },
    )

    assert result is not None
    assert "Launcher-PID: 12345" in result
    assert "Modus: full" in result
    assert "Die Verbindung kann jetzt kurz unterbrochen sein" in result

"""M4.1 Formale Policy-Gates + Audit-Entscheidungen."""

from __future__ import annotations

from pathlib import Path

import pytest

from utils.policy_gate import evaluate_policy_gate


class _DummyAuditLogger:
    def log_start(self, *_args, **_kwargs):
        return None

    def log_end(self, *_args, **_kwargs):
        return None


class _DummyAgent:
    def __init__(self, tools_description_string: str, **_kwargs):
        self.tools_description_string = tools_description_string

    async def run(self, query: str):
        return f"dummy:{query}"


def test_m4_query_policy_observe_when_not_strict(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "false")

    decision = evaluate_policy_gate(
        gate="query",
        subject="lösche die datei test.txt",
        payload={"query": "lösche die datei test.txt"},
        source="unit_test",
    )
    assert decision["action"] == "observe"
    assert decision["blocked"] is False
    assert "dangerous_query" in decision["violations"]


def test_m4_query_policy_blocks_when_strict(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "true")

    decision = evaluate_policy_gate(
        gate="query",
        subject="lösche die datei test.txt",
        payload={"query": "lösche die datei test.txt"},
        source="unit_test",
    )
    assert decision["action"] == "block"
    assert decision["blocked"] is True


def test_m4_tool_policy_can_block_sensitive_params_in_strict(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "true")

    decision = evaluate_policy_gate(
        gate="tool",
        subject="custom_tool",
        payload={"params": {"api_key": "secret-123", "query": "x"}},
        source="unit_test",
    )
    assert decision["blocked"] is True
    assert "sensitive_params" in decision["violations"]


@pytest.mark.asyncio
async def test_m4_run_agent_strict_query_block(monkeypatch) -> None:
    import main_dispatcher

    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "true")
    monkeypatch.setattr("utils.audit_logger.AuditLogger", _DummyAuditLogger)
    monkeypatch.setitem(main_dispatcher.AGENT_CLASS_MAP, "m4_dummy_agent", _DummyAgent)

    calls = []
    monkeypatch.setattr(
        main_dispatcher,
        "_log_interaction_deterministic",
        lambda **kwargs: calls.append(kwargs),
    )

    result = await main_dispatcher.run_agent(
        agent_name="m4_dummy_agent",
        query="lösche die datei /tmp/test.txt",
        tools_description="tools",
        session_id="m4_policy_block",
    )
    assert isinstance(result, str)
    assert result.startswith("Abgebrochen:")
    assert calls
    assert calls[0]["metadata"]["policy_gate"]["blocked"] is True


@pytest.mark.asyncio
async def test_m4_delegate_blocks_dangerous_shell_task_in_strict(monkeypatch) -> None:
    from agent.agent_registry import AgentRegistry

    class _ShellDummy:
        def __init__(self, tools_description_string: str, **_kwargs):
            self.tools_description_string = tools_description_string

        async def run(self, task: str):
            return f"shell:{task}"

    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "true")

    registry = AgentRegistry()
    registry.register_spec(
        name="shell",
        agent_type="shell",
        capabilities=["shell"],
        factory=_ShellDummy,
    )

    async def _fake_tools_desc() -> str:
        return "tools"

    monkeypatch.setattr(registry, "_get_tools_description", _fake_tools_desc)

    result = await registry.delegate(
        from_agent="meta",
        to_agent="shell",
        task="lösche die datei /tmp/a.txt",
    )
    assert result["status"] == "error"
    assert result.get("blocked_by_policy") is True


def test_m4_policy_gate_hooks_present() -> None:
    dispatcher_src = Path("main_dispatcher.py").read_text(encoding="utf-8")
    server_src = Path("server/mcp_server.py").read_text(encoding="utf-8")
    registry_src = Path("agent/agent_registry.py").read_text(encoding="utf-8")
    base_src = Path("agent/base_agent.py").read_text(encoding="utf-8")

    assert "evaluate_policy_gate" in dispatcher_src
    assert "audit_policy_decision" in dispatcher_src
    assert "evaluate_policy_gate" in server_src
    assert "evaluate_policy_gate" in registry_src
    assert "evaluate_policy_gate" in base_src

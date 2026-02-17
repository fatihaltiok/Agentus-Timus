"""
Milestone 6 E2E Readiness:
- Dispatcher -> Agent -> deterministisches Logging -> Memory DB
- Abdeckung für Standard- und Fehlerpfad mit persistierten Metadaten
"""

import uuid
import pytest
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


class _DummyAuditLogger:
    def log_start(self, *_args, **_kwargs):
        return None

    def log_end(self, *_args, **_kwargs):
        return None


class _DummyE2EAgent:
    def __init__(self, tools_description_string: str, **_kwargs):
        self.tools_description_string = tools_description_string

    async def run(self, query: str):
        return f"e2e_ok:{query}"

    def get_runtime_telemetry(self):
        return {
            "agent_type": "milestone6_e2e",
            "run_duration_sec": 0.02,
            "working_memory": {"enabled": True, "context_chars": 42},
        }


def _patch_common(monkeypatch):
    import utils.policy_gate as policy_gate

    monkeypatch.setattr("utils.audit_logger.AuditLogger", _DummyAuditLogger)
    monkeypatch.setattr(policy_gate, "audit_tool_call", lambda *_a, **_k: None)
    monkeypatch.setattr(policy_gate, "check_query_policy", lambda _q: (True, None))


@pytest.mark.asyncio
async def test_e2e_standard_path_persists_metadata(monkeypatch):
    import main_dispatcher
    from memory.memory_system import memory_manager

    _patch_common(monkeypatch)
    agent_key = "milestone6_e2e_agent"
    monkeypatch.setitem(main_dispatcher.AGENT_CLASS_MAP, agent_key, _DummyE2EAgent)

    session_id = f"m6ok_{uuid.uuid4().hex[:8]}"
    query = f"m6_standard_query_{uuid.uuid4().hex[:10]}"

    result = await main_dispatcher.run_agent(
        agent_name=agent_key,
        query=query,
        tools_description="tools",
        session_id=session_id,
    )
    assert result == f"e2e_ok:{query}"

    events = memory_manager.persistent.get_recent_interaction_events(
        limit=20,
        session_id=session_id,
    )
    assert events, "Es wurde kein Interaction-Event persistiert."

    event = next((ev for ev in events if ev.get("user_input") == query), None)
    assert event is not None, "Kein Event mit der erwarteten Query gefunden."
    assert event.get("status") == "completed"

    metadata = event.get("metadata", {})
    assert metadata.get("source") == "run_agent"
    assert metadata.get("execution_path") == "standard"
    assert isinstance(metadata.get("agent_runtime"), dict)
    assert metadata["agent_runtime"]["working_memory"]["enabled"] is True


@pytest.mark.asyncio
async def test_e2e_missing_agent_persists_error_event(monkeypatch):
    import main_dispatcher
    from memory.memory_system import memory_manager

    _patch_common(monkeypatch)

    session_id = f"m6err_{uuid.uuid4().hex[:8]}"
    query = f"m6_missing_agent_query_{uuid.uuid4().hex[:10]}"

    result = await main_dispatcher.run_agent(
        agent_name="m6_agent_does_not_exist",
        query=query,
        tools_description="tools",
        session_id=session_id,
    )
    assert result is None

    events = memory_manager.persistent.get_recent_interaction_events(
        limit=20,
        session_id=session_id,
    )
    assert events, "Es wurde kein Error-Event persistiert."

    event = next((ev for ev in events if ev.get("user_input") == query), None)
    assert event is not None, "Kein Error-Event mit der erwarteten Query gefunden."
    assert event.get("status") == "error"

    metadata = event.get("metadata", {})
    assert metadata.get("source") == "run_agent"
    assert metadata.get("error") == "agent_not_found"

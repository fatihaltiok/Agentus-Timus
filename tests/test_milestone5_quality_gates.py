"""
Milestone 5 Quality Gates:
- Dispatcher deterministisches Logging in allen Run-Agent Pfaden
- Metadata-Merge im Interaction-Logger
- Working-Memory Runtime-Stats als Regression-Schutz
"""

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


class _DummyAgent:
    def __init__(self, tools_description_string: str, **_kwargs):
        self.tools_description_string = tools_description_string

    async def run(self, query: str):
        return f"dummy:{query}"

    def get_runtime_telemetry(self):
        return {
            "agent_type": "unit_test",
            "run_duration_sec": 0.01,
            "working_memory": {"enabled": True, "context_chars": 123},
        }


def _patch_dispatcher_dependencies(monkeypatch):
    monkeypatch.setattr("utils.audit_logger.AuditLogger", _DummyAuditLogger)
    monkeypatch.setattr("utils.policy_gate.audit_tool_call", lambda *_a, **_k: None)
    monkeypatch.setattr("utils.policy_gate.check_query_policy", lambda _q: (True, None))


def test_log_interaction_deterministic_merges_metadata(monkeypatch):
    import main_dispatcher
    import memory.memory_system as memory_system

    captured = {}

    class _DummyMemoryManager:
        def log_interaction_event(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(memory_system, "memory_manager", _DummyMemoryManager())

    main_dispatcher._log_interaction_deterministic(
        user_input="frage",
        assistant_output="antwort",
        agent_name="executor",
        session_id="sess_1",
        metadata={"custom_flag": True},
    )

    assert captured["user_input"] == "frage"
    assert captured["assistant_response"] == "antwort"
    assert captured["status"] == "completed"
    assert captured["external_session_id"] == "sess_1"
    assert captured["metadata"]["source"] == "main_dispatcher"
    assert captured["metadata"]["agent"] == "executor"
    assert captured["metadata"]["custom_flag"] is True


@pytest.mark.asyncio
async def test_run_agent_logs_when_agent_missing(monkeypatch):
    import main_dispatcher

    _patch_dispatcher_dependencies(monkeypatch)

    calls = []
    monkeypatch.setattr(
        main_dispatcher,
        "_log_interaction_deterministic",
        lambda **kwargs: calls.append(kwargs),
    )

    result = await main_dispatcher.run_agent(
        agent_name="does_not_exist",
        query="milestone5 missing agent",
        tools_description="tools",
        session_id="sess_missing",
    )

    assert result is None
    assert len(calls) == 1
    assert calls[0]["session_id"] == "sess_missing"
    assert calls[0]["assistant_output"] is None
    assert calls[0]["metadata"]["error"] == "agent_not_found"


@pytest.mark.asyncio
async def test_run_agent_logs_runtime_metadata_on_standard_path(monkeypatch):
    import main_dispatcher

    _patch_dispatcher_dependencies(monkeypatch)
    monkeypatch.setitem(main_dispatcher.AGENT_CLASS_MAP, "unit_test_agent", _DummyAgent)

    calls = []
    monkeypatch.setattr(
        main_dispatcher,
        "_log_interaction_deterministic",
        lambda **kwargs: calls.append(kwargs),
    )

    result = await main_dispatcher.run_agent(
        agent_name="unit_test_agent",
        query="milestone5 runtime metadata",
        tools_description="tools",
        session_id="sess_standard",
    )

    assert result == "dummy:milestone5 runtime metadata"
    assert len(calls) == 1
    assert calls[0]["assistant_output"] == result
    assert calls[0]["metadata"]["execution_path"] == "standard"
    assert calls[0]["metadata"]["agent_runtime"]["working_memory"]["enabled"] is True


def test_working_memory_stats_exposed():
    from memory.memory_system import MemoryManager

    manager = MemoryManager()

    # Ensure we have at least one event to score.
    manager.log_interaction_event(
        user_input="Ich suche laufend nach Grafikkarten",
        assistant_response="Du hast mehrfach nach Grafikkarten gesucht.",
        agent_name="executor",
        status="completed",
        metadata={"source": "test"},
    )

    context = manager.build_working_memory_context(
        "was habe ich eben zu grafikkarten gesucht?",
        max_chars=900,
        max_related=3,
        max_recent_events=4,
    )
    stats = manager.get_last_working_memory_stats()

    assert isinstance(stats, dict)
    assert "status" in stats
    assert "query_terms_count" in stats
    assert stats.get("max_chars") == 900

    if stats.get("status") == "ok":
        assert len(context) <= 900
        assert stats.get("final_chars") == len(context)
        assert isinstance(stats.get("generated_sections"), list)

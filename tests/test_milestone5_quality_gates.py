"""
Milestone 5 Quality Gates:
- Dispatcher deterministisches Logging in allen Run-Agent Pfaden
- Metadata-Merge im Interaction-Logger
- Working-Memory Runtime-Stats als Regression-Schutz
"""

import pytest
import uuid
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


def test_log_interaction_deterministic_attaches_memory_snapshot(monkeypatch):
    import main_dispatcher
    import memory.memory_system as memory_system

    captured = {}

    class _DummyMemoryManager:
        def get_runtime_memory_snapshot(self, **_kwargs):
            return {
                "session_id": "sess_snap",
                "dialog_state": {"current_topic": "grafikkarten"},
                "recent_event_count": 2,
            }

        def log_interaction_event(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(memory_system, "memory_manager", _DummyMemoryManager())

    main_dispatcher._log_interaction_deterministic(
        user_input="frage",
        assistant_output="antwort",
        agent_name="executor",
        session_id="sess_snap",
        metadata={"custom_flag": True},
    )

    meta = captured.get("metadata", {})
    assert isinstance(meta.get("memory_snapshot"), dict)
    assert meta["memory_snapshot"]["session_id"] == "sess_snap"
    assert meta["memory_snapshot"]["dialog_state"]["current_topic"] == "grafikkarten"


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


@pytest.mark.asyncio
async def test_run_agent_sanitizes_control_chars(monkeypatch):
    import main_dispatcher

    _patch_dispatcher_dependencies(monkeypatch)
    monkeypatch.setitem(main_dispatcher.AGENT_CLASS_MAP, "unit_test_agent", _DummyAgent)

    calls = []
    monkeypatch.setattr(
        main_dispatcher,
        "_log_interaction_deterministic",
        lambda **kwargs: calls.append(kwargs),
    )

    raw_query = "\x16was   haben\twir gesucht?"
    result = await main_dispatcher.run_agent(
        agent_name="unit_test_agent",
        query=raw_query,
        tools_description="tools",
        session_id="sess_sanitize",
    )

    assert result == "dummy:was haben wir gesucht?"
    assert len(calls) == 1
    assert calls[0]["user_input"] == "was haben wir gesucht?"
    assert calls[0]["metadata"]["query_sanitized"] is True


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


def test_unified_recall_prioritizes_session_events():
    from memory.memory_system import MemoryManager

    manager = MemoryManager()
    token = uuid.uuid4().hex[:10]
    my_session = f"m5rec_{uuid.uuid4().hex[:8]}"
    other_session = f"m5oth_{uuid.uuid4().hex[:8]}"

    manager.log_interaction_event(
        user_input=f"ich suche grafikkarten token_{token}",
        assistant_response="okay, ich suche nach grafikkarten.",
        agent_name="executor",
        status="completed",
        external_session_id=my_session,
        metadata={"source": "test"},
    )
    manager.log_interaction_event(
        user_input="ich suche etwas anderes ohne token",
        assistant_response="anderes thema",
        agent_name="executor",
        status="completed",
        external_session_id=other_session,
        metadata={"source": "test"},
    )

    result = manager.unified_recall(
        query="was haben wir eben gesucht",
        n_results=5,
        session_id=my_session,
    )

    assert result.get("status") == "success"
    memories = result.get("memories", [])
    assert memories
    joined = " ".join(str(item.get("text", "")).lower() for item in memories)
    assert token.lower() in joined


def test_session_dialog_state_tracks_open_threads_and_topics():
    from memory.memory_system import MemoryManager

    manager = MemoryManager()
    session_id = f"m5state_{uuid.uuid4().hex[:8]}"

    manager.log_interaction_event(
        user_input="gehe zu ebay.de und suche grafikkarten preise",
        assistant_response="ActionPlan fehlgeschlagen: Tippen fehlgeschlagen",
        agent_name="executor",
        status="error",
        external_session_id=session_id,
        metadata={"source": "test"},
    )

    state = manager.session.get_dynamic_state()
    assert state.get("current_topic")
    assert state.get("open_threads")
    joined_threads = " ".join(state.get("open_threads", [])).lower()
    assert "grafikkarten" in joined_threads

    context = manager.build_working_memory_context(
        "was ist aktuell offen?",
        max_chars=1000,
        max_related=2,
        max_recent_events=4,
        preferred_session_id=session_id,
    )
    stats = manager.get_last_working_memory_stats()
    assert "AKTIVER_DIALOGZUSTAND" in context
    assert "Offene Anliegen" in context
    assert stats.get("dynamic_state_lines", 0) >= 1


def test_session_dialog_state_resolves_threads_on_success():
    from memory.memory_system import MemoryManager

    manager = MemoryManager()
    session_id = f"m5resolve_{uuid.uuid4().hex[:8]}"

    manager.log_interaction_event(
        user_input="suche grafikkarten preise",
        assistant_response="Limit erreicht.",
        agent_name="executor",
        status="error",
        external_session_id=session_id,
        metadata={"source": "test"},
    )
    assert manager.session.open_threads, "Open thread sollte nach Fehler existieren."

    manager.log_interaction_event(
        user_input="grafikkarten preise erledigt",
        assistant_response="Preise erfolgreich gesammelt.",
        agent_name="executor",
        status="completed",
        external_session_id=session_id,
        metadata={"source": "test"},
    )

    assert manager.session.open_threads == []


def test_unified_recall_prioritizes_unresolved_open_thread():
    from memory.memory_system import MemoryManager

    manager = MemoryManager()
    session_id = f"m3open_{uuid.uuid4().hex[:8]}"

    manager.log_interaction_event(
        user_input="suche grafikkarten preise auf ebay",
        assistant_response="ActionPlan fehlgeschlagen: Tippen fehlgeschlagen",
        agent_name="executor",
        status="error",
        external_session_id=session_id,
        metadata={"source": "test"},
    )
    manager.log_interaction_event(
        user_input="wie ist das wetter heute",
        assistant_response="Heute sonnig bei 22 Grad.",
        agent_name="executor",
        status="completed",
        external_session_id=session_id,
        metadata={"source": "test"},
    )

    result = manager.unified_recall(
        query="was ist aktuell offen",
        n_results=3,
        session_id=session_id,
    )
    assert result.get("status") == "success"
    memories = result.get("memories", [])
    assert memories
    top_text = str(memories[0].get("text", "")).lower()
    assert "grafikkarten" in top_text


def test_working_memory_stats_include_dynamic_relevance_flags():
    from memory.memory_system import MemoryManager

    manager = MemoryManager()
    session_id = f"m5flags_{uuid.uuid4().hex[:8]}"

    manager.log_interaction_event(
        user_input="suche grafikkarten angebote und preise",
        assistant_response="ActionPlan fehlgeschlagen: Tippen fehlgeschlagen",
        agent_name="executor",
        status="error",
        external_session_id=session_id,
        metadata={"source": "test"},
    )

    manager.build_working_memory_context(
        "was ist aktuell offen?",
        max_chars=900,
        max_related=3,
        max_recent_events=4,
        preferred_session_id=session_id,
    )
    stats = manager.get_last_working_memory_stats()

    assert "focus_terms_count" in stats
    assert "prefer_unresolved" in stats
    assert isinstance(stats["focus_terms_count"], int)
    assert isinstance(stats["prefer_unresolved"], bool)


def test_runtime_memory_snapshot_reflects_session_state():
    from memory.memory_system import MemoryManager

    manager = MemoryManager()
    session_id = f"m5snap_{uuid.uuid4().hex[:8]}"

    manager.log_interaction_event(
        user_input="ich suche grafikkarten fuer gaming",
        assistant_response="verstanden, ich suche passende modelle",
        agent_name="executor",
        status="completed",
        external_session_id=session_id,
        metadata={"source": "test"},
    )
    manager.build_working_memory_context(
        "grafikkarten gaming",
        max_chars=800,
        max_related=2,
        max_recent_events=3,
        preferred_session_id=session_id,
    )

    snapshot = manager.get_runtime_memory_snapshot(session_id=session_id, recent_limit=5)

    assert snapshot.get("session_id") == session_id
    assert isinstance(snapshot.get("dialog_state"), dict)
    assert "current_topic" in snapshot["dialog_state"]
    assert snapshot.get("recent_event_count", 0) >= 1
    assert isinstance(snapshot.get("working_memory_last_stats"), dict)
    assert snapshot["working_memory_last_stats"].get("query")

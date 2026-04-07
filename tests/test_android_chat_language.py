import sys
from types import SimpleNamespace

import pytest

from server import mcp_server


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _stub_chat_memory_logging(monkeypatch):
    monkeypatch.setattr(mcp_server, "_log_chat_interaction", lambda **kwargs: None)


async def test_canvas_chat_honors_response_language_german(monkeypatch, tmp_path):
    captured = {}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        captured["decision_query"] = query
        captured["decision_session_id"] = session_id
        return "meta"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_query"] = query
        captured["run_agent_name"] = agent_name
        captured["run_tools_description"] = tools_description
        captured["run_session_id"] = session_id
        return "Antwort auf Deutsch"

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    response = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "Sag hallo",
                "session_id": "android_test",
                "response_language": "de",
            }
        )
    )

    assert response["status"] == "success"
    assert response["reply"] == "Antwort auf Deutsch"
    assert captured["decision_query"] == "Sag hallo"
    assert "Antworte ausschließlich auf Deutsch" in captured["run_query"]
    assert "Sag hallo" in captured["run_query"]


async def test_canvas_chat_preserves_live_location_context_when_response_language_is_german(monkeypatch, tmp_path):
    captured = {}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])
    monkeypatch.setattr(
        mcp_server,
        "_get_location_snapshot",
        lambda: {
            "presence_status": "live",
            "usable_for_context": True,
            "has_coordinates": True,
            "display_name": "Alexanderplatz, Berlin, Deutschland",
            "locality": "Berlin",
            "latitude": 52.52,
            "longitude": 13.40,
            "captured_at": "2026-03-16T12:00:00Z",
            "received_at": "2026-03-16T12:00:02Z",
            "maps_url": "https://www.google.com/maps/search/?api=1&query=52.52,13.40",
        },
    )

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        return "executor"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_query"] = query
        return "Route wird vorbereitet."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    response = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "Zeig mir den Weg zum Hauptbahnhof",
                "session_id": "android_loc_lang",
                "response_language": "de",
            }
        )
    )

    assert response["status"] == "success"
    assert "Antworte ausschließlich auf Deutsch" in captured["run_query"]
    assert "# LIVE LOCATION CONTEXT" in captured["run_query"]
    assert "latitude: 52.52" in captured["run_query"]
    assert "Zeig mir den Weg zum Hauptbahnhof" in captured["run_query"]


async def test_canvas_chat_routes_followup_to_same_executor_lane(monkeypatch, tmp_path):
    captured = {"decision_queries": [], "run_queries": []}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        captured["decision_queries"].append((query, session_id))
        return "executor"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_queries"].append((agent_name, query, session_id, tools_description))
        if "was hast du fuer probleme" in query.lower():
            return "Gerade sehe ich diese Baustellen bei mir."
        if "# follow-up context" in query.lower():
            return "Dagegen kann ich diese Pfade haerten."
        return "fallback"

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    first = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "Was hast du fuer Probleme?",
                "session_id": "followup_lane",
            }
        )
    )
    second = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "und was kannst du dagegen tun",
                "session_id": "followup_lane",
            }
        )
    )

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert second["agent"] == "executor"
    assert len(captured["decision_queries"]) == 1
    assert captured["decision_queries"][0][0] == "Was hast du fuer Probleme?"
    followup_agent, followup_query, followup_session_id, followup_tools = captured["run_queries"][-1]
    assert followup_agent == "executor"
    assert followup_session_id == "followup_lane"
    assert followup_tools == "tools"
    assert "# FOLLOW-UP CONTEXT" in followup_query
    assert "last_agent: executor" in followup_query
    assert "session_id: followup_lane" in followup_query
    assert "last_user: Was hast du fuer Probleme?" in followup_query
    assert "last_assistant: Gerade sehe ich diese Baustellen bei mir." in followup_query
    assert "recent_agents: executor" in followup_query
    assert "recent_user_queries:" in followup_query
    assert "recent_assistant_replies:" in followup_query
    assert "# CURRENT USER QUERY" in followup_query
    assert "und was kannst du dagegen tun" in followup_query


async def test_canvas_chat_injects_live_location_context_for_location_queries(monkeypatch, tmp_path):
    captured = {}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])
    monkeypatch.setattr(
        mcp_server,
        "_get_location_snapshot",
        lambda: {
            "presence_status": "live",
            "usable_for_context": True,
            "has_coordinates": True,
            "display_name": "Alexanderplatz, Berlin, Deutschland",
            "locality": "Berlin",
            "accuracy_meters": 12.4,
            "captured_at": "2026-03-16T12:00:00Z",
            "received_at": "2026-03-16T12:00:02Z",
            "maps_url": "https://www.google.com/maps/search/?api=1&query=52.52,13.40",
        },
    )

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        captured["decision_query"] = query
        return "executor"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_query"] = query
        return "Du bist gerade in Berlin."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    response = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "Wo bin ich gerade?",
                "session_id": "loc_ctx_live",
            }
        )
    )

    assert response["status"] == "success"
    assert captured["decision_query"] == "Wo bin ich gerade?"
    assert "# LIVE LOCATION CONTEXT" in captured["run_query"]
    assert "presence_status: live" in captured["run_query"]
    assert "display_name: Alexanderplatz, Berlin, Deutschland" in captured["run_query"]


async def test_canvas_chat_injects_live_location_context_for_local_place_requests(monkeypatch, tmp_path):
    captured = {}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])
    monkeypatch.setattr(
        mcp_server,
        "_get_location_snapshot",
        lambda: {
            "presence_status": "live",
            "usable_for_context": True,
            "has_coordinates": True,
            "display_name": "Alexanderplatz, Berlin, Deutschland",
            "locality": "Berlin",
            "accuracy_meters": 12.4,
            "captured_at": "2026-03-16T12:00:00Z",
            "received_at": "2026-03-16T12:00:02Z",
            "maps_url": "https://www.google.com/maps/search/?api=1&query=52.52,13.40",
        },
    )

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        captured["decision_query"] = query
        return "executor"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_query"] = query
        return "Ich suche dir gleich Kaffee in der Naehe."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    response = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "Wo bekomme ich gerade Kaffee?",
                "session_id": "loc_ctx_coffee",
            }
        )
    )

    assert response["status"] == "success"
    assert captured["decision_query"] == "Wo bekomme ich gerade Kaffee?"
    assert "# LIVE LOCATION CONTEXT" in captured["run_query"]


async def test_canvas_chat_does_not_inject_stale_location_context(monkeypatch, tmp_path):
    captured = {}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])
    monkeypatch.setattr(
        mcp_server,
        "_get_location_snapshot",
        lambda: {
            "presence_status": "stale",
            "usable_for_context": False,
            "has_coordinates": True,
            "display_name": "Berlin",
        },
    )

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        return "executor"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_query"] = query
        return "Standort ist veraltet."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    response = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "Wo bin ich gerade?",
                "session_id": "loc_ctx_stale",
            }
        )
    )

    assert response["status"] == "success"
    assert "# LIVE LOCATION CONTEXT" not in captured["run_query"]


def test_followup_resolver_does_not_keep_visual_without_visual_intent():
    capsule = {
        "last_agent": "visual",
        "last_user": "oeffne booking und suche hotels",
        "last_assistant": "Resultatliste sichtbar",
    }

    assert mcp_server._resolve_followup_agent("und was jetzt", capsule) == "meta"
    assert mcp_server._resolve_followup_agent("und klick den button", capsule) == "visual"


def test_session_capsule_rolls_old_entries_into_summary(tmp_path, monkeypatch):
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("TIMUS_SESSION_ENTRY_LIMIT", "4")
    monkeypatch.setenv("TIMUS_SESSION_SUMMARY_CHAR_LIMIT", "800")
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])

    session_id = "capsule_rollup"
    for idx in range(8):
        role = "user" if idx % 2 == 0 else "assistant"
        agent = "executor" if role == "assistant" else ""
        mcp_server._append_chat_entry(
            session_id=session_id,
            role=role,
            text=f"Nachricht {idx}",
            ts=f"2026-03-14T19:5{idx}:00Z",
            agent=agent,
        )

    capsule = mcp_server._load_session_capsule(session_id)
    assert capsule["session_id"] == session_id
    assert len(capsule["entries"]) <= 4
    assert "Nachricht 0" in capsule["summary"]
    assert "Nachricht 1" in capsule["summary"]
    assert capsule["conversation_state"]["schema_version"] == 1
    assert capsule["conversation_state"]["session_id"] == session_id

    followup_capsule = mcp_server._build_followup_capsule(session_id)
    assert followup_capsule["last_agent"] == "executor"
    assert "Nachricht 6" in followup_capsule["recent_user_queries"][-1]
    assert "Nachricht 7" in followup_capsule["recent_assistant_replies"][-1]
    assert "Nachricht 0" in followup_capsule["session_summary"]
    assert followup_capsule["conversation_state"]["session_id"] == session_id

    augmented = mcp_server._augment_query_with_followup_capsule("und was jetzt", followup_capsule)
    assert "session_summary:" in augmented
    assert "recent_user_queries:" in augmented


def test_session_capsule_conversation_state_tracks_pending_followup_prompt(tmp_path, monkeypatch):
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))

    session_id = "capsule_state_sync"
    mcp_server._store_pending_followup_prompt_in_capsule(session_id, "Welche Option soll ich zuerst angehen?")

    capsule = mcp_server._load_session_capsule(session_id)
    state = capsule["conversation_state"]
    assert state["open_loop"] == "Welche Option soll ich zuerst angehen?"
    assert state["next_expected_step"] == "Welche Option soll ich zuerst angehen?"
    assert "pending_followup_prompt" in state["state_source"]

    mcp_server._store_pending_followup_prompt_in_capsule(session_id, "")
    capsule = mcp_server._load_session_capsule(session_id)
    state = capsule["conversation_state"]
    assert state["open_loop"] == ""
    assert state["next_expected_step"] == ""
    assert "pending_followup_prompt" not in state["state_source"]


def test_followup_capsule_includes_semantic_recall(tmp_path, monkeypatch):
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(
        mcp_server,
        "_semantic_recall_chat_turns",
        lambda **kwargs: [
            {
                "role": "assistant",
                "agent": "executor",
                "text": "Frueher habe ich den Visual-Pfad bereits als Hauptproblem markiert.",
                "distance": 0.08,
            }
        ],
    )

    mcp_server._append_chat_entry(
        session_id="semantic_followup",
        role="assistant",
        text="Gerade sehe ich diese Baustellen bei mir.",
        ts="2026-03-14T20:10:00Z",
        agent="executor",
    )
    capsule = mcp_server._build_followup_capsule(
        "semantic_followup",
        query="wie war nochmal dein plan fuer visual",
    )

    assert capsule["session_id"] == "semantic_followup"
    assert capsule["semantic_recall"]
    assert "Visual-Pfad" in capsule["semantic_recall"][0]["text"]

    augmented = mcp_server._augment_query_with_followup_capsule(
        "wie war nochmal dein plan fuer visual",
        capsule,
    )
    assert "semantic_recall:" in augmented
    assert "executor =>" in augmented


def test_followup_capsule_serializes_conversation_state_into_query_block(tmp_path, monkeypatch):
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))

    session_id = "conversation_state_followup"
    capsule = mcp_server._load_session_capsule(session_id)
    capsule["conversation_state"] = {
        "active_topic": "Weltlage und News-Qualitaet",
        "active_goal": "Echtzeit-Agenturmeldungen priorisieren",
        "open_loop": "Reuters und AP priorisieren",
        "next_expected_step": "Praeferenz bestaetigen",
        "turn_type_hint": "behavior_instruction",
        "preferences": ["Reuters zuerst", "AP zuerst"],
        "recent_corrections": ["Nicht auf Standort abdriften"],
    }
    mcp_server._store_session_capsule(capsule)

    followup_capsule = mcp_server._build_followup_capsule(session_id, query="und was jetzt")
    augmented = mcp_server._augment_query_with_followup_capsule("und was jetzt", followup_capsule)

    assert "conversation_state_active_topic: Weltlage und News-Qualitaet" in augmented
    assert "conversation_state_active_goal: Echtzeit-Agenturmeldungen priorisieren" in augmented
    assert "conversation_state_open_loop: Reuters und AP priorisieren" in augmented
    assert "conversation_state_turn_type_hint: behavior_instruction" in augmented
    assert "conversation_state_preferences: Reuters zuerst || AP zuerst" in augmented
    assert "conversation_state_recent_corrections: Nicht auf Standort abdriften" in augmented


def test_record_meta_turn_understanding_observations_emits_context_misread_suspected(monkeypatch):
    captured: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        mcp_server,
        "_record_chat_observation",
        lambda event_type, payload: captured.append((event_type, payload)),
    )

    mcp_server._record_meta_turn_understanding_observations(
        request_id="req_meta_risk",
        session_id="sess_meta_risk",
        classification={
            "dominant_turn_type": "followup",
            "response_mode": "resume_open_loop",
            "reason": "context_anchored_followup",
            "turn_understanding": {
                "turn_signals": ["followup"],
                "route_bias": "meta_only",
                "confidence": 0.41,
                "state_effects": {},
            },
            "meta_context_bundle": {
                "bundle_reason": "meta_context_rehydration",
                "context_slots": [
                    {"slot": "current_query", "priority": 1, "content": "ok fang an", "source": "current_user_query"},
                    {
                        "slot": "assistant_fallback_context",
                        "priority": 2,
                        "content": "Soll ich mit dem ersten Schritt anfangen?",
                        "source": "recent_assistant_replies",
                    },
                ],
                "suppressed_context": [],
                "confidence": 0.41,
            },
        },
    )

    assert any(event_type == "context_misread_suspected" for event_type, _ in captured)
    risk_payloads = [payload for event_type, payload in captured if event_type == "context_misread_suspected"]
    assert any("resume_mode_without_open_loop" in (payload.get("risk_reasons") or []) for payload in risk_payloads)


def test_record_meta_turn_understanding_observations_emits_topic_shift_and_state_update(monkeypatch):
    captured: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        mcp_server,
        "_record_chat_observation",
        lambda event_type, payload: captured.append((event_type, payload)),
    )

    mcp_server._record_meta_turn_understanding_observations(
        request_id="req_topic_shift",
        session_id="sess_topic_shift",
        classification={
            "dominant_turn_type": "new_task",
            "response_mode": "execute",
            "reason": "single_lane",
            "turn_understanding": {
                "turn_signals": ["new_work_request"],
                "route_bias": "route_normally",
                "confidence": 0.7,
                "state_effects": {"shift_active_topic": True},
            },
            "topic_shift_detected": True,
            "topic_state_transition": {
                "previous_topic": "aktuelle Weltlage und News-Qualitaet",
                "next_topic": "browser automation",
                "previous_goal": "Live-News",
                "next_goal": "UI-Workflows verstehen",
                "open_loop_state": "unchanged",
            },
            "meta_context_bundle": {
                "bundle_reason": "meta_context_rehydration",
                "context_slots": [
                    {"slot": "current_query", "priority": 1, "content": "lass uns ueber browser automation reden", "source": "current_user_query"},
                    {"slot": "conversation_state", "priority": 2, "content": "conversation_state: aktuelle Weltlage", "source": "conversation_state"},
                ],
                "suppressed_context": [],
                "confidence": 0.7,
            },
        },
        updated_state={
            "active_topic": "browser automation",
            "active_goal": "UI-Workflows verstehen",
            "open_loop": "",
            "next_expected_step": "",
            "open_questions": [],
            "turn_type_hint": "new_task",
        },
    )

    assert any(event_type == "topic_shift_detected" for event_type, _ in captured)
    assert any(event_type == "conversation_state_updated" for event_type, _ in captured)


async def test_canvas_chat_routes_topic_followup_to_executor(monkeypatch, tmp_path):
    captured = {"decision_queries": [], "run_queries": []}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        captured["decision_queries"].append((query, session_id))
        return "meta"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_queries"].append((agent_name, query, session_id, tools_description))
        if "tag gestern" in query.lower():
            return (
                "Mein Tag gestern? Ein Chaos.\n"
                "- Kamera-Start fehlgeschlagen — keine /dev/video* Geräte.\n"
                "- Telegram-Versand gescheitert — DNS-Auflösung kaputt."
            )
        return "Mit Telegram war gemeint: Telegram-Versand gescheitert — DNS-Auflösung kaputt."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    first = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "erzähl mir wie war dein tag gestern",
                "session_id": "topic_lane",
            }
        )
    )
    second = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "was war nochmal mit telegram ?",
                "session_id": "topic_lane",
            }
        )
    )

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert second["agent"] == "executor"
    assert len(captured["decision_queries"]) == 1
    followup_agent, followup_query, followup_session_id, _ = captured["run_queries"][-1]
    assert followup_agent == "executor"
    assert followup_session_id == "topic_lane"
    assert "topic_recall:" in followup_query
    assert "Telegram-Versand gescheitert" in followup_query
    assert "Kamera-Start fehlgeschlagen" not in followup_query.split("topic_recall:", 1)[1]


async def test_canvas_chat_routes_capability_followup_to_executor(monkeypatch, tmp_path):
    captured = {"decision_queries": [], "run_queries": []}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        captured["decision_queries"].append((query, session_id))
        return "meta"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_queries"].append((agent_name, query, session_id, tools_description))
        if "pizza bestellen" in query.lower():
            return (
                "Nein, ich kann keine Pizza bestellen. "
                "Ich habe keinen Zugang zu Lieferplattformen, keine Zahlungsdaten und keine Lieferadresse."
            )
        return (
            "Ja, theoretisch schon, aber nicht einfach spontan aus mir selbst heraus. "
            "Dafuer braeuchte ich Integrationen, Zahlungsfreigaben und eine bestaetigte Lieferadresse."
        )

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    first = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "kannst du eine pizza bestellen",
                "session_id": "pizza_lane",
            }
        )
    )
    second = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "könntest du dir das beibringen irgendwie",
                "session_id": "pizza_lane",
            }
        )
    )

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert second["agent"] == "executor"
    assert len(captured["decision_queries"]) == 1
    followup_agent, followup_query, followup_session_id, _ = captured["run_queries"][-1]
    assert followup_agent == "executor"
    assert followup_session_id == "pizza_lane"
    assert "# FOLLOW-UP CONTEXT" in followup_query
    assert "recent_assistant_replies:" in followup_query
    assert "Pizza bestellen" in followup_query or "Pizza bestellen".lower() in followup_query.lower()


async def test_canvas_chat_treats_result_extraction_as_lookup_followup(monkeypatch, tmp_path):
    captured = {"decision_queries": [], "run_queries": []}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        captured["decision_queries"].append((query, session_id))
        return "meta"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_queries"].append((agent_name, query, session_id, tools_description))
        if "aktuelle llm preise" in query.lower():
            return (
                "Zu den aktuellen Preisen habe ich gerade diese Treffer gefunden:\n"
                "Top-Treffer:\n"
                "- Alle KI-Modelle vergleichen – LLM Vergleich (2026) | https://www.byte.de/vergleich/llm\n"
                "Direkt gepruefte Quelle:\n"
                "- Alle KI-Modelle vergleichen – LLM Vergleich (2026) | https://www.byte.de/vergleich/llm"
            )
        return "Ich habe aus der Quelle die Preise extrahiert."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    first = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "so jetzt suche mir aktuelle llm preise der besten llms in abhänggkeit ihrer leistungen mach eine tabelle",
                "session_id": "lookup_followup_lane",
            }
        )
    )
    second = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "hole die preise heraus und liste sie mir aus",
                "session_id": "lookup_followup_lane",
            }
        )
    )

    assert first["status"] == "success"
    assert second["status"] == "success"
    followup_agent, followup_query, followup_session_id, _ = captured["run_queries"][-1]
    assert followup_agent == "meta"
    assert followup_session_id == "lookup_followup_lane"
    assert "# FOLLOW-UP CONTEXT" in followup_query
    assert "last_assistant:" in followup_query
    assert "https://www.byte.de/vergleich/llm" in followup_query
    assert "hole die preise heraus und liste sie mir aus" in followup_query


async def test_canvas_chat_routes_short_contextual_reply_to_same_lane(monkeypatch, tmp_path):
    captured = {"decision_queries": [], "run_queries": []}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        captured["decision_queries"].append((query, session_id))
        return "research"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_queries"].append((agent_name, query, session_id, tools_description))
        if "deepresearch agenten" in query.lower():
            return (
                "Ich kann zuerst die Query-Planung schaerfen oder das Relevanz-Gating haerten. "
                "Welche Option soll ich zuerst angehen?"
            )
        return "Ich starte mit der Query-Planung."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    first = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "pruef den deepresearch agenten",
                "session_id": "short_reply_lane",
            }
        )
    )
    second = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "die erste option",
                "session_id": "short_reply_lane",
            }
        )
    )

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert second["agent"] == "research"
    assert len(captured["decision_queries"]) == 1
    assert captured["decision_queries"][0][0] == "pruef den deepresearch agenten"
    followup_agent, followup_query, followup_session_id, _ = captured["run_queries"][-1]
    assert followup_agent == "research"
    assert followup_session_id == "short_reply_lane"
    assert "# FOLLOW-UP CONTEXT" in followup_query
    assert "last_agent: research" in followup_query
    assert "pending_followup_prompt:" in followup_query
    assert "Welche Option soll ich zuerst angehen?" in followup_query
    assert "die erste option" in followup_query


async def test_canvas_chat_routes_deferred_contextual_reply_to_same_meta_lane(monkeypatch, tmp_path):
    captured = {"decision_queries": [], "run_queries": []}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        captured["decision_queries"].append((query, session_id))
        return "meta"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        captured["run_queries"].append((agent_name, query, session_id, tools_description))
        if "telefonfunktion" in query.lower():
            return (
                "Was willst du?\n\n"
                "A) Lokalen Voice-Chat nutzen\n"
                "B) Twilio-Integration einrichten\n"
                "C) Telegram Voice-Integration"
            )
        return "Klar, überleg es dir in Ruhe. Wenn du dich entschieden hast, machen wir damit weiter."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    first = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "könntest du dir selbst eine telefonfunktion einrichten um mit mir zu telefonieren",
                "session_id": "phone_followup_lane",
            }
        )
    )
    second = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "muss ich mir noch überlegen",
                "session_id": "phone_followup_lane",
            }
        )
    )

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert second["agent"] == "meta"
    assert len(captured["decision_queries"]) == 1
    assert captured["decision_queries"][0][0] == "könntest du dir selbst eine telefonfunktion einrichten um mit mir zu telefonieren"
    followup_agent, followup_query, followup_session_id, _ = captured["run_queries"][-1]
    assert followup_agent == "meta"
    assert followup_session_id == "phone_followup_lane"
    assert "# FOLLOW-UP CONTEXT" in followup_query
    assert "pending_followup_prompt:" in followup_query
    assert "Was willst du?" in followup_query
    assert "muss ich mir noch überlegen" in followup_query


async def test_canvas_chat_persists_meta_turn_understanding_to_conversation_state(monkeypatch, tmp_path):
    captured = {"events": []}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])
    fake_memory_manager = SimpleNamespace(
        find_related_memories=lambda query, n_results=6: [
            {
                "content": "Reuters meldete neue Entwicklungen zur Weltlage.",
                "category": "news_archive",
                "relevance": 0.88,
            }
        ],
        get_behavior_hooks=lambda: ["Wichtige Aussagen mit Quellen belegen."],
        get_self_model_prompt=lambda: "Präferenzen: Wichtige Aussagen mit Quellen belegen.",
        persistent=SimpleNamespace(
            get_memory_items=lambda category: [SimpleNamespace(key="preference", value="Fakten und Quellen zuerst")]
            if category == "user_profile"
            else []
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "memory.memory_system",
        SimpleNamespace(memory_manager=fake_memory_manager),
    )
    monkeypatch.setattr(
        mcp_server,
        "_record_chat_observation",
        lambda event_type, payload: captured["events"].append((event_type, payload)),
    )

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None, request_id=None):
        return "meta"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        return "Verstanden. Ich priorisiere kuenftig Agenturquellen fuer aktuelle News."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    response = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "dann mach das in zukunft so dass du auf echtzeit agenturmeldungen zugreifst",
                "session_id": "turn_state_lane",
            }
        )
    )

    assert response["status"] == "success"
    assert response["agent"] == "meta"

    capsule = mcp_server._load_session_capsule("turn_state_lane")
    state = capsule["conversation_state"]
    assert state["turn_type_hint"] == "behavior_instruction"
    assert any("agenturmeldungen" in item.lower() for item in state["preferences"])
    assert state["topic_confidence"] > 0

    event_types = [event_type for event_type, _ in captured["events"]]
    assert "meta_turn_type_selected" in event_types
    assert "meta_response_mode_selected" in event_types
    assert "conversation_state_effects_derived" in event_types
    assert "context_rehydration_bundle_built" in event_types
    assert "topic_memory_attached" in event_types
    assert "preference_memory_attached" in event_types


async def test_canvas_chat_emits_context_slot_selection_and_suppression_events(monkeypatch, tmp_path):
    captured = {"events": []}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])
    monkeypatch.setattr(
        mcp_server,
        "_record_chat_observation",
        lambda event_type, payload: captured["events"].append((event_type, payload)),
    )

    session_id = "context_slot_obs_lane"
    mcp_server._append_chat_entry(
        session_id=session_id,
        role="user",
        text="wie stehts um die aktuelle weltlage",
        ts="2026-04-07T09:50:00Z",
    )
    mcp_server._append_chat_entry(
        session_id=session_id,
        role="assistant",
        text="Dein letzter bekannter Standort war in Offenbach am Main.",
        ts="2026-04-07T09:50:05Z",
        agent="executor",
    )

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None, request_id=None):
        return "meta"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        return "Verstanden. Ich fokussiere aktuelle News statt Standortkontext."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    response = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "nein ich meinte aktuelle news",
                "session_id": session_id,
            }
        )
    )

    assert response["status"] == "success"
    event_types = [event_type for event_type, _ in captured["events"]]
    assert "context_slot_selected" in event_types
    assert "context_slot_suppressed" in event_types
    assert any(
        payload.get("reason") == "location_context_without_current_evidence"
        for event_type, payload in captured["events"]
        if event_type == "context_slot_suppressed"
    )


async def test_canvas_chat_logs_completed_interaction_to_memory(monkeypatch, tmp_path):
    captured = {"memory_logs": []}
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])
    monkeypatch.setattr(
        mcp_server,
        "_log_chat_interaction",
        lambda **kwargs: captured["memory_logs"].append(kwargs),
    )

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None):
        return "meta"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        return "Ich habe den Kontext gespeichert. Was soll ich als Nächstes prüfen?"

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    response = await mcp_server.canvas_chat(
        _FakeRequest(
            {
                "query": "merk dir diesen chatkontext",
                "session_id": "memory_logging_lane",
            }
        )
    )

    assert response["status"] == "success"
    assert len(captured["memory_logs"]) == 1
    logged = captured["memory_logs"][0]
    assert logged["session_id"] == "memory_logging_lane"
    assert logged["user_input"] == "merk dir diesen chatkontext"
    assert logged["assistant_response"] == "Ich habe den Kontext gespeichert. Was soll ich als Nächstes prüfen?"
    assert logged["agent"] == "meta"
    assert logged["metadata"]["dispatcher_query_kind"] == "plain"
    assert logged["metadata"]["pending_followup_prompt"] == "Ich habe den Kontext gespeichert. Was soll ich als Nächstes prüfen?"

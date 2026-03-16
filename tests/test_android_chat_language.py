import sys
from types import SimpleNamespace

from server import mcp_server


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


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

    followup_capsule = mcp_server._build_followup_capsule(session_id)
    assert followup_capsule["last_agent"] == "executor"
    assert "Nachricht 6" in followup_capsule["recent_user_queries"][-1]
    assert "Nachricht 7" in followup_capsule["recent_assistant_replies"][-1]
    assert "Nachricht 0" in followup_capsule["session_summary"]

    augmented = mcp_server._augment_query_with_followup_capsule("und was jetzt", followup_capsule)
    assert "session_summary:" in augmented
    assert "recent_user_queries:" in augmented


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

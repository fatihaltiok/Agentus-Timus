import sys
from types import SimpleNamespace

from server import mcp_server


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


async def test_canvas_chat_honors_response_language_german(monkeypatch):
    captured = {}

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


async def test_canvas_chat_routes_followup_to_same_executor_lane(monkeypatch):
    captured = {"decision_queries": [], "run_queries": []}
    mcp_server._chat_history.clear()

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
    assert "last_user: Was hast du fuer Probleme?" in followup_query
    assert "last_assistant: Gerade sehe ich diese Baustellen bei mir." in followup_query
    assert "# CURRENT USER QUERY" in followup_query
    assert "und was kannst du dagegen tun" in followup_query


def test_followup_resolver_does_not_keep_visual_without_visual_intent():
    capsule = {
        "last_agent": "visual",
        "last_user": "oeffne booking und suche hotels",
        "last_assistant": "Resultatliste sichtbar",
    }

    assert mcp_server._resolve_followup_agent("und was jetzt", capsule) == "meta"
    assert mcp_server._resolve_followup_agent("und klick den button", capsule) == "visual"

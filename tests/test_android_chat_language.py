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

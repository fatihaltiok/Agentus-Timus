import asyncio
import json
from types import SimpleNamespace

import pytest

from gateway import telegram_gateway
from orchestration.feedback_engine import FeedbackEngine
from utils.telegram_notify import build_feedback_callback_data


class _FakeMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.replies = []
        self.chat = SimpleNamespace(send_action=self._send_action)

    async def reply_text(self, text, parse_mode=None, reply_markup=None):
        self.replies.append({"text": text, "parse_mode": parse_mode, "reply_markup": reply_markup})
        return SimpleNamespace(delete=self._delete, edit_text=self._edit_text)

    async def reply_voice(self, voice=None, caption=None):
        self.replies.append({"voice": True, "caption": caption})

    async def reply_photo(self, photo=None, caption=None):
        self.replies.append({"photo": True, "caption": caption})

    async def reply_document(self, document=None, filename=None, caption=None):
        self.replies.append({"document": filename, "caption": caption})

    async def _send_action(self, action):
        return None

    async def _delete(self):
        return None

    async def _edit_text(self, text, parse_mode=None):
        self.replies.append({"edited_text": text, "parse_mode": parse_mode})


class _FakeUser:
    def __init__(self, user_id: int = 42):
        self.id = user_id
        self.username = "tester"
        self.first_name = "Test"


class _FakeUpdate:
    def __init__(self, text: str = ""):
        self.effective_user = _FakeUser()
        self.message = _FakeMessage(text=text)
        self.callback_query = None


class _FakeCallbackQuery:
    def __init__(self, data: str):
        self.data = data
        self.answers = []

    async def answer(self, text):
        self.answers.append(text)


@pytest.mark.asyncio
async def test_handle_message_uses_feedback_reply(monkeypatch):
    update = _FakeUpdate(text="was kannst du alles")
    context = SimpleNamespace(bot_data={"tools_desc": ""})
    calls = []

    async def _fake_reply_with_feedback(update_obj, **kwargs):
        calls.append(kwargs)

    async def _fake_run_agent(agent_name, query, tools_description, session_id=None):
        return "Antwort von Timus"

    async def _fake_keep_typing(update_obj):
        await asyncio.sleep(0)

    monkeypatch.setattr(telegram_gateway, "_is_allowed", lambda _: True)
    monkeypatch.setattr(telegram_gateway, "_get_session", lambda _: "tg_42_test")
    monkeypatch.setattr(telegram_gateway, "_reply_with_feedback", _fake_reply_with_feedback)
    monkeypatch.setattr(telegram_gateway, "_try_send_image", lambda *args, **kwargs: asyncio.sleep(0, result=False))
    monkeypatch.setattr(telegram_gateway, "_try_send_document", lambda *args, **kwargs: asyncio.sleep(0, result=False))
    monkeypatch.setattr(telegram_gateway, "_keep_typing", _fake_keep_typing)
    monkeypatch.setattr(
        "main_dispatcher.get_agent_decision",
        lambda _text, session_id=None: asyncio.sleep(0, result="meta"),
    )
    monkeypatch.setattr("main_dispatcher.run_agent", _fake_run_agent)

    await telegram_gateway.handle_message(update, context)

    assert len(calls) == 1
    assert calls[0]["text"] == "Antwort von Timus"
    assert {"namespace": "dispatcher_agent", "key": "meta"} in calls[0]["feedback_targets"]
    assert calls[0]["context"]["source"] == "telegram_reply"


@pytest.mark.asyncio
async def test_handle_message_records_request_lifecycle_with_request_id(monkeypatch):
    update = _FakeUpdate(text="was kostet benzin heute")
    context = SimpleNamespace(bot_data={"tools_desc": ""})
    observed = []

    async def _fake_reply_with_feedback(update_obj, **kwargs):
        return None

    async def _fake_run_agent(agent_name, query, tools_description, session_id=None):
        assert agent_name == "meta"
        assert session_id == "tg_42_test"
        return "Antwort von Timus"

    async def _fake_keep_typing(update_obj):
        await asyncio.sleep(0)

    async def _fake_get_agent_decision(_text, session_id=None, request_id=None):
        assert session_id == "tg_42_test"
        assert str(request_id).startswith("req_")
        return "meta"

    monkeypatch.setattr(telegram_gateway, "_is_allowed", lambda _: True)
    monkeypatch.setattr(telegram_gateway, "_get_session", lambda _: "tg_42_test")
    monkeypatch.setattr(telegram_gateway, "_reply_with_feedback", _fake_reply_with_feedback)
    monkeypatch.setattr(telegram_gateway, "_try_send_image", lambda *args, **kwargs: asyncio.sleep(0, result=False))
    monkeypatch.setattr(telegram_gateway, "_try_send_document", lambda *args, **kwargs: asyncio.sleep(0, result=False))
    monkeypatch.setattr(telegram_gateway, "_keep_typing", _fake_keep_typing)
    monkeypatch.setattr(telegram_gateway, "record_autonomy_observation", lambda event, payload: observed.append((event, dict(payload))))
    monkeypatch.setattr("main_dispatcher.get_agent_decision", _fake_get_agent_decision)
    monkeypatch.setattr("main_dispatcher.run_agent", _fake_run_agent)

    await telegram_gateway.handle_message(update, context)

    assert [event for event, _payload in observed] == [
        "chat_request_received",
        "request_route_selected",
        "chat_request_completed",
    ]
    request_ids = {payload["request_id"] for _event, payload in observed}
    assert len(request_ids) == 1
    assert next(iter(request_ids)).startswith("req_")
    assert all(payload["session_id"] == "tg_42_test" for _event, payload in observed)
    assert all(payload["source"] == "telegram_chat" for _event, payload in observed)


@pytest.mark.asyncio
async def test_callback_query_short_token_records_feedback(monkeypatch, tmp_path):
    engine = FeedbackEngine(db_path=tmp_path / "feedback.db")
    token = engine.register_feedback_request(
        action_id="reply-42",
        context={"source": "telegram_reply", "dispatcher_agent": "meta"},
        feedback_targets=[{"namespace": "dispatcher_agent", "key": "meta"}],
    )
    update = _FakeUpdate()
    update.callback_query = _FakeCallbackQuery(build_feedback_callback_data("positive", token))

    monkeypatch.setattr(telegram_gateway, "_is_allowed", lambda _: True)
    monkeypatch.setattr("orchestration.feedback_engine.get_feedback_engine", lambda: engine)

    await telegram_gateway.handle_callback_query(update, None)

    events = engine.get_recent_events(limit=5)
    assert len(events) == 1
    assert events[0].signal == "positive"
    assert events[0].context["source"] == "telegram_reply"
    assert engine.get_target_score("dispatcher_agent", "meta") > 1.0
    assert any("gespeichert" in item for item in update.callback_query.answers)

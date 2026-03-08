import asyncio
import json
from types import SimpleNamespace

import pytest

from agent.prompts import DEVELOPER_SYSTEM_PROMPT
from gateway import telegram_gateway
from orchestration.autonomous_runner import _self_modify_feature_enabled
from orchestration.self_healing_engine import PLAYBOOK_CODE_FIX, SelfHealingEngine
from server import mcp_server


def test_tool_module_registered():
    assert "tools.code_editor_tool.tool" in mcp_server.TOOL_MODULES


def test_developer_prompt_mentions_apply_code_edit():
    assert "apply_code_edit" in DEVELOPER_SYSTEM_PROMPT
    assert "Mercury Edit" in DEVELOPER_SYSTEM_PROMPT


def test_self_healing_has_code_fix_playbook():
    engine = SelfHealingEngine()
    playbook = engine._playbook_template(PLAYBOOK_CODE_FIX, component="code", signal="syntax_error")
    assert "SelfModifierEngine.modify_file()" in " ".join(playbook["steps"])


def test_autonomous_runner_self_modify_flag(monkeypatch):
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SELF_MODIFY_ENABLED", "true")
    assert _self_modify_feature_enabled() is True


class _FakeQuery:
    def __init__(self, data: str):
        self.data = data
        self.answers = []

    async def answer(self, text):
        self.answers.append(text)


class _FakeUser:
    def __init__(self, user_id: int = 1):
        self.id = user_id


class _FakeUpdate:
    def __init__(self, data: str):
        self.callback_query = _FakeQuery(data)
        self.effective_user = _FakeUser()


class _FakeEngine:
    async def approve_pending(self, pending_id: str, approver: str = ""):
        return SimpleNamespace(status="success")

    async def reject_pending(self, pending_id: str, approver: str = ""):
        return SimpleNamespace(status="blocked")


@pytest.mark.asyncio
async def test_callback_query_approves_code_edit(monkeypatch):
    update = _FakeUpdate(json.dumps({"type": "code_edit_approve", "pid": "abc"}))
    monkeypatch.setattr(telegram_gateway, "_is_allowed", lambda _: True)
    monkeypatch.setattr("orchestration.self_modifier_engine.get_self_modifier_engine", lambda: _FakeEngine())
    await telegram_gateway.handle_callback_query(update, None)
    assert any("angewendet" in msg for msg in update.callback_query.answers)


@pytest.mark.asyncio
async def test_callback_query_rejects_code_edit(monkeypatch):
    update = _FakeUpdate(json.dumps({"type": "code_edit_reject", "pid": "abc"}))
    monkeypatch.setattr(telegram_gateway, "_is_allowed", lambda _: True)
    monkeypatch.setattr("orchestration.self_modifier_engine.get_self_modifier_engine", lambda: _FakeEngine())
    await telegram_gateway.handle_callback_query(update, None)
    assert any("abgelehnt" in msg for msg in update.callback_query.answers)


@pytest.mark.asyncio
async def test_attempt_code_fix_uses_self_modifier_engine(monkeypatch):
    class _Modifier:
        async def modify_file(self, **kwargs):
            return SimpleNamespace(status="success")

    monkeypatch.setattr("orchestration.self_modifier_engine.get_self_modifier_engine", lambda: _Modifier())
    result = await SelfHealingEngine().attempt_code_fix(file_path="tools/x.py", error_text="ImportError: x")
    assert result["ok"] is True
    assert result["status"] == "success"

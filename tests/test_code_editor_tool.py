import asyncio
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from tools.code_editor_tool import tool as editor


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json, headers):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse({"choices": [{"message": {"content": "def answer():\n    return 42\n"}}]})


def test_build_mercury_edit_prompt_contains_required_tags():
    prompt = editor.build_mercury_edit_prompt("print('a')", "change this")
    assert "<|original_code|>" in prompt
    assert "<|/original_code|>" in prompt
    assert "<|update_snippet|>" in prompt
    assert "change this" in prompt


def test_safety_check_allows_whitelisted_path(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "PROJECT_ROOT", tmp_path)
    (tmp_path / "tools").mkdir()
    result = editor.safety_check("tools/sample.py")
    assert result["relative_path"] == "tools/sample.py"


def test_safety_check_rejects_never_modify():
    with pytest.raises(PermissionError):
        editor.safety_check("agent/base_agent.py")


def test_validate_code_syntax_valid_python():
    result = editor.validate_code_syntax("def ok():\n    return 1\n")
    assert result["valid"] is True


def test_validate_code_syntax_invalid_python():
    result = editor.validate_code_syntax("def broken(:\n")
    assert result["valid"] is False
    assert "SyntaxError" in result["error"]


def test_list_modifiable_files_returns_whitelist_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(editor, "MODIFIABLE_WHITELIST", ["tools/", "agent/prompts.py"])
    monkeypatch.setattr(editor, "NEVER_MODIFY", ["tools/code_editor_tool/"])
    (tmp_path / "tools" / "x").mkdir(parents=True)
    (tmp_path / "tools" / "x" / "tool.py").write_text("pass", encoding="utf-8")
    (tmp_path / "agent").mkdir(parents=True)
    (tmp_path / "agent" / "prompts.py").write_text("PROMPT = ''", encoding="utf-8")

    files = editor.list_modifiable_files()["files"]
    assert "tools/x/tool.py" in files
    assert "agent/prompts.py" in files


@pytest.mark.asyncio
async def test_apply_code_edit_formats_request_and_returns_modified_code(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "PROJECT_ROOT", tmp_path)
    target = tmp_path / "tools" / "email_tool" / "tool.py"
    target.parent.mkdir(parents=True)
    target.write_text("def old():\n    return 1\n", encoding="utf-8")
    monkeypatch.setenv("INCEPTION_API_KEY", "secret")
    calls = []

    class _Client(_FakeAsyncClient):
        async def post(self, url, json, headers):
            calls.append({"url": url, "json": json, "headers": headers})
            return await super().post(url, json, headers)

    monkeypatch.setattr(editor.httpx, "AsyncClient", _Client)
    result = await editor.apply_code_edit("tools/email_tool/tool.py", "return 42")

    assert result["success"] is True
    assert result["file_path"] == "tools/email_tool/tool.py"
    assert result["modified_code"].startswith("def answer")
    payload = calls[0]["json"]
    assert payload["model"] == editor.MERCURY_MODEL_NAME
    assert isinstance(payload["messages"], list)
    assert payload["messages"][0]["role"] == "user"
    content = payload["messages"][0]["content"]
    assert "<|original_code|>" in content
    assert "<|update_snippet|>" in content


@pytest.mark.asyncio
async def test_apply_code_edit_rejects_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("INCEPTION_API_KEY", "secret")
    with pytest.raises(FileNotFoundError):
        await editor.apply_code_edit("tools/nope/tool.py", "fix")


@pytest.mark.asyncio
async def test_apply_code_edit_returns_error_on_invalid_syntax(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "PROJECT_ROOT", tmp_path)
    target = tmp_path / "tools" / "x.py"
    target.parent.mkdir(parents=True)
    target.write_text("def old():\n    return 1\n", encoding="utf-8")
    monkeypatch.setenv("INCEPTION_API_KEY", "secret")

    class _Client(_FakeAsyncClient):
        async def post(self, url, json, headers):
            return _FakeResponse({"choices": [{"message": {"content": "def broken(:\n"}}]})

    monkeypatch.setattr(editor.httpx, "AsyncClient", _Client)
    result = await editor.apply_code_edit("tools/x.py", "break it")
    assert result["success"] is False
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_apply_code_edit_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "PROJECT_ROOT", tmp_path)
    target = tmp_path / "tools" / "x.py"
    target.parent.mkdir(parents=True)
    target.write_text("def old():\n    return 1\n", encoding="utf-8")
    monkeypatch.delenv("INCEPTION_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        await editor.apply_code_edit("tools/x.py", "change")


@pytest.mark.asyncio
async def test_core_file_flag_is_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("INCEPTION_API_KEY", "secret")
    target = tmp_path / "agent" / "agents" / "meta.py"
    target.parent.mkdir(parents=True)
    target.write_text("def old():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(editor.httpx, "AsyncClient", _FakeAsyncClient)
    result = await editor.apply_code_edit("agent/agents/meta.py", "change")
    assert result["is_core"] is True


@given(st.text(min_size=1, max_size=40))
def test_hypothesis_normalized_paths_stay_relative(path_text: str):
    normalized = editor._normalize_relative_path(path_text)
    assert not normalized.startswith("/")
    assert "\\" not in normalized

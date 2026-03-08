import sqlite3
from pathlib import Path

import deal
import pytest
from hypothesis import given, strategies as st

from orchestration.self_modifier_engine import SelfModifierEngine, SelfModifyResult
from tools.code_editor_tool import tool as editor


@deal.pre(lambda result: result.status in {"success", "pending_approval", "rolled_back", "blocked", "error"})
@deal.post(lambda r: r in {"success", "pending_approval", "rolled_back", "blocked", "error"})
def _result_status_value(result: SelfModifyResult) -> str:
    return result.status


@deal.post(lambda r: isinstance(r, bool))
def _core_gate_value(path: str) -> bool:
    return editor.requires_core_approval(path)


class _DummyAwaitable:
    def __init__(self, result=None):
        self.result = result

    def __await__(self):
        async def _inner():
            return self.result
        return _inner().__await__()


@pytest.mark.asyncio
async def test_safety_gate_blocks_never_modify(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    engine = SelfModifierEngine(db_path)
    result = await engine.modify_file("agent/base_agent.py", "do not touch")
    assert result.status == "blocked"


@pytest.mark.asyncio
async def test_git_backup_saved_before_edit(tmp_path, monkeypatch):
    project = tmp_path
    target = project / "tools" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("def old():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(editor, "PROJECT_ROOT", project)
    monkeypatch.setattr("orchestration.self_modifier_engine.PROJECT_ROOT", project)
    engine = SelfModifierEngine(project / "data" / "timus_memory.db")
    monkeypatch.setattr("orchestration.self_modifier_engine.request_code_edit", lambda **_: _DummyAwaitable({"success": True, "modified_code": "def new():\n    return 2\n"}))
    monkeypatch.setattr(engine, "_run_tests", lambda _: "skipped")
    monkeypatch.setattr(engine, "_write_blackboard", lambda *args, **kwargs: None)
    result = await engine.modify_file("tools/demo.py", "rename")
    assert result.status == "success"
    assert Path(result.backup_ref).exists()


@pytest.mark.asyncio
async def test_rollback_restores_original_on_failed_tests(tmp_path, monkeypatch):
    project = tmp_path
    target = project / "tools" / "demo.py"
    target.parent.mkdir(parents=True)
    original = "def old():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    monkeypatch.setattr(editor, "PROJECT_ROOT", project)
    monkeypatch.setattr("orchestration.self_modifier_engine.PROJECT_ROOT", project)
    engine = SelfModifierEngine(project / "data" / "timus_memory.db")
    monkeypatch.setattr("orchestration.self_modifier_engine.request_code_edit", lambda **_: _DummyAwaitable({"success": True, "modified_code": "def new():\n    return 2\n"}))
    monkeypatch.setattr(engine, "_run_tests", lambda _: "failed")
    monkeypatch.setattr(engine, "_write_blackboard", lambda *args, **kwargs: None)

    result = await engine.modify_file("tools/demo.py", "rename")

    assert result.status == "rolled_back"
    assert target.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_core_files_go_pending_approval(tmp_path, monkeypatch):
    project = tmp_path
    target = project / "agent" / "agents" / "meta.py"
    target.parent.mkdir(parents=True)
    target.write_text("def old():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(editor, "PROJECT_ROOT", project)
    monkeypatch.setattr("orchestration.self_modifier_engine.PROJECT_ROOT", project)
    monkeypatch.setenv("SELF_MODIFY_REQUIRE_APPROVAL", "true")
    engine = SelfModifierEngine(project / "data" / "timus_memory.db")
    monkeypatch.setattr("orchestration.self_modifier_engine.request_code_edit", lambda **_: _DummyAwaitable({"success": True, "modified_code": "def new():\n    return 2\n"}))
    sent = {}

    async def _fake_telegram(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(engine, "_telegram_approval_request", _fake_telegram)
    monkeypatch.setattr(engine, "_write_blackboard", lambda *args, **kwargs: None)
    result = await engine.modify_file("agent/agents/meta.py", "rename")

    assert result.status == "pending_approval"
    assert sent["file_path"] == "agent/agents/meta.py"


@pytest.mark.asyncio
async def test_non_core_file_written_without_approval(tmp_path, monkeypatch):
    project = tmp_path
    target = project / "tools" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("def old():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(editor, "PROJECT_ROOT", project)
    monkeypatch.setattr("orchestration.self_modifier_engine.PROJECT_ROOT", project)
    monkeypatch.setenv("SELF_MODIFY_REQUIRE_APPROVAL", "true")
    engine = SelfModifierEngine(project / "data" / "timus_memory.db")
    monkeypatch.setattr("orchestration.self_modifier_engine.request_code_edit", lambda **_: _DummyAwaitable({"success": True, "modified_code": "def new():\n    return 2\n"}))
    monkeypatch.setattr(engine, "_run_tests", lambda _: "skipped")
    monkeypatch.setattr(engine, "_write_blackboard", lambda *args, **kwargs: None)
    result = await engine.modify_file("tools/demo.py", "rename")
    assert result.status == "success"
    assert "def new" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_approve_pending_writes_file_and_clears_queue(tmp_path, monkeypatch):
    project = tmp_path
    monkeypatch.setattr(editor, "PROJECT_ROOT", project)
    monkeypatch.setattr("orchestration.self_modifier_engine.PROJECT_ROOT", project)
    engine = SelfModifierEngine(project / "data" / "timus_memory.db")
    target = project / "agent" / "agents" / "meta.py"
    target.parent.mkdir(parents=True)
    target.write_text("def old():\n    return 1\n", encoding="utf-8")
    backup = engine._save_git_backup("agent/agents/meta.py", target.read_text(encoding="utf-8"))
    pid = engine._store_pending(
        file_path="agent/agents/meta.py",
        original="def old():\n    return 1\n",
        modified="def new():\n    return 2\n",
        change_description="rename",
        update_snippet="rename",
        backup_ref=backup,
        session_id="s1",
        require_tests=False,
    )
    monkeypatch.setattr(engine, "_write_blackboard", lambda *args, **kwargs: None)
    result = await engine.approve_pending(pid)
    assert result.status == "success"
    assert engine.pending_count() == 0
    assert "def new" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_reject_pending_marks_blocked(tmp_path, monkeypatch):
    project = tmp_path
    monkeypatch.setattr(editor, "PROJECT_ROOT", project)
    monkeypatch.setattr("orchestration.self_modifier_engine.PROJECT_ROOT", project)
    engine = SelfModifierEngine(project / "data" / "timus_memory.db")
    pid = engine._store_pending(
        file_path="agent/agents/meta.py",
        original="x",
        modified="y",
        change_description="rename",
        update_snippet="rename",
        backup_ref="backup",
        session_id="s1",
        require_tests=True,
    )
    monkeypatch.setattr(engine, "_write_blackboard", lambda *args, **kwargs: None)
    result = await engine.reject_pending(pid)
    assert result.status == "blocked"
    assert engine.pending_count() == 0


def test_self_modify_log_written(tmp_path):
    engine = SelfModifierEngine(tmp_path / "timus_memory.db")
    engine._audit_log("aid", "tools/demo.py", "change", "success", "backup", "session")
    with sqlite3.connect(tmp_path / "timus_memory.db") as conn:
        row = conn.execute("SELECT file_path, status FROM self_modify_log WHERE id = 'aid'").fetchone()
    assert row == ("tools/demo.py", "success")


def test_run_cycle_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTONOMY_SELF_MODIFY_ENABLED", raising=False)
    engine = SelfModifierEngine(tmp_path / "memory.db")
    summary = engine.run_cycle()
    assert summary["status"] == "disabled"


def test_run_cycle_enabled_reports_max_per_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTONOMY_SELF_MODIFY_ENABLED", "true")
    monkeypatch.setenv("SELF_MODIFY_MAX_PER_CYCLE", "5")
    engine = SelfModifierEngine(tmp_path / "memory.db")
    summary = engine.run_cycle()
    assert summary["status"] == "enabled"
    assert summary["max_per_cycle"] == 5


@given(st.sampled_from(["agent/agents/meta.py", "tools/x.py", "orchestration/demo.py"]))
def test_hypothesis_core_gate_returns_bool(path: str):
    assert isinstance(_core_gate_value(path), bool)


@given(st.sampled_from(["success", "pending_approval", "rolled_back", "blocked", "error"]))
def test_hypothesis_result_status_contract(status: str):
    result = SelfModifyResult(status, "tools/x.py", "change", "backup", "skipped", "aid")
    assert _result_status_value(result) == status

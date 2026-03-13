from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestration.self_modifier_engine import SelfModifierEngine
from tools.code_editor_tool import tool as editor


class _DummyAwaitable:
    def __init__(self, result=None):
        self.result = result

    def __await__(self):
        async def _inner():
            return self.result

        return _inner().__await__()


@pytest.mark.asyncio
async def test_change_memory_written_on_success(tmp_path, monkeypatch):
    project = tmp_path
    target = project / "orchestration" / "meta_orchestration.py"
    target.parent.mkdir(parents=True)
    target.write_text("def old():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(editor, "PROJECT_ROOT", project)
    monkeypatch.setattr("orchestration.self_modifier_engine.PROJECT_ROOT", project)
    engine = SelfModifierEngine(project / "data" / "timus_memory.db")
    monkeypatch.setattr(
        "orchestration.self_modifier_engine.request_code_edit",
        lambda **_: _DummyAwaitable({"success": True, "modified_code": "def new():\n    return 2\n"}),
    )
    monkeypatch.setattr(
        "orchestration.self_modifier_engine.run_self_modification_verification",
        lambda **_: SimpleNamespace(status="passed", summary="py_compile:passed"),
    )
    monkeypatch.setattr(
        "orchestration.self_modifier_engine.run_self_modification_canary",
        lambda **_: SimpleNamespace(state="passed", summary="production_gates:passed", rollback_required=False),
    )
    monkeypatch.setattr(engine, "_write_blackboard", lambda *args, **kwargs: None)

    result = await engine.modify_file("orchestration/meta_orchestration.py", "rename")

    assert result.status == "success"
    rows = engine.list_change_memory(limit=10)
    assert len(rows) == 1
    assert rows[0]["file_path"] == "orchestration/meta_orchestration.py"
    assert rows[0]["outcome_status"] == "success"
    assert rows[0]["rollback_applied"] == 0
    assert rows[0]["regression_detected"] == 0


@pytest.mark.asyncio
async def test_change_memory_marks_regression_on_canary_rollback(tmp_path, monkeypatch):
    project = tmp_path
    target = project / "orchestration" / "meta_orchestration.py"
    target.parent.mkdir(parents=True)
    original = "def old():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    monkeypatch.setattr(editor, "PROJECT_ROOT", project)
    monkeypatch.setattr("orchestration.self_modifier_engine.PROJECT_ROOT", project)
    engine = SelfModifierEngine(project / "data" / "timus_memory.db")
    monkeypatch.setattr(
        "orchestration.self_modifier_engine.request_code_edit",
        lambda **_: _DummyAwaitable({"success": True, "modified_code": "def new():\n    return 2\n"}),
    )
    monkeypatch.setattr(
        "orchestration.self_modifier_engine.run_self_modification_verification",
        lambda **_: SimpleNamespace(status="passed", summary="py_compile:passed"),
    )
    monkeypatch.setattr(
        "orchestration.self_modifier_engine.run_self_modification_canary",
        lambda **_: SimpleNamespace(state="failed", summary="production_gates:failed", rollback_required=True),
    )
    monkeypatch.setattr(engine, "_write_blackboard", lambda *args, **kwargs: None)

    result = await engine.modify_file("orchestration/meta_orchestration.py", "rename")

    assert result.status == "rolled_back"
    rows = engine.list_change_memory(limit=10)
    assert len(rows) == 1
    assert rows[0]["outcome_status"] == "rolled_back"
    assert rows[0]["rollback_applied"] == 1
    assert rows[0]["regression_detected"] == 1


def test_change_memory_summary_aggregates_latest_outcomes(tmp_path):
    engine = SelfModifierEngine(tmp_path / "timus_memory.db")
    engine._record_change_memory(
        change_key="c1",
        audit_id="a1",
        file_path="orchestration/meta_orchestration.py",
        change_description="ok",
        policy_zone="meta_orchestration",
        risk_level="low",
        risk_reason="safe",
        test_result="passed",
        verification_summary="py_compile:passed",
        canary_state="passed",
        canary_summary="production_gates:passed",
        outcome_status="success",
        rollback_applied=False,
        regression_detected=False,
        workspace_mode="mirror_copy",
        session_id="s1",
    )
    engine._record_change_memory(
        change_key="c2",
        audit_id="a2",
        file_path="orchestration/meta_orchestration.py",
        change_description="bad",
        policy_zone="meta_orchestration",
        risk_level="low",
        risk_reason="safe",
        test_result="failed",
        verification_summary="pytest_targeted:failed",
        canary_state="",
        canary_summary="",
        outcome_status="rolled_back",
        rollback_applied=True,
        regression_detected=True,
        workspace_mode="mirror_copy",
        session_id="s2",
    )

    summary = engine.summarize_change_memory(limit=10)
    assert summary.total == 2
    assert summary.success_count == 1
    assert summary.rolled_back_count == 1
    assert summary.rollback_count == 1
    assert summary.regression_count == 1

from __future__ import annotations

from orchestration.self_hardening_execution_policy import evaluate_self_hardening_execution


def test_self_hardening_execution_developer_task_routes_to_development() -> None:
    decision = evaluate_self_hardening_execution(
        requested_fix_mode="developer_task",
        recommended_agent="development",
        target_file_path="agent/base_agent.py",
        change_type="orchestration_policy",
    )
    assert decision.allow_task is True
    assert decision.allow_self_modify is False
    assert decision.route_target == "development"
    assert decision.effective_fix_mode == "developer_task"


def test_self_hardening_execution_allowed_self_modify_routes_to_self_modify() -> None:
    decision = evaluate_self_hardening_execution(
        requested_fix_mode="self_modify_safe",
        recommended_agent="development",
        target_file_path="tools/deep_research/tool.py",
        change_type="report_quality_guardrails",
    )
    assert decision.allow_task is True
    assert decision.allow_self_modify is True
    assert decision.route_target == "self_modify"
    assert decision.effective_fix_mode == "self_modify_safe"
    assert "tests/test_deep_research_report_quality.py" in decision.required_test_targets


def test_self_hardening_execution_blocked_self_modify_downgrades_to_development() -> None:
    decision = evaluate_self_hardening_execution(
        requested_fix_mode="self_modify_safe",
        recommended_agent="development",
        target_file_path="agent/agents/executor.py",
        change_type="orchestration_policy",
    )
    assert decision.allow_task is True
    assert decision.allow_self_modify is False
    assert decision.route_target == "development"
    assert decision.effective_fix_mode == "developer_task"
    assert "self_modify_policy_blocked" in decision.reason


def test_self_hardening_execution_human_only_creates_no_task() -> None:
    decision = evaluate_self_hardening_execution(
        requested_fix_mode="human_only",
        recommended_agent="development",
    )
    assert decision.allow_task is False
    assert decision.route_target == ""


def test_self_hardening_execution_rollout_observe_only_disables_developer_task(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HARDENING_ROLLOUT_STAGE", "observe_only")
    decision = evaluate_self_hardening_execution(
        requested_fix_mode="developer_task",
        recommended_agent="development",
        target_file_path="agent/base_agent.py",
        change_type="orchestration_policy",
    )
    assert decision.allow_task is False
    assert decision.rollout_stage == "observe_only"


def test_self_hardening_execution_rollout_developer_only_downgrades_self_modify(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_SELF_HARDENING_ROLLOUT_STAGE", "developer_only")
    decision = evaluate_self_hardening_execution(
        requested_fix_mode="self_modify_safe",
        recommended_agent="development",
        target_file_path="tools/deep_research/tool.py",
        change_type="report_quality_guardrails",
    )
    assert decision.allow_task is True
    assert decision.allow_self_modify is False
    assert decision.route_target == "development"
    assert decision.effective_fix_mode == "developer_task"

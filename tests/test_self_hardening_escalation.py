from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestration.self_hardening_engine import HardeningProposal, SelfHardeningEngine
from orchestration.self_hardening_escalation import (
    classify_self_hardening_effective_fix_mode,
    get_self_hardening_pattern_state,
    is_self_hardening_freeze_active,
    record_self_hardening_pattern_event,
)
from orchestration.task_queue import TaskQueue


def _make_engine() -> SelfHardeningEngine:
    with patch.object(SelfHardeningEngine, "_load_cooldown_from_blackboard"):
        return SelfHardeningEngine()


def _make_self_modify_proposal() -> HardeningProposal:
    return HardeningProposal(
        pattern_name="narrative_synthesis_empty",
        component="deep_research.tool._create_narrative",
        suggestion="Narrative-Fallback-Schwelle prüfen",
        severity="medium",
        fix_mode="self_modify_safe",
        recommended_agent="development",
        verification_hint="py_compile + pytest tests/test_deep_research_report_quality.py",
        target_file_path="tools/deep_research/tool.py",
        change_type="report_quality_guardrails",
        occurrences=4,
        sample_lines=["Narrative leer"],
    )


def test_classify_self_hardening_effective_fix_mode_downgrades_after_first_self_modify_failure() -> None:
    decision = classify_self_hardening_effective_fix_mode(
        requested_fix_mode="self_modify_safe",
        self_modify_failures=1,
    )
    assert decision.effective_fix_mode == "developer_task"
    assert decision.reason == "self_modify_failure_budget_exhausted"


def test_classify_self_hardening_effective_fix_mode_freezes_after_repeated_self_modify_failures() -> None:
    decision = classify_self_hardening_effective_fix_mode(
        requested_fix_mode="self_modify_safe",
        self_modify_failures=2,
    )
    assert decision.effective_fix_mode == "human_only"
    assert decision.reason == "repeated_self_modify_failures"


def test_is_self_hardening_freeze_active_honors_future_timestamp() -> None:
    freeze_until = (datetime.now() + timedelta(hours=2)).isoformat()
    assert is_self_hardening_freeze_active(freeze_until=freeze_until) is True


def test_record_self_hardening_pattern_event_persists_developer_downgrade(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")

    record_self_hardening_pattern_event(
        queue,
        pattern_name="narrative_synthesis_empty",
        requested_fix_mode="self_modify_safe",
        stage="self_modify_finished",
        status="error",
    )

    state = get_self_hardening_pattern_state(
        queue,
        pattern_name="narrative_synthesis_empty",
        requested_fix_mode="self_modify_safe",
    )
    assert state["effective_fix_mode"] == "developer_task"
    assert state["self_modify_failure_count"] == 1
    assert state["freeze_active"] is False


def test_record_self_hardening_pattern_event_activates_human_freeze_after_repeated_failures(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")

    record_self_hardening_pattern_event(
        queue,
        pattern_name="narrative_synthesis_empty",
        requested_fix_mode="self_modify_safe",
        stage="self_modify_finished",
        status="error",
    )
    outcome = record_self_hardening_pattern_event(
        queue,
        pattern_name="narrative_synthesis_empty",
        requested_fix_mode="self_modify_safe",
        stage="self_modify_finished",
        status="rolled_back",
    )

    state = outcome["state"]
    assert state["effective_fix_mode"] == "human_only"
    assert state["freeze_active"] is True
    assert state["freeze_until"]
    assert outcome["transition_metrics"]["human_only_escalations_total"] == 1
    assert outcome["transition_metrics"]["freeze_activations_total"] == 1


def test_engine_uses_persisted_escalation_to_route_self_modify_pattern_to_development(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    record_self_hardening_pattern_event(
        queue,
        pattern_name="narrative_synthesis_empty",
        requested_fix_mode="self_modify_safe",
        stage="self_modify_finished",
        status="error",
    )
    engine = _make_engine()
    proposal = _make_self_modify_proposal()

    queue.get_all = MagicMock(return_value=[])
    queue.add = MagicMock(return_value="task-dev")

    with patch("orchestration.task_queue.get_queue", return_value=queue):
        task_id = engine._create_hardening_task(proposal, goal_id="goal-1")

    assert task_id == "task-dev"
    _, kwargs = queue.add.call_args
    assert kwargs["target_agent"] == "development"
    assert '"execution_mode": "developer_task"' in kwargs["metadata"]
    assert '"escalation_reason": "self_modify_failure_budget_exhausted"' in kwargs["metadata"]


def test_engine_skips_task_when_pattern_is_frozen_to_human_only(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    record_self_hardening_pattern_event(
        queue,
        pattern_name="narrative_synthesis_empty",
        requested_fix_mode="self_modify_safe",
        stage="self_modify_finished",
        status="error",
    )
    record_self_hardening_pattern_event(
        queue,
        pattern_name="narrative_synthesis_empty",
        requested_fix_mode="self_modify_safe",
        stage="self_modify_finished",
        status="rolled_back",
    )
    engine = _make_engine()
    proposal = _make_self_modify_proposal()

    queue.get_all = MagicMock(return_value=[])
    queue.add = MagicMock(return_value="task-human")

    with patch("orchestration.task_queue.get_queue", return_value=queue):
        task_id = engine._create_hardening_task(proposal, goal_id="goal-1")

    assert task_id is None
    queue.add.assert_not_called()

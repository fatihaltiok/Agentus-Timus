from hypothesis import given, strategies as st

from orchestration.meta_runtime_plan import advance_meta_execution_plan


@given(
    signal=st.sampled_from(["step_completed", "step_blocked", "step_unnecessary", "goal_satisfied"]),
    reason=st.text(min_size=0, max_size=40),
)
def test_advance_meta_execution_plan_keeps_runtime_shape_stable(signal: str, reason: str) -> None:
    updated, summary = advance_meta_execution_plan(
        {
            "plan_id": "plan_1",
            "plan_mode": "multi_step_execution",
            "goal": "Build aufsetzen",
            "goal_satisfaction_mode": "goal_satisfied",
            "steps": [
                {
                    "id": "setup",
                    "title": "Setup ausfuehren",
                    "assigned_agent": "executor",
                    "status": "pending",
                    "depends_on": [],
                    "completion_signals": ["goal_satisfied"],
                    "recipe_stage_id": "setup",
                }
            ],
            "next_step_id": "setup",
            "metadata": {"task_type": "build_setup", "step_count": 1},
        },
        stage_id="setup",
        plan_step_id="setup",
        stage_status="success" if signal != "step_blocked" else "partial",
        specialist_step_signal=signal,
        specialist_step_reason=reason,
    )

    assert isinstance(updated["steps"], list)
    assert updated["status"] in {"active", "blocked", "completed"}
    assert isinstance(updated["blocked_by"], list)
    assert isinstance(summary["applied"], bool)

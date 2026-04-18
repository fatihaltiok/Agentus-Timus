from orchestration.meta_runtime_plan import (
    advance_meta_execution_plan,
    insert_runtime_stage_into_meta_execution_plan,
)


def _base_plan() -> dict:
    return {
        "plan_id": "yt-plan-1",
        "plan_mode": "multi_step_execution",
        "goal": "Videoinhalt sammeln",
        "goal_satisfaction_mode": "goal_satisfied",
        "steps": [
            {
                "id": "visual_access",
                "title": "YouTube-Seite oeffnen",
                "assigned_agent": "visual",
                "status": "pending",
                "depends_on": [],
                "completion_signals": ["step_completed"],
                "recipe_stage_id": "visual_access",
            },
            {
                "id": "research_synthesis",
                "title": "Transcript verdichten",
                "assigned_agent": "research",
                "status": "pending",
                "depends_on": ["visual_access"],
                "completion_signals": ["step_completed"],
                "recipe_stage_id": "research_synthesis",
            },
        ],
        "next_step_id": "visual_access",
        "blocked_by": [],
        "metadata": {"task_type": "youtube_content_extraction", "step_count": 2},
    }


def test_advance_meta_execution_plan_marks_step_complete_and_moves_next_step() -> None:
    updated, summary = advance_meta_execution_plan(
        _base_plan(),
        stage_id="visual_access",
        plan_step_id="visual_access",
        stage_status="success",
    )

    assert summary["applied"] is True
    assert summary["state"] == "advanced"
    assert summary["last_completed_step_id"] == "visual_access"
    assert summary["next_step_id"] == "research_synthesis"
    assert updated["status"] == "active"
    assert updated["steps"][0]["status"] == "completed"
    assert updated["next_step_id"] == "research_synthesis"


def test_advance_meta_execution_plan_treats_goal_satisfied_as_terminal() -> None:
    updated, summary = advance_meta_execution_plan(
        _base_plan(),
        stage_id="visual_access",
        plan_step_id="visual_access",
        stage_status="success",
        specialist_step_signal="goal_satisfied",
        specialist_step_reason="already_logged_in",
    )

    assert summary["goal_satisfied"] is True
    assert summary["plan_status"] == "completed"
    assert updated["status"] == "completed"
    assert updated["next_step_id"] == ""
    assert all(step["status"] in {"completed", "cancelled"} for step in updated["steps"])


def test_insert_runtime_stage_into_meta_execution_plan_inserts_before_next_step() -> None:
    updated, summary = insert_runtime_stage_into_meta_execution_plan(
        {
            **_base_plan(),
            "steps": [
                {**_base_plan()["steps"][0], "status": "completed"},
                _base_plan()["steps"][1],
            ],
            "next_step_id": "research_synthesis",
            "last_completed_step_id": "visual_access",
            "last_completed_step_title": "YouTube-Seite oeffnen",
            "status": "active",
        },
        {
            "stage_id": "research_validation",
            "agent": "research",
            "goal": "Quellen verifizieren",
            "expected_output": "verified_summary",
        },
        before_step_id="research_synthesis",
        depends_on_step_id="visual_access",
    )

    assert summary["applied"] is True
    assert summary["inserted_step_id"] == "research_validation"
    assert updated["next_step_id"] == "research_validation"
    assert [step["id"] for step in updated["steps"]] == [
        "visual_access",
        "research_validation",
        "research_synthesis",
    ]
    assert updated["steps"][1]["depends_on"] == ["visual_access"]

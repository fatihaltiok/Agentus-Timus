from __future__ import annotations

import deal

from orchestration.meta_runtime_plan import advance_meta_execution_plan


@deal.post(lambda r: r == 1)
def _contract_goal_satisfied_finishes_plan() -> int:
    updated, summary = advance_meta_execution_plan(
        {
            "plan_id": "plan_1",
            "plan_mode": "multi_step_execution",
            "goal": "YouTube-Inhalt sammeln",
            "goal_satisfaction_mode": "goal_satisfied",
            "steps": [
                {
                    "id": "visual_access",
                    "title": "Video erreichen",
                    "assigned_agent": "visual",
                    "status": "pending",
                    "depends_on": [],
                    "completion_signals": ["goal_satisfied"],
                    "recipe_stage_id": "visual_access",
                }
            ],
            "next_step_id": "visual_access",
            "metadata": {"task_type": "youtube_content_extraction", "step_count": 1},
        },
        stage_id="visual_access",
        plan_step_id="visual_access",
        stage_status="success",
        specialist_step_signal="goal_satisfied",
        specialist_step_reason="already_on_target",
    )
    return 1 if summary["goal_satisfied"] and updated["status"] == "completed" and not updated["next_step_id"] else 0

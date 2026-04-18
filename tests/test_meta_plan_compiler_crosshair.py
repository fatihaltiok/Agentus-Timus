from __future__ import annotations

import json

import deal

from orchestration.meta_plan_compiler import (
    build_meta_execution_plan,
    parse_meta_execution_plan,
)


@deal.post(lambda r: r == 1)
def _contract_meta_execution_plan_keeps_next_step() -> int:
    plan = build_meta_execution_plan(
        source_query="Plane und fuehre die Integration aus.",
        handoff_payload={
            "task_type": "integration_setup",
            "recommended_agent_chain": ["meta", "executor"],
        },
        task_decomposition={
            "intent_family": "build_setup",
            "goal": "Integration umsetzen",
            "subtasks": [
                {"id": "analyze_target", "title": "Ziel analysieren", "kind": "analysis"},
                {"id": "execute_setup", "title": "Setup ausfuehren", "kind": "setup"},
            ],
            "completion_signals": ["goal_satisfied"],
            "goal_satisfaction_mode": "goal_satisfied",
            "planning_needed": True,
        },
    )
    return 1 if plan["next_step_id"] and len(plan["steps"]) >= 1 else 0


@deal.post(lambda r: r == 1)
def _contract_meta_execution_plan_parse_keeps_schema() -> int:
    plan = build_meta_execution_plan(
        source_query="Hole Inhalte aus einem YouTube-Video und schreibe einen Bericht.",
        handoff_payload={
            "task_type": "youtube_content_extraction",
            "recommended_agent_chain": ["meta", "visual", "research", "document"],
            "recipe_stages": [
                {
                    "stage_id": "visual_access",
                    "agent": "visual",
                    "goal": "Video erreichen",
                    "expected_output": "page_state",
                }
            ],
        },
    )
    parsed = parse_meta_execution_plan(json.dumps(plan, ensure_ascii=False))
    return 1 if parsed["schema_version"] == 1 and isinstance(parsed["steps"], list) else 0

import json

from orchestration.meta_plan_compiler import (
    build_meta_execution_plan,
    parse_meta_execution_plan,
)


def test_build_meta_execution_plan_enriches_recipe_with_explicit_steps() -> None:
    plan = build_meta_execution_plan(
        source_query="Hole aus einem YouTube-Video maximal viel Inhalt raus und schreibe einen Bericht dazu.",
        handoff_payload={
            "task_type": "youtube_content_extraction",
            "site_kind": "youtube",
            "response_mode": "execute",
            "recommended_recipe_id": "youtube_content_extraction",
            "recommended_agent_chain": ["meta", "visual", "research", "document"],
            "recipe_stages": [
                {
                    "stage_id": "visual_access",
                    "agent": "visual",
                    "goal": "Oeffne YouTube",
                    "expected_output": "page_state",
                },
                {
                    "stage_id": "research_synthesis",
                    "agent": "research",
                    "goal": "Verdichte den Inhalt",
                    "expected_output": "summary",
                },
                {
                    "stage_id": "document_output",
                    "agent": "document",
                    "goal": "Erzeuge einen Bericht",
                    "expected_output": "report artifact",
                    "optional": True,
                },
            ],
        },
        task_decomposition={
            "intent_family": "execute_multistep",
            "goal": "Videoinhalt extrahieren und als Bericht liefern",
            "constraints": {"hard": ["freshness=recent"]},
            "subtasks": [
                {
                    "id": "gather_context",
                    "title": "Video und Kontext erfassen",
                    "kind": "research",
                    "completion_signals": ["context_collected"],
                },
                {
                    "id": "verify_result",
                    "title": "Ergebnis pruefen",
                    "kind": "verification",
                    "completion_signals": ["verification_passed"],
                },
                {
                    "id": "deliver_result",
                    "title": "Bericht liefern",
                    "kind": "delivery",
                    "completion_signals": ["artifact_ready"],
                },
            ],
            "completion_signals": ["artifact_ready"],
            "goal_satisfaction_mode": "goal_satisfied",
            "planning_needed": True,
        },
    )

    assert plan["schema_version"] == 1
    assert plan["plan_mode"] == "multi_step_execution"
    assert plan["planning_needed"] is True
    assert plan["next_step_id"] == "visual_access"
    assert [step["assigned_agent"] for step in plan["steps"]][:2] == [
        "visual",
        "research",
    ]
    assert any(step["step_kind"] == "verification" for step in plan["steps"])
    assert plan["steps"][-1]["assigned_agent"] == "document"
    assert plan["steps"][0]["recipe_stage_id"] == "visual_access"
    assert plan["steps"][-1]["source_subtask_id"] == "deliver_result"


def test_parse_meta_execution_plan_roundtrips_json_shape() -> None:
    plan = build_meta_execution_plan(
        source_query="Plane den Ablauf fuer eine Integration.",
        handoff_payload={
            "task_type": "integration_setup",
            "site_kind": "web",
            "response_mode": "execute",
            "recommended_agent_chain": ["meta", "executor"],
        },
        task_decomposition={
            "intent_family": "build_setup",
            "goal": "Integration kontrolliert umsetzen",
            "constraints": {"soft": ["plane_vor_der_ausfuehrung"]},
            "subtasks": [
                {"id": "analyze_target", "title": "Ziel analysieren", "kind": "analysis"},
                {"id": "execute_setup", "title": "Setup ausfuehren", "kind": "setup"},
            ],
            "completion_signals": ["goal_satisfied"],
            "goal_satisfaction_mode": "goal_satisfied",
            "planning_needed": True,
        },
    )

    parsed = parse_meta_execution_plan(json.dumps(plan, ensure_ascii=False))

    assert parsed == plan

from hypothesis import given, strategies as st

from orchestration.meta_plan_compiler import build_meta_execution_plan


@given(
    query=st.text(min_size=1, max_size=320),
    task_type=st.text(min_size=0, max_size=48),
    site_kind=st.text(min_size=0, max_size=32),
    response_mode=st.text(min_size=0, max_size=24),
    intent_family=st.sampled_from(
        ["single_step", "research", "plan_only", "build_setup", "execute_multistep"]
    ),
    planning_needed=st.booleans(),
)
def test_meta_execution_plan_shape_is_stable(
    query: str,
    task_type: str,
    site_kind: str,
    response_mode: str,
    intent_family: str,
    planning_needed: bool,
) -> None:
    plan = build_meta_execution_plan(
        source_query=query,
        handoff_payload={
            "task_type": task_type,
            "site_kind": site_kind,
            "response_mode": response_mode,
            "recommended_agent_chain": ["meta", "executor"],
        },
        task_decomposition={
            "intent_family": intent_family,
            "goal": query,
            "subtasks": [
                {
                    "id": "respond",
                    "title": "Antwort liefern",
                    "kind": "response",
                    "completion_signals": ["answer_delivered"],
                }
            ],
            "completion_signals": ["answer_delivered"],
            "goal_satisfaction_mode": "answer_or_artifact_ready",
            "planning_needed": planning_needed,
        },
    )

    assert plan["schema_version"] == 1
    assert plan["plan_mode"] in {
        "direct_response",
        "lightweight_lookup",
        "plan_only",
        "multi_step_execution",
    }
    assert isinstance(plan["planning_needed"], bool)
    assert isinstance(plan["steps"], list)
    assert plan["metadata"]["step_count"] >= 0

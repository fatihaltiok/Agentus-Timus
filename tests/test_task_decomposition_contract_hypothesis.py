from hypothesis import given, strategies as st

from orchestration.task_decomposition_contract import build_task_decomposition


@given(
    query=st.text(min_size=1, max_size=320),
    task_type=st.text(min_size=0, max_size=48),
    response_mode=st.text(min_size=0, max_size=32),
    action_count=st.integers(min_value=0, max_value=6),
    capability_count=st.integers(min_value=0, max_value=8),
    route_to_meta=st.booleans(),
)
def test_task_decomposition_shape_is_stable(
    query: str,
    task_type: str,
    response_mode: str,
    action_count: int,
    capability_count: int,
    route_to_meta: bool,
) -> None:
    decomposition = build_task_decomposition(
        source_query=query,
        orchestration_policy={
            "task_type": task_type,
            "response_mode": response_mode,
            "action_count": action_count,
            "capability_count": capability_count,
            "route_to_meta": route_to_meta,
        },
    )

    assert decomposition["schema_version"] == 1
    assert decomposition["intent_family"] in {
        "single_step",
        "research",
        "plan_only",
        "build_setup",
        "execute_multistep",
    }
    assert decomposition["goal_satisfaction_mode"] in {
        "answer_or_artifact_ready",
        "plan_ready",
        "goal_satisfied",
    }
    assert isinstance(decomposition["planning_needed"], bool)
    assert isinstance(decomposition["subtasks"], list)
    assert decomposition["metadata"]["action_count"] >= 0
    assert decomposition["metadata"]["capability_count"] >= 0

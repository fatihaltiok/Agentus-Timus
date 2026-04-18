from hypothesis import given, strategies as st

from orchestration.specialist_step_package import build_specialist_step_package_payload

_VISIBLE_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
    min_size=1,
    max_size=120,
).filter(lambda value: bool(value.strip()))


@given(
    goal=_VISIBLE_TEXT,
    step_title=_VISIBLE_TEXT,
    previous_stage_result=_VISIBLE_TEXT,
)
def test_specialist_step_package_shape_is_stable(
    goal: str,
    step_title: str,
    previous_stage_result: str,
) -> None:
    payload = build_specialist_step_package_payload(
        plan_summary={"plan_id": "plan_z4", "goal": goal, "plan_mode": "multi_step_execution"},
        plan_step={"id": "step_1", "title": step_title, "assigned_agent": "research"},
        previous_stage_result=previous_stage_result,
    )

    assert payload["schema_version"] == 1
    assert payload["plan_id"] == "plan_z4"
    assert payload["step_id"] == "step_1"
    assert payload["step_title"]
    assert payload["focus_context"]["previous_stage_result"]
    assert payload["return_signal_contract"] == [
        "step_completed",
        "step_blocked",
        "step_unnecessary",
        "goal_satisfied",
    ]

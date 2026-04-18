from hypothesis import given, strategies as st

from orchestration.conversation_state import apply_turn_interpretation, normalize_conversation_state

_VISIBLE_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
    min_size=1,
    max_size=120,
).filter(lambda value: bool(value.strip()))

_VISIBLE_ID = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
    min_size=1,
    max_size=24,
).filter(lambda value: bool(value.strip()))


@given(
    plan_id=_VISIBLE_ID,
    goal=_VISIBLE_TEXT,
    next_step_title=_VISIBLE_TEXT,
    step_count=st.integers(min_value=1, max_value=8),
)
def test_normalize_conversation_state_preserves_active_plan_resume_fields(
    plan_id: str,
    goal: str,
    next_step_title: str,
    step_count: int,
) -> None:
    state = normalize_conversation_state(
        {
            "active_plan": {
                "plan_id": plan_id,
                "plan_mode": "multi_step_execution",
                "goal": goal,
                "next_step_id": "step_1",
                "next_step_title": next_step_title,
                "step_count": step_count,
            }
        },
        session_id="z3_hypothesis",
        last_updated="2026-04-18T12:00:00Z",
    )

    assert state.active_plan is not None
    assert state.active_plan.step_count >= 1
    assert state.next_expected_step
    assert state.open_loop
    assert state.active_plan.next_step_id == "step_1"
    assert state.active_plan.next_step_title == state.next_expected_step


@given(
    plan_id=_VISIBLE_ID,
    next_step_title=_VISIBLE_TEXT,
)
def test_apply_turn_interpretation_keeps_active_plan_for_resume_turns(
    plan_id: str,
    next_step_title: str,
) -> None:
    updated = apply_turn_interpretation(
        {
            "active_topic": "Build Setup",
            "active_goal": "Setup abschliessen",
        },
        session_id="z3_hypothesis",
        dominant_turn_type="followup",
        response_mode="resume_open_loop",
        state_effects={"keep_active_topic": True},
        effective_query="weiter",
        active_topic="Build Setup",
        active_goal="Setup abschliessen",
        next_step="",
        active_plan={
            "plan_id": plan_id,
            "plan_mode": "multi_step_execution",
            "goal": "Setup abschliessen",
            "next_step_id": "step_2",
            "next_step_title": next_step_title,
            "step_count": 3,
        },
        confidence=0.8,
        updated_at="2026-04-18T12:05:00Z",
    )

    assert updated.active_plan is not None
    assert updated.next_expected_step
    assert updated.open_loop
    assert updated.active_plan.next_step_id == "step_2"
    assert updated.active_plan.next_step_title == updated.next_expected_step

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_meta_orchestration_eval_contracts import (
    _contract_evaluate_meta_orchestration_case,
    _contract_evaluate_meta_replan_case,
)


@given(
    st.fixed_dictionaries(
        {
            "name": st.text(max_size=40),
            "query": st.text(max_size=120),
            "expected_route_to_meta": st.booleans(),
            "expected_task_type": st.text(max_size=40),
            "expected_entry_agent": st.text(max_size=20),
            "expected_agent_chain": st.lists(st.text(min_size=1, max_size=20), max_size=5),
            "expected_recipe_id": st.one_of(st.none(), st.text(max_size=40)),
            "expected_structured_handoff": st.booleans(),
            "expected_capabilities": st.lists(st.text(min_size=1, max_size=40), max_size=5),
        }
    )
)
@settings(max_examples=60)
def test_hypothesis_meta_orchestration_eval_score_range(case: dict):
    result = _contract_evaluate_meta_orchestration_case(case)
    assert 0.0 <= result["score"] <= 1.0
    assert 0.0 <= result["benchmark"]["capability_score"] <= 1.0


@given(
    st.fixed_dictionaries(
        {
            "name": st.text(max_size=40),
            "query": st.text(max_size=120),
            "runtime_constraints": st.dictionaries(
                st.text(min_size=1, max_size=30),
                st.one_of(st.text(max_size=20), st.booleans(), st.integers(min_value=0, max_value=5)),
                max_size=8,
            ),
            "learning_snapshot": st.dictionaries(
                st.text(min_size=1, max_size=30),
                st.one_of(
                    st.text(max_size=20),
                    st.floats(allow_nan=False, allow_infinity=False, min_value=-2, max_value=2),
                ),
                max_size=4,
            ),
            "failed_stage": st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=40), max_size=4),
            "alternative_recipe_scores": st.lists(
                st.dictionaries(
                    st.text(min_size=1, max_size=30),
                    st.one_of(
                        st.text(max_size=40),
                        st.integers(min_value=0, max_value=6),
                        st.floats(allow_nan=False, allow_infinity=False, min_value=-2, max_value=2),
                    ),
                    max_size=6,
                ),
                max_size=4,
            ),
            "expected_initial_recipe": st.text(max_size=40),
            "expected_replan_recipe": st.text(max_size=40),
        }
    )
)
@settings(max_examples=40)
def test_hypothesis_meta_replan_eval_score_range(case: dict):
    result = _contract_evaluate_meta_replan_case(case)
    assert 0.0 <= result["score"] <= 1.0

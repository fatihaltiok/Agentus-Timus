from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.general_decision_kernel import build_general_decision_kernel
from orchestration.general_decision_kernel_eval import score_gdk5_expectations


@given(
    turn_kind=st.sampled_from(["think", "inspect", "research", "execute", "clarify"]),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    required=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(deadline=None, max_examples=80)
def test_hypothesis_gdk5_score_stays_bounded(
    turn_kind: str,
    confidence: float,
    required: float,
) -> None:
    result = score_gdk5_expectations(
        {"turn_kind": turn_kind, "confidence": confidence},
        {"turn_kind_in": ["think", "inspect", "research", "execute", "clarify"], "min_confidence": required},
    )

    assert 0.0 <= result["score"] <= 1.0
    assert 0 <= result["passed_checks"] <= result["total_checks"]


@given(
    prefix=st.text(max_size=20),
    phrase=st.sampled_from(
        [
            "was ist deine meinung",
            "deine einschätzung",
            "hilf mir bei einer entscheidung",
            "was bedeutet das für mich",
        ]
    ),
    suffix=st.text(max_size=40),
)
@settings(deadline=None, max_examples=80)
def test_hypothesis_think_language_never_allows_execution(prefix: str, phrase: str, suffix: str) -> None:
    query = f"{prefix} {phrase} {suffix}".strip()

    kernel = build_general_decision_kernel(effective_query=query).to_dict()

    assert kernel["turn_kind"] == "think"
    assert kernel["interaction_mode"] == "think_partner"
    assert kernel["evidence_requirement"] == "none"
    assert kernel["execution_permission"] == "forbidden"


@given(
    phrase=st.sampled_from(
        [
            "mach dich schlau über",
            "recherchiere über",
            "informier dich über",
            "arbeite dich in",
        ]
    ),
    topic=st.text(min_size=1, max_size=40),
)
@settings(deadline=None, max_examples=60)
def test_hypothesis_research_language_requires_bounded_research(topic: str, phrase: str) -> None:
    query = f"{phrase} {topic} und hilf mir dann"

    kernel = build_general_decision_kernel(effective_query=query).to_dict()

    assert kernel["turn_kind"] == "research"
    assert kernel["interaction_mode"] == "inspect"
    assert kernel["evidence_requirement"] == "research"
    assert kernel["execution_permission"] == "bounded"


@given(
    phrase=st.sampled_from(["prüf", "pruef", "schau nach", "lies"]),
    topic=st.text(min_size=1, max_size=40),
)
@settings(deadline=None, max_examples=60)
def test_hypothesis_inspect_language_stays_bounded(phrase: str, topic: str) -> None:
    query = f"{phrase} {topic}"

    kernel = build_general_decision_kernel(effective_query=query).to_dict()

    assert kernel["turn_kind"] == "inspect"
    assert kernel["interaction_mode"] == "inspect"
    assert kernel["evidence_requirement"] == "bounded"
    assert kernel["execution_permission"] == "bounded"

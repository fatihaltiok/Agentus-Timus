"""CrossHair + Hypothesis contracts for compact Telegram feedback and target-score clamping.

Lean 4 Bezug (CiSpecs.lean):
- m16_target_score_lower
- m16_target_score_upper
"""

import json

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.feedback_engine import (
    clamp_feedback_target_score,
    feedback_evidence_confidence,
    next_feedback_target_score,
)
from utils.telegram_notify import build_feedback_callback_data, decode_feedback_signal


@deal.pre(lambda current, signal: 0.1 <= current <= 3.0 and signal in {"positive", "negative", "neutral"})
@deal.post(lambda r: 0.1 <= r <= 3.0)
def _contract_next_feedback_target_score(current: float, signal: str) -> float:
    return next_feedback_target_score(current, signal)


@deal.pre(
    lambda token, signal: 1 <= len(token) <= 12
    and token.isalnum()
    and signal in {"positive", "negative", "neutral"}
)
@deal.post(lambda r: len(r) <= 64)
def _contract_compact_feedback_callback(token: str, signal: str) -> str:
    return build_feedback_callback_data(signal, token)


@deal.pre(lambda evidence_count, min_evidence: min_evidence > 0)
@deal.post(lambda r: 0.0 <= r <= 1.0)
def _contract_feedback_evidence_confidence(evidence_count: int, min_evidence: int) -> float:
    return feedback_evidence_confidence(evidence_count, min_evidence)


@given(
    st.floats(min_value=0.1, max_value=3.0, allow_infinity=False, allow_nan=False),
    st.sampled_from(["positive", "negative", "neutral"]),
)
@settings(max_examples=80)
def test_hypothesis_next_feedback_target_score_stays_bounded(current: float, signal: str):
    result = _contract_next_feedback_target_score(current, signal)
    assert 0.1 <= result <= 3.0


@given(
    st.text(
        alphabet=st.characters(min_codepoint=48, max_codepoint=122).filter(str.isalnum),
        min_size=1,
        max_size=12,
    ),
    st.sampled_from(["positive", "negative", "neutral"]),
)
@settings(max_examples=80)
def test_hypothesis_compact_feedback_callback_stays_short(token: str, signal: str):
    callback_data = _contract_compact_feedback_callback(token, signal)
    assert len(callback_data) <= 64
    assert decode_feedback_signal(json.loads(callback_data)["s"]) == signal


@given(
    st.integers(min_value=-100, max_value=200),
    st.integers(min_value=1, max_value=50),
)
@settings(max_examples=80)
def test_hypothesis_feedback_evidence_confidence_stays_bounded(evidence_count: int, min_evidence: int):
    confidence = _contract_feedback_evidence_confidence(evidence_count, min_evidence)
    assert 0.0 <= confidence <= 1.0


def test_clamp_feedback_target_score_respects_lean_bounds():
    assert 0.1 <= clamp_feedback_target_score(-999.0) <= 3.0
    assert 0.1 <= clamp_feedback_target_score(999.0) <= 3.0

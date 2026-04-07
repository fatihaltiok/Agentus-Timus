from __future__ import annotations

from orchestration.meta_context_eval import (
    MetaContextEvalCase,
    detect_context_misread_risk,
    evaluate_meta_context_case,
    summarize_meta_context_evals,
)


def _bundle(*slot_types: str, suppressed: list[dict[str, str]] | None = None) -> dict:
    return {
        "context_slots": [
            {"slot": slot, "priority": idx + 1, "content": f"{slot} content", "source": slot}
            for idx, slot in enumerate(slot_types)
        ],
        "suppressed_context": list(suppressed or []),
    }


def test_detect_context_misread_risk_flags_thin_followup_bundle():
    risk = detect_context_misread_risk(
        _bundle("current_query", "assistant_fallback_context"),
        dominant_turn_type="followup",
        response_mode="resume_open_loop",
    )

    assert risk["suspicious"] is True
    assert "assistant_fallback_without_user_anchor" in risk["reasons"]
    assert "resume_mode_without_open_loop" in risk["reasons"]


def test_detect_context_misread_risk_accepts_recovered_followup_bundle():
    risk = detect_context_misread_risk(
        _bundle("current_query", "conversation_state", "open_loop", "recent_user_turn"),
        dominant_turn_type="followup",
        response_mode="resume_open_loop",
    )

    assert risk["suspicious"] is False
    assert risk["reasons"] == []


def test_evaluate_meta_context_case_scores_missing_slots_and_forbidden_suppression():
    case = MetaContextEvalCase(
        label="news correction",
        bundle=_bundle(
            "current_query",
            "assistant_fallback_context",
            suppressed=[{"reason": "location_context_without_current_evidence", "source": "assistant_reply"}],
        ),
        dominant_turn_type="correction",
        response_mode="correct_previous_path",
        expected_slots=["recent_user_turn", "conversation_state"],
        forbidden_suppression_reasons=["preference_not_relevant_for_current_topic"],
        expected_suspicious=True,
    )

    result = evaluate_meta_context_case(case)

    assert result["passes"] is False
    assert "recent_user_turn" in result["missing_slots"]
    assert result["actual_suspicious"] is True
    assert result["score"] < 1.0


def test_summarize_meta_context_evals_aggregates_results():
    cases = [
        MetaContextEvalCase(
            label="good followup",
            bundle=_bundle("current_query", "conversation_state", "open_loop", "recent_user_turn"),
            dominant_turn_type="followup",
            response_mode="resume_open_loop",
            expected_slots=["conversation_state", "open_loop"],
            forbidden_suppression_reasons=[],
            expected_suspicious=False,
        ),
        MetaContextEvalCase(
            label="thin correction",
            bundle=_bundle("current_query", "assistant_fallback_context"),
            dominant_turn_type="correction",
            response_mode="correct_previous_path",
            expected_slots=[],
            forbidden_suppression_reasons=[],
            expected_suspicious=True,
        ),
    ]

    summary = summarize_meta_context_evals(cases)

    assert summary["total_cases"] == 2
    assert summary["pass_rate"] == 1.0
    assert summary["avg_score"] > 0.0
    assert len(summary["results"]) == 2

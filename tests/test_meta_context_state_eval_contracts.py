from __future__ import annotations

from typing import Any

import deal

from orchestration.meta_context_state_eval import (
    MetaContextStateEvalCase,
    evaluate_meta_context_state_case,
    summarize_meta_context_state_evals,
)


def _normalize_case(case: dict[str, Any]) -> MetaContextStateEvalCase:
    return MetaContextStateEvalCase(
        label=str(case.get("label") or ""),
        query=str(case.get("query") or ""),
        action_count=int(case.get("action_count") or 0),
        conversation_state=dict(case.get("conversation_state") or {}),
        recent_user_turns=tuple(str(item) for item in list(case.get("recent_user_turns") or [])[:4]),
        recent_assistant_turns=tuple(str(item) for item in list(case.get("recent_assistant_turns") or [])[:4]),
        session_summary=str(case.get("session_summary") or ""),
        topic_memory_hits=tuple(list(case.get("topic_memory_hits") or [])[:4]),
        preference_memory_hits=tuple(list(case.get("preference_memory_hits") or [])[:4]),
        semantic_recall_hits=tuple(list(case.get("semantic_recall_hits") or [])[:4]),
        expected_task_type=str(case.get("expected_task_type") or ""),
        expected_chain=tuple(str(item) for item in list(case.get("expected_chain") or [])[:4]),
        expected_turn_type=str(case.get("expected_turn_type") or ""),
        expected_response_mode=str(case.get("expected_response_mode") or ""),
        expected_reason_contains=str(case.get("expected_reason_contains") or ""),
        expected_slots=tuple(str(item) for item in list(case.get("expected_slots") or [])[:6]),
        expected_signals=tuple(str(item) for item in list(case.get("expected_signals") or [])[:6]),
        expected_suspicious=bool(case.get("expected_suspicious", False)),
    )


@deal.post(lambda r: isinstance(r, dict))
@deal.post(lambda r: 0.0 <= float(r.get("score", 0.0)) <= 1.0)
@deal.post(lambda r: isinstance((r.get("decision", {}) or {}).get("recommended_agent_chain", []), list))
@deal.post(lambda r: 0.0 <= float((r.get("benchmark", {}) or {}).get("slot_score", 0.0)) <= 1.0)
@deal.post(lambda r: 0.0 <= float((r.get("benchmark", {}) or {}).get("signal_score", 0.0)) <= 1.0)
def _contract_evaluate_meta_context_state_case(case: dict[str, Any]) -> dict[str, Any]:
    return evaluate_meta_context_state_case(_normalize_case(case))


@deal.post(lambda r: isinstance(r, dict))
@deal.post(lambda r: int(r.get("total_cases", 0)) >= 0)
@deal.post(lambda r: 0.0 <= float(r.get("pass_rate", 0.0)) <= 1.0)
@deal.post(lambda r: 0.0 <= float(r.get("avg_score", 0.0)) <= 1.0)
@deal.post(lambda r: 0.0 <= float(r.get("quality_score", 0.0)) <= 1.0)
@deal.post(lambda r: isinstance(r.get("by_family", {}), dict))
def _contract_summarize_meta_context_state_evals(cases: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [_normalize_case(case) for case in list(cases or [])[:6]]
    return summarize_meta_context_state_evals(normalized)


def test_contract_evaluate_meta_context_state_case_returns_bounded_scores():
    result = _contract_evaluate_meta_context_state_case(
        {
            "label": "contract",
            "query": "dann mach das in zukunft so dass du bei news agenturmeldungen priorisierst",
            "conversation_state": {
                "session_id": "contract_d07",
                "active_topic": "News",
                "active_goal": "Belastbare Quellen zuerst",
                "open_loop": "Agenturquellen priorisieren",
            },
            "expected_task_type": "single_lane",
            "expected_chain": ["meta"],
            "expected_turn_type": "behavior_instruction",
            "expected_response_mode": "acknowledge_and_store",
            "expected_slots": ["conversation_state", "open_loop"],
            "expected_signals": ["behavior_instruction", "preference_update"],
        }
    )

    assert isinstance(result["decision"]["recommended_agent_chain"], list)
    assert 0.0 <= result["score"] <= 1.0


def test_contract_summarize_meta_context_state_evals_handles_small_case_list():
    summary = _contract_summarize_meta_context_state_evals(
        [
            {
                "label": "contract-summary",
                "query": "die erste option",
                "conversation_state": {
                    "session_id": "contract_summary_d07",
                    "active_topic": "Amsterdam Reisevergleich",
                    "active_goal": "Beste Reiseoption finden",
                    "open_loop": "Waehle eine Option",
                    "next_expected_step": "Waehle eine Option",
                },
                "expected_task_type": "single_lane",
                "expected_chain": ["meta"],
                "expected_turn_type": "handover_resume",
                "expected_response_mode": "resume_open_loop",
                "expected_slots": ["conversation_state", "open_loop"],
            }
        ]
    )

    assert summary["total_cases"] == 1
    assert 0.0 <= summary["avg_score"] <= 1.0
    assert isinstance(summary["by_family"], dict)

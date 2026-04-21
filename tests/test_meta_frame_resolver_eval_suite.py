from __future__ import annotations

import pytest

from orchestration.meta_orchestration import classify_meta_task


def _assert_chain_prefix(result: dict, expected_prefix: list[str]) -> None:
    chain = list(result.get("recommended_agent_chain") or [])
    assert chain[: len(expected_prefix)] == expected_prefix


@pytest.mark.parametrize(
    (
        "case_id",
        "query",
        "kwargs",
        "expected_frame_kind",
        "expected_task_domain",
        "expected_execution_mode",
        "expected_reason",
        "expected_task_type",
        "expected_chain_prefix",
        "expected_clarity_kind",
        "expected_forbidden_memory_domain",
    ),
    [
        (
            "docs_status",
            "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",
            {
                "action_count": 2,
                "conversation_state": {
                    "session_id": "mfr6_docs_status",
                    "active_topic": "Phase F Abschluss",
                    "active_goal": "Naechsten Hauptblock festlegen",
                    "open_loop": "Nachfolger von Phase F bestimmen",
                    "next_expected_step": "Mehrschritt-Planungsblock starten",
                },
            },
            "direct_answer",
            "docs_status",
            "answer_directly",
            "meta_policy:next_step_summary_request",
            "single_lane",
            ["meta"],
            "direct_recommendation",
            "skill_creation",
        ),
        (
            "migration_work_followup",
            "Informationen ueber Kanada wie kann ich dort arbeiten",
            {
                "action_count": 0,
                "conversation_state": {
                    "session_id": "mfr6_canada_followup",
                    "active_topic": "Kanada",
                    "active_goal": "Moeglichkeiten in Kanada Fuss zu fassen",
                    "open_loop": "",
                    "next_expected_step": "",
                    "turn_type_hint": "followup",
                    "topic_confidence": 0.83,
                },
                "recent_user_turns": ["suche mir Moeglichkeiten in Kanada Fuss zu fassen"],
            },
            "stateful_followup",
            "migration_work",
            "plan_and_delegate",
            "frame:migration_work",
            "knowledge_research",
            ["meta", "research"],
            "resume_action",
            "telephony_setup",
        ),
        (
            "setup_build",
            (
                "Richte fuer mich eine Anruffunktion ein. Du sollst mich ueber Twilio anrufen "
                "koennen mit der Stimme von Inworld.ai Lennart. Schau mal nach ob es schon "
                "Vorbereitungen gibt."
            ),
            {
                "action_count": 0,
            },
            "new_task",
            "setup_build",
            "plan_and_delegate",
            "frame:setup_build",
            "single_lane",
            ["meta", "executor"],
            "execute_task",
            "location_route",
        ),
        (
            "planning_advisory",
            "Plane meinen Tag fuer morgen",
            {
                "action_count": 0,
            },
            "new_task",
            "planning_advisory",
            "plan_and_delegate",
            "frame:planning_advisory",
            "single_lane",
            ["meta"],
            "execute_task",
            "telephony_setup",
        ),
        (
            "research_advisory",
            "Mach dich schlau ueber Kreislaufwirtschaft im Bau und steh mir dann hilfreich zur Seite",
            {
                "action_count": 0,
            },
            "new_task",
            "research_advisory",
            "plan_and_delegate",
            "frame:research_advisory",
            "single_lane",
            ["meta", "executor"],
            "execute_task",
            "telephony_setup",
        ),
        (
            "self_status",
            "Hey Timus, wie ist dein Zustand, hast du Probleme mich zu verstehen?",
            {
                "action_count": 0,
            },
            "status_summary",
            "self_status",
            "answer_directly",
            "meta_policy:self_model_status_request",
            "single_lane",
            ["meta"],
            "self_model_status",
            "skill_creation",
        ),
    ],
    ids=lambda item: item if isinstance(item, str) else None,
)
def test_mfr6_meta_frame_eval_suite(
    case_id: str,
    query: str,
    kwargs: dict,
    expected_frame_kind: str,
    expected_task_domain: str,
    expected_execution_mode: str,
    expected_reason: str,
    expected_task_type: str,
    expected_chain_prefix: list[str],
    expected_clarity_kind: str,
    expected_forbidden_memory_domain: str,
) -> None:
    result = classify_meta_task(query, **kwargs)

    frame = dict(result["meta_request_frame"])
    clarity = dict(result["meta_clarity_contract"])
    task_decomposition = dict(result["task_decomposition"])
    task_metadata = dict(task_decomposition.get("metadata") or {})

    assert frame["frame_kind"] == expected_frame_kind, case_id
    assert frame["task_domain"] == expected_task_domain, case_id
    assert frame["execution_mode"] == expected_execution_mode, case_id
    assert expected_forbidden_memory_domain in frame["forbidden_memory_domains"], case_id

    assert result["reason"] == expected_reason, case_id
    assert result["task_type"] == expected_task_type, case_id
    _assert_chain_prefix(result, expected_chain_prefix)

    assert clarity["request_kind"] == expected_clarity_kind, case_id
    assert task_metadata["frame_task_domain"] == expected_task_domain, case_id
    assert task_metadata["frame_execution_mode"] == expected_execution_mode, case_id


def test_mfr6_planning_advisory_keeps_meta_local_and_zero_delegate_budget() -> None:
    result = classify_meta_task("Plane meinen Tag fuer morgen", action_count=0)

    assert result["recommended_agent_chain"] == ["meta"]
    assert result["meta_request_frame"]["delegation_budget"] == 0
    assert result["meta_clarity_contract"]["delegation_mode"] == "direct_only"
    assert result["meta_clarity_contract"]["max_delegate_calls"] == 0


def test_mfr6_research_advisory_prefers_focused_research_support() -> None:
    result = classify_meta_task(
        "Mach dich schlau ueber kommunale Waermenetzplanung und steh mir dann hilfreich zur Seite",
        action_count=0,
    )

    assert result["recommended_agent_chain"][:2] == ["meta", "executor"]
    assert result["meta_request_frame"]["task_domain"] == "research_advisory"
    assert result["meta_clarity_contract"]["delegation_mode"] == "focused_research"
    assert result["meta_clarity_contract"]["allowed_delegate_agents"] == ["executor"]

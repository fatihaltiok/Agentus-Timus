"""Ausbaustufe 5 B1/B2: Live-Request-Korpus als Klassifikations-Gate.

Der Korpus bildet echte Alltagsthemen ab, bevor weitere GDK-Fixes gebaut
werden. Bekannte Ziel-Luecken sind als xfail markiert, harte Drifts auf
Skill-/Setup-Routen duerfen aber nie unbemerkt passieren.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pytest

from orchestration.meta_orchestration import classify_meta_task


CORPUS_PATH = Path(__file__).parent / "fixtures" / "live_request_corpus.json"
MANDATORY_CATEGORIES = {
    "trivial_execution",
    "quick_lookup",
    "followup_context",
    "advisory",
    "behavior_instruction",
    "multi_step",
    "correction",
    "clarification",
    "document_or_file",
    "communication",
    "direct_answer",
}
HARD_FORBIDDEN_TASK_DOMAINS = {"skill_creation", "setup_build"}
HARD_FORBIDDEN_AGENTS = {"skill_creator", "skill-creator"}


def _load_cases() -> list[dict[str, Any]]:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return list(payload["cases"])


def _case_params() -> Iterable[pytest.ParameterSet]:
    for case in _load_cases():
        marks: list[Any] = []
        if case.get("xfail"):
            marks.append(pytest.mark.xfail(reason=case["xfail"], strict=False))
        yield pytest.param(case, id=case["id"], marks=marks)


def _classify(case: dict[str, Any]) -> dict[str, Any]:
    return classify_meta_task(
        case["query"],
        action_count=int(case.get("action_count", 0)),
        conversation_state=case.get("conversation_state"),
        recent_user_turns=case.get("recent_user_turns"),
        recent_assistant_turns=case.get("recent_assistant_turns"),
        session_summary=str(case.get("session_summary", "")),
        topic_history=case.get("topic_history"),
        topic_memory_hits=case.get("topic_memory_hits"),
        preference_memory_hits=case.get("preference_memory_hits"),
        semantic_recall_hits=case.get("semantic_recall_hits"),
    )


def _chain(result: dict[str, Any]) -> list[str]:
    return list(result.get("recommended_agent_chain") or [])


def _frame(result: dict[str, Any]) -> dict[str, Any]:
    return dict(result.get("meta_request_frame") or {})


def _interaction_mode(result: dict[str, Any]) -> str:
    mode = result.get("meta_interaction_mode") or {}
    return str(mode.get("mode") or "")


def _dominant_turn_type(result: dict[str, Any]) -> str:
    direct = str(result.get("dominant_turn_type") or "")
    if direct:
        return direct
    understanding = result.get("turn_understanding") or {}
    return str(understanding.get("dominant_turn_type") or "")


def _assert_forbidden_target(result: dict[str, Any], forbidden: dict[str, Any]) -> None:
    response_mode = result.get("response_mode")
    if "response_modes" in forbidden:
        assert response_mode not in set(forbidden["response_modes"])

    if "task_types" in forbidden:
        assert result.get("task_type") not in set(forbidden["task_types"])

    if "interaction_modes" in forbidden:
        assert _interaction_mode(result) not in set(forbidden["interaction_modes"])

    if "task_domains" in forbidden:
        assert _frame(result).get("task_domain") not in set(forbidden["task_domains"])


def _assert_expected(result: dict[str, Any], expected: dict[str, Any]) -> None:
    if "task_type" in expected:
        assert result.get("task_type") == expected["task_type"]

    if "not_task_types" in expected:
        assert result.get("task_type") not in set(expected["not_task_types"])

    if "response_mode" in expected:
        assert result.get("response_mode") == expected["response_mode"]

    if "chain" in expected:
        assert _chain(result) == expected["chain"]

    if "chain_prefix" in expected:
        prefix = list(expected["chain_prefix"])
        assert _chain(result)[: len(prefix)] == prefix

    if "entry_agent" in expected:
        assert result.get("recommended_entry_agent") == expected["entry_agent"]

    if "recipe_id" in expected:
        assert result.get("recommended_recipe_id") == expected["recipe_id"]

    if "task_domain" in expected:
        assert _frame(result).get("task_domain") == expected["task_domain"]

    if "interaction_mode" in expected:
        assert _interaction_mode(result) == expected["interaction_mode"]

    if "reason" in expected:
        assert result.get("reason") == expected["reason"]

    if "dominant_turn_type" in expected:
        assert _dominant_turn_type(result) == expected["dominant_turn_type"]

    if "personal_assessment" in expected:
        gate = result.get("personal_assessment_gate") or {}
        assert bool(gate.get("is_personal_assessment")) is bool(expected["personal_assessment"])

    if "deictic_kind" in expected:
        deictic = result.get("deictic_reference") or {}
        assert deictic.get("has_reference") is True
        assert deictic.get("reference_kind") == expected["deictic_kind"]

    if "deictic_reference" in expected:
        deictic = result.get("deictic_reference") or {}
        assert bool(deictic.get("has_reference")) is bool(expected["deictic_reference"])


def test_live_request_corpus_shape():
    cases = _load_cases()
    ids = [case["id"] for case in cases]
    categories = {case["category"] for case in cases}

    assert len(cases) >= 40
    assert len(ids) == len(set(ids))
    assert MANDATORY_CATEGORIES <= categories

    for case in cases:
        assert case.get("query")
        assert case.get("expected")
        assert case["category"] in MANDATORY_CATEGORIES


@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: case["id"])
def test_live_request_corpus_has_no_hard_skill_or_setup_drift(case: dict[str, Any]):
    result = _classify(case)
    task_domain = _frame(result).get("task_domain")
    chain = set(_chain(result))

    assert task_domain not in HARD_FORBIDDEN_TASK_DOMAINS
    assert result.get("task_type") not in HARD_FORBIDDEN_TASK_DOMAINS
    assert chain.isdisjoint(HARD_FORBIDDEN_AGENTS)


@pytest.mark.parametrize("case", list(_case_params()))
def test_live_request_corpus_classification_targets(case: dict[str, Any]):
    result = _classify(case)

    _assert_expected(result, case["expected"])
    if case.get("target_forbidden"):
        _assert_forbidden_target(result, case["target_forbidden"])

"""CCF5: Tests fuer den Answer-Formation-Guard.

Sichert: wenn der Authority-Vertrag conversation_state freigegeben hat
und ein primary_objective vorliegt, darf Meta NICHT 'Kontext leer'
behaupten. Solche Antworten werden vom Guard verworfen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from agent.base_agent import BaseAgent  # noqa: E402


def _meta_handoff_text(*, primary_objective: str, allowed_classes: list[str]) -> str:
    authority = {
        "schema_version": 1,
        "primary_objective": primary_objective,
        "allowed_context_classes": allowed_classes,
        "forbidden_context_classes": [],
        "rationale": "session:followup | gdk:think/forbidden",
    }
    frame = {
        "frame_kind": "clarify_needed",
        "task_domain": "topic_advisory",
        "execution_mode": "answer_directly",
        "primary_objective": primary_objective,
    }
    clarity = {
        "primary_objective": primary_objective,
        "request_kind": "direct_recommendation",
        "answer_obligation": "answer_now_with_single_recommendation",
        "completion_condition": "named_or_clarified",
        "direct_answer_required": True,
    }
    return (
        "# META ORCHESTRATION HANDOFF\n"
        f"meta_request_frame_json: {json.dumps(frame, ensure_ascii=False)}\n"
        f"meta_clarity_contract_json: {json.dumps(clarity, ensure_ascii=False)}\n"
        f"meta_context_authority_json: {json.dumps(authority, ensure_ascii=False)}\n"
        "# ORIGINAL USER TASK\n"
        "kannst du dieses Problem beheben\n"
    )


def _make_agent_stub() -> BaseAgent:
    """Minimaler BaseAgent-Stub, der nur _build_meta_frame_answer_redirect_prompt
    ausfuehren kann."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.agent_type = "meta"
    agent._current_task_text = ""
    return agent


def test_ccf5_claims_no_context_with_authority_and_objective_triggers_redirect():
    """CCF5: 'Kontext leer'-Antwort wird verworfen, wenn Authority
    conversation_state freigegeben hat und primary_objective vorliegt.
    """
    agent = _make_agent_stub()
    task = _meta_handoff_text(
        primary_objective="Unternehmensgruendung mit KI - Skills klaeren",
        allowed_classes=["conversation_state"],
    )
    agent._current_task_text = task
    answer = (
        "Welches Problem? Ich sehe keine konkrete Frage. "
        "Der Conversation-State ist hier abgeschnitten."
    )
    redirect = agent._build_meta_frame_answer_redirect_prompt(task, answer)
    assert redirect is not None
    # Mindestens eine der drei moeglichen Korrekturarten muss greifen.
    assert (
        "CCF3" in redirect
        or "CCF5" in redirect
        or "Meta-Frame-Korrektur" in redirect
    )


def test_ccf5_real_recommendation_passes_through():
    """Eine konkrete Empfehlung darf nicht abgelehnt werden."""
    agent = _make_agent_stub()
    task = _meta_handoff_text(
        primary_objective="Plane meinen Tag",
        allowed_classes=["conversation_state"],
    )
    agent._current_task_text = task
    answer = (
        "Hier sind 3 konkrete Vorschlaege:\n"
        "1. Spaziergang im Grueneburgpark\n"
        "2. Staedel-Museum besuchen\n"
        "3. Cafe in Sachsenhausen"
    )
    redirect = agent._build_meta_frame_answer_redirect_prompt(task, answer)
    # Soll durchgehen - ist eine echte Empfehlung
    assert redirect is None


def test_ccf5_no_authority_no_redirect():
    """Ohne Authority-Block darf der CCF5-Guard nicht ausloesen."""
    agent = _make_agent_stub()
    task = "kannst du dieses Problem beheben"  # kein Handoff-Block
    agent._current_task_text = task
    answer = "Welches Problem? Ich sehe keine konkrete Frage."
    redirect = agent._build_meta_frame_answer_redirect_prompt(task, answer)
    # Ohne Handoff: kein Frame, kein Redirect.
    assert redirect is None


def test_ccf5_authority_without_objective_no_redirect():
    """Wenn primary_objective leer ist, darf CCF5 nicht greifen."""
    agent = _make_agent_stub()
    authority = {
        "schema_version": 1,
        "primary_objective": "",
        "allowed_context_classes": ["conversation_state"],
        "forbidden_context_classes": [],
    }
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        f"meta_context_authority_json: {json.dumps(authority)}\n"
        "# ORIGINAL USER TASK\n"
        "kannst du dieses Problem beheben\n"
    )
    agent._current_task_text = task
    answer = "Welches Problem? Ich sehe keine konkrete Frage."
    redirect = agent._build_meta_frame_answer_redirect_prompt(task, answer)
    # primary_objective leer: kein Redirect
    # (Es koennte aber andere Pfade geben - wir erwarten None.)
    # Der CCF5-Pfad selbst loest nicht aus.
    if redirect is not None:
        # Falls ein anderer Pfad triggert, darf es nicht CCF5 sein
        assert "CCF5" not in redirect


def test_ccf5_authority_without_conversation_state_no_redirect():
    """Wenn conversation_state nicht in allowed_classes ist,
    soll CCF5 nicht ausloesen.
    """
    agent = _make_agent_stub()
    task = _meta_handoff_text(
        primary_objective="Recherche zu KI-Trends",
        allowed_classes=["semantic_recall"],  # kein conversation_state
    )
    agent._current_task_text = task
    answer = "Welches Problem? Der Kontext ist leer."
    redirect = agent._build_meta_frame_answer_redirect_prompt(task, answer)
    # Mindestens nicht CCF5-spezifisch
    if redirect is not None:
        assert "CCF5" not in redirect

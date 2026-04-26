"""CCF3 Integration: Deictic Reference Resolver in Meta-Orchestration und
Handoff."""

from __future__ import annotations

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.meta_orchestration import classify_meta_task


def test_ccf3_classify_meta_task_emits_deictic_reference_field():
    result = classify_meta_task(
        "kannst du dieses Problem beheben",
        action_count=0,
    )
    assert "deictic_reference" in result
    deictic = result["deictic_reference"]
    assert isinstance(deictic, dict)
    assert deictic["has_reference"] is True
    assert deictic["reference_kind"] == "self_problem"


def test_ccf3_classify_meta_task_no_reference_returns_empty_marker():
    result = classify_meta_task(
        "wie ist das wetter morgen in berlin",
        action_count=0,
    )
    assert "deictic_reference" in result
    assert result["deictic_reference"]["has_reference"] is False


def test_ccf3_recall_query_resolves_to_recent_user_turn():
    result = classify_meta_task(
        "worueber hatte ich dich eben gebeten",
        recent_user_turns=[
            "ich will ein Unternehmen gruenden mit KI",
        ],
        recent_assistant_turns=[
            "Was bringst du mit?",
        ],
        conversation_state={
            "active_topic": "Unternehmensgruendung mit KI",
            "active_goal": "Skills nennen",
            "active_domain": "topic_advisory",
            "open_loop": "Skills nennen",
            "next_expected_step": "Skills nennen",
            "turn_type_hint": "followup",
        },
    )
    deictic = result.get("deictic_reference") or {}
    # Bei classify_meta_task ohne Followup-Capsule-Block liegt last_user
    # nicht direkt im query, deshalb Confidence ggf. niedrig.
    # Aber active_topic ist im dialog_state -> Trigger erkannt.
    assert deictic.get("has_reference") is True
    assert deictic.get("reference_kind") == "recall"


def test_ccf3_handoff_carries_deictic_reference_json():
    """Der Dispatcher-Handoff muss deictic_reference_json mittragen,
    damit der base_agent den Guard aktivieren kann.
    """
    from main_dispatcher import _render_meta_handoff_block  # type: ignore

    payload = {
        "task_type": "single_lane",
        "recommended_agent_chain": ["meta"],
        "reason": "test",
        "deictic_reference": {
            "schema_version": 1,
            "has_reference": True,
            "reference_kind": "self_problem",
            "trigger_phrase": "dieses problem",
            "resolved_reference": "Conversation-State abgeschnitten",
            "source_anchor": "last_assistant",
            "confidence": 0.8,
            "fallback_question": "",
        },
    }
    handoff_text = _render_meta_handoff_block(payload)
    assert "deictic_reference_json:" in handoff_text
    # JSON in der Zeile muss valide parsen
    for line in handoff_text.splitlines():
        if line.startswith("deictic_reference_json:"):
            json_part = line.split("deictic_reference_json:", 1)[1].strip()
            parsed = json.loads(json_part)
            assert parsed["has_reference"] is True
            assert parsed["reference_kind"] == "self_problem"
            break
    else:
        raise AssertionError("deictic_reference_json zeile nicht gefunden")


def test_ccf3_base_agent_extract_helper_parses_deictic_reference():
    """base_agent._extract_meta_deictic_reference muss aus einem
    fertigen Task-Text mit Handoff-Block die Deictic-Resolution lesen.
    """
    from agent.base_agent import BaseAgent  # type: ignore

    task_text = (
        "# META ORCHESTRATION HANDOFF\n"
        'meta_request_frame_json: {"frame_kind":"clarify_needed","task_domain":"topic_advisory"}\n'
        'deictic_reference_json: {"schema_version":1,"has_reference":true,'
        '"reference_kind":"self_problem","trigger_phrase":"dieses problem",'
        '"resolved_reference":"Letzter Drift","source_anchor":"last_assistant",'
        '"confidence":0.8,"fallback_question":""}\n'
        "# ORIGINAL USER TASK\n"
        "kannst du dieses Problem beheben\n"
    )
    parsed = BaseAgent._extract_meta_deictic_reference(task_text)
    assert parsed["has_reference"] is True
    assert parsed["reference_kind"] == "self_problem"
    assert float(parsed["confidence"]) >= 0.7


def test_ccf3_base_agent_extract_helper_returns_empty_without_handoff():
    from agent.base_agent import BaseAgent  # type: ignore

    parsed = BaseAgent._extract_meta_deictic_reference("kannst du das beheben")
    assert parsed == {}

"""Executable evaluation cases and scoring for D0 meta context state behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from orchestration.meta_context_eval import MetaContextEvalCase, evaluate_meta_context_case
from orchestration.meta_orchestration import classify_meta_task


@dataclass(frozen=True)
class MetaContextStateEvalCase:
    label: str
    query: str
    family: str = "general"
    action_count: int = 0
    conversation_state: Mapping[str, Any] | None = None
    recent_user_turns: Sequence[str] = field(default_factory=tuple)
    recent_assistant_turns: Sequence[str] = field(default_factory=tuple)
    session_summary: str = ""
    topic_memory_hits: Sequence[Any] = field(default_factory=tuple)
    preference_memory_hits: Sequence[Any] = field(default_factory=tuple)
    semantic_recall_hits: Sequence[Any] = field(default_factory=tuple)
    expected_task_type: str = ""
    expected_chain: Sequence[str] = field(default_factory=tuple)
    expected_turn_type: str = ""
    expected_response_mode: str = ""
    expected_reason_contains: str = ""
    expected_slots: Sequence[str] = field(default_factory=tuple)
    expected_signals: Sequence[str] = field(default_factory=tuple)
    expected_suspicious: bool = False


D0_META_CONTEXT_STATE_EVAL_CASES: list[MetaContextStateEvalCase] = [
    MetaContextStateEvalCase(
        label="behavior_instruction_news_policy",
        family="preference_instruction",
        query="dann mach das in zukunft so dass du auf echtzeit agenturmeldungen zugreifst bei news und aktuellem geschehen",
        conversation_state={
            "session_id": "d07_behavior",
            "active_topic": "aktuelle Weltlage und News-Qualitaet",
            "active_goal": "belastbare Live-News",
            "open_loop": "Reuters und AP priorisieren",
            "next_expected_step": "Praeferenz bestaetigen",
            "preferences": ["ehrlich Grenzen nennen"],
        },
        recent_user_turns=("wie stehts um die aktuelle weltlage",),
        expected_task_type="single_lane",
        expected_chain=("meta",),
        expected_turn_type="behavior_instruction",
        expected_response_mode="acknowledge_and_store",
        expected_reason_contains="semantic_preference_alignment",
        expected_slots=("conversation_state", "open_loop", "recent_user_turn"),
        expected_signals=("behavior_instruction", "preference_update"),
    ),
    MetaContextStateEvalCase(
        label="correction_realigns_live_news_path",
        family="correction",
        query=(
            "# FOLLOW-UP CONTEXT\n"
            "last_agent: meta\n"
            "session_id: d07_correction\n"
            "last_user: wie stehts um die weltlage\n"
            "pending_followup_prompt: Soll ich aktuelle News oder eine tiefere Analyse priorisieren?\n"
            "\n"
            "# CURRENT USER QUERY\n"
            "nein, ich meinte aktuelle news und nicht wieder lokale nearby treffer"
        ),
        conversation_state={
            "session_id": "d07_correction",
            "active_topic": "aktuelle Weltlage und News-Qualitaet",
            "active_goal": "belastbare aktuelle Nachrichten",
            "open_loop": "aktuelle News priorisieren",
            "next_expected_step": "Live-Recherche neu ausrichten",
        },
        recent_user_turns=("wie stehts um die weltlage",),
        expected_task_type="single_lane",
        expected_chain=("meta",),
        expected_turn_type="correction",
        expected_response_mode="correct_previous_path",
        expected_reason_contains="turn_understanding:correction",
        expected_slots=("conversation_state", "open_loop", "recent_user_turn"),
        expected_signals=("correction_language", "followup_context_present"),
    ),
    MetaContextStateEvalCase(
        label="short_option_resume",
        family="reference_followup",
        query=(
            "# FOLLOW-UP CONTEXT\n"
            "last_agent: meta\n"
            "session_id: d07_option\n"
            "last_user: soll ich fuer amsterdam lieber mit dem zug oder mit dem auto fahren\n"
            "pending_followup_prompt: Waehle eine der zwei Optionen und ich arbeite sie aus\n"
            "\n"
            "# CURRENT USER QUERY\n"
            "die erste option"
        ),
        conversation_state={
            "session_id": "d07_option",
            "active_topic": "Amsterdam Reisevergleich",
            "active_goal": "Beste Reiseoption zwischen Zug und Auto finden",
            "open_loop": "Waehle eine der zwei Optionen und ich arbeite sie aus",
            "next_expected_step": "Waehle eine Option",
        },
        recent_user_turns=("soll ich fuer amsterdam lieber mit dem zug oder mit dem auto fahren",),
        expected_task_type="single_lane",
        expected_chain=("meta",),
        expected_turn_type="handover_resume",
        expected_response_mode="resume_open_loop",
        expected_slots=("conversation_state", "open_loop", "recent_user_turn"),
        expected_signals=("handover_resume_language", "followup_context_present"),
    ),
    MetaContextStateEvalCase(
        label="topic_resumption_after_gap_uses_memory",
        family="topic_resumption",
        query="so aber mit live-news",
        conversation_state={
            "session_id": "d07_resume_gap",
            "active_topic": "aktuelle Weltlage und News-Qualitaet",
            "active_goal": "belastbare aktuelle Nachrichten",
            "open_loop": "Reuters und AP zuerst pruefen",
            "next_expected_step": "schnelle Live-Recherche mit Agenturquellen",
        },
        recent_user_turns=("wie stehts um die aktuelle weltlage",),
        session_summary="Vor einigen Tagen ging es um News-Qualitaet und belastbare Live-Quellen.",
        topic_memory_hits=(
            {
                "content": "Topic memory: Bei aktueller Weltlage sollten Reuters und AP zuerst geprueft werden.",
                "category": "topic_memory",
                "relevance": 0.92,
            },
        ),
        expected_task_type="simple_live_lookup",
        expected_chain=("meta", "executor"),
        expected_turn_type="followup",
        expected_response_mode="resume_open_loop",
        expected_reason_contains="simple_live_lookup",
        expected_slots=("conversation_state", "open_loop", "recent_user_turn", "topic_memory"),
        expected_signals=("short_contextual_followup_language", "active_topic_present"),
    ),
    MetaContextStateEvalCase(
        label="complaint_plus_instruction_prefers_storeable_alignment",
        family="complaint_plus_instruction",
        query=(
            "# FOLLOW-UP CONTEXT\n"
            "last_agent: meta\n"
            "session_id: d07_complaint\n"
            "last_user: wie stehts um die aktuelle weltlage\n"
            "last_assistant: Ich habe gerade keine brauchbaren News-Treffer gefunden.\n"
            "\n"
            "# CURRENT USER QUERY\n"
            "du hast die letzte antwort wieder voellig aus dem kontext gezogen, dann mach das in zukunft so dass du bei news reuters und ap zuerst nimmst"
        ),
        conversation_state={
            "session_id": "d07_complaint",
            "active_topic": "aktuelle Weltlage und News-Qualitaet",
            "active_goal": "brauchbare aktuelle News mit belastbaren Quellen",
            "open_loop": "News-Strategie korrigieren",
            "recent_corrections": ["nicht wieder lokale oder unpassende Quellen priorisieren"],
        },
        recent_user_turns=("wie stehts um die aktuelle weltlage",),
        recent_assistant_turns=("Ich habe gerade keine brauchbaren News-Treffer gefunden.",),
        expected_task_type="single_lane",
        expected_chain=("meta",),
        expected_turn_type="behavior_instruction",
        expected_response_mode="acknowledge_and_store",
        expected_reason_contains="semantic_preference_alignment",
        expected_slots=("conversation_state", "open_loop", "recent_user_turn"),
        expected_signals=("complaint_language", "behavior_instruction", "preference_update"),
    ),
    MetaContextStateEvalCase(
        label="approval_resume_keeps_open_loop",
        family="approval_resume",
        query=(
            "# FOLLOW-UP CONTEXT\n"
            "last_agent: meta\n"
            "session_id: d07_approval\n"
            "last_user: soll ich die recherche direkt starten\n"
            "pending_followup_prompt: Bestaetige kurz und ich starte die Recherche\n"
            "\n"
            "# CURRENT USER QUERY\n"
            "ja mach das"
        ),
        conversation_state={
            "session_id": "d07_approval",
            "active_topic": "Recherche zu aktuellem KI-Markt",
            "active_goal": "kompakte Live-Recherche starten",
            "open_loop": "Bestaetige kurz und ich starte die Recherche",
            "next_expected_step": "Startfreigabe",
        },
        recent_user_turns=("soll ich die recherche direkt starten",),
        expected_task_type="single_lane",
        expected_chain=("meta",),
        expected_turn_type="approval_response",
        expected_response_mode="resume_open_loop",
        expected_slots=("conversation_state", "open_loop", "recent_user_turn"),
        expected_signals=("approval_language", "followup_context_present"),
    ),
    MetaContextStateEvalCase(
        label="auth_resume_stays_meta_bounded",
        family="auth_resume",
        query=(
            "# FOLLOW-UP CONTEXT\n"
            "last_agent: meta\n"
            "session_id: d07_auth\n"
            "last_user: wenn login noetig ist sag bescheid\n"
            "pending_followup_prompt: Fuer X koennte Login oder Nutzerfreigabe noetig werden\n"
            "\n"
            "# CURRENT USER QUERY\n"
            "ok nutze meinen zugang und sag wenn du login brauchst"
        ),
        conversation_state={
            "session_id": "d07_auth",
            "active_topic": "X-Live-Recherche",
            "active_goal": "bei Bedarf authentifizierten Zugriff sauber handhaben",
            "open_loop": "Login-Bedarf explizit behandeln",
            "next_expected_step": "Auth-Antwort auswerten",
        },
        recent_user_turns=("wenn login noetig ist sag bescheid",),
        expected_task_type="single_lane",
        expected_chain=("meta",),
        expected_turn_type="auth_response",
        expected_response_mode="resume_open_loop",
        expected_slots=("conversation_state", "open_loop", "recent_user_turn"),
        expected_signals=("auth_language", "followup_context_present"),
    ),
]


def _sequence_matches(actual: Sequence[str], expected: Sequence[str]) -> bool:
    return list(actual) == list(expected)


def _slot_score(actual_slot_types: Sequence[str], expected_slots: Sequence[str]) -> float:
    if not expected_slots:
        return 1.0
    matched = sum(1 for slot in expected_slots if slot in actual_slot_types)
    return round(matched / len(expected_slots), 3)


def _signal_score(actual_signals: Sequence[str], expected_signals: Sequence[str]) -> float:
    if not expected_signals:
        return 1.0
    matched = sum(1 for signal in expected_signals if signal in actual_signals)
    return round(matched / len(expected_signals), 3)


def evaluate_meta_context_state_case(case: MetaContextStateEvalCase) -> dict[str, Any]:
    decision = classify_meta_task(
        case.query,
        action_count=int(case.action_count),
        conversation_state=case.conversation_state,
        recent_user_turns=case.recent_user_turns,
        recent_assistant_turns=case.recent_assistant_turns,
        session_summary=case.session_summary,
        topic_memory_hits=case.topic_memory_hits,
        preference_memory_hits=case.preference_memory_hits,
        semantic_recall_hits=case.semantic_recall_hits,
    )
    context_eval = evaluate_meta_context_case(
        MetaContextEvalCase(
            label=case.label,
            bundle=dict(decision.get("meta_context_bundle") or {}),
            dominant_turn_type=str(decision.get("dominant_turn_type") or ""),
            response_mode=str(decision.get("response_mode") or ""),
            expected_slots=list(case.expected_slots),
            forbidden_suppression_reasons=[],
            expected_suspicious=case.expected_suspicious,
        )
    )

    actual_chain = list(decision.get("recommended_agent_chain") or [])
    actual_slot_types = list(decision.get("meta_context_slot_types") or [])
    actual_signals = list(decision.get("turn_signals") or [])
    actual_reason = str(decision.get("reason") or "")

    benchmark = {
        "task_type_match": str(decision.get("task_type") or "") == str(case.expected_task_type or ""),
        "chain_match": _sequence_matches(actual_chain, case.expected_chain),
        "turn_type_match": str(decision.get("dominant_turn_type") or "") == str(case.expected_turn_type or ""),
        "response_mode_match": str(decision.get("response_mode") or "") == str(case.expected_response_mode or ""),
        "reason_match": (not case.expected_reason_contains) or (case.expected_reason_contains in actual_reason),
        "slot_score": _slot_score(actual_slot_types, case.expected_slots),
        "signal_score": _signal_score(actual_signals, case.expected_signals),
        "context_eval_passes": bool(context_eval.get("passes")),
    }
    total_checks = 8
    passed_total = sum(
        1
        for key in ("task_type_match", "chain_match", "turn_type_match", "response_mode_match", "reason_match", "context_eval_passes")
        if benchmark[key]
    )
    passed_total += 1 if float(benchmark["slot_score"]) >= 1.0 else 0
    passed_total += 1 if float(benchmark["signal_score"]) >= 1.0 else 0
    score = round(passed_total / total_checks, 3)

    return {
        "label": case.label,
        "family": case.family,
        "decision": decision,
        "context_eval": context_eval,
        "benchmark": benchmark,
        "score": score,
        "passed": (
            benchmark["task_type_match"]
            and benchmark["chain_match"]
            and benchmark["turn_type_match"]
            and benchmark["response_mode_match"]
            and benchmark["reason_match"]
            and benchmark["context_eval_passes"]
            and float(benchmark["slot_score"]) >= 1.0
            and float(benchmark["signal_score"]) >= 1.0
        ),
    }


def summarize_meta_context_state_evals(
    cases: Sequence[MetaContextStateEvalCase],
) -> dict[str, Any]:
    if not cases:
        return {
            "total_cases": 0,
            "pass_rate": 0.0,
            "avg_score": 0.0,
            "avg_slot_score": 0.0,
            "avg_signal_score": 0.0,
            "quality_score": 0.0,
            "gate_passed": False,
            "by_family": {},
            "results": [],
        }

    results = [evaluate_meta_context_state_case(case) for case in cases]
    total = len(results)
    by_family: dict[str, dict[str, Any]] = {}
    for item in results:
        family = str(item.get("family") or "general")
        bucket = by_family.setdefault(
            family,
            {
                "total_cases": 0,
                "passed_cases": 0,
                "avg_score": 0.0,
                "avg_slot_score": 0.0,
                "avg_signal_score": 0.0,
            },
        )
        bucket["total_cases"] += 1
        bucket["passed_cases"] += 1 if item["passed"] else 0
        bucket["avg_score"] += float(item["score"])
        bucket["avg_slot_score"] += float(item["benchmark"]["slot_score"])
        bucket["avg_signal_score"] += float(item["benchmark"]["signal_score"])
    for bucket in by_family.values():
        count = int(bucket["total_cases"] or 0) or 1
        bucket["pass_rate"] = round(int(bucket["passed_cases"] or 0) / count, 3)
        bucket["avg_score"] = round(float(bucket["avg_score"]) / count, 3)
        bucket["avg_slot_score"] = round(float(bucket["avg_slot_score"]) / count, 3)
        bucket["avg_signal_score"] = round(float(bucket["avg_signal_score"]) / count, 3)

    pass_rate = round(sum(1 for item in results if item["passed"]) / total, 3)
    avg_score = round(sum(float(item["score"]) for item in results) / total, 3)
    avg_slot_score = round(sum(float(item["benchmark"]["slot_score"]) for item in results) / total, 3)
    avg_signal_score = round(sum(float(item["benchmark"]["signal_score"]) for item in results) / total, 3)
    quality_score = round((pass_rate * 0.5) + (avg_score * 0.3) + (avg_slot_score * 0.1) + (avg_signal_score * 0.1), 3)
    return {
        "total_cases": total,
        "pass_rate": pass_rate,
        "avg_score": avg_score,
        "avg_slot_score": avg_slot_score,
        "avg_signal_score": avg_signal_score,
        "quality_score": quality_score,
        "gate_passed": bool(pass_rate >= 0.95 and avg_slot_score >= 0.95 and avg_signal_score >= 0.9),
        "by_family": by_family,
        "results": results,
    }

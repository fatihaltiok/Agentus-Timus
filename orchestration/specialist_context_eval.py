"""Executable eval cases for D0.9 specialist context propagation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from agent.agents.research import DeepResearchAgent
from agent.agents.system import SystemAgent
from agent.agents.visual import VisualAgent
from agent.shared.delegation_handoff import parse_delegation_handoff
from orchestration.specialist_context import (
    build_specialist_context_payload,
    format_specialist_signal_response,
    parse_specialist_signal_response,
)


@dataclass(frozen=True)
class SpecialistContextEvalCase:
    label: str
    family: str
    actual: str
    expected: str
    score: float
    passed: bool


def _sample_handoff(agent: str, goal: str, specialist_context: dict[str, Any], extra_lines: Sequence[str] = ()) -> str:
    lines = [
        "# DELEGATION HANDOFF",
        f"target_agent: {agent}",
        f"goal: {goal}",
        "expected_output: structured_output",
        "success_signal: ok",
        "handoff_data:",
        f"- specialist_context_json: {__import__('json').dumps(specialist_context, ensure_ascii=False, sort_keys=True)}",
    ]
    lines.extend(extra_lines)
    return "\n".join(lines)


def evaluate_specialist_context_cases() -> list[SpecialistContextEvalCase]:
    results: list[SpecialistContextEvalCase] = []

    research_ctx = build_specialist_context_payload(
        current_topic="Live-News",
        active_goal="Belastbare Quellen knapp zusammenfassen",
        open_loop="News-Faden fortsetzen",
        next_expected_step="Bitte knapp zusammenfassen",
        turn_type="followup",
        response_mode="execute",
        user_preferences=["Quellen zuerst", "Bitte kurz"],
    )
    research_agent = object.__new__(DeepResearchAgent)
    research_handoff = parse_delegation_handoff(
        _sample_handoff(
            "research",
            "Fasse die Lage kompakt zusammen.",
            research_ctx,
            extra_lines=(
                "- source_urls: https://example.com/a",
                "- captured_context: erste Notizen vorhanden",
            ),
        )
    )
    research_policy = research_agent._derive_research_context_policy(research_handoff, research_ctx)
    research_actual = research_agent._research_strategy_mode(research_policy)
    results.append(
        SpecialistContextEvalCase(
            label="research_source_first_compact",
            family="research",
            actual=research_actual,
            expected="source_first_compact",
            score=1.0 if research_actual == "source_first_compact" else 0.0,
            passed=research_actual == "source_first_compact",
        )
    )

    visual_agent = object.__new__(VisualAgent)
    visual_text_ctx = build_specialist_context_payload(
        current_topic="Dialog lesen",
        active_goal="Zuerst sichtbaren Text lesen",
        open_loop="OCR zuerst",
        next_expected_step="Bitte zuerst den sichtbaren Text lesen",
        turn_type="followup",
        response_mode="execute",
        user_preferences=["OCR/Text zuerst"],
    )
    visual_text_handoff = parse_delegation_handoff(
        _sample_handoff(
            "visual",
            "Lies den sichtbaren Text im Dialog und gib ihn wieder.",
            visual_text_ctx,
            extra_lines=(
                "- source_url: https://example.com/login",
                "- expected_state: login_dialog",
            ),
        )
    )
    visual_text_mode = visual_agent._choose_visual_strategy_mode(
        visual_text_handoff,
        visual_text_ctx,
        "Lies den sichtbaren Text im Dialog und gib ihn wieder.",
    )
    results.append(
        SpecialistContextEvalCase(
            label="visual_text_prefers_vision_first",
            family="visual",
            actual=visual_text_mode,
            expected="vision_first",
            score=1.0 if visual_text_mode == "vision_first" else 0.0,
            passed=visual_text_mode == "vision_first",
        )
    )

    visual_browser_ctx = build_specialist_context_payload(
        current_topic="Browser-Login",
        active_goal="Login-Dialog oeffnen",
        open_loop="UI-Aktion offen",
        turn_type="followup",
        response_mode="execute",
    )
    visual_browser_handoff = parse_delegation_handoff(
        _sample_handoff(
            "visual",
            "Oeffne die Website und pruefe den Login-Dialog.",
            visual_browser_ctx,
            extra_lines=(
                "- source_url: https://example.com/login",
                "- expected_state: login_dialog",
            ),
        )
    )
    visual_browser_mode = visual_agent._choose_visual_strategy_mode(
        visual_browser_handoff,
        visual_browser_ctx,
        "Oeffne die Website und pruefe den Login-Dialog.",
    )
    results.append(
        SpecialistContextEvalCase(
            label="visual_browser_prefers_structured_navigation",
            family="visual",
            actual=visual_browser_mode,
            expected="structured_navigation",
            score=1.0 if visual_browser_mode == "structured_navigation" else 0.0,
            passed=visual_browser_mode == "structured_navigation",
        )
    )

    system_agent = object.__new__(SystemAgent)
    system_ctx = build_specialist_context_payload(
        current_topic="Runtime-Status",
        active_goal="Status des MCP zusammenfassen",
        open_loop="Health-Frage beantworten",
        turn_type="followup",
        response_mode="summarize_state",
        user_preferences=["Bitte kurz"],
    )
    system_handoff = parse_delegation_handoff(
        _sample_handoff(
            "system",
            "Pruefe den Zustand von timus-mcp und fasse ihn kurz zusammen.",
            system_ctx,
            extra_lines=(
                "- service_name: timus-mcp",
                "- expected_state: active",
            ),
        )
    )
    system_plan = system_agent._derive_system_snapshot_plan(system_handoff, system_ctx)
    system_actual = (
        "compact_service_snapshot"
        if system_plan.get("compact")
        else ("service_snapshot" if system_plan.get("preferred_service") else "full_snapshot")
    )
    results.append(
        SpecialistContextEvalCase(
            label="system_summary_prefers_compact_service_snapshot",
            family="system",
            actual=system_actual,
            expected="compact_service_snapshot",
            score=1.0 if system_actual == "compact_service_snapshot" else 0.0,
            passed=system_actual == "compact_service_snapshot",
        )
    )

    signal_text = format_specialist_signal_response(
        "needs_meta_reframe",
        reason="state_mode_conflicts_with_action_task",
        message="Meta sollte erst neu rahmen.",
    )
    signal_payload = parse_specialist_signal_response(signal_text)
    signal_actual = str(signal_payload.get("signal") or "")
    results.append(
        SpecialistContextEvalCase(
            label="specialist_signal_contract_roundtrip",
            family="signal_contract",
            actual=signal_actual,
            expected="needs_meta_reframe",
            score=1.0 if signal_actual == "needs_meta_reframe" else 0.0,
            passed=signal_actual == "needs_meta_reframe",
        )
    )
    return results


def summarize_specialist_context_evals() -> dict[str, Any]:
    results = evaluate_specialist_context_cases()
    total = len(results)
    if total == 0:
        return {
            "total_cases": 0,
            "pass_rate": 0.0,
            "avg_score": 0.0,
            "gate_passed": False,
            "by_family": {},
            "results": [],
        }
    by_family: dict[str, dict[str, Any]] = {}
    for item in results:
        bucket = by_family.setdefault(
            item.family,
            {"total_cases": 0, "passed_cases": 0, "avg_score": 0.0},
        )
        bucket["total_cases"] += 1
        bucket["passed_cases"] += 1 if item.passed else 0
        bucket["avg_score"] += float(item.score)
    for bucket in by_family.values():
        count = int(bucket["total_cases"] or 0) or 1
        bucket["pass_rate"] = round(int(bucket["passed_cases"] or 0) / count, 3)
        bucket["avg_score"] = round(float(bucket["avg_score"]) / count, 3)
    pass_rate = round(sum(1 for item in results if item.passed) / total, 3)
    avg_score = round(sum(float(item.score) for item in results) / total, 3)
    return {
        "total_cases": total,
        "pass_rate": pass_rate,
        "avg_score": avg_score,
        "gate_passed": bool(pass_rate >= 1.0 and avg_score >= 0.99),
        "by_family": by_family,
        "results": [
            {
                "label": item.label,
                "family": item.family,
                "actual": item.actual,
                "expected": item.expected,
                "score": item.score,
                "passed": item.passed,
            }
            for item in results
        ],
    }

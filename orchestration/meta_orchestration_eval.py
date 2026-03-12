"""Canonical evaluation cases and benchmark scoring for Meta Orchestration v2."""

from __future__ import annotations

from typing import Any, Dict, List

from orchestration.orchestration_policy import evaluate_query_orchestration


META_ORCHESTRATION_EVAL_CASES: List[Dict[str, Any]] = [
    {
        "name": "youtube_content_extraction",
        "query": "Öffne YouTube, hole maximal viel Inhalt aus dem Video und schreibe einen Bericht",
        "expected_route_to_meta": True,
        "expected_task_type": "youtube_content_extraction",
        "expected_entry_agent": "meta",
        "expected_agent_chain": ["meta", "visual", "research", "document"],
        "expected_recipe_id": "youtube_content_extraction",
        "expected_structured_handoff": True,
        "expected_capabilities": ["browser_navigation", "content_extraction", "document_creation"],
    },
    {
        "name": "x_thread_summary",
        "query": "Öffne x.com, lies den Thread zu KI-Agenten und fasse die wichtigsten Punkte zusammen",
        "expected_route_to_meta": True,
        "expected_task_type": "web_content_extraction",
        "expected_entry_agent": "meta",
        "expected_agent_chain": ["meta", "visual", "research"],
        "expected_recipe_id": None,
        "expected_structured_handoff": True,
        "expected_capabilities": ["browser_navigation", "content_extraction"],
    },
    {
        "name": "booking_search",
        "query": "Öffne booking.com, gib Berlin ein, wähle Daten und starte die Suche",
        "expected_route_to_meta": True,
        "expected_task_type": "multi_stage_web_task",
        "expected_entry_agent": "meta",
        "expected_agent_chain": ["meta", "visual"],
        "expected_recipe_id": "booking_search",
        "expected_structured_handoff": True,
        "expected_capabilities": ["browser_navigation"],
    },
    {
        "name": "system_diagnosis",
        "query": "Prüfe die Logs, analysiere journalctl und starte den Service per systemctl bei Bedarf neu",
        "expected_route_to_meta": True,
        "expected_task_type": "system_diagnosis",
        "expected_entry_agent": "meta",
        "expected_agent_chain": ["meta", "system", "shell"],
        "expected_recipe_id": "system_diagnosis",
        "expected_structured_handoff": True,
        "expected_capabilities": ["diagnostics", "terminal_execution"],
    },
    {
        "name": "simple_booking_navigation_guard",
        "query": "Starte den Browser und gehe auf booking.com",
        "expected_route_to_meta": False,
        "expected_task_type": "ui_navigation",
        "expected_entry_agent": "visual",
        "expected_agent_chain": ["visual"],
        "expected_recipe_id": None,
        "expected_structured_handoff": False,
        "expected_capabilities": ["browser_navigation"],
    },
]


def _score_ratio(passed: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return round(max(0.0, min(1.0, passed / total)), 3)


def evaluate_meta_orchestration_case(case: Dict[str, Any]) -> Dict[str, Any]:
    query = str(case.get("query", "") or "")
    expected_capabilities = list(case.get("expected_capabilities") or [])
    decision = evaluate_query_orchestration(query)

    route_match = bool(decision.get("route_to_meta", False)) == bool(case.get("expected_route_to_meta", False))
    task_type_match = str(decision.get("task_type") or "") == str(case.get("expected_task_type") or "")
    entry_match = str(decision.get("recommended_entry_agent") or "") == str(case.get("expected_entry_agent") or "")
    chain_match = list(decision.get("recommended_agent_chain") or []) == list(case.get("expected_agent_chain") or [])
    recipe_match = str(decision.get("recommended_recipe_id") or "") == str(case.get("expected_recipe_id") or "")
    handoff_match = bool(decision.get("needs_structured_handoff", False)) == bool(
        case.get("expected_structured_handoff", False)
    )

    actual_capabilities = list(decision.get("required_capabilities") or [])
    matched_capabilities = [item for item in expected_capabilities if item in actual_capabilities]
    capability_score = _score_ratio(len(matched_capabilities), len(expected_capabilities))

    dimension_results = {
        "route_match": route_match,
        "task_type_match": task_type_match,
        "entry_match": entry_match,
        "chain_match": chain_match,
        "recipe_match": recipe_match,
        "handoff_match": handoff_match,
        "capability_score": capability_score,
    }
    passed_checks = sum(
        1
        for key, value in dimension_results.items()
        if key != "capability_score" and bool(value)
    )
    total_checks = 6 + (1 if expected_capabilities else 0)
    passed_total = passed_checks + (1 if capability_score >= 1.0 else 0)
    score = _score_ratio(passed_total, total_checks)

    return {
        "name": case.get("name", ""),
        "query": query,
        "decision": decision,
        "expected": {
            "route_to_meta": bool(case.get("expected_route_to_meta", False)),
            "task_type": case.get("expected_task_type"),
            "entry_agent": case.get("expected_entry_agent"),
            "agent_chain": list(case.get("expected_agent_chain") or []),
            "recipe_id": case.get("expected_recipe_id"),
            "structured_handoff": bool(case.get("expected_structured_handoff", False)),
            "capabilities": expected_capabilities,
        },
        "matched_capabilities": matched_capabilities,
        "missing_capabilities": [item for item in expected_capabilities if item not in matched_capabilities],
        "benchmark": dimension_results,
        "score": score,
        "passed": (
            route_match
            and task_type_match
            and entry_match
            and chain_match
            and recipe_match
            and handoff_match
            and capability_score >= 1.0
        ),
    }


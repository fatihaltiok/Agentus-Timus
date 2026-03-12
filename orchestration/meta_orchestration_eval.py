"""Canonical evaluation cases and benchmark scoring for Meta Orchestration v2."""

from __future__ import annotations

from typing import Any, Dict, List

from agent.agents.meta import MetaAgent
from orchestration.meta_self_state import build_meta_self_state
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
        "expected_alternative_recipe_ids": ["youtube_search_then_visual", "youtube_research_only"],
        "expected_recovery_stage_ids": ["research_context_recovery"],
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
        "expected_recipe_id": "web_visual_research_summary",
        "expected_alternative_recipe_ids": ["web_research_only"],
        "expected_recovery_stage_ids": ["research_context_recovery"],
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
        "expected_alternative_recipe_ids": [],
        "expected_recovery_stage_ids": [],
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
        "expected_alternative_recipe_ids": ["system_shell_probe_first"],
        "expected_recovery_stage_ids": ["shell_runtime_probe"],
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
        "expected_alternative_recipe_ids": [],
        "expected_recovery_stage_ids": [],
        "expected_structured_handoff": False,
        "expected_capabilities": ["browser_navigation"],
    },
]


META_REPLAN_EVAL_CASES: List[Dict[str, Any]] = [
    {
        "name": "youtube_blocked_runtime_prefers_research_only",
        "query": "Öffne YouTube, hole maximal viel Inhalt aus dem Video und schreibe einen Bericht",
        "runtime_constraints": {
            "budget_state": "soft_limit",
            "stability_gate_state": "blocked",
            "degrade_mode": "degraded",
            "open_incidents": 1,
            "circuit_breakers_open": 1,
            "resource_guard_state": "active",
            "resource_guard_reason": "browser_unstable",
            "quarantined_incidents": 0,
            "cooldown_incidents": 1,
            "known_bad_patterns": 1,
            "release_blocked": True,
            "autonomy_hold": True,
        },
        "expected_initial_recipe": "youtube_research_only",
    },
    {
        "name": "youtube_learning_prefers_search_then_visual",
        "query": "Öffne YouTube, hole maximal viel Inhalt aus dem Video und schreibe einen Bericht",
        "learning_snapshot": {
            "posture": "conservative",
            "recipe_score": 0.84,
            "site_recipe_score": 0.8,
        },
        "alternative_recipe_scores": [
            {
                "recipe_id": "youtube_search_then_visual",
                "recipe_score": 1.21,
                "recipe_evidence": 4,
                "site_recipe_key": "youtube::youtube_search_then_visual",
                "site_recipe_score": 1.12,
                "site_recipe_evidence": 4,
            }
        ],
        "expected_initial_recipe": "youtube_search_then_visual",
    },
    {
        "name": "x_visual_failure_replans_to_research_only",
        "query": "Öffne x.com, lies den Thread zu KI-Agenten und fasse die wichtigsten Punkte zusammen",
        "failed_stage": {"stage_id": "visual_access", "agent": "visual"},
        "expected_replan_recipe": "web_research_only",
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
    actual_alternative_ids = [str(item.get("recipe_id") or "") for item in (decision.get("alternative_recipes") or [])]
    actual_recovery_ids = [str(item.get("recovery_stage_id") or "") for item in (decision.get("recipe_recoveries") or [])]
    alternative_match = actual_alternative_ids == list(case.get("expected_alternative_recipe_ids") or [])
    recovery_match = actual_recovery_ids == list(case.get("expected_recovery_stage_ids") or [])
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
        "alternative_match": alternative_match,
        "recovery_match": recovery_match,
        "handoff_match": handoff_match,
        "capability_score": capability_score,
    }
    passed_checks = sum(
        1
        for key, value in dimension_results.items()
        if key != "capability_score" and bool(value)
    )
    total_checks = 8 + (1 if expected_capabilities else 0)
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
            "alternative_recipe_ids": list(case.get("expected_alternative_recipe_ids") or []),
            "recovery_stage_ids": list(case.get("expected_recovery_stage_ids") or []),
            "structured_handoff": bool(case.get("expected_structured_handoff", False)),
            "capabilities": expected_capabilities,
        },
        "actual_alternative_recipe_ids": actual_alternative_ids,
        "actual_recovery_stage_ids": actual_recovery_ids,
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
            and alternative_match
            and recovery_match
            and handoff_match
            and capability_score >= 1.0
        ),
    }


def evaluate_meta_replan_case(case: Dict[str, Any]) -> Dict[str, Any]:
    query = str(case.get("query", "") or "")
    decision = evaluate_query_orchestration(query)
    learning_snapshot = dict(case.get("learning_snapshot") or {"posture": "neutral"})
    runtime_constraints = dict(
        case.get("runtime_constraints")
        or {
            "budget_state": "pass",
            "stability_gate_state": "pass",
            "degrade_mode": "normal",
            "open_incidents": 0,
            "circuit_breakers_open": 0,
            "resource_guard_state": "inactive",
            "resource_guard_reason": "",
            "quarantined_incidents": 0,
            "cooldown_incidents": 0,
            "known_bad_patterns": 0,
            "release_blocked": False,
            "autonomy_hold": False,
        }
    )
    self_state = build_meta_self_state(decision, learning_snapshot, runtime_constraints)
    handoff = dict(decision)
    handoff["meta_self_state"] = self_state
    handoff["meta_learning_posture"] = learning_snapshot.get("posture")
    handoff["recipe_feedback_score"] = learning_snapshot.get("recipe_score")
    handoff["site_recipe_feedback_score"] = learning_snapshot.get("site_recipe_score")
    handoff["alternative_recipe_scores"] = list(case.get("alternative_recipe_scores") or [])

    initial = MetaAgent._select_initial_recipe_payload(handoff)
    failed_stage = dict(case.get("failed_stage") or {})
    replanned = None
    if failed_stage:
        replanned = MetaAgent._choose_alternative_recipe_payload(
            handoff,
            current_recipe_id=str(initial.get("recipe_id") or ""),
            failed_stage=failed_stage,
            attempted_recipe_ids={str(initial.get("recipe_id") or "")},
        )

    expected_initial = str(case.get("expected_initial_recipe") or "")
    expected_replan = str(case.get("expected_replan_recipe") or "")
    initial_match = (not expected_initial) or str(initial.get("recipe_id") or "") == expected_initial
    replan_match = (not expected_replan) or str((replanned or {}).get("recipe_id") or "") == expected_replan
    score = _score_ratio(int(initial_match) + int(replan_match), (1 if expected_initial else 0) + (1 if expected_replan else 0))
    return {
        "name": str(case.get("name", "") or ""),
        "decision": decision,
        "initial_recipe_id": str(initial.get("recipe_id") or ""),
        "replanned_recipe_id": str((replanned or {}).get("recipe_id") or ""),
        "initial_match": initial_match,
        "replan_match": replan_match,
        "score": score,
        "passed": initial_match and replan_match,
    }

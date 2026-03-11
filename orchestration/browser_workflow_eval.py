"""Canonical evaluation cases and benchmark scoring for meta -> visual browser workflows."""

from __future__ import annotations

from typing import Any, Dict, List

from orchestration.browser_workflow_plan import (
    ALLOWED_RECOVERY_TYPES,
    build_browser_workflow_plan,
    build_structured_browser_workflow_plan,
)
from orchestration.orchestration_policy import evaluate_query_orchestration


BROWSER_WORKFLOW_EVAL_CASES: List[Dict[str, Any]] = [
    {
        "name": "booking_search",
        "query": (
            "Starte den Browser, gehe auf booking.com, tippe Berlin, "
            "wähle 15. März bis 17. März und klicke auf Suchen"
        ),
        "task": "suche hotels in Berlin für 15.03.2026 bis 17.03.2026 2 personen",
        "url": "https://booking.com",
        "expected_route_to_meta": True,
        "required_markers": [
            "navigate: booking.com",
            "autocomplete_open",
            "datepicker_open",
            "results_loaded",
        ],
        "required_states": [
            "search_form",
            "autocomplete_open",
            "datepicker_open",
            "results_loaded",
        ],
    },
    {
        "name": "login_flow",
        "query": (
            "Öffne github.com/login, gib Benutzername und Passwort ein "
            "und klicke auf Sign in"
        ),
        "task": (
            "Öffne github.com/login, gib Benutzername und Passwort ein "
            "und klicke auf Sign in"
        ),
        "url": "https://github.com/login",
        "expected_route_to_meta": True,
        "required_markers": [
            "login_modal",
            "Benutzername oder E-Mail",
            "Passwort",
            "authenticated",
        ],
        "required_states": [
            "login_modal",
            "authenticated",
        ],
    },
    {
        "name": "contact_form",
        "query": (
            "Öffne das Kontaktformular auf example.com, trage Name, E-Mail "
            "und Nachricht ein und sende das Formular ab"
        ),
        "task": (
            "Öffne das Kontaktformular auf example.com, trage Name, E-Mail "
            "und Nachricht ein und sende das Formular ab"
        ),
        "url": "https://example.com/contact",
        "expected_route_to_meta": True,
        "required_markers": [
            "form_ready",
            "Namensfeld",
            "E-Mail-Feld",
            "Nachrichtenfeld",
            "form_submitted",
        ],
        "required_states": [
            "form_ready",
            "form_submitted",
        ],
    },
    {
        "name": "youtube_search",
        "query": "Öffne YouTube, suche nach KI News März 2026 und öffne das erste relevante Video",
        "task": "Suche nach KI News März 2026 auf YouTube und öffne das erste relevante Video",
        "url": "https://youtube.com",
        "expected_route_to_meta": True,
        "required_markers": [
            "navigate: youtube.com",
            "results_loaded",
            "video_page",
        ],
        "required_states": [
            "search_form",
            "results_loaded",
            "video_page",
        ],
    },
    {
        "name": "x_compose",
        "query": "Öffne x.com und schreibe Hallo aus Timus in einen neuen Beitrag",
        "task": "Öffne x.com und schreibe Hallo aus Timus in einen neuen Beitrag",
        "url": "https://x.com",
        "expected_route_to_meta": True,
        "required_markers": [
            "navigate: x.com",
            "timeline_ready",
            "compose_ready",
        ],
        "required_states": [
            "timeline_ready",
            "compose_ready",
        ],
    },
]


def _score_ratio(passed: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return round(max(0.0, min(1.0, passed / total)), 3)


def evaluate_browser_workflow_case(case: Dict[str, Any]) -> Dict[str, Any]:
    query = str(case.get("query", "") or "")
    task = str(case.get("task", "") or "")
    url = str(case.get("url", "") or "")
    required_markers = list(case.get("required_markers", []) or [])
    required_states = list(case.get("required_states", []) or [])
    route_decision = evaluate_query_orchestration(query)
    plan = build_browser_workflow_plan(task, url)
    structured_plan = build_structured_browser_workflow_plan(task, url)
    matched_markers = [
        marker
        for marker in required_markers
        if any(marker in step for step in plan)
    ]
    plan_states = [step.expected_state for step in structured_plan.steps]
    matched_states = [state for state in required_states if state in plan_states]
    evidence_steps = sum(1 for step in structured_plan.steps if step.success_signal)
    verification_steps = sum(1 for step in structured_plan.steps if step.action == "verify_state")
    recovery_steps = sum(
        1
        for step in structured_plan.steps
        if step.fallback_strategy in ALLOWED_RECOVERY_TYPES
        and step.fallback_strategy != "abort_with_handoff"
    )
    distinct_recoveries = sorted({step.fallback_strategy for step in structured_plan.steps})
    route_match = bool(route_decision.get("route_to_meta", False)) == bool(
        case.get("expected_route_to_meta", False)
    )
    marker_score = _score_ratio(len(matched_markers), len(required_markers))
    state_score = _score_ratio(len(matched_states), len(required_states))
    evidence_score = _score_ratio(evidence_steps, len(structured_plan.steps))
    verification_score = 1.0 if verification_steps >= 1 else 0.0
    recovery_score = 1.0 if recovery_steps >= 1 and len(distinct_recoveries) >= 2 else 0.0
    total_checks = len(required_markers) + len(required_states) + 4
    passed_checks = (
        len(matched_markers)
        + len(matched_states)
        + (1 if route_match else 0)
        + (1 if evidence_steps == len(structured_plan.steps) else 0)
        + (1 if verification_steps >= 1 else 0)
        + (1 if recovery_steps >= 1 and len(distinct_recoveries) >= 2 else 0)
    )
    score = round(passed_checks / total_checks, 3) if total_checks else 1.0
    return {
        "name": case.get("name", ""),
        "route_to_meta": bool(route_decision.get("route_to_meta", False)),
        "expected_route_to_meta": bool(case.get("expected_route_to_meta", False)),
        "route_match": route_match,
        "plan": plan,
        "structured_plan": structured_plan,
        "matched_markers": matched_markers,
        "missing_markers": [marker for marker in required_markers if marker not in matched_markers],
        "matched_states": matched_states,
        "missing_states": [state for state in required_states if state not in matched_states],
        "benchmark": {
            "marker_score": marker_score,
            "state_score": state_score,
            "evidence_score": evidence_score,
            "verification_score": verification_score,
            "recovery_score": recovery_score,
            "step_count": len(structured_plan.steps),
            "verification_steps": verification_steps,
            "distinct_recoveries": distinct_recoveries,
        },
        "score": score,
        "passed": (
            route_match
            and len(matched_markers) == len(required_markers)
            and len(matched_states) == len(required_states)
            and evidence_steps == len(structured_plan.steps)
            and verification_steps >= 1
            and recovery_steps >= 1
            and len(distinct_recoveries) >= 2
        ),
    }

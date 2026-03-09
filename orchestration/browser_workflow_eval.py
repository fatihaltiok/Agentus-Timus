"""Canonical evaluation cases for meta -> visual browser workflows."""

from __future__ import annotations

from typing import Any, Dict, List

from orchestration.browser_workflow_plan import build_browser_workflow_plan
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
            "Navigiere zu booking.com",
            "Autocomplete",
            "Datepicker",
            "Verifiziere, dass beide Daten",
            "Verifiziere, dass Suchergebnisse",
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
            "Login-Maske",
            "Benutzername oder E-Mail",
            "Passwort-Feld",
            "Login-/Sign-in-Button",
            "Verifiziere, dass ein eingeloggter Zustand",
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
            "Pflichtfelder sichtbar",
            "Namensfeld",
            "E-Mail-Feld",
            "Nachrichten- oder Textfeld",
            "Bestätigung, Success-Meldung oder Fehlermeldung",
        ],
    },
]


def evaluate_browser_workflow_case(case: Dict[str, Any]) -> Dict[str, Any]:
    query = str(case.get("query", "") or "")
    task = str(case.get("task", "") or "")
    url = str(case.get("url", "") or "")
    required_markers = list(case.get("required_markers", []) or [])
    route_decision = evaluate_query_orchestration(query)
    plan = build_browser_workflow_plan(task, url)
    matched_markers = [
        marker
        for marker in required_markers
        if any(marker in step for step in plan)
    ]
    route_match = bool(route_decision.get("route_to_meta", False)) == bool(
        case.get("expected_route_to_meta", False)
    )
    total_checks = len(required_markers) + 1
    passed_checks = len(matched_markers) + (1 if route_match else 0)
    score = round(passed_checks / total_checks, 3) if total_checks else 1.0
    return {
        "name": case.get("name", ""),
        "route_to_meta": bool(route_decision.get("route_to_meta", False)),
        "expected_route_to_meta": bool(case.get("expected_route_to_meta", False)),
        "route_match": route_match,
        "plan": plan,
        "matched_markers": matched_markers,
        "missing_markers": [marker for marker in required_markers if marker not in matched_markers],
        "score": score,
        "passed": route_match and len(matched_markers) == len(required_markers),
    }

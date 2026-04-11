from __future__ import annotations

from orchestration.browser_workflow_plan import (
    ALLOWED_EVIDENCE_TYPES,
    ALLOWED_RECOVERY_TYPES,
    build_browser_workflow_plan,
    build_structured_browser_workflow_plan,
)


def test_build_browser_workflow_plan_for_booking_contains_verification_steps():
    steps = build_browser_workflow_plan(
        "suche hotels in Berlin für 15.03.2026 bis 17.03.2026 2 personen",
        "https://booking.com",
    )

    assert steps[0].startswith("navigate: booking.com")
    assert any("autocomplete_open" in step for step in steps)
    assert any("datepicker_open" in step for step in steps)
    assert any("results_loaded" in step for step in steps)
    assert steps[-1] == "Beende Task und berichte Ergebnisse"


def test_build_browser_workflow_plan_fallback_still_enforces_verification():
    steps = build_browser_workflow_plan(
        "öffne example.com und finde die Preise",
        "https://example.com",
    )

    assert any("verify_state" in step for step in steps)
    assert steps[-1] == "Beende Task und berichte Ergebnisse"


def test_build_structured_browser_workflow_plan_for_booking_has_evidence_and_recovery():
    plan = build_structured_browser_workflow_plan(
        "suche hotels in Berlin für 15.03.2026 bis 17.03.2026 2 personen",
        "https://booking.com",
    )

    assert plan.flow_type == "booking_search"
    assert plan.initial_state == "landing"
    assert any(step.expected_state == "autocomplete_open" for step in plan.steps)
    assert any(step.expected_state == "datepicker_open" for step in plan.steps)
    assert any(step.expected_state == "results_loaded" for step in plan.steps)
    assert all(step.success_signal for step in plan.steps)
    assert all(
        evidence.evidence_type in ALLOWED_EVIDENCE_TYPES
        for step in plan.steps
        for evidence in step.success_signal
    )
    assert all(step.fallback_strategy in ALLOWED_RECOVERY_TYPES for step in plan.steps)


def test_build_structured_browser_workflow_plan_for_login_and_form_use_reference_flows():
    login_plan = build_structured_browser_workflow_plan(
        "Öffne github.com/login, gib Benutzername und Passwort ein und klicke auf Sign in",
        "https://github.com/login",
    )
    form_plan = build_structured_browser_workflow_plan(
        "Öffne das Kontaktformular auf example.com, trage Name, E-Mail und Nachricht ein und sende das Formular ab",
        "https://example.com/contact",
    )

    assert login_plan.flow_type == "login_flow"
    assert any(step.expected_state == "login_modal" for step in login_plan.steps)
    assert any(step.expected_state == "authenticated" for step in login_plan.steps)
    assert form_plan.flow_type == "simple_form"
    assert any(step.expected_state == "form_ready" for step in form_plan.steps)
    assert any(step.expected_state == "form_submitted" for step in form_plan.steps)


def test_build_structured_browser_workflow_plan_recognizes_natural_login_prompt_and_normalizes_login_url():
    login_plan = build_structured_browser_workflow_plan(
        "Bitte melde mich in Chrome bei GitHub an und nutze den Passwortmanager.",
        "https://github.com",
    )

    assert login_plan.flow_type == "login_flow"
    assert login_plan.steps[0].action == "navigate"
    assert login_plan.steps[0].target_text == "https://github.com/login"
    assert any(step.expected_state == "login_modal" for step in login_plan.steps)


def test_build_structured_browser_workflow_plan_for_youtube_and_x_use_site_profiles():
    youtube_plan = build_structured_browser_workflow_plan(
        "Suche nach KI News März 2026 auf YouTube und öffne das erste relevante Video",
        "https://youtube.com",
    )
    x_plan = build_structured_browser_workflow_plan(
        "Öffne x.com und schreibe Hallo aus Timus in einen neuen Beitrag",
        "https://x.com",
    )

    assert youtube_plan.flow_type == "youtube_search"
    assert any(step.expected_state == "results_loaded" for step in youtube_plan.steps)
    assert any(step.expected_state == "video_page" for step in youtube_plan.steps)
    assert x_plan.flow_type == "x_compose"
    assert any(step.expected_state == "timeline_ready" for step in x_plan.steps)
    assert any(step.expected_state == "compose_ready" for step in x_plan.steps)

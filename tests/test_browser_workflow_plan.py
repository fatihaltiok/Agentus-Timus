from __future__ import annotations

from orchestration.browser_workflow_plan import build_browser_workflow_plan


def test_build_browser_workflow_plan_for_booking_contains_verification_steps():
    steps = build_browser_workflow_plan(
        "suche hotels in Berlin für 15.03.2026 bis 17.03.2026 2 personen",
        "https://booking.com",
    )

    assert steps[0] == "Navigiere zu booking.com"
    assert any("Verifiziere, dass die Zielseite geladen ist" in step for step in steps)
    assert any("Autocomplete-Vorschlag" in step for step in steps)
    assert any("Öffne den Datepicker" in step for step in steps)
    assert any("Verifiziere, dass beide Daten" in step for step in steps)
    assert any("Verifiziere, dass Suchergebnisse" in step for step in steps)
    assert steps[-1] == "Beende Task und berichte Ergebnisse"


def test_build_browser_workflow_plan_fallback_still_enforces_verification():
    steps = build_browser_workflow_plan(
        "öffne example.com und finde die Preise",
        "https://example.com",
    )

    assert any("Verifiziere" in step for step in steps)
    assert steps[-1] == "Beende Task und berichte Ergebnisse"

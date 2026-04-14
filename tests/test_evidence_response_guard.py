from __future__ import annotations

from orchestration.evidence_response_guard import (
    build_evidence_response_guard,
    looks_like_tabular_data_task,
    should_add_evidence_response_guard,
)


def test_evidence_response_guard_triggers_for_career_followup() -> None:
    query = "AI Training Data und Annotation erklaere mir wie ich damit anfangen kann"

    assert should_add_evidence_response_guard(query) is True
    assert "# EVIDENZ-ANTWORT-GUARD" in build_evidence_response_guard(query)


def test_evidence_response_guard_does_not_trigger_for_csv_analysis() -> None:
    query = "Analysiere die CSV /tmp/umsatz.csv und berechne den Mittelwert"

    assert looks_like_tabular_data_task(query) is True
    assert should_add_evidence_response_guard(query) is False
    assert build_evidence_response_guard(query) == ""

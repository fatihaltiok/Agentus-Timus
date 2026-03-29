from __future__ import annotations

from pathlib import Path

from agent.agents.meta import MetaAgent


def test_meta_developer_handoff_includes_verified_diagnosis_data(tmp_path: Path) -> None:
    verified_file = tmp_path / "location_registry.py"
    verified_file.write_text("def select_active_location_snapshot():\n    return None\n", encoding="utf-8")

    payload = MetaAgent._build_specialist_handoff_payload(
        "developer",
        "implement_feature",
        {
            "diagnosis_records": [
                {
                    "source_agent": "system",
                    "claim": "User-reported invalidation fehlt im Location-State.",
                    "evidence_level": "verified",
                    "confidence": 0.95,
                    "actionability": 0.9,
                    "verified_paths": [str(verified_file)],
                    "verified_functions": ["select_active_location_snapshot"],
                    "evidence_refs": ["utils/location_registry.py:190"],
                },
                {
                    "source_agent": "meta",
                    "claim": "Parser neu bauen.",
                    "evidence_level": "unverified",
                    "confidence": 0.2,
                    "actionability": 0.3,
                },
            ],
        },
        "Implementiere die Korrektur.",
    )

    handoff_data = dict(payload["handoff_data"])
    assert "primary_fix_json" in handoff_data
    assert handoff_data["verified_paths_json"] == [str(verified_file.resolve())]
    assert handoff_data["verified_functions_json"] == ["select_active_location_snapshot"]
    assert handoff_data["suppressed_claims_count"] == 1
    assert "nur_verifizierte_dateien_und_funktionen_verwenden" in payload["constraints"]
    assert payload["goal"] == "User-reported invalidation fehlt im Location-State."


def test_meta_developer_handoff_records_diagnosis_observation(monkeypatch, tmp_path: Path) -> None:
    verified_file = tmp_path / "mcp_server.py"
    verified_file.write_text("def _persist_location_snapshot():\n    return None\n", encoding="utf-8")
    observed: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        "agent.agents.meta.record_autonomy_observation",
        lambda event_type, payload: observed.append((event_type, dict(payload))),
    )

    rendered = MetaAgent._render_structured_delegation_task(
        "developer",
        "implement_feature",
        {
            "diagnosis_records": [
                {
                    "source_agent": "system",
                    "claim": "Location-State muss user-reported invalidation beachten.",
                    "evidence_level": "verified",
                    "confidence": 0.9,
                    "actionability": 1.0,
                    "verified_paths": [str(verified_file)],
                    "verified_functions": ["_persist_location_snapshot"],
                },
                {
                    "source_agent": "reasoning",
                    "claim": "Fuege Monitoring fuer frische Revalidierung vor Route-Antwort hinzu.",
                    "evidence_level": "observed",
                    "confidence": 0.75,
                    "actionability": 0.85,
                },
            ],
        },
        "Baue den Fix sauber ein.",
    )

    assert "primary_fix_json" in rendered
    event_types = [item[0] for item in observed]
    assert "lead_diagnosis_selected" in event_types
    assert "diagnosis_conflict_detected" in event_types
    assert "developer_task_compiled" in event_types
    assert "primary_fix_task_emitted" in event_types
    assert "followup_task_deferred" in event_types


def test_meta_developer_handoff_blocks_fix_without_root_cause_gate(monkeypatch) -> None:
    observed: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        "agent.agents.meta.record_autonomy_observation",
        lambda event_type, payload: observed.append((event_type, dict(payload))),
    )

    payload = MetaAgent._build_specialist_handoff_payload(
        "developer",
        "implement_feature",
        {
            "diagnosis_records": [
                {
                    "source_agent": "meta",
                    "claim": "Fuege Alerting fuer kuenftige Vorfaelle hinzu.",
                    "evidence_level": "hypothesis",
                    "confidence": 0.3,
                    "actionability": 0.5,
                }
            ],
        },
        "Baue den Vorfall aus.",
    )

    handoff_data = dict(payload["handoff_data"])
    assert handoff_data["root_cause_gate_json"]["state"] == "verification_needed"
    assert "verification_needed_json" in handoff_data
    assert "primary_fix_json" not in handoff_data
    assert payload["goal"].startswith("Verifiziere zuerst die primaere Ursache")
    rendered = MetaAgent._render_structured_delegation_task(
        "developer",
        "implement_feature",
        {
            "diagnosis_records": [
                {
                    "source_agent": "meta",
                    "claim": "Fuege Alerting fuer kuenftige Vorfaelle hinzu.",
                    "evidence_level": "hypothesis",
                    "confidence": 0.3,
                    "actionability": 0.5,
                }
            ],
        },
        "Baue den Vorfall aus.",
    )
    assert "verification_needed_json" in rendered
    event_types = [item[0] for item in observed]
    assert "root_cause_gate_blocked" in event_types

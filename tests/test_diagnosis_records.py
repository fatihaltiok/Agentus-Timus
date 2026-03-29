from __future__ import annotations

from pathlib import Path

from orchestration.diagnosis_records import (
    build_diagnosis_records,
    compile_developer_task_brief,
    select_lead_diagnosis,
)
from orchestration.meta_orchestration import (
    build_meta_diagnosis_resolution,
    compile_meta_developer_task_payload,
)


def test_build_meta_diagnosis_resolution_prefers_verified_runtime_evidence(tmp_path: Path) -> None:
    verified_file = tmp_path / "location_registry.py"
    verified_file.write_text("def select_active_location_snapshot():\n    return None\n", encoding="utf-8")

    resolution = build_meta_diagnosis_resolution(
        [
            {
                "source_agent": "meta",
                "claim": "Snapshot-Pfad fehlt.",
                "evidence_level": "hypothesis",
                "confidence": 0.3,
                "actionability": 0.4,
                "verified_paths": ["/does/not/exist.py"],
            },
            {
                "source_agent": "system",
                "claim": "Freshness-Klassifikation beruecksichtigt kein user-reported state update.",
                "evidence_level": "verified",
                "confidence": 0.95,
                "actionability": 0.9,
                "verified_paths": [str(verified_file)],
                "verified_functions": ["select_active_location_snapshot"],
                "evidence_refs": ["utils/location_registry.py:190"],
            },
        ],
        existing_paths=[str(verified_file)],
    )

    lead = dict(resolution["lead_diagnosis"] or {})
    assert lead["source_agent"] == "system"
    assert lead["verified_paths"] == [str(verified_file.resolve())]
    assert resolution["suppressed_claims"] == ["Snapshot-Pfad fehlt."]


def test_compile_meta_developer_task_payload_keeps_only_verified_paths(tmp_path: Path) -> None:
    verified_file = tmp_path / "mcp_server.py"
    verified_file.write_text("def _persist_location_snapshot():\n    return None\n", encoding="utf-8")

    compiled = compile_meta_developer_task_payload(
        [
            {
                "source_agent": "system",
                "claim": "User-reported invalidation fehlt.",
                "evidence_level": "verified",
                "confidence": 0.9,
                "actionability": 1.0,
                "verified_paths": [str(verified_file), "/not/real/path.py"],
                "verified_functions": ["_persist_location_snapshot"],
                "evidence_refs": ["server/mcp_server.py:1351"],
            },
            {
                "source_agent": "meta",
                "claim": "Parser eventuell neu bauen.",
                "evidence_level": "unverified",
                "confidence": 0.2,
                "actionability": 0.4,
            },
        ],
        existing_paths=[str(verified_file)],
    )

    brief = dict(compiled["developer_task_brief"])
    assert brief["lead_diagnosis"] == "User-reported invalidation fehlt."
    assert brief["verified_paths"] == [str(verified_file.resolve())]
    assert brief["verified_functions"] == ["_persist_location_snapshot"]
    assert brief["suppressed_claims"] == ["Parser eventuell neu bauen."]


def test_compile_developer_task_brief_marks_conflict_when_multiple_supported_sources(tmp_path: Path) -> None:
    verified_file = tmp_path / "location_presence.py"
    verified_file.write_text("def classify_location_freshness():\n    return {}\n", encoding="utf-8")
    records = build_diagnosis_records(
        [
            {
                "source_agent": "system",
                "claim": "Freshness ist timestamp-only.",
                "evidence_level": "verified",
                "confidence": 0.95,
                "actionability": 0.8,
                "verified_paths": [str(verified_file)],
            },
            {
                "source_agent": "reasoning",
                "claim": "User-reported invalidation fehlt.",
                "evidence_level": "observed",
                "confidence": 0.8,
                "actionability": 0.9,
            },
        ],
        existing_paths=[str(verified_file)],
    )

    resolution = select_lead_diagnosis(records)
    brief = compile_developer_task_brief(resolution)

    assert resolution.conflict_detected is True
    assert brief.conflict_detected is True
    assert brief.supporting_diagnoses == ("User-reported invalidation fehlt.",)

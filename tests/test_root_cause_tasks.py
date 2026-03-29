from __future__ import annotations

from pathlib import Path

from orchestration.diagnosis_records import build_diagnosis_records, select_lead_diagnosis
from orchestration.meta_orchestration import compile_meta_developer_task_payload
from orchestration.root_cause_tasks import build_root_cause_task_payload, classify_change_focus


def test_classify_change_focus_splits_root_cause_from_monitoring() -> None:
    focus = classify_change_focus(
        "Behebe den Type-Error bei moondream_answer und fuege danach Logging/Alerting hinzu."
    )

    assert focus["primary_change_type"] == "type_normalization"
    assert "monitoring" in focus["followup_change_types"]


def test_build_root_cause_task_payload_emits_primary_fix_and_defers_followup(tmp_path: Path) -> None:
    verified_file = tmp_path / "tool.py"
    verified_file.write_text("def analyze_screen_verified():\n    return {}\n", encoding="utf-8")
    records = build_diagnosis_records(
        [
            {
                "source_agent": "system",
                "claim": "Normalisiere moondream_answer defensiv, damit strip() nie auf dict aufgerufen wird.",
                "evidence_level": "verified",
                "confidence": 0.95,
                "actionability": 0.95,
                "verified_paths": [str(verified_file)],
                "verified_functions": ["analyze_screen_verified"],
            },
            {
                "source_agent": "reasoning",
                "claim": "Fuege zusaetzliches Monitoring fuer wiederkehrende Vision-Fehler hinzu.",
                "evidence_level": "observed",
                "confidence": 0.7,
                "actionability": 0.7,
            },
        ],
        existing_paths=[str(verified_file)],
    )

    payload = build_root_cause_task_payload(select_lead_diagnosis(records))

    assert payload.state == "primary_fix_emitted"
    assert payload.primary_fix is not None
    assert payload.primary_fix.change_type == "type_normalization"
    assert payload.followup_tasks
    assert payload.followup_tasks[0].task_kind == "followup_monitoring"


def test_build_root_cause_task_payload_blocks_without_verified_path() -> None:
    records = build_diagnosis_records(
        [
            {
                "source_agent": "system",
                "claim": "Normalisiere moondream_answer defensiv, damit strip() nie auf dict aufgerufen wird.",
                "evidence_level": "verified",
                "confidence": 0.95,
                "actionability": 0.95,
            }
        ],
        existing_paths=[],
    )

    payload = build_root_cause_task_payload(select_lead_diagnosis(records))

    assert payload.state == "verification_needed"
    assert payload.gate_reason == "missing_verified_paths"
    assert payload.primary_fix is None


def test_compile_meta_developer_task_payload_includes_root_cause_split(tmp_path: Path) -> None:
    verified_file = tmp_path / "vision_tool.py"
    verified_file.write_text("def analyze_screen_verified():\n    return {}\n", encoding="utf-8")

    compiled = compile_meta_developer_task_payload(
        [
            {
                "source_agent": "system",
                "claim": "Normalisiere moondream_answer defensiv, damit strip() nie auf dict aufgerufen wird.",
                "evidence_level": "verified",
                "confidence": 0.95,
                "actionability": 0.95,
                "verified_paths": [str(verified_file)],
                "verified_functions": ["analyze_screen_verified"],
            },
            {
                "source_agent": "meta",
                "claim": "Fuege Monitoring fuer Folgeloops hinzu.",
                "evidence_level": "observed",
                "confidence": 0.6,
                "actionability": 0.6,
            },
        ],
        existing_paths=[str(verified_file)],
    )

    root_cause = dict(compiled["root_cause_tasks"])
    assert root_cause["state"] == "primary_fix_emitted"
    assert root_cause["primary_fix"]["task_kind"] == "primary_fix"
    assert root_cause["followup_tasks"][0]["task_kind"] == "followup_monitoring"

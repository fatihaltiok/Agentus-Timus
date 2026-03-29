from __future__ import annotations

import deal

from orchestration.diagnosis_records import (
    build_diagnosis_records,
    compile_developer_task_brief,
    normalize_evidence_level,
    select_lead_diagnosis,
)


@deal.post(lambda r: r in {"verified", "corroborated", "observed", "hypothesis", "unverified"})
def _contract_normalize_evidence_level_crosshair(raw: str) -> str:
    return normalize_evidence_level(raw)


@deal.post(lambda r: 0 <= r <= 4)
def _contract_supporting_count_crosshair(level_a: str, level_b: str) -> int:
    records = build_diagnosis_records(
        [
            {
                "source_agent": "system",
                "claim": "lead",
                "evidence_level": level_a,
                "confidence": 0.9,
                "actionability": 0.9,
            },
            {
                "source_agent": "meta",
                "claim": "other",
                "evidence_level": level_b,
                "confidence": 0.4,
                "actionability": 0.4,
            },
        ],
        existing_paths=[],
    )
    resolution = select_lead_diagnosis(records)
    return len(resolution.supporting_diagnoses)


@deal.post(lambda r: 0 <= r <= 8)
def _contract_suppressed_count_crosshair(level_a: str, level_b: str) -> int:
    records = build_diagnosis_records(
        [
            {
                "source_agent": "system",
                "claim": "lead",
                "evidence_level": level_a,
                "confidence": 0.9,
                "actionability": 0.9,
            },
            {
                "source_agent": "meta",
                "claim": "other",
                "evidence_level": level_b,
                "confidence": 0.1,
                "actionability": 0.1,
            },
        ],
        existing_paths=[],
    )
    resolution = select_lead_diagnosis(records)
    brief = compile_developer_task_brief(resolution)
    return len(brief.suppressed_claims)

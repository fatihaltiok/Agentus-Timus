from __future__ import annotations

import deal

from orchestration.diagnosis_records import build_diagnosis_records, select_lead_diagnosis
from orchestration.root_cause_tasks import build_root_cause_task_payload, classify_change_focus


@deal.post(lambda r: 0 <= r <= 3)
def _contract_change_focus_crosshair(text: str) -> int:
    return len(classify_change_focus(text)["followup_change_types"])


@deal.post(lambda r: r in {0, 1})
def _contract_primary_fix_presence_crosshair(with_path: bool) -> int:
    records = build_diagnosis_records(
        [
            {
                "source_agent": "system",
                "claim": "Normalisiere dict/string Antwort defensiv",
                "evidence_level": "verified",
                "confidence": 0.9,
                "actionability": 0.9,
                "verified_paths": ["/tmp/root_fix.py"] if with_path else [],
            }
        ],
        existing_paths=["/tmp/root_fix.py"] if with_path else [],
    )
    payload = build_root_cause_task_payload(select_lead_diagnosis(records))
    return 1 if payload.primary_fix is not None else 0

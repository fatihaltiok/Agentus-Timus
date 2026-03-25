from __future__ import annotations

import sys
from pathlib import Path

import deal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.tool import _normalize_conflict_scan_payload


@deal.post(lambda r: r is True)
def _contract_conflict_scan_payload_tolerates_null_lists() -> bool:
    normalized = _normalize_conflict_scan_payload(
        {
            "conflicts": None,
            "open_questions": None,
            "weak_evidence_flags": None,
            "report_notes": None,
        }
    )
    return (
        normalized["conflicts"] == []
        and normalized["open_questions"] == []
        and normalized["weak_evidence_flags"] == []
        and normalized["report_notes"] == []
    )


@deal.post(lambda r: r is True)
def _contract_conflict_scan_payload_applies_caps() -> bool:
    normalized = _normalize_conflict_scan_payload(
        {
            "conflicts": [
                {
                    "claim_text": f"Claim {idx}",
                    "issue_type": "scope_gap",
                    "reason": "note",
                    "confidence": 0.95,
                }
                for idx in range(12)
            ],
            "open_questions": [f"Question {idx}" for idx in range(12)],
            "weak_evidence_flags": [
                {
                    "claim_text": f"Weak {idx}",
                    "reason": "note",
                    "confidence": 0.95,
                }
                for idx in range(12)
            ],
            "report_notes": [f"Note {idx}" for idx in range(12)],
        }
    )
    return (
        len(normalized["conflicts"]) <= 6
        and len(normalized["open_questions"]) <= 8
        and len(normalized["weak_evidence_flags"]) <= 6
        and len(normalized["report_notes"]) <= 6
    )


def test_contract_conflict_scan_payload_tolerates_null_lists():
    assert _contract_conflict_scan_payload_tolerates_null_lists() is True


def test_contract_conflict_scan_payload_applies_caps():
    assert _contract_conflict_scan_payload_applies_caps() is True

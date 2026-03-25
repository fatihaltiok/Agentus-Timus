from __future__ import annotations

import pytest


def test_build_conflict_scan_input_caps_claims_conflicts_and_unknowns():
    from tools.deep_research.research_contracts import ClaimRecord, ClaimVerdict
    from tools.deep_research.tool import DeepResearchSession, _build_conflict_scan_input

    session = DeepResearchSession("Robot X industrial assembly AI deployment")
    session.contract_v2.claims = [
        ClaimRecord(
            claim_id=f"c{i}",
            question_id=session.contract_v2.question.question_id,
            domain="robotics",
            subject="robot",
            claim_text=f"Robot X industrial assembly AI deployment claim {i}",
            claim_type="verified_fact",
            verdict=ClaimVerdict.LIKELY,
            supports=["s1", "s2"][: 1 + (i % 2)],
            unknowns=[f"Unknown {i}"],
        )
        for i in range(20)
    ]
    session.conflicting_info = [
        {
            "fact": f"Robot X industrial assembly conflict fact {i}",
            "note": f"Note {i}",
            "internal_confidence": 0.8,
            "corroborator_confidence": 0.4,
        }
        for i in range(12)
    ]
    session.limitations = [f"Open question {i}" for i in range(10)]

    payload = _build_conflict_scan_input(session)

    assert len(payload["claims"]) == 15
    assert len(payload["conflicting_info"]) == 8
    assert len(payload["open_questions"]) == 6


@pytest.mark.asyncio
async def test_conflict_scan_skips_when_no_material(monkeypatch):
    from tools.deep_research.tool import DeepResearchSession, _populate_conflict_scan_cache

    monkeypatch.setenv("DR_WORKER_CONFLICT_SCAN_ENABLED", "true")

    async def _must_not_run(*args, **kwargs):
        raise AssertionError("worker must not be called")

    monkeypatch.setattr("tools.deep_research.tool.run_worker", _must_not_run)

    session = DeepResearchSession("Robot X industrial assembly AI deployment")
    await _populate_conflict_scan_cache(session, session_id="research_test_session")

    meta = session.research_metadata["conflict_scan_worker"]
    assert meta["status"] == "skipped_no_material"
    assert meta["fallback_used"] is False


def test_conflict_scan_normalizer_tolerates_null_lists():
    from tools.deep_research.tool import _normalize_conflict_scan_payload

    normalized = _normalize_conflict_scan_payload(
        {
            "conflicts": None,
            "open_questions": None,
            "weak_evidence_flags": None,
            "report_notes": None,
        }
    )

    assert normalized["conflicts"] == []
    assert normalized["open_questions"] == []
    assert normalized["weak_evidence_flags"] == []
    assert normalized["report_notes"] == []


@pytest.mark.asyncio
async def test_conflict_scan_does_not_mutate_claim_or_evidence_counts(monkeypatch):
    from orchestration.ephemeral_workers import WorkerResult
    from tools.deep_research.research_contracts import (
        ClaimRecord,
        ClaimVerdict,
        EvidenceRecord,
        EvidenceStance,
        SourceRecord,
        SourceTier,
        SourceType,
    )
    from tools.deep_research.tool import DeepResearchSession, ResearchNode, _populate_conflict_scan_cache

    monkeypatch.setenv("DR_WORKER_CONFLICT_SCAN_ENABLED", "true")

    async def _fake_run_worker(*args, **kwargs):
        return WorkerResult(
            worker_type="conflict_scan",
            status="ok",
            payload={
                "conflicts": [
                    {
                        "claim_text": "Robot X industrial assembly uses AI deployment logic.",
                        "issue_type": "scope_gap",
                        "reason": "Evidence is limited to one production line.",
                        "confidence": 0.9,
                    }
                ],
                "open_questions": ["How transferable is the deployment to other factories?"],
                "weak_evidence_flags": [],
                "report_notes": ["Keep uncertainty explicit in the report."],
            },
            provider="openai",
            model="gpt-5.4-mini",
            duration_ms=7,
            max_tokens=1200,
        )

    monkeypatch.setattr("tools.deep_research.tool.run_worker", _fake_run_worker)

    session = DeepResearchSession("Robot X industrial assembly AI deployment")
    session.research_tree = [
        ResearchNode(
            url="https://example.com/robot-x",
            title="Robot X",
            content_snippet="assembly",
        )
    ]
    session.contract_v2.sources = [
        SourceRecord("s1", "https://example.com/robot-x", "Robot X", SourceType.ANALYSIS, SourceTier.B, has_methodology=True),
    ]
    session.contract_v2.claims = [
        ClaimRecord(
            claim_id="c1",
            question_id=session.contract_v2.question.question_id,
            domain="robotics",
            subject="robot",
            claim_text="Robot X industrial assembly uses AI deployment logic.",
            claim_type="verified_fact",
            verdict=ClaimVerdict.LIKELY,
            confidence=0.7,
            supports=["s1"],
        )
    ]
    session.contract_v2.evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS),
    ]

    before = session.export_contract_v2()
    before_claims = len(before["claims"])
    before_evidences = len(before["evidences"])

    await _populate_conflict_scan_cache(session, session_id="research_test_session")
    after = session.export_contract_v2()

    assert len(after["claims"]) == before_claims
    assert len(after["evidences"]) == before_evidences
    assert session.research_metadata["conflict_scan_worker"]["conflicts"]


def test_academic_report_includes_conflict_scan_hints():
    from tools.deep_research.research_contracts import (
        ClaimRecord,
        ClaimVerdict,
        EvidenceRecord,
        EvidenceStance,
        SourceRecord,
        SourceTier,
        SourceType,
    )
    from tools.deep_research.tool import DeepResearchSession, _create_academic_markdown_report

    session = DeepResearchSession("Robot X industrial assembly AI deployment")
    session.visited_urls = {"https://example.com/a"}
    session.contract_v2.sources = [
        SourceRecord("s1", "https://example.com/a", "A", SourceType.ANALYSIS, SourceTier.B, has_methodology=True),
    ]
    session.contract_v2.claims = [
        ClaimRecord(
            claim_id="c1",
            question_id=session.contract_v2.question.question_id,
            domain="robotics",
            subject="robot",
            claim_text="Robot X industrial assembly uses AI deployment logic.",
            claim_type="verified_fact",
            verdict=ClaimVerdict.LIKELY,
            confidence=0.7,
            supports=["s1"],
        )
    ]
    session.contract_v2.evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS),
    ]
    session.research_metadata["conflict_scan_worker"] = {
        "status": "ok",
        "conflicts": [
            {
                "claim_text": "Robot X industrial assembly uses AI deployment logic.",
                "issue_type": "scope_gap",
                "reason": "Evidence is limited to one production line.",
                "confidence": 0.9,
            }
        ],
        "open_questions": ["How transferable is the deployment to other factories?"],
        "weak_evidence_flags": [],
        "report_notes": ["Keep uncertainty explicit in the report."],
    }

    report = _create_academic_markdown_report(session)

    assert "Conflict-Scan-Hinweise" in report
    assert "scope_gap" in report
    assert "Keep uncertainty explicit in the report." in report

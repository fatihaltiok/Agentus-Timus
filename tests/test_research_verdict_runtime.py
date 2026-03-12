from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_materialize_verification_claims_marks_conflicts_as_contested():
    from tools.deep_research.research_contracts import ClaimVerdict
    from tools.deep_research.tool import DeepResearchSession

    session = DeepResearchSession("Pruefe Modellfaehigkeiten")
    grouped = [[
        {
            "fact": "Modell X ist stark in Coding.",
            "source_url": "https://example.com/a",
            "source_title": "Benchmark A",
            "source_type": "analysis",
            "source_quote": "Model X performs well.",
        }
    ]]
    verified = [
        {
            "fact": "Modell X ist stark in Coding.",
            "status": "verified",
            "confidence_score_numeric": 0.8,
        }
    ]
    conflicts = [
        {
            "fact": "Modell X ist stark in Coding.",
            "note": "Conflicting confidence levels between verification methods",
        }
    ]

    session._materialize_verification_claims_v2(grouped, verified, [], conflicts)

    assert len(session.contract_v2.claims) == 1
    assert session.contract_v2.claims[0].verdict == ClaimVerdict.CONTESTED
    assert any(evidence.stance.value == "contradicts" for evidence in session.contract_v2.evidences)


@pytest.mark.asyncio
async def test_deep_verify_facts_populates_contract_v2_runtime_claims(monkeypatch):
    from tools.deep_research.tool import DeepResearchSession, _deep_verify_facts

    async def fake_group(raw_facts, query):
        assert query == "Teste Research Runtime"
        return [raw_facts]

    async def fake_corroborator(fact_text, query):
        assert fact_text == "Qwen ist stark in Coding."
        assert query == "Teste Research Runtime"
        return None

    monkeypatch.setattr("tools.deep_research.tool._group_similar_facts", fake_group)
    monkeypatch.setattr("tools.deep_research.tool._verify_fact_with_corroborator", fake_corroborator)

    session = DeepResearchSession("Teste Research Runtime")
    session.all_extracted_facts_raw = [
        {
            "fact": "Qwen ist stark in Coding.",
            "source_url": "https://example.com/a",
            "source_title": "Benchmark A",
            "source_type": "analysis",
            "source_quote": "Strong coding results",
        },
        {
            "fact": "Qwen ist stark in Coding.",
            "source_url": "https://example.com/b",
            "source_title": "Benchmark B",
            "source_type": "analysis",
            "source_quote": "Independent confirmation",
        },
    ]

    result = await _deep_verify_facts(session, "moderate")

    assert result["verified_facts"]
    assert session.contract_v2.claims
    assert session.contract_v2.evidences
    assert session.contract_v2.claims[0].claim_type == "runtime_fact_group"


def test_academic_report_uses_claim_language_instead_of_blanket_multisource_verification():
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

    session = DeepResearchSession("Vergleiche Frontier-Modelle")
    session.visited_urls = {"https://example.com/a", "https://example.com/b"}
    session.all_extracted_facts_raw = [{"fact": "Claim A"}, {"fact": "Claim B"}]
    session.verified_facts = [
        {
            "fact": "Qwen ist in Coding frontier-nah.",
            "status": "verified",
            "confidence": "high",
            "confidence_score_numeric": 0.81,
            "source_count": 2,
            "example_source_url": "https://example.com/a",
        }
    ]
    session.contract_v2.sources = [
        SourceRecord("s1", "https://example.com/a", "A", SourceType.BENCHMARK, SourceTier.A, has_methodology=True),
        SourceRecord("s2", "https://example.com/b", "B", SourceType.ANALYSIS, SourceTier.B, has_methodology=True),
    ]
    session.contract_v2.claims = [
        ClaimRecord(
            claim_id="c1",
            question_id=session.contract_v2.question.question_id,
            domain="coding",
            subject="Qwen",
            claim_text="Qwen ist in Coding frontier-nah.",
            verdict=ClaimVerdict.CONFIRMED,
            confidence=0.9,
            supports=["s1", "s2"],
        )
    ]
    session.contract_v2.evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS),
        EvidenceRecord("e2", "c1", "s2", EvidenceStance.SUPPORTS),
    ]

    report = _create_academic_markdown_report(session)

    assert "**Claim-Status:** 1 confirmed" in report
    assert "Executive Briefing" in report
    assert "Kernthesen" in report
    assert "Executive Verdict Table" in report
    assert "Domain Scorecards" in report
    assert "Claim Register" in report
    assert "Schlussfolgerungen" in report
    assert "Quellenanhang" in report
    assert "## Inhaltsverzeichnis" not in report
    assert "durch mehrere unabhängige Quellen verifiziert werden" not in report
    assert report.index("## Executive Briefing") < report.index("## Executive Verdict Table")
    assert report.index("## Kernthesen") < report.index("## Claim Register")
    assert report.index("## Schlussfolgerungen") < report.index("## Domain Scorecards")

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_export_contract_v2_builds_claims_and_evidence_from_legacy_data():
    from tools.deep_research.tool import DeepResearchSession, ResearchNode

    session = DeepResearchSession("Vergleiche chinesische und US-Modelle")
    session.research_tree.append(
        ResearchNode(
            url="https://example.com/benchmark",
            title="Independent Benchmark",
            content_snippet="benchmark",
        )
    )
    session.verified_facts = [
        {
            "fact": "Qwen3-Coder ist stark in Coding-Benchmarks.",
            "status": "verified",
            "example_source_url": "https://example.com/benchmark",
        }
    ]
    session.unverified_claims = [
        {
            "fact": "Offizieller YouTube-Launch nennt Agent-Faehigkeiten.",
            "source": "https://www.youtube.com/watch?v=abc",
            "source_title": "Official Launch",
            "source_type": "youtube",
            "key_quote": "Agentic workflows",
            "is_official": True,
        }
    ]

    exported = session.export_contract_v2()

    assert len(exported["claims"]) == 2
    assert len(exported["evidences"]) == 2
    assert any(claim["claim_type"] == "verified_fact" for claim in exported["claims"])
    assert any(claim["claim_type"] == "legacy_claim" for claim in exported["claims"])


def test_export_contract_v2_marks_youtube_source_with_transcript_like_signal():
    from tools.deep_research.tool import DeepResearchSession

    session = DeepResearchSession("Pruefe Agentik")
    session.unverified_claims = [
        {
            "fact": "Das Video beschreibt Tool Use.",
            "source": "https://www.youtube.com/watch?v=abc",
            "source_title": "Official Dev Update",
            "source_type": "youtube",
            "key_quote": "Tool use and agents",
            "is_official": True,
        }
    ]

    exported = session.export_contract_v2()
    youtube_sources = [source for source in exported["sources"] if source["source_type"] == "youtube"]

    assert len(youtube_sources) == 1
    assert youtube_sources[0]["has_transcript"] is True
    assert youtube_sources[0]["is_official"] is True


def test_export_contract_v2_filters_off_topic_admin_claims():
    from tools.deep_research.tool import DeepResearchSession

    session = DeepResearchSession("Chinese LLMs Qwen DeepSeek AI agents capabilities comparison 2025 2026")
    session.verified_facts = [
        {
            "fact": "Als Kontaktadresse ist research@deepseek.com angegeben.",
            "status": "verified",
            "source_count": 1,
            "example_source_url": "https://arxiv.org/abs/2501.12948",
        },
        {
            "fact": "DeepSeek-R1 zeigt starke Reasoning-Leistung in Coding-Benchmarks.",
            "status": "verified",
            "source_count": 2,
            "example_source_url": "https://arxiv.org/abs/2501.12948",
        },
    ]

    exported = session.export_contract_v2()
    claim_texts = [claim["claim_text"] for claim in exported["claims"]]

    assert "Als Kontaktadresse ist research@deepseek.com angegeben." not in claim_texts
    assert "DeepSeek-R1 zeigt starke Reasoning-Leistung in Coding-Benchmarks." in claim_texts

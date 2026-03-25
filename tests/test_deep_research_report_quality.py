from __future__ import annotations

import pytest


def test_research_plan_contains_query_variants_and_subquestions():
    from tools.deep_research.tool import DeepResearchSession, _ensure_research_plan

    session = DeepResearchSession(
        "Chinese LLMs DeepSeek Qwen agent capabilities",
        focus_areas=["tool use", "benchmarks"],
    )
    plan = _ensure_research_plan(session)

    assert plan.query_variants
    assert any("tool use" in query.lower() for query in plan.query_variants)
    assert "benchmark" in " ".join(plan.query_variants).lower()
    assert len(plan.subquestions) >= 2


def test_auto_scope_mode_chooses_landscape_for_broad_topic():
    from tools.deep_research.tool import DeepResearchSession, _ensure_research_plan

    session = DeepResearchSession("Introspective Autonomous Systems AI 2025 2026")
    plan = _ensure_research_plan(session)

    assert plan.scope_mode == "landscape"


def test_landscape_scope_keeps_adjacent_signals_but_rejects_noise():
    from tools.deep_research.tool import DeepResearchSession, _is_text_on_session_topic

    session = DeepResearchSession(
        "Introspective Autonomous Systems AI 2025 2026",
        scope_mode="landscape",
    )

    assert _is_text_on_session_topic(
        session,
        "Multi-Agent-Orchestrierung mit Planer, Arbeiter und Kritiker fuer komplexe Aufgaben.",
    ) is True
    assert _is_text_on_session_topic(
        session,
        "International AI Safety Report 2026 diskutiert Risiken und Governance fortgeschrittener KI.",
    ) is True
    assert _is_text_on_session_topic(
        session,
        "Make.com Automatisierung mit Bundle, Iterator, Aggregator und Router.",
    ) is False


def test_strict_scope_rejects_adjacent_but_unspecific_iass_content():
    from tools.deep_research.tool import DeepResearchSession, _is_text_on_session_topic

    session = DeepResearchSession(
        "Introspective Autonomous Systems AI 2025 2026",
        scope_mode="strict",
    )

    assert _is_text_on_session_topic(
        session,
        "Multi-Agent-Orchestrierung mit Planer, Arbeiter und Kritiker fuer komplexe Aufgaben.",
    ) is False


@pytest.mark.asyncio
async def test_evaluate_relevance_rejects_admin_noise_for_strict_topic_query():
    from tools.deep_research.tool import DeepResearchSession, _evaluate_relevance

    session = DeepResearchSession(
        "Chinese LLMs DeepSeek Qwen agent capabilities tool use",
        focus_areas=["benchmarks", "function calling"],
    )
    sources = [
        {
            "url": "https://example.com/contact",
            "title": "DeepSeek contact email and careers",
            "snippet": "support jobs address customer service",
            "score": 0.92,
        },
        {
            "url": "https://example.com/agent-benchmark",
            "title": "DeepSeek and Qwen tool use benchmark 2026",
            "snippet": "function calling multi agent evaluation",
            "score": 0.48,
        },
    ]

    relevant = await _evaluate_relevance(sources, session, 5)

    assert [item[0]["url"] for item in relevant] == ["https://example.com/agent-benchmark"]


def test_research_metadata_summary_exposes_research_plan():
    from tools.deep_research.tool import DeepResearchSession, _get_research_metadata_summary

    session = DeepResearchSession(
        "Enterprise RAG systems",
        focus_areas=["retrieval augmented generation", "evaluation"],
    )

    summary = _get_research_metadata_summary(session)

    assert "research_plan" in summary
    assert summary["research_plan"]["scope_mode"] == "strict"
    assert summary["research_plan"]["query_variants"]
    assert summary["research_plan"]["subquestions"]
    assert summary["research_plan"]["must_have_terms"]
    assert "query_variant_worker" in summary
    assert "semantic_claim_dedupe" in summary
    assert "conflict_scan_worker" in summary


@pytest.mark.asyncio
async def test_narrative_synthesis_falls_back_when_llm_returns_empty(monkeypatch):
    from tools.deep_research.tool import DeepResearchSession, ResearchNode, _create_narrative_synthesis_report

    class _FakeResponse:
        choices = [type("Choice", (), {"message": type("Message", (), {"content": ""})()})()]

    monkeypatch.setattr(
        "tools.deep_research.tool.client.chat.completions.create",
        lambda **_: _FakeResponse(),
    )

    session = DeepResearchSession("Chinese LLMs agent capabilities")
    session.research_tree = [
        ResearchNode(url="https://example.com/agent-benchmark", title="Agent Benchmark", content_snippet="benchmarks")
    ]
    session.verified_facts = [
        {
            "fact": "DeepSeek und Qwen werden in agentischen Benchmarks diskutiert.",
            "source_count": 2,
            "supporting_quotes": ["Agentic evaluation and planning."],
        }
    ]
    session.unverified_claims = [
        {
            "fact": "Kimi nennt Agent Swarm fuer komplexe Aufgaben.",
            "source_type": "arxiv",
            "source": "https://arxiv.org/abs/2602.00001",
            "source_title": "Kimi K2.5",
        }
    ]

    report = await _create_narrative_synthesis_report(session)

    assert "0 Wörter" not in report
    assert "## Einordnung" in report
    assert "## Fazit" in report
    assert "## Quellenhinweise" in report


def test_compose_pdf_markdown_includes_readable_article_and_appendix():
    from tools.deep_research.tool import _compose_pdf_markdown

    readable_narrative = "## Einordnung\n\n" + ("Lesbarer Bericht mit Kontext und Agentik. " * 130)
    academic = "# Tiefenrecherche-Bericht\n\n## Kernthesen\n\nStrukturierte Analyse."

    combined = _compose_pdf_markdown(readable_narrative, academic)

    assert combined.startswith("## Einordnung")
    assert "## Analytischer Anhang" in combined
    assert "## Kernthesen" in combined


def test_export_contract_v2_dedupes_duplicate_verified_and_legacy_claims():
    from tools.deep_research.tool import DeepResearchSession, ResearchNode

    claim_text = "Qwen und DeepSeek unterstuetzen agentische Workflows und Tool-Use."
    source_url = "https://example.com/agentic"

    session = DeepResearchSession("Chinese LLMs Qwen DeepSeek agent capabilities tool use")
    session.research_tree = [
        ResearchNode(url=source_url, title="Agentic capabilities", content_snippet="agentic")
    ]
    session.verified_facts = [
        {
            "fact": claim_text,
            "status": "tentatively_verified",
            "source_count": 1,
            "example_source_url": source_url,
        }
    ]
    session.unverified_claims = [
        {
            "fact": claim_text,
            "source": source_url,
            "source_type": "web",
            "source_count": 1,
        }
    ]

    exported = session.export_contract_v2()
    matching = [claim for claim in exported["claims"] if claim["claim_text"] == claim_text]

    assert len(matching) == 1
    assert matching[0]["claim_type"] == "verified_fact"
    assert "legacy_status=tentatively_verified" in matching[0]["notes"]


def test_claim_is_on_topic_rejects_non_agentic_medical_benchmark_for_agentic_query():
    from tools.deep_research.research_contracts import claim_is_on_topic

    query = (
        "Chinese LLMs DeepSeek Qwen Yi Baichuan Ernie Doubao Kimi "
        "agent capabilities tool use function calling multi-agent support benchmarks"
    )

    assert claim_is_on_topic(
        query,
        "DeepSeek-R1 und Qwen-2.5 werden bei ophthalmologischen Patientenfragen in Englisch und Arabisch verglichen.",
    ) is False
    assert claim_is_on_topic(
        query,
        "DeepSeek und Qwen werden fuer Tool Use, Function Calling und Multi-Agent-Planung in Benchmarks beschrieben.",
    ) is True

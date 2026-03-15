from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.research_contracts import claim_is_on_topic
from tools.deep_research.tool import _compose_pdf_markdown, _dedupe_contract_claims
from tools.deep_research.research_contracts import ClaimRecord


@given(
    dup_count=st.integers(min_value=1, max_value=6),
    suffix=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        min_size=1,
        max_size=12,
    ),
)
@settings(deadline=None, max_examples=50)
def test_hypothesis_claim_dedupe_never_increases_count(dup_count: int, suffix: str):
    claim_text = f"Qwen {suffix} unterstuetzt Tool Use."
    claims = [
        ClaimRecord(f"c{i}", "q", "agentic", "Qwen", claim_text, claim_type="legacy_claim")
        for i in range(dup_count)
    ]

    deduped = _dedupe_contract_claims(claims)

    assert 0 < len(deduped) <= len(claims)
    assert len({claim.claim_text for claim in deduped}) == len(deduped)


@given(word_count=st.integers(min_value=120, max_value=400))
@settings(deadline=None, max_examples=40)
def test_hypothesis_compose_pdf_markdown_keeps_readable_narrative(word_count: int):
    narrative = "## Einordnung\n\n" + ("lesbar " * word_count)
    academic = "# Tiefenrecherche-Bericht\n\n## Kernthesen\n\nAnalyse."

    combined = _compose_pdf_markdown(narrative, academic)

    assert combined.startswith("## Einordnung")
    assert "## Analytischer Anhang" in combined


@given(model=st.sampled_from(["DeepSeek", "Qwen", "Kimi", "Baichuan"]))
@settings(deadline=None, max_examples=20)
def test_hypothesis_agentic_query_requires_agentic_signal(model: str):
    query = "Chinese LLMs agent capabilities tool use function calling multi-agent support"
    medical_claim = f"{model} wird bei ophthalmologischen Patientenfragen verglichen."
    agentic_claim = f"{model} unterstuetzt Tool Use und Multi-Agent-Planung."

    assert claim_is_on_topic(query, medical_claim) is False
    assert claim_is_on_topic(query, agentic_claim) is True

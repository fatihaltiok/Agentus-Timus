from __future__ import annotations

import sys
from pathlib import Path

import deal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.research_contracts import claim_is_on_topic
from tools.deep_research.tool import (
    _compose_pdf_markdown,
    _dedupe_contract_claims,
)
from tools.deep_research.research_contracts import ClaimRecord


@deal.post(lambda r: r is True)
def _contract_compose_pdf_markdown_prefers_readable_narrative() -> bool:
    narrative = "## Einordnung\n\n" + ("Lesbarer Bericht mit Agentik und Kontext. " * 130)
    academic = "# Tiefenrecherche-Bericht\n\n## Kernthesen\n\nAnalytischer Block."
    combined = _compose_pdf_markdown(narrative, academic)
    return combined.startswith("## Einordnung") and "## Analytischer Anhang" in combined


@deal.post(lambda r: r is True)
def _contract_dedupe_contract_claims_never_expands() -> bool:
    claims = [
        ClaimRecord("c1", "q", "agentic", "Qwen", "Qwen unterstuetzt Tool Use.", claim_type="verified_fact"),
        ClaimRecord("c2", "q", "agentic", "Qwen", "Qwen unterstuetzt Tool Use.", claim_type="legacy_claim"),
    ]
    deduped = _dedupe_contract_claims(claims)
    return len(deduped) <= len(claims) and len(deduped) == 1


@deal.post(lambda r: r is True)
def _contract_agentic_query_rejects_non_agentic_claim() -> bool:
    query = "Chinese LLMs DeepSeek Qwen agent capabilities tool use function calling multi-agent support"
    claim = "DeepSeek und Qwen werden in ophthalmologischen Patientenfragen verglichen."
    return claim_is_on_topic(query, claim) is False


def test_contract_compose_pdf_markdown_prefers_readable_narrative():
    assert _contract_compose_pdf_markdown_prefers_readable_narrative() is True


def test_contract_dedupe_contract_claims_never_expands():
    assert _contract_dedupe_contract_claims_never_expands() is True


def test_contract_agentic_query_rejects_non_agentic_claim():
    assert _contract_agentic_query_rejects_non_agentic_claim() is True

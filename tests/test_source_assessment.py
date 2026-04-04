from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.research_contracts import (
    SourceTier,
    SourceType,
    build_source_record_from_legacy,
    infer_source_type,
    is_german_state_affiliated_url,
)


def test_infer_source_type_for_known_domains():
    assert infer_source_type("https://www.youtube.com/watch?v=abc") == SourceType.YOUTUBE
    assert infer_source_type("https://arxiv.org/abs/2501.00001") == SourceType.PAPER
    assert infer_source_type("https://github.com/QwenLM/Qwen3") == SourceType.REPOSITORY
    assert infer_source_type("https://api-docs.deepseek.com/news/news251201") == SourceType.VENDOR


def test_build_source_record_marks_official_youtube_with_transcript_as_a():
    source = build_source_record_from_legacy(
        source_id="yt1",
        url="https://www.youtube.com/watch?v=abc",
        title="Official Launch",
        declared_type="youtube",
        metadata={"is_official": True, "has_transcript": True},
    )
    assert source.source_type == SourceType.YOUTUBE
    assert source.tier == SourceTier.A


def test_build_source_record_marks_german_state_affiliated_metadata():
    source = build_source_record_from_legacy(
        source_id="de1",
        url="https://www.bundestag.de/dokumente/textarchiv",
        title="Deutscher Bundestag",
    )
    assert source.source_type == SourceType.REGULATOR
    assert source.metadata["state_affiliated"] is True
    assert source.metadata["country_code"] == "de"


def test_detects_state_affiliated_dw_domain():
    assert is_german_state_affiliated_url("https://www.dw.com/de/thema")


class TestAcademicPublicationDomains:
    """P5-Fix: Medizinische/akademische Datenbanken dürfen nicht als REGULATOR landen."""

    def test_pmc_ncbi_is_paper_not_regulator(self):
        """pmc.ncbi.nlm.nih.gov endet auf .gov aber ist eine Literaturdatenbank."""
        assert infer_source_type("https://pmc.ncbi.nlm.nih.gov/articles/PMC12059827/") == SourceType.PAPER

    def test_pubmed_is_paper(self):
        assert infer_source_type("https://pubmed.ncbi.nlm.nih.gov/39891234/") == SourceType.PAPER

    def test_europepmc_is_paper(self):
        assert infer_source_type("https://europepmc.org/article/med/12345678") == SourceType.PAPER

    def test_biorxiv_is_paper(self):
        assert infer_source_type("https://www.biorxiv.org/content/10.1101/2025.03.01") == SourceType.PAPER

    def test_ssrn_is_paper(self):
        assert infer_source_type("https://ssrn.com/abstract=4987654") == SourceType.PAPER

    def test_actual_gov_regulator_unaffected(self):
        """Echte .gov-Behörden-URLs müssen weiterhin REGULATOR bleiben."""
        assert infer_source_type("https://www.regulations.gov/document/abc") == SourceType.REGULATOR
        assert infer_source_type("https://ec.europa.eu/commission/policy") == SourceType.REGULATOR

    def test_pmc_tier_is_a_with_methodology(self):
        """PAPER + has_methodology → Tier A (nicht mehr D wie bei UNKNOWN)."""
        source = build_source_record_from_legacy(
            source_id="pmc1",
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12059827/",
            title="Chinese generative AI models rival ChatGPT-4 in ophthalmology",
            metadata={"has_methodology": True},
        )
        assert source.source_type == SourceType.PAPER
        assert source.tier == SourceTier.A

    def test_pmc_is_primary(self):
        """Akademische Paper sind is_primary=True."""
        source = build_source_record_from_legacy(
            source_id="pmc2",
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12059827/",
            title="Study",
        )
        assert source.is_primary is True


def test_build_source_record_marks_forum_like_sources_as_d():
    source = build_source_record_from_legacy(
        source_id="f1",
        url="https://reddit.com/r/LocalLLaMA",
        title="Forum Thread",
    )
    assert source.source_type == SourceType.UNKNOWN
    assert source.tier == SourceTier.D

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_build_research_pdf_raises_when_pdf_required_and_builder_fails(monkeypatch, tmp_path):
    from tools.deep_research.tool import DeepResearchSession, _build_research_pdf

    monkeypatch.setenv("DEEP_RESEARCH_PDF_ENABLED", "true")
    session = DeepResearchSession("Teste PDF Strict Mode")

    with patch(
        "tools.deep_research.pdf_builder.ResearchPDFBuilder.build_pdf",
        side_effect=RuntimeError("weasyprint boom"),
    ):
        with pytest.raises(RuntimeError, match="PDF-Erstellung fehlgeschlagen"):
            _build_research_pdf(
                content="# Report",
                images=[],
                session=session,
                output_dir=str(tmp_path),
                session_id="sess-pdf-strict",
                require_pdf=True,
            )


def test_build_research_pdf_returns_none_when_pdf_optional_and_builder_fails(monkeypatch, tmp_path):
    from tools.deep_research.tool import DeepResearchSession, _build_research_pdf

    monkeypatch.setenv("DEEP_RESEARCH_PDF_ENABLED", "true")
    session = DeepResearchSession("Teste PDF Optional Mode")

    with patch(
        "tools.deep_research.pdf_builder.ResearchPDFBuilder.build_pdf",
        side_effect=RuntimeError("weasyprint boom"),
    ):
        result = _build_research_pdf(
            content="# Report",
            images=[],
            session=session,
            output_dir=str(tmp_path),
            session_id="sess-pdf-optional",
            require_pdf=False,
        )

    assert result is None


def test_build_research_pdf_raises_when_builder_returns_nonexistent_file(monkeypatch, tmp_path):
    from tools.deep_research.tool import DeepResearchSession, _build_research_pdf

    monkeypatch.setenv("DEEP_RESEARCH_PDF_ENABLED", "true")
    session = DeepResearchSession("Teste fehlenden Artefaktpfad")

    with patch(
        "tools.deep_research.pdf_builder.ResearchPDFBuilder.build_pdf",
        return_value=str(Path(tmp_path) / "nicht_da.pdf"),
    ):
        with pytest.raises(RuntimeError, match="Kein gueltiger PDF-Artefaktpfad"):
            _build_research_pdf(
                content="# Report",
                images=[],
                session=session,
                output_dir=str(tmp_path),
                session_id="sess-pdf-missing",
                require_pdf=True,
            )

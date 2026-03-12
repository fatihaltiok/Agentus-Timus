import base64
import sys
from pathlib import Path
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.image_collector import ImageResult
from tools.deep_research.pdf_builder import ResearchPDFBuilder


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0s0AAAAASUVORK5CYII="
)


def _write_png(path: Path) -> None:
    path.write_bytes(_PNG_1X1)


def test_build_section_figures_returns_figure_metadata(tmp_path):
    builder = ResearchPDFBuilder()
    image_path = tmp_path / "chart.png"
    _write_png(image_path)

    figures = builder._build_section_figures([
        ImageResult(
            local_path=str(image_path),
            caption="Produktionslinie mit Agenten",
            section_title="Praxisbeispiele",
            source="dalle",
        )
    ])

    assert "Praxisbeispiele" in figures
    assert len(figures["Praxisbeispiele"]) == 1
    figure = figures["Praxisbeispiele"][0]
    assert figure["caption"] == "Produktionslinie mit Agenten"
    assert figure["kind_label"] == "KI-generierte Abbildung"
    assert figure["path"].startswith("data:image/")


def test_build_template_sections_embeds_figures_and_lead(tmp_path):
    builder = ResearchPDFBuilder()
    image_path = tmp_path / "visual.png"
    _write_png(image_path)
    figure_map = builder._build_section_figures([
        ImageResult(
            local_path=str(image_path),
            caption="Abbildung zur Einordnung",
            section_title="Einordnung",
            source="web",
        )
    ])

    sections = builder._build_template_sections(
        [("Einordnung", "Erste Kernaussage.\n\n- Punkt A")],
        figure_map,
    )

    assert len(sections) == 1
    section = sections[0]
    assert section["lead"] == "Erste Kernaussage."
    assert section["slug"] == "einordnung"
    assert len(section["figures"]) == 1


def test_build_template_sections_skips_heading_for_lead_and_deduplicates_body():
    builder = ResearchPDFBuilder()

    sections = builder._build_template_sections(
        [("Methodik", "### Recherche-Ansatz\n\nErste Kernaussage.\n\nMehr Kontext.")],
        {},
    )

    assert len(sections) == 1
    section = sections[0]
    assert section["lead"] == "Erste Kernaussage."
    assert "<h3>Recherche-Ansatz</h3>" in section["text_html"]
    assert section["text_html"].count("Erste Kernaussage.") == 0
    assert "Mehr Kontext." in section["text_html"]


def test_template_contains_new_cover_and_figure_hooks():
    template = Path("tools/deep_research/report_template.html").read_text(encoding="utf-8")
    assert 'class="cover"' in template
    assert 'class="hero-figure"' in template
    assert 'class="figure-grid"' in template
    assert 'class="atlas-grid"' in template
    assert "cover_visual" in template
    assert "report_figures" in template


def test_markdown_to_html_renders_markdown_tables():
    builder = ResearchPDFBuilder()
    html = builder._markdown_to_html(
        "| Col A | Col B |\n"
        "|-------|-------|\n"
        "| one | two |\n"
        "| three | four |"
    )

    assert "<table>" in html
    assert "<thead>" in html
    assert "<tbody>" in html
    assert "<th>Col A</th>" in html
    assert "<td>three</td>" in html


def test_build_pdf_uses_autoescape_for_plain_fields(monkeypatch, tmp_path):
    captured = {}

    class _FakeHTML:
        def __init__(self, string: str, base_url: str):
            captured["html"] = string
            captured["base_url"] = base_url

        def write_pdf(self, output_path: str) -> None:
            Path(output_path).write_bytes(b"%PDF-1.4 test")

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=_FakeHTML))

    session = SimpleNamespace(
        query='<script>alert("x")</script>',
        research_tree=[],
        unverified_claims=[],
    )

    output_path = tmp_path / "report.pdf"
    builder = ResearchPDFBuilder()
    result = builder.build_pdf(
        narrative_md="## Abschnitt\n\nSicherer **Inhalt**.",
        images=[],
        session=session,
        output_path=str(output_path),
    )

    assert result == str(output_path)
    assert output_path.exists()
    assert '&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt;' in captured["html"]
    assert "<strong>Inhalt</strong>" in captured["html"]


@given(
    web_count=st.integers(min_value=0, max_value=500),
    yt_count=st.integers(min_value=0, max_value=500),
    trend_count=st.integers(min_value=0, max_value=500),
    image_count=st.integers(min_value=0, max_value=500),
    word_count=st.integers(min_value=0, max_value=50000),
)
@settings(deadline=None, max_examples=100)
def test_hypothesis_key_metrics_contract(web_count, yt_count, trend_count, image_count, word_count):
    metrics = ResearchPDFBuilder._build_key_metrics(
        web_count=web_count,
        yt_count=yt_count,
        trend_count=trend_count,
        image_count=image_count,
        word_count=word_count,
    )
    assert len(metrics) == 5
    assert metrics[0]["value"] == str(web_count)
    assert metrics[3]["value"] == str(image_count)
    assert metrics[4]["value"] == str(word_count)

# tools/deep_research/pdf_builder.py
"""
ResearchPDFBuilder — erstellt ein professionelles A4-PDF via WeasyPrint + Jinja2.

Workflow: Markdown → HTML (Jinja2-Template) → PDF (WeasyPrint CSS-Renderer)

Layout:
- A4, Ränder 20mm, DejaVu Sans (System-Font, kein Download)
- Titelseite (dunkelblau #1a3a5c / gold #c8a84b) → TOC → Abschnitte → Quellenverzeichnis
- Bilder rechtsbündig, 75mm breit, mit Bildunterschrift
"""

import base64
import logging
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from tools.deep_research.image_collector import ImageResult

logger = logging.getLogger("pdf_builder")

_TEMPLATE_DIR = Path(__file__).parent
_TEMPLATE_FILE = "report_template.html"


class ResearchPDFBuilder:
    """Erstellt ein A4-PDF aus einem Markdown-Lesebericht und gesammelten Bildern."""

    def build_pdf(
        self,
        narrative_md: str,
        images: List["ImageResult"],
        session,
        output_path: str,
    ) -> str:
        """
        Erstellt das PDF und speichert es unter output_path.

        Args:
            narrative_md: Markdown-Text des Lese-Berichts
            images: Liste von ImageResult-Objekten (aus image_collector)
            session: DeepResearchSession (für Metadaten)
            output_path: Ziel-Pfad für das PDF

        Returns:
            output_path (str)
        """
        from weasyprint import HTML as WP_HTML

        sections = self._parse_markdown(narrative_md)
        toc_titles = [heading for heading, _ in sections]
        figures_by_section = self._build_section_figures(images)
        template_sections = self._build_template_sections(sections, figures_by_section)
        report_figures = [figure for section in template_sections for figure in section["figures"]]
        cover_visual = report_figures[0] if report_figures else None

        # Quellen aufbereiten
        web_sources = [
            {"title": (n.title or "")[:80], "url": (n.url or "")[:120]}
            for n in session.research_tree
        ]
        yt_sources = [
            {
                "title": c.get("source_title", c.get("video_id", ""))[:80],
                "channel": c.get("channel", ""),
                "url": c.get("source", "")[:120],
            }
            for c in session.unverified_claims
            if c.get("source_type") == "youtube"
        ]
        arxiv_sources = [
            {
                "title": c.get("source_title", "")[:80],
                "authors": c.get("authors", "")[:60],
                "published": c.get("published_date", ""),
                "arxiv_id": c.get("arxiv_id", ""),
                "url": c.get("source", "")[:120],
            }
            for c in session.unverified_claims
            if c.get("source_type") == "arxiv"
        ]
        github_sources = [
            {
                "title": c.get("full_name", c.get("source_title", ""))[:80],
                "stars": c.get("stars", 0),
                "language": c.get("language", ""),
                "url": c.get("source", "")[:120],
            }
            for c in session.unverified_claims
            if c.get("source_type") == "github"
        ]
        hf_sources = [
            {
                "title": c.get("source_title", "")[:80],
                "hf_type": c.get("hf_type", "model"),
                "downloads": c.get("downloads", 0),
                "upvotes": c.get("upvotes", 0),
                "url": c.get("source", "")[:120],
            }
            for c in session.unverified_claims
            if c.get("source_type") == "huggingface"
        ]
        edison_sources = [
            {
                "title": c.get("source_title", c.get("title", ""))[:80],
                "authors": c.get("authors", "")[:80],
                "year": str(c.get("year", c.get("published_date", ""))),
                "journal": c.get("journal", c.get("venue", ""))[:60],
                "url": c.get("source", c.get("doi", ""))[:120],
            }
            for c in session.unverified_claims
            if c.get("source_type") == "edison"
        ]

        trend_count = len(arxiv_sources) + len(github_sources) + len(hf_sources)

        # Wortanzahl
        word_count = len(narrative_md.split())
        reading_minutes = max(1, round(word_count / 180))

        # Deutsches Datum (strftime %B ist systemabhängig englisch)
        _MONTHS_DE = [
            "", "Januar", "Februar", "März", "April", "Mai", "Juni",
            "Juli", "August", "September", "Oktober", "November", "Dezember"
        ]
        now = datetime.now()
        date_str = f"{now.day:02d}. {_MONTHS_DE[now.month]} {now.year}"

        # Template rendern
        env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
        tmpl = env.get_template(_TEMPLATE_FILE)
        html_content = tmpl.render(
            query=str(session.query),
            date=date_str,
            web_count=len(web_sources),
            yt_count=len(yt_sources),
            trend_count=trend_count,
            image_count=len(report_figures),
            word_count=word_count,
            reading_minutes=reading_minutes,
            toc=toc_titles,
            sections=template_sections,
            report_figures=report_figures,
            cover_visual=cover_visual,
            key_metrics=self._build_key_metrics(
                web_count=len(web_sources),
                yt_count=len(yt_sources),
                trend_count=trend_count,
                image_count=len(report_figures),
                word_count=word_count,
            ),
            web_sources=web_sources,
            yt_sources=yt_sources,
            arxiv_sources=arxiv_sources,
            github_sources=github_sources,
            hf_sources=hf_sources,
            edison_sources=edison_sources,
        )

        # PDF erzeugen
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        WP_HTML(string=html_content, base_url=str(_TEMPLATE_DIR)).write_pdf(output_path)

        size_kb = Path(output_path).stat().st_size // 1024
        logger.info(f"📄 PDF erstellt: {output_path} ({size_kb} KB)")
        return output_path

    # ------------------------------------------------------------------
    # Hilfs-Methoden
    # ------------------------------------------------------------------

    @staticmethod
    def _figure_kind_label(source: str) -> str:
        mapping = {
            "web": "Web-Referenzbild",
            "dalle": "KI-generierte Abbildung",
            "creative": "Kreative Visualisierung",
        }
        return mapping.get((source or "").lower(), "Abbildung")

    def _build_section_figures(self, images: List["ImageResult"]) -> Dict[str, List[Dict[str, str]]]:
        by_section: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for idx, img in enumerate(images, start=1):
            if not img or not img.section_title:
                continue
            if not os.path.isfile(img.local_path):
                continue
            data_uri = self._file_to_data_uri(img.local_path)
            if not data_uri:
                continue
            by_section[img.section_title].append({
                "id": f"fig-{idx}",
                "path": data_uri,
                "caption": img.caption or img.section_title,
                "alt": img.section_title,
                "kind_label": self._figure_kind_label(img.source),
                "source": img.source,
            })
        return dict(by_section)

    def _build_template_sections(
        self,
        sections: List[Tuple[str, str]],
        figures_by_section: Dict[str, List[Dict[str, str]]],
    ) -> List[Dict[str, object]]:
        template_sections: List[Dict[str, object]] = []
        for idx, (heading, text) in enumerate(sections, start=1):
            template_sections.append({
                "index": idx,
                "heading": heading,
                "slug": self._slugify(heading),
                "lead": self._extract_lead(text),
                "text_html": self._markdown_to_html(text),
                "figures": figures_by_section.get(heading, []),
            })
        return template_sections

    @staticmethod
    def _build_key_metrics(
        web_count: int,
        yt_count: int,
        trend_count: int,
        image_count: int,
        word_count: int,
    ) -> List[Dict[str, str]]:
        metrics = [
            {"label": "Webquellen", "value": str(web_count), "tone": "primary"},
            {"label": "YouTube", "value": str(yt_count), "tone": "neutral"},
            {"label": "Trendquellen", "value": str(trend_count), "tone": "neutral"},
            {"label": "Abbildungen", "value": str(image_count), "tone": "accent"},
            {"label": "Woerter", "value": str(word_count), "tone": "neutral"},
        ]
        return metrics

    @staticmethod
    def _extract_lead(text: str) -> str:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line = re.sub(r"^\s*[-*•]\s+", "", line)
            return line[:260]
        return ""

    @staticmethod
    def _slugify(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return cleaned or "section"

    def _parse_markdown(self, md: str) -> List[Tuple[str, str]]:
        """Zerlegt Markdown in (Heading, Content)-Paare anhand ## Grenzen."""
        sections: List[Tuple[str, str]] = []
        current_heading = ""
        current_lines: List[str] = []

        for line in md.splitlines():
            # H2-Überschrift → neuer Abschnitt
            if re.match(r"^##\s+", line):
                if current_heading and current_lines:
                    sections.append((current_heading, "\n".join(current_lines).strip()))
                current_heading = re.sub(r"^##\s+", "", line).strip()
                current_lines = []
            # H1 überspringen
            elif re.match(r"^#\s+", line):
                continue
            # Horizontale Linie überspringen
            elif re.match(r"^-{3,}$", line.strip()):
                continue
            # Metazeile (*Erstellt am...*) überspringen
            elif re.match(r"^\*[^*].*[^*]\*$", line.strip()):
                continue
            else:
                current_lines.append(line)

        if current_heading and current_lines:
            sections.append((current_heading, "\n".join(current_lines).strip()))

        # Abschnitte ohne Inhalt entfernen
        sections = [(h, t) for h, t in sections if t.strip()]

        return sections

    def _markdown_to_html(self, text: str) -> str:
        """Konvertiert Markdown-Absätze zu HTML für das Template."""
        lines = text.splitlines()
        html_parts: List[str] = []
        in_ul = False
        table_lines: List[str] = []
        para_lines: List[str] = []

        def flush_para():
            nonlocal para_lines
            if para_lines:
                combined = " ".join(l for l in para_lines if l.strip())
                if combined:
                    html_parts.append(f"<p>{combined}</p>")
                para_lines = []

        def flush_ul():
            nonlocal in_ul
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False

        def is_table_line(line: str) -> bool:
            stripped = line.strip()
            return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2

        def is_table_separator(line: str) -> bool:
            stripped = line.strip()
            return bool(re.match(r"^\|\s*[-:| ]+\|\s*$", stripped))

        def flush_table():
            nonlocal table_lines
            if not table_lines:
                return
            rows = [line for line in table_lines if line.strip()]
            if len(rows) >= 2 and is_table_separator(rows[1]):
                header = [self._inline_md(cell.strip()) for cell in rows[0].strip().strip("|").split("|")]
                body_rows = rows[2:]
            else:
                header = [self._inline_md(cell.strip()) for cell in rows[0].strip().strip("|").split("|")]
                body_rows = rows[1:]
            html_parts.append("<table>")
            html_parts.append("<thead><tr>")
            for cell in header:
                html_parts.append(f"<th>{cell}</th>")
            html_parts.append("</tr></thead>")
            if body_rows:
                html_parts.append("<tbody>")
                for row in body_rows:
                    cells = [self._inline_md(cell.strip()) for cell in row.strip().strip("|").split("|")]
                    html_parts.append("<tr>")
                    for cell in cells:
                        html_parts.append(f"<td>{cell}</td>")
                    html_parts.append("</tr>")
                html_parts.append("</tbody>")
            html_parts.append("</table>")
            table_lines = []

        for line in lines:
            if is_table_line(line):
                flush_para()
                flush_ul()
                table_lines.append(line)
                continue
            flush_table()
            # Bullet-Listenelement
            if re.match(r"^\s*[-*•]\s+", line):
                flush_para()
                if not in_ul:
                    html_parts.append("<ul>")
                    in_ul = True
                item = re.sub(r"^\s*[-*•]\s+", "", line)
                html_parts.append(f"<li>{self._inline_md(item)}</li>")
            # Leerzeile = Absatzgrenze
            elif not line.strip():
                flush_ul()
                flush_para()
            # Normaler Text
            else:
                flush_ul()
                para_lines.append(self._inline_md(line))

        flush_ul()
        flush_para()
        flush_table()
        return "\n".join(html_parts)

    def _inline_md(self, text: str) -> str:
        """Konvertiert Inline-Markdown (**bold**, *italic*, `code`) zu HTML."""
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)  # Links → nur Text
        # Blockquote-Erkennung: Zeilen die mit " starten
        if text.startswith('"') and text.endswith('"'):
            text = f"<blockquote>{text}</blockquote>"
        return text

    def _file_to_data_uri(self, path: str) -> str:
        """Kodiert eine Bilddatei als data-URI für WeasyPrint (funktioniert offline)."""
        try:
            with open(path, "rb") as f:
                data = f.read()
            ext = Path(path).suffix.lower().lstrip(".")
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
            b64 = base64.b64encode(data).decode()
            return f"data:{mime};base64,{b64}"
        except Exception as e:
            logger.warning(f"Bild-Encoding fehlgeschlagen ({path}): {e}")
            return ""

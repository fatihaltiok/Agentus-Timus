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
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, TYPE_CHECKING

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

        # Bildmap: section_title → ImageResult
        image_map = {}
        for img in images:
            if img.section_title not in image_map:
                image_map[img.section_title] = img

        # Abschnitte für Template aufbereiten
        template_sections = []
        for heading, text in sections:
            img = image_map.get(heading)
            img_path = None
            img_caption = ""
            if img and os.path.isfile(img.local_path):
                img_path = self._file_to_data_uri(img.local_path)
                img_caption = img.caption

            template_sections.append({
                "heading": heading,
                "text_html": self._markdown_to_html(text),
                "image_path": img_path,
                "image_caption": img_caption,
            })

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

        # Wortanzahl
        word_count = len(narrative_md.split())

        # Template rendern
        env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
        tmpl = env.get_template(_TEMPLATE_FILE)
        html_content = tmpl.render(
            query=str(session.query),
            date=datetime.now().strftime("%d. %B %Y"),
            web_count=len(web_sources),
            yt_count=len(yt_sources),
            image_count=len(images),
            word_count=word_count,
            toc=toc_titles,
            sections=template_sections,
            web_sources=web_sources,
            yt_sources=yt_sources,
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

    def _parse_markdown(self, md: str) -> List[Tuple[str, str]]:
        """Zerlegt Markdown in (Heading, Content)-Paare anhand ## Grenzen."""
        sections: List[Tuple[str, str]] = []
        current_heading = ""
        current_lines: List[str] = []

        for line in md.splitlines():
            if re.match(r"^##\s+", line):
                if current_heading and current_lines:
                    sections.append((current_heading, "\n".join(current_lines).strip()))
                current_heading = re.sub(r"^##\s+", "", line).strip()
                current_lines = []
            elif re.match(r"^#\s+", line):
                continue  # H1 = Dokumenttitel, überspringen
            elif re.match(r"^\*.*\*$", line.strip()) and not current_heading:
                continue  # Metazeile unter H1 überspringen
            else:
                current_lines.append(line)

        if current_heading and current_lines:
            sections.append((current_heading, "\n".join(current_lines).strip()))

        return sections

    def _markdown_to_html(self, text: str) -> str:
        """Konvertiert Markdown-Absätze zu HTML für das Template."""
        lines = text.splitlines()
        html_parts: List[str] = []
        in_ul = False
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

        for line in lines:
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

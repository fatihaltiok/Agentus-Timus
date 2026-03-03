# tools/deep_research/pdf_builder.py
"""
ResearchPDFBuilder — erstellt ein professionelles A4-PDF aus einem Deep-Research-Bericht.

Layout:
- A4, Ränder 20mm, Helvetica (fpdf2 builtin)
- Farben: Dunkelblau #1a3a5c, Schwarz, Gold #c8a84b
- Titelseite → Inhaltsverzeichnis → Abschnitte mit Bildern → Quellenverzeichnis
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, TYPE_CHECKING

from fpdf import FPDF

if TYPE_CHECKING:
    from tools.deep_research.image_collector import ImageResult

logger = logging.getLogger("pdf_builder")

# Farbkonstanten (R, G, B)
_COLOR_DARK_BLUE = (26, 58, 92)    # #1a3a5c
_COLOR_BLACK = (0, 0, 0)
_COLOR_GOLD = (200, 168, 75)       # #c8a84b
_COLOR_LIGHT_GRAY = (240, 240, 240)
_COLOR_MID_GRAY = (128, 128, 128)

# Layout
_MARGIN = 20          # mm
_LINE_HEIGHT = 6      # mm
_IMG_MAX_W = 80       # mm


class ResearchPDF(FPDF):
    """FPDF-Subklasse mit Kopf-/Fußzeile."""

    def __init__(self, title: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._report_title = title

    def header(self):
        if self.page_no() == 1:
            return  # Titelseite ohne Header
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_COLOR_MID_GRAY)
        self.cell(0, 5, self._report_title[:80], align="L")
        self.ln(5)
        self.set_draw_color(*_COLOR_LIGHT_GRAY)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_text_color(*_COLOR_BLACK)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_COLOR_MID_GRAY)
        self.cell(0, 5, f"Seite {self.page_no()} | Timus Deep Research v6.0", align="C")
        self.set_text_color(*_COLOR_BLACK)


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
        sections = self._parse_markdown(narrative_md)
        toc_titles = [heading for heading, _ in sections]

        # Bildmap: section_title → ImageResult
        image_map = {}
        for img in images:
            if img.section_title not in image_map:
                image_map[img.section_title] = img

        pdf = ResearchPDF(
            title=str(session.query)[:80],
            orientation="P",
            unit="mm",
            format="A4",
        )
        pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
        pdf.set_auto_page_break(auto=True, margin=_MARGIN)

        # --- Seite 1: Titelseite ---
        pdf.add_page()
        self._render_cover(pdf, session, len(images))

        # --- Seite 2: Inhaltsverzeichnis ---
        if toc_titles:
            pdf.add_page()
            self._render_toc(pdf, toc_titles)

        # --- Inhalt: Abschnitte ---
        pdf.add_page()
        for heading, text in sections:
            img = image_map.get(heading)
            self._render_section(pdf, heading, text, img)

        # --- Quellenverzeichnis ---
        self._render_source_list(pdf, session)

        # Speichern
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        pdf.output(output_path)
        logger.info(f"📄 PDF erstellt: {output_path} ({Path(output_path).stat().st_size // 1024} KB)")
        return output_path

    # ------------------------------------------------------------------
    # Render-Methoden
    # ------------------------------------------------------------------

    def _render_cover(self, pdf: ResearchPDF, session, image_count: int) -> None:
        """Titelseite mit dunkelblauem Header-Balken."""
        # Hintergrund-Balken (obere Hälfte)
        pdf.set_fill_color(*_COLOR_DARK_BLUE)
        pdf.rect(0, 0, 210, 120, "F")

        # Timus-Badge
        pdf.set_xy(0, 15)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_COLOR_GOLD)
        pdf.cell(210, 8, "TIMUS DEEP RESEARCH v6.0", align="C")

        # Titel
        pdf.set_xy(20, 35)
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(255, 255, 255)
        query_text = str(session.query)
        # Zeilenumbruch wenn nötig
        pdf.multi_cell(170, 10, query_text, align="C")

        # Datum
        pdf.set_xy(0, 90)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*_COLOR_GOLD)
        now = datetime.now().strftime("%d. %B %Y")
        pdf.cell(210, 8, now, align="C")

        # Trennlinie
        pdf.set_draw_color(*_COLOR_GOLD)
        pdf.line(40, 104, 170, 104)

        # Statistiken
        web_count = len(session.research_tree)
        yt_count = len([c for c in session.unverified_claims if c.get("source_type") == "youtube"])

        pdf.set_xy(0, 107)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(200, 220, 255)
        stats = f"{web_count} Web-Quellen"
        if yt_count:
            stats += f"  |  {yt_count} YouTube-Videos"
        if image_count:
            stats += f"  |  {image_count} Bilder"
        pdf.cell(210, 6, stats, align="C")

        # Unterer Bereich: weißes Emblem
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(*_COLOR_DARK_BLUE)
        pdf.set_xy(20, 140)
        pdf.set_font("Helvetica", "I", 11)
        pdf.set_text_color(*_COLOR_MID_GRAY)
        pdf.cell(170, 8, "Automatisch generierter Recherchebericht", align="C")

        pdf.set_xy(20, 152)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(170, 6, "Alle Informationen basieren auf öffentlich zugänglichen Quellen.", align="C")

        # Reset Farben
        pdf.set_text_color(*_COLOR_BLACK)

    def _render_toc(self, pdf: ResearchPDF, sections: List[str]) -> None:
        """Inhaltsverzeichnis."""
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*_COLOR_DARK_BLUE)
        pdf.cell(0, 10, "Inhaltsverzeichnis", ln=True)
        pdf.set_draw_color(*_COLOR_GOLD)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(6)

        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(*_COLOR_BLACK)
        for i, title in enumerate(sections, 1):
            pdf.cell(10, _LINE_HEIGHT, f"{i}.", ln=False)
            pdf.cell(0, _LINE_HEIGHT, title, ln=True)
            pdf.ln(1)

    def _render_section(
        self,
        pdf: ResearchPDF,
        heading: str,
        text: str,
        image: Optional["ImageResult"],
    ) -> None:
        """Rendert einen Abschnitt mit optionalem Bild."""
        # Heading
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*_COLOR_DARK_BLUE)
        pdf.ln(4)
        pdf.cell(0, 8, heading, ln=True)
        pdf.set_draw_color(*_COLOR_DARK_BLUE)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(3)
        pdf.set_text_color(*_COLOR_BLACK)

        # Bild (rechtsbündig, Text fließt links)
        img_placed = False
        if image and os.path.isfile(image.local_path):
            try:
                img_x = pdf.w - _MARGIN - _IMG_MAX_W
                img_y = pdf.get_y()
                pdf.image(image.local_path, x=img_x, y=img_y, w=_IMG_MAX_W)
                # Bildunterschrift
                caption_y = img_y + pdf.image_height(image.local_path, _IMG_MAX_W) + 1
                pdf.set_xy(img_x, caption_y)
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(*_COLOR_MID_GRAY)
                pdf.cell(_IMG_MAX_W, 4, image.caption[:60], align="C", ln=True)
                pdf.set_text_color(*_COLOR_BLACK)
                img_placed = True
            except Exception as e:
                logger.warning(f"Bild-Einbettung fehlgeschlagen: {e}")

        # Text
        text_width = (pdf.w - 2 * _MARGIN - _IMG_MAX_W - 5) if img_placed else (pdf.w - 2 * _MARGIN)
        pdf.set_font("Helvetica", "", 10)

        plain = self._markdown_to_plain(text)
        paragraphs = [p.strip() for p in plain.split("\n\n") if p.strip()]

        for para in paragraphs:
            pdf.set_x(pdf.l_margin)
            if img_placed and pdf.get_y() < (20 + _MARGIN + 80):  # noch im Bildbereich
                pdf.multi_cell(text_width, _LINE_HEIGHT, para)
            else:
                pdf.multi_cell(0, _LINE_HEIGHT, para)
            pdf.ln(2)

    def _render_source_list(self, pdf: ResearchPDF, session) -> None:
        """Quellenverzeichnis am Ende."""
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*_COLOR_DARK_BLUE)
        pdf.cell(0, 10, "Quellenverzeichnis", ln=True)
        pdf.set_draw_color(*_COLOR_GOLD)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(6)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_COLOR_BLACK)

        # Web-Quellen
        if session.research_tree:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, "Web-Quellen:", ln=True)
            pdf.set_font("Helvetica", "", 9)
            for i, node in enumerate(session.research_tree, 1):
                title = (node.title or "")[:60]
                url = (node.url or "")[:80]
                pdf.cell(8, 5, f"{i}.", ln=False)
                pdf.multi_cell(0, 5, f"{title}\n{url}")
                pdf.ln(1)

        # YouTube-Quellen
        yt_claims = [c for c in session.unverified_claims if c.get("source_type") == "youtube"]
        if yt_claims:
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, "YouTube-Quellen:", ln=True)
            pdf.set_font("Helvetica", "", 9)
            for i, c in enumerate(yt_claims, 1):
                title = c.get("source_title", c.get("video_id", ""))[:60]
                channel = c.get("channel", "")
                url = c.get("source", "")[:80]
                pdf.cell(8, 5, f"[YT{i}]", ln=False)
                pdf.multi_cell(0, 5, f"{title} | Kanal: {channel}\n{url}")
                pdf.ln(1)

    # ------------------------------------------------------------------
    # Hilfs-Methoden
    # ------------------------------------------------------------------

    def _parse_markdown(self, md: str) -> List[Tuple[str, str]]:
        """
        Zerlegt den Markdown-Text in (Heading, Content)-Paare.
        Erkennt ## als Abschnittsgrenzen.
        """
        sections: List[Tuple[str, str]] = []
        current_heading = "Einleitung"
        current_content: List[str] = []

        for line in md.splitlines():
            m = re.match(r"^##\s+(.+)$", line)
            if m:
                # Vorherigen Abschnitt speichern
                content = "\n\n".join(current_content).strip()
                if content:
                    sections.append((current_heading, content))
                current_heading = m.group(1).strip()
                current_content = []
            elif re.match(r"^#\s+", line):
                # H1 überspringen (Titel)
                continue
            else:
                current_content.append(line)

        # Letzten Abschnitt
        content = "\n\n".join(current_content).strip()
        if content and current_heading:
            sections.append((current_heading, content))

        return sections

    def _markdown_to_plain(self, text: str) -> str:
        """Konvertiert einfaches Markdown zu Plain-Text für fpdf2."""
        # Kursiv und Fett
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)
        # Links
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        # Bullet-Listen
        text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)
        # Nummerierte Listen
        text = re.sub(r"^\s*\d+\.\s+", "• ", text, flags=re.MULTILINE)
        # Code-Blöcke
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`(.+?)`", r"\1", text)
        # Mehrfache Leerzeilen normalisieren
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def image_height(self, path: str, width_mm: float) -> float:
        """Berechnet die Höhe eines Bildes bei gegebener Breite in mm."""
        try:
            from PIL import Image
            img = Image.open(path)
            w_px, h_px = img.size
            return width_mm * h_px / w_px
        except Exception:
            return 60.0  # Fallback

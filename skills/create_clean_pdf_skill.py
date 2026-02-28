"""
create_clean_pdf_skill.py — Playwright-basierter PDF-Generator (Goldstandard)

Pipeline: Markdown/HTML-Text → HTML mit CSS → Headless Chromium → sauberes PDF
Vorteile gegenüber WeasyPrint:
  * Echter Browser-Renderer: Tabellen, Code-Blöcke, Schriftarten pixelgenau
  * Seitenumbrüche automatisch und sauber
  * Kein Systemabhängigkeits-Chaos (WeasyPrint brauchte Cairo, Pango, etc.)
"""

import os
import asyncio
import markdown as md_lib
from typing import Dict, Any, Optional


# ---------------------------------------------------------------------------
# Standard-CSS für professionelle PDFs
# ---------------------------------------------------------------------------
DEFAULT_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.7;
    color: #1a1a2e;
    background: #ffffff;
    padding: 0;
}

.page-wrapper {
    max-width: 100%;
    padding: 2.5cm 2.8cm 2.5cm 2.8cm;
}

/* Überschriften */
h1 {
    font-size: 22pt;
    font-weight: 700;
    color: #0f3460;
    border-bottom: 3px solid #0f3460;
    padding-bottom: 8px;
    margin-top: 0;
    margin-bottom: 20px;
}
h2 {
    font-size: 15pt;
    font-weight: 600;
    color: #16213e;
    margin-top: 28px;
    margin-bottom: 10px;
    border-left: 4px solid #0f3460;
    padding-left: 10px;
}
h3 {
    font-size: 12pt;
    font-weight: 600;
    color: #1a1a2e;
    margin-top: 20px;
    margin-bottom: 8px;
}

/* Absätze */
p {
    margin-bottom: 10px;
    orphans: 3;
    widows: 3;
}

/* Links */
a {
    color: #0f3460;
    text-decoration: underline;
}

/* Listen */
ul, ol {
    margin: 8px 0 12px 24px;
}
li {
    margin-bottom: 4px;
}

/* Tabellen */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 10pt;
    page-break-inside: avoid;
}
th {
    background-color: #0f3460;
    color: #ffffff;
    font-weight: 600;
    padding: 8px 12px;
    text-align: left;
    border: 1px solid #0f3460;
}
td {
    padding: 7px 12px;
    border: 1px solid #dde2e8;
}
tr:nth-child(even) td {
    background-color: #f5f7fa;
}

/* Code */
code {
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New', monospace;
    font-size: 9.5pt;
    background: #f0f4f8;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 1px 5px;
}
pre {
    background: #1e1e2e;
    color: #cdd6f4;
    border-radius: 6px;
    padding: 14px 16px;
    margin: 12px 0;
    overflow-x: auto;
    page-break-inside: avoid;
}
pre code {
    background: none;
    border: none;
    color: inherit;
    padding: 0;
    font-size: 9pt;
}

/* Blockquote */
blockquote {
    border-left: 4px solid #0f3460;
    margin: 12px 0;
    padding: 8px 16px;
    background: #f0f4f8;
    color: #444;
    font-style: italic;
}

/* Horizontale Linie */
hr {
    border: none;
    border-top: 2px solid #e0e6ed;
    margin: 20px 0;
}

/* Fett / Kursiv */
strong { font-weight: 700; }
em { font-style: italic; }

/* Seitenumbruch-Kontrolle */
h1, h2 { page-break-after: avoid; }
pre, table, blockquote { page-break-inside: avoid; }

/* Kopfzeile / Fußzeile via CSS @page — wird von Chromium respektiert */
@page {
    margin: 0;
    size: A4;
}
"""


def _build_full_html(
    content_html: str,
    title: str,
    author: str,
    css_override: Optional[str],
) -> str:
    """Baut das vollständige HTML-Dokument zusammen."""
    css = css_override if css_override else DEFAULT_CSS
    # Kopfzeile & Fußzeile als echte HTML-Elemente (Playwright-kompatibel)
    header_html = f"""
    <div style="
        display: flex; justify-content: space-between; align-items: center;
        padding: 12px 2.8cm; font-size: 9pt; color: #888;
        border-bottom: 1px solid #e0e6ed; background: #fff;
    ">
        <span>{title}</span>
        <span>{author}</span>
    </div>
    """
    footer_html = """
    <div id="footer" style="
        display: flex; justify-content: center;
        padding: 8px 2.8cm; font-size: 9pt; color: #aaa;
        border-top: 1px solid #e0e6ed; background: #fff;
    ">
        <span class="pageNumber"></span> / <span class="totalPages"></span>
    </div>
    """

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{css}</style>
</head>
<body>
    <div class="page-wrapper">
        {content_html}
    </div>
</body>
</html>"""


def _markdown_to_html(text: str) -> str:
    """Wandelt Markdown in HTML um. Unterstützt Tabellen und Code-Blöcke."""
    return md_lib.markdown(
        text,
        extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"],
        extension_configs={
            "codehilite": {"css_class": "highlight", "guess_lang": True},
        },
    )


class CreateCleanPdfSkill:
    """
    Playwright-basierter PDF-Generator.

    Akzeptiert:
      * markdown_content (str) — Markdown-Text → wird intern zu HTML konvertiert
      * html_content     (str) — fertiges HTML (überschreibt markdown_content)
      * output_path      (str) — Ziel-Pfad für das PDF
      * title            (str) — Dokumenttitel (optional)
      * author           (str) — Autor (optional)
      * css_string       (str) — CSS-Override (optional, ersetzt DEFAULT_CSS)
    """

    parameters: Dict[str, Any] = {
        "markdown_content": {
            "type": "string",
            "description": "Markdown-Inhalt, wird automatisch zu HTML konvertiert.",
            "required": False,
        },
        "html_content": {
            "type": "string",
            "description": "Fertiges HTML (hat Vorrang vor markdown_content).",
            "required": False,
        },
        "output_path": {
            "type": "string",
            "description": "Ziel-Dateipfad für das erzeugte PDF.",
            "required": True,
        },
        "title": {
            "type": "string",
            "description": "Dokumenttitel (erscheint in Kopfzeile & Metadaten).",
            "required": False,
        },
        "author": {
            "type": "string",
            "description": "Autor (erscheint in Kopfzeile & Metadaten).",
            "required": False,
        },
        "css_string": {
            "type": "string",
            "description": "CSS-Override — ersetzt vollständig das Default-CSS.",
            "required": False,
        },
    }

    steps: list = [
        "validate_parameters",
        "convert_content",
        "render_pdf_playwright",
        "save_pdf",
    ]

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------
    def run(self, params: Dict[str, Any]) -> str:
        """Synchroner Einstiegspunkt — delegiert an async-Logik."""
        self._validate(params)
        return asyncio.run(self._run_async(params))

    async def run_async(self, params: Dict[str, Any]) -> str:
        """Async-Einstiegspunkt für bereits laufende Event-Loops."""
        self._validate(params)
        return await self._run_async(params)

    # ------------------------------------------------------------------
    # Intern
    # ------------------------------------------------------------------
    def _validate(self, params: Dict[str, Any]) -> None:
        if not params.get("output_path"):
            raise ValueError("'output_path' ist ein Pflichtparameter.")
        if not params.get("html_content") and not params.get("markdown_content"):
            raise ValueError("Entweder 'html_content' oder 'markdown_content' muss angegeben werden.")

    async def _run_async(self, params: Dict[str, Any]) -> str:
        output_path = params["output_path"]
        title = params.get("title", "Dokument")
        author = params.get("author", "Timus")
        css_override = params.get("css_string")

        # 1. Inhalt ermitteln (HTML hat Vorrang)
        if params.get("html_content"):
            content_html = params["html_content"]
        else:
            content_html = _markdown_to_html(params["markdown_content"])

        # 2. Vollständiges HTML-Dokument zusammenbauen
        full_html = _build_full_html(content_html, title, author, css_override)

        # 3. Zielverzeichnis anlegen
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # 4. Playwright: Headless Chromium → PDF
        await self._playwright_render(full_html, output_path, title, author)

        print(f"PDF erfolgreich erstellt: {output_path}")
        return output_path

    async def _playwright_render(
        self,
        html: str,
        output_path: str,
        title: str,
        author: str,
    ) -> None:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # HTML direkt laden (kein Webserver nötig)
            await page.set_content(html, wait_until="networkidle")

            # Warte auf Web-Fonts falls Google Fonts geladen werden können
            await page.wait_for_timeout(500)

            await page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
                margin={
                    "top": "0mm",
                    "bottom": "0mm",
                    "left": "0mm",
                    "right": "0mm",
                },
                display_header_footer=True,
                header_template=f"""
                    <div style="
                        width: 100%; font-size: 9pt; color: #888;
                        display: flex; justify-content: space-between;
                        padding: 10px 2.8cm; border-bottom: 1px solid #e0e6ed;
                        font-family: 'Inter', Arial, sans-serif;
                    ">
                        <span>{title}</span>
                        <span>{author}</span>
                    </div>
                """,
                footer_template="""
                    <div style="
                        width: 100%; font-size: 9pt; color: #aaa;
                        text-align: center; padding: 6px 2.8cm;
                        border-top: 1px solid #e0e6ed;
                        font-family: 'Inter', Arial, sans-serif;
                    ">
                        Seite <span class="pageNumber"></span> von <span class="totalPages"></span>
                    </div>
                """,
            )

            await browser.close()

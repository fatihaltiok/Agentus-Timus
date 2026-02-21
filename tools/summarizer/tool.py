# tools/summarizer/tool.py

import logging
import asyncio

from bs4 import BeautifulSoup

# V2 Tool Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

from utils.openai_compat import prepare_openai_params
# KORREKTUR: Wir importieren nicht mehr `browser_session_manager`, sondern nur noch die Helferfunktion.
from tools.shared_context import (
    openai_client,
    log
)
from tools.browser_tool.tool import ensure_browser_initialized

@tool(
    name="summarize_article",
    description="Fasst den Text der aktuell im Browser geoeffneten Seite zusammen.",
    parameters=[
        P("max_input_len", "integer", "Maximale Laenge des Eingabetexts in Zeichen", required=False, default=10000),
        P("sentences_count", "integer", "Anzahl der Saetze in der Zusammenfassung", required=False, default=5),
    ],
    capabilities=["document", "summarize"],
    category=C.DOCUMENT
)
async def summarize_article(max_input_len: int = 10000, sentences_count: int = 5) -> dict:
    """
    Fasst den Text der aktuell im Browser geöffneten Seite zusammen.
    """
    if not openai_client:
        raise Exception("OpenAI-Client nicht konfiguriert.")

    try:
        # `ensure_browser_initialized` ist jetzt die einzige Schnittstelle zum Browser.
        page = await ensure_browser_initialized()
    except RuntimeError as e_init:
        log.error(f"Fehler bei Browser-Initialisierung für Summarizer: {e_init}")
        raise Exception(f"Browser konnte nicht initialisiert werden: {e_init}")

    try:
        current_page_url = page.url
        log.info(f"Extrahiere Text von URL {current_page_url} für Zusammenfassung.")

        html_content = await page.content()
        soup = BeautifulSoup(html_content, "lxml")

        for selector in ["script", "style", "nav", "header", "footer", "aside", "form", "iframe", ".ad", "[class*='advert']", "[id*='advert']", "noscript", "[class*='cookie']", "[class*='banner']"]:
            for tag in soup.select(selector):
                tag.decompose()

        main_content_area = soup.find("article") or soup.find("main") or soup.body
        raw_text_content = main_content_area.get_text(" ", strip=True) if main_content_area else ""
        clean_text = ' '.join(raw_text_content.split())

        if not clean_text:
            raise Exception("Kein Text auf der Seite zum Zusammenfassen gefunden.")

        text_for_llm = clean_text[:max_input_len]

        prompt_text = f"Fasse den folgenden deutschen Text prägnant in etwa {sentences_count} Sätzen zusammen...\n\n---\n{text_for_llm}\n---\n\nZusammenfassung:"

        llm_response = await asyncio.to_thread(
            openai_client.chat.completions.create,
            model="gpt-4o",
            messages=[{"role": "system", "content": "Du bist ein Experte für präzise Textzusammenfassungen."}, {"role": "user", "content": prompt_text}],
            temperature=0.3, max_tokens=sentences_count * 50
        )

        summary_text = llm_response.choices[0].message.content.strip()

        return {"summary": summary_text, "url": current_page_url}

    except Exception as e:
        log.error(f"Fehler beim Zusammenfassen des Artikels: {e}", exc_info=True)
        raise Exception(f"Fehler beim Erstellen der Zusammenfassung: {e}")

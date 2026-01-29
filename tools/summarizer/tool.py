# tools/summarizer/tool.py

import logging
import asyncio
from typing import Union

from bs4 import BeautifulSoup
from jsonrpcserver import method, Success, Error

from tools.universal_tool_caller import register_tool
# KORREKTUR: Wir importieren nicht mehr `browser_session_manager`, sondern nur noch die Helferfunktion.
from tools.shared_context import (
from utils.openai_compat import prepare_openai_params
    openai_client,
    ensure_browser_initialized,
    log
)

@method
async def summarize_article(max_input_len: int = 10000, sentences_count: int = 5) -> Union[Success, Error]:
    """
    Fasst den Text der aktuell im Browser geöffneten Seite zusammen.
    """
    if not openai_client:
        return Error(code=-32003, message="OpenAI-Client nicht konfiguriert.")

    try:
        # `ensure_browser_initialized` ist jetzt die einzige Schnittstelle zum Browser.
        page = await ensure_browser_initialized()
    except RuntimeError as e_init:
        log.error(f"Fehler bei Browser-Initialisierung für Summarizer: {e_init}")
        return Error(code=-32001, message=f"Browser konnte nicht initialisiert werden: {e_init}")

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
            return Error(code=-32004, message="Kein Text auf der Seite zum Zusammenfassen gefunden.")

        text_for_llm = clean_text[:max_input_len]

        prompt_text = f"Fasse den folgenden deutschen Text prägnant in etwa {sentences_count} Sätzen zusammen...\n\n---\n{text_for_llm}\n---\n\nZusammenfassung:"
        
        llm_response = await asyncio.to_thread(
            openai_client.chat.completions.create,
            model="gpt-4o",
            messages=[{"role": "system", "content": "Du bist ein Experte für präzise Textzusammenfassungen."}, {"role": "user", "content": prompt_text}],
            temperature=0.3, max_tokens=sentences_count * 50
        )
        
        summary_text = llm_response.choices[0].message.content.strip()
        
        return Success({"summary": summary_text, "url": current_page_url})

    except Exception as e:
        log.error(f"Fehler beim Zusammenfassen des Artikels: {e}", exc_info=True)
        return Error(code=-32000, message=f"Fehler beim Erstellen der Zusammenfassung: {e}")

register_tool("summarize_article", summarize_article)
log.info("✅ Summarizer Tool (summarize_article) registriert.")
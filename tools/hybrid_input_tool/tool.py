"""
Hybrid Input Tool – Phase 1.1 + Phase 3.1

Strategie:
  1. DOM-First (Playwright Locator) – höchste Zuverlässigkeit
  2. activeElement-Check (Phase 3.1) – SPAs fokussieren Felder anders
  3. VISION_FALLBACK – Signal an den Aufrufer, Vision-Pipeline zu nutzen

Verwendung in browser_tool/tool.py:
    success, method = await hybrid_click_or_fill(page, selector=selector, value=text)
    if not success:
        # eigene Fallback-Logik
"""

from typing import Optional, Tuple
from playwright.async_api import Page
import logging

logger = logging.getLogger("hybrid_input_tool")

# Breites Locator-Set für alle gängigen Eingabefelder (kein expliziter Selector nötig)
_DEFAULT_INPUT_LOCATOR = (
    'input:not([type="hidden"]):not([type="file"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]), '
    'textarea, '
    '[contenteditable="true"], '
    '[role="textbox"], '
    '[role="searchbox"], '
    '[role="combobox"]'
)


async def hybrid_click_or_fill(
    page: Page,
    selector: Optional[str] = None,
    value: Optional[str] = None,
    timeout: int = 8000,
) -> Tuple[bool, str]:
    """
    DOM-First Klick oder Fill mit activeElement-Check für SPAs.

    Args:
        page:     Playwright Page-Objekt der aktiven Session.
        selector: CSS-Selector (optional). Ohne Selector → erstes sichtbares Eingabefeld.
        value:    Text zum Eintragen. None = nur klicken (kein Fill).
        timeout:  Timeout in ms für scroll_into_view und click.

    Returns:
        (True,  "DOM_SUCCESS")    – Aktion erfolgreich via DOM.
        (False, "VISION_FALLBACK") – DOM-Pfad fehlgeschlagen, Aufrufer soll Vision nutzen.
    """
    try:
        locator = page.locator(selector) if selector else page.locator(_DEFAULT_INPUT_LOCATOR)

        count = await locator.count()
        if count == 0:
            logger.debug("Kein DOM-Element gefunden → VISION_FALLBACK")
            return False, "VISION_FALLBACK"

        element = locator.first
        await element.scroll_into_view_if_needed(timeout=timeout)

        if value is not None:
            # Fokus setzen
            await element.click(timeout=timeout)

            # Phase 3.1: activeElement-Check — SPAs reagieren oft nicht auf fill()
            # direkt nach click(), prüfen ob das Feld wirklich den Fokus hat
            active_tag = await page.evaluate("() => document.activeElement.tagName.toUpperCase()")

            if active_tag in ("INPUT", "TEXTAREA"):
                # Keyboard.type() ist zuverlässiger als fill() bei React/Vue/Angular SPAs
                await page.keyboard.type(value, delay=30)
                logger.info(f"✅ DOM-TYPE (keyboard) [{active_tag}]: {value[:40]}...")
            else:
                # fill() für Standard-HTML-Formulare
                await element.fill(value)
                logger.info(f"✅ DOM-FILL [{active_tag}]: {value[:40]}...")
        else:
            await element.click(timeout=timeout)
            logger.info("✅ DOM-CLICK erfolgreich")

        return True, "DOM_SUCCESS"

    except Exception as exc:
        logger.debug(f"DOM-Pfad fehlgeschlagen (erwartet bei fehlenden Elementen): {exc}")

    logger.info("DOM nicht gefunden oder Fehler → VISION_FALLBACK")
    return False, "VISION_FALLBACK"

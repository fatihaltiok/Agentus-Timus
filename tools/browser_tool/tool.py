"""
Browser-Tool (Playwright) • Navigation + Smart Consent-Dismiss
--------------------------------------------------------------
Methoden:
  • open_url(url, session_id)
  • dismiss_overlays()
  • get_text()
  • list_links()
  • click_by_href(href)
  • click_by_text(text)
  • click_by_selector(selector)
  • get_page_content()
  • type_text(selector, text_to_type)

v2.0 NEU:
  • Session-Isolation via PersistentContextManager
  • Persistenter Cookie/LocalStorage State
  • Retry-Logik für Network-Fehler

Alle Rückgaben: dict (V2 Registry)
"""
# --- Standard-Bibliotheken ---
import logging
import time
import asyncio
import subprocess
from urllib.parse import urljoin
from typing import Optional, Any, Dict, List, Union
import json
import re

# --- Drittanbieter-Bibliotheken ---
from bs4 import BeautifulSoup
from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Page,
    BrowserContext,
    Browser as PlaywrightBrowser,
    Playwright
)

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# NEU: PersistentContextManager und RetryHandler
from .persistent_context import (
    PersistentContextManager,
    SessionContext,
    get_context_manager,
    set_context_manager
)
from .retry_handler import retry_handler, BrowserRetryHandler
from tools.hybrid_input_tool import hybrid_click_or_fill

# --- Globale Konfiguration & Logging ---
CONSENT_SELECTORS = [
    "button#onetrust-accept-btn-handler",
    "button[aria-label='Alle akzeptieren']",
    "button[aria-label='Accept all']",
    ".cmpboxbtnyes",
    ".fc-cta-consent",
    "[data-testid='cookie-banner-accept']",
    "button[data-accept-action='all']",
]

log = logging.getLogger("browser_tool")
if not log.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)-12s | %(message)s")


# =================================================================
# SESSION-MANAGEMENT (v2.0)
# =================================================================

async def ensure_browser_initialized(session_id: str = "default") -> Page:
    """
    Stellt sicher dass ein Browser-Context für die Session existiert.
    
    Nutzt PersistentContextManager für Session-Isolierung.
    
    Args:
        session_id: Eindeutige Session-ID für Context-Isolation
    
    Returns:
        Page-Objekt für die Session
    """
    import tools.shared_context as shared_context
    
    # Context Manager aus shared_context holen oder erstellen
    manager = shared_context.browser_context_manager
    if not manager:
        manager = PersistentContextManager()
        await manager.initialize()
        shared_context.browser_context_manager = manager
    
    # Context für Session holen/erstellen
    session = await manager.get_or_create_context(session_id)
    return session.page


async def save_session_state(session_id: str = "default") -> bool:
    """Speichert den State einer Session (Cookies, LocalStorage)."""
    import tools.shared_context as shared_context
    manager = shared_context.browser_context_manager
    if manager:
        return await manager.save_context_state(session_id)
    return False


async def close_session(session_id: str, save_state: bool = True) -> bool:
    """Schließt eine Browser-Session."""
    import tools.shared_context as shared_context
    manager = shared_context.browser_context_manager
    if manager:
        return await manager.close_context(session_id, save_state)
    return False


def _adaptive_timeout(host: str, default_ms: int = 30000) -> int:
    """Berechnet adaptives Timeout basierend auf Domain-Stats."""
    # Vereinfacht - in Zukunft mit Context Manager Stats
    return default_ms


# =================================================================
# LEGACY BROWSER SESSION (für Backward Compatibility)
# =================================================================

class BrowserSession:
    """
    Legacy Browser-Session für Backward Compatibility.
    
    Wird durch PersistentContextManager ersetzt.
    """
    def __init__(self):
        self.play: Optional[Playwright] = None
        self.browser_instance: Optional[PlaywrightBrowser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_initialized = False
        self.domain_stats: Dict[str, float] = {}
        self.max_frames = 10

    async def initialize(self):
        if self.is_initialized:
            return
        try:
            self.play = await async_playwright().start()
            try:
                self.browser_instance = await self.play.firefox.launch(headless=True)
            except PlaywrightTimeoutError as e:
                if "ENOENT" in str(e) or "no such file or directory" in str(e):
                    log.warning(f"Browser-Dateien nicht gefunden. Starte automatische Reparatur: 'playwright install firefox'")
                    process = await asyncio.create_subprocess_exec("playwright", "install", "firefox")
                    await process.wait()
                    if process.returncode == 0:
                        log.info("✅ Playwright-Installation erfolgreich. Versuche erneut, den Browser zu starten.")
                        self.browser_instance = await self.play.firefox.launch(headless=True)
                    else:
                        raise RuntimeError("Automatische Reparatur der Playwright-Installation fehlgeschlagen.")
                else:
                    raise e

            self.context = await self.browser_instance.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
                accept_downloads=False
            )
            self.page = await self.context.new_page()
            self.is_initialized = True
            log.info("✅ Playwright Browser-Session erfolgreich initialisiert.")
        except Exception as e:
            log.error(f"❌ Kritischer Fehler bei Initialisierung der Playwright-Session: {e}", exc_info=True)
            self.is_initialized = False
            raise RuntimeError(f"Playwright konnte nicht initialisiert werden: {e}")

    async def close(self):
        if self.context:
            try: await self.context.close()
            except Exception as e_ctx: log.debug(f"Fehler beim Schließen des Browser-Kontexts: {e_ctx}")
            self.context = None
        if self.browser_instance:
            try:
                await self.browser_instance.close()
            except Exception as e_brw:
                log.debug(f"Fehler beim Schließen der Browser-Instanz: {e_brw}")
            self.browser_instance = None
        if self.play:
            try:
                await self.play.stop()
            except Exception as e_play:
                log.debug(f"Fehler beim Stoppen von Playwright: {e_play}")
            self.play = None
        self.is_initialized = False
        self.page = None
        log.info("Playwright Browser-Session geschlossen.")


# Legacy global für Backward Compatibility
browser_session_manager = BrowserSession()

# --- Überarbeitete Tool-Methoden (v2.0 mit session_id) ---

@tool(
    name="open_url",
    description="Öffnet eine URL im Browser, behandelt Blocker und gibt klaren Status zurück.",
    parameters=[
        P("url", "string", "Die zu öffnende URL", required=True),
        P("session_id", "string", "Browser-Session ID für Context-Isolation", required=False, default="default"),
    ],
    capabilities=["browser", "navigation", "interaction"],
    category=C.BROWSER
)
async def open_url(url: str, session_id: str = "default") -> dict:
    """Öffnet eine URL, behandelt Blocker und gibt klaren Status zurück.
    
    Args:
        url: Die zu öffnende URL
        session_id: Session-ID für Context-Isolation (Cookies werden pro Session persistiert)
    """
    try:
        page = await ensure_browser_initialized(session_id)
    except RuntimeError as e_init:
        log.error(f"Kritischer Fehler bei Browser-Initialisierung: {e_init}", exc_info=True)
        raise Exception(f"Browser konnte nicht initialisiert werden: {e_init}")

    log.info(f"🌐 [{session_id}] Öffne URL: {url}")
    
    # Mit Retry-Handler ausführen
    async def _navigate():
        response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
        return response
    
    try:
        response = await retry_handler.execute_with_retry(_navigate)
        
        if isinstance(response, dict) and response.get("retries_exhausted"):
            return {"status": "failed_retry", "url": url, "error": response.get("error")}

        page_content = await page.content()
        if "Checking if the site connection is secure" in page_content or "DDoS protection by Cloudflare" in page_content:
            log.warning(f"Seite {url} wird durch Blocker geschützt.")
            return {"status": "blocked_by_security", "url": url, "title": await page.title(), "session_id": session_id}

        status = response.status if response else "unbekannt"
        title = await page.title()
        log.info(f"✅ [{session_id}] Seite '{title}' geladen mit Status {status}.")

        await dismiss_overlays(session_id=session_id)

        return {"status": "opened", "url": page.url, "title": title, "http_status": status, "session_id": session_id}

    except PlaywrightTimeoutError:
        log.error(f"Timeout beim Laden von {url}.")
        return {"status": "failed_timeout", "url": url, "message": "Seite konnte nicht innerhalb des Zeitlimits geladen werden.", "session_id": session_id}
    except Exception as e:
        log.error(f"Allgemeiner Fehler beim Öffnen von {url}: {e}", exc_info=True)
        raise Exception(f"Unerwarteter Browser-Fehler: {str(e)}")

@tool(
    name="dismiss_overlays",
    description="Schließt Cookie-Banner, Consent-Overlays und andere Popup-Elemente auf der aktuellen Seite.",
    parameters=[
        P("max_secs", "integer", "Maximale Dauer in Sekunden für das Schließen", required=False, default=5),
        P("session_id", "string", "Browser-Session ID", required=False, default="default"),
    ],
    capabilities=["browser", "navigation", "interaction"],
    category=C.BROWSER
)
async def dismiss_overlays(max_secs: int = 5, session_id: str = "default") -> dict:
    page = await ensure_browser_initialized(session_id)
    if not page:
        raise Exception("Seite nicht geladen oder Browser nicht initialisiert.")

    start_time = time.time()
    patterns = [
        "Alle akzeptieren", "Akzeptieren", "Alles akzeptieren", "Zustimmen und schließen",
        "Zustimmen", "Zustimmen & weiter", "Zustimmen & fortfahren", "Ich stimme zu",
        "Einverstanden", "Akzeptieren & schließen", "Verstanden", "Okay", "OK",
        "Accept All", "Accept all & continue", "Agree", "I agree", "Got it", "Allow all"
    ]
    found_interactions_count = 0
    clicked_buttons_count = 0
    removed_iframes_js_count = 0
    max_frames = 10

    async def try_page_interactions(target_element: Union[Page, Any]):
        nonlocal found_interactions_count, clicked_buttons_count
        if time.time() - start_time > max_secs: return True

        for sel in CONSENT_SELECTORS:
            if time.time() - start_time > max_secs: return True
            try:
                locators = target_element.locator(sel)
                count = await locators.count()
                for i in range(count):
                    if time.time() - start_time > max_secs: return True
                    try:
                        element_to_click = locators.nth(i)
                        if await element_to_click.is_visible(timeout=500) and await element_to_click.is_enabled(timeout=500):
                            await element_to_click.click(timeout=1000, force=True)
                            clicked_buttons_count += 1
                            log.debug(f"Button via CSS '{sel}' (Element {i+1}) geklickt.")
                            await asyncio.sleep(0.7)
                            return True
                    except Exception as e_click_css:
                        log.debug(f"Klick auf CSS '{sel}' (Element {i+1}) fehlgeschlagen: {str(e_click_css)[:100]}")
            except Exception as e_loc_css:
                 log.debug(f"Fehler beim Finden von Elementen für CSS '{sel}': {str(e_loc_css)[:100]}")

        for pat in patterns:
            if time.time() - start_time > max_secs: return True
            try:
                buttons = target_element.get_by_role("button", name=pat, exact=False)
                count = await buttons.count()
                if count > 0:
                    found_interactions_count += count
                    for i in range(count):
                        if time.time() - start_time > max_secs: return True
                        try:
                            button_to_click = buttons.nth(i)
                            if await button_to_click.is_visible(timeout=500) and await button_to_click.is_enabled(timeout=500):
                                await button_to_click.click(timeout=1500, force=True)
                                clicked_buttons_count += 1
                                log.debug(f"Button via Text '{pat}' (Element {i+1}) geklickt.")
                                await asyncio.sleep(0.7)
                                return True
                        except Exception as e_click_text:
                            log.debug(f"Klick auf Button mit Text '{pat}' (Element {i+1}) fehlgeschlagen: {str(e_click_text)[:100]}")
            except Exception as e_get_btn:
                log.debug(f"Fehler beim Suchen von Buttons mit Text '{pat}': {str(e_get_btn)[:100]}")

        try:
            # Prüfe auf sichtbaren Dialog, bevor ESC gesendet wird
            # Verwende einen allgemeineren Selektor für Dialoge
            dialog_locator = target_element.locator(':is(dialog, [role="dialog"], [aria-modal="true"]) >> visible=true').first
            if await dialog_locator.count() > 0: # Prüft, ob mindestens ein sichtbarer Dialog existiert
                log.debug("Sichtbarer Dialog gefunden, versuche ESC...")
                await target_element.keyboard.press("Escape")
                await asyncio.sleep(0.3)
        except Exception as e_esc_key:
            log.debug(f"Fehler bei ESC-Tastendruck oder Dialogprüfung: {str(e_esc_key)[:100]}")
        return False

    if await try_page_interactions(page):
        pass

    if clicked_buttons_count == 0 and time.time() - start_time <= max_secs:
        try:
            page_frames = page.frames
            sorted_page_frames = sorted(
                page_frames,
                key=lambda fr: ('cmp' in fr.name.lower() or 'consent' in fr.url.lower() or
                                'banner' in fr.name.lower() or 'google_ads' in fr.url.lower() or
                                'onetrust' in fr.url.lower() or 'sp_message' in fr.name.lower()),
                reverse=True
            )
            for i, current_frame in enumerate(sorted_page_frames[:max_frames]):
                if time.time() - start_time > max_secs: break
                log.debug(f"Prüfe Frame {i+1}/{len(sorted_page_frames[:max_frames])}: Name='{current_frame.name}', URL='{current_frame.url[:60]}...'")
                if await try_page_interactions(current_frame):
                    if clicked_buttons_count > 0:
                        log.info(f"Consent-Aktion in Frame '{current_frame.name}' erfolgreich.")
                        break
        except Exception as e_frame_iter:
            log.warning(f"Fehler beim Iterieren/Zugriff auf Frames: {e_frame_iter}")

    if clicked_buttons_count == 0 and time.time() - start_time <= max_secs :
        try:
            removed_iframes_js_count = await page.evaluate("""
                () => { /* ... JavaScript code ... */ }
            """) # JavaScript Code wie in vorheriger Version
            if removed_iframes_js_count > 0:
                log.info(f"{removed_iframes_js_count} potenzielle Overlays/iFrames via JavaScript entfernt.")
        except Exception as e_js_eval:
            log.warning(f"Fehler beim Entfernen von Elementen via JavaScript: {e_js_eval}")

    total_duration_secs = round(time.time() - start_time, 2)
    log.info(f"dismiss_overlays: {found_interactions_count} potenzielle Interaktionen, {clicked_buttons_count} Klicks, {removed_iframes_js_count} JS-Entfernungen. Dauer: {total_duration_secs}s")
    return {
        "found_potential_elements": found_interactions_count,
        "clicked_elements": clicked_buttons_count,
        "elements_removed_by_script": removed_iframes_js_count,
        "processing_duration_seconds": total_duration_secs
    }

@tool(
    name="get_text",
    description="Extrahiert den sichtbaren Textinhalt der aktuellen Seite (bereinigt von Scripts, Styles, Navigation etc.).",
    parameters=[],
    capabilities=["browser", "navigation", "interaction"],
    category=C.BROWSER
)
async def get_text() -> dict:
    page = await ensure_browser_initialized()
    if not page:
        raise Exception("Seite nicht geladen oder Browser nicht initialisiert.")

    try:
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "lxml")

        # KORREKTUR: Die Liste der Selektoren wird einer Variable zugewiesen
        unwanted_selectors = [
            "script", "style", "nav", "header", "footer", "aside", "form", "iframe",
            ".ad", "[class*='advert']", "[id*='advert']", "[class*='cookie']", "[class*='banner']",
            "noscript", "link", "meta"
        ]

        # KORREKTUR: Die for-Schleife iteriert über die definierte Liste
        for selector in unwanted_selectors:
            for tag in soup.select(selector):
                tag.decompose()

        # Der Rest der Logik ist jetzt korrekt eingerückt
        main_content_area = soup.find("article") or soup.find("main") or soup.find("div", role="main") or soup.body
        if not main_content_area:
            main_content_area = soup

        text_parts = []
        # Wir durchlaufen nur die direkten Kinder des Haupt-Content-Bereichs, um die Struktur zu erhalten
        for element in main_content_area.find_all(recursive=False):
            # Nutze .get_text() um den Text aus jedem Block zu holen
            block_text = element.get_text(separator=" ", strip=True)
            if block_text:
                text_parts.append(block_text)

        # Füge die Textblöcke mit doppelten Zeilenumbrüchen zusammen
        text_content = "\n\n".join(text_parts)
        # Entferne überflüssige Leerzeichen, aber behalte die Absätze
        text_content = ' '.join(text_content.split())

        max_text_length = 20000
        if len(text_content) > max_text_length:
            log.info(f"Seitentext auf {max_text_length} Zeichen gekürzt (Original: {len(text_content)}).")
            text_content = text_content[:max_text_length] + "..."

        return {"text": text_content, "length": len(text_content)}

    except Exception as e:
        log.error(f"Fehler beim Extrahieren von Text: {e}", exc_info=True)
        raise Exception(f"Fehler beim Extrahieren von Text: {str(e)}")

@tool(
    name="list_links",
    description="Listet alle relevanten Links auf der Seite auf, bewertet ihre Relevanz und filtert unwichtige Links heraus.",
    parameters=[],
    capabilities=["browser", "navigation", "interaction"],
    category=C.BROWSER
)
async def list_links() -> dict:
    """
    Listet alle relevanten Links auf der Seite auf, bewertet ihre Relevanz
    und filtert unwichtige Links heraus. Verwendet die moderne Playwright-API.
    """
    page = await ensure_browser_initialized()
    if not page:
        raise Exception("Seite nicht geladen.")

    try:
        # Schlüsselwörter für irrelevante Links (alles in Kleinbuchstaben)
        noise_keywords = [
            'anmelden', 'login', 'registrieren', 'sign in', 'register',
            'datenschutz', 'privacy', 'impressum', 'legal', 'agb', 'terms',
            'kontakt', 'contact', 'hilfe', 'help', 'faq', 'karriere', 'jobs',
            'warenkorb', 'cart', 'kasse', 'checkout', 'facebook', 'twitter',
            'instagram', 'linkedin', 'youtube', 'pinterest', 'rss'
        ]

        # Schlüsselwörter für "Action"-Links
        action_keywords = ['weiter', 'mehr', 'details', 'lesen', 'download', 'next', 'more', 'read']

        links_from_page = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href]').forEach((a, index) => {
                const href = a.getAttribute('href');
                if (href && !href.startsWith('javascript:') && !href.startsWith('#')) {
                    links.push({
                        href: a.href,
                        text: a.textContent.trim(),
                        depth: (() => { let d = 0; let e = a; while(e.parentElement) { d++; e = e.parentElement; } return d; })(),
                        in_nav_footer: !!a.closest('nav, header, footer, aside')
                    });
                }
            });
            return links;
        }""")

        found_links_data = []
        for i, link_data in enumerate(links_from_page):
            link_text_lower = link_data['text'].lower()

            # 1. Grundlegende Filterung
            if not link_data['text'] or any(keyword in link_text_lower for keyword in noise_keywords):
                continue

            # 2. Relevanz-Scoring
            score = 100
            # Links in Nav/Footer werden abgewertet
            if link_data['in_nav_footer']:
                score -= 40
            # Sehr "tiefe" Links (oft in verschachtelten Menüs) werden abgewertet
            if link_data['depth'] > 15:
                score -= 20
            # Kürzere, prägnantere Link-Texte sind oft relevanter
            if len(link_data['text']) < 5:
                score -= 10
            if len(link_data['text']) > 100: # Sehr lange Link-Texte sind oft ganze Sätze
                score -= 10

            # 3. "Action"-Links identifizieren
            is_action_link = any(keyword in link_text_lower for keyword in action_keywords)

            found_links_data.append({
                "idx": i,
                "text": link_data['text'][:150],
                "href": link_data['href'],
                "relevance": score,
                "is_action_link": is_action_link
            })

        # Sortiere die Links nach Relevanz (höchste zuerst)
        sorted_links = sorted(found_links_data, key=lambda x: x['relevance'], reverse=True)

        # Gib nur die Top 50 relevantesten Links zurück, um den Agenten nicht zu überfordern
        top_links = sorted_links[:50]

        log.info(f"{len(top_links)} relevante Links gefunden und nach Relevanz sortiert (von {len(links_from_page)} ursprünglich).")

        return {"links": top_links}

    except Exception as e:
        log.error(f"Fehler beim Auflisten der Links: {e}", exc_info=True)
        raise Exception(f"Fehler beim Auflisten der Links: {str(e)}")

# Ersetze die alten click-Funktionen in tools/browser_tool/tool.py

@tool(
    name="click_by_href",
    description="Klickt auf einen Link, der durch seine exakte URL (href) identifiziert wird. Dies ist die zuverlässigste Klick-Methode.",
    parameters=[
        P("href", "string", "Die exakte URL (href-Attribut) des zu klickenden Links", required=True),
    ],
    capabilities=["browser", "navigation", "interaction"],
    category=C.BROWSER
)
async def click_by_href(href: str) -> dict:
    """
    Klickt auf einen Link, der durch seine exakte URL (href) identifiziert wird.
    Dies ist die zuverlässigste Klick-Methode.
    Args:
        href (str): Die exakte URL (href-Attribut) des zu klickenden Links.
    """
    page = await ensure_browser_initialized()
    if not page:
        raise Exception("Seite nicht geladen.")

    log.info(f"Versuche Klick auf Link mit exaktem href: '{href}'")
    try:
        # Finde den Link über sein href-Attribut. Das ist eindeutig.
        link_locator = page.locator(f'a[href="{href}"]')
        count = await link_locator.count()
        if count == 0:
            raise Exception(f"Link mit href '{href}' nicht gefunden.")

        target_link = link_locator.first

        # Hole den Text nur für Logging-Zwecke
        link_text_content = (await target_link.text_content(timeout=1000) or "[Kein Text]").strip()
        log.info(f"Link gefunden: '{link_text_content[:60]}'. Führe Klick aus.")

        if not await target_link.is_visible(timeout=3000):
            await target_link.scroll_into_view_if_needed()

        # Erwarte Navigation und klicke
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=45000):
            await target_link.click(timeout=15000)

        new_url = page.url
        new_title = await page.title()
        log.info(f"Klick auf Link mit href '{href}' erfolgreich. Neue URL: {new_url}")
        return {
            "status": "clicked_by_href",
            "href_clicked": href,
            "new_url": new_url,
            "new_title": new_title
        }

    except PlaywrightTimeoutError as e:
        log.warning(f"Timeout beim Klick auf href '{href}' oder der nachfolgenden Navigation. Fehler: {e}")
        raise Exception(f"Timeout beim Klick auf Link mit href '{href}'.")
    except Exception as exc:
        log.error(f"Fehler beim Klick auf href '{href}': {exc}", exc_info=True)
        raise Exception(f"Allgemeiner Fehler beim Klick auf Link mit href '{href}': {str(exc)}")


# Ersetze den Block ab @method click_by_text bis zum Ende der Datei

@tool(
    name="click_by_text",
    description="Klickt auf ein interaktives Element (Link, Button etc.) basierend auf seinem sichtbaren Text.",
    parameters=[
        P("text", "string", "Der exakte oder ein Teil des Textes des Elements", required=True),
        P("exact", "boolean", "Ob der Text exakt übereinstimmen muss", required=False, default=False),
    ],
    capabilities=["browser", "navigation", "interaction"],
    category=C.BROWSER
)
async def click_by_text(text: str, exact: bool = False) -> dict:
    """
    Klickt auf ein interaktives Element (Link, Button etc.) basierend auf seinem sichtbaren Text.
    Args:
        text (str): Der exakte oder ein Teil des Textes des Elements.
        exact (bool): Ob der Text exakt übereinstimmen muss.
    """
    page = await ensure_browser_initialized()
    if not page:
        raise Exception("Seite nicht geladen.")

    log.info(f"Versuche Klick auf Element mit Text: '{text}' (exact={exact})")
    try:
        element_locator = page.get_by_text(text, exact=exact)

        count = await element_locator.count()
        if count == 0:
            raise Exception(f"Kein klickbares Element mit Text '{text}' gefunden.")

        target_element = None
        for i in range(count):
            candidate = element_locator.nth(i)
            if await candidate.is_visible(timeout=1000):
                target_element = candidate
                break

        if not target_element:
            raise Exception(f"Element mit Text '{text}' gefunden, aber keines davon ist sichtbar.")

        await target_element.scroll_into_view_if_needed(timeout=5000)

        log.info("Element gefunden, führe Klick aus...")

        await target_element.click(timeout=5000)

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            log.info(f"Klick auf '{text}' scheint eine Seiten-Aktion oder Navigation ausgelöst zu haben.")
        except PlaywrightTimeoutError:
            log.info(f"Klick auf '{text}' löste keine Änderung des Ladezustands aus.")

        new_url = page.url
        new_title = await page.title()

        return {
            "status": "clicked_by_text",
            "text_used": text,
            "current_url": new_url,
            "current_title": new_title,
            "message": f"Klick auf Element mit Text '{text}' wurde ausgeführt."
        }

    except Exception as exc:
        log.error(f"Fehler beim Klick auf Text '{text}': {exc}", exc_info=True)
        raise Exception(f"Allgemeiner Fehler beim Klick auf Text '{text}': {str(exc)}")

@tool(
    name="click_by_selector",
    description="Klickt auf ein Element via CSS-Selector (DOM-First Methode).",
    parameters=[
        P("selector", "string", "CSS-Selector (z.B. 'button.submit', '#login-btn', 'input[name=q]')", required=True),
    ],
    capabilities=["browser", "navigation", "interaction"],
    category=C.BROWSER
)
async def click_by_selector(selector: str) -> dict:
    """
    Klickt auf ein Element via CSS-Selector (DOM-First Methode).

    Args:
        selector: CSS-Selector (z.B. "button.submit", "#login-btn", "input[name='q']")

    Returns:
        dict mit Status-Informationen
    """
    try:
        log.info(f"🎯 Klicke auf Element via Selector: {selector}")

        if not browser_session_manager.is_initialized:
            await browser_session_manager.initialize()

        page = browser_session_manager.page

        # Element finden
        element = await page.query_selector(selector)
        if not element:
            raise Exception(f"Element mit Selector '{selector}' nicht gefunden.")

        # In Viewport scrollen
        await element.scroll_into_view_if_needed(timeout=5000)

        # Klicken
        await element.click(timeout=5000)

        # Warten auf DOM-Änderung
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            log.info(f"✅ Klick auf '{selector}' löste DOM-Änderung aus.")
        except PlaywrightTimeoutError:
            log.info(f"✅ Klick auf '{selector}' ohne DOM-Änderung.")

        return {
            "status": "clicked_by_selector",
            "selector": selector,
            "current_url": page.url,
            "current_title": await page.title(),
            "message": f"Element '{selector}' wurde geklickt."
        }

    except Exception as exc:
        log.error(f"❌ Fehler beim Klick auf Selector '{selector}': {exc}", exc_info=True)
        raise Exception(f"Fehler beim Klick: {str(exc)}")


@tool(
    name="get_page_content",
    description="Holt den kompletten HTML-Inhalt der aktuellen Seite (für DOM-Parsing).",
    parameters=[],
    capabilities=["browser", "navigation", "interaction"],
    category=C.BROWSER
)
async def get_page_content() -> dict:
    """
    Holt den kompletten HTML-Inhalt der aktuellen Seite (für DOM-Parsing).

    Returns:
        dict mit HTML-Content
    """
    try:
        log.info("📄 Hole Seiten-HTML für DOM-Parsing...")

        if not browser_session_manager.is_initialized:
            await browser_session_manager.initialize()

        page = browser_session_manager.page

        # HTML-Content holen
        html_content = await page.content()

        # URL und Title für Kontext
        url = page.url
        title = await page.title()

        return {
            "status": "page_content_retrieved",
            "html": html_content,
            "url": url,
            "title": title,
            "content_length": len(html_content),
            "message": f"HTML-Content ({len(html_content)} Zeichen) abgerufen."
        }

    except Exception as exc:
        log.error(f"❌ Fehler beim Abrufen des Seiten-Contents: {exc}", exc_info=True)
        raise Exception(f"Fehler beim Abrufen: {str(exc)}")


@tool(
    name="type_text",
    description="Gibt Text in ein Input-Element ein (via CSS-Selector).",
    parameters=[
        P("selector", "string", "CSS-Selector des Input-Elements (z.B. 'input[name=search]', '#email')", required=True),
        P("text_to_type", "string", "Text zum Eingeben", required=True),
    ],
    capabilities=["browser", "navigation", "interaction"],
    category=C.BROWSER
)
async def type_text(selector: str, text_to_type: str) -> dict:
    """
    Gibt Text in ein Input-Element ein.

    Strategie:
      1. hybrid_click_or_fill (DOM-First + activeElement-Check für SPAs)
      2. Legacy fill() als Fallback

    Args:
        selector: CSS-Selector des Input-Elements (z.B. "input[name='search']", "#email")
        text_to_type: Text zum Eingeben

    Returns:
        dict mit Status-Informationen
    """
    try:
        log.info(f"⌨️  Tippe Text in Element: {selector}")

        page = await ensure_browser_initialized()

        # 1. Hybrid Input (DOM-First + activeElement-Check)
        success, method = await hybrid_click_or_fill(
            page=page,
            selector=selector,
            value=text_to_type,
        )

        if success:
            log.info(f"✅ Text '{text_to_type[:40]}' via {method} eingegeben.")
            return {
                "status": "text_typed",
                "selector": selector,
                "text": text_to_type,
                "method": method,
                "current_url": page.url,
                "message": f"Text in Element '{selector}' eingegeben via {method}.",
            }

        # 2. Legacy-Fallback (direktes query_selector + fill)
        log.info(f"   hybrid_click_or_fill: VISION_FALLBACK → Legacy fill()")
        element = await page.query_selector(selector)
        if not element:
            raise Exception(f"Input-Element mit Selector '{selector}' nicht gefunden.")

        await element.scroll_into_view_if_needed(timeout=5000)
        await element.click()
        await element.fill(text_to_type)

        log.info(f"✅ Text '{text_to_type[:40]}' via LEGACY_FILL eingegeben.")
        return {
            "status": "text_typed",
            "selector": selector,
            "text": text_to_type,
            "method": "LEGACY_FILL",
            "current_url": page.url,
            "message": f"Text in Element '{selector}' eingegeben.",
        }

    except Exception as exc:
        log.error(f"❌ Fehler beim Tippen in '{selector}': {exc}", exc_info=True)
        raise Exception(f"Fehler beim Tippen: {str(exc)}")


async def shutdown_browser_tool():
    """Fährt die Playwright-Session sauber herunter."""
    if browser_session_manager.is_initialized:
        log.info("Fahre Browser-Tool herunter...")
        await browser_session_manager.close()


# =================================================================
# NEUE SESSION-MANAGEMENT TOOLS (v2.0)
# =================================================================

@tool(
    name="browser_session_status",
    description="Gibt Status aller aktiven Browser-Sessions zurück.",
    parameters=[],
    capabilities=["browser", "system"],
    category=C.BROWSER
)
async def browser_session_status() -> dict:
    """Gibt Status aller aktiven Browser-Sessions."""
    import tools.shared_context as shared_context
    
    manager = shared_context.browser_context_manager
    if not manager:
        return {
            "status": "not_initialized",
            "message": "PersistentContextManager nicht initialisiert"
        }
    
    manager_status = manager.get_status()
    return {
        "status": "ok",
        "manager_status": manager_status,
        "coordinate_context": manager_status.get("coordinate_context", {}),
    }


@tool(
    name="browser_save_session",
    description="Speichert den State einer Browser-Session (Cookies, LocalStorage).",
    parameters=[
        P("session_id", "string", "Session-ID zum Speichern", required=False, default="default"),
    ],
    capabilities=["browser", "system"],
    category=C.BROWSER
)
async def browser_save_session(session_id: str = "default") -> dict:
    """Speichert Session-State für spätere Wiederherstellung."""
    success = await save_session_state(session_id)
    
    if success:
        return {
            "status": "saved",
            "session_id": session_id,
            "message": f"Session '{session_id}' State gespeichert"
        }
    else:
        return {
            "status": "error",
            "session_id": session_id,
            "message": f"Session '{session_id}' nicht gefunden oder Save fehlgeschlagen"
        }


@tool(
    name="browser_close_session",
    description="Schließt eine Browser-Session und speichert optional den State.",
    parameters=[
        P("session_id", "string", "Session-ID zum Schließen", required=True),
        P("save_state", "boolean", "State vor dem Schließen speichern", required=False, default=True),
    ],
    capabilities=["browser", "system"],
    category=C.BROWSER
)
async def browser_close_session(session_id: str, save_state: bool = True) -> dict:
    """Schließt eine Browser-Session."""
    if session_id == "default":
        return {
            "status": "error",
            "message": "Default-Session kann nicht geschlossen werden"
        }
    
    success = await close_session(session_id, save_state)
    
    if success:
        return {
            "status": "closed",
            "session_id": session_id,
            "saved": save_state,
            "message": f"Session '{session_id}' geschlossen"
        }
    else:
        return {
            "status": "error",
            "session_id": session_id,
            "message": f"Session '{session_id}' nicht gefunden"
        }


@tool(
    name="browser_cleanup_expired",
    description="Räumt abgelaufene Browser-Sessions auf.",
    parameters=[],
    capabilities=["browser", "system"],
    category=C.BROWSER
)
async def browser_cleanup_expired() -> dict:
    """Entfernt abgelaufene Sessions (Timeout)."""
    import tools.shared_context as shared_context
    
    manager = shared_context.browser_context_manager
    if not manager:
        return {"status": "error", "message": "Manager nicht initialisiert"}
    
    count = await manager.cleanup_expired()
    
    return {
        "status": "ok",
        "sessions_removed": count,
        "message": f"{count} abgelaufene Sessions entfernt"
    }


if __name__ == '__main__':
    async def main_test():
        try:
            pass
        finally:
            await shutdown_browser_tool()
    asyncio.run(main_test())

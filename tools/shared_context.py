# tools/shared_context.py

import logging
import asyncio
import subprocess
from typing import Optional, List, Dict

# Wir importieren die Typen und die Kern-Playwright-Funktion auf oberster Ebene
from openai import OpenAI
import chromadb.types
from playwright.async_api import Page, Playwright, Browser, BrowserContext, async_playwright

# =================================================================
# PASSIVER CONTAINER FÜR GETEILTE RESSOURCEN
# =================================================================
# Diese Datei definiert nur die "Behälter" für die globalen Objekte.
# Die Initialisierung und Befüllung dieser Variablen erfolgt AUSSCHLIESSLICH
# im `startup_event` des `mcp_server.py`.
# =================================================================

# --- Geteilte API-Clients ---
openai_client: Optional[OpenAI] = None
inception_client: Optional[OpenAI] = None
# `easyocr_reader` wurde entfernt, da wir jetzt die Hugging Face Engine verwenden.

# --- Geteilte Datenbank-Verbindung ---
memory_collection: Optional[chromadb.types.Collection] = None

# --- Geteilte Browser-Session ---
browser_session: Dict = {
    "play": None,
    "browser_instance": None,
    "context": None,
    "page": None,
    "is_initialized": False,
}

# --- Geteilte Konstanten ---
CONSENT_SELECTORS: List[str] = [
    "button#onetrust-accept-btn-handler", "button[aria-label='Alle akzeptieren']",
    "button[aria-label='Accept all']", ".cmpboxbtnyes", ".fc-cta-consent",
    "[data-testid='cookie-banner-accept']", "button[data-accept-action='all']",
]

# --- Geteilte Engines ---
# Segmentation Engine für visuelle UI-Element-Erkennung
try:
    from tools.engines.segmentation_engine import segmentation_engine_instance
except ImportError:
    segmentation_engine_instance = None

# Object Detection Engine für einfachere UI-Element-Erkennung
try:
    from tools.engines.object_detection_engine import object_detection_engine_instance
except ImportError:
    object_detection_engine_instance = None

# --- Globaler Logger ---
# Der Logger wird im mcp_server konfiguriert. Hier wird nur der Zugriffspunkt definiert.
log = logging.getLogger("timus.context")

# =================================================================
# BROWSER HELPER FUNKTIONEN
# =================================================================

async def ensure_browser_initialized() -> Page:
    """
    Stellt sicher, dass die globale Browser-Session initialisiert ist
    und gibt die aktive Page zurück. Führt bei Bedarf die Initialisierung durch.
    """
    if browser_session["is_initialized"] and browser_session["page"] and not browser_session["page"].is_closed():
        return browser_session["page"]

    log.info("Initialisiere oder überprüfe Playwright Browser-Session...")

    try:
        browser_session["play"] = await async_playwright().start()
        
        try:
            browser_session["browser_instance"] = await browser_session["play"].firefox.launch(headless=True)
        except Exception as e:
            if "ENOENT" in str(e) or "no such file or directory" in str(e):
                log.warning("Browser-Dateien nicht gefunden. Starte automatische Reparatur: 'playwright install firefox'")
                process = await asyncio.create_subprocess_exec("playwright", "install", "firefox")
                await process.wait()
                if process.returncode == 0:
                    log.info("✅ Playwright-Reparatur erfolgreich. Versuche Browser-Start erneut.")
                    browser_session["browser_instance"] = await browser_session["play"].firefox.launch(headless=True)
                else:
                    raise RuntimeError("Automatische Playwright-Reparatur fehlgeschlagen.")
            else:
                raise e

        context = await browser_session["browser_instance"].new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
            accept_downloads=False
        )
        browser_session["context"] = context
        browser_session["page"] = await context.new_page()
        browser_session["is_initialized"] = True
        
        log.info("✅ Playwright Browser-Session erfolgreich initialisiert.")
        
        if not browser_session["page"]:
            raise RuntimeError("Browser-Seite konnte nicht erstellt werden.")
            
        return browser_session["page"]

    except Exception as e:
        log.error(f"❌ Kritischer Fehler bei Browser-Initialisierung: {e}", exc_info=True)
        browser_session["is_initialized"] = False
        raise RuntimeError(f"Playwright konnte nicht initialisiert werden: {e}")

# KORREKTUR: Der `ocr_engine_instance`-Import gehört hier nicht hin.
# Jedes Modul, das eine Engine benötigt, sollte sie direkt importieren.
# Das vermeidet zyklische Abhängigkeiten.
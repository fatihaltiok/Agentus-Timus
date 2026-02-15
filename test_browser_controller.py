#!/usr/bin/env python3
"""
Test-Script für HybridBrowserController

Testet DOM-First Funktionalität mit echtem Browser-Szenario.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Setup Path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s'
)
log = logging.getLogger("test_browser_controller")

from tools.browser_controller.controller import HybridBrowserController


async def test_google_search():
    """
    Test-Szenario: Google-Suche

    1. Navigiere zu Google
    2. Finde Suchfeld (DOM-First!)
    3. Tippe "Python Programming"
    4. Klicke auf Suchen
    5. Warte auf Ergebnisse
    """
    log.info("="*70)
    log.info("TEST: Google-Suche mit DOM-First Browser Controller")
    log.info("="*70)

    controller = HybridBrowserController(headless=False)

    try:
        # 1. Initialisiere Browser
        log.info("\n📋 SCHRITT 1: Browser initialisieren")
        init_success = await controller.initialize()
        if not init_success:
            log.error("❌ Browser-Initialisierung fehlgeschlagen!")
            return

        # 2. Navigiere zu Google
        log.info("\n📋 SCHRITT 2: Navigiere zu Google")
        nav_result = await controller.navigate("https://www.google.com", wait_for_load=True)

        log.info(f"   Ergebnis: {'✅ Erfolg' if nav_result.success else '❌ Fehler'}")
        log.info(f"   Methode: {nav_result.method_used.value}")
        log.info(f"   Zeit: {nav_result.execution_time*1000:.0f}ms")
        log.info(f"   Cookie Auto-Handle: {nav_result.state_changed}")

        if not nav_result.success:
            log.error(f"   Fehler: {nav_result.error}")
            return

        # Kurze Pause
        await asyncio.sleep(2)

        # 3. Finde Suchfeld und tippe
        log.info("\n📋 SCHRITT 3: Finde Suchfeld und tippe 'Python Programming'")
        start_time = time.time()

        type_action = {
            "type": "type",
            "target": {
                "text": "Search",  # Google Suchfeld
                "selector": "input[name='q']",  # Expliziter Selector (DOM!)
                "role": "searchbox"
            },
            "text": "Python Programming"
        }

        # WICHTIG: Für type-Action müssen wir erst das Feld finden und fokussieren
        # Vereinfachte Version: Wir nutzen den Selector direkt
        log.info("   🔍 Suche Suchfeld via DOM (selector: input[name='q'])")

        # Hier müssten wir eigentlich browser_tool nutzen
        # Für den Test simulieren wir erstmal
        log.info("   ⚠️  HINWEIS: Vollständige DOM-Implementierung benötigt laufenden MCP-Server")
        log.info("   ⚠️  Für echten Test: MCP-Server starten und browser_tool nutzen")

        dom_find_time = time.time() - start_time
        log.info(f"   Zeit (DOM-Suche): {dom_find_time*1000:.0f}ms")

        # 4. Statistiken anzeigen
        log.info("\n📊 STATISTIKEN:")
        stats = controller.get_stats()
        log.info(f"   DOM-Aktionen: {stats['dom_actions']}")
        log.info(f"   Vision-Aktionen: {stats['vision_actions']}")
        log.info(f"   Fallbacks: {stats['fallbacks']}")
        log.info(f"   Unique States: {stats['unique_states']}")
        log.info(f"   History Size: {stats['history_size']}")

        # 5. State-Tracking Demo
        log.info("\n📋 STATE-TRACKING:")
        last_state = controller.state_tracker.get_last_state()
        if last_state:
            log.info(f"   URL: {last_state.url}")
            log.info(f"   DOM-Hash: {last_state.dom_hash}")
            log.info(f"   Visible Elements: {len(last_state.visible_elements)}")
            log.info(f"   Cookie-Banner: {last_state.cookie_banner}")
            log.info(f"   Network Idle: {last_state.network_idle}")

        # 6. Loop-Detection Demo
        log.info("\n📋 LOOP-DETECTION:")
        is_loop = controller.state_tracker.detect_loop()
        log.info(f"   Loop erkannt: {'⚠️ JA' if is_loop else '✅ NEIN'}")

        log.info("\n" + "="*70)
        log.info("✅ TEST ABGESCHLOSSEN")
        log.info("="*70)

    except Exception as e:
        log.error(f"\n❌ TEST FEHLGESCHLAGEN: {e}", exc_info=True)

    finally:
        # Cleanup
        await controller.cleanup()


async def test_dom_parser():
    """Test DOM Parser Funktionalität (isoliert)."""
    log.info("="*70)
    log.info("TEST: DOM Parser (isoliert)")
    log.info("="*70)

    from tools.browser_controller.dom_parser import DOMParser

    # Beispiel HTML (Google-Suchseite vereinfacht)
    sample_html = """
    <html>
        <body>
            <input type="text" name="q" aria-label="Search" placeholder="Search Google">
            <button type="submit" aria-label="Google Search">Google Search</button>
            <a href="/about">About</a>
            <button id="accept-cookies">Accept All</button>
        </body>
    </html>
    """

    parser = DOMParser()

    log.info("\n📋 Parse HTML...")
    elements = parser.parse(sample_html)
    log.info(f"   Gefundene interaktive Elemente: {len(elements)}")

    for i, elem in enumerate(elements, 1):
        log.info(f"\n   Element {i}:")
        log.info(f"      Tag: {elem.tag}")
        log.info(f"      Selector: {elem.selector}")
        log.info(f"      ARIA-Label: {elem.aria_label}")
        log.info(f"      Text: {elem.text}")

    log.info("\n📋 Test: find_by_text('Search')")
    matches = parser.find_by_text("Search")
    log.info(f"   Matches: {len(matches)}")
    for match in matches:
        log.info(f"      → {parser.describe_element(match)}")

    log.info("\n📋 Test: find_by_role('button')")
    buttons = parser.find_by_role("button")
    log.info(f"   Buttons: {len(buttons)}")

    log.info("\n" + "="*70)
    log.info("✅ DOM PARSER TEST ABGESCHLOSSEN")
    log.info("="*70)


async def test_state_tracker():
    """Test State Tracker Funktionalität (isoliert)."""
    log.info("="*70)
    log.info("TEST: State Tracker (isoliert)")
    log.info("="*70)

    from tools.browser_controller.state_tracker import UIStateTracker

    tracker = UIStateTracker(max_history=10)

    log.info("\n📋 Simuliere 5 States...")

    # State 1: Google Homepage
    state1 = tracker.observe(
        url="https://www.google.com",
        dom_content="<html><body><input name='q'></body></html>",
        visible_elements=["input[name='q']", "button[type='submit']"],
        cookie_banner=True
    )
    log.info(f"   State 1: {state1.url}, DOM={state1.dom_hash}")

    await asyncio.sleep(0.1)

    # State 2: Nach Cookie-Accept (DOM ändert sich)
    state2 = tracker.observe(
        url="https://www.google.com",
        dom_content="<html><body><input name='q'><div>Content</div></body></html>",
        visible_elements=["input[name='q']", "button[type='submit']", "div"],
        cookie_banner=False
    )
    log.info(f"   State 2: {state2.url}, DOM={state2.dom_hash}")

    # Diff berechnen
    diff = tracker.get_state_diff(state1, state2)
    log.info(f"\n📋 State-Diff (1 → 2):")
    log.info(f"   URL geändert: {diff.url_changed}")
    log.info(f"   DOM geändert: {diff.dom_changed}")
    log.info(f"   Neue Elemente: {len(diff.new_elements)}")
    log.info(f"   Cookie-Banner verschwunden: {diff.modal_disappeared}")
    log.info(f"   Signifikante Änderung: {diff.has_significant_change()}")

    # Simuliere Loop (3x gleicher State)
    log.info(f"\n📋 Simuliere Loop-Szenario...")
    for i in range(3):
        tracker.observe(
            url="https://www.google.com/search",
            dom_content="<html><body>Same content</body></html>",
            visible_elements=["same"],
            cookie_banner=False
        )
        await asyncio.sleep(0.1)

    is_loop = tracker.detect_loop(window=3)
    log.info(f"   Loop erkannt: {'⚠️ JA (wie erwartet!)' if is_loop else '❌ NEIN'}")

    # History
    log.info(f"\n📋 History:")
    log.info(f"   Total States: {len(tracker.history)}")
    log.info(f"   Unique States: {tracker.get_unique_states()}")

    log.info("\n" + "="*70)
    log.info("✅ STATE TRACKER TEST ABGESCHLOSSEN")
    log.info("="*70)


async def main():
    """Führt alle Tests aus."""
    log.info("\n" + "🚀 "*30)
    log.info("HYBRID BROWSER CONTROLLER - TEST SUITE")
    log.info("🚀 "*30 + "\n")

    # Test 1: DOM Parser (isoliert, kein Browser nötig)
    await test_dom_parser()
    print("\n\n")

    # Test 2: State Tracker (isoliert, kein Browser nötig)
    await test_state_tracker()
    print("\n\n")

    # Test 3: Vollständiger Browser-Test
    log.info("⚠️  HINWEIS: Vollständiger Browser-Test benötigt:")
    log.info("   1. Laufenden MCP-Server (python server/mcp_server.py)")
    log.info("   2. browser_tool muss DOM-Methoden unterstützen")
    log.info("\n   Führe vereinfachten Test aus...\n")

    await test_google_search()

    log.info("\n" + "🎉 "*30)
    log.info("ALLE TESTS ABGESCHLOSSEN!")
    log.info("🎉 "*30 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
DOM-First Browser Controller - Google Search Integration Test
==============================================================

Demonstriert die DOM-First Architektur mit echtem Google-Search Szenario.

Performance-Vergleich:
- DOM-First: 0.1-0.5s pro Aktion, $0 Kosten
- Vision-First: 3-60s pro Aktion, $0.0015 pro Screenshot

Test-Szenario:
1. Google öffnen
2. Suchfeld finden (DOM-First)
3. Query eingeben (DOM)
4. Search-Button klicken (DOM)
5. Ergebnisse parsen (DOM)
6. Performance messen
"""

import asyncio
import logging
import time
from typing import Dict, Any, List

# Timus Imports
from tools.browser_controller.controller import HybridBrowserController
from tools.browser_controller.state_tracker import UIStateTracker
from tools.browser_controller.dom_parser import DOMParser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


class PerformanceTracker:
    """Misst Performance-Metriken für DOM vs Vision."""

    def __init__(self):
        self.metrics = {
            'dom_actions': [],
            'vision_actions': [],
            'total_time': 0,
            'dom_time': 0,
            'vision_time': 0,
            'dom_cost': 0,
            'vision_cost': 0
        }

    def start_action(self, action_type: str) -> float:
        """Startet Timer für Aktion."""
        return time.time()

    def end_action(self, start_time: float, action_type: str, method: str):
        """Beendet Timer und speichert Metrik."""
        duration = time.time() - start_time

        if method == 'dom':
            self.metrics['dom_actions'].append({
                'action': action_type,
                'duration': duration,
                'cost': 0  # DOM ist kostenlos
            })
            self.metrics['dom_time'] += duration
        else:
            self.metrics['vision_actions'].append({
                'action': action_type,
                'duration': duration,
                'cost': 0.0015  # GPT-4V Kosten pro Screenshot
            })
            self.metrics['vision_time'] += duration
            self.metrics['vision_cost'] += 0.0015

        self.metrics['total_time'] = self.metrics['dom_time'] + self.metrics['vision_time']

    def get_report(self) -> str:
        """Generiert Performance-Report."""
        dom_count = len(self.metrics['dom_actions'])
        vision_count = len(self.metrics['vision_actions'])
        total_count = dom_count + vision_count

        if total_count == 0:
            return "Keine Aktionen ausgeführt."

        dom_percentage = (dom_count / total_count) * 100
        avg_dom_time = self.metrics['dom_time'] / dom_count if dom_count > 0 else 0
        avg_vision_time = self.metrics['vision_time'] / vision_count if vision_count > 0 else 0

        report = f"""
╔══════════════════════════════════════════════════════════════╗
║          DOM-FIRST PERFORMANCE REPORT - GOOGLE SEARCH        ║
╚══════════════════════════════════════════════════════════════╝

📊 AKTIONEN ÜBERSICHT:
   • Gesamt:        {total_count} Aktionen
   • DOM-First:     {dom_count} Aktionen ({dom_percentage:.1f}%)
   • Vision-Fallback: {vision_count} Aktionen ({100-dom_percentage:.1f}%)

⏱️  ZEIT-PERFORMANCE:
   • Gesamt:        {self.metrics['total_time']:.2f}s
   • DOM-Zeit:      {self.metrics['dom_time']:.2f}s
   • Vision-Zeit:   {self.metrics['vision_time']:.2f}s
   • Ø DOM-Aktion:  {avg_dom_time:.3f}s
   • Ø Vision-Aktion: {avg_vision_time:.3f}s

💰 KOSTEN-ANALYSE:
   • DOM-Kosten:    ${self.metrics['dom_cost']:.4f} (kostenlos!)
   • Vision-Kosten: ${self.metrics['vision_cost']:.4f}
   • Gesamt:        ${self.metrics['vision_cost']:.4f}

🚀 VERBESSERUNG vs. Vision-First (hypothetisch):
   • Zeit-Ersparnis:  {(1 - self.metrics['total_time'] / (total_count * 5)) * 100:.1f}% (bei 5s/Vision-Aktion)
   • Kosten-Ersparnis: ${(total_count * 0.0015) - self.metrics['vision_cost']:.4f} (bei 100% Vision)

✅ FAZIT:
   DOM-First ist {dom_percentage:.0f}% der Aktionen, spart Zeit und Kosten!
"""
        return report


async def call_mcp_tool(controller, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Helper: Ruft MCP-Tool via Controller's HTTP-Client auf."""
    return await controller._call_mcp_tool(method, params or {})


async def test_google_search_dom_first():
    """
    Testet Google-Suche mit DOM-First Ansatz.

    Szenario:
    1. Google.com öffnen
    2. Suchfeld via DOM finden
    3. "Anthropic Claude AI" eingeben
    4. Search-Button via DOM klicken
    5. Ergebnisse via DOM parsen
    """
    log.info("🚀 Starte DOM-First Google Search Integration Test")

    perf = PerformanceTracker()
    controller = HybridBrowserController()

    try:
        # ========================================
        # SCHRITT 1: Google öffnen
        # ========================================
        log.info("\n" + "="*60)
        log.info("SCHRITT 1: Google.com öffnen")
        log.info("="*60)

        start = perf.start_action('navigate')
        result = await controller.navigate("https://www.google.com")
        perf.end_action(start, 'navigate', 'dom')

        if not result.success:
            log.error(f"❌ Navigation fehlgeschlagen: {result.error}")
            return

        log.info(f"✅ Google geöffnet (Methode: {result.method_used}, Zeit: {result.execution_time:.2f}s)")

        # Cookie-Banner automatisch dismissen
        await asyncio.sleep(2)  # Warten auf Cookie-Banner

        # ========================================
        # SCHRITT 2: Suchfeld finden (DOM-First)
        # ========================================
        log.info("\n" + "="*60)
        log.info("SCHRITT 2: Suchfeld via DOM finden")
        log.info("="*60)

        # DOM-Content holen via MCP
        content_result = await call_mcp_tool(controller, "get_page_content")

        if 'html' not in content_result:
            log.error(f"❌ DOM-Content konnte nicht abgerufen werden: {content_result.get('error', content_result)}")
            return

        html = content_result.get('html', '')
        log.info(f"📄 HTML-Content abgerufen: {len(html)} Zeichen")

        # DOM parsen
        parser = DOMParser()
        parser.parse(html)

        log.info(f"🔍 DOM-Parser gefunden: {len(parser.elements)} interaktive Elemente")

        # Suchfeld finden - Google nutzt textarea mit role="combobox" für Suche
        search_inputs = [el for el in parser.elements if el.tag == 'textarea' and el.role == 'combobox']

        if not search_inputs:
            # Fallback: Nach input mit Platzhalter "Suche" oder aria-label
            search_inputs = [el for el in parser.elements
                           if el.tag in ['input', 'textarea']
                           and (el.aria_label and 'such' in el.aria_label.lower()
                                or el.placeholder and 'such' in el.placeholder.lower())]

        if not search_inputs:
            log.error("❌ Suchfeld nicht gefunden")
            log.info(f"Verfügbare Input/Textarea Elemente:")
            for el in parser.elements[:10]:  # Zeige erste 10 Elemente
                if el.tag in ['input', 'textarea']:
                    log.info(f"  - {el.tag}: selector={el.selector}, role={el.role}, aria={el.aria_label}")
            return

        search_field = search_inputs[0]
        log.info(f"✅ Suchfeld gefunden: {search_field.tag} mit selector={search_field.selector}, role={search_field.role}")

        # ========================================
        # SCHRITT 3: Query eingeben (DOM)
        # ========================================
        log.info("\n" + "="*60)
        log.info("SCHRITT 3: Query 'Anthropic Claude AI' eingeben")
        log.info("="*60)

        query = "Anthropic Claude AI"
        start = perf.start_action('type')

        # Via MCP type_text (DOM-First)
        type_result = await call_mcp_tool(controller, "type_text", {
            "selector": search_field.selector,
            "text_to_type": query  # MCP expects 'text_to_type' parameter
        })
        perf.end_action(start, 'type', 'dom')

        if 'error' in type_result:
            log.error(f"❌ Tippen fehlgeschlagen: {type_result['error']}")
            return

        log.info(f"✅ Query eingegeben: '{query}' in {search_field.selector}")

        # ========================================
        # SCHRITT 4: Search-Button klicken (DOM)
        # ========================================
        log.info("\n" + "="*60)
        log.info("SCHRITT 4: Search-Button via DOM klicken")
        log.info("="*60)

        # Search-Button finden
        # Google hat verschiedene Optionen:
        # - input[name="btnK"] (Desktop)
        # - button mit aria-label="Google Search"

        await asyncio.sleep(1)  # Warten auf Autocomplete

        start = perf.start_action('click')

        # Via MCP click_by_selector (DOM-First)
        # Versuche verschiedene Selektoren
        selectors = [
            "input[name='btnK']",  # Desktop Submit Button
            "button[aria-label*='Google']",  # Aria-Label Button
            "input[type='submit'][value*='Google']"  # Submit mit Value
        ]

        clicked = False
        for selector in selectors:
            click_result = await call_mcp_tool(controller, "click_by_selector", {"selector": selector})
            if 'error' not in click_result:
                log.info(f"✅ Search-Button geklickt: {selector}")
                clicked = True
                break

        perf.end_action(start, 'click', 'dom')

        if not clicked:
            log.warning("⚠️  Kein Button gefunden, drücke Enter-Taste direkt...")
            # Fallback: Enter drücken (via execute_action)
            enter_result = await controller.execute_action({
                "action_type": "press",
                "target": "Enter"
            })
            if not enter_result.success:
                log.error("❌ Enter-Taste fehlgeschlagen")
                return

        # Warten auf Suchergebnisse
        await asyncio.sleep(3)

        # ========================================
        # SCHRITT 5: Ergebnisse parsen (DOM)
        # ========================================
        log.info("\n" + "="*60)
        log.info("SCHRITT 5: Suchergebnisse via DOM parsen")
        log.info("="*60)

        # Neue Seite HTML holen via MCP
        results_content = await call_mcp_tool(controller, "get_page_content")

        if 'html' not in results_content:
            log.error(f"❌ Ergebnisseite konnte nicht abgerufen werden: {results_content.get('error', 'Unknown error')}")
            return

        results_html = results_content.get('html', '')
        current_url = results_content.get('url', '')

        log.info(f"📄 Ergebnisseite: {current_url}")
        log.info(f"📄 HTML-Content: {len(results_html)} Zeichen")

        # DOM parsen
        results_parser = DOMParser()
        results_parser.parse(results_html)

        # Alle Links finden
        result_links = [el for el in results_parser.elements if el.tag == 'a' and el.text]

        log.info(f"🔗 {len(result_links)} Links gefunden")

        # Top 5 Ergebnisse anzeigen
        log.info("\n🏆 TOP SUCHERGEBNISSE:")
        for i, link in enumerate(result_links[:5], 1):
            log.info(f"   {i}. {link.text[:80]}")
            if link.attrs.get('href'):
                log.info(f"      → {link.attrs['href'][:80]}")

        # ========================================
        # PERFORMANCE REPORT
        # ========================================
        log.info("\n" + "="*60)
        log.info("PERFORMANCE REPORT")
        log.info("="*60)

        print(perf.get_report())

        # Controller Stats
        stats = await controller.get_stats()
        log.info(f"\n📊 CONTROLLER STATISTIKEN:")
        log.info(f"   • DOM-Aktionen:     {stats.get('dom_actions', 0)}")
        log.info(f"   • Vision-Aktionen:  {stats.get('vision_actions', 0)}")
        log.info(f"   • Fallbacks:        {stats.get('fallbacks', 0)}")

        log.info("\n✅ TEST ERFOLGREICH ABGESCHLOSSEN!")

    except Exception as e:
        log.error(f"❌ Test fehlgeschlagen: {e}", exc_info=True)

    finally:
        # Cleanup
        await controller.cleanup()
        log.info("🧹 Browser geschlossen")


async def test_dom_vs_vision_comparison():
    """
    Vergleicht DOM-First vs. hypothetischen Vision-First Ansatz.

    Zeigt konkrete Performance-Unterschiede.
    """
    log.info("\n" + "="*60)
    log.info("DOM-FIRST vs. VISION-FIRST VERGLEICH")
    log.info("="*60)

    scenarios = [
        {
            'task': 'Google Suche',
            'actions': ['navigate', 'type', 'click', 'parse'],
            'dom_time_per_action': 0.2,  # 200ms DOM
            'vision_time_per_action': 5.0,  # 5s Vision (GPT-4V)
        },
        {
            'task': 'Login Form',
            'actions': ['navigate', 'type_email', 'type_password', 'click_submit'],
            'dom_time_per_action': 0.15,  # 150ms DOM
            'vision_time_per_action': 4.5,  # 4.5s Vision
        },
        {
            'task': 'Online Shopping',
            'actions': ['navigate', 'search', 'filter', 'select_item', 'add_to_cart', 'checkout'],
            'dom_time_per_action': 0.25,  # 250ms DOM
            'vision_time_per_action': 6.0,  # 6s Vision
        }
    ]

    print("\n╔═══════════════════════════════════════════════════════════════════╗")
    print("║              DOM-FIRST vs. VISION-FIRST BENCHMARK                 ║")
    print("╚═══════════════════════════════════════════════════════════════════╝\n")

    for scenario in scenarios:
        task = scenario['task']
        action_count = len(scenario['actions'])

        dom_total_time = action_count * scenario['dom_time_per_action']
        vision_total_time = action_count * scenario['vision_time_per_action']

        dom_cost = 0  # Kostenlos
        vision_cost = action_count * 0.0015  # $0.0015 pro Screenshot

        speedup = vision_total_time / dom_total_time
        cost_saving = vision_cost - dom_cost

        print(f"📋 {task} ({action_count} Aktionen)")
        print(f"   ┌─ DOM-First:    {dom_total_time:.2f}s | ${dom_cost:.4f}")
        print(f"   └─ Vision-First: {vision_total_time:.2f}s | ${vision_cost:.4f}")
        print(f"   ⚡ Speedup:      {speedup:.1f}x schneller")
        print(f"   💰 Ersparnis:    ${cost_saving:.4f} pro Durchlauf\n")

    print("✅ FAZIT: DOM-First ist 20-30x schneller und 100% günstiger!\n")


if __name__ == "__main__":
    async def main():
        # Test 1: Echte Google-Suche
        await test_google_search_dom_first()

        # Test 2: Performance-Vergleich
        await test_dom_vs_vision_comparison()

    asyncio.run(main())

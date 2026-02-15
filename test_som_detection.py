#!/usr/bin/env python3
"""
Test-Script für SoM Tool - Erkennung von UI-Elementen
Testet die Erkennungsqualität und loggt Details
"""
import asyncio
import httpx
import json
import logging
from datetime import datetime

# Logging konfigurieren
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'som_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)

log = logging.getLogger("som_test")

# MCP Server URL
MCP_URL = "http://127.0.0.1:5000"


async def call_rpc(method: str, params: dict = None):
    """Ruft eine RPC-Methode auf dem MCP-Server auf."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": "test-1"
    }

    log.info(f"📤 Aufruf: {method} mit params: {params}")

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            response = await client.post(MCP_URL, json=payload)
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                log.error(f"❌ RPC Error: {result['error']}")
                return None

            return result.get("result")

        except httpx.TimeoutException:
            log.error(f"⏱️ Timeout beim Aufruf von {method}")
            return None
        except Exception as e:
            log.error(f"❌ Fehler beim Aufruf: {e}")
            return None


async def test_som_detection():
    """Testet die SoM-Element-Erkennung."""

    log.info("="*80)
    log.info("🧪 SoM Tool Detection Test")
    log.info("="*80)

    # Test 1: Unterstützte Element-Typen abrufen
    log.info("\n📋 Test 1: Unterstützte Element-Typen")
    types_result = await call_rpc("get_supported_element_types")
    if types_result:
        log.info(f"✅ {types_result.get('count')} Element-Typen verfügbar:")
        for category, types in types_result.get('categories', {}).items():
            log.info(f"   {category}: {', '.join(types[:5])}{'...' if len(types) > 5 else ''}")

    # Test 2: Bildschirm scannen (nur wichtigste Typen für schnellen Test)
    log.info("\n🔍 Test 2: Bildschirm scannen (Prioritäts-Typen)")
    priority_types = ["button", "text field", "input field", "chat input", "search bar"]

    scan_result = await call_rpc("scan_ui_elements", {"element_types": priority_types})

    if not scan_result:
        log.error("❌ Scan fehlgeschlagen - keine Ergebnisse")
        return

    count = scan_result.get("count", 0)
    elements = scan_result.get("elements", [])

    log.info(f"\n✅ Scan abgeschlossen: {count} Elemente erkannt")
    log.info(f"   Nachricht: {scan_result.get('message', 'N/A')}")

    # Details ausgeben
    if elements:
        log.info("\n📊 Erkannte Elemente im Detail:")
        log.info("-" * 80)
        log.info(f"{'ID':<4} {'Typ':<15} {'X':<6} {'Y':<6} {'Breite':<7} {'Höhe':<7} {'Konfidenz':<10}")
        log.info("-" * 80)

        for elem in elements:
            log.info(
                f"{elem['id']:<4} "
                f"{elem['type']:<15} "
                f"{elem['x']:<6} "
                f"{elem['y']:<6} "
                f"{elem['bounds']['width']:<7} "
                f"{elem['bounds']['height']:<7} "
                f"{elem.get('confidence', 1.0):<10.2f}"
            )

        # Statistik nach Typ
        log.info("\n📈 Statistik nach Element-Typ:")
        type_counts = {}
        for elem in elements:
            elem_type = elem['type']
            type_counts[elem_type] = type_counts.get(elem_type, 0) + 1

        for elem_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            log.info(f"   {elem_type}: {count}x")
    else:
        log.warning("⚠️ Keine Elemente erkannt!")
        log.warning("   Mögliche Gründe:")
        log.warning("   - Kein Fenster im Fokus")
        log.warning("   - Moondream API nicht erreichbar")
        log.warning("   - Elemente zu klein/undeutlich")

    # Test 3: Screenshot mit Annotationen speichern
    log.info("\n📸 Test 3: Annotierter Screenshot speichern")
    screenshot_result = await call_rpc(
        "save_annotated_screenshot",
        {"filename": f"som_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"}
    )

    if screenshot_result and screenshot_result.get("saved"):
        log.info(f"✅ Screenshot gespeichert: {screenshot_result.get('path')}")
        log.info(f"   Markierte Elemente: {screenshot_result.get('elements_marked')}")
    else:
        log.error("❌ Screenshot konnte nicht gespeichert werden")

    # Test 4: Spezifisches Element suchen (z.B. Text Field)
    log.info("\n🎯 Test 4: Suche nach spezifischem Element-Typ")
    search_type = "text field"
    search_result = await call_rpc("find_and_click_element", {"element_type": search_type})

    if search_result and search_result.get("found"):
        log.info(f"✅ '{search_type}' gefunden:")
        log.info(f"   Position: ({search_result.get('x')}, {search_result.get('y')})")
        log.info(f"   Gesamt gefunden: {search_result.get('total_found')}")
        log.info(f"   Anweisung: {search_result.get('instruction')}")
    else:
        log.warning(f"⚠️ Kein '{search_type}' gefunden")

    # Test 5: Screen Description
    log.info("\n📝 Test 5: Screen Description")
    desc_result = await call_rpc("describe_screen_elements")

    if desc_result:
        log.info("✅ Bildschirm-Beschreibung:")
        log.info(desc_result.get("description", "N/A"))

    log.info("\n" + "="*80)
    log.info("✅ Test abgeschlossen!")
    log.info("="*80)

    # Zusammenfassung
    log.info("\n📊 ZUSAMMENFASSUNG:")
    log.info(f"   Gescannte Element-Typen: {len(priority_types)}")
    log.info(f"   Erkannte Elemente: {count}")
    log.info(f"   Erkennungsrate: {'Gut' if count > 0 else 'Schlecht'}")

    if count == 0:
        log.warning("\n⚠️ PROBLEM: Keine Elemente erkannt!")
        log.warning("   Prüfe:")
        log.warning("   1. Läuft der MCP-Server? (http://127.0.0.1:5000)")
        log.warning("   2. Ist Moondream API erreichbar?")
        log.warning("   3. Ist ein Fenster mit UI-Elementen geöffnet?")
        log.warning("   4. Sind die Element-Typen korrekt?")


async def main():
    """Hauptfunktion."""
    try:
        await test_som_detection()
    except KeyboardInterrupt:
        log.info("\n⚠️ Test abgebrochen durch Benutzer")
    except Exception as e:
        log.error(f"❌ Unerwarteter Fehler: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())

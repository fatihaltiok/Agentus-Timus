#!/usr/bin/env python3
"""
Test-Script für Hybrid Detection Tool
Testet die verbesserte Erkennungsqualität
"""
import asyncio
import httpx
import logging
from datetime import datetime

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)

log = logging.getLogger("hybrid_test")

MCP_URL = "http://127.0.0.1:5000"


async def call_rpc(method: str, params: dict = None):
    """Ruft eine RPC-Methode auf."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": "test-1"
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            response = await client.post(MCP_URL, json=payload)
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                log.error(f"❌ RPC Error: {result['error']}")
                return None

            return result.get("result")

        except Exception as e:
            log.error(f"❌ Fehler: {e}")
            return None


async def test_hybrid_detection():
    """Testet das Hybrid Detection System."""

    log.info("="*80)
    log.info("🧪 Hybrid Detection Test")
    log.info("="*80)

    # Test 1: Verbesserte SoM-Erkennung (mit Filterung)
    log.info("\n📋 Test 1: Verbesserte SoM-Erkennung")
    som_result = await call_rpc("scan_ui_elements", {
        "element_types": ["button", "text field", "input field"]
    })

    if som_result:
        count = som_result.get("count", 0)
        log.info(f"✅ SoM: {count} Elemente erkannt (mit Filterung)")

        elements = som_result.get("elements", [])
        for elem in elements[:3]:  # Zeige nur erste 3
            log.info(
                f"   [{elem['id']}] {elem['type']} @ ({elem['x']}, {elem['y']}) "
                f"- Größe: {elem['bounds']['width']}x{elem['bounds']['height']}"
            )
    else:
        log.error("❌ SoM-Scan fehlgeschlagen")

    # Test 2: Hybrid Find Element (ohne Text)
    log.info("\n📋 Test 2: Hybrid Find Element (Object Detection)")
    hybrid_result1 = await call_rpc("hybrid_find_element", {
        "element_type": "text field",
        "refine": True
    })

    if hybrid_result1 and hybrid_result1.get("found"):
        log.info(f"✅ Hybrid gefunden:")
        log.info(f"   Methode: {hybrid_result1.get('method')}")
        log.info(f"   Position: ({hybrid_result1.get('x')}, {hybrid_result1.get('y')})")
        log.info(f"   Konfidenz: {hybrid_result1.get('confidence'):.2f}")

        metadata = hybrid_result1.get("metadata", {})
        if "refinement_offset" in metadata:
            offset = metadata["refinement_offset"]
            log.info(f"   Verfeinerung: {offset[0]:+d}px, {offset[1]:+d}px")
            log.info(f"   Cursor: {metadata.get('cursor_type')}")
    else:
        log.warning("⚠️ Hybrid-Suche (ohne Text) fehlgeschlagen")

    # Test 3: Hybrid Find Element (mit Text - falls vorhanden)
    log.info("\n📋 Test 3: Hybrid Find Element (Text-basiert)")

    # Suche nach häufigem Text (anpassen an deinen Bildschirm)
    test_texts = ["Search", "Suchen", "File", "Datei", "Settings"]

    for test_text in test_texts:
        hybrid_result2 = await call_rpc("hybrid_find_element", {
            "text": test_text,
            "refine": True
        })

        if hybrid_result2 and hybrid_result2.get("found"):
            log.info(f"✅ Text '{test_text}' gefunden:")
            log.info(f"   Methode: {hybrid_result2.get('method')}")
            log.info(f"   Position: ({hybrid_result2.get('x')}, {hybrid_result2.get('y')})")
            break
    else:
        log.warning(f"⚠️ Keiner der Test-Texte gefunden: {test_texts}")

    # Test 4: Screenshot mit annotierten Elementen
    log.info("\n📋 Test 4: Screenshot speichern")
    screenshot_result = await call_rpc("save_annotated_screenshot", {
        "filename": f"hybrid_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    })

    if screenshot_result and screenshot_result.get("saved"):
        log.info(f"✅ Screenshot: {screenshot_result.get('path')}")
    else:
        log.error("❌ Screenshot fehlgeschlagen")

    log.info("\n" + "="*80)
    log.info("✅ Test abgeschlossen!")
    log.info("="*80)

    # Zusammenfassung
    log.info("\n📊 VERBESSERUNGEN:")
    log.info("   ✓ Kleinere Bilder (800x600 statt 1024x768)")
    log.info("   ✓ JPEG statt PNG (schneller)")
    log.info("   ✓ Filterung zu großer Bounding Boxes (>70%)")
    log.info("   ✓ Hybrid-Ansatz: OCR + Object Detection + Mouse Feedback")
    log.info("   ✓ Intelligente Verfeinerung mit Cursor-Erkennung")


async def main():
    try:
        await test_hybrid_detection()
    except KeyboardInterrupt:
        log.info("\n⚠️ Test abgebrochen")
    except Exception as e:
        log.error(f"❌ Fehler: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())

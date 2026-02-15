#!/usr/bin/env python3
"""
Test-Script für Zoom-basierte Element-Erkennung
Vergleicht Standard vs. Zoom-Detection
"""
import asyncio
import httpx
import logging
from datetime import datetime
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)

log = logging.getLogger("zoom_test")

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


async def test_zoom_detection():
    """Testet Zoom vs. Standard Erkennung."""

    log.info("="*80)
    log.info("🔍 Zoom Detection Test - Vergleich Standard vs. Multi-Resolution")
    log.info("="*80)

    # Element-Typen zum Testen
    test_types = ["text field", "chat input", "input field", "textbox"]

    # Test 1: OHNE Zoom (Standard)
    log.info("\n📋 Test 1: Standard-Erkennung (OHNE Zoom)")
    start_time = time.time()

    standard_result = await call_rpc("scan_ui_elements", {
        "element_types": test_types,
        "use_zoom": False
    })

    standard_time = time.time() - start_time

    if standard_result:
        standard_count = standard_result.get("count", 0)
        log.info(f"✅ Standard: {standard_count} Elemente in {standard_time:.1f}s")

        if standard_count > 0:
            for elem in standard_result.get("elements", [])[:3]:
                log.info(f"   [{elem['id']}] {elem['type']} @ ({elem['x']}, {elem['y']}) "
                        f"- {elem['bounds']['width']}x{elem['bounds']['height']}px")
    else:
        standard_count = 0
        log.error("❌ Standard-Scan fehlgeschlagen")

    # Test 2: MIT Zoom (Multi-Resolution + Smart Crop)
    log.info("\n📋 Test 2: Zoom-Erkennung (Multi-Resolution + Smart Crop)")
    start_time = time.time()

    zoom_result = await call_rpc("scan_ui_elements", {
        "element_types": test_types,
        "use_zoom": True
    })

    zoom_time = time.time() - start_time

    if zoom_result:
        zoom_count = zoom_result.get("count", 0)
        log.info(f"✅ Zoom: {zoom_count} Elemente in {zoom_time:.1f}s")

        if zoom_count > 0:
            for elem in zoom_result.get("elements", [])[:3]:
                log.info(f"   [{elem['id']}] {elem['type']} @ ({elem['x']}, {elem['y']}) "
                        f"- {elem['bounds']['width']}x{elem['bounds']['height']}px")
    else:
        zoom_count = 0
        log.error("❌ Zoom-Scan fehlgeschlagen")

    # Test 3: Screenshot mit Annotationen speichern
    log.info("\n📋 Test 3: Screenshot speichern")
    screenshot_result = await call_rpc("save_annotated_screenshot", {
        "filename": f"zoom_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    })

    if screenshot_result and screenshot_result.get("saved"):
        log.info(f"✅ Screenshot: {screenshot_result.get('path')}")
    else:
        log.error("❌ Screenshot fehlgeschlagen")

    # Vergleich
    log.info("\n" + "="*80)
    log.info("📊 VERGLEICH:")
    log.info("="*80)
    log.info(f"Standard (ohne Zoom):  {standard_count} Elemente in {standard_time:.1f}s")
    log.info(f"Zoom (Multi-Res):      {zoom_count} Elemente in {zoom_time:.1f}s")

    improvement = zoom_count - standard_count
    if improvement > 0:
        log.info(f"\n✅ VERBESSERUNG: +{improvement} Elemente erkannt mit Zoom!")
        log.info(f"   Erkennungsrate: {zoom_count}/{standard_count if standard_count > 0 else 1} "
                f"= {(zoom_count / standard_count * 100) if standard_count > 0 else 'N/A'}%")
    elif improvement < 0:
        log.warning(f"\n⚠️ VERSCHLECHTERUNG: {improvement} weniger Elemente mit Zoom")
    else:
        log.info(f"\n➡️ GLEICH: Beide Methoden fanden {zoom_count} Elemente")

    # Zeit-Vergleich
    time_diff = zoom_time - standard_time
    if time_diff > 0:
        log.info(f"   Zeit: +{time_diff:.1f}s langsamer mit Zoom (höhere Qualität)")
    else:
        log.info(f"   Zeit: {abs(time_diff):.1f}s schneller mit Zoom")

    log.info("\n" + "="*80)
    log.info("✅ Test abgeschlossen!")
    log.info("="*80)

    # Empfehlung
    if zoom_count > standard_count:
        log.info("\n💡 EMPFEHLUNG: Zoom aktiviert lassen (use_zoom=True)")
        log.info("   → Mehr Elemente erkannt, bessere Präzision für kleine UI-Elemente")
    elif zoom_time > standard_time * 2:
        log.warning("\n⚠️ ACHTUNG: Zoom ist deutlich langsamer")
        log.warning("   → Nur bei Bedarf aktivieren (kleine Elemente, hohe Auflösung)")
    else:
        log.info("\n➡️ Standard reicht aus für diese Ansicht")


async def main():
    try:
        await test_zoom_detection()
    except KeyboardInterrupt:
        log.info("\n⚠️ Test abgebrochen")
    except Exception as e:
        log.error(f"❌ Fehler: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())

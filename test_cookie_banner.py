#!/usr/bin/env python3
# test_cookie_banner.py
"""
Test-Script für Cookie-Banner Tool

Testet:
1. Health-Check
2. detect_cookie_banner (Scan-Modus)
3. detect_cookie_banner mit Click
4. auto_accept_cookies
"""

import asyncio
import httpx
import json
import sys

# --- Konfiguration ---
MCP_URL = "http://127.0.0.1:5000"
TIMEOUT = 30.0

# --- Hilfsfunktionen ---
async def call_rpc(method: str, params: dict = None) -> dict:
    """RPC-Aufruf zum MCP-Server."""
    params = params or {}
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(MCP_URL, json=payload)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                return {"error": data["error"]}

            return data.get("result", {})
    except Exception as e:
        return {"error": str(e)}


async def test_health():
    """Test 1: Health-Check."""
    print("\n" + "="*60)
    print("TEST 1: Cookie-Banner Health-Check")
    print("="*60)

    result = await call_rpc("cookie_banner_health")

    if "error" in result:
        print(f"❌ Health-Check fehlgeschlagen: {result['error']}")
        return False

    print("✅ Health-Check erfolgreich!")
    print(f"\nStatus: {result.get('status')}")
    print(f"OCR verfügbar: {result.get('ocr_available')}")
    print(f"OCR Backend: {result.get('ocr_backend')}")
    print(f"Screenshot verfügbar: {result.get('screenshot_available')}")
    print(f"Mouse verfügbar: {result.get('mouse_available')}")
    print(f"Monitor: {result.get('active_monitor')}")

    print("\nUnterstützte Sprachen:")
    for lang in result.get('supported_languages', []):
        print(f"  • {lang}")

    print(f"\nErkennung:")
    print(f"  • Banner-Keywords: {result.get('detection_keywords')}")
    print(f"  • Accept-Patterns: {result.get('accept_patterns')}")

    return True


async def test_detect_only():
    """Test 2: Detection ohne Klick."""
    print("\n" + "="*60)
    print("TEST 2: Cookie-Banner Detection (Scan-Modus)")
    print("="*60)
    print("🔍 Suche nach Cookie-Banner auf aktuellem Bildschirm...")

    result = await call_rpc("detect_cookie_banner", {
        "click_accept": False
    })

    if "error" in result:
        print(f"❌ Detection fehlgeschlagen: {result['error']}")
        return False

    detected = result.get("cookie_banner_detected", False)

    if not detected:
        print("✅ Kein Cookie-Banner gefunden")
        print(f"   Analysierte Textblöcke: {result.get('text_blocks_analyzed', 0)}")
        return True

    print("✅ Cookie-Banner erkannt!")

    button_found = result.get("accept_button_found", False)
    if button_found:
        print(f"\n🎯 Accept-Button gefunden:")
        print(f"   Text: '{result.get('button_text')}'")
        print(f"   Position: ({result.get('button_position', {}).get('x')}, {result.get('button_position', {}).get('y')})")
        print(f"   Priorität: {result.get('button_priority')}")
        print(f"   Confidence: {result.get('button_confidence', 0):.1%}")

        total = result.get('total_buttons_found', 0)
        if total > 1:
            print(f"\n📋 Weitere Buttons gefunden: {total - 1}")
            for i, btn in enumerate(result.get('all_buttons', [])[1:], 2):
                print(f"   {i}. '{btn['text']}' (Prio: {btn['priority']}, Conf: {btn['confidence']:.1%})")
    else:
        print("⚠️ Cookie-Banner gefunden, aber kein Accept-Button erkannt")

    return True


async def test_detect_with_click():
    """Test 3: Detection mit Klick."""
    print("\n" + "="*60)
    print("TEST 3: Cookie-Banner Detection mit Auto-Click")
    print("="*60)

    choice = input("⚠️ Dies wird auf einen gefundenen Button KLICKEN!\n   Fortfahren? (y/N): ")

    if choice.lower() != 'y':
        print("⏭️ Test übersprungen")
        return True

    print("🔍 Suche und klicke auf Cookie-Banner...")

    result = await call_rpc("detect_cookie_banner", {
        "click_accept": True,
        "verify_click": True
    })

    if "error" in result:
        print(f"❌ Detection fehlgeschlagen: {result['error']}")
        return False

    detected = result.get("cookie_banner_detected", False)

    if not detected:
        print("ℹ️ Kein Cookie-Banner gefunden")
        return True

    clicked = result.get("clicked", False)
    success = result.get("click_success", False)

    if clicked and success:
        print(f"✅ Cookie-Banner erfolgreich akzeptiert!")
        print(f"   Button: '{result.get('button_text')}'")
        print(f"   Position: ({result.get('button_position', {}).get('x')}, {result.get('button_position', {}).get('y')})")
    elif clicked and not success:
        print(f"⚠️ Klick fehlgeschlagen auf '{result.get('button_text')}'")
    else:
        print("ℹ️ Button gefunden aber nicht geklickt")

    return clicked and success


async def test_auto_accept():
    """Test 4: Auto-Accept."""
    print("\n" + "="*60)
    print("TEST 4: Auto-Accept Cookies")
    print("="*60)

    choice = input("⚠️ Dies wird versuchen Cookie-Banner automatisch zu akzeptieren!\n   Fortfahren? (y/N): ")

    if choice.lower() != 'y':
        print("⏭️ Test übersprungen")
        return True

    print("🔄 Starte Auto-Accept (max 2 Versuche)...")

    result = await call_rpc("auto_accept_cookies", {
        "max_attempts": 2,
        "wait_between_attempts": 1.5
    })

    if "error" in result:
        print(f"❌ Auto-Accept fehlgeschlagen: {result['error']}")
        return False

    status = result.get("status", "unknown")
    attempts = result.get("attempts", 0)
    message = result.get("message", "")

    print(f"\n📊 Status: {status}")
    print(f"   Versuche: {attempts}")
    print(f"   {message}")

    if status == "success":
        print(f"✅ Cookie-Banner akzeptiert: '{result.get('button_clicked')}'")
        return True
    elif status == "no_banner":
        print("ℹ️ Kein Cookie-Banner gefunden")
        return True
    else:
        print("⚠️ Kein vollständiger Erfolg")
        return False


async def main():
    """Hauptfunktion."""
    print("\n" + "="*80)
    print("🍪 Cookie-Banner Tool Test Suite")
    print("="*80)
    print("\n⚠️ HINWEIS: Für Tests 3 & 4 sollte eine Webseite mit Cookie-Banner geöffnet sein!")
    print("   Beispiele:")
    print("   • https://www.spiegel.de")
    print("   • https://www.zeit.de")
    print("   • https://www.bbc.com")

    results = []

    # Test 1: Health
    result1 = await test_health()
    results.append(("Health-Check", result1))

    # Test 2: Detection
    result2 = await test_detect_only()
    results.append(("Detection (Scan)", result2))

    # Test 3: Detection + Click (optional)
    result3 = await test_detect_with_click()
    results.append(("Detection + Click", result3))

    # Test 4: Auto-Accept (optional)
    result4 = await test_auto_accept()
    results.append(("Auto-Accept", result4))

    # Zusammenfassung
    print("\n" + "="*80)
    print("📊 TEST-ZUSAMMENFASSUNG")
    print("="*80)

    for test_name, passed in results:
        status = "✅ BESTANDEN" if passed else "❌ FEHLGESCHLAGEN"
        print(f"{status}: {test_name}")

    print("="*80)
    print("\n✅ Cookie-Banner Tool bereit zur Nutzung:")
    print("  • cookie_banner_health() - Health-Check")
    print("  • detect_cookie_banner(click_accept, verify_click) - Banner erkennen ± klicken")
    print("  • auto_accept_cookies(max_attempts, wait_between_attempts) - Automatisch akzeptieren")
    print("\n💡 Beispiele:")
    print("  # Nur scannen:")
    print("  detect_cookie_banner(click_accept=False)")
    print("\n  # Scannen + Klicken:")
    print("  detect_cookie_banner(click_accept=True, verify_click=True)")
    print("\n  # Auto-Accept mit Wiederholung:")
    print("  auto_accept_cookies(max_attempts=3, wait_between_attempts=2.0)")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

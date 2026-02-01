#!/usr/bin/env python3
"""
Test für ROI-Support in VisualAgent.

Testet:
1. ROI-Management (set, clear, push, pop)
2. Automatische Erkennung dynamischer UIs
3. Screen-Change-Gate mit ROI

Usage:
    python test_roi_support.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Pfad-Setup
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.timus_consolidated import VisualAgent
from dotenv import load_dotenv

load_dotenv()

# Test-Farben
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_test(name: str):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print('='*60)


def print_success(msg: str):
    print(f"{GREEN}✅ {msg}{RESET}")


def print_error(msg: str):
    print(f"{RED}❌ {msg}{RESET}")


def print_info(msg: str):
    print(f"{YELLOW}ℹ️  {msg}{RESET}")


# ==============================================================================
# TEST 1: ROI-Management
# ==============================================================================

def test_roi_management():
    print_test("ROI-Management (set, clear, push, pop)")

    try:
        tools_desc = "Available tools for VisualAgent"
        agent = VisualAgent(tools_desc)

        # Test 1: Set ROI
        print("   1. Set ROI...")
        agent._set_roi(x=100, y=200, width=600, height=400, name="test_roi")

        if agent.current_roi:
            print_success(f"ROI gesetzt: {agent.current_roi}")
        else:
            print_error("ROI nicht gesetzt")
            return False

        # Test 2: Clear ROI
        print("   2. Clear ROI...")
        agent._clear_roi()

        if agent.current_roi is None:
            print_success("ROI gelöscht")
        else:
            print_error("ROI nicht gelöscht")
            return False

        # Test 3: Push/Pop ROI (verschachtelt)
        print("   3. Push/Pop ROI...")
        agent._set_roi(x=0, y=0, width=100, height=100, name="roi_1")
        agent._push_roi(x=50, y=50, width=200, height=200, name="roi_2")

        if agent.current_roi and agent.current_roi["name"] == "roi_2":
            print_success(f"ROI gepusht: {agent.current_roi['name']}")
        else:
            print_error("ROI push fehlgeschlagen")
            return False

        agent._pop_roi()

        if agent.current_roi and agent.current_roi["name"] == "roi_1":
            print_success(f"ROI gepoppt: {agent.current_roi['name']}")
        else:
            print_error("ROI pop fehlgeschlagen")
            return False

        return True

    except Exception as e:
        print_error(f"Fehler: {e}")
        return False


# ==============================================================================
# TEST 2: Dynamische UI-Erkennung
# ==============================================================================

async def test_dynamic_ui_detection():
    print_test("Dynamische UI-Erkennung")

    try:
        tools_desc = "Available tools for VisualAgent"
        agent = VisualAgent(tools_desc)

        # Test 1: Google-Erkennung
        print("   1. Google Search erkenne...")
        roi_set = await agent._detect_dynamic_ui_and_set_roi("Google suche nach Python")

        if roi_set and agent.current_roi:
            print_success(f"Google erkannt, ROI gesetzt: {agent.current_roi['name']}")
        else:
            print_error("Google nicht erkannt")
            return False

        agent._clear_roi()

        # Test 2: Booking.com-Erkennung
        print("   2. Booking.com erkenne...")
        roi_set = await agent._detect_dynamic_ui_and_set_roi("Booking Hotel suchen")

        if roi_set and agent.current_roi:
            print_success(f"Booking.com erkannt, ROI gesetzt: {agent.current_roi['name']}")
        else:
            print_error("Booking.com nicht erkannt")
            return False

        agent._clear_roi()

        # Test 3: Keine Erkennung (normale Task)
        print("   3. Normale Task (kein ROI)...")
        roi_set = await agent._detect_dynamic_ui_and_set_roi("Öffne Firefox")

        if not roi_set and agent.current_roi is None:
            print_success("Keine dynamische UI erkannt (erwartet)")
        else:
            print_error("Falsche Erkennung")
            return False

        return True

    except Exception as e:
        print_error(f"Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# TEST 3: Screen-Change-Gate mit ROI
# ==============================================================================

async def test_screen_change_with_roi():
    print_test("Screen-Change-Gate mit ROI")

    try:
        tools_desc = "Available tools for VisualAgent"
        agent = VisualAgent(tools_desc)

        # Setze ROI
        agent._set_roi(x=100, y=100, width=400, height=300, name="test_roi")

        # Screen-Change-Check mit ROI
        print("   1. Screen-Change-Check mit ROI...")
        should_analyze = await agent._should_analyze_screen(roi=agent.current_roi)

        print_success(f"Screen-Change-Check erfolgreich: {should_analyze}")

        # Zweiter Check (sollte Cache-Hit sein wenn Screen unverändert)
        print("   2. Zweiter Check (Cache-Hit?)...")
        should_analyze2 = await agent._should_analyze_screen(roi=agent.current_roi)

        if not should_analyze2:
            print_success("Cache-Hit! (ROI unverändert)")
        else:
            print_info(f"Kein Cache-Hit (result={should_analyze2})")

        return True

    except Exception as e:
        print_error(f"Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# MAIN
# ==============================================================================

async def main():
    print("\n" + "="*60)
    print("🧪 ROI-SUPPORT TESTS")
    print("="*60)
    print(f"Datum: {os.popen('date').read().strip()}")
    print("="*60)

    results = []

    # Test 1: ROI-Management
    results.append(("ROI-Management", test_roi_management()))

    # Test 2: Dynamische UI-Erkennung
    results.append(("Dynamische UI-Erkennung", await test_dynamic_ui_detection()))

    # Test 3: Screen-Change-Gate mit ROI
    results.append(("Screen-Change mit ROI", await test_screen_change_with_roi()))

    # Zusammenfassung
    print("\n" + "="*60)
    print("📊 ZUSAMMENFASSUNG")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = f"{GREEN}✅ BESTANDEN{RESET}" if result else f"{RED}❌ FEHLGESCHLAGEN{RESET}"
        print(f"{name:35s} {status}")

    print("="*60)
    print(f"Ergebnis: {passed}/{total} Tests bestanden")

    if passed == total:
        print(f"{GREEN}✅ ALLE TESTS BESTANDEN!{RESET}")
        print("\n🚀 ROI-Support ist einsatzbereit!")
    else:
        print(f"{RED}❌ EINIGE TESTS FEHLGESCHLAGEN{RESET}")
        print("\n⚠️ Prüfe die Fehler oben und behebe sie.")

    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

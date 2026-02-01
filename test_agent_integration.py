#!/usr/bin/env python3
"""
Test-Script für Screen-Change-Gate Integration in Agents.

Testet:
1. Ist Screen-Change-Gate in BaseAgent verfügbar?
2. Wird es korrekt aktiviert via ENV?
3. Funktionieren die Helper-Methoden?
4. Performance-Verbesserung messbar?

Usage:
    python test_agent_integration.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Pfad-Setup
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.timus_consolidated import ExecutorAgent, VisualAgent
from dotenv import load_dotenv

load_dotenv()

# Test-Farben
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
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
# TEST 1: Screen-Change-Gate ENV Variable
# ==============================================================================

def test_env_variable():
    print_test("ENV Variable Check")

    use_gate = os.getenv("USE_SCREEN_CHANGE_GATE", "false").lower()
    print(f"   USE_SCREEN_CHANGE_GATE = {use_gate}")

    if use_gate == "true":
        print_success("Screen-Change-Gate ist AKTIVIERT in .env")
        return True
    else:
        print_error("Screen-Change-Gate ist DEAKTIVIERT in .env")
        print_info("Setze 'USE_SCREEN_CHANGE_GATE=true' in .env")
        return False


# ==============================================================================
# TEST 2: Agent-Initialisierung
# ==============================================================================

def test_agent_initialization():
    print_test("Agent-Initialisierung")

    try:
        # Dummy tools_description
        tools_desc = "Available tools: test_tool"

        # ExecutorAgent
        print("   Erstelle ExecutorAgent...")
        executor = ExecutorAgent(tools_desc)

        if hasattr(executor, "use_screen_change_gate"):
            print_success("ExecutorAgent hat 'use_screen_change_gate' Attribut")
            print(f"      Wert: {executor.use_screen_change_gate}")
        else:
            print_error("ExecutorAgent fehlt 'use_screen_change_gate' Attribut")
            return False

        if hasattr(executor, "cached_screen_state"):
            print_success("ExecutorAgent hat 'cached_screen_state' Attribut")
        else:
            print_error("ExecutorAgent fehlt 'cached_screen_state' Attribut")
            return False

        # Prüfe ob Gate aktiviert (wenn ENV=true)
        use_gate = os.getenv("USE_SCREEN_CHANGE_GATE", "false").lower() == "true"
        if use_gate and not executor.use_screen_change_gate:
            print_error("ENV=true aber Agent hat Gate nicht aktiviert!")
            return False
        elif use_gate:
            print_success("Gate ist korrekt aktiviert (ENV=true, Agent=True)")

        return True

    except Exception as e:
        print_error(f"Fehler bei Agent-Initialisierung: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# TEST 3: Helper-Methoden vorhanden
# ==============================================================================

def test_helper_methods():
    print_test("Helper-Methoden Check")

    try:
        tools_desc = "Available tools: test_tool"
        agent = ExecutorAgent(tools_desc)

        # _should_analyze_screen
        if hasattr(agent, "_should_analyze_screen"):
            print_success("Agent hat '_should_analyze_screen()' Methode")
        else:
            print_error("Agent fehlt '_should_analyze_screen()' Methode")
            return False

        # _get_screen_state
        if hasattr(agent, "_get_screen_state"):
            print_success("Agent hat '_get_screen_state()' Methode")
        else:
            print_error("Agent fehlt '_get_screen_state()' Methode")
            return False

        return True

    except Exception as e:
        print_error(f"Fehler: {e}")
        return False


# ==============================================================================
# TEST 4: Functional Test (mit MCP-Server)
# ==============================================================================

async def test_functional():
    print_test("Functional Test (benötigt MCP-Server)")

    print_info("Prüfe ob MCP-Server läuft...")

    try:
        tools_desc = "Available tools: test_tool"
        agent = ExecutorAgent(tools_desc)

        # Test 1: _should_analyze_screen (ohne ROI)
        print("\n   Test 1: _should_analyze_screen() aufrufen...")

        if not agent.use_screen_change_gate:
            print_info("   Gate deaktiviert - Methode sollte True zurückgeben")
            result = await agent._should_analyze_screen()
            if result == True:
                print_success("Korrekt: True bei deaktiviertem Gate")
            else:
                print_error(f"Erwartet True, bekam {result}")
                return False
        else:
            print_info("   Gate aktiviert - rufe Tool auf...")
            try:
                result = await agent._should_analyze_screen()
                print_success(f"Tool-Aufruf erfolgreich: {result}")

                # Zweiter Aufruf - sollte False sein (Cache-Hit)
                print("   Test 2: Zweiter Aufruf (sollte Cache-Hit sein)...")
                result2 = await agent._should_analyze_screen()

                if result2 == False:
                    print_success("Cache-Hit! (erwartet bei unverändert Screen)")
                else:
                    print_info(f"Kein Cache-Hit (result={result2}), möglich bei verändertem Screen")

            except Exception as e:
                print_error(f"Tool-Aufruf fehlgeschlagen: {e}")
                print_info("Stelle sicher, dass MCP-Server läuft:")
                print_info("   python server/mcp_server.py")
                return False

        # Test 3: Stats abrufen
        print("\n   Test 3: Performance-Stats abrufen...")
        try:
            stats = await agent._call_tool("get_screen_change_stats", {})

            if stats and "total_checks" in stats:
                print_success("Stats erfolgreich abgerufen:")
                print(f"      Total Checks: {stats.get('total_checks')}")
                print(f"      Changes Detected: {stats.get('changes_detected')}")
                print(f"      Cache-Hits: {stats.get('cache_hits')}")
                print(f"      Cache-Hit-Rate: {stats.get('cache_hit_rate', 0) * 100:.0f}%")
            else:
                print_error(f"Unerwartete Stats-Struktur: {stats}")
                return False

        except Exception as e:
            print_error(f"Stats-Abfrage fehlgeschlagen: {e}")
            return False

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
    print("🧪 SCREEN-CHANGE-GATE INTEGRATION TESTS")
    print("="*60)
    print(f"Datum: {os.popen('date').read().strip()}")
    print("="*60)

    results = []

    # Test 1: ENV Variable
    results.append(("ENV Variable", test_env_variable()))

    # Test 2: Agent-Initialisierung
    results.append(("Agent-Initialisierung", test_agent_initialization()))

    # Test 3: Helper-Methoden
    results.append(("Helper-Methoden", test_helper_methods()))

    # Test 4: Functional (async)
    results.append(("Functional Test", await test_functional()))

    # Zusammenfassung
    print("\n" + "="*60)
    print("📊 ZUSAMMENFASSUNG")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = f"{GREEN}✅ BESTANDEN{RESET}" if result else f"{RED}❌ FEHLGESCHLAGEN{RESET}"
        print(f"{name:30s} {status}")

    print("="*60)
    print(f"Ergebnis: {passed}/{total} Tests bestanden")

    if passed == total:
        print(f"{GREEN}✅ ALLE TESTS BESTANDEN!{RESET}")
        print("\n🚀 Screen-Change-Gate Integration ist einsatzbereit!")
    else:
        print(f"{RED}❌ EINIGE TESTS FEHLGESCHLAGEN{RESET}")
        print("\n⚠️ Prüfe die Fehler oben und behebe sie.")

    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

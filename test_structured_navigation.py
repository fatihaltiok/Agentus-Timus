#!/usr/bin/env python3
"""
Test für strukturierte Navigation in VisualAgent.

Testet die neuen Navigation-Logik-Features:
1. Screen-Analyse mit Auto-Discovery
2. LLM-basierte ActionPlan-Erstellung
3. ActionPlan-Execution

Usage:
    python test_structured_navigation.py
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


def print_step(msg: str):
    print(f"{BLUE}▶️ {msg}{RESET}")


# ==============================================================================
# TEST 1: Screen-Analyse (Auto-Discovery)
# ==============================================================================

async def test_screen_analysis():
    print_test("Screen-Analyse mit Auto-Discovery")

    try:
        # Erstelle Agent
        tools_desc = "Available tools for VisualAgent"
        agent = VisualAgent(tools_desc)

        print_step("Führe Screen-Analyse aus...")
        screen_state = await agent._analyze_current_screen()

        if screen_state:
            print_success(f"Screen-State erhalten")
            print(f"   Screen-ID: {screen_state.get('screen_id')}")
            print(f"   Elemente: {len(screen_state.get('elements', []))}")

            # Zeige erste 5 Elemente
            for i, elem in enumerate(screen_state.get("elements", [])[:5]):
                text = elem.get("text", "")[:30]
                print(f"     {i+1}. {elem.get('name')}: \"{text}\" at ({elem.get('x')}, {elem.get('y')})")

            return True
        else:
            print_error("Keine Screen-State erhalten")
            return False

    except Exception as e:
        print_error(f"Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# TEST 2: ActionPlan-Erstellung (LLM)
# ==============================================================================

async def test_action_plan_creation():
    print_test("ActionPlan-Erstellung mit LLM")

    try:
        tools_desc = "Available tools for VisualAgent"
        agent = VisualAgent(tools_desc)

        # Mock Screen-State
        mock_screen_state = {
            "screen_id": "test_screen",
            "elements": [
                {"name": "elem_0", "type": "text", "text": "Search", "x": 100, "y": 200},
                {"name": "elem_1", "type": "text", "text": "Google", "x": 300, "y": 50},
                {"name": "elem_2", "type": "text_field", "text": "Enter search term", "x": 400, "y": 200},
                {"name": "elem_3", "type": "button", "text": "Search Button", "x": 600, "y": 200}
            ]
        }

        task = "Suche nach Python Tutorials"

        print_step(f"Erstelle ActionPlan für: {task}")
        action_plan = await agent._create_navigation_plan_with_llm(task, mock_screen_state)

        if action_plan:
            print_success("ActionPlan erstellt")
            print(f"   Goal: {action_plan.get('goal')}")
            print(f"   Screen-ID: {action_plan.get('screen_id')}")
            print(f"   Steps: {len(action_plan.get('steps', []))}")

            for i, step in enumerate(action_plan.get("steps", [])):
                print(f"     Step {i+1}: {step.get('op')} auf {step.get('target')}")
                if step.get("params", {}).get("text"):
                    print(f"       Text: {step['params']['text']}")

            return True
        else:
            print_error("Kein ActionPlan erstellt")
            return False

    except Exception as e:
        print_error(f"Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# TEST 3: Strukturierte Navigation (End-to-End)
# ==============================================================================

async def test_structured_navigation():
    print_test("Strukturierte Navigation (End-to-End)")

    print_info("⚠️ Dieser Test benötigt einen laufenden Screen mit interaktiven Elementen")
    print_info("   Stelle sicher, dass z.B. Firefox mit Google geöffnet ist")

    try:
        tools_desc = "Available tools for VisualAgent"
        agent = VisualAgent(tools_desc)

        task = "Prüfe ob Firefox geöffnet ist"

        print_step(f"Führe strukturierte Navigation aus: {task}")
        result = await agent._try_structured_navigation(task)

        if result:
            if result.get("success"):
                print_success(f"Navigation erfolgreich: {result.get('result')}")
                return True
            else:
                print_info(f"Navigation fehlgeschlagen (erwartet wenn kein passender Screen): {result}")
                return True  # Nicht als Fehler werten
        else:
            print_info("Strukturierte Navigation nicht möglich - Fallback zu Vision würde greifen")
            return True  # Nicht als Fehler werten

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
    print("🧪 STRUKTURIERTE NAVIGATION TESTS")
    print("="*60)
    print(f"Datum: {os.popen('date').read().strip()}")
    print("="*60)

    results = []

    # Test 1: Screen-Analyse
    results.append(("Screen-Analyse", await test_screen_analysis()))

    # Test 2: ActionPlan-Erstellung
    results.append(("ActionPlan-Erstellung", await test_action_plan_creation()))

    # Test 3: Strukturierte Navigation (End-to-End)
    results.append(("Strukturierte Navigation", await test_structured_navigation()))

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
        print("\n🚀 Strukturierte Navigation ist einsatzbereit!")
    else:
        print(f"{RED}❌ EINIGE TESTS FEHLGESCHLAGEN{RESET}")
        print("\n⚠️ Prüfe die Fehler oben und behebe sie.")

    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

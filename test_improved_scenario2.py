#!/usr/bin/env python3
"""
Automatisierter Test für Scenario 2 (Google Search) mit neuen Features.

Testet die Verbesserungen:
1. ROI-Support für Google (Suchleiste)
2. Strukturierte Navigation (Screen-Contract-Tool)
3. Loop-Recovery (Force-Vision bei Loops)

Usage:
    python test_improved_scenario2.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Pfad-Setup
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.timus_consolidated import VisualAgent
from dotenv import load_dotenv
import httpx

load_dotenv()

# Test-Farben
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
RESET = "\033[0m"


def print_header(text: str):
    print(f"\n{CYAN}{'='*70}{RESET}")
    print(f"{CYAN}{text:^70}{RESET}")
    print(f"{CYAN}{'='*70}{RESET}\n")


def print_step(text: str):
    print(f"{BLUE}▶️ {text}{RESET}")


def print_success(text: str):
    print(f"{GREEN}✅ {text}{RESET}")


def print_error(text: str):
    print(f"{RED}❌ {text}{RESET}")


def print_info(text: str):
    print(f"{YELLOW}ℹ️  {text}{RESET}")


async def get_screen_change_stats():
    """Holt Screen-Change-Stats vom MCP-Server."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://127.0.0.1:5000",
                json={"jsonrpc": "2.0", "method": "get_screen_change_stats", "params": {}, "id": "1"}
            )
            data = resp.json()
            if "result" in data:
                return data["result"]
            return None
    except Exception as e:
        print_error(f"Stats-Abfrage fehlgeschlagen: {e}")
        return None


async def reset_screen_detector():
    """Reset Screen-Detector."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://127.0.0.1:5000",
                json={"jsonrpc": "2.0", "method": "reset_screen_detector", "params": {}, "id": "1"}
            )
            return resp.status_code == 200
    except:
        return False


async def main():
    print_header("🚀 SCENARIO 2 TEST: Google Search (Verbessert)")

    print(f"Datum: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"USE_SCREEN_CHANGE_GATE: {os.getenv('USE_SCREEN_CHANGE_GATE', 'false')}")

    # Reset Stats
    print_step("Reset Screen-Change-Detector...")
    await reset_screen_detector()

    # Initial Stats
    print_step("Hole Initial-Stats...")
    initial_stats = await get_screen_change_stats()
    if initial_stats:
        print(f"   Initial Cache-Hit-Rate: {initial_stats.get('cache_hit_rate', 0) * 100:.1f}%")

    print("\n" + "-"*70)
    print_step("Starte VisualAgent mit Google-Search-Task...")
    print("-"*70 + "\n")

    # Erstelle Agent
    tools_desc = "Available tools for VisualAgent"
    agent = VisualAgent(tools_desc)

    # Task: Google Search (sollte ROI auslösen)
    task = "Prüfe ob Google Search verfügbar ist"

    # Start Timer
    start_time = time.time()

    try:
        # Führe Task aus
        result = await agent.run(task)

        # End Timer
        execution_time = time.time() - start_time

        print("\n" + "-"*70)
        print_step("Task abgeschlossen!")
        print("-"*70 + "\n")

        print(f"Ergebnis: {result}")
        print(f"Execution-Zeit: {execution_time:.2f}s")

        # Hole Final Stats
        print_step("\nHole Final-Stats...")
        final_stats = await get_screen_change_stats()

        if final_stats:
            print("\n" + "="*70)
            print(f"{CYAN}📊 SCREEN-CHANGE-GATE PERFORMANCE{RESET}")
            print("="*70)

            total_checks = final_stats.get("total_checks", 0)
            changes_detected = final_stats.get("changes_detected", 0)
            cache_hits = final_stats.get("cache_hits", 0)
            cache_hit_rate = final_stats.get("cache_hit_rate", 0)

            print(f"Total Checks:        {total_checks}")
            print(f"Changes Detected:    {changes_detected}")
            print(f"Cache-Hits:          {cache_hits}")
            print(f"Cache-Hit-Rate:      {cache_hit_rate * 100:.1f}%")

            if cache_hit_rate >= 0.5:
                print_success(f"\nCache-Hit-Rate >= 50% - VERBESSERT! (Vorher: 0%)")
            elif cache_hit_rate >= 0.3:
                print_info(f"\nCache-Hit-Rate >= 30% - Teilerfolg (Vorher: 0%)")
            else:
                print_error(f"\nCache-Hit-Rate < 30% - Noch verbesserungswürdig")

            # Savings
            savings = final_stats.get("savings_estimate", "N/A")
            if savings != "N/A":
                print(f"\nErsparnis:           {savings}")

            # Check-Zeit
            avg_check_time = final_stats.get("avg_check_time_ms", 0)
            print(f"Avg Check-Zeit:      {avg_check_time:.1f}ms")

            print("="*70)

        # ROI-Info
        if agent.current_roi:
            print_info(f"\nROI war gesetzt: {agent.current_roi['name']}")
        else:
            print_info("\nKeine ROI gesetzt (wurde cleared nach Task)")

        # Loop-Info
        if agent.recent_actions:
            unique_actions = len(set(agent.recent_actions))
            total_actions = len(agent.recent_actions)
            print_info(f"Actions: {total_actions} total, {unique_actions} unique")

            # Prüfe auf Loops
            action_counts = {}
            for action in agent.recent_actions:
                action_counts[action] = action_counts.get(action, 0) + 1

            loops = {k: v for k, v in action_counts.items() if v >= 2}
            if loops:
                print_error(f"Loops detected: {len(loops)} Actions mit Wiederholungen")
                for action, count in list(loops.items())[:3]:
                    print(f"   - {action[:50]}... ({count}x)")
            else:
                print_success("Keine Loops detected!")

        print("\n" + "="*70)
        print_success("TEST ABGESCHLOSSEN")
        print("="*70)

    except Exception as e:
        print_error(f"\nFehler während Test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Production-Test: Screen-Change-Gate mit echtem Use-Case

Use-Case: Browser-Navigation mit Google-Suche
1. Öffne Firefox
2. Navigiere zu Google
3. Suche nach "Timus AI"
4. Warte auf Ergebnisse

Misst Performance-Verbesserung durch Screen-Change-Gate.
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Pfad-Setup
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.timus_consolidated import VisualAgent
from dotenv import load_dotenv
import httpx

load_dotenv()

# MCP Server URL
MCP_URL = "http://127.0.0.1:5000"
http_client = httpx.AsyncClient(timeout=300.0)


async def call_tool(method: str, params: dict = None) -> dict:
    """Ruft Tool über MCP auf."""
    try:
        resp = await http_client.post(
            MCP_URL,
            json={"jsonrpc": "2.0", "method": method, "params": params or {}, "id": "1"}
        )
        data = resp.json()
        return data.get("result", {})
    except Exception as e:
        return {"error": str(e)}


def print_header(title: str):
    """Druckt formatierten Header."""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def print_section(title: str):
    """Druckt Sektion."""
    print(f"\n{'─'*70}")
    print(f"  {title}")
    print('─'*70)


def print_metric(label: str, value: str, unit: str = ""):
    """Druckt Metrik."""
    print(f"   {label:30s} {value:>15s} {unit}")


async def get_stats() -> dict:
    """Holt Screen-Change-Stats."""
    return await call_tool("get_screen_change_stats")


async def reset_stats():
    """Setzt Stats zurück."""
    await call_tool("reset_screen_detector")


# ==============================================================================
# TEST-SZENARIEN
# ==============================================================================

async def scenario_simple_navigation():
    """
    Szenario 1: Einfache Navigation
    - Öffne Firefox (falls nicht offen)
    - Screenshot-Check mehrmals
    """
    print_header("SZENARIO 1: Einfache Navigation (Firefox öffnen)")

    # Stats zurücksetzen
    await reset_stats()
    print("✓ Stats zurückgesetzt\n")

    # Tools-Description (minimiert)
    tools_desc = """
    Available tools:
    - open_application(app_name): Öffnet eine Anwendung
    - click_at(x, y): Klickt an Position
    - type_text(text): Tippt Text
    - start_visual_browser(url): Öffnet Browser mit URL
    - finish_task(message): Beendet Task
    """

    # Agent erstellen
    print("📌 Erstelle VisualAgent...")
    agent = VisualAgent(tools_desc)

    if agent.use_screen_change_gate:
        print("✅ Screen-Change-Gate: AKTIV")
    else:
        print("⚠️  Screen-Change-Gate: INAKTIV")

    # Task definieren
    task = """
    Prüfe ob Firefox bereits geöffnet ist.
    Falls nicht, öffne Firefox mit start_visual_browser("https://google.com").
    Falls ja, sage einfach "Firefox ist bereits offen".
    """

    print(f"\n📋 Task:\n   {task.strip()}\n")

    # Stats VOR Ausführung
    stats_before = await get_stats()
    print("📊 Stats VOR Ausführung:")
    print_metric("Total Checks", str(stats_before.get("total_checks", 0)))
    print_metric("Cache-Hits", str(stats_before.get("cache_hits", 0)))

    # Task ausführen
    print("\n🚀 Starte Task-Ausführung...")
    start_time = time.time()

    try:
        result = await agent.run(task)
        execution_time = time.time() - start_time

        print(f"\n✅ Task abgeschlossen in {execution_time:.2f}s")
        print(f"\n📝 Ergebnis:\n   {result[:200]}...")

    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Stats NACH Ausführung
    stats_after = await get_stats()

    print_section("Performance-Metriken")

    # Berechne Differenzen
    checks_diff = stats_after.get("total_checks", 0) - stats_before.get("total_checks", 0)
    changes_diff = stats_after.get("changes_detected", 0) - stats_before.get("changes_detected", 0)
    cache_hits_diff = stats_after.get("cache_hits", 0) - stats_before.get("cache_hits", 0)

    print_metric("Ausführungszeit", f"{execution_time:.2f}", "s")
    print_metric("Screen-Checks (gesamt)", str(checks_diff))
    print_metric("Changes Detected", str(changes_diff))
    print_metric("Cache-Hits", str(cache_hits_diff))

    if checks_diff > 0:
        cache_rate = (cache_hits_diff / checks_diff) * 100
        print_metric("Cache-Hit-Rate", f"{cache_rate:.1f}", "%")

        # Geschätzte Ersparnis
        without_gate = checks_diff * 500  # ms pro Vision-Call (geschätzt)
        with_gate = (changes_diff * 500) + (cache_hits_diff * 23)  # 23ms pro Cache-Check
        savings = (1 - with_gate / without_gate) * 100 if without_gate > 0 else 0

        print_metric("Geschätzte Zeit-Ersparnis", f"{savings:.1f}", "%")

    return {
        "execution_time": execution_time,
        "checks": checks_diff,
        "changes": changes_diff,
        "cache_hits": cache_hits_diff,
        "stats": stats_after
    }


async def scenario_google_search():
    """
    Szenario 2: Google-Suche
    - Öffne Firefox mit Google
    - Suche nach "Timus AI"
    - Warte auf Ergebnisse
    """
    print_header("SZENARIO 2: Google-Suche (Browser + Formular)")

    # Stats zurücksetzen
    await reset_stats()
    print("✓ Stats zurückgesetzt\n")

    tools_desc = """
    Available tools:
    - start_visual_browser(url): Öffnet Browser mit URL
    - click_at(x, y): Klickt an Position
    - type_text(text): Tippt Text
    - hybrid_find_element(text, element_type): Findet UI-Element
    - hybrid_find_and_click(text, element_type): Findet und klickt Element
    - hybrid_find_text_field_and_type(text, field_text): Findet Textfeld und tippt
    - finish_task(message): Beendet Task
    """

    # Agent erstellen
    print("📌 Erstelle VisualAgent...")
    agent = VisualAgent(tools_desc)

    if agent.use_screen_change_gate:
        print("✅ Screen-Change-Gate: AKTIV")
    else:
        print("⚠️  Screen-Change-Gate: INAKTIV")

    # Task definieren
    task = """
    1. Öffne Firefox mit Google: start_visual_browser("https://google.com")
    2. Warte 3 Sekunden bis Seite geladen ist
    3. Finde das Suchfeld (meist in der Mitte)
    4. Klicke auf das Suchfeld
    5. Tippe "Timus AI"
    6. Drücke Enter oder klicke auf "Google Suche"
    7. Warte 2 Sekunden auf Ergebnisse
    8. Sage "Suche abgeschlossen"
    """

    print(f"\n📋 Task:\n   {task.strip()[:150]}...\n")

    # Stats VOR Ausführung
    stats_before = await get_stats()

    # Task ausführen
    print("🚀 Starte Task-Ausführung...")
    print("   (Das kann 30-60 Sekunden dauern)\n")
    start_time = time.time()

    try:
        result = await agent.run(task)
        execution_time = time.time() - start_time

        print(f"\n✅ Task abgeschlossen in {execution_time:.2f}s")
        print(f"\n📝 Ergebnis:\n   {result[:300]}...")

    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Stats NACH Ausführung
    stats_after = await get_stats()

    print_section("Performance-Metriken")

    # Berechne Differenzen
    checks_diff = stats_after.get("total_checks", 0) - stats_before.get("total_checks", 0)
    changes_diff = stats_after.get("changes_detected", 0) - stats_before.get("changes_detected", 0)
    cache_hits_diff = stats_after.get("cache_hits", 0) - stats_before.get("cache_hits", 0)

    print_metric("Ausführungszeit", f"{execution_time:.2f}", "s")
    print_metric("Screen-Checks (gesamt)", str(checks_diff))
    print_metric("Changes Detected", str(changes_diff))
    print_metric("Cache-Hits", str(cache_hits_diff))

    if checks_diff > 0:
        cache_rate = (cache_hits_diff / checks_diff) * 100
        print_metric("Cache-Hit-Rate", f"{cache_rate:.1f}", "%")

        # Geschätzte Ersparnis
        without_gate = checks_diff * 500  # ms pro Vision-Call
        with_gate = (changes_diff * 500) + (cache_hits_diff * 23)
        savings = (1 - with_gate / without_gate) * 100 if without_gate > 0 else 0

        print_metric("Geschätzte Zeit-Ersparnis", f"{savings:.1f}", "%")

        # Geschätzte Zeit ohne Gate
        time_without_gate = execution_time / (1 - savings/100) if savings > 0 else execution_time
        time_saved = time_without_gate - execution_time

        print_metric("Geschätzte Zeit ohne Gate", f"{time_without_gate:.2f}", "s")
        print_metric("Eingesparte Zeit", f"{time_saved:.2f}", "s")

    return {
        "execution_time": execution_time,
        "checks": checks_diff,
        "changes": changes_diff,
        "cache_hits": cache_hits_diff,
        "stats": stats_after
    }


async def scenario_element_detection():
    """
    Szenario 3: Element-Detection (viele Checks)
    - Suche mehrere Elemente auf dem Screen
    - Demonstriert Cache-Effekt bei statischem Screen
    """
    print_header("SZENARIO 3: Element-Detection (Cache-Effekt)")

    # Stats zurücksetzen
    await reset_stats()
    print("✓ Stats zurückgesetzt\n")

    print("📌 Test: Mehrfache Element-Suche auf statischem Screen")
    print("   (Simuliert Agent der mehrmals gleichen Screen analysiert)\n")

    # 10 Checks durchführen
    print("🔄 Führe 10 Screen-Checks durch...")

    start_time = time.time()
    results = []

    for i in range(10):
        result = await call_tool("should_analyze_screen")
        results.append(result.get("changed", True))
        print(f"   Check {i+1:2d}: changed={result.get('changed')}, "
              f"reason={result.get('info', {}).get('reason', 'unknown')}, "
              f"time={result.get('info', {}).get('check_time_ms', 0):.1f}ms")

        # Kurze Pause
        await asyncio.sleep(0.1)

    execution_time = time.time() - start_time

    # Stats
    stats = await get_stats()

    print_section("Performance-Metriken")

    changed_count = sum(1 for r in results if r)
    unchanged_count = 10 - changed_count

    print_metric("Total Checks", "10")
    print_metric("Changed", str(changed_count))
    print_metric("Unchanged (Cache-Hit)", str(unchanged_count))
    print_metric("Cache-Hit-Rate", f"{(unchanged_count/10)*100:.1f}", "%")
    print_metric("Total Zeit", f"{execution_time:.2f}", "s")
    print_metric("Avg Zeit pro Check", f"{(execution_time/10)*1000:.1f}", "ms")

    # Ersparnis berechnen
    # Ohne Gate: 10 × 500ms = 5000ms
    # Mit Gate: changed × 500ms + unchanged × 23ms
    without_gate = 10 * 500
    with_gate = (changed_count * 500) + (unchanged_count * 23)
    savings = (1 - with_gate / without_gate) * 100

    print_metric("Geschätzte Ersparnis", f"{savings:.1f}", "%")
    print_metric("Zeit ohne Gate", f"{without_gate/1000:.2f}", "s")
    print_metric("Zeit mit Gate", f"{with_gate/1000:.2f}", "s")
    print_metric("Eingesparte Zeit", f"{(without_gate - with_gate)/1000:.2f}", "s")

    return {
        "execution_time": execution_time,
        "checks": 10,
        "changed": changed_count,
        "unchanged": unchanged_count,
        "cache_rate": (unchanged_count/10)*100,
        "savings": savings
    }


# ==============================================================================
# MAIN
# ==============================================================================

async def main():
    """Hauptfunktion."""
    print("\n" + "="*70)
    print("  🚀 PRODUCTION-TEST: Screen-Change-Gate")
    print("="*70)
    print(f"  Datum: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  USE_SCREEN_CHANGE_GATE: {os.getenv('USE_SCREEN_CHANGE_GATE', 'false')}")
    print("="*70)

    # Prüfe ob MCP-Server läuft
    print("\n🔍 Prüfe MCP-Server...")
    try:
        health = await call_tool("get_screen_change_stats")
        if "error" in health:
            print(f"❌ MCP-Server nicht erreichbar: {health['error']}")
            print("\n⚠️  Starte MCP-Server mit:")
            print("   python server/mcp_server.py")
            return
        print("✅ MCP-Server läuft\n")
    except Exception as e:
        print(f"❌ MCP-Server Fehler: {e}")
        return

    # Menü
    print("\n📋 Verfügbare Szenarien:")
    print("   1. Einfache Navigation (Firefox Check)")
    print("   2. Google-Suche (Komplett-Workflow)")
    print("   3. Element-Detection (Cache-Effekt)")
    print("   4. Alle Szenarien nacheinander")
    print("   0. Abbrechen")

    choice = input("\n🔹 Wähle Szenario (1-4): ").strip()

    results = {}

    if choice == "1":
        results["scenario_1"] = await scenario_simple_navigation()
    elif choice == "2":
        results["scenario_2"] = await scenario_google_search()
    elif choice == "3":
        results["scenario_3"] = await scenario_element_detection()
    elif choice == "4":
        print("\n⏳ Führe alle Szenarien nacheinander aus...\n")
        results["scenario_1"] = await scenario_simple_navigation()
        await asyncio.sleep(2)
        results["scenario_2"] = await scenario_google_search()
        await asyncio.sleep(2)
        results["scenario_3"] = await scenario_element_detection()
    elif choice == "0":
        print("\n👋 Abgebrochen")
        return
    else:
        print(f"\n❌ Ungültige Auswahl: {choice}")
        return

    # Finale Zusammenfassung
    print_header("📊 GESAMT-ZUSAMMENFASSUNG")

    for name, result in results.items():
        if result:
            print(f"\n{name.upper().replace('_', ' ')}:")
            if "execution_time" in result:
                print(f"   Ausführungszeit: {result['execution_time']:.2f}s")
            if "checks" in result:
                print(f"   Screen-Checks: {result['checks']}")
            if "cache_hits" in result:
                cache_rate = (result['cache_hits'] / result['checks'] * 100) if result['checks'] > 0 else 0
                print(f"   Cache-Hit-Rate: {cache_rate:.1f}%")
            if "cache_rate" in result:
                print(f"   Cache-Hit-Rate: {result['cache_rate']:.1f}%")
            if "savings" in result:
                print(f"   Ersparnis: {result['savings']:.1f}%")

    # Finale Stats
    final_stats = await get_stats()
    print_section("Gesamt-Stats (Session)")
    print_metric("Total Checks", str(final_stats.get("total_checks", 0)))
    print_metric("Changes Detected", str(final_stats.get("changes_detected", 0)))
    print_metric("Cache-Hits", str(final_stats.get("cache_hits", 0)))
    print_metric("Cache-Hit-Rate", f"{final_stats.get('cache_hit_rate', 0)*100:.1f}", "%")
    print_metric("Avg Check-Zeit", f"{final_stats.get('avg_check_time_ms', 0):.1f}", "ms")
    print_metric("Performance", final_stats.get("performance", "unknown"))

    print("\n" + "="*70)
    print("  ✅ Production-Test abgeschlossen!")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Test abgebrochen (Ctrl+C)")
    finally:
        # Cleanup
        asyncio.run(http_client.aclose())

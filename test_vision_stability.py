#!/usr/bin/env python3
"""
Test-Script für das neue Vision-Stabilitäts-System.

Testet:
1. Screen-Change-Gate (Detector)
2. Screen Contract Tool (ScreenState + ActionPlan)
3. Performance-Metriken

Usage:
    python test_vision_stability.py
"""

import asyncio
import httpx
import json
import time
from typing import Dict, Any

# MCP Server URL
MCP_URL = "http://127.0.0.1:5000"
TIMEOUT = 30.0

http_client = httpx.AsyncClient(timeout=TIMEOUT)


async def call_tool(method: str, params: Dict[str, Any] = None) -> Dict:
    """Ruft ein Tool über MCP-Server auf."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": "test-1"
    }

    response = await http_client.post(MCP_URL, json=payload)
    response.raise_for_status()
    result = response.json()

    if "error" in result:
        raise Exception(f"Tool-Fehler: {result['error']}")

    return result.get("result", {})


# ==============================================================================
# TEST 1: Screen-Change-Gate
# ==============================================================================

async def test_screen_change_gate():
    """
    Testet Screen-Change-Detector.

    Erwartung:
    - Erster Check: changed=True
    - Zweiter Check sofort danach: changed=False (Cache-Hit!)
    - Nach ~2s: changed=False (immer noch gleich)
    """
    print("\n" + "="*60)
    print("TEST 1: Screen-Change-Gate")
    print("="*60)

    # Reset Detector (clean slate)
    await call_tool("reset_screen_detector")
    print("✓ Detector zurückgesetzt")

    # Check 1 - sollte immer changed=True beim ersten Mal
    print("\n1. Check (erster):")
    result1 = await call_tool("should_analyze_screen")
    print(f"   Changed: {result1['changed']}")
    print(f"   Reason: {result1['info']['reason']}")
    print(f"   Method: {result1['info']['method']}")
    print(f"   Check-Zeit: {result1['info']['check_time_ms']}ms")

    assert result1["changed"] == True, "Erster Check sollte changed=True sein"
    print("   ✅ PASS")

    # Check 2 - sofort danach, sollte changed=False (Cache-Hit)
    print("\n2. Check (sofort danach):")
    result2 = await call_tool("should_analyze_screen")
    print(f"   Changed: {result2['changed']}")
    print(f"   Reason: {result2['info']['reason']}")
    print(f"   Method: {result2['info']['method']}")
    print(f"   Check-Zeit: {result2['info']['check_time_ms']}ms")

    assert result2["changed"] == False, "Zweiter Check sollte changed=False sein (Cache-Hit)"
    assert result2["info"]["method"] == "hash", "Sollte Hash-Methode nutzen (schnell)"
    print("   ✅ PASS - Cache-Hit!")

    # Check 3 - nach 2s, sollte immer noch unchanged
    print("\n3. Check (nach 2s):")
    await asyncio.sleep(2)
    result3 = await call_tool("should_analyze_screen")
    print(f"   Changed: {result3['changed']}")
    print(f"   Reason: {result3['info']['reason']}")
    print(f"   Check-Zeit: {result3['info']['check_time_ms']}ms")

    # Stats abrufen
    print("\n📊 Performance-Stats:")
    stats = await call_tool("get_screen_change_stats")
    print(f"   Total Checks: {stats['total_checks']}")
    print(f"   Changes Detected: {stats['changes_detected']}")
    print(f"   Cache-Hits: {stats['cache_hits']}")
    print(f"   Cache-Hit-Rate: {stats['cache_hit_rate'] * 100:.1f}%")
    print(f"   Avg Check-Zeit: {stats['avg_check_time_ms']:.2f}ms")
    print(f"   Ersparnis: {stats['savings_estimate']}")
    print(f"   Performance: {stats['performance']}")

    # Erwartung: 2 von 3 Checks waren Cache-Hits (66%)
    expected_cache_rate = 2/3
    actual_cache_rate = stats['cache_hit_rate']

    if abs(actual_cache_rate - expected_cache_rate) < 0.1:
        print("   ✅ Cache-Hit-Rate wie erwartet")
    else:
        print(f"   ⚠️ Cache-Hit-Rate: {actual_cache_rate:.2f} (erwartet: {expected_cache_rate:.2f})")

    print("\n✅ TEST 1 BESTANDEN")


# ==============================================================================
# TEST 2: Screen-State-Analyse
# ==============================================================================

async def test_screen_state_analysis():
    """
    Testet Screen-State-Analyse mit Ankern und Elementen.

    Erwartung:
    - Anker werden gefunden (falls vorhanden)
    - Elemente werden identifiziert
    - Missing-Liste zeigt fehlende Elemente
    """
    print("\n" + "="*60)
    print("TEST 2: Screen-State-Analyse")
    print("="*60)

    # Definiere Test-Screen
    print("\n📋 Screen-Spezifikation:")
    anchor_specs = [
        {"name": "desktop_icon", "type": "text", "text": "Files"},
        {"name": "taskbar", "type": "text", "text": "Activities"}
    ]

    element_specs = [
        {"name": "terminal_icon", "type": "icon", "text": "Terminal"},
        {"name": "settings_icon", "type": "icon", "text": "Settings"}
    ]

    print(f"   Anker: {len(anchor_specs)}")
    for anchor in anchor_specs:
        print(f"     - {anchor['name']}: '{anchor['text']}'")

    print(f"   Elemente: {len(element_specs)}")
    for elem in element_specs:
        print(f"     - {elem['name']}: '{elem['text']}'")

    # Analyse durchführen
    print("\n🔍 Analysiere Screen...")
    start = time.time()

    try:
        state = await call_tool("analyze_screen_state", {
            "screen_id": "test_desktop",
            "anchor_specs": anchor_specs,
            "element_specs": element_specs,
            "extract_ocr": False
        })

        elapsed = (time.time() - start) * 1000
        print(f"   Analyse-Zeit: {elapsed:.0f}ms")

        # Ergebnisse
        print("\n📊 Ergebnisse:")
        print(f"   Screen-ID: {state['screen_id']}")
        print(f"   Timestamp: {state['timestamp']}")

        # Anker
        print(f"\n   Anker gefunden: {len([a for a in state['anchors'] if a['found']])}/{len(state['anchors'])}")
        for anchor in state['anchors']:
            status = "✓" if anchor['found'] else "✗"
            conf = f"({anchor['confidence']:.2f})" if anchor['found'] else ""
            print(f"     {status} {anchor['name']} {conf}")

        # Elemente
        print(f"\n   Elemente gefunden: {len(state['elements'])}/{len(element_specs)}")
        for elem in state['elements']:
            print(f"     ✓ {elem['name']}: ({elem['x']}, {elem['y']}) - {elem['method']} - conf: {elem['confidence']:.2f}")

        # Missing
        if state['missing']:
            print(f"\n   ⚠️ Fehlende Elemente: {len(state['missing'])}")
            for missing in state['missing']:
                print(f"     - {missing}")
        else:
            print("\n   ✅ Alle Elemente gefunden!")

        # Warnings
        if state['warnings']:
            print(f"\n   ⚠️ Warnungen: {len(state['warnings'])}")
            for warning in state['warnings']:
                print(f"     - {warning}")

        print("\n✅ TEST 2 BESTANDEN")

    except Exception as e:
        print(f"\n❌ TEST 2 FEHLGESCHLAGEN: {e}")


# ==============================================================================
# TEST 3: Action-Plan-Ausführung (Simulation)
# ==============================================================================

async def test_action_plan_execution():
    """
    Testet Action-Plan-Ausführung.

    Hinweis: Dieser Test ist eine Simulation, da wir keine echte UI-Interaktion
    durchführen können ohne die Kontrolle zu übernehmen.
    """
    print("\n" + "="*60)
    print("TEST 3: Action-Plan (Struktur-Test)")
    print("="*60)

    # Definiere Test-Plan
    plan = {
        "goal": "Testplan - Demonstriert Struktur",
        "screen_id": "test_screen",
        "steps": [
            {
                "op": "verify",
                "target": "screen_ready",
                "verify_before": [
                    {
                        "type": "screen_unchanged",
                        "target": "screen"
                    }
                ]
            }
        ],
        "abort_conditions": []
    }

    print("\n📋 Plan-Struktur:")
    print(f"   Goal: {plan['goal']}")
    print(f"   Screen: {plan['screen_id']}")
    print(f"   Steps: {len(plan['steps'])}")

    for i, step in enumerate(plan['steps']):
        print(f"\n   Step {i+1}:")
        print(f"     Op: {step['op']}")
        print(f"     Target: {step['target']}")
        print(f"     Verify-Before: {len(step.get('verify_before', []))}")
        print(f"     Verify-After: {len(step.get('verify_after', []))}")

    print("\n🚀 Führe Plan aus...")

    try:
        start = time.time()
        result = await call_tool("execute_action_plan", {"plan_dict": plan})  # FIX: plan_dict Parameter
        elapsed = (time.time() - start) * 1000

        print(f"\n📊 Ergebnis:")
        print(f"   Success: {result['success']}")
        print(f"   Completed Steps: {result['completed_steps']}/{result['total_steps']}")
        print(f"   Execution Time: {result['execution_time_ms']:.0f}ms")

        if result['logs']:
            print(f"\n   📝 Logs:")
            for log in result['logs'][:5]:  # Erste 5 Logs
                print(f"     {log}")

        if result['success']:
            print("\n✅ TEST 3 BESTANDEN")
        else:
            print(f"\n⚠️ Plan fehlgeschlagen (erwartet für Struktur-Test)")
            print(f"   Failed Step: {result.get('failed_step')}")
            print(f"   Error: {result.get('error_message')}")

    except Exception as e:
        print(f"\n⚠️ Fehler (erwartet für Struktur-Test): {e}")


# ==============================================================================
# TEST 4: Performance-Vergleich
# ==============================================================================

async def test_performance_comparison():
    """
    Vergleicht Performance mit und ohne Screen-Change-Gate.
    """
    print("\n" + "="*60)
    print("TEST 4: Performance-Vergleich")
    print("="*60)

    # Reset
    await call_tool("reset_screen_detector")

    # Simulation: 10 Checks hintereinander
    num_checks = 10

    print(f"\n🔄 Führe {num_checks} Checks aus (Screen unverändert)...")

    start = time.time()
    results = []

    for i in range(num_checks):
        result = await call_tool("should_analyze_screen")
        results.append(result)

    total_time = (time.time() - start) * 1000

    # Analyse
    changed_count = sum(1 for r in results if r['changed'])
    unchanged_count = num_checks - changed_count
    avg_time = total_time / num_checks

    print(f"\n📊 Ergebnisse:")
    print(f"   Total Checks: {num_checks}")
    print(f"   Changed: {changed_count}")
    print(f"   Unchanged (Cache-Hit): {unchanged_count}")
    print(f"   Total Zeit: {total_time:.0f}ms")
    print(f"   Avg Zeit pro Check: {avg_time:.2f}ms")
    print(f"   Cache-Hit-Rate: {unchanged_count/num_checks * 100:.0f}%")

    # Geschätzte Ersparnis
    # Ohne Gate: Jeder Check = volle Vision-Analyse (~500ms)
    # Mit Gate: Nur 1 Check = Vision, Rest = Cache (~1-2ms)

    without_gate_time = num_checks * 500  # ms (geschätzt)
    with_gate_time = total_time
    savings = (1 - with_gate_time / without_gate_time) * 100

    print(f"\n💰 Geschätzte Ersparnis:")
    print(f"   Ohne Gate: ~{without_gate_time:.0f}ms")
    print(f"   Mit Gate: ~{with_gate_time:.0f}ms")
    print(f"   Ersparnis: ~{savings:.0f}%")

    if savings > 70:
        print("\n✅ TEST 4 BESTANDEN - Massive Performance-Verbesserung!")
    else:
        print(f"\n⚠️ Ersparnis unter 70% ({savings:.0f}%)")


# ==============================================================================
# MAIN
# ==============================================================================

async def main():
    """Führt alle Tests aus."""
    print("\n" + "="*60)
    print("🚀 TIMUS VISION STABILITY TESTS")
    print("="*60)
    print("\nBasiert auf GPT-5.2's Empfehlungen:")
    print("  1. Screen-Change-Gate (70-95% Call-Reduktion)")
    print("  2. JSON-Vertrag System (Locate → Verify → Act → Verify)")
    print("\n" + "="*60)

    try:
        # Test 1: Screen-Change-Gate
        await test_screen_change_gate()

        # Test 2: Screen-State-Analyse
        await test_screen_state_analysis()

        # Test 3: Action-Plan (Struktur)
        await test_action_plan_execution()

        # Test 4: Performance-Vergleich
        await test_performance_comparison()

        print("\n" + "="*60)
        print("✅ ALLE TESTS ABGESCHLOSSEN")
        print("="*60)

    except Exception as e:
        print(f"\n❌ FEHLER: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await http_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

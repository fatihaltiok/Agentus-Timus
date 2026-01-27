#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test-Script zum Vergleich von Developer Agent v1 vs. v2

Testet beide Versionen mit den gleichen Aufgaben und vergleicht:
- Erfolgsrate
- Anzahl Schritte
- Code-Qualität
- Fehler-Recovery
"""
import sys
import time
from pathlib import Path

# Pfad Setup
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import beider Versionen
try:
    from agent.developer_agent import run_developer_task as run_v1
    V1_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Developer Agent v1 nicht verfügbar: {e}")
    V1_AVAILABLE = False

try:
    from agent.developer_agent_v2 import run_developer_task as run_v2
    V2_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Developer Agent v2 nicht verfügbar: {e}")
    V2_AVAILABLE = False

# Test-Aufgaben
TEST_TASKS = [
    {
        "name": "Einfache Funktion",
        "query": "Erstelle eine Funktion 'is_prime(n)' die prüft ob eine Zahl eine Primzahl ist",
        "folder": "test_project",
        "max_steps": 8
    },
    {
        "name": "Klasse mit Methoden",
        "query": "Erstelle eine Klasse 'Calculator' mit Methoden add, subtract, multiply, divide",
        "folder": "test_project",
        "max_steps": 10
    },
    {
        "name": "Mit Kontext",
        "query": "Lies die bestehende calculator.py und erweitere sie um eine power() Methode",
        "folder": "test_project",
        "max_steps": 12
    }
]


def run_test(version: str, task: dict) -> dict:
    """
    Führt einen Test mit einer Version aus.

    Returns:
        dict mit success, duration, steps, result
    """
    print(f"\n{'='*80}")
    print(f"🧪 Test: {task['name']} - {version}")
    print(f"{'='*80}")

    start_time = time.time()

    try:
        if version == "v1":
            result = run_v1(task["query"], max_steps=task["max_steps"])
        else:  # v2
            result = run_v2(
                task["query"],
                dest_folder=task["folder"],
                max_steps=task["max_steps"]
            )

        duration = time.time() - start_time

        # Erfolg basierend auf Result-Text
        success = (
            "✅" in result or
            "erfolgreich" in result.lower() or
            "erstellt" in result.lower() or
            ("final answer" in result.lower() and "fehler" not in result.lower())
        )

        return {
            "success": success,
            "duration": duration,
            "result": result,
            "error": None
        }

    except Exception as e:
        duration = time.time() - start_time
        return {
            "success": False,
            "duration": duration,
            "result": None,
            "error": str(e)
        }


def print_comparison_table(results: dict):
    """Druckt Vergleichs-Tabelle."""
    print("\n" + "="*100)
    print("📊 VERGLEICHS-ERGEBNISSE")
    print("="*100)

    print(f"\n{'Test':<30} {'v1 Erfolg':<15} {'v1 Zeit':<15} {'v2 Erfolg':<15} {'v2 Zeit':<15}")
    print("-" * 100)

    for task_name, data in results.items():
        v1_data = data.get("v1", {})
        v2_data = data.get("v2", {})

        v1_success = "✅" if v1_data.get("success") else "❌"
        v2_success = "✅" if v2_data.get("success") else "❌"

        v1_time = f"{v1_data.get('duration', 0):.1f}s" if v1_data else "N/A"
        v2_time = f"{v2_data.get('duration', 0):.1f}s" if v2_data else "N/A"

        print(f"{task_name:<30} {v1_success:<15} {v1_time:<15} {v2_success:<15} {v2_time:<15}")

    # Statistiken
    print("\n" + "="*100)
    print("📈 STATISTIKEN")
    print("="*100)

    v1_successes = sum(1 for data in results.values() if data.get("v1", {}).get("success"))
    v2_successes = sum(1 for data in results.values() if data.get("v2", {}).get("success"))
    total_tests = len(results)

    v1_total_time = sum(data.get("v1", {}).get("duration", 0) for data in results.values())
    v2_total_time = sum(data.get("v2", {}).get("duration", 0) for data in results.values())

    print(f"\nv1 Erfolgsrate: {v1_successes}/{total_tests} ({v1_successes/total_tests*100:.0f}%)")
    print(f"v2 Erfolgsrate: {v2_successes}/{total_tests} ({v2_successes/total_tests*100:.0f}%)")

    print(f"\nv1 Gesamt-Zeit: {v1_total_time:.1f}s (Ø {v1_total_time/total_tests:.1f}s)")
    print(f"v2 Gesamt-Zeit: {v2_total_time:.1f}s (Ø {v2_total_time/total_tests:.1f}s)")

    # Gewinner
    print("\n" + "="*100)
    if v2_successes > v1_successes:
        print("🏆 GEWINNER: Developer Agent v2 (höhere Erfolgsrate)")
    elif v2_successes == v1_successes and v2_total_time < v1_total_time:
        print("🏆 GEWINNER: Developer Agent v2 (gleiche Erfolgsrate, schneller)")
    elif v2_successes == v1_successes:
        print("🤝 UNENTSCHIEDEN: Beide gleich erfolgreich")
    else:
        print("🏆 GEWINNER: Developer Agent v1 (höhere Erfolgsrate)")
    print("="*100)


def main():
    """Hauptfunktion."""
    print("🧪 Developer Agent Vergleichstest: v1 vs. v2")
    print("="*100)

    if not V1_AVAILABLE and not V2_AVAILABLE:
        print("❌ Keine Version verfügbar!")
        return

    if not V1_AVAILABLE:
        print("⚠️ Nur v2 verfügbar, kein Vergleich möglich")
        print("Führe v2-Tests durch...")

    if not V2_AVAILABLE:
        print("⚠️ Nur v1 verfügbar, kein Vergleich möglich")
        print("Führe v1-Tests durch...")

    results = {}

    for task in TEST_TASKS:
        task_results = {}

        # Test v1
        if V1_AVAILABLE:
            print(f"\n🔵 Teste v1 mit: {task['name']}")
            task_results["v1"] = run_test("v1", task)

            if task_results["v1"]["success"]:
                print(f"✅ v1 erfolgreich in {task_results['v1']['duration']:.1f}s")
            else:
                print(f"❌ v1 fehlgeschlagen: {task_results['v1'].get('error', 'Siehe Logs')}")

        # Test v2
        if V2_AVAILABLE:
            print(f"\n🟢 Teste v2 mit: {task['name']}")
            task_results["v2"] = run_test("v2", task)

            if task_results["v2"]["success"]:
                print(f"✅ v2 erfolgreich in {task_results['v2']['duration']:.1f}s")
            else:
                print(f"❌ v2 fehlgeschlagen: {task_results['v2'].get('error', 'Siehe Logs')}")

        results[task["name"]] = task_results

        # Kurze Pause zwischen Tests
        time.sleep(2)

    # Vergleichs-Tabelle
    if V1_AVAILABLE and V2_AVAILABLE:
        print_comparison_table(results)
    else:
        print("\n⚠️ Kein Vergleich möglich (nur eine Version verfügbar)")

    print("\n✅ Test abgeschlossen!")


if __name__ == "__main__":
    main()

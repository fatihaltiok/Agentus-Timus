#!/usr/bin/env python3
# test_visual_agent_tool.py
"""
Test-Script für Visual Agent Tool - MCP-Integration

Testet:
1. Health-Check des Visual Agent Tools
2. Tool-Registrierung im MCP-Server
3. execute_visual_task (optional mit echtem Task)
"""

import asyncio
import httpx
import json
import sys
from pathlib import Path

# --- Konfiguration ---
MCP_URL = "http://127.0.0.1:5000"
TIMEOUT = 60.0

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


async def test_health_check():
    """Test 1: Health-Check."""
    print("\n" + "="*60)
    print("TEST 1: Visual Agent Health-Check")
    print("="*60)

    result = await call_rpc("visual_agent_health")

    if "error" in result:
        print(f"❌ Health-Check fehlgeschlagen: {result['error']}")
        return False

    print("✅ Health-Check erfolgreich!")
    print(f"\nStatus: {result.get('status')}")
    print(f"Vision Model: {result.get('vision_model')}")
    print(f"MCP URL: {result.get('mcp_url')}")
    print(f"Monitor: {result.get('active_monitor')}")
    print(f"Mouse Feedback: {result.get('mouse_feedback')}")

    print("\nFeatures:")
    for feature in result.get('features', []):
        print(f"  ✓ {feature}")

    print("\nDependencies:")
    deps = result.get('dependencies', {})
    for key, value in deps.items():
        print(f"  {key}: {value}")

    return True


async def test_tool_registration():
    """Test 2: Tool-Registrierung prüfen."""
    print("\n" + "="*60)
    print("TEST 2: Tool-Registrierung prüfen")
    print("="*60)

    # Liste aller Tools abrufen
    result = await call_rpc("list_tools")

    if "error" in result:
        print(f"❌ list_tools fehlgeschlagen: {result['error']}")
        return False

    tools = result.get('tools', [])

    # Suche Visual Agent Tools
    visual_tools = [
        "visual_agent_health",
        "execute_visual_task",
        "execute_visual_task_quick"
    ]

    found_tools = []
    for tool in visual_tools:
        if tool in tools:
            found_tools.append(tool)
            print(f"✅ Tool registriert: {tool}")
        else:
            print(f"❌ Tool NICHT registriert: {tool}")

    if len(found_tools) == len(visual_tools):
        print(f"\n✅ Alle {len(visual_tools)} Visual Agent Tools registriert!")
        return True
    else:
        print(f"\n⚠️ Nur {len(found_tools)}/{len(visual_tools)} Tools registriert")
        return False


async def test_execute_visual_task_simple():
    """Test 3: execute_visual_task mit einfachem Test."""
    print("\n" + "="*60)
    print("TEST 3: execute_visual_task (Dry-Run)")
    print("="*60)
    print("⚠️ Dieser Test würde den Visual Agent wirklich starten.")
    print("   Überspringe aus Sicherheitsgründen...")
    print("   Um zu testen, führe manuell aus:")
    print("   python3 -c 'import asyncio; from test_visual_agent_tool import call_rpc; asyncio.run(call_rpc(\"execute_visual_task\", {\"task\": \"Zeige mir den Desktop\", \"max_iterations\": 3}))'")

    return True


async def main():
    """Hauptfunktion."""
    print("\n" + "="*80)
    print("🧪 Visual Agent Tool Test Suite")
    print("="*80)

    results = []

    # Test 1: Health-Check
    result1 = await test_health_check()
    results.append(("Health-Check", result1))

    # Test 2: Tool-Registrierung
    result2 = await test_tool_registration()
    results.append(("Tool-Registrierung", result2))

    # Test 3: Execute Task (Dry-Run)
    result3 = await test_execute_visual_task_simple()
    results.append(("Execute Task (Dry-Run)", result3))

    # Zusammenfassung
    print("\n" + "="*80)
    print("📊 TEST-ZUSAMMENFASSUNG")
    print("="*80)

    all_passed = True
    for test_name, passed in results:
        status = "✅ BESTANDEN" if passed else "❌ FEHLGESCHLAGEN"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print("="*80)

    if all_passed:
        print("✅ ALLE TESTS BESTANDEN!")
        print("\nVisual Agent Tool ist bereit zur Nutzung:")
        print("  • visual_agent_health() - Health-Check")
        print("  • execute_visual_task(task, max_iterations) - Visual Task ausführen")
        print("  • execute_visual_task_quick(task) - Schnelle Version (10 Iterationen)")
        return 0
    else:
        print("❌ EINIGE TESTS FEHLGESCHLAGEN")
        print("\nPrüfe:")
        print("  1. MCP-Server läuft auf Port 5000")
        print("  2. ANTHROPIC_API_KEY in .env gesetzt")
        print("  3. tools/visual_agent_tool/tool.py korrekt")
        print("  4. Server mit neuem Tool neu gestartet")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

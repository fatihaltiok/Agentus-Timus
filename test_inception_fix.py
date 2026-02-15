#!/usr/bin/env python3
"""
Testet die Inception-Tool Fixes.
"""

import asyncio
import sys
import os

# Setze PYTHONPATH
sys.path.insert(0, os.path.dirname(__file__))

async def test_inception():
    """Testet Inception Health-Check."""
    print("="*60)
    print("🧪 Teste Inception-Tool Fix")
    print("="*60)

    # Importiere nach PYTHONPATH-Setup
    from tools.inception_tool.tool import inception_health, generate_and_integrate, INCEPTION_URL
    from tools.universal_tool_caller import tool_caller_instance

    print(f"\n📍 INCEPTION_URL: {INCEPTION_URL}")

    # Zeige registrierte Tools
    tools = tool_caller_instance.list_registered_tools()
    inception_tools = [t for t in tools if 'inception' in t.lower() or 'generate' in t.lower()]

    print(f"\n✅ Registrierte Inception-Tools ({len(inception_tools)}):")
    for tool in sorted(inception_tools):
        print(f"  - {tool}")

    # Teste Health-Check
    print("\n🩺 Führe Health-Check aus...")
    try:
        result = await inception_health()
        print(f"✅ Health-Check erfolgreich!")

        if hasattr(result, 'result'):
            data = result.result
            print(f"\nStatus: {data.get('status')}")
            print(f"URL: {data.get('inception_url')}")
            print(f"Python: {data.get('python_executable')}")
            print(f"\nAbhängigkeiten:")
            for dep, status in data.get('dependencies', {}).items():
                print(f"  - {dep}: {status}")
        else:
            print(f"Ergebnis: {result}")

    except Exception as e:
        print(f"❌ Health-Check fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)
    print("✅ Test abgeschlossen!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_inception())

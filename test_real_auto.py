#!/usr/bin/env python3
"""
Non-Interactive Real Scenario Test
"""
import subprocess
import time
import sys
import asyncio

sys.path.insert(0, "/home/fatih-ubuntu/dev/timus")

from tools.moondream_tool.tool import describe_ui_with_moondream, find_element_with_moondream

async def test_non_interactive():
    # Chrome öffnen
    url = "https://example.com"
    print(f"Öffne Chrome mit '{url}'...")
    subprocess.Popen(["google-chrome", url])
    time.sleep(3)  # Warten bis Seite geladen ist
    print("Chrome geöffnet, warte noch 2s...")
    time.sleep(2)
    
    print("\n" + "=" * 60)
    print("Analyse des Screenshots:")
    print("=" * 60)
    
    print("\n1. Describe UI:")
    try:
        result = await describe_ui_with_moondream()
        desc = result.result.get("description", "") if hasattr(result, 'result') else str(result)
        print(f"Resultat: {desc[:500]}...")
    except Exception as e:
        print(f"ERROR: {e}")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_non_interactive())
    print(f"\nTest {'erfolgreich' if success else 'fehlgeschlagen'}!")

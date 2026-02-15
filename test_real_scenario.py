#!/usr/bin/env python3
"""
Real Scenario Test - Testet Moondream mit echten Browser Screenshots
"""
import sys
import asyncio
import os
import subprocess
import time

sys.path.insert(0, "/home/fatih-ubuntu/dev/timus")

from tools.moondream_tool.tool import describe_ui_with_moondream, find_element_with_moondream

def open_chrome_with_example():
    """Öffnet Chrome mit einer Beispiel-Website."""
    url = "https://example.com"
    try:
        # Chrome öffnen
        subprocess.Popen(["google-chrome", url])
        print(f"Chrome wurde mit '{url}' geöffnet")
        time.sleep(2)  # Warten bis Chrome geladen ist
    except FileNotFoundError:
        print("Google Chrome nicht gefunden. Öffne Chrome manuell.")
        input("Drücke Enter wenn Chrome mit example.com geöffnet ist...")

async def test_real_scenario():
    print("=" * 60)
    print("Real Scenario Test: example.com Screenshot")
    print("=" * 60)
    
    # Chrome öffnen
    print("Öffne Chrome mit example.com...")
    open_chrome_with_example()
    
    input("\nDrücke Enter wenn Chrome mit example.com vollständig geladen ist...")
    
    print("\n1. Describe UI with Moondream (Optimized Prompts):")
    print("-" * 60)
    try:
        result = await describe_ui_with_moondream()
        desc = result.result.get("description", "") if hasattr(result, 'result') else str(result)
        print(f"Antwort:\n{desc}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n2. Find Element 'More information' button:")
    print("-" * 60)
    try:
        result = await find_element_with_moondream("More information button")
        print(f"Result:\n{result}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    print("\n3. Find Element 'Example Domain' heading:")
    print("-" * 60)
    try:
        result = await find_element_with_moondream("Example Domain heading")
        print(f"Result:\n{result}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_real_scenario())

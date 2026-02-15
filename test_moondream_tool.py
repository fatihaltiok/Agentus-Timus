#!/usr/bin/env python3
"""
Test Moondream Tools (moondream_tool und som_tool) direkt
"""
import sys
import asyncio
import os

# Füge Projekt-Verzeichnis zum Pfad hinzu
sys.path.insert(0, "/home/fatih-ubuntu/dev/timus")

from tools.moondream_tool.tool import describe_screen_with_moondream, point_objects_with_moondream
from tools.som_tool.tool import scan_ui_elements

async def test_moondream_tools():
    print("=" * 60)
    print("TEST 1: describe_screen_with_moondream")
    print("=" * 60)
    
    try:
        result = await describe_screen_with_moondream("What do you see?")
        print(f"Result: {result}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("TEST 2: point_objects_with_moondream")
    print("=" * 60)
    
    try:
        result = await point_objects_with_moondream("button")
        print(f"Result: {result}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("TEST 3: scan_ui_elements")
    print("=" * 60)
    
    try:
        result = await scan_ui_elements(["button", "text field"])
        print(f"Result: {result}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_moondream_tools())

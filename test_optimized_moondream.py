#!/usr/bin/env python3
"""
Test optimierte Moondream Tools
"""
import sys
import asyncio
import os

sys.path.insert(0, "/home/fatih-ubuntu/dev/timus")

from tools.moondream_tool.tool import describe_ui_with_moondream, find_element_with_moondream

async def test_optimized_prompts():
    print("=" * 60)
    print("TEST 1: describe_ui_with_moondream (Optimized - English + Reasoning Mode)")
    print("=" * 60)
    
    try:
        result = await describe_ui_with_moondream()
        print(f"Success: {result}")
        print(f"\nDescription:")
        desc = result.result.get("description", "") if hasattr(result, 'result') else str(result)
        print(desc if isinstance(desc, str) else str(desc)[:500])
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("TEST 2: find_element_with_moondream (Optimized - English + Reasoning Mode)")
    print("=" * 60)
    
    try:
        result = await find_element_with_moondream("submit button")
        print(f"Success: {result}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_optimized_prompts())

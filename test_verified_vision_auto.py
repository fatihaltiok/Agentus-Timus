#!/usr/bin/env python3
"""
Auto-Test für Verified Vision Tool (non-interactive)
"""
import sys
import asyncio

sys.path.insert(0, "/home/fatih-ubuntu/dev/timus")

from tools.verified_vision_tool.tool import analyze_screen_verified, find_element_verified

async def test_verified_vision_auto():
    print("=" * 70)
    print("AUTO-TEST: Verified Vision Tool")
    print("=" * 70)
    print("Dieser Test kombiniert Moondream + OCR + LLM")
    print("Testet mit aktuellem Screenshot in 3 Sekunden...")
    await asyncio.sleep(3)
    
    print("\n" + "=" * 70)
    print("TEST 1: analyze_screen_verified()")
    print("=" * 70)
    
    try:
        result = await analyze_screen_verified(
            target_elements=["buttons", "input fields", "links"],
            min_confidence=0.6,
            verify_with_ocr=True,
            verify_with_llm=True
        )
        
        # Handle jsonrpcserver Result
        if hasattr(result, 'result'):
            data = result.result
        elif hasattr(result, 'is_success') and result.is_success:
            data = result.result
        else:
            print(f"❌ Error: {result}")
            return
        
        if isinstance(data, dict):
            print(f"✅ Total Elements: {data.get('total', 0)}")
            print(f"✅ Filtered (≥0.6): {data.get('filtered_count', 0)}")
            print(f"✅ Verified: {data.get('verified_count', 0)}")
            elements = data.get('verified_elements', [])
        else:
            print(f"Result: {data}")
            elements = []
        print(f"\nTop 3 Elements:")
        for i, elem in enumerate(elements[:3], 1):
            verified_mark = "✓" if elem.get('verified') else "○"
            print(f"  {verified_mark} [{i}] {elem.get('type', 'unknown')}: "
                  f"'{elem.get('label', 'N/A')[:30]}...' "
                  f"conf={elem.get('confidence', 0):.2f}")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("TEST 2: find_element_verified('button')")
    print("=" * 70)
    
    try:
        result = await find_element_verified("button", min_confidence=0.5)
        
        # Handle jsonrpcserver Result
        if hasattr(result, 'result'):
            data = result.result
        elif hasattr(result, 'is_success') and result.is_success:
            data = result.result
        else:
            print(f"❌ Error: {result}")
            return
        
        if isinstance(data, dict):
            if data.get('found'):
                elem = data.get('element', {})
                print(f"✅ Found: {elem.get('type')} '{elem.get('label')}'")
                print(f"   Click: ({elem.get('click_coordinates', {}).get('x', 0)}, "
                      f"{elem.get('click_coordinates', {}).get('y', 0)})")
                print(f"   Confidence: {elem.get('confidence', 0):.2f}")
                print(f"   Verified: {elem.get('verified', False)}")
            else:
                print(f"⚠️ Not found: {data.get('message', 'N/A')}")
        else:
            print(f"Result: {data}")
                
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("TEST ABGESCHLOSSEN")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_verified_vision_auto())

#!/usr/bin/env python3
"""
Test für Verified Vision Tool
Testet die Multi-Layer Verifikation: Moondream + OCR + LLM
"""
import sys
import asyncio

sys.path.insert(0, "/home/fatih-ubuntu/dev/timus")

from tools.verified_vision_tool.tool import analyze_screen_verified, find_element_verified

async def test_verified_vision():
    print("=" * 70)
    print("TEST: Verified Vision Tool (Multi-Layer)")
    print("=" * 70)
    print("\nDieser Test kombiniert:")
    print("  1. Moondream (visuelle Extraktion)")
    print("  2. OCR (Text-Verifikation)")
    print("  3. LLM (Plausibilitätsprüfung)")
    print("\nStelle sicher, dass der Bildschirm sichtbare UI-Elemente zeigt!")
    input("\nDrücke ENTER wenn bereit...")
    
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
        
        if hasattr(result, 'result'):
            data = result.result
        else:
            data = result
        
        print(f"\n✅ Ergebnis:")
        print(f"   Total Elements: {data.get('total', 0)}")
        print(f"   Filtered (≥0.6): {data.get('filtered_count', 0)}")
        print(f"   Verified: {data.get('verified_count', 0)}")
        print(f"   High Confidence (≥0.8): {data.get('high_confidence_elements', 0)}")
        
        elements = data.get('verified_elements', [])
        print(f"\n   Top 5 Elements:")
        for i, elem in enumerate(elements[:5], 1):
            verified_mark = "✓" if elem.get('verified') else "○"
            print(f"   {verified_mark} [{i}] {elem.get('type', 'unknown')}: "
                  f"'{elem.get('label', 'N/A')}' "
                  f"@ ({elem.get('position', {}).get('x', 0):.2f}, "
                  f"{elem.get('position', {}).get('y', 0):.2f}) "
                  f"[conf: {elem.get('confidence', 0):.2f}]")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("TEST 2: find_element_verified('submit button')")
    print("=" * 70)
    
    try:
        result = await find_element_verified("submit button", min_confidence=0.6)
        
        if hasattr(result, 'result'):
            data = result.result
        else:
            data = result
        
        if data.get('found'):
            elem = data.get('element', {})
            print(f"\n✅ Element gefunden:")
            print(f"   Type: {elem.get('type')}")
            print(f"   Label: {elem.get('label')}")
            print(f"   Position: ({elem.get('position', {}).get('x', 0):.3f}, "
                  f"{elem.get('position', {}).get('y', 0):.3f})")
            print(f"   Click: ({elem.get('click_coordinates', {}).get('x', 0)}, "
                  f"{elem.get('click_coordinates', {}).get('y', 0)})")
            print(f"   Confidence: {elem.get('confidence', 0):.2f}")
            print(f"   Verified: {elem.get('verified', False)}")
            print(f"   Sources: {', '.join(elem.get('sources', []))}")
            print(f"   Reasoning: {elem.get('reasoning', 'N/A')[:100]}...")
        else:
            print(f"\n⚠️ Element nicht gefunden")
            print(f"   Message: {data.get('message', 'N/A')}")
        
        if data.get('alternatives'):
            print(f"\n   Alternativen:")
            for alt in data.get('alternatives', [])[:3]:
                print(f"     - {alt.get('type')}: '{alt.get('label')}' [conf: {alt.get('confidence', 0):.2f}]")
                
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("TEST ABGESCHLOSSEN")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_verified_vision())

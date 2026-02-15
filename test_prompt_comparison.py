#!/usr/bin/env python3
"""
Vergleich Test: Alte vs Neue Moondream Prompts
Zeigt den Unterschied zwischen Deutschen/English Prompts mit/ohne Reasoning Mode
"""
import sys
import asyncio
import os
import base64
import httpx
from PIL import Image
import io
import mss

sys.path.insert(0, "/home/fatih-ubuntu/dev/timus")

MOONDREAM_BASE_URL = os.getenv("MOONDREAM_API_BASE", "http://localhost:2022/v1")

def capture_screenshot_base64() -> str:
    """Macht einen Screenshot und gibt Base64 zurück."""
    with mss.mss() as sct:
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

async def call_moondream_api(question: str, description: str):
    """Ruft Moondream mit einer Frage auf."""
    client = httpx.AsyncClient(timeout=60.0)
    
    try:
        b64_image = await asyncio.to_thread(capture_screenshot_base64)
        image_url = f"data:image/png;base64,{b64_image}"
        
        response = await client.post(
            f"{MOONDREAM_BASE_URL}/query",
            json={"image_url": image_url, "question": question}
        )
        
        result = response.json()
        answer = result.get("answer", result.get("result", str(result)))
        
        print(f"\n{'='*60}")
        print(f"{description}")
        print(f"{'='*60}")
        print(f"Prompt: {question[:100]}...")
        print(f"\nAntwort:\n{answer[:600]}...")
        print(f"\nLänge: {len(answer)} Zeichen")
        
        return answer
        
    except Exception as e:
        print(f"ERROR: {e}")
        return None
    finally:
        await client.aclose()

async def compare_prompts():
    print("\n" + "=" * 70)
    print("VERGLEICH TEST: Alte vs Neue Moondream Prompts")
    print("=" * 70)
    
    # ALTE PROMPTS (Deutsch, kein Reasoning Mode, keine Struktur)
    print("\n--- ALTE PROMPTS ---")
    
    old_prompt_1 = (
        "Liste alle Buttons, Links und Eingabefelder auf diesem Screenshot "
        "mit grober Position (oben/mitte/unten, links/mitte/rechts) und kurzem Label."
    )
    await call_moondream_api(old_prompt_1, "ALTER PROMPT #1: Deutsch, keine Struktur")
    
    old_prompt_2 = (
        "Wo ist der Submit Button auf diesem Screenshot? Beschreibe die Position "
        "(oben/mitte/unten, links/mitte/rechts) und wie er aussieht."
    )
    await call_moondream_api(old_prompt_2, "ALTER PROMPT #2: Deutsch Element-Suche")
    
    # NEUE PROMPTS (Englisch, Reasoning Mode, strukturierte JSON)
    print("\n" + "-" * 70)
    print("--- NEUE PROMPTS (OPTIMIERT) ---")
    print("-" * 70)
    
    new_prompt_1 = (
        "In reasoning mode: Analyze this browser screenshot and identify ALL "
        "interactive UI elements. Provide a structured JSON array containing: "
        "type (button/text field/checkbox/etc.), label (visible text or aria-label), "
        "position (x,y as center coordinates 0-1), and visibility state. Focus on "
        "buttons, links, input fields, dropdowns, and checkboxes. Respond ONLY with "
        "valid JSON array format: [{\"type\": \"button\", \"label\": \"Submit\", "
        "\"position\": {\"x\": 0.5, \"y\": 0.8}, \"visibility\": \"visible\"}, ...]"
    )
    await call_moondream_api(new_prompt_1, "NEUER PROMPT #1: Englisch + Reasoning Mode + JSON")
    
    new_prompt_2 = (
        "In reasoning mode: Locate 'submit button' on this screenshot. Describe its "
        "exact position using coordinates (x,y as center 0-1) and relative terms "
        "(top/middle/bottom, left/center/right). If found, provide a structured JSON "
        "response with type, label, position {x, y}, visibility, and confidence. "
        "If not found, respond with {\"found\": false, \"reason\": \"Element not found\"}. "
        "Respond ONLY with valid JSON."
    )
    await call_moondream_api(new_prompt_2, "NEUER PROMPT #2: Englisch + Reasoning Mode + JSON Element-Suche")
    
    print("\n" + "=" * 70)
    print("VERGLEICH ABGESCHLOSSEN")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(compare_prompts())

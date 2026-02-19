"""
Florence-2 Setup & Schnelltest für Timus.

Ausführen (vom Timus-Projektroot):
    conda run -n timus python tools/florence2_tool/setup_florence2.py

Testet:
    1. Abhängigkeiten
    2. Tool-Registrierung in registry_v2
    3. florence2_health
    4. Screenshot + full_analysis
    5. Nemotron-Verbindung (wenn OPENROUTER_API_KEY gesetzt)
"""

import os
import sys
import time
import logging
from pathlib import Path

# Projektroot zum Suchpfad hinzufügen
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("setup_florence2")


def check_dependencies():
    print("\n[1/5] Abhängigkeiten prüfen...")
    missing = []
    deps = [
        ("torch", "torch"),
        ("transformers", "transformers"),
        ("PIL", "Pillow"),
        ("timm", "timm"),
        ("einops", "einops"),
        ("mss", "mss"),
        ("pyautogui", "pyautogui"),
        ("openai", "openai"),
        ("flash_attn", "flash-attn (optional)"),
    ]
    for module, pkg in deps:
        try:
            import importlib
            m = importlib.import_module(module)
            ver = getattr(m, "__version__", "?")
            print(f"  OK  {pkg} ({ver})")
        except ImportError:
            if "optional" in pkg:
                print(f"  --  {pkg}")
            else:
                print(f"  FEHLT  {pkg}")
                missing.append(pkg)
    if missing:
        print(f"\nInstallieren: pip install {' '.join(missing)}")
        return False
    return True


def check_tool_registration():
    print("\n[2/5] Tool-Registrierung in registry_v2 prüfen...")
    try:
        # Import löst @tool Decorator aus → registriert alle florence2_* Tools
        from tools.florence2_tool import tool as florence_tool_module  # noqa
        import importlib
        importlib.import_module("tools.florence2_tool.tool")

        from tools.tool_registry_v2 import registry_v2
        all_tools = registry_v2.list_all_tools()
        expected = ["florence2_health", "florence2_full_analysis",
                    "florence2_detect_ui", "florence2_ocr", "florence2_analyze_region"]
        ok = True
        for name in expected:
            if name in all_tools:
                print(f"  OK  {name} registriert")
            else:
                print(f"  FEHLT  {name} NICHT in registry_v2")
                ok = False
        return ok
    except Exception as e:
        print(f"  FEHLER: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_health():
    print("\n[3/5] florence2_health aufrufen (kein Modell-Load)...")
    try:
        from tools.tool_registry_v2 import registry_v2
        import asyncio
        result = asyncio.run(registry_v2.execute("florence2_health"))
        print(f"  Ergebnis: {result}")
        if isinstance(result, dict) and "status" in result:
            print(f"  OK  Status: {result['status']}")
            return True
        print("  FEHLER: Unerwartetes Format")
        return False
    except Exception as e:
        print(f"  FEHLER: {e}")
        return False


def check_screenshot_analysis():
    print("\n[4/5] Screenshot + florence2_full_analysis...")
    try:
        import mss
        from mss.tools import to_png

        path = "/tmp/timus_florence2_test.png"
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            shot = sct.grab(monitor)
            to_png(shot.rgb, shot.size, output=path)
        print(f"  Screenshot: {path} ({shot.width}x{shot.height})")

        from tools.tool_registry_v2 import registry_v2
        import asyncio
        t0 = time.time()
        result = asyncio.run(registry_v2.execute("florence2_full_analysis", image_path=path))
        elapsed = time.time() - t0

        if "error" in result:
            print(f"  FEHLER: {result['error']}")
            return False

        print(f"  OK  Analyse in {elapsed:.1f}s")
        print(f"  Caption: {str(result.get('caption',''))[:80]}...")
        print(f"  Elemente: {result.get('element_count', 0)}")
        print(f"  Gerät: {result.get('device', '?')}")
        print(f"  Modell: {result.get('model', '?')}")
        return True
    except Exception as e:
        print(f"  FEHLER: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_nemotron():
    print("\n[5/5] Nemotron-Verbindung (OpenRouter)...")
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        print("  --  OPENROUTER_API_KEY nicht gesetzt, überspringe")
        return True
    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        resp = client.chat.completions.create(
            model="nvidia/nemotron-3-nano-30b-a3b",
            messages=[{"role": "user", "content": "Antworte nur mit: OK"}],
            max_tokens=5,
        )
        answer = resp.choices[0].message.content.strip()
        print(f"  OK  Nemotron antwortet: '{answer}'")
        return True
    except Exception as e:
        print(f"  FEHLER: {e}")
        return False


def main():
    print("=" * 55)
    print("Timus Florence-2 — Setup & Validierung")
    print("=" * 55)

    results = {}
    results["deps"] = check_dependencies()
    if not results["deps"]:
        print("\n❌ Abhängigkeiten fehlen. Abbruch.")
        sys.exit(1)

    results["registration"] = check_tool_registration()
    results["health"] = check_health()
    results["analysis"] = check_screenshot_analysis()
    results["nemotron"] = check_nemotron()

    print("\n" + "=" * 55)
    print("ERGEBNIS:")
    all_ok = True
    for name, ok in results.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon}  {name}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n✅ Florence-2 Tool ist bereit für Phase 3 (MCP-Server).")
    else:
        print("\n❌ Probleme gefunden. Bitte beheben vor Phase 3.")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# test_ocr_backends.py
"""
Testet verschiedene OCR-Backends und vergleicht Geschwindigkeit & Genauigkeit.
"""

import os
import time
import asyncio
import pytest
from PIL import Image
import mss

# Setze PYTHONPATH
import sys
sys.path.insert(0, os.path.dirname(__file__))

from tools.engines.ocr_engine import OCREngine, EASYOCR_AVAILABLE, TESSERACT_AVAILABLE, TROCR_AVAILABLE, PADDLEOCR_AVAILABLE


if os.getenv("RUN_OCR_TESTS") != "1":
    pytest.skip("OCR-Backend-Test ist manuell und benötigt lokale Abhängigkeiten.", allow_module_level=True)

def capture_screenshot():
    """Macht einen Screenshot."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        sct_img = sct.grab(monitor)
        return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

async def test_backend(backend_name: str, image: Image.Image):
    """
    Testet ein OCR-Backend.

    Args:
        backend_name: Name des Backends (easyocr, tesseract, trocr, paddleocr)
        image: Test-Bild

    Returns:
        Dict mit Ergebnissen
    """
    print(f"\n{'='*60}")
    print(f"🧪 Teste Backend: {backend_name.upper()}")
    print(f"{'='*60}")

    # Setze Backend in der Engine
    os.environ["OCR_BACKEND"] = backend_name

    # Erstelle neue Engine-Instanz
    engine = OCREngine()

    # Initialisiere
    start_init = time.time()
    try:
        engine.initialize()
        init_time = time.time() - start_init
    except Exception as e:
        print(f"❌ Initialisierung fehlgeschlagen: {e}")
        return None

    if not engine.is_initialized():
        print(f"❌ Backend '{backend_name}' konnte nicht initialisiert werden (nicht installiert?)")
        return None

    print(f"✅ Initialisierung: {init_time:.2f}s")

    # Führe OCR durch
    print(f"🔍 Führe OCR durch...")
    start_ocr = time.time()
    try:
        result = engine.process(image, with_boxes=True)
        ocr_time = time.time() - start_ocr
    except Exception as e:
        print(f"❌ OCR fehlgeschlagen: {e}")
        return None

    # Ergebnisse
    text_count = result.get("count", 0)
    full_text = result.get("full_text", "")
    extracted = result.get("extracted_text", [])

    print(f"✅ OCR-Zeit: {ocr_time:.2f}s")
    print(f"📊 Textblöcke gefunden: {text_count}")
    print(f"📝 Gesamttext-Länge: {len(full_text)} Zeichen")

    if extracted:
        avg_confidence = sum(item["confidence"] for item in extracted) / len(extracted)
        print(f"🎯 Durchschnittliche Confidence: {avg_confidence:.2%}")

    # Zeige erste 3 Textblöcke
    print(f"\n📋 Erste 3 erkannte Textblöcke:")
    for i, item in enumerate(extracted[:3], 1):
        text = item["text"][:50]  # Erste 50 Zeichen
        conf = item["confidence"]
        bbox = item.get("bbox", [])
        print(f"  {i}. '{text}' (Conf: {conf:.2%}, BBox: {bbox})")

    return {
        "backend": backend_name,
        "init_time": init_time,
        "ocr_time": ocr_time,
        "total_time": init_time + ocr_time,
        "text_count": text_count,
        "text_length": len(full_text),
        "full_text": full_text,
        "avg_confidence": sum(item["confidence"] for item in extracted) / len(extracted) if extracted else 0.0
    }

async def main():
    """Hauptfunktion."""
    print("="*60)
    print("🚀 OCR-Backend Vergleichstest")
    print("="*60)

    # Verfügbare Backends
    backends_available = {
        "easyocr": EASYOCR_AVAILABLE,
        "tesseract": TESSERACT_AVAILABLE,
        "trocr": TROCR_AVAILABLE,
        "paddleocr": PADDLEOCR_AVAILABLE
    }

    print("\n📦 Verfügbare Backends:")
    for backend, available in backends_available.items():
        status = "✅ Verfügbar" if available else "❌ Nicht installiert"
        print(f"  - {backend}: {status}")

    # Screenshot machen
    print("\n📸 Mache Screenshot...")
    image = capture_screenshot()
    print(f"✅ Screenshot: {image.size[0]}x{image.size[1]}px")

    # Teste alle verfügbaren Backends
    results = []

    for backend_name, available in backends_available.items():
        if not available:
            print(f"\n⏭️  Überspringe {backend_name} (nicht installiert)")
            continue

        result = await test_backend(backend_name, image)
        if result:
            results.append(result)

        # Warte kurz zwischen Tests
        await asyncio.sleep(1)

    # Zusammenfassung
    print(f"\n{'='*60}")
    print("📊 ZUSAMMENFASSUNG")
    print(f"{'='*60}\n")

    if not results:
        print("❌ Keine Tests erfolgreich durchgeführt!")
        return

    # Sortiere nach Gesamtzeit
    results.sort(key=lambda x: x["total_time"])

    print("🏆 Ranking nach Geschwindigkeit:")
    for i, result in enumerate(results, 1):
        backend = result["backend"]
        total_time = result["total_time"]
        text_count = result["text_count"]
        conf = result["avg_confidence"]
        print(f"  {i}. {backend:12s} - {total_time:5.2f}s | {text_count:3d} Blöcke | Conf: {conf:.1%}")

    print("\n💡 Empfehlung:")
    fastest = results[0]
    print(f"  🚀 Schnellstes: {fastest['backend']} ({fastest['total_time']:.2f}s)")

    # Finde Backend mit bester Confidence
    best_conf = max(results, key=lambda x: x["avg_confidence"])
    print(f"  🎯 Beste Confidence: {best_conf['backend']} ({best_conf['avg_confidence']:.1%})")

    # Finde Backend mit meisten Textblöcken
    most_text = max(results, key=lambda x: x["text_count"])
    print(f"  📝 Meiste Textblöcke: {most_text['backend']} ({most_text['text_count']} Blöcke)")

    # Beste Balance
    print("\n🌟 Beste Balance (Geschwindigkeit + Genauigkeit):")
    # Score: weniger Zeit ist besser, mehr Confidence ist besser
    for result in results:
        # Normalisiere Score (niedrig = besser)
        time_score = result["total_time"] / max(r["total_time"] for r in results)
        conf_score = 1 - result["avg_confidence"]  # Invertiere, da höher besser ist
        result["balance_score"] = (time_score + conf_score) / 2

    results.sort(key=lambda x: x["balance_score"])
    best_balance = results[0]
    print(f"  ⭐ {best_balance['backend']} - Score: {best_balance['balance_score']:.3f}")
    print(f"     Zeit: {best_balance['total_time']:.2f}s | Conf: {best_balance['avg_confidence']:.1%}")

if __name__ == "__main__":
    asyncio.run(main())

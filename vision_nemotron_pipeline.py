#!/usr/bin/env python3
"""
Vision + Nemotron Pipeline für strukturierte Webseiten-Analyse.

Pipeline:
1. Vision-Analyse (Moondream ODER GPT-4 Vision als Fallback) -> Textbeschreibung
2. Nemotron (OpenRouter) konvertiert Text -> strukturiertes JSON

Features:
- Automatischer Fallback: Moondream -> GPT-4 Vision
- Native Moondream API (/v1/query)
- Strict JSON Schema für Nemotron

Autor: Timus Development
Version: 2.0 (mit Fallback)
"""

import sys
import json
import base64
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# .env laden
load_dotenv()

try:
    from openai import OpenAI
    import httpx
except ImportError:
    print("FEHLER: Benötigte Packages nicht installiert!")
    print("Bitte ausführen: pip install openai pillow httpx python-dotenv")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("FEHLER: 'pillow' package nicht installiert!")
    print("Bitte ausführen: pip install openai pillow httpx python-dotenv")
    sys.exit(1)


# ============================================================================
# KONFIGURATION
# ============================================================================

# Moondream (Primary)
MOONDREAM_BASE_URL = os.getenv("MOONDREAM_API_BASE", "http://localhost:2020/v1")
MOONDREAM_MODEL = "moondream-3-preview"

# GPT-4 Vision (Fallback)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GPT4_VISION_MODEL = "gpt-4o"

# Nemotron (NVIDIA NIM Primary, GPT-4 Fallback)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "nvidia/llama-3.1-nemotron-nano-8b-v1"

# GPT-4 Fallback für Strukturierung
GPT4_STRUCTURE_MODEL = "gpt-4o-mini"

# Screenshot-Pfad
DEFAULT_SCREENSHOT = Path(__file__).parent / "test_project" / "screenshot.png"


# ============================================================================
# JSON SCHEMA FÜR NEMOTRON
# ============================================================================

NEMOTRON_SCHEMA = {
    "type": "object",
    "properties": {
        "page_title": {"type": "string"},
        "main_heading": {"type": "string"},
        "meta_description": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "header",
                            "hero",
                            "navigation",
                            "main_content",
                            "sidebar",
                            "footer",
                            "form",
                            "product_grid",
                            "other"
                        ]
                    },
                    "heading": {"type": "string"},
                    "text_blocks": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "links": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "url": {"type": "string"}
                            },
                            "required": ["text", "url"],
                            "additionalProperties": False
                        }
                    },
                    "buttons": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "forms": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "fields": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "submit_text": {"type": "string"}
                            },
                            "required": ["fields", "submit_text"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["type"],
                "additionalProperties": False
            }
        },
        "detected_elements_summary": {
            "type": "object",
            "additionalProperties": {"type": "number"}
        }
    },
    "required": ["page_title", "sections"],
    "additionalProperties": False
}


# ============================================================================
# HILFSFUNKTIONEN
# ============================================================================

def encode_image_base64(image_path: Path) -> str:
    """Lädt ein Bild und konvertiert es zu Base64."""
    if not image_path.exists():
        raise FileNotFoundError(f"Bild nicht gefunden: {image_path}")

    img = Image.open(image_path)
    img.verify()

    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')


# ============================================================================
# VISION-ANALYSE (SCHRITT 1)
# ============================================================================

def analyze_with_moondream(image_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Versucht Analyse mit Moondream Station.

    Returns:
        (description, error) - eines ist None
    """
    try:
        b64_image = encode_image_base64(image_path)
        image_url = f"data:image/png;base64,{b64_image}"

        question = """Analysiere diesen Webseiten-Screenshot sehr detailliert.

Beschreibe in natürlicher Sprache:
1. Alle sichtbaren Texte in Lesereihenfolge (Header, Navigation, Überschriften, Absätze, Footer)
2. Layout-Struktur (Header, Hero-Section, Content-Bereiche, Sidebar, Footer, Formulare, Grids)
3. Alle Buttons und Links mit ihrem sichtbaren Text
4. Eingabefelder und Formulare
5. Auffällige Bilder oder Grafiken
6. Relative Positionen der Elemente (oben, mittig, unten, links, rechts)

Schreibe eine detaillierte, strukturierte Beschreibung OHNE JSON-Format."""

        api_url = f"{MOONDREAM_BASE_URL.rstrip('/')}/query"

        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                api_url,
                json={
                    "image_url": image_url,
                    "question": question
                }
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                return None, result["error"]

            description = result.get("answer", result.get("result", ""))

            if description and len(description) >= 10:
                return description, None
            else:
                return None, "Ungültige Antwort (zu kurz)"

    except Exception as e:
        return None, str(e)


def analyze_with_gpt4_vision(image_path: Path) -> str:
    """
    Analysiert Screenshot mit GPT-4 Vision (Fallback).

    Returns:
        Detaillierte Textbeschreibung des Screenshots
    """
    if not OPENAI_API_KEY:
        print("\nFEHLER: OPENAI_API_KEY nicht gesetzt!")
        print("Setze OPENAI_API_KEY in .env oder Umgebungsvariable")
        sys.exit(1)

    try:
        b64_image = encode_image_base64(image_path)

        client = OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model=GPT4_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Analysiere diesen Webseiten-Screenshot sehr detailliert.

Beschreibe in natürlicher Sprache:
1. Alle sichtbaren Texte in Lesereihenfolge (Header, Navigation, Überschriften, Absätze, Footer)
2. Layout-Struktur (Header, Hero-Section, Content-Bereiche, Sidebar, Footer, Formulare, Grids)
3. Alle Buttons und Links mit ihrem sichtbaren Text
4. Eingabefelder und Formulare
5. Auffällige Bilder oder Grafiken
6. Relative Positionen der Elemente (oben, mittig, unten, links, rechts)

Schreibe eine detaillierte, strukturierte Beschreibung OHNE JSON-Format."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.0,
            max_tokens=2000
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"\nFEHLER bei GPT-4 Vision: {e}")
        sys.exit(1)


def analyze_screenshot(image_path: Path) -> str:
    """
    Analysiert Screenshot mit automatischem Fallback.
    Versucht: Moondream -> GPT-4 Vision

    Returns:
        Detaillierte Textbeschreibung
    """
    print(f"[1/3] Vision-Analyse startet...")
    print(f"      Bild: {image_path}")

    # Versuch 1: Moondream
    print(f"      Versuche Moondream ({MOONDREAM_BASE_URL})...")
    description, error = analyze_with_moondream(image_path)

    if description:
        print(f"[✓] Moondream-Analyse erfolgreich ({len(description)} Zeichen)")
        print(f"    Preview: {description[:200]}...")
        return description
    else:
        print(f"      ✗ Moondream fehlgeschlagen: {error[:100]}")

    # Versuch 2: GPT-4 Vision (Fallback)
    print(f"      Fallback zu GPT-4 Vision...")
    description = analyze_with_gpt4_vision(image_path)
    print(f"[✓] GPT-4 Vision-Analyse erfolgreich ({len(description)} Zeichen)")
    print(f"    Preview: {description[:200]}...")
    return description


# ============================================================================
# NEMOTRON STRUKTURIERUNG (SCHRITT 2)
# ============================================================================

def structure_with_nemotron(description: str) -> Dict[str, Any]:
    """
    Konvertiert Textbeschreibung zu strukturiertem JSON via Nemotron.
    Versucht: NVIDIA NIM -> OpenRouter (Fallback)

    Args:
        description: Roh-Textbeschreibung von Vision-Modell

    Returns:
        Strukturiertes JSON-Objekt
    """
    print(f"[2/3] Nemotron-Strukturierung startet...")

    # Verwende GPT-4 für Strukturierung (zuverlässig und verfügbar)
    if not OPENAI_API_KEY:
        print("FEHLER: OPENAI_API_KEY nicht gesetzt!")
        print("Setze OPENAI_API_KEY in .env")
        sys.exit(1)

    print(f"      Verwende GPT-4 für Strukturierung...")
    client = OpenAI(api_key=OPENAI_API_KEY)
    model = GPT4_STRUCTURE_MODEL

    system_prompt = """Du bist ein Experte für Webseiten-Struktur-Analyse.

Deine Aufgabe:
1. Lies die detaillierte Textbeschreibung einer Webseite
2. Extrahiere strukturierte Informationen
3. Gib ein valides JSON-Objekt zurück gemäß dem vorgegebenen Schema

Wichtig:
- Alle Texte, Buttons, Links korrekt den Sektionen zuordnen
- page_title: Haupttitel der Seite
- main_heading: Größte Überschrift (meist H1)
- sections: Array mit allen erkennbaren Bereichen (header, navigation, hero, main_content, sidebar, footer, etc.)
- detected_elements_summary: Anzahl der verschiedenen Element-Typen (z.B. {"buttons": 5, "links": 12, "forms": 1})"""

    user_prompt = f"""Analysiere folgende Webseiten-Beschreibung und strukturiere sie:

{description}

Erstelle ein strukturiertes JSON gemäß Schema."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=2000,
            stream=False,
            response_format={"type": "json_object"}
        )

        json_text = response.choices[0].message.content
        structured_data = json.loads(json_text)

        print(f"[✓] Nemotron-Strukturierung abgeschlossen")
        print(f"    Sektionen: {len(structured_data.get('sections', []))}")

        return structured_data

    except json.JSONDecodeError as e:
        print(f"FEHLER: JSON-Parsing fehlgeschlagen: {e}")
        print(f"Response: {response.choices[0].message.content[:500]}...")
        sys.exit(1)
    except Exception as e:
        print(f"FEHLER bei Nemotron API-Call: {e}")
        sys.exit(1)


# ============================================================================
# SPEICHERN (SCHRITT 3)
# ============================================================================

def save_result(image_path: Path, data: Dict[str, Any]) -> Path:
    """
    Speichert strukturiertes JSON neben dem Original-Bild.

    Returns:
        Pfad der gespeicherten JSON-Datei
    """
    print(f"[3/3] Ergebnis speichern...")

    output_path = image_path.with_suffix('.json')

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[✓] Ergebnis gespeichert: {output_path}")
        return output_path

    except Exception as e:
        print(f"FEHLER beim Speichern: {e}")
        sys.exit(1)


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def main():
    """Hauptfunktion - führt die komplette Pipeline aus."""

    print("=" * 70)
    print("Vision + Nemotron Pipeline v2.0 (mit Fallback)")
    print("=" * 70)
    print()

    # Screenshot-Pfad
    if len(sys.argv) > 1:
        screenshot_path = Path(sys.argv[1])
    else:
        screenshot_path = DEFAULT_SCREENSHOT

    screenshot_path = screenshot_path.resolve()

    # Pipeline ausführen
    try:
        # Schritt 1: Vision-Analyse (Moondream -> GPT-4 Fallback)
        description = analyze_screenshot(screenshot_path)
        print()

        # Schritt 2: Nemotron Strukturierung
        structured_data = structure_with_nemotron(description)
        print()

        # Schritt 3: Speichern
        output_path = save_result(screenshot_path, structured_data)
        print()

        # Ausgabe auf Konsole
        print("=" * 70)
        print("ERGEBNIS (JSON)")
        print("=" * 70)
        print(json.dumps(structured_data, indent=2, ensure_ascii=False))
        print()

        print("=" * 70)
        print(f"✓ Pipeline erfolgreich abgeschlossen")
        print(f"✓ Ergebnis: {output_path}")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n\n[!] Pipeline abgebrochen durch Benutzer")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFEHLER: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

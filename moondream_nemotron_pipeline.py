#!/usr/bin/env python3
"""
Moondream + Nemotron Pipeline für strukturierte Webseiten-Analyse.

Pipeline:
1. Moondream Station (localhost:2020) analysiert Screenshot -> Textbeschreibung
2. Nemotron (OpenRouter) konvertiert Text -> strukturiertes JSON

Autor: Timus Development
Version: 1.0
"""

import sys
import json
import base64
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# .env laden
load_dotenv()

try:
    from openai import OpenAI
    import httpx
except ImportError:
    print("FEHLER: 'openai' oder 'httpx' package nicht installiert!")
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

# Moondream - Port 2020 (Standard)
MOONDREAM_BASE_URL = os.getenv("MOONDREAM_API_BASE", "http://localhost:2020/v1")
MOONDREAM_MODEL = "moondream-3-preview"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NEMOTRON_MODEL = "nvidia/nemotron-3-nano-30b-a3b"

# Screenshot-Pfad (konfigurierbar)
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
                            "required": ["text"],
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
                            }
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
# MOONDREAM ANALYSE (SCHRITT 1)
# ============================================================================

def encode_image_base64(image_path: Path) -> str:
    """Lädt ein Bild und konvertiert es zu Base64."""
    if not image_path.exists():
        raise FileNotFoundError(f"Bild nicht gefunden: {image_path}")

    # Bild laden und validieren
    img = Image.open(image_path)
    img.verify()  # Prüft ob Bild valide ist

    # Neu laden nach verify() (PIL Limitierung)
    img = Image.open(image_path)

    # Zu Base64 konvertieren
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')


def analyze_with_moondream(image_path: Path) -> str:
    """
    Analysiert Screenshot mit Moondream Station.
    Verwendet die native Moondream API (/v1/query).

    Returns:
        Detaillierte Textbeschreibung des Screenshots
    """
    print(f"[1/3] Moondream-Analyse startet...")
    print(f"      Bild: {image_path}")
    print(f"      API: {MOONDREAM_BASE_URL}")

    # Bild zu Base64 konvertieren
    try:
        b64_image = encode_image_base64(image_path)
    except FileNotFoundError as e:
        print(f"FEHLER: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"FEHLER beim Bildladen: {e}")
        sys.exit(1)

    # Data-URL Format für Moondream
    image_url = f"data:image/png;base64,{b64_image}"

    # Moondream-Prompt (detaillierte Beschreibung, kein JSON)
    question = """Analysiere diesen Webseiten-Screenshot sehr detailliert.

Beschreibe in natürlicher Sprache:
1. Alle sichtbaren Texte in Lesereihenfolge (Header, Navigation, Überschriften, Absätze, Footer)
2. Layout-Struktur (Header, Hero-Section, Content-Bereiche, Sidebar, Footer, Formulare, Grids)
3. Alle Buttons und Links mit ihrem sichtbaren Text
4. Eingabefelder und Formulare
5. Auffällige Bilder oder Grafiken
6. Relative Positionen der Elemente (oben, mittig, unten, links, rechts)

Schreibe eine detaillierte, strukturierte Beschreibung OHNE JSON-Format."""

    # API Call
    api_url = f"{MOONDREAM_BASE_URL.rstrip('/')}/query"

    try:
        with httpx.Client(timeout=90.0) as client:
            print(f"      Sende Anfrage...")

            response = client.post(
                api_url,
                json={
                    "image_url": image_url,
                    "question": question
                }
            )
            response.raise_for_status()

            result = response.json()

            # Prüfe auf Fehler in der Response
            if "error" in result:
                error_msg = result["error"]
                print(f"\nFEHLER: Moondream-Fehler: {error_msg}")
                print(f"\nMögliche Lösungen:")
                print(f"  1. Starte Moondream Station neu: moondream-station")
                print(f"  2. Wechsle Modell: moondream-station model use moondream-2")
                print(f"  3. Aktualisiere: pip install --upgrade moondream-station")
                sys.exit(1)

            description = result.get("answer", result.get("result", str(result)))

            # Prüfe ob Beschreibung valide ist
            if not description or len(description) < 10:
                print(f"\nFEHLER: Ungültige Antwort von Moondream: {description}")
                sys.exit(1)

            print(f"[✓] Moondream-Analyse abgeschlossen ({len(description)} Zeichen)")
            print(f"    Preview: {description[:200]}...")

            return description

    except httpx.ConnectError:
        print(f"\nFEHLER: Moondream Station nicht erreichbar!")
        print(f"API: {MOONDREAM_BASE_URL}")
        print(f"\nBitte stelle sicher, dass Moondream Station läuft:")
        print(f"  moondream-station")
        print(f"\nOder setze MOONDREAM_API_BASE in .env")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"\nFEHLER: HTTP {e.response.status_code}")
        print(f"Response: {e.response.text[:200]}")
        sys.exit(1)
    except Exception as e:
        print(f"\nFEHLER: {e}")
        sys.exit(1)


# ============================================================================
# NEMOTRON STRUKTURIERUNG (SCHRITT 2)
# ============================================================================

def structure_with_nemotron(description: str) -> Dict[str, Any]:
    """
    Konvertiert Textbeschreibung zu strukturiertem JSON via Nemotron.

    Args:
        description: Roh-Textbeschreibung von Moondream

    Returns:
        Strukturiertes JSON-Objekt
    """
    print(f"[2/3] Nemotron-Strukturierung startet...")

    # OpenRouter API Key
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("FEHLER: OPENROUTER_API_KEY nicht gesetzt!")
        print("Setze die Umgebungsvariable: export OPENROUTER_API_KEY='sk-or-...'")
        sys.exit(1)

    # Client für OpenRouter
    openrouter_client = OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL
    )

    # Nemotron-Prompt
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

    # API-Call mit strict JSON schema
    try:
        response = openrouter_client.chat.completions.create(
            model=NEMOTRON_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            stream=False,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "webpage_structure",
                    "strict": True,
                    "schema": NEMOTRON_SCHEMA
                }
            }
        )

        # JSON parsen
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

    # Output-Pfad: gleicher Name wie Bild, aber .json Extension
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
    print("Moondream + Nemotron Pipeline v1.0")
    print("=" * 70)
    print()

    # Screenshot-Pfad (anpassbar via Command-Line Argument)
    if len(sys.argv) > 1:
        screenshot_path = Path(sys.argv[1])
    else:
        screenshot_path = DEFAULT_SCREENSHOT

    screenshot_path = screenshot_path.resolve()

    # Pipeline ausführen
    try:
        # Schritt 1: Moondream Analyse
        description = analyze_with_moondream(screenshot_path)
        print()

        # Schritt 2: Nemotron Strukturierung
        structured_data = structure_with_nemotron(description)
        print()

        # Schritt 3: Speichern
        output_path = save_result(screenshot_path, structured_data)
        print()

        # Ausgabe auf Konsole (formatiert)
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

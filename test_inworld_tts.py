#!/usr/bin/env python3
"""
Test-Script für Inworld.AI TTS Integration
"""

import os
import sys
import requests
import base64
from pathlib import Path
from dotenv import load_dotenv

# .env laden
load_dotenv(Path.home() / "dev" / "timus" / ".env")

INWORLD_API_KEY = os.getenv("INWORLD_API_KEY")
INWORLD_VOICE = os.getenv("INWORLD_VOICE", "Ashley")
INWORLD_MODEL = os.getenv("INWORLD_MODEL", "inworld-tts-1.5-max")
INWORLD_SPEAKING_RATE = float(os.getenv("INWORLD_SPEAKING_RATE", "1.0"))
INWORLD_TEMPERATURE = float(os.getenv("INWORLD_TEMPERATURE", "1.0"))

def test_inworld_api():
    """Testet die Inworld.AI TTS API."""

    print("="*60)
    print("🧪 INWORLD.AI TTS - API TEST")
    print("="*60)

    # Config prüfen
    print("\n📋 Konfiguration:")
    print(f"   API Key: {'✅ Gesetzt' if INWORLD_API_KEY else '❌ FEHLT'}")
    print(f"   Voice: {INWORLD_VOICE}")
    print(f"   Model: {INWORLD_MODEL}")
    print(f"   Speaking Rate: {INWORLD_SPEAKING_RATE}x (0.5-1.5)")
    print(f"   Temperature: {INWORLD_TEMPERATURE}")

    if not INWORLD_API_KEY:
        print("\n❌ FEHLER: INWORLD_API_KEY nicht in .env gesetzt!")
        print("   1. Gehe zu: https://platform.inworld.ai/v2/workspaces/default-aktxk7b87hi3mx_pdfw/settings/api-keys")
        print("   2. Kopiere den 'Basic (Base64)' Key")
        print("   3. Füge in .env ein: INWORLD_API_KEY=dein_key_hier")
        return False

    # API Key Format prüfen
    if not INWORLD_API_KEY.endswith("==") and not INWORLD_API_KEY.startswith("sX"):
        print("\n⚠️  WARNUNG: API Key sieht nicht wie ein Base64-Key aus!")
        print("   Stelle sicher dass du den 'Basic (Base64)' Key kopiert hast, nicht JWT Key!")

    # API Call testen
    print("\n🌐 Teste API Verbindung...")

    try:
        url = "https://api.inworld.ai/tts/v1/voice"
        headers = {
            "Authorization": f"Basic {INWORLD_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "text": "Hallo! Dies ist ein Test der Inworld AI Sprachsynthese.",
            "voiceId": INWORLD_VOICE,
            "modelId": INWORLD_MODEL,
            "voiceSettings": {
                "speaking_rate": INWORLD_SPEAKING_RATE,
            },
            "temperature": INWORLD_TEMPERATURE
        }

        print(f"   Endpoint: {url}")
        print(f"   Payload: text={len(payload['text'])} chars, voice={INWORLD_VOICE}, model={INWORLD_MODEL}")
        print(f"   Settings: speaking_rate={INWORLD_SPEAKING_RATE}x, temperature={INWORLD_TEMPERATURE}")

        response = requests.post(url, json=payload, headers=headers, timeout=30)

        print(f"   Status: {response.status_code}")

        if response.status_code == 401:
            print("\n❌ Authentifizierung fehlgeschlagen!")
            print("   - Prüfe ob der API Key korrekt in .env steht")
            print("   - Stelle sicher dass du den 'Basic (Base64)' Key verwendest")
            print("   - Prüfe ob der Key im Portal 'Activated' ist")
            return False

        response.raise_for_status()

        result = response.json()

        if 'audioContent' in result:
            audio_bytes = base64.b64decode(result['audioContent'])
            print(f"\n✅ API TEST ERFOLGREICH!")
            print(f"   Audio empfangen: {len(audio_bytes)} bytes")

            # Optional: Audio speichern
            output_path = Path.home() / "dev" / "timus" / "test_inworld_output.mp3"
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            print(f"   Gespeichert: {output_path}")

            # Preis berechnen
            chars = len(payload['text'])
            if INWORLD_MODEL == "inworld-tts-1.5-max":
                cost = (chars / 1_000_000) * 10  # $10 pro 1M chars
            else:
                cost = (chars / 1_000_000) * 5   # $5 pro 1M chars
            print(f"   Kosten: ${cost:.6f} ({chars} chars)")

            return True
        else:
            print(f"\n❌ Unerwartete Antwort: {result}")
            return False

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP Fehler: {e}")
        print(f"   Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
        return False
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        return False

if __name__ == "__main__":
    success = test_inworld_api()

    if success:
        print("\n" + "="*60)
        print("✅ MIGRATION BEREIT!")
        print("="*60)
        print("\nDu kannst jetzt timus_hybrid_v2.py starten:")
        print("   python3 timus_hybrid_v2.py")
        print("\nVorteile vs. ElevenLabs:")
        print("   💰 50-75% günstiger ($10/1M vs ~$40/1M)")
        print("   🚀 Schneller (120-200ms Latenz)")
        print("   🌍 15 Sprachen inkl. Deutsch")
    else:
        print("\n" + "="*60)
        print("❌ TEST FEHLGESCHLAGEN")
        print("="*60)
        print("\nBitte behebe die Fehler oben bevor du Timus startest.")

    sys.exit(0 if success else 1)

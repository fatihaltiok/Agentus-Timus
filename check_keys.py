import os
from dotenv import load_dotenv
from openai import OpenAI
from utils.openai_compat import prepare_openai_params

# 1. Umgebung laden
print("--- Lade .env Datei ---")
loaded = load_dotenv()
if not loaded:
    print("❌ WARNUNG: .env Datei wurde nicht gefunden oder ist leer!")
else:
    print("✅ .env Datei gefunden.")

# 2. Prüfe OpenAI Key (Für den Agenten selbst)
openai_key = os.getenv("OPENAI_API_KEY")
print(f"\n--- OpenAI Key Check (für Agenten) ---")
if openai_key:
    print(f"✅ Vorhanden. Start: {openai_key[:8]}... Ende: ...{openai_key[-4:]}")
    print(f"   Länge: {len(openai_key)} Zeichen")
    
    # Kurzer Verbindungstest
    try:
        print("   Test-Verbindung zu OpenAI...")
        client = OpenAI(api_key=openai_key)
        client.models.list()
        print("   ✅ Verbindung erfolgreich!")
    except Exception as e:
        print(f"   ❌ Verbindung fehlgeschlagen: {e}")
else:
    print("❌ FEHLER: 'OPENAI_API_KEY' fehlt in .env! Der Agent kann nicht denken.")

# 3. Prüfe Inception Key (Für das Coding-Tool)
inception_key = os.getenv("INCEPTION_API_KEY")
inception_url = os.getenv("INCEPTION_API_URL", "https://api.inceptionlabs.ai/v1")

print(f"\n--- Inception Key Check (für Coding) ---")
print(f"   Ziel-URL: {inception_url}")

if inception_key:
    print(f"✅ Vorhanden. Start: {inception_key[:4]}... Ende: ...{inception_key[-4:]}")
    
    # Kurzer Verbindungstest an Inception
    try:
        print("   Test-Verbindung zu Inception...")
        # Wir nutzen den OpenAI Client, aber mit Inception URL
        inc_client = OpenAI(api_key=inception_key, base_url=inception_url)
        # Wir fragen das Modell 'mercury' ab (oder ein einfaches Chat-Hello)
        inc_client.chat.completions.create(
            model="mercury",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5
        )
        print("   ✅ Verbindung erfolgreich!")
    except Exception as e:
        print(f"   ❌ Verbindung fehlgeschlagen: {e}")
else:
    print("⚠️ WARNUNG: 'INCEPTION_API_KEY' fehlt. Das Developer-Tool wird nicht funktionieren.")

print("\n--- Ende der Diagnose ---")
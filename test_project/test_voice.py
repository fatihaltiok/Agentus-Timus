from elevenlabs.client import ElevenLabs
import os
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/dev/timus/.env"))

api_key = os.getenv("ELEVENLABS_API_KEY")
print(f"API Key geladen: {api_key[:10]}..." if api_key else "FEHLER: Kein API Key!")

client = ElevenLabs(api_key=api_key)

print("Generiere Audio...")

# Korrekte API laut Doku
audio = client.text_to_speech.convert(
    text="Hallo Fatih, ich bin Timus. Wie kann ich dir helfen?",
    voice_id="pNInz6obpgDQGcFmaJgB",  # Adam
    model_id="eleven_multilingual_v2"
)

# Als Datei speichern
with open("output.mp3", "wb") as f:
    for chunk in audio:
        f.write(chunk)

print("✅ Audio gespeichert als output.mp3")
print("Spiele ab...")
os.system("ffplay -nodisp -autoexit output.mp3 2>/dev/null || mpv output.mp3 || xdg-open output.mp3")

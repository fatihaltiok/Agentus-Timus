#!/usr/bin/env python3
"""
Einfacher Voice Test - Ohne Timus Integration

Testet nur Spracheingabe → Sprachausgabe
"""

import os
import asyncio
import tempfile
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/dev/timus/.env"))

# Konfiguration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam
SAMPLE_RATE = 16000


def listen(whisper_model, duration=5.0):
    """Nimmt auf und transkribiert."""
    print("🎤 Sprich jetzt...")
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
    sd.wait()
    
    print("   Verarbeite...")
    segments, _ = whisper_model.transcribe(audio.flatten(), language="de")
    text = " ".join([s.text.strip() for s in segments])
    return text


def speak(client, text):
    """Spricht mit ElevenLabs."""
    print(f"🔊 Sage: {text}")
    
    audio = client.text_to_speech.convert(
        text=text,
        voice_id=VOICE_ID,
        model_id="eleven_multilingual_v2"
    )
    
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        for chunk in audio:
            f.write(chunk)
        temp_path = f.name
    
    os.system(f"ffplay -nodisp -autoexit -loglevel quiet '{temp_path}' 2>/dev/null")
    os.unlink(temp_path)


def main():
    print("🚀 Lade Modelle...")
    
    # Whisper
    print("   Whisper (medium)...")
    whisper = WhisperModel("medium", device="cuda", compute_type="float16")
    
    # ElevenLabs
    print("   ElevenLabs...")
    elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    
    print("✅ Bereit!\n")
    
    # Echo-Loop: Was du sagst wird wiederholt
    print("Echo-Modus: Ich wiederhole was du sagst. Sage 'stop' zum Beenden.\n")
    
    while True:
        text = listen(whisper)
        print(f"👤 Du sagtest: {text}")
        
        if "stop" in text.lower():
            speak(elevenlabs, "Auf Wiedersehen!")
            break
        
        speak(elevenlabs, f"Du sagtest: {text}")
        print()


if __name__ == "__main__":
    main()

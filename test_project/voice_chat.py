import asyncio
import os
import sys
import tempfile
import numpy as np
import sounddevice as sd
from pathlib import Path
from dotenv import load_dotenv

# .env laden
load_dotenv(Path.home() / "dev" / "timus" / ".env")

from faster_whisper import WhisperModel
from elevenlabs.client import ElevenLabs

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "pNInz6obpgDQGcFmaJgB"
SAMPLE_RATE = 16000
EXIT_COMMANDS = ["stop", "beenden", "ende", "tschüss"]


class TimusVoiceChat:
    def __init__(self):
        self.whisper = None
        self.elevenlabs = None
    
    def initialize(self):
        print("🚀 Initialisiere...")
        
        print("   📥 Lade Whisper (medium)...")
        try:
            self.whisper = WhisperModel("medium", device="cuda", compute_type="float16")
        except:
            self.whisper = WhisperModel("medium", device="cpu", compute_type="int8")
        print("   ✅ Whisper geladen")
        
        if ELEVENLABS_API_KEY:
            self.elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            print("   ✅ ElevenLabs verbunden")
        else:
            print("   ❌ ELEVENLABS_API_KEY fehlt!")
            return False
        
        print("✅ Bereit!\n")
        return True
    
    def listen(self, duration=5.0):
        print("🎤 Höre zu...")
        audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
        sd.wait()
        
        segments, _ = self.whisper.transcribe(audio.flatten(), language="de", vad_filter=True)
        text = " ".join([s.text.strip() for s in segments])
        return text
    
    def speak(self, text):
        if not text.strip():
            return
        print(f"🔊 Timus: {text}")
        
        audio = self.elevenlabs.text_to_speech.convert(
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
    
    def chat_loop(self):
        self.speak("Hallo! Ich bin Timus. Wie kann ich dir helfen?")
        
        while True:
            try:
                text = self.listen()
                if not text.strip():
                    continue
                
                print(f"👤 Du: {text}")
                
                if any(cmd in text.lower() for cmd in EXIT_COMMANDS):
                    self.speak("Auf Wiedersehen!")
                    break
                
                # Echo-Modus (später durch Timus-Agent ersetzen)
                self.speak(f"Du sagtest: {text}")
                print()
                
            except KeyboardInterrupt:
                print("\n👋 Beende...")
                break


def main():
    print("""
╔════════════════════════════════════════╗
║       🎤 TIMUS VOICE CHAT 🔊          ║
║  Sage "Stop" zum Beenden              ║
║  Ctrl+C zum Abbrechen                 ║
╚════════════════════════════════════════╝
    """)
    
    chat = TimusVoiceChat()
    if chat.initialize():
        chat.chat_loop()
    print("✅ Beendet.")


if __name__ == "__main__":
    main()
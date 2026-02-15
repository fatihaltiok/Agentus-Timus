"""Timus Voice Chat - Mit Agent-Integration"""

import asyncio
import os
import sys
import tempfile
import numpy as np
import sounddevice as sd
from pathlib import Path

sys.path.insert(0, str(Path.home() / "dev" / "timus"))

from dotenv import load_dotenv
load_dotenv(Path.home() / "dev" / "timus" / ".env")

from faster_whisper import WhisperModel
from elevenlabs.client import ElevenLabs

from main_dispatcher import (
    run_agent,
    get_agent_decision,
    fetch_tool_descriptions_from_server,
    quick_intent_check
)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "onwK4e9ZLuTAKqWW03F9"
SAMPLE_RATE = 16000
EXIT_COMMANDS = ["stop", "beenden", "ende", "tschüss", "auf wiedersehen"]


class TimusVoiceChat:
    def __init__(self):
        self.whisper = None
        self.elevenlabs = None
        self.tools_description = None
    
    async def initialize(self):
        print("🚀 Initialisiere Timus Voice...")
        
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
        
        print("   🔧 Lade Tool-Beschreibungen...")
        self.tools_description = await fetch_tool_descriptions_from_server()
        if self.tools_description:
            print("   ✅ Tools geladen")
        else:
            print("   ⚠️ MCP Server nicht erreichbar")
            return False
        
        print("✅ Initialisierung abgeschlossen!\n")
        return True
    
    def listen(self, duration=5.0):
        """Nimmt Sprache auf - feste Dauer."""
        print("🎤 Höre zu... (sprich jetzt)")
        
        audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
        sd.wait()
        audio = audio.flatten()
        
        print("   🔄 Transkribiere...")
        segments, _ = self.whisper.transcribe(audio, language="de", vad_filter=True)
        text = " ".join([s.text.strip() for s in segments])
        return text
    
    def speak(self, text):
        """Spricht Text mit ElevenLabs."""
        # None-Check!
        if text is None:
            text = "Ich habe leider keine Antwort erhalten."
        
        if not text.strip():
            return
        
        if len(text) > 500:
            text = text[:500] + "... Ich habe die Antwort gekürzt."
        
        print(f"🔊 Timus: {text}")
        
        try:
            audio = self.elevenlabs.text_to_speech.convert(
                text=text,
                voice_id=VOICE_ID,
                model_id="eleven_multilingual_v2"
            )
            
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                for chunk in audio:
                    f.write(chunk)
                temp_path = f.name
            
            os.system(f"ffplay -nodisp -autoexit '{temp_path}' 2>/dev/null")
            os.unlink(temp_path)
            
        except Exception as e:
            print(f"   ❌ Sprachausgabe Fehler: {e}")
    
    async def process_with_timus(self, text: str) -> str:
        """Sendet Text an Timus Agent."""
        try:
            print("   🤔 Timus denkt...")
            
            agent_name = quick_intent_check(text)
            if not agent_name:
                agent_name = await get_agent_decision(text)
            
            print(f"   📌 Agent: {agent_name.upper()}")
            
            result = await run_agent(agent_name, text, self.tools_description)
            
            # None-Check!
            if result is None:
                return "Ich konnte keine Antwort generieren."
            
            return str(result)
            
        except Exception as e:
            return f"Entschuldigung, es gab einen Fehler: {e}"
    
    async def chat_loop(self):
        """Haupt-Chat-Schleife."""
        self.speak("Hallo! Ich bin Timus. Wie kann ich dir helfen?")
        
        while True:
            try:
                text = await asyncio.to_thread(self.listen)
                
                if not text.strip():
                    print("   (keine Sprache erkannt)")
                    continue
                
                print(f"👤 Du: {text}")
                
                if any(cmd in text.lower() for cmd in EXIT_COMMANDS):
                    self.speak("Auf Wiedersehen!")
                    break
                
                response = await self.process_with_timus(text)
                await asyncio.to_thread(self.speak, response)
                print()
                
            except KeyboardInterrupt:
                print("\n👋 Beende Voice Chat...")
                break
            except Exception as e:
                print(f"❌ Fehler: {e}")
                import traceback
                traceback.print_exc()
                continue


async def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║              🎤 TIMUS VOICE CHAT 🔊                        ║
║                                                            ║
║  Du hast 5 Sekunden zum Sprechen.                         ║
║  Sage "Stop" oder "Beenden" zum Beenden.                  ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    chat = TimusVoiceChat()
    
    if not await chat.initialize():
        print("❌ Initialisierung fehlgeschlagen!")
        return
    
    await chat.chat_loop()
    print("\n✅ Voice Chat beendet.")


if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
Timus Voice + Dispatcher Integration
Kombiniert Voice-Input/Output mit dem Multi-Agent Dispatching System
"""

import asyncio
import os
import sys
import tempfile
import threading
import queue
import time
import atexit
import httpx
import numpy as np
import sounddevice as sd
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

sys.path.insert(0, str(Path.home() / "dev" / "timus"))

from dotenv import load_dotenv
load_dotenv(Path.home() / "dev" / "timus" / ".env")

from faster_whisper import WhisperModel
import requests
import base64

# Dispatcher Imports
from main_dispatcher import (
    run_agent,
    get_agent_decision,
    fetch_tool_descriptions_from_server,
    quick_intent_check,
    AGENT_CLASS_MAP
)

# Memory System
from memory import memory_manager, get_memory_context, add_to_memory, end_session

# Emotion Detection
try:
    from emotion_detector import get_emotion_detector
    EMOTION_ENABLED = True
except ImportError:
    EMOTION_ENABLED = False

# Personality
try:
    from config import get_greeting, get_reaction
    PERSONALITY_ENABLED = True
except ImportError:
    PERSONALITY_ENABLED = False
    def get_greeting(name=None): return "Hallo!"
    def get_reaction(t): return ""

# Konfiguration
INWORLD_API_KEY = os.getenv("INWORLD_API_KEY")
INWORLD_VOICE = os.getenv("INWORLD_VOICE", "Ashley")
INWORLD_MODEL = os.getenv("INWORLD_MODEL", "inworld-tts-1.5-max")
INWORLD_SPEAKING_RATE = float(os.getenv("INWORLD_SPEAKING_RATE", "1.3"))
INWORLD_TEMPERATURE = float(os.getenv("INWORLD_TEMPERATURE", "1.5"))
SAMPLE_RATE = 16000
EXIT_COMMANDS = ["stop", "beenden", "ende", "tschüss", "exit", "quit", "pause"]

# VAD Settings
VAD_THRESHOLD = 0.003
VAD_SILENCE_DURATION = 1.5
VAD_MIN_SPEECH_DURATION = 0.5

# Voice-Modus Settings
CONTINUOUS_VOICE_MODE = True  # Immer Voice-Input bereit
VOICE_ACTIVITY_TIMEOUT = 30.0  # Sekunden bis "Noch da?"


class TimusVoiceDispatcher:
    """
    Kombiniert Voice I/O mit dem Timus Multi-Agent Dispatcher.
    
    Features:
    - Kontinuierliches Voice Listening (wie OpenClaw's Voice Wake)
    - Automatische Agent-Auswahl via Dispatcher
    - Emotion-aware Responses
    - Persistent Memory Integration
    - Parallel Text + Voice Input
    """
    
    def __init__(self):
        self.whisper: Optional[WhisperModel] = None
        self.inworld_api_key: Optional[str] = None
        self.tools_description: Optional[str] = None
        self.emotion_detector = None
        
        # Queues
        self.input_queue: queue.Queue = queue.Queue()
        self.tts_queue: queue.Queue = queue.Queue()
        self.running = False
        self.is_speaking = False
        self.is_processing = False
        
        # Voice State
        self.audio_buffer = []
        self.is_recording = False
        self.silence_start = None
        self.speech_start = None
        self.last_activity = time.time()
        
        # Emotion State
        self.current_emotion = "neutral"
        self.emotion_confidence = 0.0
        
        # Stats
        self.session_stats = {
            "voice_inputs": 0,
            "text_inputs": 0,
            "agent_calls": {},
            "start_time": datetime.now()
        }
        
        atexit.register(self._cleanup)
    
    def _cleanup(self):
        """Speichert Memory bei Beendigung."""
        print("\n💾 Speichere Session Memory...")
        end_session()
        print(f"📊 Session Stats: {self.session_stats}")
    
    async def initialize(self) -> bool:
        """Initialisiert alle Komponenten."""
        print("🚀 Timus Voice + Dispatcher Integration")
        print("=" * 60)
        
        # Whisper laden
        print("\n1️⃣ Lade Whisper (Speech-to-Text)...")
        try:
            self.whisper = WhisperModel("medium", device="cuda", compute_type="float16")
            print("   ✅ Whisper auf CUDA geladen")
        except:
            self.whisper = WhisperModel("medium", device="cpu", compute_type="int8")
            print("   ⚠️ Whisper auf CPU geladen (langsamer)")
        
        # Inworld.AI TTS
        print("\n2️⃣ Verbinde Inworld.AI (Text-to-Speech)...")
        if INWORLD_API_KEY:
            self.inworld_api_key = INWORLD_API_KEY
            print(f"   ✅ Voice: {INWORLD_VOICE} | Rate: {INWORLD_SPEAKING_RATE}x | Temp: {INWORLD_TEMPERATURE}")
        else:
            print("   ❌ Kein INWORLD_API_KEY - TTS deaktiviert")
        
        # Emotion Detector
        if EMOTION_ENABLED:
            print("\n3️⃣ Lade Emotion Detector...")
            try:
                self.emotion_detector = get_emotion_detector()
                print("   ✅ Emotion Detection aktiv")
            except Exception as e:
                print(f"   ⚠️ Emotion Detector Fehler: {e}")
        
        # Tools laden
        print("\n4️⃣ Lade Agent Tools...")
        self.tools_description = await fetch_tool_descriptions_from_server()
        if self.tools_description:
            print("   ✅ MCP Server verbunden")
        else:
            print("   ❌ MCP Server nicht erreichbar!\n      Starte: python server/mcp_server.py")
            return False
        
        # Memory Status
        print("\n5️⃣ Memory System...")
        stats = memory_manager.get_stats()
        print(f"   🧠 {stats['total_facts']} Fakten | {stats['total_summaries']} Zusammenfassungen")
        
        print("\n" + "=" * 60)
        print("✅ Bereit! Spreche einfach los oder tippe einen Befehl.")
        print("   Befehle: 'stop' = Beenden | 'text' = Text-Modus | 'voice' = Voice-Modus")
        print("=" * 60 + "\n")
        return True
    
    def audio_callback(self, indata, frames, time_info, status):
        """Kontinuierliches Audio-Monitoring mit VAD."""
        if self.is_speaking or self.is_processing:
            return
        
        volume = np.abs(indata).mean()
        
        if volume > VAD_THRESHOLD:
            if not self.is_recording:
                self.is_recording = True
                self.speech_start = time.time()
                self.audio_buffer = []
                print("\n🎤 [Höre zu...]", end="", flush=True)
            
            self.audio_buffer.append(indata.copy())
            self.silence_start = None
            self.last_activity = time.time()
            
        elif self.is_recording:
            self.audio_buffer.append(indata.copy())
            
            if self.silence_start is None:
                self.silence_start = time.time()
            elif time.time() - self.silence_start > VAD_SILENCE_DURATION:
                speech_duration = time.time() - self.speech_start - VAD_SILENCE_DURATION
                
                if speech_duration >= VAD_MIN_SPEECH_DURATION:
                    audio_data = np.concatenate(self.audio_buffer)
                    self.input_queue.put(("voice", audio_data))
                    print(" ✓")
                else:
                    print(" (ignoriert - zu kurz)")
                
                self.is_recording = False
                self.audio_buffer = []
                self.silence_start = None
    
    def start_continuous_listener(self):
        """Startet kontinuierlichen Audio-Listener (wie OpenClaw Voice Wake)."""
        def audio_thread():
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype='float32',
                blocksize=int(SAMPLE_RATE * 0.1),
                callback=self.audio_callback
            ):
                print("👂 Kontinuierliches Listening aktiv...")
                while self.running:
                    # Check für Inaktivität
                    if time.time() - self.last_activity > VOICE_ACTIVITY_TIMEOUT:
                        if not self.is_speaking and not self.is_processing:
                            pass  # Optional: "Noch da?" Prompt
                    time.sleep(0.1)
        
        thread = threading.Thread(target=audio_thread, daemon=True)
        thread.start()
        return thread
    
    def start_keyboard_listener(self):
        """Keyboard-Listener für Text-Input."""
        def keyboard_thread():
            while self.running:
                try:
                    text = input()
                    if text.strip():
                        self.input_queue.put(("text", text.strip()))
                        self.last_activity = time.time()
                except EOFError:
                    break
        
        thread = threading.Thread(target=keyboard_thread, daemon=True)
        thread.start()
        return thread
    
    def transcribe(self, audio: np.ndarray) -> str:
        """Whisper Transkription."""
        if len(audio.shape) > 1:
            audio = audio.flatten()
        
        segments, _ = self.whisper.transcribe(audio, language="de", vad_filter=True)
        text = " ".join([s.text.strip() for s in segments])
        return text
    
    def detect_emotion(self, audio: np.ndarray) -> dict:
        """Erkennt Emotion aus Audio."""
        if not self.emotion_detector:
            return {"emotion": "neutral", "confidence": 0.0}
        
        try:
            return self.emotion_detector.detect_from_array(audio, SAMPLE_RATE)
        except Exception as e:
            return {"emotion": "neutral", "confidence": 0.0}
    
    def speak(self, text: str, emotion: str = "neutral"):
        """Text-to-Speech mit Inworld.AI."""
        if not self.inworld_api_key or not text.strip():
            return
        
        self.is_speaking = True
        
        try:
            # Emotion-basierte Parameter-Anpassung
            temp = INWORLD_TEMPERATURE
            rate = INWORLD_SPEAKING_RATE
            
            if emotion == "excited":
                temp = min(temp + 0.3, 2.0)
                rate = min(rate + 0.2, 1.5)
            elif emotion == "sad":
                temp = max(temp - 0.3, 0.5)
                rate = max(rate - 0.2, 0.8)
            elif emotion == "calm":
                rate = max(rate - 0.1, 0.9)
            
            if len(text) > 500:
                text = text[:500] + "..."
            
            url = "https://api.inworld.ai/tts/v1/voice"
            headers = {
                "Authorization": f"Basic {self.inworld_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "text": text,
                "voiceId": INWORLD_VOICE,
                "modelId": INWORLD_MODEL,
                "voiceSettings": {"speaking_rate": rate},
                "temperature": temp
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            audio_bytes = base64.b64decode(result['audioContent'])
            
            # Audio abspielen
            import io
            from pydub import AudioSegment
            
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
            samples = samples / np.max(np.abs(samples))
            
            if audio_segment.channels == 2:
                samples = samples.reshape((-1, 2)).mean(axis=1)
            
            sd.play(samples, samplerate=audio_segment.frame_rate)
            sd.wait()
            
        except Exception as e:
            print(f"   ⚠️ TTS Fehler: {e}")
        finally:
            self.is_speaking = False
    
    def _build_enhanced_prompt(self, user_input: str, input_type: str) -> str:
        """Baut erweiterten Prompt mit Memory und Kontext."""
        memory_context = get_memory_context()
        emotion_context = f"[EMOTION: {self.current_emotion}]" if self.current_emidence > 0.6 else ""
        
        base = f"""INPUT_TYPE: {input_type}
{emotion_context}

USER_INPUT:
{user_input}"""
        
        if memory_context:
            base = f"{memory_context}\n\n{base}"
        
        return base
    
    async def process_voice_input(self, audio: np.ndarray) -> str:
        """Verarbeitet Voice-Input durch den Dispatcher."""
        self.is_processing = True
        self.session_stats["voice_inputs"] += 1
        
        try:
            # 1. Transkribieren
            print("   🔄 Transkribiere...")
            text = await asyncio.to_thread(self.transcribe, audio)
            
            if not text.strip():
                return ""
            
            # 2. Emotion erkennen
            if self.emotion_detector:
                emotion_result = await asyncio.to_thread(self.detect_emotion, audio)
                self.current_emotion = emotion_result.get("emotion", "neutral")
                self.emotion_confidence = emotion_result.get("confidence", 0.0)
                
                if self.emotion_confidence > 0.6:
                    emoji = {"happy": "😊", "sad": "😔", "angry": "😤", 
                            "neutral": "😐", "excited": "🤩", "calm": "😌"}.get(
                                self.current_emotion, "🎭"
                            )
                    print(f"   🎭 {self.current_emotion} {emoji}")
            
            print(f"👤 {text}")
            
            # 3. Enhanced Prompt bauen
            enhanced = self._build_enhanced_prompt(text, "VOICE")
            
            # 4. Dispatcher: Agent auswählen
            print("   🤔 Analysiere...")
            agent = quick_intent_check(enhanced) or await get_agent_decision(enhanced)
            print(f"   📌 {agent.upper()}")
            
            # Stats
            self.session_stats["agent_calls"][agent] = self.session_stats["agent_calls"].get(agent, 0) + 1
            
            # 5. Agent ausführen
            result = await run_agent(agent, enhanced, self.tools_description)
            
            if result:
                # Memory speichern
                add_to_memory(text, str(result))
                return str(result)
            else:
                return "Ich konnte keine Antwort generieren."
                
        except Exception as e:
            print(f"❌ Fehler: {e}")
            return f"Es ist ein Fehler aufgetreten: {str(e)}"
        finally:
            self.is_processing = False
    
    async def process_text_input(self, text: str) -> str:
        """Verarbeitet Text-Input durch den Dispatcher."""
        self.is_processing = True
        self.session_stats["text_inputs"] += 1
        self.current_emotion = "neutral"  # Text hat keine Audio-Emotion
        
        try:
            # Special Commands
            if text.lower() in ["stop", "exit", "quit", "beenden"]:
                return "__EXIT__"
            
            if text.lower() == "status":
                return self._get_status_report()
            
            if text.lower() == "memory":
                return self._get_memory_summary()
            
            print(f"👤 (Text) {text}")
            
            # Enhanced Prompt
            enhanced = self._build_enhanced_prompt(text, "TEXT")
            
            # Dispatcher
            print("   🤔 Analysiere...")
            agent = quick_intent_check(enhanced) or await get_agent_decision(enhanced)
            print(f"   📌 {agent.upper()}")
            
            self.session_stats["agent_calls"][agent] = self.session_stats["agent_calls"].get(agent, 0) + 1
            
            # Agent ausführen
            result = await run_agent(agent, enhanced, self.tools_description)
            
            if result:
                add_to_memory(text, str(result))
                return str(result)
            else:
                return "Ich konnte keine Antwort generieren."
                
        except Exception as e:
            print(f"❌ Fehler: {e}")
            return f"Es ist ein Fehler aufgetreten: {str(e)}"
        finally:
            self.is_processing = False
    
    def _get_status_report(self) -> str:
        """Gibt Session-Status zurück."""
        stats = self.session_stats
        duration = datetime.now() - stats["start_time"]
        
        report = f"""📊 Session Status:
⏱️  Laufzeit: {duration.seconds // 60}m {duration.seconds % 60}s
🎤 Voice Inputs: {stats['voice_inputs']}
⌨️  Text Inputs: {stats['text_inputs']}
🤖 Agent Aufrufe:"""
        
        for agent, count in stats["agent_calls"].items():
            report += f"\n   • {agent}: {count}x"
        
        return report
    
    def _get_memory_summary(self) -> str:
        """Gibt Memory-Zusammenfassung zurück."""
        stats = memory_manager.get_stats()
        
        # Letzte Fakten
        facts = memory_manager.persistent.get_all_facts()[:5]
        fact_str = "\n".join([f"   • {f.key}: {f.value}" for f in facts]) if facts else "   (keine)"
        
        return f"""🧠 Memory Status:
📚 {stats['total_facts']} persistente Fakten
📝 {stats['total_summaries']} Zusammenfassungen

Letzte Fakten:
{fact_str}"""
    
    async def main_loop(self):
        """Haupt-Event-Loop für Voice + Text + Dispatcher."""
        self.running = True
        
        # Listener starten
        audio_thread = self.start_continuous_listener()
        keyboard_thread = self.start_keyboard_listener()
        
        # Begrüßung
        name_fact = memory_manager.persistent.get_fact("preference", "preferred_name")
        user_name = name_fact.value if name_fact else None
        
        greeting = get_greeting(user_name) if PERSONALITY_ENABLED else (
            f"Hallo {user_name}!" if user_name else "Hallo! Ich bin Timus mit Voice."
        )
        
        print(f"\n🔊 {greeting}")
        await asyncio.to_thread(self.speak, greeting)
        
        print("\n💡 Tippe 'status' für Stats | 'memory' für Gedächtnis | 'stop' zum Beenden\n")
        
        # Main Loop
        while self.running:
            try:
                # Input holen (blockierend mit Timeout)
                try:
                    input_type, content = self.input_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                # Verarbeiten
                if input_type == "voice":
                    response = await self.process_voice_input(content)
                else:
                    response = await self.process_text_input(content)
                
                # Exit Check
                if response == "__EXIT__":
                    farewell = "Auf Wiedersehen! Ich speichere unsere Session."
                    print(f"\n🔊 {farewell}")
                    await asyncio.to_thread(self.speak, farewell, "calm")
                    break
                
                # Ausgabe
                if response:
                    print(f"\n🔊 Timus: {response}\n")
                    await asyncio.to_thread(self.speak, response, self.current_emotion)
                    
                    # Emotion zurücksetzen
                    self.current_emotion = "neutral"
                    self.emotion_confidence = 0.0
                    
            except KeyboardInterrupt:
                print("\n\n👋 Beende...")
                break
            except Exception as e:
                print(f"❌ Loop Fehler: {e}")
                continue
        
        self.running = False


async def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║     🤖 TIMUS VOICE + DISPATCHER INTEGRATION v1.0 🤖         ║
║                                                              ║
║   🎤 Voice Input: Sprich einfach los                        ║
║   ⌨️  Text Input: Tippe Befehle                            ║
║   🧠 Multi-Agent: Executor | Research | Visual | etc.     ║
║   🎭 Emotion-Aware: Erkennt Stimmung aus Sprache         ║
║   💾 Persistent Memory: Merkt sich alles                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    timus = TimusVoiceDispatcher()
    
    if not await timus.initialize():
        print("❌ Initialisierung fehlgeschlagen!")
        print("   Starte zuerst: python server/mcp_server.py")
        return 1
    
    try:
        await timus.main_loop()
    except Exception as e:
        print(f"\n❌ Fataler Fehler: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n✅ Timus Voice Dispatcher beendet.")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

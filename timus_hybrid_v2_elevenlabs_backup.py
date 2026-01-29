#!/usr/bin/env python3
"""
Timus Hybrid v2 - Mit Memory System + Emotion Detection

Features:
- Text UND Voice parallel
- Conversation Memory (erinnert sich an Kontext)
- Persistent Memory (merkt sich Fakten über dich)
- Automatische Zusammenfassung bei Session-Ende
- Emotion Detection (erkennt Stimmung aus Sprache)
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
from typing import Optional
from datetime import datetime

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

# Memory System importieren
from memory import memory_manager, get_memory_context, add_to_memory, end_session

# Emotion Detector importieren
try:
    from emotion_detector import get_emotion_detector
    EMOTION_ENABLED = True
except ImportError:
    EMOTION_ENABLED = False
    print("⚠️ Emotion Detector nicht verfügbar")

# Persönlichkeits-System importieren
try:
    from config import get_greeting, get_reaction
    PERSONALITY_ENABLED = True
except ImportError:
    PERSONALITY_ENABLED = False
    def get_greeting(name=None): return "Hallo!"
    def get_reaction(t): return ""

# Konfiguration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "IKne3meq5aSn9XLyUdCD"
SAMPLE_RATE = 16000
EXIT_COMMANDS = ["stop", "beenden", "ende", "tschüss", "exit", "quit"]

# VAD Einstellungen
VAD_THRESHOLD = 0.003
VAD_SILENCE_DURATION = 1.5
VAD_MIN_SPEECH_DURATION = 0.5


class TimusHybridWithMemory:
    def __init__(self):
        self.whisper: Optional[WhisperModel] = None
        self.elevenlabs: Optional[ElevenLabs] = None
        self.tools_description: Optional[str] = None
        self.emotion_detector = None
        
        # Queues und Status
        self.input_queue: queue.Queue = queue.Queue()
        self.running = False
        self.is_speaking = False
        self.is_processing = False
        
        # Audio Buffer für VAD
        self.audio_buffer = []
        self.is_recording = False
        self.silence_start = None
        self.speech_start = None
        
        # Aktuelle Emotion
        self.current_emotion = "neutral"
        self.emotion_confidence = 0.0
        
        # Bei Beendigung Session speichern
        atexit.register(self._cleanup)
    
    def _cleanup(self):
        """Cleanup bei Beendigung."""
        print("\n💾 Speichere Memory...")
        end_session()
    
    async def initialize(self):
        """Initialisiert alle Komponenten."""
        print("🚀 Initialisiere Timus Hybrid v2 (mit Memory + Emotion)...")
        
        # Whisper
        print("   📥 Lade Whisper (medium)...")
        try:
            self.whisper = WhisperModel("medium", device="cuda", compute_type="float16")
        except:
            self.whisper = WhisperModel("medium", device="cpu", compute_type="int8")
        print("   ✅ Whisper geladen")
        
        # ElevenLabs
        if ELEVENLABS_API_KEY:
            self.elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            print("   ✅ ElevenLabs verbunden")
        else:
            print("   ⚠️ ElevenLabs nicht konfiguriert")
        
        # Emotion Detector
        if EMOTION_ENABLED:
            print("   🎭 Lade Emotion Detector...")
            try:
                self.emotion_detector = get_emotion_detector()
                print("   ✅ Emotion Detector geladen")
            except Exception as e:
                print(f"   ⚠️ Emotion Detector Fehler: {e}")
                self.emotion_detector = None
        
        # Tools
        print("   🔧 Lade Tool-Beschreibungen...")
        self.tools_description = await fetch_tool_descriptions_from_server()
        if self.tools_description:
            print("   ✅ Tools geladen")
        else:
            print("   ❌ MCP Server nicht erreichbar!")
            return False
        
        # Memory Stats
        stats = memory_manager.get_stats()
        print(f"   🧠 Memory: {stats['total_facts']} Fakten, {stats['total_summaries']} Zusammenfassungen")
        
        print("✅ Initialisierung abgeschlossen!\n")
        return True
    
    def audio_callback(self, indata, frames, time_info, status):
        """Callback für kontinuierliches Audio-Sampling."""
        if self.is_speaking or self.is_processing:
            return
        
        volume = np.abs(indata).mean()
        
        if volume > VAD_THRESHOLD:
            if not self.is_recording:
                self.is_recording = True
                self.speech_start = time.time()
                self.audio_buffer = []
                print("\n🎤 [Sprache erkannt...]", end="", flush=True)
            
            self.audio_buffer.append(indata.copy())
            self.silence_start = None
            
        elif self.is_recording:
            self.audio_buffer.append(indata.copy())
            
            if self.silence_start is None:
                self.silence_start = time.time()
            elif time.time() - self.silence_start > VAD_SILENCE_DURATION:
                speech_duration = time.time() - self.speech_start - VAD_SILENCE_DURATION
                
                if speech_duration >= VAD_MIN_SPEECH_DURATION:
                    audio_data = np.concatenate(self.audio_buffer)
                    self.input_queue.put(("audio", audio_data))
                    print(" ✓")
                else:
                    print(" (zu kurz)")
                
                self.is_recording = False
                self.audio_buffer = []
                self.silence_start = None
    
    def start_audio_listener(self):
        """Startet den Audio-Listener."""
        def audio_thread():
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype='float32',
                blocksize=int(SAMPLE_RATE * 0.1),
                callback=self.audio_callback
            ):
                while self.running:
                    time.sleep(0.1)
        
        thread = threading.Thread(target=audio_thread, daemon=True)
        thread.start()
        return thread
    
    def start_keyboard_listener(self):
        """Startet den Keyboard-Listener."""
        def keyboard_thread():
            while self.running:
                try:
                    text = input()
                    if text.strip():
                        self.input_queue.put(("text", text.strip()))
                except EOFError:
                    break
        
        thread = threading.Thread(target=keyboard_thread, daemon=True)
        thread.start()
        return thread
    
    def transcribe(self, audio: np.ndarray) -> str:
        """Transkribiert Audio zu Text."""
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
            result = self.emotion_detector.detect_from_array(audio, SAMPLE_RATE)
            return result
        except Exception as e:
            print(f"   ⚠️ Emotion Detection Fehler: {e}")
            return {"emotion": "neutral", "confidence": 0.0}
    
    def get_emotion_prefix(self, emotion: str) -> str:
        """Gibt passenden Antwort-Prefix basierend auf Emotion zurück."""
        if not self.emotion_detector:
            return ""
        
        style = self.emotion_detector.get_response_style(emotion)
        return style.get("prefix", "")
    
    def speak(self, text: str):
        """Spricht Text mit ElevenLabs."""
        if not self.elevenlabs or not text.strip():
            return
        
        self.is_speaking = True
        
        try:
            if len(text) > 500:
                text = text[:500] + "..."
            
            # Neue ElevenLabs API
            audio_data = self.elevenlabs.text_to_speech.convert(
                text=text,
                voice_id=VOICE_ID,
                model_id="eleven_multilingual_v2"
            )
            
            # Audio-Daten sammeln (Generator)
            audio_bytes = b"".join(chunk for chunk in audio_data)
            
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
    
    def _build_prompt_with_memory(self, user_input: str) -> str:
        """Baut Prompt mit Memory-Kontext."""
        memory_context = get_memory_context()
        
        if memory_context:
            return f"""{memory_context}

AKTUELLE ANFRAGE:
{user_input}

WICHTIG: Nutze den Kontext um die Anfrage zu verstehen. Wenn sich der Benutzer auf etwas Vorheriges bezieht (er, sie, das, etc.), nutze die bekannten Informationen."""
        
        return user_input

    async def process_input(self, input_type: str, content) -> str:
        """Verarbeitet Eingabe durch Timus mit Memory."""
        self.is_processing = True
        
        try:
            # Bei Audio: Transkribieren UND Emotion erkennen
            if input_type == "audio":
                print("   🔄 Transkribiere...")
                text = await asyncio.to_thread(self.transcribe, content)
                if not text.strip():
                    return ""
                
                # Emotion parallel erkennen
                if self.emotion_detector:
                    emotion_result = await asyncio.to_thread(self.detect_emotion, content)
                    self.current_emotion = emotion_result.get("emotion", "neutral")
                    self.emotion_confidence = emotion_result.get("confidence", 0.0)
                    
                    if self.emotion_confidence > 0.6:
                        emotion_emoji = {"happy": "😊", "sad": "😔", "angry": "😤", "neutral": "😐"}.get(self.current_emotion, "🎭")
                        print(f"   🎭 Emotion: {self.current_emotion} {emotion_emoji} ({self.emotion_confidence*100:.0f}%)")
                
                print(f"👤 Du (Voice): {text}")
                # Markiere als Spracheingabe für den Agent
                text = f"[SPRACHEINGABE via Mikrofon] {text}"
            else:
                text = content
                print(f"👤 Du (Text): {text}")
                # Markiere als Texteingabe für den Agent  
                text = f"[TEXTEINGABE via Tastatur] {text}"
                # Bei Text keine Emotion erkennen
                self.current_emotion = "neutral"
                self.emotion_confidence = 0.0
            
            # Exit-Check (aber nicht wenn es um Aufzeichnung geht)
            if any(cmd in text.lower() for cmd in EXIT_COMMANDS) and "aufzeichnung" not in text.lower() and "aufnahme" not in text.lower():
                return "__EXIT__"
            
            # Memory-Befehle prüfen
            text_lower = text.lower()
            
            if "was weißt du über mich" in text_lower or "was erinnerst du" in text_lower:
                facts = memory_manager.persistent.get_all_facts()
                if facts:
                    fact_list = "\n".join([f"- {f.key}: {f.value}" for f in facts[:10]])
                    return f"Das weiß ich über dich:\n{fact_list}"
                else:
                    return "Ich habe noch keine Informationen über dich gespeichert."
            
            if "vergiss" in text_lower and ("alles" in text_lower or "memory" in text_lower):
                # Gefährlich - nachfragen
                return "Bist du sicher? Sage 'Ja, vergiss alles' um dein Memory zu löschen."
            
            if "ja, vergiss alles" in text_lower:
                memory_manager.session.clear()
                # DB löschen wäre hier - aber das ist destruktiv
                return "Ich habe mein Kurzzeit-Gedächtnis gelöscht. Die langfristigen Fakten bleiben erhalten."
            
            # === SKILL RECORDING BEFEHLE ===
            def is_recording_start_command(text: str) -> bool:
                """Prüft ob es ein Recording-Start-Befehl ist (robust)."""
                t = text.lower()
                # Kernwörter die auf Recording hindeuten
                recording_words = ["aufzeichnung", "aufnahme", "recording", "aufzeich", "aufnah"]
                action_words = ["start", "beginn", "lerne", "nehme", "mach"]
                skill_words = ["skill", "fähigkeit", "aktion"]
                
                has_recording = any(w in t for w in recording_words)
                has_action = any(w in t for w in action_words)
                has_skill = any(w in t for w in skill_words)
                
                # "aufzeichnung" + irgendein Aktionswort ODER "skill" + "lerne/aufnehmen"
                return (has_recording and has_action) or (has_skill and has_action) or ("lerne" in t and "skill" in t)
            
            def is_recording_stop_command(text: str) -> bool:
                """Prüft ob es ein Recording-Stop-Befehl ist (robust)."""
                t = text.lower()
                stop_words = ["beende", "stopp", "stop", "fertig", "ende", "speicher"]
                recording_words = ["aufzeichnung", "aufnahme", "recording", "aufzeich"]
                
                has_stop = any(w in t for w in stop_words)
                has_recording = any(w in t for w in recording_words)
                
                return has_stop and has_recording
            
            def extract_skill_name(text: str) -> str:
                """Extrahiert Skill-Namen aus dem Text."""
                import re
                t = text.lower()
                # Suche nach "für X", "namens X", "genannt X"
                patterns = [
                    r'(?:für|namens|genannt|called|name)\s+["\']?(\w+)["\']?',
                    r'skill\s+["\']?(\w+)["\']?',
                    r'(\w+)\s*(?:skill|aufzeichnung|aufnahme)$'
                ]
                for pattern in patterns:
                    match = re.search(pattern, t)
                    if match:
                        name = match.group(1)
                        # Filtere generische Wörter
                        if name not in ["für", "die", "der", "das", "eine", "einen", "skill", "aufzeichnung"]:
                            return name
                return f"skill_{int(time.time())}"
            
            # Recording Start
            if is_recording_start_command(text):
                skill_name = extract_skill_name(text)
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post("http://127.0.0.1:5000", json={
                        "jsonrpc": "2.0",
                        "method": "start_skill_recording",
                        "params": {"skill_name": skill_name, "description": f"Aufgezeichneter Skill: {skill_name}"},
                        "id": 1
                    })
                    result = r.json()
                    if "result" in result:
                        return f"🎬 Aufzeichnung gestartet für '{skill_name}'! Führe jetzt deine Aktionen aus. Sage 'Beende Aufzeichnung' wenn fertig."
                    else:
                        return f"❌ Fehler: {result.get('error', {}).get('message', 'Unbekannt')}"
            
            # Recording Stop
            if is_recording_stop_command(text):
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post("http://127.0.0.1:5000", json={
                        "jsonrpc": "2.0",
                        "method": "stop_skill_recording",
                        "params": {"save": True},
                        "id": 1
                    })
                    result = r.json()
                    if "result" in result:
                        res = result["result"]
                        return f"✅ Skill '{res.get('skill_name')}' gespeichert mit {res.get('steps_count', '?')} Schritten!"
                    else:
                        return f"❌ Fehler: {result.get('error', {}).get('message', 'Unbekannt')}"
            
            # Recording Status
            if "status" in text_lower and any(w in text_lower for w in ["aufzeichnung", "recording", "aufnahme"]):
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post("http://127.0.0.1:5000", json={
                        "jsonrpc": "2.0",
                        "method": "get_recording_status",
                        "params": {},
                        "id": 1
                    })
                    result = r.json().get("result", {})
                    if result.get("active"):
                        return f"🎬 Aufzeichnung läuft: '{result.get('skill_name')}' - {result.get('action_count')} Aktionen"
                    else:
                        return "📴 Keine Aufzeichnung aktiv."
            # === ENDE SKILL RECORDING ===
            
            # === SKILL AUSFÜHRUNG ===
            def is_skill_list_command(text: str) -> bool:
                t = text.lower()
                list_words = ["liste", "zeige", "welche", "verfügbar", "gelernt", "kennst"]
                skill_words = ["skill", "fähigkeit", "können"]
                return any(l in t for l in list_words) and any(s in t for s in skill_words)
            
            def is_skill_run_command(text: str) -> tuple:
                """Prüft ob Skill ausgeführt werden soll. Returns (True/False, skill_name)"""
                import re
                t = text.lower()
                run_words = ["führe", "starte", "nutze", "ausführen", "run", "execute"]
                
                if any(w in t for w in run_words) and "skill" in t:
                    # Extrahiere Skill-Namen
                    match = re.search(r'skill\s+["\']?(\w+)["\']?', t)
                    if match:
                        return True, match.group(1)
                return False, None
            
            # Skill-Liste
            if is_skill_list_command(text):
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post("http://127.0.0.1:5000", json={
                        "jsonrpc": "2.0",
                        "method": "list_available_skills",
                        "id": 1
                    })
                    result = r.json().get("result", {})
                    skills = result.get("skills", [])
                    if skills:
                        skill_list = "\n".join([f"• {s['name']}: {s['description'][:50]}" for s in skills])
                        return f"📚 Meine erlernten Skills:\n{skill_list}"
                    else:
                        return "Ich habe noch keine Skills gelernt."
            
            # Skill ausführen
            should_run, skill_name = is_skill_run_command(text)
            if should_run and skill_name:
                async with httpx.AsyncClient(timeout=60) as client:
                    r = await client.post("http://127.0.0.1:5000", json={
                        "jsonrpc": "2.0",
                        "method": "run_skill",
                        "params": {"name": skill_name, "params": {}},
                        "id": 1
                    })
                    result = r.json()
                    if "result" in result:
                        return f"✅ Skill '{skill_name}' ausgeführt!"
                    else:
                        return f"❌ Fehler: {result.get('error', {}).get('message', 'Skill nicht gefunden')}"
            # === ENDE SKILL AUSFÜHRUNG ===

            # Prompt mit Memory bauen
            enhanced_prompt = self._build_prompt_with_memory(text)
            
            # Agent entscheiden
            print("   🤔 Timus denkt...")
            agent_name = quick_intent_check(text)
            if not agent_name:
                agent_name = await get_agent_decision(text)
            
            print(f"   📌 Agent: {agent_name.upper()}")
            
            # Agent ausführen
            result = await run_agent(agent_name, enhanced_prompt, self.tools_description)
            
            if result is None:
                result = "Ich konnte keine Antwort generieren."
            
            # Emotion-basierte Antwort-Anpassung
            if self.current_emotion != "neutral" and self.emotion_confidence > 0.7:
                emotion_prefix = self.get_emotion_prefix(self.current_emotion)
                if emotion_prefix and not str(result).startswith(emotion_prefix):
                    result = emotion_prefix + str(result)
            
            # Interaktion im Memory speichern
            add_to_memory(text, str(result))
            
            return str(result)
            
        except Exception as e:
            return f"Fehler: {e}"
        finally:
            self.is_processing = False
    
    async def main_loop(self):
        """Haupt-Verarbeitungsschleife."""
        self.running = True
        
        # Listener starten
        self.start_audio_listener()
        self.start_keyboard_listener()
        
        # Begrüßung (personalisiert mit Persönlichkeit)
        name_fact = memory_manager.persistent.get_fact("preference", "preferred_name")
        if not name_fact:
            name_fact = memory_manager.persistent.get_fact("name", "name")
        
        user_name = name_fact.value if name_fact else None
        
        if PERSONALITY_ENABLED:
            greeting = get_greeting(user_name)
        elif user_name:
            greeting = f"Hallo {user_name}! Schön dich wiederzusehen."
        else:
            greeting = "Hallo! Ich bin Timus. Du kannst tippen oder sprechen."
        
        print(f"🔊 Timus: {greeting}")
        await asyncio.to_thread(self.speak, greeting)
        
        print("\n" + "─" * 60)
        print("📝 Tippe Text + Enter  ODER  🎤 Sprich einfach los")
        print("🧠 Memory aktiv - Ich erinnere mich an unser Gespräch")
        print("🎭 Emotion aktiv - Ich erkenne deine Stimmung")
        print("─" * 60 + "\n")
        
        while self.running:
            try:
                try:
                    input_type, content = self.input_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                response = await self.process_input(input_type, content)
                
                if not response:
                    continue
                
                if response == "__EXIT__":
                    print("🔊 Timus: Auf Wiedersehen! Ich speichere unser Gespräch.")
                    await asyncio.to_thread(self.speak, "Auf Wiedersehen! Ich speichere unser Gespräch.")
                    break
                
                print(f"\n🔊 Timus: {response}\n")
                await asyncio.to_thread(self.speak, response)
                
            except KeyboardInterrupt:
                print("\n\n👋 Beende Timus...")
                break
            except Exception as e:
                print(f"❌ Fehler: {e}")
                continue
        
        self.running = False


async def main():
    print("""
╔════════════════════════════════════════════════════════════════╗
║         🤖 TIMUS HYBRID v2 (MIT MEMORY + EMOTION) 🤖           ║
║                                                                ║
║   📝 Text: Tippe und drücke Enter                             ║
║   🎤 Voice: Sprich einfach los                                ║
║   🧠 Memory: Ich erinnere mich an unser Gespräch              ║
║   🎭 Emotion: Ich erkenne deine Stimmung                      ║
║                                                                ║
║   Sage "Stop" oder "Beenden" zum Beenden                      ║
║   Frage "Was weißt du über mich?" für Memory-Status           ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    timus = TimusHybridWithMemory()
    
    if not await timus.initialize():
        print("❌ Initialisierung fehlgeschlagen!")
        return
    
    await timus.main_loop()
    print("\n✅ Timus beendet.")


if __name__ == "__main__":
    asyncio.run(main())

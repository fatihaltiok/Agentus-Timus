#!/usr/bin/env python3
"""
Timus Hybrid v2 - Mit Memory System + Emotion Detection + Inworld.AI TTS

Features:
- Text UND Voice parallel
- Conversation Memory (erinnert sich an Kontext)
- Persistent Memory (merkt sich Fakten über dich)
- Automatische Zusammenfassung bei Session-Ende
- Emotion Detection (erkennt Stimmung aus Sprache)
- Inworld.AI TTS (50-75% günstiger als ElevenLabs, ~120-200ms Latenz)
"""

import asyncio
import os
import sys
import threading
import queue
import time
import atexit
import re
import uuid
import httpx
import numpy as np
import sounddevice as sd
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path.home() / "dev" / "timus"))

from dotenv import load_dotenv
load_dotenv(Path.home() / "dev" / "timus" / ".env", override=True)

from faster_whisper import WhisperModel

# Inworld.AI statt ElevenLabs (50-75% günstiger)
import requests
import base64

from main_dispatcher import (
    run_agent,
    get_agent_decision,
    fetch_tool_descriptions_from_server,
    quick_intent_check
)

# Memory System importieren
from memory import memory_manager, end_session

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
# Inworld.AI TTS (günstiger: $10/1M chars vs ElevenLabs ~$40/1M)
INWORLD_API_KEY = os.getenv("INWORLD_API_KEY")
INWORLD_VOICE = os.getenv("INWORLD_VOICE", "Ashley")
INWORLD_MODEL = os.getenv("INWORLD_MODEL", "inworld-tts-1.5-max")
INWORLD_SPEAKING_RATE = float(os.getenv("INWORLD_SPEAKING_RATE", "1.3"))  # 0.5-1.5, Standard: 1.0
INWORLD_TEMPERATURE = float(os.getenv("INWORLD_TEMPERATURE", "1.5"))      # Emotionale Varianz
SAMPLE_RATE = 16000
EXIT_COMMANDS = ["stop", "beenden", "ende", "tschüss", "exit", "quit"]
NEW_SESSION_COMMANDS = {
    "/new",
    "new session",
    "neue session",
    "neue konversation",
    "reset session",
}

# VAD Einstellungen
VAD_THRESHOLD = 0.003
VAD_SILENCE_DURATION = 1.5
VAD_MIN_SPEECH_DURATION = 0.5


class TimusHybridWithMemory:
    def __init__(self):
        self.whisper: Optional[WhisperModel] = None
        self.inworld_api_key: Optional[str] = None
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
        self.conversation_session_id = self._new_session_id()

        # Bei Beendigung Session speichern
        atexit.register(self._cleanup)

    @staticmethod
    def _new_session_id() -> str:
        return f"hybrid_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _sanitize_user_input(text: str) -> str:
        cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", str(text or ""))
        return re.sub(r"\s+", " ", cleaned).strip()

    def _log_local_interaction(
        self,
        user_input: str,
        assistant_response: str,
        status: str = "completed",
        command: str = "",
    ) -> None:
        """Lokale Kommandos ebenfalls deterministisch im Memory-Kern persistieren."""
        try:
            memory_manager.log_interaction_event(
                user_input=user_input,
                assistant_response=assistant_response,
                agent_name="hybrid_local",
                status=status,
                external_session_id=self.conversation_session_id,
                metadata={
                    "source": "timus_hybrid_v2",
                    "local_command": command,
                },
            )
        except Exception as e:
            print(f"   ⚠️ Lokales Logging fehlgeschlagen: {e}")
    
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
        
        # Inworld.AI TTS
        if INWORLD_API_KEY:
            self.inworld_api_key = INWORLD_API_KEY
            print(f"   ✅ Inworld.AI verbunden (Voice: {INWORLD_VOICE}, Model: {INWORLD_MODEL})")
        else:
            print("   ⚠️ Inworld.AI nicht konfiguriert (setze INWORLD_API_KEY in .env)")
        
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
        print(f"   🧵 Aktive Session: {self.conversation_session_id}")
        
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
        """Spricht Text mit Inworld.AI TTS (50-75% günstiger als ElevenLabs)."""
        if not self.inworld_api_key or not text.strip():
            return

        self.is_speaking = True

        try:
            if len(text) > 500:
                text = text[:500] + "..."

            # Inworld.AI API Call
            url = "https://api.inworld.ai/tts/v1/voice"
            headers = {
                "Authorization": f"Basic {self.inworld_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "text": text,
                "voiceId": INWORLD_VOICE,
                "modelId": INWORLD_MODEL,
                "voiceSettings": {
                    "speaking_rate": INWORLD_SPEAKING_RATE,  # 0.5-1.5 (schneller = höher)
                },
                "temperature": INWORLD_TEMPERATURE  # Emotionale Varianz
            }

            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()

            # Audio Content decodieren (Base64 -> Bytes)
            result = response.json()
            audio_bytes = base64.b64decode(result['audioContent'])

            # Audio abspielen (gleicher Code wie vorher)
            import io
            from pydub import AudioSegment

            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
            samples = samples / np.max(np.abs(samples))

            if audio_segment.channels == 2:
                samples = samples.reshape((-1, 2)).mean(axis=1)

            sd.play(samples, samplerate=audio_segment.frame_rate)
            sd.wait()

        except requests.exceptions.HTTPError as e:
            print(f"   ⚠️ TTS API Fehler: {e}")
            if e.response.status_code == 401:
                print(f"   ❌ Authentifizierung fehlgeschlagen - prüfe INWORLD_API_KEY in .env")
        except Exception as e:
            print(f"   ⚠️ TTS Fehler: {e}")
        finally:
            self.is_speaking = False
    
    async def process_input(self, input_type: str, content) -> str:
        """Verarbeitet Eingabe durch Timus mit Memory."""
        self.is_processing = True

        try:
            # Bei Audio: Transkribieren UND Emotion erkennen
            if input_type == "audio":
                print("   🔄 Transkribiere...")
                user_text = await asyncio.to_thread(self.transcribe, content)
                if not user_text.strip():
                    return ""

                # Emotion parallel erkennen
                if self.emotion_detector:
                    emotion_result = await asyncio.to_thread(self.detect_emotion, content)
                    self.current_emotion = emotion_result.get("emotion", "neutral")
                    self.emotion_confidence = emotion_result.get("confidence", 0.0)

                    if self.emotion_confidence > 0.6:
                        emotion_emoji = {
                            "happy": "😊",
                            "sad": "😔",
                            "angry": "😤",
                            "neutral": "😐",
                        }.get(self.current_emotion, "🎭")
                        print(f"   🎭 Emotion: {self.current_emotion} {emotion_emoji} ({self.emotion_confidence*100:.0f}%)")

                print(f"👤 Du (Voice): {user_text}")
            else:
                user_text = str(content or "")
                print(f"👤 Du (Text): {user_text}")
                # Bei Text keine Emotion erkennen
                self.current_emotion = "neutral"
                self.emotion_confidence = 0.0

            user_text = self._sanitize_user_input(user_text)
            if not user_text:
                return ""

            text_lower = user_text.lower()

            def local_response(message: str, command: str, status: str = "completed") -> str:
                self._log_local_interaction(
                    user_input=user_text,
                    assistant_response=message,
                    status=status,
                    command=command,
                )
                return message

            # Session-Kontinuitaet: expliziter Session-Reset per Kommando
            if text_lower in NEW_SESSION_COMMANDS:
                old_session = self.conversation_session_id
                self.conversation_session_id = self._new_session_id()
                message = (
                    f"♻️ Neue Session gestartet: {self.conversation_session_id} "
                    f"(vorher: {old_session})"
                )
                print(f"   {message}")
                return local_response(message, command="new_session")

            # Exit-Check (aber nicht wenn es um Aufzeichnung geht)
            if any(cmd in text_lower for cmd in EXIT_COMMANDS) and "aufzeichnung" not in text_lower and "aufnahme" not in text_lower:
                self._log_local_interaction(
                    user_input=user_text,
                    assistant_response="Session durch Exit-Kommando beendet.",
                    status="cancelled",
                    command="exit",
                )
                return "__EXIT__"

            # Memory-Befehle prüfen
            if "was weißt du über mich" in text_lower or "was erinnerst du" in text_lower:
                facts = memory_manager.persistent.get_all_facts()
                if facts:
                    fact_list = "\n".join([f"- {f.key}: {f.value}" for f in facts[:10]])
                    return local_response(
                        f"Das weiß ich über dich:\n{fact_list}",
                        command="memory_facts",
                    )
                return local_response(
                    "Ich habe noch keine Informationen über dich gespeichert.",
                    command="memory_facts",
                )

            if "vergiss" in text_lower and ("alles" in text_lower or "memory" in text_lower):
                # Gefährlich - nachfragen
                return local_response(
                    "Bist du sicher? Sage 'Ja, vergiss alles' um dein Memory zu löschen.",
                    command="memory_confirm_clear",
                )

            if "ja, vergiss alles" in text_lower:
                memory_manager.session.clear()
                # DB löschen wäre hier - aber das ist destruktiv
                return local_response(
                    "Ich habe mein Kurzzeit-Gedächtnis gelöscht. Die langfristigen Fakten bleiben erhalten.",
                    command="memory_clear_session",
                )

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
            if is_recording_start_command(user_text):
                skill_name = extract_skill_name(user_text)
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post("http://127.0.0.1:5000", json={
                        "jsonrpc": "2.0",
                        "method": "start_skill_recording",
                        "params": {"skill_name": skill_name, "description": f"Aufgezeichneter Skill: {skill_name}"},
                        "id": 1
                    })
                    result = r.json()
                    if "result" in result:
                        return local_response(
                            f"🎬 Aufzeichnung gestartet für '{skill_name}'! Führe jetzt deine Aktionen aus. Sage 'Beende Aufzeichnung' wenn fertig.",
                            command="skill_record_start",
                        )
                    return local_response(
                        f"❌ Fehler: {result.get('error', {}).get('message', 'Unbekannt')}",
                        command="skill_record_start",
                        status="error",
                    )

            # Recording Stop
            if is_recording_stop_command(user_text):
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
                        return local_response(
                            f"✅ Skill '{res.get('skill_name')}' gespeichert mit {res.get('steps_count', '?')} Schritten!",
                            command="skill_record_stop",
                        )
                    return local_response(
                        f"❌ Fehler: {result.get('error', {}).get('message', 'Unbekannt')}",
                        command="skill_record_stop",
                        status="error",
                    )

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
                        return local_response(
                            f"🎬 Aufzeichnung läuft: '{result.get('skill_name')}' - {result.get('action_count')} Aktionen",
                            command="skill_record_status",
                        )
                    return local_response("📴 Keine Aufzeichnung aktiv.", command="skill_record_status")
            # === ENDE SKILL RECORDING ===

            # === SKILL AUSFÜHRUNG ===
            def is_skill_list_command(text: str) -> bool:
                t = text.lower()
                list_words = ["liste", "zeige", "welche", "verfügbar", "gelernt", "kennst"]
                skill_words = ["skill", "fähigkeit", "können"]
                return any(l in t for l in list_words) and any(s in t for s in skill_words)

            def is_skill_run_command(text: str) -> tuple:
                """Prüft ob Skill ausgeführt werden soll. Returns (True/False, skill_name)"""
                t = text.lower()
                run_words = ["führe", "starte", "nutze", "ausführen", "run", "execute"]

                if any(w in t for w in run_words) and "skill" in t:
                    # Extrahiere Skill-Namen
                    match = re.search(r'skill\s+["\']?(\w+)["\']?', t)
                    if match:
                        return True, match.group(1)
                return False, None

            # Skill-Liste
            if is_skill_list_command(user_text):
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
                        return local_response(
                            f"📚 Meine erlernten Skills:\n{skill_list}",
                            command="skill_list",
                        )
                    return local_response("Ich habe noch keine Skills gelernt.", command="skill_list")

            # Skill ausführen
            should_run, skill_name = is_skill_run_command(user_text)
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
                        return local_response(f"✅ Skill '{skill_name}' ausgeführt!", command="skill_run")
                    return local_response(
                        f"❌ Fehler: {result.get('error', {}).get('message', 'Skill nicht gefunden')}",
                        command="skill_run",
                        status="error",
                    )
            # === ENDE SKILL AUSFÜHRUNG ===

            # Agent entscheiden
            print("   🤔 Timus denkt...")
            agent_name = quick_intent_check(user_text)
            if not agent_name:
                agent_name = await get_agent_decision(user_text)

            print(f"   📌 Agent: {agent_name.upper()}")

            # Agent ausführen (Session-kontinuierlich, deterministisches Logging im Dispatcher)
            result = await run_agent(
                agent_name,
                user_text,
                self.tools_description,
                session_id=self.conversation_session_id,
            )

            if result is None:
                result = "Ich konnte keine Antwort generieren."

            # Emotion-basierte Antwort-Anpassung
            if self.current_emotion != "neutral" and self.emotion_confidence > 0.7:
                emotion_prefix = self.get_emotion_prefix(self.current_emotion)
                if emotion_prefix and not str(result).startswith(emotion_prefix):
                    result = emotion_prefix + str(result)

            return str(result)

        except Exception as e:
            error_msg = f"Fehler: {e}"
            try:
                self._log_local_interaction(
                    user_input=self._sanitize_user_input(content if isinstance(content, str) else ""),
                    assistant_response=error_msg,
                    status="error",
                    command="exception",
                )
            except Exception:
                pass
            return error_msg
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
        print(f"🧵 Session: {self.conversation_session_id}  |  Kommando: /new fuer neue Session")
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
║   Tippe "/new" fuer eine neue Session-ID                      ║
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

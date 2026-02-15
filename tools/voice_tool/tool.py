# tools/voice_tool/tool.py
"""
Timus Voice Tool v1.0

Spracheingabe: Faster-Whisper (lokal, GPU)
Sprachausgabe: ElevenLabs (Cloud, beste Qualität)

Features:
- listen() - Nimmt Sprache auf und transkribiert
- speak(text) - Spricht Text mit ElevenLabs
- voice_chat() - Kontinuierlicher Dialog mit Timus
- set_voice(voice_id) - Wechselt ElevenLabs Stimme
"""

import logging
import asyncio
import os
import io
import tempfile
import threading
import queue
import time
from typing import Optional, Union, Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd
from elevenlabs.client import ElevenLabs
from faster_whisper import WhisperModel
from dotenv import load_dotenv

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# --- Setup ---
load_dotenv()
log = logging.getLogger("voice_tool")

# Konfiguration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")  # small, medium, large-v3
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")  # cuda oder cpu
SAMPLE_RATE = 16000
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam
DEFAULT_MODEL_ID = "eleven_multilingual_v2"

# Verfügbare ElevenLabs Stimmen
VOICES = {
    "adam": "pNInz6obpgDQGcFmaJgB",
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "domi": "AZnzlk1XvdvUeBnXmlld",
    "bella": "EXAVITQu4vr4xnSDxMaL",
    "antoni": "ErXwobaYiN019PkySvjV",
    "elli": "MF3mGyEYCl7XYWbV9V6O",
    "josh": "TxGEqnHWrfWFTfGW9XjX",
    "arnold": "VR6AewLTigWG4xSOukaG",
    "sam": "yoZ06aMxZJJ28mfd3POQ",
}


@dataclass
class VoiceConfig:
    """Konfiguration für Voice-Tool."""
    voice_id: str = DEFAULT_VOICE_ID
    model_id: str = DEFAULT_MODEL_ID
    listen_duration: float = 5.0  # Sekunden
    silence_threshold: float = 0.01
    silence_duration: float = 1.5  # Sekunden Stille = Ende
    language: str = "de"


class VoiceEngine:
    """
    Engine für Spracheingabe und -ausgabe.
    """

    def __init__(self):
        self.config = VoiceConfig()
        self.whisper_model: Optional[WhisperModel] = None
        self.elevenlabs_client: Optional[ElevenLabs] = None
        self.is_listening = False
        self.is_speaking = False
        self._audio_queue = queue.Queue()
        self._initialized = False

    def initialize(self):
        """Initialisiert Whisper und ElevenLabs."""
        if self._initialized:
            return

        log.info(f"🎤 Lade Whisper Modell '{WHISPER_MODEL}' auf {WHISPER_DEVICE}...")
        try:
            self.whisper_model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type="float16" if WHISPER_DEVICE == "cuda" else "int8"
            )
            log.info("✅ Whisper Modell geladen")
        except Exception as e:
            log.error(f"❌ Whisper Fehler: {e}")
            # Fallback auf CPU
            log.info("Versuche CPU-Fallback...")
            self.whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

        if ELEVENLABS_API_KEY:
            self.elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            log.info("✅ ElevenLabs Client initialisiert")
        else:
            log.warning("⚠️ ELEVENLABS_API_KEY nicht gesetzt - Sprachausgabe deaktiviert")

        self._initialized = True

    def _record_audio(self, duration: float) -> np.ndarray:
        """Nimmt Audio für eine bestimmte Dauer auf."""
        log.debug(f"Aufnahme für {duration}s...")
        audio = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32'
        )
        sd.wait()
        return audio.flatten()

    def _record_until_silence(self, max_duration: float = 30.0) -> np.ndarray:
        """
        Nimmt Audio auf bis Stille erkannt wird.
        Intelligenter als feste Dauer.
        """
        log.debug("Aufnahme bis Stille...")

        chunk_duration = 0.5  # 500ms Chunks
        chunk_samples = int(chunk_duration * SAMPLE_RATE)

        audio_chunks = []
        silence_start = None
        total_duration = 0

        self.is_listening = True

        while total_duration < max_duration and self.is_listening:
            chunk = sd.rec(chunk_samples, samplerate=SAMPLE_RATE, channels=1, dtype='float32')
            sd.wait()
            chunk = chunk.flatten()

            # Lautstärke prüfen
            volume = np.abs(chunk).mean()

            if volume < self.config.silence_threshold:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > self.config.silence_duration:
                    log.debug("Stille erkannt - Aufnahme beendet")
                    break
            else:
                silence_start = None
                audio_chunks.append(chunk)

            total_duration += chunk_duration

        self.is_listening = False

        if not audio_chunks:
            return np.array([], dtype='float32')

        return np.concatenate(audio_chunks)

    def listen(self, duration: Optional[float] = None, wait_for_silence: bool = True) -> str:
        """
        Hört zu und transkribiert Sprache zu Text.

        Args:
            duration: Feste Aufnahmedauer (None = bis Stille)
            wait_for_silence: Wenn True, wartet auf Stille statt feste Dauer

        Returns:
            Transkribierter Text
        """
        if not self.whisper_model:
            self.initialize()

        log.info("🎤 Höre zu...")

        if duration:
            audio = self._record_audio(duration)
        elif wait_for_silence:
            audio = self._record_until_silence()
        else:
            audio = self._record_audio(self.config.listen_duration)

        if len(audio) == 0:
            log.warning("Keine Audio-Daten aufgenommen")
            return ""

        log.debug("Transkribiere...")
        segments, info = self.whisper_model.transcribe(
            audio,
            language=self.config.language,
            vad_filter=True  # Filtert Stille
        )

        text = " ".join([s.text.strip() for s in segments])
        log.info(f"📝 Erkannt: {text}")

        return text

    def speak(self, text: str, voice: Optional[str] = None) -> bool:
        """
        Spricht Text mit ElevenLabs.

        Args:
            text: Zu sprechender Text
            voice: Stimmen-Name oder ID (optional)

        Returns:
            True wenn erfolgreich
        """
        if not self.elevenlabs_client:
            log.error("ElevenLabs nicht initialisiert")
            return False

        if not text.strip():
            return True

        # Voice ID bestimmen
        voice_id = self.config.voice_id
        if voice:
            voice_id = VOICES.get(voice.lower(), voice)

        log.info(f"🔊 Spreche: {text[:50]}...")
        self.is_speaking = True

        try:
            # Audio generieren
            audio = self.elevenlabs_client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id=self.config.model_id
            )

            # In temporäre Datei speichern und abspielen
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                for chunk in audio:
                    f.write(chunk)
                temp_path = f.name

            # Abspielen mit ffplay (leise, ohne Fenster)
            os.system(f"ffplay -nodisp -autoexit -loglevel quiet '{temp_path}' 2>/dev/null")

            # Aufräumen
            os.unlink(temp_path)

            self.is_speaking = False
            return True

        except Exception as e:
            log.error(f"❌ Sprachausgabe Fehler: {e}")
            self.is_speaking = False
            return False

    async def speak_async(self, text: str, voice: Optional[str] = None) -> bool:
        """Asynchrone Version von speak()."""
        return await asyncio.to_thread(self.speak, text, voice)

    async def listen_async(self, duration: Optional[float] = None) -> str:
        """Asynchrone Version von listen()."""
        return await asyncio.to_thread(self.listen, duration)

    def set_voice(self, voice_name: str) -> bool:
        """
        Wechselt die ElevenLabs Stimme.

        Args:
            voice_name: Name (adam, rachel, etc.) oder Voice ID
        """
        if voice_name.lower() in VOICES:
            self.config.voice_id = VOICES[voice_name.lower()]
            log.info(f"✅ Stimme gewechselt zu: {voice_name}")
            return True
        elif len(voice_name) > 10:  # Wahrscheinlich eine Voice ID
            self.config.voice_id = voice_name
            return True
        else:
            log.warning(f"Unbekannte Stimme: {voice_name}")
            return False

    def set_language(self, language: str):
        """Setzt die Sprache für Whisper (de, en, etc.)."""
        self.config.language = language
        log.info(f"✅ Sprache: {language}")

    def stop_listening(self):
        """Stoppt eine laufende Aufnahme."""
        self.is_listening = False

    def get_available_voices(self) -> dict:
        """Gibt verfügbare Stimmen zurück."""
        return VOICES.copy()


# Globale Engine-Instanz
voice_engine = VoiceEngine()


# ==============================================================================
# RPC METHODEN
# ==============================================================================

@tool(
    name="voice_listen",
    description="Hört zu und transkribiert Sprache zu Text. Nimmt bis zur Stille auf oder für eine feste Dauer.",
    parameters=[
        P("duration", "number", "Optionale feste Aufnahmedauer in Sekunden. Wenn nicht angegeben, wird bis zur Stille aufgenommen.", required=False, default=None),
    ],
    capabilities=["voice", "speech"],
    category=C.VOICE
)
async def voice_listen(duration: Optional[float] = None) -> dict:
    """
    Hört zu und transkribiert Sprache zu Text.

    Args:
        duration: Optionale feste Aufnahmedauer in Sekunden.
                  Wenn nicht angegeben, wird bis zur Stille aufgenommen.

    Returns:
        Erkannter Text
    """
    try:
        if not voice_engine._initialized:
            await asyncio.to_thread(voice_engine.initialize)

        text = await voice_engine.listen_async(duration)

        return {
            "text": text,
            "success": bool(text),
            "message": f"Erkannt: {text}" if text else "Keine Sprache erkannt"
        }
    except Exception as e:
        log.error(f"Listen Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="voice_speak",
    description="Spricht Text mit ElevenLabs Stimme.",
    parameters=[
        P("text", "string", "Zu sprechender Text", required=True),
        P("voice", "string", "Optional - Stimmen-Name (adam, rachel, domi, bella, etc.)", required=False, default=None),
    ],
    capabilities=["voice", "speech"],
    category=C.VOICE
)
async def voice_speak(text: str, voice: Optional[str] = None) -> dict:
    """
    Spricht Text mit ElevenLabs.

    Args:
        text: Zu sprechender Text
        voice: Optional - Stimmen-Name (adam, rachel, domi, bella, etc.)

    Returns:
        Erfolgs-Status
    """
    try:
        if not voice_engine._initialized:
            await asyncio.to_thread(voice_engine.initialize)

        success = await voice_engine.speak_async(text, voice)

        return {
            "success": success,
            "text": text,
            "voice": voice or "default",
            "message": "Gesprochen" if success else "Fehler bei Sprachausgabe"
        }
    except Exception as e:
        log.error(f"Speak Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="voice_set_voice",
    description="Wechselt die Stimme für Sprachausgabe.",
    parameters=[
        P("voice_name", "string", "Name der Stimme (adam, rachel, domi, bella, antoni, elli, josh, arnold, sam)", required=True),
    ],
    capabilities=["voice", "speech"],
    category=C.VOICE
)
async def voice_set_voice(voice_name: str) -> dict:
    """
    Wechselt die Stimme für Sprachausgabe.

    Args:
        voice_name: Name der Stimme (adam, rachel, domi, bella, antoni, elli, josh, arnold, sam)

    Returns:
        Erfolgs-Status
    """
    success = voice_engine.set_voice(voice_name)

    if success:
        return {
            "success": True,
            "voice": voice_name,
            "message": f"Stimme gewechselt zu: {voice_name}"
        }
    else:
        raise Exception(f"Unbekannte Stimme: {voice_name}. Verfügbar: {list(VOICES.keys())}")


@tool(
    name="voice_list_voices",
    description="Listet alle verfügbaren Stimmen auf.",
    parameters=[],
    capabilities=["voice", "speech"],
    category=C.VOICE
)
async def voice_list_voices() -> dict:
    """
    Listet alle verfügbaren Stimmen auf.

    Returns:
        Dictionary mit Stimmen-Namen und IDs
    """
    return {
        "voices": voice_engine.get_available_voices(),
        "current": voice_engine.config.voice_id
    }


@tool(
    name="voice_set_language",
    description="Setzt die Sprache für Spracherkennung.",
    parameters=[
        P("language", "string", "Sprachcode (de, en, fr, es, etc.)", required=True),
    ],
    capabilities=["voice", "speech"],
    category=C.VOICE
)
async def voice_set_language(language: str) -> dict:
    """
    Setzt die Sprache für Spracherkennung.

    Args:
        language: Sprachcode (de, en, fr, es, etc.)

    Returns:
        Erfolgs-Status
    """
    voice_engine.set_language(language)
    return {
        "success": True,
        "language": language
    }


@tool(
    name="voice_chat_turn",
    description="Führt einen Voice-Chat-Turn durch: Hört zu und gibt den erkannten Text zurück.",
    parameters=[
        P("timeout", "number", "Maximale Aufnahmedauer in Sekunden", required=False, default=10.0),
    ],
    capabilities=["voice", "speech"],
    category=C.VOICE
)
async def voice_chat_turn(timeout: float = 10.0) -> dict:
    """
    Führt einen Voice-Chat-Turn durch:
    1. Hört zu
    2. Gibt Text zurück (für Agent-Verarbeitung)

    Der Agent kann dann antworten und voice_speak() aufrufen.

    Args:
        timeout: Maximale Aufnahmedauer

    Returns:
        Erkannter Text vom Benutzer
    """
    try:
        if not voice_engine._initialized:
            await asyncio.to_thread(voice_engine.initialize)

        # Kurzer Hinweis-Sound wäre hier gut
        log.info("🎤 Warte auf Spracheingabe...")

        text = await voice_engine.listen_async()

        if not text.strip():
            return {
                "text": "",
                "success": False,
                "message": "Keine Sprache erkannt. Bitte erneut sprechen."
            }

        return {
            "text": text,
            "success": True,
            "message": "Bereit für Antwort"
        }

    except Exception as e:
        log.error(f"Voice Chat Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="voice_initialize",
    description="Initialisiert das Voice-System (lädt Modelle). Kann beim Start aufgerufen werden um Latenz später zu vermeiden.",
    parameters=[],
    capabilities=["voice", "speech"],
    category=C.VOICE
)
async def voice_initialize() -> dict:
    """
    Initialisiert das Voice-System (lädt Modelle).
    Kann beim Start aufgerufen werden um Latenz später zu vermeiden.

    Returns:
        Status der Initialisierung
    """
    try:
        await asyncio.to_thread(voice_engine.initialize)

        return {
            "initialized": True,
            "whisper_model": WHISPER_MODEL,
            "whisper_device": WHISPER_DEVICE,
            "elevenlabs": bool(voice_engine.elevenlabs_client),
            "message": "Voice-System bereit"
        }
    except Exception as e:
        log.error(f"Initialisierung Fehler: {e}", exc_info=True)
        raise Exception(str(e))

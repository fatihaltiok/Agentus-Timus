# tools/voice_tool/tool.py
"""
Timus Voice Tool v2.0

Spracheingabe: Faster-Whisper (lokal, GPU)
Sprachausgabe: Inworld.AI TTS (günstiger als ElevenLabs)

Features:
- listen() - Nimmt Sprache auf und transkribiert
- speak(text) - Spricht Text mit Inworld.AI
- voice_chat() - Kontinuierlicher Dialog mit Timus
- set_voice(voice_id) - Wechselt Inworld Stimme
"""

import logging
import asyncio
import os
import io
import base64
import queue
import time
import requests
from typing import Optional
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from dotenv import load_dotenv

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# --- Setup ---
load_dotenv()
log = logging.getLogger("voice_tool")

# Konfiguration
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")  # small, medium, large-v3
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")  # cuda oder cpu
SAMPLE_RATE = 16000

# Inworld.AI TTS
INWORLD_API_KEY     = os.getenv("INWORLD_API_KEY")
INWORLD_VOICE       = os.getenv("INWORLD_VOICE", "Lennart")
INWORLD_MODEL       = os.getenv("INWORLD_MODEL", "inworld-tts-1.5-max")
INWORLD_SPEAKING_RATE = float(os.getenv("INWORLD_SPEAKING_RATE", "1.3"))
INWORLD_TEMPERATURE   = float(os.getenv("INWORLD_TEMPERATURE", "1.5"))
INWORLD_TTS_URL     = "https://api.inworld.ai/tts/v1/voice"


@dataclass
class VoiceConfig:
    """Konfiguration für Voice-Tool."""
    inworld_voice: str = INWORLD_VOICE
    listen_duration: float = 5.0  # Sekunden
    silence_threshold: float = 0.003  # niedrig: bei 44.1 kHz float32 ist Sprache oft 0.01-0.1
    silence_duration: float = 1.8   # Sekunden Stille nach Sprache = Ende
    language: str = "de"


class VoiceEngine:
    """
    Engine für Spracheingabe (Faster-Whisper) und -ausgabe (Inworld.AI TTS).
    """

    def __init__(self):
        self.config = VoiceConfig()
        self.whisper_model: Optional[WhisperModel] = None
        self.is_listening = False
        self.is_speaking = False
        self._audio_queue = queue.Queue()
        self._initialized = False

    def initialize(self):
        """Initialisiert Whisper und prüft Inworld.AI Konfiguration."""
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
            log.info("Versuche CPU-Fallback...")
            self.whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

        if INWORLD_API_KEY:
            log.info(f"✅ Inworld.AI TTS bereit (Voice: {INWORLD_VOICE}, Model: {INWORLD_MODEL})")
        else:
            log.warning("⚠️ INWORLD_API_KEY nicht gesetzt - Sprachausgabe deaktiviert")

        self._initialized = True

    def _device_rate(self) -> int:
        """Gibt die native Samplerate des Standard-Eingabegeräts zurück."""
        try:
            info = sd.query_devices(kind='input')
            rate = int(info['default_samplerate'])
            log.debug(f"Gerät native Samplerate: {rate} Hz")
            return rate
        except Exception:
            return SAMPLE_RATE

    def _resample(self, audio: np.ndarray, from_rate: int) -> np.ndarray:
        """Resampled Audio von from_rate auf SAMPLE_RATE (16 kHz) via scipy (hohe Qualität)."""
        if from_rate == SAMPLE_RATE or len(audio) == 0:
            return audio
        from scipy.signal import resample_poly
        import math
        g = math.gcd(SAMPLE_RATE, from_rate)
        up, down = SAMPLE_RATE // g, from_rate // g
        resampled = resample_poly(audio, up, down)
        return resampled.astype('float32')

    def _record_audio(self, duration: float) -> np.ndarray:
        """Nimmt Audio für eine bestimmte Dauer auf (native Rate, dann resampeln)."""
        rate = self._device_rate()
        log.debug(f"Aufnahme für {duration}s bei {rate} Hz...")
        audio = sd.rec(int(duration * rate), samplerate=rate, channels=1, dtype='float32')
        sd.wait()
        return self._resample(audio.flatten(), rate)

    def _record_until_silence(self, max_duration: float = 30.0) -> np.ndarray:
        """Nimmt kontinuierlich Audio auf bis Stille erkannt wird (native Rate → 16 kHz)."""
        log.debug("Aufnahme bis Stille...")
        rate = self._device_rate()

        chunk_duration = 0.4  # 400ms Chunks
        chunk_samples = int(chunk_duration * rate)

        all_chunks = []       # ALLE Chunks (Sprache + Stille) für Whisper
        silence_start = None
        speech_detected = False
        total_duration = 0

        self.is_listening = True

        while total_duration < max_duration and self.is_listening:
            chunk = sd.rec(chunk_samples, samplerate=rate, channels=1, dtype='float32')
            sd.wait()
            chunk = chunk.flatten()

            volume = np.abs(chunk).mean()
            all_chunks.append(chunk)  # immer speichern

            if volume >= self.config.silence_threshold:
                speech_detected = True
                silence_start = None
            else:
                # Stille zählen — aber erst nach erster Sprache stoppen
                if speech_detected:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > self.config.silence_duration:
                        log.debug(f"Stille erkannt nach {total_duration:.1f}s — Aufnahme beendet")
                        break

            total_duration += chunk_duration

        self.is_listening = False

        if not all_chunks:
            return np.array([], dtype='float32')

        audio = np.concatenate(all_chunks)
        log.info(f"🎤 Aufnahme: {total_duration:.1f}s, Peak: {np.abs(audio).max():.4f}, RMS: {np.abs(audio).mean():.4f}")

        # Auf 16 kHz resampeln für Whisper
        return self._resample(audio, rate)

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

        log.info(f"🔍 Whisper: {len(audio)} Samples ({len(audio)/SAMPLE_RATE:.1f}s), Peak={np.abs(audio).max():.4f}")
        segments, info = self.whisper_model.transcribe(
            audio,
            language=self.config.language,
            vad_filter=False,   # Kein VAD — wir übergeben bereits aufbereitetes Audio
            beam_size=5,
        )

        text = " ".join([s.text.strip() for s in segments]).strip()
        log.info(f"📝 Erkannt: '{text}'")

        return text

    def speak(self, text: str, voice: Optional[str] = None) -> bool:
        """
        Spricht Text mit Inworld.AI TTS.

        Args:
            text: Zu sprechender Text
            voice: Inworld Stimmen-Name (optional, überschreibt .env INWORLD_VOICE)

        Returns:
            True wenn erfolgreich
        """
        if not INWORLD_API_KEY:
            log.error("INWORLD_API_KEY nicht gesetzt")
            return False

        if not text.strip():
            return True

        self.is_speaking = True
        voice_name = voice or self.config.inworld_voice

        # Länge begrenzen (API-Limit)
        if len(text) > 500:
            text = text[:500] + "..."

        log.info(f"🔊 Inworld.AI spricht ({voice_name}): {text[:60]}…")

        try:
            response = requests.post(
                INWORLD_TTS_URL,
                json={
                    "text": text,
                    "voiceId": voice_name,
                    "modelId": INWORLD_MODEL,
                    "voiceSettings": {"speaking_rate": INWORLD_SPEAKING_RATE},
                    "temperature": INWORLD_TEMPERATURE,
                },
                headers={
                    "Authorization": f"Basic {INWORLD_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()

            audio_bytes = base64.b64decode(response.json()["audioContent"])

            from pydub import AudioSegment
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
            samples = samples / (np.max(np.abs(samples)) or 1.0)
            if audio_segment.channels == 2:
                samples = samples.reshape((-1, 2)).mean(axis=1)

            sd.play(samples, samplerate=audio_segment.frame_rate)
            sd.wait()

            self.is_speaking = False
            return True

        except requests.exceptions.HTTPError as e:
            log.error(f"❌ Inworld.AI HTTP-Fehler: {e}")
            if e.response is not None and e.response.status_code == 401:
                log.error("Authentifizierung fehlgeschlagen — prüfe INWORLD_API_KEY in .env")
        except Exception as e:
            log.error(f"❌ Sprachausgabe Fehler: {e}")
        finally:
            self.is_speaking = False

        return False

    async def speak_async(self, text: str, voice: Optional[str] = None) -> bool:
        """Asynchrone Version von speak()."""
        return await asyncio.to_thread(self.speak, text, voice)

    async def listen_async(self, duration: Optional[float] = None) -> str:
        """Asynchrone Version von listen()."""
        return await asyncio.to_thread(self.listen, duration)

    def set_voice(self, voice_name: str) -> bool:
        """Wechselt die Inworld.AI Stimme."""
        self.config.inworld_voice = voice_name
        log.info(f"✅ Inworld-Stimme gesetzt: {voice_name}")
        return True

    def set_language(self, language: str):
        """Setzt die Sprache für Whisper (de, en, etc.)."""
        self.config.language = language
        log.info(f"✅ Sprache: {language}")

    def stop_listening(self):
        """Stoppt eine laufende Aufnahme."""
        self.is_listening = False

    def get_available_voices(self) -> dict:
        """Gibt bekannte Inworld.AI Stimmen zurück (nicht abschließend)."""
        return {
            "Lennart": "de-DE männlich, natürlich",
            "Ashley": "en-US weiblich, freundlich",
            "Derek": "en-US männlich, professionell",
        }


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
    description="Spricht Text mit Inworld.AI TTS.",
    parameters=[
        P("text", "string", "Zu sprechender Text", required=True),
        P("voice", "string", "Optional - Inworld Stimmen-Name (z.B. Lennart, Ashley, Derek)", required=False, default=None),
    ],
    capabilities=["voice", "speech"],
    category=C.VOICE
)
async def voice_speak(text: str, voice: Optional[str] = None) -> dict:
    """
    Spricht Text mit Inworld.AI TTS.

    Args:
        text: Zu sprechender Text
        voice: Optional - Inworld Stimmen-Name

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
            "voice": voice or voice_engine.config.inworld_voice,
            "message": "Gesprochen" if success else "Fehler bei Sprachausgabe"
        }
    except Exception as e:
        log.error(f"Speak Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="voice_set_voice",
    description="Wechselt die Inworld.AI Stimme für Sprachausgabe.",
    parameters=[
        P("voice_name", "string", "Inworld Stimmen-Name (z.B. Lennart, Ashley, Derek)", required=True),
    ],
    capabilities=["voice", "speech"],
    category=C.VOICE
)
async def voice_set_voice(voice_name: str) -> dict:
    """Wechselt die Inworld.AI Stimme."""
    voice_engine.set_voice(voice_name)
    return {"success": True, "voice": voice_name, "message": f"Stimme gesetzt: {voice_name}"}


@tool(
    name="voice_list_voices",
    description="Listet alle verfügbaren Stimmen auf.",
    parameters=[],
    capabilities=["voice", "speech"],
    category=C.VOICE
)
async def voice_list_voices() -> dict:
    """Listet bekannte Inworld.AI Stimmen auf."""
    return {
        "voices": voice_engine.get_available_voices(),
        "current": voice_engine.config.inworld_voice,
        "provider": "Inworld.AI",
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
            "inworld_tts": bool(INWORLD_API_KEY),
            "inworld_voice": voice_engine.config.inworld_voice,
            "message": "Voice-System bereit"
        }
    except Exception as e:
        log.error(f"Initialisierung Fehler: {e}", exc_info=True)
        raise Exception(str(e))

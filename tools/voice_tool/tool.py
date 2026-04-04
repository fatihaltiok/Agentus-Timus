from __future__ import annotations

# tools/voice_tool/tool.py
"""
Timus Voice Tool v2.0

Spracheingabe: Faster-Whisper (lokal, GPU)
Sprachausgabe: Inworld.AI TTS
"""

import asyncio
import base64
import io
import logging
import os
import queue
import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import requests
from dotenv import load_dotenv

from tools.tool_registry_v2 import ToolCategory as C
from tools.tool_registry_v2 import ToolParameter as P
from tools.tool_registry_v2 import tool
from utils.voice_text import normalize_tts_text

load_dotenv(override=True)
log = logging.getLogger("voice_tool")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
SAMPLE_RATE = 16000
VOICE_TRANSCRIBE_BACKEND = os.getenv("VOICE_TRANSCRIBE_BACKEND", "openai_api")
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

INWORLD_API_KEY = os.getenv("INWORLD_API_KEY")
INWORLD_VOICE = os.getenv("INWORLD_VOICE", "Lennart")
INWORLD_MODEL = os.getenv("INWORLD_MODEL", "inworld-tts-1.5-max")
INWORLD_SPEAKING_RATE = float(os.getenv("INWORLD_SPEAKING_RATE", "1.3"))
INWORLD_TEMPERATURE = float(os.getenv("INWORLD_TEMPERATURE", "1.5"))
INWORLD_TTS_URL = "https://api.inworld.ai/tts/v1/voice"


@dataclass
class VoiceConfig:
    inworld_voice: str = INWORLD_VOICE
    listen_duration: float = 5.0
    silence_threshold: float = 0.003
    silence_duration: float = 1.8
    language: str = "de"


class VoiceEngine:
    def __init__(self) -> None:
        self.config = VoiceConfig()
        self.whisper_model: Optional[Any] = None
        self.is_listening = False
        self.is_speaking = False
        self._audio_queue = queue.Queue()
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return

        self.ensure_whisper_model()

        if INWORLD_API_KEY:
            log.info("✅ Inworld.AI TTS bereit (Voice: %s, Model: %s)", INWORLD_VOICE, INWORLD_MODEL)
        else:
            log.warning("⚠️ INWORLD_API_KEY nicht gesetzt - Sprachausgabe deaktiviert")

        self._initialized = True

    def ensure_whisper_model(self) -> None:
        if self.whisper_model is not None:
            return

        from faster_whisper import WhisperModel

        log.info("🎤 Lade Whisper Modell '%s' auf %s...", WHISPER_MODEL, WHISPER_DEVICE)
        try:
            self.whisper_model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type="float16" if WHISPER_DEVICE == "cuda" else "int8",
            )
            log.info("✅ Whisper Modell geladen")
        except Exception as exc:
            log.error("❌ Whisper Fehler: %s", exc)
            log.info("Versuche CPU-Fallback...")
            self.whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    def _device_rate(self) -> int:
        try:
            import sounddevice as sd

            info = sd.query_devices(kind="input")
            return int(info["default_samplerate"])
        except Exception:
            return SAMPLE_RATE

    def _resample(self, audio: Any, from_rate: int) -> Any:
        if from_rate == SAMPLE_RATE or len(audio) == 0:
            return audio

        import math
        from scipy.signal import resample_poly

        gcd = math.gcd(SAMPLE_RATE, from_rate)
        up, down = SAMPLE_RATE // gcd, from_rate // gcd
        return resample_poly(audio, up, down).astype("float32")

    def _record_audio(self, duration: float) -> Any:
        import sounddevice as sd

        rate = self._device_rate()
        audio = sd.rec(int(duration * rate), samplerate=rate, channels=1, dtype="float32")
        sd.wait()
        return self._resample(audio.flatten(), rate)

    def _record_until_silence(self, max_duration: float = 30.0) -> Any:
        import sounddevice as sd

        rate = self._device_rate()
        chunk_duration = 0.4
        chunk_samples = int(chunk_duration * rate)

        all_chunks = []
        silence_start = None
        speech_detected = False
        total_duration = 0.0

        self.is_listening = True

        while total_duration < max_duration and self.is_listening:
            chunk = sd.rec(chunk_samples, samplerate=rate, channels=1, dtype="float32")
            sd.wait()
            chunk = chunk.flatten()

            volume = np.abs(chunk).mean()
            all_chunks.append(chunk)

            if volume >= self.config.silence_threshold:
                speech_detected = True
                silence_start = None
            elif speech_detected:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > self.config.silence_duration:
                    break

            total_duration += chunk_duration

        self.is_listening = False

        if not all_chunks:
            return np.array([], dtype="float32")

        return self._resample(np.concatenate(all_chunks), rate)

    def listen(self, duration: Optional[float] = None, wait_for_silence: bool = True) -> str:
        self.ensure_whisper_model()

        if duration:
            audio = self._record_audio(duration)
        elif wait_for_silence:
            audio = self._record_until_silence()
        else:
            audio = self._record_audio(self.config.listen_duration)

        if len(audio) == 0:
            log.warning("Keine Audio-Daten aufgenommen")
            return ""

        segments, _ = self.whisper_model.transcribe(
            audio,
            language=self.config.language,
            vad_filter=False,
            beam_size=5,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        log.info("📝 Erkannt: '%s'", text)
        return text

    def _transcribe_audio_bytes_via_openai(
        self,
        audio_bytes: bytes,
        audio_format: Optional[str] = None,
    ) -> Optional[str]:
        if not OPENAI_API_KEY:
            return None

        try:
            from openai import OpenAI

            suffix = (audio_format or "webm").strip(".")
            file_like = io.BytesIO(audio_bytes)
            file_like.name = f"voice-upload.{suffix}"

            client = OpenAI(api_key=OPENAI_API_KEY)
            response = client.audio.transcriptions.create(
                model=OPENAI_TRANSCRIBE_MODEL,
                file=file_like,
                language=self.config.language,
            )
            return (getattr(response, "text", "") or "").strip()
        except Exception as exc:
            log.error("❌ OpenAI-Transkriptionsfehler: %s", exc)
            return None

    def transcribe_audio_bytes(self, audio_bytes: bytes, audio_format: Optional[str] = None) -> str:
        if not audio_bytes:
            return ""

        if VOICE_TRANSCRIBE_BACKEND == "openai_api" and OPENAI_API_KEY:
            text = self._transcribe_audio_bytes_via_openai(audio_bytes, audio_format)
            if text is not None:
                return text

        self.ensure_whisper_model()

        from pydub import AudioSegment

        source = io.BytesIO(audio_bytes)
        audio = AudioSegment.from_file(source, format=audio_format or None)
        audio = audio.set_channels(1).set_frame_rate(16000)
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0

        segments, _ = self.whisper_model.transcribe(
            samples,
            language=self.config.language,
            vad_filter=True,
            beam_size=5,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        log.info("📝 Browser-Audio erkannt: '%s'", text)
        return text

    def synthesize_mp3(self, text: str, voice: Optional[str] = None) -> Optional[bytes]:
        if not INWORLD_API_KEY:
            log.error("INWORLD_API_KEY nicht gesetzt")
            return None

        text = normalize_tts_text(text)
        if not text:
            return b""

        voice_name = voice or self.config.inworld_voice

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
            return base64.b64decode(response.json()["audioContent"])
        except requests.exceptions.HTTPError as exc:
            log.error("❌ Inworld.AI HTTP-Fehler: %s", exc)
        except Exception as exc:
            log.error("❌ TTS-Synthese Fehler: %s", exc)
        return None

    def speak(self, text: str, voice: Optional[str] = None) -> bool:
        if not INWORLD_API_KEY:
            log.error("INWORLD_API_KEY nicht gesetzt")
            return False

        if not text.strip():
            return True

        self.is_speaking = True

        try:
            audio_bytes = self.synthesize_mp3(text, voice or self.config.inworld_voice)
            if audio_bytes is None:
                return False
            if audio_bytes == b"":
                return True

            from pydub import AudioSegment
            import sounddevice as sd

            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
            samples = samples / (np.max(np.abs(samples)) or 1.0)
            if audio_segment.channels == 2:
                samples = samples.reshape((-1, 2)).mean(axis=1)

            sd.play(samples, samplerate=audio_segment.frame_rate)
            sd.wait()
            return True
        except Exception as exc:
            log.error("❌ Sprachausgabe Fehler: %s", exc)
            return False
        finally:
            self.is_speaking = False

    async def speak_async(self, text: str, voice: Optional[str] = None) -> bool:
        return await asyncio.to_thread(self.speak, text, voice)

    async def listen_async(self, duration: Optional[float] = None) -> str:
        return await asyncio.to_thread(self.listen, duration)

    async def transcribe_audio_bytes_async(
        self,
        audio_bytes: bytes,
        audio_format: Optional[str] = None,
    ) -> str:
        return await asyncio.to_thread(self.transcribe_audio_bytes, audio_bytes, audio_format)

    def set_voice(self, voice_name: str) -> bool:
        self.config.inworld_voice = voice_name
        return True

    def set_language(self, language: str) -> None:
        self.config.language = language

    def stop_listening(self) -> None:
        self.is_listening = False

    def get_available_voices(self) -> dict:
        return {
            "Lennart": "de-DE männlich, natürlich",
            "Ashley": "en-US weiblich, freundlich",
            "Derek": "en-US männlich, professionell",
        }


voice_engine = VoiceEngine()


@tool(
    name="voice_listen",
    description="Hört zu und transkribiert Sprache zu Text.",
    parameters=[
        P(
            "duration",
            "number",
            "Optionale feste Aufnahmedauer in Sekunden.",
            required=False,
            default=None,
        ),
    ],
    capabilities=["voice", "speech"],
    category=C.VOICE,
)
async def voice_listen(duration: Optional[float] = None) -> dict:
    if not voice_engine._initialized:
        await asyncio.to_thread(voice_engine.initialize)

    text = await voice_engine.listen_async(duration)
    return {
        "text": text,
        "success": bool(text),
        "message": f"Erkannt: {text}" if text else "Keine Sprache erkannt",
    }


@tool(
    name="voice_speak",
    description="Spricht Text mit Inworld.AI TTS.",
    parameters=[
        P("text", "string", "Zu sprechender Text", required=True),
        P("voice", "string", "Optionaler Inworld-Stimmenname", required=False, default=None),
    ],
    capabilities=["voice", "speech"],
    category=C.VOICE,
)
async def voice_speak(text: str, voice: Optional[str] = None) -> dict:
    if not voice_engine._initialized:
        await asyncio.to_thread(voice_engine.initialize)

    success = await voice_engine.speak_async(text, voice)
    return {
        "success": success,
        "text": text,
        "voice": voice or voice_engine.config.inworld_voice,
        "message": "Gesprochen" if success else "Fehler bei Sprachausgabe",
    }


@tool(
    name="voice_set_voice",
    description="Wechselt die Inworld.AI Stimme.",
    parameters=[P("voice_name", "string", "Inworld Stimmen-Name", required=True)],
    capabilities=["voice", "speech"],
    category=C.VOICE,
)
async def voice_set_voice(voice_name: str) -> dict:
    voice_engine.set_voice(voice_name)
    return {"success": True, "voice": voice_name, "message": f"Stimme gesetzt: {voice_name}"}


@tool(
    name="voice_list_voices",
    description="Listet alle verfügbaren Stimmen auf.",
    parameters=[],
    capabilities=["voice", "speech"],
    category=C.VOICE,
)
async def voice_list_voices() -> dict:
    return {
        "voices": voice_engine.get_available_voices(),
        "current": voice_engine.config.inworld_voice,
        "provider": "Inworld.AI",
    }


@tool(
    name="voice_set_language",
    description="Setzt die Sprache für Spracherkennung.",
    parameters=[P("language", "string", "Sprachcode", required=True)],
    capabilities=["voice", "speech"],
    category=C.VOICE,
)
async def voice_set_language(language: str) -> dict:
    voice_engine.set_language(language)
    return {"success": True, "language": language}


@tool(
    name="voice_chat_turn",
    description="Führt einen Voice-Chat-Turn durch.",
    parameters=[P("timeout", "number", "Maximale Aufnahmedauer in Sekunden", required=False, default=10.0)],
    capabilities=["voice", "speech"],
    category=C.VOICE,
)
async def voice_chat_turn(timeout: float = 10.0) -> dict:
    if not voice_engine._initialized:
        await asyncio.to_thread(voice_engine.initialize)

    text = await voice_engine.listen_async(timeout)
    if not text.strip():
        return {
            "text": "",
            "success": False,
            "message": "Keine Sprache erkannt. Bitte erneut sprechen.",
        }

    return {"text": text, "success": True, "message": "Bereit für Antwort"}


@tool(
    name="voice_initialize",
    description="Initialisiert das Voice-System.",
    parameters=[],
    capabilities=["voice", "speech"],
    category=C.VOICE,
)
async def voice_initialize() -> dict:
    await asyncio.to_thread(voice_engine.initialize)
    return {
        "initialized": True,
        "whisper_model": WHISPER_MODEL,
        "whisper_device": WHISPER_DEVICE,
        "inworld_tts": bool(INWORLD_API_KEY),
        "inworld_voice": voice_engine.config.inworld_voice,
        "message": "Voice-System bereit",
    }

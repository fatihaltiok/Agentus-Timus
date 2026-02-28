# Tagesbericht — 2026-02-28
## Timus Canvas: Voice-Integration & Bugfixes

---

## Zusammenfassung

Heute wurde die vollständige Voice-Integration des Timus Canvas abgeschlossen. Das browserbasierte Web Speech API wurde durch das native Timus Voice System (Faster-Whisper STT + Inworld.AI TTS) ersetzt. Dabei wurden mehrere Bugs identifiziert und behoben, die ein zuverlässiges Funktionieren des Mikrofons verhindert haben.

---

## Durchgeführte Arbeiten

### 1. Voice REST Endpoints — `server/mcp_server.py`

Vier neue Endpoints wurden hinzugefügt, die das native Voice System über HTTP erreichbar machen:

| Endpoint | Methode | Funktion |
|---|---|---|
| `/voice/status` | GET | Gibt `{initialized, listening, speaking}` zurück |
| `/voice/listen` | POST | Startet Faster-Whisper STT im Hintergrund-Task, Ergebnis per SSE |
| `/voice/stop` | POST | Bricht laufende Aufnahme ab |
| `/voice/speak` | POST | Inworld.AI TTS, SSE `voice_speaking_start/end` |

**Wichtig:** Alle Endpoints geben sofort zurück (`asyncio.create_task`), kein Blocking.

---

### 2. Canvas UI Mic IIFE — `server/canvas_ui.py`

Das gesamte Mikrofon-Modul wurde neu geschrieben:

**Entfernt:**
- Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`)

**Neu:**
- HTTP-Calls zu `/voice/listen` und `/voice/stop`
- `window.onVoiceSSE` Callback für SSE-Events
- `window.voiceActive` Flag für kontinuierlichen Sprach-Modus
- Auto-Submit nach `voice_transcript` SSE
- Auto-Speak nach `chat_reply` wenn Sprach-Modus aktiv
- Kontinuierlicher Dialog: nach `voice_speaking_end` startet Mic automatisch neu (900ms Pause)

**SSE-Events (neu):**
- `voice_listening_start` → "● Höre zu…"
- `voice_status` → "⏳ Lade Sprachmodell…" (Whisper-Init Feedback)
- `voice_transcript` → Text in chatInput + auto-submit
- `voice_speaking_start` → `voicePulse.startSpeaking()`
- `voice_speaking_end` → `voicePulse.stopThinking()`
- `voice_error` → Fehlermeldung anzeigen

---

### 3. TTS-Provider Wechsel — `tools/voice_tool/tool.py`

**ElevenLabs → Inworld.AI** (auf Nutzerwunsch, 50-75% günstiger)

| | Vorher | Nachher |
|---|---|---|
| Import | `from elevenlabs.client import ElevenLabs` | `import requests, base64, io` |
| API | ElevenLabs REST | `https://api.inworld.ai/tts/v1/voice` |
| Auth | API-Key Header | Basic Auth mit `INWORLD_API_KEY` |
| Audio | ElevenLabs-Stream | Base64-MP3 → pydub → sounddevice |
| Stimme | `INWORLD_VOICE=Lennart` (aus `.env`) | |
| Model | `INWORLD_MODEL=inworld-tts-1.5-max` | |

---

### 4. Bug: NetworkError beim Mic-Klick

**Ursache:** `await asyncio.to_thread(voice_engine.initialize)` blockierte den HTTP-Request bis Whisper vollständig geladen war (30–120 Sekunden). Browser-Fetch timed out → `NetworkError when attempting to fetch resource`.

**Fix:** Initialisierung in den Hintergrund-Task verschoben:
```python
# VORHER (fehlerhaft):
await asyncio.to_thread(voice_engine.initialize)  # blockiert Request
create_task(...)

# NACHHER (korrekt):
async def _listen_and_broadcast():
    await asyncio.to_thread(voice_engine.initialize)  # im Hintergrund
    ...
create_task(_listen_and_broadcast())
return sofort  # HTTP-Antwort sofort
```

---

### 5. Bug: PaErrorCode -9997 (Invalid sample rate)

**Ursache:** `samplerate=16000` war fest kodiert in `sd.rec()`. Das Audiogerät (`default`, 44.100 Hz) unterstützt 16 kHz nicht.

**Fix:** Native Geräterate abfragen und resampeln:
```python
def _device_rate(self) -> int:
    return int(sd.query_devices(kind='input')['default_samplerate'])  # → 44100

def _resample(self, audio, from_rate):
    from scipy.signal import resample_poly  # Hohe Qualität, Antialiasing
    up, down = SAMPLE_RATE // gcd, from_rate // gcd  # 16000/44100
    return resample_poly(audio, up, down).astype('float32')
```

---

### 6. Bug: "Keine Stimme erkannt" (Whisper gibt leeren Text)

Drei Ursachen identifiziert und behoben:

**Bug 6a — Zerhacktes Audio:**
`_record_until_silence` speicherte früher nur laute Chunks (nur Sprache, keine Stille). Whisper bekam unnatürlich zerhackte Audio-Fetzen ohne Pausen zwischen Wörtern → Transkription schlug fehl.

**Fix:** Alle Chunks speichern, Stille nur als Stop-Signal nutzen:
```python
all_chunks.append(chunk)  # IMMER speichern (Sprache + Stille)
if volume >= threshold:
    speech_detected = True
elif speech_detected and silence > 1.8s:
    break  # Stop erst nach erkannter Sprache
```

**Bug 6b — Whisper VAD zu aggressiv:**
`vad_filter=True` auf vorverarbeitetem Audio filterte zu viel weg.

**Fix:** `vad_filter=False`, `beam_size=5`

**Bug 6c — Schlechtes Resampling:**
`np.interp` (lineare Interpolation) produziert Aliasing-Artefakte bei starker Downsampling-Ratio (44100→16000).

**Fix:** `scipy.signal.resample_poly` mit Antialiasing-Filter.

**Bug 6d — Browser-Mikro-Konflikt:**
Browser `getUserMedia` startete vor sounddevice → mögliche Mikrofon-Exklusivität auf manchen PulseAudio-Konfigurationen.

**Fix:** Server-Call (`/voice/listen`) startet BEVOR Browser-`getUserMedia` aufgerufen wird.

---

## Geänderte Dateien

| Datei | Art der Änderung |
|---|---|
| `server/mcp_server.py` | +90 Zeilen: 4 Voice REST Endpoints, `_voice_listen_task` global |
| `server/canvas_ui.py` | Mic IIFE komplett neu, SSE-Patch erweitert, Server-Call-Reihenfolge |
| `tools/voice_tool/tool.py` | ElevenLabs→Inworld.AI, `_device_rate()`, `_resample()` mit scipy, `_record_until_silence` überarbeitet, `vad_filter=False` |

---

## Aktueller Datenfluss (Voice)

```
[Mic-Button klicken]
  → POST /voice/listen (sofortige HTTP-Antwort)
  → Background Task:
      → SSE: voice_listening_start → "● Höre zu…"
      → sounddevice.rec() bei 44100 Hz (alle Chunks)
      → Stille erkannt → Stop
      → scipy.resample_poly(44100→16000 Hz)
      → Whisper.transcribe(vad_filter=False, beam_size=5, language="de")
      → SSE: voice_transcript {text}
  → Canvas: chatInput befüllen + auto-submit
  → Timus antwortet → SSE: chat_reply
  → POST /voice/speak {text}
      → Inworld.AI REST API (Basic Auth)
      → Base64-MP3 → pydub → sounddevice.play()
      → SSE: voice_speaking_start → voicePulse.startSpeaking()
      → SSE: voice_speaking_end → voicePulse.stopThinking()
  → Wenn voiceActive: automatisch wieder startMic() (900ms Pause)
```

---

## Offene Punkte

- Nach Neustart des Servers: Whisper-Modell wird beim ersten Mic-Klick geladen (~60s, sichtbar als "⏳ Lade Sprachmodell…")
- Diagnose-Logging aktiv (`log.info Peak/RMS`) — kann später auf `log.debug` gesetzt werden
- `timus_hybrid_v2.py` läuft weiterhin als separates System; keine Duplikation, da canvas_ui die `voice_tool`-MCP-Methoden nutzt

---

## Systemstatus

- **Autonomy Score:** 79.8/100 (sichtbar im Canvas Sidebar)
- **Voice Provider:** Inworld.AI (Lennart, inworld-tts-1.5-max, Rate 1.3, Temp 1.5)
- **STT:** Faster-Whisper `medium`, CPU/CUDA auto-detect
- **Audio Device:** `default` @ 44.100 Hz → resampelt auf 16.000 Hz für Whisper
- **Canvas Version:** v3.3+ (3-Spalten Layout, Cytoscape.js, Markdown-Chat, Autonomy-Tab)

---

*Erstellt: 2026-02-28 22:58 — Claude Code (Sonnet 4.6)*

# tools/engines/vision_telemetry.py
"""
C3 Vision/OCR Telemetrie-Schicht.

Sammelt strukturierte Laufzeit-Events fuer alle Vision/OCR-Engines:
  - Modell-Initialisierung (Start + Ende + Dauer)
  - Inferenz (Start + Ende + Dauer + Bildgroesse)
  - Device-Wechsel
  - Fallback-Ereignisse
  - OOM / Timeout / Runtime-Fehler

Design-Prinzipien:
  - best-effort: kein Event darf den Hot-Path crashen
  - Singleton-Ring (max MAX_EVENTS = 500 Eintraege)
  - thread-safe via threading.Lock
  - emittiert C2-Observability fuer Aggregation (fire-and-forget)
  - KEINE Aenderung an bestehenden Engine-Klassen noetig
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any

log = logging.getLogger("vision_telemetry")

MAX_EVENTS: int = 500  # Ring-Puffer-Groesse


class VisionPhase(str, Enum):
    INIT_START    = "init_start"
    INIT_DONE     = "init_done"
    INFER_START   = "infer_start"
    INFER_DONE    = "infer_done"
    DEVICE_CHANGE = "device_change"
    FALLBACK      = "fallback"
    OOM           = "oom"
    ERROR         = "error"


@dataclass
class VisionEvent:
    engine:        str                   # "ocr" | "object_detection" | "segmentation" | "florence2" | "qwen_vl"
    phase:         VisionPhase
    model:         str          = ""     # Modellname / Backend-Name
    device:        str          = ""     # "cuda" | "cpu"
    duration_ms:   float        = 0.0   # Dauer in Millisekunden
    image_w:       int          = 0     # Bildbreite in Pixel
    image_h:       int          = 0     # Bildhoehe in Pixel
    fallback_from: str          = ""     # z.B. "cuda"
    fallback_to:   str          = ""     # z.B. "cpu"
    fallback_reason: str        = ""
    error_class:   str          = ""     # Kurzname der Exception-Klasse
    error_msg:     str          = ""     # Erste 200 Zeichen der Fehlermeldung
    success:       bool         = True
    ts:            float        = field(default_factory=time.monotonic)

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["phase"] = self.phase.value
        return d


class VisionTelemetryRecorder:
    """Singleton-Ring fuer Vision-Telemetrie-Events."""

    _instance: Optional["VisionTelemetryRecorder"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "VisionTelemetryRecorder":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._ring: List[VisionEvent] = []
            inst._ring_lock = threading.Lock()
            inst._init_durations: Dict[str, float] = {}   # engine → letzte Init-Dauer ms
            inst._infer_durations: Dict[str, float] = {}  # engine → letzte Inferenz-Dauer ms
            inst._oom_counts: Dict[str, int] = {}          # engine → OOM-Zaehler
            inst._fallback_counts: Dict[str, int] = {}    # engine → Fallback-Zaehler
            inst._error_counts: Dict[str, int] = {}        # engine → Fehler-Zaehler
            cls._instance = inst
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────

    def record(self, event: VisionEvent) -> None:
        """Fuegt ein Event zum Ring-Puffer hinzu. Nie werfen."""
        try:
            with self._ring_lock:
                self._ring.append(event)
                if len(self._ring) > MAX_EVENTS:
                    self._ring.pop(0)
            self._update_counters(event)
            self._emit_observability(event)
        except Exception as exc:
            log.debug("vision_telemetry.record ignoriert Fehler: %s", exc)

    def get_events(self, engine: str = "", last_n: int = 50) -> List[Dict[str, Any]]:
        """Gibt die letzten N Events (optional gefiltert nach Engine) zurueck."""
        with self._ring_lock:
            events = list(self._ring)
        if engine:
            events = [e for e in events if e.engine == engine]
        return [e.as_dict() for e in events[-last_n:]]

    def get_summary(self) -> Dict[str, Any]:
        """Aggregiertes Status-Dict aller erfassten Engines."""
        with self._ring_lock:
            events = list(self._ring)

        engines: Dict[str, Dict[str, Any]] = {}
        for ev in events:
            entry = engines.setdefault(ev.engine, {
                "infer_count": 0,
                "infer_errors": 0,
                "oom_count": 0,
                "fallback_count": 0,
                "last_device": "",
                "last_model": "",
                "last_infer_ms": 0.0,
                "last_init_ms": 0.0,
            })
            if ev.phase == VisionPhase.INFER_DONE:
                entry["infer_count"] += 1
                entry["last_infer_ms"] = ev.duration_ms
                entry["last_device"] = ev.device
                entry["last_model"] = ev.model
                if not ev.success:
                    entry["infer_errors"] += 1
            elif ev.phase == VisionPhase.OOM:
                entry["oom_count"] += 1
            elif ev.phase == VisionPhase.FALLBACK:
                entry["fallback_count"] += 1
            elif ev.phase == VisionPhase.INIT_DONE:
                entry["last_init_ms"] = ev.duration_ms
                entry["last_device"] = ev.device
                entry["last_model"] = ev.model

        return {
            "total_events": len(events),
            "engines": engines,
            "oom_counts": dict(self._oom_counts),
            "fallback_counts": dict(self._fallback_counts),
        }

    # ── Convenience Builder-Methoden ──────────────────────────────────

    def init_start(self, engine: str, model: str, device: str) -> float:
        """Gibt monotonen Start-Timestamp zurueck."""
        self.record(VisionEvent(engine=engine, phase=VisionPhase.INIT_START, model=model, device=device))
        return time.monotonic()

    def init_done(self, engine: str, model: str, device: str, t0: float, *, success: bool = True,
                  error_class: str = "", error_msg: str = "") -> None:
        ms = (time.monotonic() - t0) * 1000.0
        self.record(VisionEvent(engine=engine, phase=VisionPhase.INIT_DONE, model=model, device=device,
                                duration_ms=ms, success=success, error_class=error_class, error_msg=error_msg[:200]))

    def infer_start(self, engine: str, model: str, device: str,
                    image_w: int = 0, image_h: int = 0) -> float:
        self.record(VisionEvent(engine=engine, phase=VisionPhase.INFER_START,
                                model=model, device=device, image_w=image_w, image_h=image_h))
        return time.monotonic()

    def infer_done(self, engine: str, model: str, device: str, t0: float, *,
                   image_w: int = 0, image_h: int = 0, success: bool = True,
                   error_class: str = "", error_msg: str = "") -> None:
        ms = (time.monotonic() - t0) * 1000.0
        self.record(VisionEvent(engine=engine, phase=VisionPhase.INFER_DONE, model=model, device=device,
                                duration_ms=ms, image_w=image_w, image_h=image_h,
                                success=success, error_class=error_class, error_msg=error_msg[:200]))

    def fallback(self, engine: str, from_device: str, to_device: str, reason: str, model: str = "") -> None:
        self.record(VisionEvent(engine=engine, phase=VisionPhase.FALLBACK, model=model,
                                device=to_device, fallback_from=from_device, fallback_to=to_device,
                                fallback_reason=reason[:200]))

    def oom(self, engine: str, model: str, device: str, msg: str = "") -> None:
        self.record(VisionEvent(engine=engine, phase=VisionPhase.OOM, model=model, device=device,
                                success=False, error_class="OutOfMemoryError", error_msg=msg[:200]))

    def error(self, engine: str, model: str, device: str, exc: Exception) -> None:
        self.record(VisionEvent(engine=engine, phase=VisionPhase.ERROR, model=model, device=device,
                                success=False, error_class=type(exc).__name__,
                                error_msg=str(exc)[:200]))

    # ── Interne Hilfsmethoden ─────────────────────────────────────────

    def _update_counters(self, event: VisionEvent) -> None:
        try:
            if event.phase == VisionPhase.OOM:
                self._oom_counts[event.engine] = self._oom_counts.get(event.engine, 0) + 1
            elif event.phase == VisionPhase.FALLBACK:
                self._fallback_counts[event.engine] = self._fallback_counts.get(event.engine, 0) + 1
            elif event.phase in (VisionPhase.ERROR,) and not event.success:
                self._error_counts[event.engine] = self._error_counts.get(event.engine, 0) + 1
        except Exception:
            pass

    def _emit_observability(self, event: VisionEvent) -> None:
        """Fire-and-forget C2-Observability fuer relevante Events."""
        if event.phase not in (VisionPhase.OOM, VisionPhase.FALLBACK, VisionPhase.INIT_DONE, VisionPhase.ERROR):
            return
        try:
            from orchestration.autonomy_observation import record_autonomy_observation
            record_autonomy_observation(
                f"vision_{event.phase.value}",
                {
                    "engine": event.engine,
                    "model": event.model,
                    "device": event.device,
                    "success": event.success,
                    "error_class": event.error_class,
                    "fallback_from": event.fallback_from,
                    "fallback_to": event.fallback_to,
                    "duration_ms": round(event.duration_ms, 1),
                },
            )
        except Exception:
            pass  # Telemetrie darf nie crashen


# Globale Singleton-Instanz
vision_telemetry = VisionTelemetryRecorder()


def is_oom_error(exc: BaseException) -> bool:
    """Erkennt CUDA-OOM-Fehler zuverlaessig."""
    msg = str(exc).lower()
    return (
        isinstance(exc, RuntimeError)
        and ("out of memory" in msg or "cuda" in msg and "memory" in msg)
    )

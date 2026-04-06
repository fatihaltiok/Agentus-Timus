# tools/engines/vision_router.py
"""
C3 Vision/OCR Routing-Regeln.

Entscheidet explizit und nachvollziehbar welche Engine/Strategie
fuer eine gegebene Anfrage genutzt wird — kein stiller Mischpfad mehr.

Strategien:
  OCR_ONLY         — Nur OCR (Tesseract oder EasyOCR), kein Vision-Modell
  FLORENCE2_PRIMARY — Florence-2 als Hauptpfad (OD + OCR + Caption)
  FLORENCE2_HYBRID  — Florence-2 + PaddleOCR kombiniert
  CPU_FALLBACK_ONLY — Kein GPU, nur CPU-OCR (Tesseract)

Routing-Regeln (in Prioritaetsreihenfolge):
  1. Kein GPU / VRAM < VRAM_MIN_MB          → CPU_FALLBACK_ONLY
  2. task_type == "ui_detection"             → FLORENCE2_PRIMARY
  3. Bild > 2 MP  UND VRAM >= VRAM_HI_MB   → FLORENCE2_PRIMARY
  4. Bild <= 0.5 MP (kleines Textbild)       → OCR_ONLY
  5. Bild > 1 MP  UND VRAM >= VRAM_LO_MB   → FLORENCE2_HYBRID
  6. VRAM >= VRAM_LO_MB                      → FLORENCE2_PRIMARY
  7. Default                                 → OCR_ONLY

Schwellenwerte (ueberschreibbar per .env):
  VISION_VRAM_MIN_MB=1500   — Mindestspeicher fuer GPU-Nutzung
  VISION_VRAM_LO_MB=2000    — Untergrenze fuer Florence-2 primary
  VISION_VRAM_HI_MB=3000    — Schwelle fuer grosse Bilder

CrossHair-Contract: select_vision_strategy() gibt immer eine gueltige Strategie zurueck.
"""
from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Optional, Tuple

log = logging.getLogger("vision_router")

# ── Schwellenwerte ─────────────────────────────────────────────────────────────

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


VRAM_MIN_MB: int = _env_int("VISION_VRAM_MIN_MB", 1500)   # Unterhalb → kein GPU
VRAM_LO_MB:  int = _env_int("VISION_VRAM_LO_MB",  2000)   # Florence-2 möglich
VRAM_HI_MB:  int = _env_int("VISION_VRAM_HI_MB",  3000)   # Große Bilder OK

MP_SMALL:    float = 0.5e6   # Pixel — kleines Textbild → nur OCR
MP_LARGE:    float = 2.0e6   # Pixel — grosses Bild → Florence-2 primary


class VisionStrategy(str, Enum):
    OCR_ONLY          = "ocr_only"
    FLORENCE2_PRIMARY = "florence2_primary"
    FLORENCE2_HYBRID  = "florence2_hybrid"
    CPU_FALLBACK_ONLY = "cpu_fallback_only"


def get_vram_available_mb() -> int:
    """Gibt verfuegbaren VRAM in MB zurueck. 0 wenn kein CUDA oder Fehler.
    CrossHair: Ergebnis immer >= 0.
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return 0
        free_bytes, _ = torch.cuda.mem_get_info()
        result = int(free_bytes // (1024 * 1024))
        return max(0, result)
    except Exception:
        return 0


def _pixel_count(image_w: int, image_h: int) -> float:
    """Pixelzahl aus Bildgroesse. Nie negativ."""
    return float(max(0, image_w) * max(0, image_h))


def select_vision_strategy(
    image_w: int = 0,
    image_h: int = 0,
    task_type: str = "",
    vram_available_mb: Optional[int] = None,
) -> VisionStrategy:
    """Waehlt die optimale Vision-Strategie anhand von Bildgroesse, Task und VRAM.

    Args:
        image_w:           Bildbreite in Pixel (0 = unbekannt)
        image_h:           Bildhoehe in Pixel (0 = unbekannt)
        task_type:         "ui_detection" | "ocr" | "caption" | "hybrid" | "" (unbekannt)
        vram_available_mb: Override fuer VRAM (fuer Tests); None = automatisch ermitteln

    Returns:
        VisionStrategy — immer ein gueltiger Wert, wirft nie.

    CrossHair-Contract: result in VisionStrategy — immer.
    """
    try:
        vram = vram_available_mb if vram_available_mb is not None else get_vram_available_mb()
        vram = max(0, int(vram))
        pixels = _pixel_count(image_w, image_h)
        task   = str(task_type or "").lower().strip()

        # Regel 1 — Kein verwertbarer GPU-Speicher
        if vram < VRAM_MIN_MB:
            log.debug("C3 Route: CPU_FALLBACK_ONLY (vram=%d < %d)", vram, VRAM_MIN_MB)
            return VisionStrategy.CPU_FALLBACK_ONLY

        # Regel 2 — UI-Erkennung immer Florence-2
        if task == "ui_detection":
            log.debug("C3 Route: FLORENCE2_PRIMARY (task=ui_detection)")
            return VisionStrategy.FLORENCE2_PRIMARY

        # Regel 3 — Grosses Bild + genuegend VRAM
        if pixels >= MP_LARGE and vram >= VRAM_HI_MB:
            log.debug("C3 Route: FLORENCE2_PRIMARY (pixels=%.0f >= %.0f, vram=%d)", pixels, MP_LARGE, vram)
            return VisionStrategy.FLORENCE2_PRIMARY

        # Regel 4 — Kleines Textbild → reines OCR
        if 0 < pixels <= MP_SMALL:
            log.debug("C3 Route: OCR_ONLY (pixels=%.0f <= %.0f)", pixels, MP_SMALL)
            return VisionStrategy.OCR_ONLY

        # Regel 5 — Mittelgrosses Bild + VRAM-Untergrenze → Hybrid
        if pixels > MP_SMALL and vram >= VRAM_LO_MB:
            log.debug("C3 Route: FLORENCE2_HYBRID (pixels=%.0f, vram=%d)", pixels, vram)
            return VisionStrategy.FLORENCE2_HYBRID

        # Regel 6 — VRAM vorhanden aber Bild unbekannt → Florence-2 primary
        if vram >= VRAM_LO_MB:
            log.debug("C3 Route: FLORENCE2_PRIMARY (vram=%d, image unknown)", vram)
            return VisionStrategy.FLORENCE2_PRIMARY

        # Regel 7 — Default: sicherstes Fallback
        log.debug("C3 Route: OCR_ONLY (default fallback)")
        return VisionStrategy.OCR_ONLY

    except Exception as exc:
        log.error("C3 Router Fehler — fallback auf OCR_ONLY: %s", exc)
        return VisionStrategy.OCR_ONLY


def routing_summary(
    strategy: VisionStrategy,
    image_w: int = 0,
    image_h: int = 0,
    vram_mb: int = 0,
    task_type: str = "",
) -> str:
    """Gibt einen lesbaren Routing-Entscheid als String zurueck (fuer Logging/Telemetrie)."""
    px = _pixel_count(image_w, image_h)
    return (
        f"C3-Route: {strategy.value} | "
        f"task={task_type or 'unknown'} | "
        f"image={image_w}x{image_h} ({px/1e6:.1f}MP) | "
        f"vram={vram_mb}MB"
    )


def _clamp_vram(vram_mb: int) -> int:
    """Klemmt VRAM auf [0, 80000] fuer CrossHair-Verifikation."""
    return max(0, min(80000, vram_mb))

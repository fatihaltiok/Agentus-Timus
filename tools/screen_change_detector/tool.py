# tools/screen_change_detector/tool.py
"""
Screen-Change-Gate: Reduziert Vision-Calls um 70-95%.

Strategie:
1. Hash-Vergleich (schnell) - identische Bilder erkennen
2. Pixel-Diff (wenn Hash unterschiedlich) - feine Änderungen messen
3. ROI-Support - nur bestimmte Bereiche überwachen

Spart massiv Rechenzeit, indem Vision nur bei echter Änderung läuft.
"""

import logging
import asyncio
import os
import hashlib
import time
from typing import Optional, Dict, Tuple
from dataclasses import dataclass, asdict

import cv2
import numpy as np
from PIL import Image
import mss

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
log = logging.getLogger("screen_change_detector")

# Konfiguration
DIFF_THRESHOLD = float(os.getenv("DIFF_THRESHOLD", "0.001"))  # 0.1% Änderung
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))
HASH_CACHE_SIZE = 10  # Anzahl der letzten Hashes im Cache


@dataclass
class ScreenSnapshot:
    """Snapshot eines Bildschirms zu einem Zeitpunkt."""
    timestamp: float
    hash: str
    size: Tuple[int, int]  # (width, height)
    roi: Optional[Dict] = None
    thumbnail: Optional[np.ndarray] = None  # Für schnellen Diff


class ScreenChangeDetector:
    """
    Erkennt Bildschirm-Änderungen mit Multi-Level-Ansatz.

    Level 1: Hash-Vergleich (schnellste Methode, ~0.1ms)
    Level 2: Pixel-Diff (wenn Hash unterschiedlich, ~5-10ms)
    Level 3: Optional - Region-basierte Analyse
    """

    def __init__(self, threshold: float = DIFF_THRESHOLD):
        self.threshold = threshold
        self.last_snapshot: Optional[ScreenSnapshot] = None
        self.hash_history = []  # Cache für mehrere Hashes
        self.stats = {
            "total_checks": 0,
            "changes_detected": 0,
            "cache_hits": 0,
            "avg_check_time_ms": 0
        }

    def _get_screenshot(self, roi: Optional[Dict] = None) -> Image.Image:
        """Macht einen Screenshot vom konfigurierten Monitor."""
        with mss.mss() as sct:
            if ACTIVE_MONITOR < len(sct.monitors):
                monitor = sct.monitors[ACTIVE_MONITOR]
            else:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

            if roi:
                grab_region = {
                    "left": monitor["left"] + roi.get("x", 0),
                    "top": monitor["top"] + roi.get("y", 0),
                    "width": roi.get("width", monitor["width"]),
                    "height": roi.get("height", monitor["height"])
                }
            else:
                grab_region = monitor

            sct_img = sct.grab(grab_region)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            return img

    def _calculate_hash(self, img: Image.Image) -> str:
        """Berechnet MD5-Hash eines Bildes (schnell)."""
        return hashlib.md5(img.tobytes()).hexdigest()

    def _create_thumbnail(self, img: Image.Image, size: int = 32) -> np.ndarray:
        """Erstellt Thumbnail für schnellen Diff-Vergleich."""
        img.thumbnail((size, size), Image.Resampling.NEAREST)
        return np.array(img)

    def _calculate_pixel_diff(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Berechnet prozentuale Pixeldifferenz zwischen zwei Bildern."""
        if img1.shape != img2.shape:
            log.warning(f"Shape-Mismatch: {img1.shape} vs {img2.shape}")
            return 1.0

        diff = np.abs(img1.astype(int) - img2.astype(int))
        max_diff = img1.shape[0] * img1.shape[1] * 255 * 3  # RGB
        ratio = diff.sum() / max_diff

        return ratio

    def has_changed(
        self,
        roi: Optional[Dict] = None,
        force_pixel_diff: bool = False
    ) -> Tuple[bool, Dict]:
        """Prüft ob sich der Screen geändert hat."""
        start_time = time.perf_counter()

        self.stats["total_checks"] += 1

        img = self._get_screenshot(roi)
        current_hash = self._calculate_hash(img)

        if self.last_snapshot is None:
            thumbnail = self._create_thumbnail(img)
            self.last_snapshot = ScreenSnapshot(
                timestamp=time.time(),
                hash=current_hash,
                size=(img.width, img.height),
                roi=roi,
                thumbnail=thumbnail
            )
            self.hash_history.append(current_hash)

            check_time = (time.perf_counter() - start_time) * 1000
            self._update_avg_time(check_time)

            return True, {
                "reason": "first_check",
                "method": "hash",
                "check_time_ms": round(check_time, 2)
            }

        # Level 1: Hash-Vergleich
        if not force_pixel_diff and current_hash == self.last_snapshot.hash:
            self.stats["cache_hits"] += 1

            check_time = (time.perf_counter() - start_time) * 1000
            self._update_avg_time(check_time)

            return False, {
                "reason": "identical_hash",
                "method": "hash",
                "check_time_ms": round(check_time, 2)
            }

        # Level 2: Pixel-Diff
        thumbnail = self._create_thumbnail(img)
        diff_ratio = self._calculate_pixel_diff(
            self.last_snapshot.thumbnail,
            thumbnail
        )

        changed = diff_ratio >= self.threshold

        if changed:
            self.stats["changes_detected"] += 1

            self.last_snapshot = ScreenSnapshot(
                timestamp=time.time(),
                hash=current_hash,
                size=(img.width, img.height),
                roi=roi,
                thumbnail=thumbnail
            )

            self.hash_history.append(current_hash)
            if len(self.hash_history) > HASH_CACHE_SIZE:
                self.hash_history.pop(0)

        check_time = (time.perf_counter() - start_time) * 1000
        self._update_avg_time(check_time)

        return changed, {
            "reason": "changed" if changed else "below_threshold",
            "method": "pixel_diff",
            "diff_ratio": round(diff_ratio, 6),
            "threshold": self.threshold,
            "check_time_ms": round(check_time, 2)
        }

    def _update_avg_time(self, new_time_ms: float):
        """Aktualisiert durchschnittliche Check-Zeit."""
        current_avg = self.stats["avg_check_time_ms"]
        total = self.stats["total_checks"]

        self.stats["avg_check_time_ms"] = (
            (current_avg * (total - 1) + new_time_ms) / total
        )

    def reset(self):
        """Setzt Detector zurück."""
        self.last_snapshot = None
        self.hash_history.clear()
        log.info("Detector zurückgesetzt")

    def get_stats(self) -> Dict:
        """Gibt Performance-Statistiken zurück."""
        if self.stats["total_checks"] == 0:
            return {**self.stats, "cache_hit_rate": 0.0, "change_rate": 0.0}

        cache_hit_rate = self.stats["cache_hits"] / self.stats["total_checks"]
        change_rate = self.stats["changes_detected"] / self.stats["total_checks"]

        return {
            **self.stats,
            "cache_hit_rate": round(cache_hit_rate, 3),
            "change_rate": round(change_rate, 3)
        }


# Globale Detector-Instanz
detector_instance = ScreenChangeDetector()


# ==============================================================================
# RPC METHODEN
# ==============================================================================

@tool(
    name="should_analyze_screen",
    description="Prüft ob eine Screen-Analyse nötig ist. Spart massiv Vision-Calls (70-95%), indem nur bei echter Änderung analysiert wird.",
    parameters=[
        P("roi", "object", "Region of Interest: {x, y, width, height}", required=False, default=None),
        P("force_pixel_diff", "boolean", "Hash überspringen, direkt Pixel-Diff machen", required=False, default=False),
    ],
    capabilities=["vision", "screen"],
    category=C.UI
)
async def should_analyze_screen(
    roi: Optional[Dict] = None,
    force_pixel_diff: bool = False
) -> dict:
    """Prüft ob eine Screen-Analyse nötig ist."""
    log.debug(f"Screen-Change-Check" + (f" (ROI: {roi})" if roi else ""))

    try:
        changed, info = await asyncio.to_thread(
            detector_instance.has_changed,
            roi,
            force_pixel_diff
        )

        stats = detector_instance.get_stats()

        if changed:
            log.info(f"Screen geändert - {info['reason']} ({info['check_time_ms']}ms)")
        else:
            log.debug(f"Keine Änderung - {info['reason']} ({info['check_time_ms']}ms)")

        return {
            "changed": changed,
            "info": info,
            "stats": stats,
            "recommendation": "analyze" if changed else "skip"
        }

    except Exception as e:
        log.error(f"Screen-Change-Check fehlgeschlagen: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="reset_screen_detector",
    description="Setzt den Screen-Detector zurück. Nützlich nach Screen-Wechsel, Auflösungsänderung oder bei Tests.",
    parameters=[],
    capabilities=["vision", "screen"],
    category=C.UI
)
async def reset_screen_detector() -> dict:
    """Setzt den Screen-Detector zurück."""
    try:
        detector_instance.reset()

        return {
            "status": "reset",
            "message": "Screen-Detector zurückgesetzt"
        }

    except Exception as e:
        log.error(f"Reset fehlgeschlagen: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="get_screen_change_stats",
    description="Gibt Performance-Statistiken des Screen-Detectors zurück.",
    parameters=[],
    capabilities=["vision", "screen"],
    category=C.UI
)
async def get_screen_change_stats() -> dict:
    """Gibt Performance-Statistiken des Screen-Detectors zurück."""
    try:
        stats = detector_instance.get_stats()

        if stats["avg_check_time_ms"] < 5:
            performance = "excellent"
        elif stats["avg_check_time_ms"] < 15:
            performance = "good"
        else:
            performance = "slow"

        return {
            **stats,
            "performance": performance,
            "savings_estimate": f"{int(stats.get('cache_hit_rate', 0) * 100)}% Vision-Calls gespart"
        }

    except Exception as e:
        log.error(f"Stats-Abfrage fehlgeschlagen: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="set_change_threshold",
    description="Setzt den Schwellwert für Änderungserkennung (0.0 bis 1.0).",
    parameters=[
        P("threshold", "number", "Schwellwert: 0.0001=sehr sensitiv, 0.001=normal, 0.01=weniger sensitiv"),
    ],
    capabilities=["vision", "screen"],
    category=C.UI
)
async def set_change_threshold(threshold: float) -> dict:
    """Setzt den Schwellwert für Änderungserkennung."""
    if not 0.0 <= threshold <= 1.0:
        raise Exception(
            f"Threshold muss zwischen 0.0 und 1.0 liegen, nicht {threshold}"
        )

    try:
        old_threshold = detector_instance.threshold
        detector_instance.threshold = threshold

        log.info(f"Threshold geändert: {old_threshold} -> {threshold}")

        return {
            "old_threshold": old_threshold,
            "new_threshold": threshold,
            "message": f"Threshold auf {threshold} gesetzt"
        }

    except Exception as e:
        log.error(f"Threshold-Änderung fehlgeschlagen: {e}", exc_info=True)
        raise Exception(str(e))

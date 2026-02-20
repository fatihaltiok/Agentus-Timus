


# tools/verification_tool/tool.py
"""
Verification Tool für Timus Visual Agent (gefixt v3).

Prüft ob Aktionen erfolgreich waren durch:
- Screenshot-Differenz-Analyse (sensibler für subtile Changes)
- UI-Stabilitätserkennung
- Fehlerzustand-Erkennung
- Neu: Textfeld-Modus mit Qwen-VL-Analyse für Fokus-Check
"""

import logging
import asyncio
import os
import base64
import time
from typing import Optional, Dict, Tuple, Any
from dataclasses import dataclass, field
from PIL import Image, ImageChops, ImageFilter
import numpy as np
import mss
import io
import httpx

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
log = logging.getLogger("verification_tool")

# Konfiguration (gefixt: Sehr niedriger Threshold)
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))
DIFF_THRESHOLD = float(os.getenv("DIFF_THRESHOLD", "0.001"))  # 0.1% für Cursor/Fokus
STABILITY_TIMEOUT = float(os.getenv("STABILITY_TIMEOUT", "3.0"))
STABILITY_CHECK_INTERVAL = 0.3
MAX_WAIT_FOR_CHANGE = float(os.getenv("MAX_WAIT_FOR_CHANGE", "10.0"))
# Qwen-VL Engine fuer Fokus-Analyse (ersetzt Moondream)
try:
    from tools.engines.qwen_vl_engine import qwen_vl_engine_instance
    QWEN_VL_AVAILABLE = True
except ImportError:
    QWEN_VL_AVAILABLE = False

try:
    from tools.debug_screenshot_tool.tool import create_debug_artifacts
    DEBUG_SCREENSHOT_AVAILABLE = True
except ImportError:
    DEBUG_SCREENSHOT_AVAILABLE = False


@dataclass
class VerificationResult:
    """Ergebnis einer Verifikation."""
    success: bool
    change_detected: bool
    change_percentage: float
    stable: bool
    error_detected: bool
    error_type: Optional[str] = None
    message: str = ""
    before_screenshot: Optional[bytes] = None
    after_screenshot: Optional[bytes] = None
    debug_artifacts: Optional[Dict[str, Any]] = None


@dataclass
class ScreenState:
    """Speichert den Zustand des Bildschirms."""
    timestamp: float
    screenshot: Image.Image
    screenshot_hash: str = ""

    def __post_init__(self):
        # Einfacher Hash für schnellen Vergleich
        small = self.screenshot.copy()
        small.thumbnail((100, 100))
        self.screenshot_hash = str(hash(small.tobytes()))


class VerificationEngine:
    """
    Engine für Aktions-Verifikation (gefixt für Textfelder).

    Workflow:
    1. capture_before() - Screenshot vor Aktion
    2. [Aktion ausführen]
    3. verify_action() - Prüft Änderung oder Fokus via Qwen-VL
    4. wait_for_stability() - Wartet bis UI stabil
    """

    def __init__(self):
        self.before_state: Optional[ScreenState] = None
        self.after_state: Optional[ScreenState] = None
        self.history: list[VerificationResult] = []
        self.screen_width: int = 1920
        self.screen_height: int = 1200

        # Fehlermuster (Text der auf Fehler hinweist)
        self.error_patterns = [
            "error", "fehler", "failed", "fehlgeschlagen",
            "not found", "nicht gefunden", "404", "500",
            "connection", "verbindung", "timeout",
            "permission denied", "zugriff verweigert",
            "crash", "abgestürzt"
        ]

    def _capture_screenshot(self) -> Image.Image:
        """Macht einen Screenshot des aktiven Monitors."""
        with mss.mss() as sct:
            if ACTIVE_MONITOR < len(sct.monitors):
                monitor = sct.monitors[ACTIVE_MONITOR]
            else:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

            self.screen_width = monitor["width"]
            self.screen_height = monitor["height"]

            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            return img

    def _calculate_diff(self, img1: Image.Image, img2: Image.Image) -> float:
        """
        Berechnet den prozentualen Unterschied zwischen zwei Bildern (gefixt: Sensibler).
        """
        if img1.size != img2.size:
            img2 = img2.resize(img1.size)

        gray1 = img1.convert("L")
        gray2 = img2.convert("L")

        diff = ImageChops.difference(gray1, gray2)
        diff = diff.filter(ImageFilter.GaussianBlur(radius=1))

        diff_array = np.array(diff)
        changed_pixels = np.sum(diff_array > 5)
        total_pixels = diff_array.size

        change_ratio = changed_pixels / total_pixels
        return change_ratio

    def _image_to_base64(self, img: Image.Image) -> str:
        """Konvertiert PIL Image zu Base64."""
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    async def _analyze_focus_with_vision(self, img: Image.Image) -> bool:
        """Analysiert Screenshot mit Qwen-VL auf Fokus/Cursor in Textfeld."""
        if not QWEN_VL_AVAILABLE or not qwen_vl_engine_instance.is_initialized():
            log.debug("Qwen-VL nicht verfuegbar fuer Fokus-Analyse")
            return False
        try:
            query = "Ist ein Cursor oder Fokus in einem Textfeld, Eingabefeld oder Chat-Input sichtbar? Antworte nur mit Ja oder Nein."
            result = await asyncio.to_thread(
                qwen_vl_engine_instance.analyze_screenshot, img, query
            )
            answer = result.lower() if result else ""
            log.debug(f"Qwen-VL Fokus-Query: '{query}' -> '{answer}'")
            return "ja" in answer or "yes" in answer or "cursor" in answer or "fokus" in answer
        except Exception as e:
            log.error(f"Qwen-VL Fokus-Analyse Fehler: {e}")
            return False

    async def capture_before(self) -> ScreenState:
        """Speichert den Bildschirmzustand VOR einer Aktion."""
        screenshot = await asyncio.to_thread(self._capture_screenshot)
        self.before_state = ScreenState(
            timestamp=time.time(),
            screenshot=screenshot
        )
        log.debug(f"Before-Screenshot gespeichert (Hash: {self.before_state.screenshot_hash[:8]}...)")
        return self.before_state

    async def verify_action(self,
                           expected_change: bool = True,
                           min_change: float = None,
                           timeout: float = None,
                           text_field_mode: bool = False,
                           debug_context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """Verifiziert ob eine Aktion erfolgreich war."""
        if not self.before_state:
            return VerificationResult(
                success=False,
                change_detected=False,
                change_percentage=0.0,
                stable=False,
                error_detected=False,
                message="Kein Before-Screenshot vorhanden. Rufe zuerst capture_before() auf."
            )

        min_change = min_change or DIFF_THRESHOLD
        timeout = timeout or MAX_WAIT_FOR_CHANGE

        start_time = time.time()
        change_detected = False
        change_percentage = 0.0

        while time.time() - start_time < timeout:
            screenshot = await asyncio.to_thread(self._capture_screenshot)
            self.after_state = ScreenState(
                timestamp=time.time(),
                screenshot=screenshot
            )

            change_percentage = self._calculate_diff(
                self.before_state.screenshot,
                self.after_state.screenshot
            )

            log.debug(f"Änderung: {change_percentage*100:.2f}% (Min: {min_change*100:.2f}%)")

            if change_percentage >= min_change:
                change_detected = True
                break

            if not expected_change:
                break

            await asyncio.sleep(STABILITY_CHECK_INTERVAL)

        # Für Textfeld-Modus: Fallback-Analyse
        message = ""
        if text_field_mode and not change_detected and self.after_state:
            log.info("Textfeld-Modus: Fallback zu Qwen-VL-Analyse auf Fokus")
            focus_detected = await self._analyze_focus_with_vision(self.after_state.screenshot)
            if focus_detected:
                change_detected = True
                message = f"Keine Pixel-Änderung, aber Fokus erkannt via Analyse ({change_percentage*100:.1f}%)"

        # Erfolg bestimmen
        if not message:
            if expected_change:
                success = change_detected
                message = f"Änderung erkannt ({change_percentage*100:.1f}%)" if success else f"Keine Änderung erkannt ({change_percentage*100:.1f}% < {min_change*100:.1f}%)"
            else:
                success = not change_detected
                message = "Bildschirm unverändert wie erwartet" if success else f"Unerwartete Änderung ({change_percentage*100:.1f}%)"
        else:
            success = change_detected

        debug_artifacts = None
        if not success:
            debug_artifacts = await self._capture_failure_debug(
                message=message,
                expected_change=expected_change,
                min_change=min_change,
                change_percentage=change_percentage,
                debug_context=debug_context or {},
            )

        result = VerificationResult(
            success=success,
            change_detected=change_detected,
            change_percentage=change_percentage,
            stable=True,
            error_detected=False,
            message=message,
            debug_artifacts=debug_artifacts,
        )

        self.history.append(result)
        return result

    async def _capture_failure_debug(
        self,
        message: str,
        expected_change: bool,
        min_change: float,
        change_percentage: float,
        debug_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not DEBUG_SCREENSHOT_AVAILABLE:
            log.warning("debug_screenshot_tool nicht verfügbar - kein Overlay erzeugt")
            return None

        target_x = debug_context.get("x", debug_context.get("click_x"))
        target_y = debug_context.get("y", debug_context.get("click_y"))
        width = debug_context.get("width", 0)
        height = debug_context.get("height", 0)
        confidence = debug_context.get("confidence")

        metadata = {
            "verify": {
                "expected_change": expected_change,
                "min_change": min_change,
                "change_percentage": round(change_percentage * 100, 4),
                "message": message,
            },
            "before": {
                "timestamp": self.before_state.timestamp if self.before_state else None,
                "hash": self.before_state.screenshot_hash if self.before_state else None,
            },
            "after": {
                "timestamp": self.after_state.timestamp if self.after_state else None,
                "hash": self.after_state.screenshot_hash if self.after_state else None,
            },
            "context": debug_context,
        }

        try:
            result = await asyncio.to_thread(
                create_debug_artifacts,
                target_x,
                target_y,
                int(width) if width else 0,
                int(height) if height else 0,
                confidence,
                message,
                metadata,
                None,
            )
            log.info(
                "Debug-Overlay gespeichert: %s",
                result.get("screenshot_path", "unbekannt"),
            )
            return result
        except Exception as e:
            log.error(f"Fehler beim Erstellen des Debug-Overlays: {e}", exc_info=True)
            return None

    async def wait_for_stability(self, timeout: float = None) -> Tuple[bool, float]:
        """Wartet bis der Bildschirm stabil ist."""
        timeout = timeout or STABILITY_TIMEOUT
        start_time = time.time()
        last_screenshot = await asyncio.to_thread(self._capture_screenshot)
        stable_since = time.time()

        while time.time() - start_time < timeout:
            await asyncio.sleep(STABILITY_CHECK_INTERVAL)

            current_screenshot = await asyncio.to_thread(self._capture_screenshot)
            change = self._calculate_diff(last_screenshot, current_screenshot)

            if change > 0.001:
                stable_since = time.time()
                log.debug(f"Bildschirm ändert sich noch ({change*100:.2f}%)")
            else:
                if time.time() - stable_since >= 0.5:
                    elapsed = time.time() - start_time
                    log.info(f"Bildschirm stabil nach {elapsed:.1f}s")
                    return True, elapsed

            last_screenshot = current_screenshot

        elapsed = time.time() - start_time
        log.warning(f"Timeout nach {elapsed:.1f}s - Bildschirm nicht stabil")
        return False, elapsed

    async def detect_error_state(self) -> Tuple[bool, Optional[str]]:
        """Prüft ob ein Fehlerzustand auf dem Bildschirm angezeigt wird."""
        try:
            from tools.visual_grounding_tool.tool import get_all_screen_text
            result = await get_all_screen_text()

            if hasattr(result, 'value'):
                screen_text = result.value.get("text", "").lower()
            elif isinstance(result, dict):
                screen_text = result.get("text", "").lower()
            else:
                screen_text = str(result).lower()

            for pattern in self.error_patterns:
                if pattern in screen_text:
                    log.warning(f"Fehlermuster erkannt: '{pattern}'")
                    return True, pattern

            return False, None

        except Exception as e:
            log.error(f"Fehler bei Error-Detection: {e}")
            return False, None

    async def full_verification(self, action_name: str = "Aktion") -> VerificationResult:
        """Führt eine vollständige Verifikation durch."""
        log.info(f"Verifiziere: {action_name}")

        change_result = await self.verify_action(expected_change=True)

        if not change_result.change_detected:
            log.warning(f"{action_name}: Keine Änderung erkannt")
            return change_result

        is_stable, wait_time = await self.wait_for_stability()
        error_detected, error_type = await self.detect_error_state()

        result = VerificationResult(
            success=change_result.change_detected and is_stable and not error_detected,
            change_detected=change_result.change_detected,
            change_percentage=change_result.change_percentage,
            stable=is_stable,
            error_detected=error_detected,
            error_type=error_type,
            message=f"{action_name}: " + (
                "Erfolgreich" if not error_detected else f"Fehler: {error_type}"
            )
        )

        self.history.append(result)
        return result

    def get_stats(self) -> Dict:
        """Gibt Statistiken über bisherige Verifikationen zurück."""
        if not self.history:
            return {"total": 0, "success_rate": 0.0}

        total = len(self.history)
        successful = sum(1 for r in self.history if r.success)

        return {
            "total": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": successful / total if total > 0 else 0.0,
            "avg_change": sum(r.change_percentage for r in self.history) / total
        }

    def clear_history(self):
        """Löscht die Verifikations-Historie."""
        self.history = []
        self.before_state = None
        self.after_state = None


# Globale Engine-Instanz
verification_engine = VerificationEngine()


# ==============================================================================
# RPC METHODEN
# ==============================================================================

@tool(
    name="capture_screen_before_action",
    description="Speichert den aktuellen Bildschirmzustand. MUSS vor jeder zu verifizierenden Aktion aufgerufen werden.",
    parameters=[],
    capabilities=["vision", "verification"],
    category=C.UI
)
async def capture_screen_before_action() -> dict:
    """Speichert den aktuellen Bildschirmzustand."""
    try:
        state = await verification_engine.capture_before()
        return {
            "captured": True,
            "timestamp": state.timestamp,
            "hash": state.screenshot_hash[:16],
            "message": "Screenshot gespeichert. Führe jetzt die Aktion aus, dann verify_action_result()."
        }
    except Exception as e:
        log.error(f"Fehler bei capture_before: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="verify_action_result",
    description="Verifiziert ob die letzte Aktion erfolgreich war (gefixt: Textfeld-Modus).",
    parameters=[
        P("expected_change", "boolean", "True wenn sich der Bildschirm ändern sollte", required=False, default=True),
        P("timeout", "number", "Max Wartezeit auf Änderung in Sekunden", required=False, default=5.0),
        P("min_change", "number", "Minimale erwartete Änderung (0.0-1.0)", required=False, default=None),
        P("text_field_mode", "boolean", "Bei True: Fallback zu Screenshot-Analyse auf Fokus", required=False, default=False),
        P("debug_context", "object", "Optional: Kontextdaten fuer Debug-Overlay bei Fehlschlag", required=False, default=None),
    ],
    capabilities=["vision", "verification"],
    category=C.UI
)
async def verify_action_result(expected_change: bool = True,
                               timeout: float = 5.0,
                               min_change: float = None,
                               text_field_mode: bool = False,
                               debug_context: Optional[Dict[str, Any]] = None) -> dict:
    """Verifiziert ob die letzte Aktion erfolgreich war."""
    try:
        result = await verification_engine.verify_action(
            expected_change=expected_change,
            min_change=min_change,
            timeout=timeout,
            text_field_mode=text_field_mode,
            debug_context=debug_context,
        )

        payload = {
            "success": result.success,
            "change_detected": result.change_detected,
            "change_percentage": round(result.change_percentage * 100, 2),
            "message": result.message,
            "recommendation": "Aktion wiederholen" if not result.success else "Weiter mit nächstem Schritt"
        }
        if result.debug_artifacts:
            payload["debug_artifacts"] = result.debug_artifacts
        return payload
    except Exception as e:
        log.error(f"Fehler bei verify_action: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="wait_until_stable",
    description="Wartet bis der Bildschirm stabil ist (keine Animationen/Ladevorgänge).",
    parameters=[
        P("timeout", "number", "Maximale Wartezeit in Sekunden", required=False, default=5.0),
    ],
    capabilities=["vision", "verification"],
    category=C.UI
)
async def wait_until_stable(timeout: float = 5.0) -> dict:
    """Wartet bis der Bildschirm stabil ist."""
    try:
        is_stable, wait_time = await verification_engine.wait_for_stability(timeout)

        return {
            "stable": is_stable,
            "wait_time_seconds": round(wait_time, 2),
            "message": "Bildschirm stabil" if is_stable else "Timeout - Bildschirm noch nicht stabil"
        }
    except Exception as e:
        log.error(f"Fehler bei wait_for_stability: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="check_for_errors",
    description="Prüft ob ein Fehlerzustand auf dem Bildschirm angezeigt wird. Erkennt: Fehlermeldungen, 404, Timeouts, etc.",
    parameters=[],
    capabilities=["vision", "verification"],
    category=C.UI
)
async def check_for_errors() -> dict:
    """Prüft ob ein Fehlerzustand auf dem Bildschirm angezeigt wird."""
    try:
        error_detected, error_type = await verification_engine.detect_error_state()

        return {
            "error_detected": error_detected,
            "error_type": error_type,
            "message": f"Fehler erkannt: {error_type}" if error_detected else "Kein Fehler erkannt"
        }
    except Exception as e:
        log.error(f"Fehler bei error detection: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="verify_click_success",
    description="Kombinierte Methode: Prüft ob ein Klick erfolgreich war (Vergleich, Stabilität, Fehlerprüfung).",
    parameters=[
        P("x", "integer", "X-Koordinate wo geklickt wurde"),
        P("y", "integer", "Y-Koordinate wo geklickt wurde"),
    ],
    capabilities=["vision", "verification"],
    category=C.UI
)
async def verify_click_success(x: int, y: int) -> dict:
    """Kombinierte Methode: Prüft ob ein Klick erfolgreich war."""
    try:
        result = await verification_engine.full_verification(f"Klick bei ({x}, {y})")

        return {
            "success": result.success,
            "change_detected": result.change_detected,
            "change_percentage": round(result.change_percentage * 100, 2),
            "stable": result.stable,
            "error_detected": result.error_detected,
            "error_type": result.error_type,
            "message": result.message,
            "recommendation": _get_recommendation(result)
        }
    except Exception as e:
        log.error(f"Fehler bei verify_click: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="get_verification_stats",
    description="Gibt Statistiken über bisherige Verifikationen zurück.",
    parameters=[],
    capabilities=["vision", "verification"],
    category=C.UI
)
async def get_verification_stats() -> dict:
    """Gibt Statistiken über bisherige Verifikationen zurück."""
    stats = verification_engine.get_stats()
    return stats


@tool(
    name="reset_verification",
    description="Setzt den Verification-Zustand zurück. Nützlich am Anfang einer neuen Aufgabe.",
    parameters=[],
    capabilities=["vision", "verification"],
    category=C.UI
)
async def reset_verification() -> dict:
    """Setzt den Verification-Zustand zurück."""
    verification_engine.clear_history()
    return {"reset": True, "message": "Verification-Engine zurückgesetzt"}


def _get_recommendation(result: VerificationResult) -> str:
    """Gibt eine Empfehlung basierend auf dem Verifikationsergebnis."""
    if result.success:
        return "Weiter mit nächstem Schritt"

    if not result.change_detected:
        return "Klick hat nicht funktioniert. Koordinaten prüfen und erneut versuchen."

    if not result.stable:
        return "Seite lädt noch. Warte und prüfe erneut."

    if result.error_detected:
        return f"Fehler '{result.error_type}' erkannt. Fehlerbehebung nötig."

    return "Unbekanntes Problem. Screenshot analysieren."



# tools/verification_tool/tool.py
"""
Verification Tool für Timus Visual Agent (gefixt v3).

Prüft ob Aktionen erfolgreich waren durch:
- Screenshot-Differenz-Analyse (sensibler für subtile Changes)
- UI-Stabilitätserkennung
- Fehlerzustand-Erkennung
- Neu: Textfeld-Modus mit Moondream-Analyse für Fokus-Check
"""

import logging
import asyncio
import os
import base64
import time
from typing import Optional, Dict, Tuple, Union
from dataclasses import dataclass, field
from PIL import Image, ImageChops, ImageFilter
import numpy as np
import mss
import io
import httpx
from jsonrpcserver import method, Success, Error

from tools.universal_tool_caller import register_tool
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
MOONDREAM_BASE_URL = os.getenv("MOONDREAM_API_BASE", "http://localhost:2021/v1")


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
    3. verify_action() - Prüft Änderung oder Fokus via Moondream
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
        Returns: Float zwischen 0.0 (identisch) und 1.0 (komplett anders)
        """
        # Auf gleiche Größe bringen
        if img1.size != img2.size:
            img2 = img2.resize(img1.size)
        
        # Zu Graustufen konvertieren
        gray1 = img1.convert("L")
        gray2 = img2.convert("L")
        
        # Differenz berechnen
        diff = ImageChops.difference(gray1, gray2)
        
        # Leichtes Blur um Rauschen zu reduzieren
        diff = diff.filter(ImageFilter.GaussianBlur(radius=1))
        
        # Zu numpy Array
        diff_array = np.array(diff)
        
        # Pixel zählen die sich signifikant geändert haben (>5 Helligkeit – gefixt von >30)
        changed_pixels = np.sum(diff_array > 5)
        total_pixels = diff_array.size
        
        change_ratio = changed_pixels / total_pixels
        return change_ratio
    
    def _image_to_base64(self, img: Image.Image) -> str:
        """Konvertiert PIL Image zu Base64."""
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()
    
    async def _analyze_focus_with_moondream(self, img: Image.Image) -> bool:
        """Analysiert Screenshot mit Moondream auf Fokus/Cursor in Textfeld."""
        b64 = self._image_to_base64(img)
        query = "Ist ein Cursor oder Fokus in einem Textfeld, Eingabefeld oder Chat-Input sichtbar?"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{MOONDREAM_BASE_URL}/query",
                    json={"image_url": f"data:image/png;base64,{b64}", "query": query}
                )
                resp.raise_for_status()
                result = resp.json()
                answer = result.get("answer", "").lower()
                log.debug(f"Moondream-Query: '{query}' → '{answer}'")
                return "ja" in answer or "yes" in answer or "cursor" in answer or "fokus" in answer
        except Exception as e:
            log.error(f"Moondream-Analyse Fehler: {e}")
            return False
    
    async def capture_before(self) -> ScreenState:
        """
        Speichert den Bildschirmzustand VOR einer Aktion.
        Muss vor jeder zu verifizierenden Aktion aufgerufen werden.
        """
        screenshot = await asyncio.to_thread(self._capture_screenshot)
        self.before_state = ScreenState(
            timestamp=time.time(),
            screenshot=screenshot
        )
        log.debug(f"📸 Before-Screenshot gespeichert (Hash: {self.before_state.screenshot_hash[:8]}...)")
        return self.before_state
    
    async def verify_action(self, 
                           expected_change: bool = True,
                           min_change: float = None,
                           timeout: float = None,
                           text_field_mode: bool = False) -> VerificationResult:
        """
        Verifiziert ob eine Aktion erfolgreich war (gefixt: Textfeld-Modus).
        
        Args:
            expected_change: True wenn sich der Bildschirm ändern sollte
            min_change: Minimale erwartete Änderung (0.0-1.0), default: DIFF_THRESHOLD
            timeout: Max Wartezeit auf Änderung
            text_field_mode: Bei True: Fallback zu Moondream-Analyse auf Fokus, wenn Change zu klein
        
        Returns:
            VerificationResult mit Details
        """
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
        
        # Warte auf Änderung (mit Timeout)
        while time.time() - start_time < timeout:
            screenshot = await asyncio.to_thread(self._capture_screenshot)
            self.after_state = ScreenState(
                timestamp=time.time(),
                screenshot=screenshot
            )
            
            # Differenz berechnen
            change_percentage = self._calculate_diff(
                self.before_state.screenshot, 
                self.after_state.screenshot
            )
            
            log.debug(f"📊 Änderung: {change_percentage*100:.2f}% (Min: {min_change*100:.2f}%)")
            
            if change_percentage >= min_change:
                change_detected = True
                break
            
            if not expected_change:
                break
            
            await asyncio.sleep(STABILITY_CHECK_INTERVAL)
        
        # Für Textfeld-Modus: Fallback-Analyse
        if text_field_mode and not change_detected and self.after_state:
            log.info("Textfeld-Modus: Fallback zu Moondream-Analyse auf Fokus")
            focus_detected = await self._analyze_focus_with_moondream(self.after_state.screenshot)
            if focus_detected:
                change_detected = True
                message = f"Keine Pixel-Änderung, aber Fokus erkannt via Analyse ({change_percentage*100:.1f}%)"
        
        # Erfolg bestimmen
        if expected_change:
            success = change_detected
            message = f"Änderung erkannt ({change_percentage*100:.1f}%)" if success else f"Keine Änderung erkannt ({change_percentage*100:.1f}% < {min_change*100:.1f}%)"
        else:
            success = not change_detected
            message = "Bildschirm unverändert wie erwartet" if success else f"Unerwartete Änderung ({change_percentage*100:.1f}%)"
        
        result = VerificationResult(
            success=success,
            change_detected=change_detected,
            change_percentage=change_percentage,
            stable=True,  # Wird in wait_for_stability gesetzt
            error_detected=False,
            message=message
        )
        
        self.history.append(result)
        return result
    
    async def wait_for_stability(self, timeout: float = None) -> Tuple[bool, float]:
        """
        Wartet bis der Bildschirm stabil ist (keine Änderungen mehr).
        Nützlich nach Seitenladevorgängen.
        
        Args:
            timeout: Maximale Wartezeit
        
        Returns:
            (is_stable, seconds_waited)
        """
        timeout = timeout or STABILITY_TIMEOUT
        start_time = time.time()
        last_screenshot = await asyncio.to_thread(self._capture_screenshot)
        stable_since = time.time()
        
        while time.time() - start_time < timeout:
            await asyncio.sleep(STABILITY_CHECK_INTERVAL)
            
            current_screenshot = await asyncio.to_thread(self._capture_screenshot)
            change = self._calculate_diff(last_screenshot, current_screenshot)
            
            if change > 0.001:  # Gefixt: Niedriger für Sensibilität
                stable_since = time.time()
                log.debug(f"🔄 Bildschirm ändert sich noch ({change*100:.2f}%)")
            else:
                if time.time() - stable_since >= 0.5:
                    elapsed = time.time() - start_time
                    log.info(f"✅ Bildschirm stabil nach {elapsed:.1f}s")
                    return True, elapsed
            
            last_screenshot = current_screenshot
        
        elapsed = time.time() - start_time
        log.warning(f"⚠️ Timeout nach {elapsed:.1f}s - Bildschirm nicht stabil")
        return False, elapsed
    
    async def detect_error_state(self) -> Tuple[bool, Optional[str]]:
        """
        Prüft ob ein Fehlerzustand auf dem Bildschirm angezeigt wird.
        
        Returns:
            (error_detected, error_type)
        """
        try:
            # OCR auf aktuellem Screenshot
            from tools.visual_grounding_tool.tool import get_all_screen_text
            result = await get_all_screen_text()
            
            if hasattr(result, 'value'):
                screen_text = result.value.get("text", "").lower()
            else:
                screen_text = str(result).lower()
            
            for pattern in self.error_patterns:
                if pattern in screen_text:
                    log.warning(f"⚠️ Fehlermuster erkannt: '{pattern}'")
                    return True, pattern
            
            return False, None
            
        except Exception as e:
            log.error(f"Fehler bei Error-Detection: {e}")
            return False, None
    
    async def full_verification(self, action_name: str = "Aktion") -> VerificationResult:
        """
        Führt eine vollständige Verifikation durch:
        1. Prüft auf Änderung
        2. Wartet auf Stabilität
        3. Prüft auf Fehler
        
        Args:
            action_name: Name der Aktion für Logging
        
        Returns:
            Vollständiges VerificationResult
        """
        log.info(f"🔍 Verifiziere: {action_name}")
        
        # 1. Prüfe auf Änderung
        change_result = await self.verify_action(expected_change=True)
        
        if not change_result.change_detected:
            log.warning(f"⚠️ {action_name}: Keine Änderung erkannt")
            return change_result
        
        # 2. Warte auf Stabilität
        is_stable, wait_time = await self.wait_for_stability()
        
        # 3. Prüfe auf Fehler
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

@method
async def capture_screen_before_action() -> Union[Success, Error]:
    """
    Speichert den aktuellen Bildschirmzustand.
    MUSS vor jeder zu verifizierenden Aktion aufgerufen werden.
    
    Returns:
        Bestätigung mit Timestamp
    """
    try:
        state = await verification_engine.capture_before()
        return Success({
            "captured": True,
            "timestamp": state.timestamp,
            "hash": state.screenshot_hash[:16],
            "message": "Screenshot gespeichert. Führe jetzt die Aktion aus, dann verify_action_result()."
        })
    except Exception as e:
        log.error(f"Fehler bei capture_before: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def verify_action_result(expected_change: bool = True, 
                               timeout: float = 5.0,
                               min_change: float = None,
                               text_field_mode: bool = False) -> Union[Success, Error]:
    """
    Verifiziert ob die letzte Aktion erfolgreich war (gefixt: Textfeld-Modus).
    
    Args:
        expected_change: True wenn sich der Bildschirm ändern sollte (default)
        timeout: Max Wartezeit auf Änderung in Sekunden
        min_change: Optional – Übersteuert DIFF_THRESHOLD
        text_field_mode: Bei True: Fallback zu Screenshot-Analyse auf Fokus
    
    Returns:
        Verifikationsergebnis mit success, change_detected, change_percentage
    """
    try:
        result = await verification_engine.verify_action(
            expected_change=expected_change,
            min_change=min_change,
            timeout=timeout,
            text_field_mode=text_field_mode
        )
        
        return Success({
            "success": result.success,
            "change_detected": result.change_detected,
            "change_percentage": round(result.change_percentage * 100, 2),
            "message": result.message,
            "recommendation": "Aktion wiederholen" if not result.success else "Weiter mit nächstem Schritt"
        })
    except Exception as e:
        log.error(f"Fehler bei verify_action: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def wait_until_stable(timeout: float = 5.0) -> Union[Success, Error]:
    """
    Wartet bis der Bildschirm stabil ist (keine Animationen/Ladevorgänge).
    
    Args:
        timeout: Maximale Wartezeit in Sekunden
    
    Returns:
        Ob Stabilität erreicht wurde und wie lange es dauerte
    """
    try:
        is_stable, wait_time = await verification_engine.wait_for_stability(timeout)
        
        return Success({
            "stable": is_stable,
            "wait_time_seconds": round(wait_time, 2),
            "message": "Bildschirm stabil" if is_stable else "Timeout - Bildschirm noch nicht stabil"
        })
    except Exception as e:
        log.error(f"Fehler bei wait_for_stability: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def check_for_errors() -> Union[Success, Error]:
    """
    Prüft ob ein Fehlerzustand auf dem Bildschirm angezeigt wird.
    Erkennt: Fehlermeldungen, 404, Timeouts, etc.
    
    Returns:
        Ob ein Fehler erkannt wurde und welcher Typ
    """
    try:
        error_detected, error_type = await verification_engine.detect_error_state()
        
        return Success({
            "error_detected": error_detected,
            "error_type": error_type,
            "message": f"Fehler erkannt: {error_type}" if error_detected else "Kein Fehler erkannt"
        })
    except Exception as e:
        log.error(f"Fehler bei error detection: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def verify_click_success(x: int, y: int) -> Union[Success, Error]:
    """
    Kombinierte Methode: Prüft ob ein Klick erfolgreich war.
    
    Führt aus:
    1. Vergleicht mit Before-Screenshot (muss vorher capture_screen_before_action aufrufen)
    2. Wartet auf Stabilität
    3. Prüft auf Fehler
    
    Args:
        x, y: Koordinaten wo geklickt wurde (für Logging)
    
    Returns:
        Vollständiges Verifikationsergebnis
    """
    try:
        result = await verification_engine.full_verification(f"Klick bei ({x}, {y})")
        
        return Success({
            "success": result.success,
            "change_detected": result.change_detected,
            "change_percentage": round(result.change_percentage * 100, 2),
            "stable": result.stable,
            "error_detected": result.error_detected,
            "error_type": result.error_type,
            "message": result.message,
            "recommendation": _get_recommendation(result)
        })
    except Exception as e:
        log.error(f"Fehler bei verify_click: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def get_verification_stats() -> Union[Success, Error]:
    """
    Gibt Statistiken über bisherige Verifikationen zurück.
    
    Returns:
        Anzahl, Erfolgsrate, durchschnittliche Änderung
    """
    stats = verification_engine.get_stats()
    return Success(stats)


@method
async def reset_verification() -> Union[Success, Error]:
    """
    Setzt den Verification-Zustand zurück.
    Nützlich am Anfang einer neuen Aufgabe.
    """
    verification_engine.clear_history()
    return Success({"reset": True, "message": "Verification-Engine zurückgesetzt"})


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


# ==============================================================================
# REGISTRIERUNG
# ==============================================================================

register_tool("capture_screen_before_action", capture_screen_before_action)
register_tool("verify_action_result", verify_action_result)
register_tool("wait_until_stable", wait_until_stable)
register_tool("check_for_errors", check_for_errors)
register_tool("verify_click_success", verify_click_success)
register_tool("get_verification_stats", get_verification_stats)
register_tool("reset_verification", reset_verification)

log.info("✅ Verification Tool v3.0 registriert (gefixt mit Textfeld-Analyse)")
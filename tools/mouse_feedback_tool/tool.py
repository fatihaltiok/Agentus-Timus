# tools/mouse_feedback_tool/tool.py
# -*- coding: utf-8 -*-
"""
Mouse Feedback Tool - Echtzeitige Hand-Auge-Koordination für Timus.

Löst das Problem: Statische Screenshots geben kein Feedback während der Mausbewegung.
Lösung: Cursor-Typ als kontinuierliches Feedback nutzen.

Features:
- Schrittweise Mausbewegung mit Feedback
- Cursor-Typ Erkennung (Arrow, I-beam, Hand, Wait)
- Automatischer Stopp bei Textfeld/Link-Erkennung
- Hover-Verification vor Klick
- Region-basierte Suche (Spiral-Scan)
- Cross-Platform (Windows + Linux)
- Mini-Screenshot für Fein-Lokalisierung

Architektur:
  VisualAgent → Mouse Feedback Tool → Cursor Detection
                                    → PyAutoGUI
                                    → Mini-Screenshots

Version: 1.0
"""

import logging
import os
import sys
import asyncio
import time
import base64
import io
import platform
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

# --- Imports mit Fallbacks ---
try:
    import pyautogui
    pyautogui.FAILSAFE = False  # Disable fail-safe für Automation
    pyautogui.PAUSE = 0.01  # Schnellere Bewegungen
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    import mss
    from PIL import Image
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

# Platform-spezifische Cursor Detection
PLATFORM = platform.system()

if PLATFORM == "Windows":
    try:
        import ctypes
        from ctypes import wintypes
        CURSOR_DETECTION_AVAILABLE = True
    except ImportError:
        CURSOR_DETECTION_AVAILABLE = False
elif PLATFORM == "Linux":
    try:
        from Xlib import X, display
        from Xlib.ext import xfixes
        CURSOR_DETECTION_AVAILABLE = True
    except ImportError:
        CURSOR_DETECTION_AVAILABLE = False
else:
    CURSOR_DETECTION_AVAILABLE = False

# V2 Tool Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
log = logging.getLogger("mouse_feedback_tool")

if not log.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
    ))
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if os.getenv("MOUSE_TOOL_DEBUG", "0") == "1" else logging.INFO)

# Konfiguration
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))
MOVE_STEP_SIZE = int(os.getenv("MOUSE_STEP_SIZE", "30"))  # Pixel pro Schritt
MOVE_STEP_DELAY = float(os.getenv("MOUSE_STEP_DELAY", "0.02"))  # Sekunden zwischen Schritten
HOVER_WAIT_TIME = float(os.getenv("HOVER_WAIT_TIME", "0.15"))  # Sekunden für Hover-Effekt


# ==============================================================================
# CURSOR TYPES
# ==============================================================================

class CursorType(str, Enum):
    """Erkannte Cursor-Typen."""
    ARROW = "arrow"           # Standard-Pfeil
    IBEAM = "ibeam"           # Text-Eingabe (I-Cursor)
    HAND = "hand"             # Klickbarer Link
    WAIT = "wait"             # Laden/Warten
    CROSSHAIR = "crosshair"   # Präzise Auswahl
    RESIZE_H = "resize_h"     # Horizontal Resize
    RESIZE_V = "resize_v"     # Vertikal Resize
    MOVE = "move"             # Verschieben
    FORBIDDEN = "forbidden"   # Nicht erlaubt
    UNKNOWN = "unknown"       # Unbekannt


@dataclass
class CursorInfo:
    """Informationen über den aktuellen Cursor."""
    cursor_type: CursorType
    position: Tuple[int, int]
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0

    def is_text_input(self) -> bool:
        """Ist der Cursor über einem Textfeld?"""
        return self.cursor_type == CursorType.IBEAM

    def is_clickable(self) -> bool:
        """Ist das Element klickbar (Link/Button)?"""
        return self.cursor_type in [CursorType.HAND, CursorType.IBEAM]

    def is_interactive(self) -> bool:
        """Ist das Element interaktiv?"""
        return self.cursor_type not in [CursorType.ARROW, CursorType.WAIT, CursorType.FORBIDDEN]


# ==============================================================================
# CURSOR DETECTION - ABSTRACT BASE
# ==============================================================================

class CursorDetector(ABC):
    """Abstrakte Basisklasse für Cursor-Erkennung."""

    @abstractmethod
    def get_cursor_type(self) -> CursorType:
        """Gibt den aktuellen Cursor-Typ zurück."""
        pass

    @abstractmethod
    def get_cursor_info(self) -> CursorInfo:
        """Gibt vollständige Cursor-Informationen zurück."""
        pass

    def is_available(self) -> bool:
        """Prüft ob die Detection verfügbar ist."""
        return True


# ==============================================================================
# WINDOWS CURSOR DETECTION
# ==============================================================================

class WindowsCursorDetector(CursorDetector):
    """Cursor-Erkennung für Windows via win32 API."""

    # Windows Cursor IDs
    CURSOR_MAPPINGS = {
        65539: CursorType.ARROW,      # IDC_ARROW
        65541: CursorType.IBEAM,      # IDC_IBEAM
        65567: CursorType.HAND,       # IDC_HAND
        65543: CursorType.WAIT,       # IDC_WAIT
        65545: CursorType.CROSSHAIR,  # IDC_CROSS
        65549: CursorType.RESIZE_H,   # IDC_SIZEWE
        65551: CursorType.RESIZE_V,   # IDC_SIZENS
        65555: CursorType.MOVE,       # IDC_SIZEALL
        65559: CursorType.FORBIDDEN,  # IDC_NO
    }

    def __init__(self):
        if PLATFORM != "Windows":
            raise RuntimeError("WindowsCursorDetector nur auf Windows verfügbar")

        # Win32 API Setup
        self.user32 = ctypes.windll.user32

        # Strukturen definieren
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class CURSORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("flags", ctypes.c_uint),
                ("hCursor", ctypes.c_void_p),
                ("ptScreenPos", POINT)
            ]

        self.POINT = POINT
        self.CURSORINFO = CURSORINFO

    def get_cursor_type(self) -> CursorType:
        """Liest den aktuellen Cursor-Typ via Windows API."""
        try:
            cursor_info = self.CURSORINFO()
            cursor_info.cbSize = ctypes.sizeof(self.CURSORINFO)

            if self.user32.GetCursorInfo(ctypes.byref(cursor_info)):
                cursor_handle = cursor_info.hCursor

                # Handle zu Typ mappen
                # Hinweis: Die Handle-Werte sind system-abhängig
                # Wir nutzen GetCursor() für den aktuellen Cursor
                current_cursor = self.user32.GetCursor()

                # Standard-Cursor laden und vergleichen
                for cursor_id, cursor_type in self.CURSOR_MAPPINGS.items():
                    standard_cursor = self.user32.LoadCursorW(0, cursor_id)
                    if current_cursor == standard_cursor:
                        return cursor_type

                return CursorType.UNKNOWN

        except Exception as e:
            log.warning(f"Windows Cursor Detection Fehler: {e}")

        return CursorType.UNKNOWN

    def get_cursor_info(self) -> CursorInfo:
        """Gibt vollständige Cursor-Informationen zurück."""
        try:
            cursor_info = self.CURSORINFO()
            cursor_info.cbSize = ctypes.sizeof(self.CURSORINFO)

            if self.user32.GetCursorInfo(ctypes.byref(cursor_info)):
                pos = (cursor_info.ptScreenPos.x, cursor_info.ptScreenPos.y)
                cursor_type = self.get_cursor_type()
                return CursorInfo(cursor_type=cursor_type, position=pos)

        except Exception as e:
            log.warning(f"Windows CursorInfo Fehler: {e}")

        # Fallback
        if PYAUTOGUI_AVAILABLE:
            pos = pyautogui.position()
            return CursorInfo(cursor_type=CursorType.UNKNOWN, position=pos)

        return CursorInfo(cursor_type=CursorType.UNKNOWN, position=(0, 0))


# ==============================================================================
# LINUX CURSOR DETECTION
# ==============================================================================

class LinuxCursorDetector(CursorDetector):
    """Cursor-Erkennung für Linux via Xlib."""

    # X11 Cursor Namen
    CURSOR_MAPPINGS = {
        "left_ptr": CursorType.ARROW,
        "xterm": CursorType.IBEAM,
        "ibeam": CursorType.IBEAM,
        "text": CursorType.IBEAM,
        "hand": CursorType.HAND,
        "hand2": CursorType.HAND,
        "pointer": CursorType.HAND,
        "watch": CursorType.WAIT,
        "wait": CursorType.WAIT,
        "crosshair": CursorType.CROSSHAIR,
        "sb_h_double_arrow": CursorType.RESIZE_H,
        "sb_v_double_arrow": CursorType.RESIZE_V,
        "fleur": CursorType.MOVE,
        "not-allowed": CursorType.FORBIDDEN,
    }

    def __init__(self):
        if PLATFORM != "Linux":
            raise RuntimeError("LinuxCursorDetector nur auf Linux verfügbar")

        try:
            self.display = display.Display()
            self.root = self.display.screen().root

            # XFixes Extension für Cursor-Name
            self.xfixes_available = self.display.has_extension('XFIXES')
            if self.xfixes_available:
                xfixes.query_version(self.display)

        except Exception as e:
            log.warning(f"Xlib Init Fehler: {e}")
            self.display = None

    def get_cursor_type(self) -> CursorType:
        """Liest den aktuellen Cursor-Typ via Xlib."""
        if not self.display:
            return CursorType.UNKNOWN

        try:
            if self.xfixes_available:
                # XFixes kann den Cursor-Namen liefern
                # FIX: get_cursor_image() braucht manchmal root window als Parameter
                try:
                    cursor_image = xfixes.get_cursor_image(self.display, self.root)
                except TypeError:
                    # Fallback: Versuche ohne window Parameter
                    try:
                        cursor_image = xfixes.get_cursor_image(self.display)
                    except:
                        return CursorType.UNKNOWN

                cursor_name = getattr(cursor_image, 'name', '').lower()

                for pattern, cursor_type in self.CURSOR_MAPPINGS.items():
                    if pattern in cursor_name:
                        return cursor_type

            return CursorType.UNKNOWN

        except Exception as e:
            log.debug(f"Linux Cursor Detection Fehler: {e}")
            return CursorType.UNKNOWN

    def get_cursor_info(self) -> CursorInfo:
        """Gibt vollständige Cursor-Informationen zurück."""
        cursor_type = self.get_cursor_type()

        if PYAUTOGUI_AVAILABLE:
            pos = pyautogui.position()
        elif self.display:
            try:
                pointer = self.root.query_pointer()
                pos = (pointer.root_x, pointer.root_y)
            except:
                pos = (0, 0)
        else:
            pos = (0, 0)

        return CursorInfo(cursor_type=cursor_type, position=pos)


# ==============================================================================
# FALLBACK CURSOR DETECTION (Screenshot-basiert)
# ==============================================================================

class ScreenshotCursorDetector(CursorDetector):
    """
    Fallback: Erkennt interaktive Elemente durch Screenshot-Vergleich (Hover-Detection).

    Robuster als Cursor-Detection: Vergleicht Screenshots vor/nach Hover.
    Wenn sich UI ändert (Hover-Effekt) = interaktives Element gefunden.
    """

    def __init__(self):
        self.last_screenshot: Optional[Image.Image] = None
        self.last_position: Tuple[int, int] = (0, 0)
        self.hover_threshold = 0.02  # 2% Unterschied = Hover-Effekt

    def _capture_region(self, x: int, y: int, size: int = 100) -> Optional[Image.Image]:
        """Macht Mini-Screenshot um die Position (größer für Hover-Effekte)."""
        if not MSS_AVAILABLE:
            return None

        try:
            with mss.mss() as sct:
                region = {
                    "left": max(0, x - size // 2),
                    "top": max(0, y - size // 2),
                    "width": size,
                    "height": size
                }
                sct_img = sct.grab(region)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        except:
            return None

    def _compare_images(self, img1: Image.Image, img2: Image.Image) -> float:
        """Vergleicht zwei Bilder, gibt Unterschied in % zurück."""
        if img1.size != img2.size:
            return 1.0

        try:
            import numpy as np
            arr1 = np.array(img1)
            arr2 = np.array(img2)
            diff = np.mean(np.abs(arr1 - arr2)) / 255.0
            return diff
        except ImportError:
            # Fallback ohne numpy: Pixel-by-Pixel
            pixels1 = list(img1.getdata())
            pixels2 = list(img2.getdata())
            if len(pixels1) != len(pixels2):
                return 1.0

            total_diff = sum(abs(p1[i] - p2[i]) for p1, p2 in zip(pixels1, pixels2) for i in range(3))
            max_diff = len(pixels1) * 3 * 255
            return total_diff / max_diff if max_diff > 0 else 0.0

    def detect_hover_effect(self, x: int, y: int, wait_time: float = 0.15) -> bool:
        """
        Erkennt ob Hover-Effekt auftritt (= interaktives Element).

        Returns:
            True wenn UI sich ändert (Hover-Effekt erkannt)
        """
        import time

        # Screenshot vor Hover
        before = self._capture_region(x, y)
        if not before:
            return False

        # Warte für Hover-Effekt
        time.sleep(wait_time)

        # Screenshot nach Hover
        after = self._capture_region(x, y)
        if not after:
            return False

        # Vergleiche
        diff = self._compare_images(before, after)
        is_interactive = diff > self.hover_threshold

        if is_interactive:
            log.debug(f"Hover-Effekt erkannt bei ({x}, {y}): {diff*100:.1f}% Änderung")

        return is_interactive

    def get_cursor_type(self) -> CursorType:
        """
        Fallback: Nutzt Hover-Detection statt Cursor-Typ.
        Gibt UNKNOWN zurück, aber detect_hover_effect() ist die Hauptmethode.
        """
        return CursorType.UNKNOWN

    def get_cursor_info(self) -> CursorInfo:
        """Gibt Cursor-Info mit Position zurück."""
        if PYAUTOGUI_AVAILABLE:
            pos = pyautogui.position()
        else:
            pos = (0, 0)

        return CursorInfo(
            cursor_type=CursorType.UNKNOWN,
            position=pos,
            confidence=0.7  # Mittlere Konfidenz für Screenshot-basiert
        )


# ==============================================================================
# CURSOR DETECTOR FACTORY
# ==============================================================================

def get_cursor_detector() -> CursorDetector:
    """Factory: Gibt den passenden CursorDetector für das System zurück."""

    if PLATFORM == "Windows" and CURSOR_DETECTION_AVAILABLE:
        try:
            return WindowsCursorDetector()
        except Exception as e:
            log.warning(f"Windows Detector nicht verfügbar: {e}")

    elif PLATFORM == "Linux" and CURSOR_DETECTION_AVAILABLE:
        try:
            return LinuxCursorDetector()
        except Exception as e:
            log.warning(f"Linux Detector nicht verfügbar: {e}")

    log.info("Nutze Fallback Screenshot-basierte Detection")
    return ScreenshotCursorDetector()


# ==============================================================================
# MOUSE FEEDBACK ENGINE
# ==============================================================================

@dataclass
class MoveResult:
    """Ergebnis einer Mausbewegung."""
    success: bool
    final_position: Tuple[int, int]
    cursor_type: CursorType
    found_interactive: bool
    steps_taken: int
    path: List[Tuple[int, int]] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "x": self.final_position[0],
            "y": self.final_position[1],
            "cursor_type": self.cursor_type.value,
            "found_interactive": self.found_interactive,
            "is_text_field": self.cursor_type == CursorType.IBEAM,
            "is_clickable": self.cursor_type in [CursorType.HAND, CursorType.IBEAM],
            "steps_taken": self.steps_taken,
            "message": self.message
        }


class MouseFeedbackEngine:
    """
    Engine für Mausbewegung mit kontinuierlichem Cursor-Feedback.

    Ermöglicht "Hand-Auge-Koordination" für präzise UI-Navigation.
    """

    def __init__(self):
        self.detector = get_cursor_detector()
        self.monitor_offset_x = 0
        self.monitor_offset_y = 0
        self._load_monitor_offset()

        log.info(f"MouseFeedbackEngine initialisiert")
        log.info(f"  Platform: {PLATFORM}")
        log.info(f"  Detector: {self.detector.__class__.__name__}")
        log.info(f"  PyAutoGUI: {PYAUTOGUI_AVAILABLE}")

    def _load_monitor_offset(self):
        """Lädt Monitor-Offset für Multi-Monitor Setup."""
        if not MSS_AVAILABLE:
            return

        try:
            with mss.mss() as sct:
                if ACTIVE_MONITOR < len(sct.monitors):
                    monitor = sct.monitors[ACTIVE_MONITOR]
                else:
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

                self.monitor_offset_x = monitor["left"]
                self.monitor_offset_y = monitor["top"]
                log.debug(f"Monitor Offset: ({self.monitor_offset_x}, {self.monitor_offset_y})")
        except Exception as e:
            log.warning(f"Monitor Offset Fehler: {e}")

    def get_current_position(self) -> Tuple[int, int]:
        """Gibt aktuelle Mausposition zurück."""
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.position()
        return (0, 0)

    def get_cursor_info(self) -> CursorInfo:
        """Gibt aktuelle Cursor-Informationen zurück."""
        return self.detector.get_cursor_info()

    async def move_to(
        self,
        target_x: int,
        target_y: int,
        step_size: int = MOVE_STEP_SIZE,
        stop_on_interactive: bool = True,
        max_steps: int = 100
    ) -> MoveResult:
        """
        Bewegt die Maus schrittweise zum Ziel mit kontinuierlichem Feedback.

        Args:
            target_x: Ziel X-Koordinate
            target_y: Ziel Y-Koordinate
            step_size: Pixel pro Bewegungsschritt
            stop_on_interactive: Bei interaktivem Element stoppen?
            max_steps: Maximale Schritte

        Returns:
            MoveResult mit finaler Position und Cursor-Info
        """
        if not PYAUTOGUI_AVAILABLE:
            return MoveResult(
                success=False,
                final_position=(0, 0),
                cursor_type=CursorType.UNKNOWN,
                found_interactive=False,
                steps_taken=0,
                message="PyAutoGUI nicht verfügbar"
            )

        start_x, start_y = self.get_current_position()
        current_x, current_y = float(start_x), float(start_y)

        # Distanz berechnen
        dx = target_x - start_x
        dy = target_y - start_y
        distance = (dx**2 + dy**2) ** 0.5

        if distance < 1:
            # Schon am Ziel
            cursor_info = self.get_cursor_info()
            return MoveResult(
                success=True,
                final_position=(target_x, target_y),
                cursor_type=cursor_info.cursor_type,
                found_interactive=cursor_info.is_interactive(),
                steps_taken=0,
                message="Bereits am Ziel"
            )

        # Anzahl Schritte berechnen
        num_steps = max(1, int(distance / step_size))
        num_steps = min(num_steps, max_steps)

        step_dx = dx / num_steps
        step_dy = dy / num_steps

        path: List[Tuple[int, int]] = [(start_x, start_y)]
        found_interactive = False

        log.debug(f"Bewege von ({start_x}, {start_y}) nach ({target_x}, {target_y}) in {num_steps} Schritten")

        for step in range(num_steps):
            # Nächste Position
            current_x += step_dx
            current_y += step_dy

            new_x = int(current_x)
            new_y = int(current_y)

            # Bewegen
            pyautogui.moveTo(new_x, new_y, _pause=False)
            path.append((new_x, new_y))

            # Kurze Pause für System-Update
            await asyncio.sleep(MOVE_STEP_DELAY)

            # Cursor-Typ prüfen
            cursor_info = self.get_cursor_info()

            if stop_on_interactive and cursor_info.is_interactive():
                found_interactive = True
                log.info(f"Interaktives Element bei ({new_x}, {new_y}): {cursor_info.cursor_type.value}")

                return MoveResult(
                    success=True,
                    final_position=(new_x, new_y),
                    cursor_type=cursor_info.cursor_type,
                    found_interactive=True,
                    steps_taken=step + 1,
                    path=path,
                    message=f"Interaktives Element gefunden: {cursor_info.cursor_type.value}"
                )

        # Ziel erreicht
        pyautogui.moveTo(target_x, target_y, _pause=False)
        await asyncio.sleep(HOVER_WAIT_TIME)  # Warten auf Hover-Effekt

        cursor_info = self.get_cursor_info()

        return MoveResult(
            success=True,
            final_position=(target_x, target_y),
            cursor_type=cursor_info.cursor_type,
            found_interactive=cursor_info.is_interactive(),
            steps_taken=num_steps,
            path=path,
            message="Ziel erreicht"
        )

    async def search_in_region(
        self,
        center_x: int,
        center_y: int,
        radius: int = 50,
        target_cursor: Optional[CursorType] = None,
        spiral: bool = True
    ) -> MoveResult:
        """
        Sucht in einer Region nach einem interaktiven Element.

        Nutzt Spiral-Scan vom Zentrum nach außen.

        Args:
            center_x: Zentrum X
            center_y: Zentrum Y
            radius: Suchradius in Pixeln
            target_cursor: Spezifischer Cursor-Typ suchen (None = jeder interaktive)
            spiral: Spiral-Scan (True) oder Grid-Scan (False)

        Returns:
            MoveResult wenn gefunden
        """
        if not PYAUTOGUI_AVAILABLE:
            return MoveResult(
                success=False,
                final_position=(center_x, center_y),
                cursor_type=CursorType.UNKNOWN,
                found_interactive=False,
                steps_taken=0,
                message="PyAutoGUI nicht verfügbar"
            )

        log.info(f"Suche in Region ({center_x}, {center_y}) mit Radius {radius}")

        # Spiral-Punkte generieren
        if spiral:
            points = self._generate_spiral_points(center_x, center_y, radius)
        else:
            points = self._generate_grid_points(center_x, center_y, radius)

        steps = 0
        for x, y in points:
            pyautogui.moveTo(x, y, _pause=False)
            await asyncio.sleep(MOVE_STEP_DELAY * 2)  # Etwas länger warten

            cursor_info = self.get_cursor_info()
            steps += 1

            # Prüfen ob gefunden via Cursor-Typ
            if target_cursor:
                if cursor_info.cursor_type == target_cursor:
                    log.info(f"Gefunden: {target_cursor.value} bei ({x}, {y})")
                    return MoveResult(
                        success=True,
                        final_position=(x, y),
                        cursor_type=cursor_info.cursor_type,
                        found_interactive=True,
                        steps_taken=steps,
                        message=f"Ziel-Cursor gefunden: {target_cursor.value}"
                    )
            elif cursor_info.is_interactive():
                log.info(f"Interaktiv bei ({x}, {y}): {cursor_info.cursor_type.value}")
                return MoveResult(
                    success=True,
                    final_position=(x, y),
                    cursor_type=cursor_info.cursor_type,
                    found_interactive=True,
                    steps_taken=steps,
                    message=f"Interaktives Element: {cursor_info.cursor_type.value}"
                )

            # FALLBACK: Screenshot-basierte Hover-Detection (wenn Cursor UNKNOWN)
            if cursor_info.cursor_type == CursorType.UNKNOWN:
                if isinstance(self.detector, ScreenshotCursorDetector):
                    if self.detector.detect_hover_effect(x, y, wait_time=0.1):
                        log.info(f"Hover-Effekt erkannt bei ({x}, {y})")
                        return MoveResult(
                            success=True,
                            final_position=(x, y),
                            cursor_type=CursorType.HAND,  # Assume clickable
                            found_interactive=True,
                            steps_taken=steps,
                            message="Interaktives Element via Hover-Detection gefunden"
                        )

        # Nichts gefunden - zurück zum Zentrum
        pyautogui.moveTo(center_x, center_y, _pause=False)
        cursor_info = self.get_cursor_info()

        return MoveResult(
            success=False,
            final_position=(center_x, center_y),
            cursor_type=cursor_info.cursor_type,
            found_interactive=False,
            steps_taken=steps,
            message="Kein interaktives Element in Region gefunden"
        )

    def _generate_spiral_points(
        self,
        cx: int,
        cy: int,
        radius: int,
        step: int = 10
    ) -> List[Tuple[int, int]]:
        """Generiert Spiral-Punkte vom Zentrum nach außen."""
        points = [(cx, cy)]  # Start im Zentrum

        r = step
        while r <= radius:
            # Punkte auf dem Kreis mit Radius r
            num_points = max(4, int(2 * 3.14159 * r / step))
            for i in range(num_points):
                angle = 2 * 3.14159 * i / num_points
                x = int(cx + r * __import__('math').cos(angle))
                y = int(cy + r * __import__('math').sin(angle))
                points.append((x, y))
            r += step

        return points

    def _generate_grid_points(
        self,
        cx: int,
        cy: int,
        radius: int,
        step: int = 15
    ) -> List[Tuple[int, int]]:
        """Generiert Grid-Punkte in der Region."""
        points = []

        for dy in range(-radius, radius + 1, step):
            for dx in range(-radius, radius + 1, step):
                if dx*dx + dy*dy <= radius*radius:  # Nur innerhalb Kreis
                    points.append((cx + dx, cy + dy))

        # Nach Distanz zum Zentrum sortieren
        points.sort(key=lambda p: (p[0]-cx)**2 + (p[1]-cy)**2)
        return points

    async def hover_and_verify(
        self,
        x: int,
        y: int,
        wait_time: float = HOVER_WAIT_TIME
    ) -> CursorInfo:
        """
        Bewegt zu Position und wartet auf Hover-Effekt.

        Returns:
            CursorInfo nach Hover-Zeit
        """
        if PYAUTOGUI_AVAILABLE:
            pyautogui.moveTo(x, y, _pause=False)

        await asyncio.sleep(wait_time)
        return self.get_cursor_info()

    def click_at_current(self):
        """Klickt an aktueller Position."""
        if PYAUTOGUI_AVAILABLE:
            pyautogui.click(_pause=False)

    async def click_at(self, x: int, y: int, verify: bool = True) -> Dict[str, Any]:
        """
        Bewegt zu Position und klickt.

        Args:
            x: X-Koordinate
            y: Y-Koordinate
            verify: Cursor vor Klick verifizieren?

        Returns:
            Klick-Ergebnis mit Cursor-Info
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "PyAutoGUI nicht verfügbar"}

        # Zu Position bewegen
        result = await self.move_to(x, y, stop_on_interactive=False)

        if verify:
            cursor_info = await self.hover_and_verify(x, y)
        else:
            cursor_info = self.get_cursor_info()

        # Klicken
        pyautogui.click(x, y, _pause=False)

        return {
            "success": True,
            "x": x,
            "y": y,
            "cursor_before_click": cursor_info.cursor_type.value,
            "was_interactive": cursor_info.is_interactive(),
            "was_text_field": cursor_info.is_text_input()
        }


# ==============================================================================
# GLOBALE ENGINE INSTANZ
# ==============================================================================

_engine: Optional[MouseFeedbackEngine] = None

def get_engine() -> MouseFeedbackEngine:
    """Gibt die globale Engine-Instanz zurück."""
    global _engine
    if _engine is None:
        _engine = MouseFeedbackEngine()
    return _engine


# ==============================================================================
# JSON-RPC METHODEN
# ==============================================================================

@tool(
    name="move_with_feedback",
    description="Bewegt die Maus schrittweise zum Ziel mit Cursor-Feedback. Stoppt automatisch bei interaktiven Elementen (Textfeld, Link, Button).",
    parameters=[
        P("target_x", "integer", "Ziel X-Koordinate"),
        P("target_y", "integer", "Ziel Y-Koordinate"),
        P("stop_on_interactive", "boolean", "Bei interaktivem Element stoppen?", required=False, default=True),
        P("step_size", "integer", "Pixel pro Bewegungsschritt", required=False, default=30),
    ],
    capabilities=["mouse", "feedback"],
    category=C.MOUSE
)
async def move_with_feedback(
    target_x: int,
    target_y: int,
    stop_on_interactive: bool = True,
    step_size: int = MOVE_STEP_SIZE
) -> dict:
    """
    Bewegt die Maus schrittweise zum Ziel mit Cursor-Feedback.

    Stoppt automatisch bei interaktiven Elementen (Textfeld, Link, Button).
    """
    try:
        engine = get_engine()
        result = await engine.move_to(
            target_x, target_y,
            step_size=step_size,
            stop_on_interactive=stop_on_interactive
        )
        return result.to_dict()
    except Exception as e:
        log.error(f"move_with_feedback Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="search_for_element",
    description="Sucht in einer Region nach einem interaktiven Element. Nutzt Spiral-Scan vom Zentrum nach außen.",
    parameters=[
        P("center_x", "integer", "Zentrum X-Koordinate"),
        P("center_y", "integer", "Zentrum Y-Koordinate"),
        P("radius", "integer", "Suchradius in Pixeln", required=False, default=50),
        P("element_type", "string", "Element-Typ: text_field, clickable, any", required=False, default="any"),
    ],
    capabilities=["mouse", "feedback"],
    category=C.MOUSE
)
async def search_for_element(
    center_x: int,
    center_y: int,
    radius: int = 50,
    element_type: str = "any"
) -> dict:
    """
    Sucht in einer Region nach einem interaktiven Element.

    Nutzt Spiral-Scan vom Zentrum nach außen.
    """
    try:
        engine = get_engine()

        # Element-Typ zu Cursor-Typ mappen
        target_cursor = None
        if element_type == "text_field":
            target_cursor = CursorType.IBEAM
        elif element_type == "clickable":
            target_cursor = CursorType.HAND

        result = await engine.search_in_region(
            center_x, center_y,
            radius=radius,
            target_cursor=target_cursor
        )

        response = result.to_dict()
        response["found"] = result.found_interactive
        return response

    except Exception as e:
        log.error(f"search_for_element Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="get_cursor_at_position",
    description="Gibt den Cursor-Typ an einer Position zurück. Wenn keine Position angegeben, wird die aktuelle Position genutzt.",
    parameters=[
        P("x", "integer", "X-Koordinate", required=False, default=None),
        P("y", "integer", "Y-Koordinate", required=False, default=None),
    ],
    capabilities=["mouse", "feedback"],
    category=C.MOUSE
)
async def get_cursor_at_position(x: int = None, y: int = None) -> dict:
    """
    Gibt den Cursor-Typ an einer Position zurück.

    Wenn keine Position angegeben, wird die aktuelle Position genutzt.
    """
    try:
        engine = get_engine()

        if x is not None and y is not None:
            cursor_info = await engine.hover_and_verify(x, y)
        else:
            cursor_info = engine.get_cursor_info()

        return {
            "x": cursor_info.position[0],
            "y": cursor_info.position[1],
            "cursor_type": cursor_info.cursor_type.value,
            "is_text_field": cursor_info.is_text_input(),
            "is_clickable": cursor_info.is_clickable(),
            "is_interactive": cursor_info.is_interactive()
        }

    except Exception as e:
        log.error(f"get_cursor_at_position Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="click_with_verification",
    description="Bewegt zu Position, verifiziert Cursor, dann klickt.",
    parameters=[
        P("x", "integer", "X-Koordinate"),
        P("y", "integer", "Y-Koordinate"),
    ],
    capabilities=["mouse", "feedback"],
    category=C.MOUSE
)
async def click_with_verification(x: int, y: int) -> dict:
    """
    Bewegt zu Position, verifiziert Cursor, dann klickt.
    """
    try:
        engine = get_engine()
        result = await engine.click_at(x, y, verify=True)
        return result
    except Exception as e:
        log.error(f"click_with_verification Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="find_text_field_nearby",
    description="Sucht nach einem Textfeld in der Nähe einer Position. Nützlich wenn SoM ungenaue Koordinaten liefert.",
    parameters=[
        P("x", "integer", "Ungefähre X-Koordinate"),
        P("y", "integer", "Ungefähre Y-Koordinate"),
        P("radius", "integer", "Suchradius", required=False, default=80),
    ],
    capabilities=["mouse", "feedback"],
    category=C.MOUSE
)
async def find_text_field_nearby(x: int, y: int, radius: int = 80) -> dict:
    """
    Sucht nach einem Textfeld in der Nähe einer Position.

    Nützlich wenn SoM ungenaue Koordinaten liefert.
    """
    try:
        engine = get_engine()
        result = await engine.search_in_region(
            x, y,
            radius=radius,
            target_cursor=CursorType.IBEAM
        )

        if result.found_interactive:
            return {
                "found": True,
                "x": result.final_position[0],
                "y": result.final_position[1],
                "cursor_type": result.cursor_type.value,
                "instruction": f"Nutze click_at({result.final_position[0]}, {result.final_position[1]}) dann type_text()"
            }
        else:
            return {
                "found": False,
                "message": f"Kein Textfeld in Radius {radius}px um ({x}, {y}) gefunden",
                "suggestion": "Versuche scan_ui_elements() oder find_text_coordinates()"
            }

    except Exception as e:
        log.error(f"find_text_field_nearby Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="get_mouse_position",
    description="Gibt die aktuelle Mausposition und den Cursor-Typ zurück.",
    parameters=[],
    capabilities=["mouse", "feedback"],
    category=C.MOUSE
)
def get_mouse_position() -> dict:
    """
    Gibt die aktuelle Mausposition zurück.
    """
    try:
        engine = get_engine()
        pos = engine.get_current_position()
        cursor_info = engine.get_cursor_info()

        return {
            "x": pos[0],
            "y": pos[1],
            "cursor_type": cursor_info.cursor_type.value
        }
    except Exception as e:
        raise Exception(str(e))


# ==============================================================================
# CLI TEST
# ==============================================================================

async def _test():
    """Test-Funktion für CLI."""
    print("\nMouse Feedback Tool - Test")
    print("=" * 50)

    engine = get_engine()

    # Aktuelle Position
    pos = engine.get_current_position()
    print(f"Aktuelle Position: {pos}")

    cursor = engine.get_cursor_info()
    print(f"Cursor-Typ: {cursor.cursor_type.value}")

    # Test: Bewege zum Zentrum des Bildschirms
    print("\nBewege zur Mitte des Bildschirms...")
    result = await engine.move_to(960, 540, stop_on_interactive=True)
    print(f"Ergebnis: {result.to_dict()}")

    print("\nTest abgeschlossen")


if __name__ == "__main__":
    import asyncio

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(_test())
    else:
        print("\nMouse Feedback Tool v1.0")
        print(f"   Platform: {PLATFORM}")
        print(f"   PyAutoGUI: {PYAUTOGUI_AVAILABLE}")
        print(f"   Cursor Detection: {CURSOR_DETECTION_AVAILABLE}")
        print(f"   MSS: {MSS_AVAILABLE}")
        print("\nUsage:")
        print("  python tool.py test  - Führt Test aus")
        print("\nAls MCP Tool:")
        print("  - move_with_feedback(x, y)")
        print("  - search_for_element(x, y, radius)")
        print("  - find_text_field_nearby(x, y)")

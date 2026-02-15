# ~/dev/timus/tools/mouse_tool_fixed.py
"""
Korrigiertes Mouse-Tool mit einheitlicher Monitor-Logik über monitor_config.py.
- Koordinaten-Logging für Debug
- Keine hartcodierten Werte
- Relative → Absolute Umwandlung zentral
"""

import logging
import asyncio
import os
from typing import Tuple
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from monitor_config import convert_relative_to_absolute, get_monitor_bounds

# PyAutoGUI Import mit Fehlerbehandlung
try:
    import pyautogui
except Exception as e:
    pyautogui = None
    _import_error = e
else:
    _import_error = None

log = logging.getLogger(__name__)

def _ensure_pyautogui_ok():
    """Prüft PyAutoGUI-Verfügbarkeit."""
    if pyautogui is None:
        raise Exception(f"PyAutoGUI nicht verfügbar: {_import_error}")
    try:
        pyautogui.size()
    except Exception as e:
        raise Exception(f"Kein GUI-Display erreichbar: {e}")
    return None

def _clamp_coords(x: int, y: int) -> Tuple[int, int]:
    """Begrenzt Koordinaten auf primären Bildschirm."""
    width, height = pyautogui.size()
    return max(0, min(int(x), width - 1)), max(0, min(int(y), height - 1))

# Synchrone Worker (in Threads ausführen)
def _move_sync(x: int, y: int, duration: float):
    pyautogui.FAILSAFE = False  # Wir prüfen Position vorher
    x, y = _clamp_coords(x, y)
    pyautogui.moveTo(x, y, duration=max(0.0, duration))
    pyautogui.FAILSAFE = True  # Wieder aktivieren

def _click_sync(x: int, y: int, button: str):
    pyautogui.FAILSAFE = False  # Wir prüfen Position vorher
    x, y = _clamp_coords(x, y)
    pyautogui.moveTo(x, y, duration=0.05)
    pyautogui.click(x=x, y=y, button=button)
    pyautogui.FAILSAFE = True  # Wieder aktivieren

def _ensure_safe_mouse_position():
    """Prüft ob Maus in einer Ecke ist und bewegt sie in eine sichere Position."""
    width, height = pyautogui.size()
    x, y = pyautogui.position()

    # Grenzen für Ecken-Bereich (50px von jedem Rand)
    corner_threshold = 50

    # Wenn in einer Ecke, in die Mitte bewegen
    if x < corner_threshold and y < corner_threshold:
        pyautogui.moveTo(width // 2, height // 2, duration=0.05)
        return True
    if x > width - corner_threshold and y < corner_threshold:
        pyautogui.moveTo(width // 2, height // 2, duration=0.05)
        return True
    if x < corner_threshold and y > height - corner_threshold:
        pyautogui.moveTo(width // 2, height // 2, duration=0.05)
        return True
    if x > width - corner_threshold and y > height - corner_threshold:
        pyautogui.moveTo(width // 2, height // 2, duration=0.05)
        return True
    return False

def _type_write(text: str, press_enter: bool):
    """Direktes Tippen Zeichen für Zeichen (robust, funktioniert ohne perfekten Fokus)."""
    pyautogui.FAILSAFE = False  # Deaktivieren, da wir Position prüfen
    _ensure_safe_mouse_position()
    # pyautogui.write() unterstützt Unicode besser als typewrite()
    pyautogui.write(text, interval=0.03)
    if press_enter:
        pyautogui.press('enter')
    pyautogui.FAILSAFE = True  # Wieder aktivieren

def _type_sync(text: str, press_enter: bool):
    pyautogui.FAILSAFE = False  # Deaktivieren, da wir Position prüfen
    _ensure_safe_mouse_position()
    # Zwischenablage-Methode (schnell, robust für alle Layouts)
    try:
        subprocess = __import__("subprocess")
        process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE)
        process.communicate(text.encode('utf-8'))
    except Exception:
        try:
            process = subprocess.Popen(['xsel', '--clipboard', '--input'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
        except Exception:
            # Fallback zu direktem Tippen
            _type_write(text, press_enter)
            pyautogui.FAILSAFE = True
            return
    pyautogui.hotkey('ctrl', 'v')
    if press_enter:
        pyautogui.press('enter')
    pyautogui.FAILSAFE = True  # Wieder aktivieren

def _scroll_sync(amount: int):
    pyautogui.FAILSAFE = False  # Wir prüfen Position vorher
    pyautogui.scroll(int(amount))
    pyautogui.FAILSAFE = True  # Wieder aktivieren

def _click_and_focus_sync(x: int, y: int):
    """Klickt mehrfach bis Fokus gewährleistet (für hartnäckige Felder wie ChatGPT)."""
    pyautogui.FAILSAFE = False  # Wir prüfen Position vorher
    x, y = _clamp_coords(x, y)

    # Mehrfach-Klick-Strategie für schwierige Felder
    pyautogui.moveTo(x, y, duration=0.1)
    pyautogui.click(x=x, y=y, clicks=1)  # Erster Klick
    import time
    time.sleep(0.1)
    pyautogui.click(x=x, y=y, clicks=1)  # Sicherheits-Klick
    time.sleep(0.1)
    pyautogui.FAILSAFE = True  # Wieder aktivieren

# Asynchrone RPC-Methoden
@tool(
    name="move_mouse",
    description="Bewegt die Maus zu den angegebenen relativen Koordinaten mit einheitlicher Monitor-Logik.",
    parameters=[
        P("x", "integer", "X-Koordinate (relativ)"),
        P("y", "integer", "Y-Koordinate (relativ)"),
        P("duration", "number", "Dauer der Bewegung in Sekunden", required=False, default=0.05),
    ],
    capabilities=["mouse", "interaction"],
    category=C.MOUSE
)
async def move_mouse(x: int, y: int, duration: float = 0.05) -> dict:
    _ensure_pyautogui_ok()
    abs_x, abs_y = convert_relative_to_absolute(x, y)
    log.info(f"move_mouse: relativ ({x},{y}) → absolut ({abs_x},{abs_y})")
    try:
        await asyncio.to_thread(_move_sync, abs_x, abs_y, duration)
        return {"status": "moved", "absolute": (abs_x, abs_y)}
    except pyautogui.FailSafeException as e:
        log.warning(f"FailSafeException in move_mouse: {e} - Maus in sicherer Position...")
        _ensure_safe_mouse_position()
        try:
            await asyncio.to_thread(_move_sync, abs_x, abs_y, duration)
            return {"status": "moved", "absolute": (abs_x, abs_y), "retry": True}
        except Exception as e2:
            raise Exception(f"Move-Operation fehlgeschlagen: {e2}")
    except Exception as e:
        raise Exception(f"Move-Operation fehlgeschlagen: {e}")

@tool(
    name="click_at",
    description="Klickt an den angegebenen relativen Koordinaten mit der gewählten Maustaste.",
    parameters=[
        P("x", "integer", "X-Koordinate (relativ)"),
        P("y", "integer", "Y-Koordinate (relativ)"),
        P("button_name", "string", "Maustaste: left, right, middle", required=False, default="left"),
    ],
    capabilities=["mouse", "interaction"],
    category=C.MOUSE
)
async def click_at(x: int, y: int, button_name: str = 'left') -> dict:
    _ensure_pyautogui_ok()
    abs_x, abs_y = convert_relative_to_absolute(x, y)
    log.info(f"click_at '{button_name}' bei relativ ({x},{y}) → absolut ({abs_x},{abs_y})")
    try:
        await asyncio.to_thread(_click_sync, abs_x, abs_y, button_name)
        return {"status": "clicked", "absolute": (abs_x, abs_y), "button": button_name}
    except pyautogui.FailSafeException as e:
        log.warning(f"FailSafeException in click_at: {e} - Maus in sicherer Position...")
        _ensure_safe_mouse_position()
        try:
            await asyncio.to_thread(_click_sync, abs_x, abs_y, button_name)
            return {"status": "clicked", "absolute": (abs_x, abs_y), "button": button_name, "retry": True}
        except Exception as e2:
            raise Exception(f"Click-Operation fehlgeschlagen: {e2}")
    except Exception as e:
        raise Exception(f"Click-Operation fehlgeschlagen: {e}")

@tool(
    name="type_text",
    description="Tippt Text ein. Unterstützt 3 Methoden: auto (Zwischenablage mit Fallback), clipboard (Ctrl+V), write (Zeichen für Zeichen).",
    parameters=[
        P("text_to_type", "string", "Der einzutippende Text"),
        P("press_enter_after", "boolean", "Enter-Taste nach dem Tippen drücken", required=False, default=False),
        P("method", "string", "Eingabemethode: auto, clipboard, write", required=False, default="auto"),
    ],
    capabilities=["mouse", "interaction"],
    category=C.MOUSE
)
async def type_text(text_to_type: str, press_enter_after: bool = False, method: str = "auto") -> dict:
    """
    Tippt Text ein. Unterstützt 3 Methoden:
    - "auto" (default): Versucht Zwischenablage, Fallback zu write
    - "clipboard": Zwischenablage + Ctrl+V (schnell, für Umlaute)
    - "write": Direktes Tippen Zeichen für Zeichen (robust, langsam)
    """
    _ensure_pyautogui_ok()
    preview = text_to_type[:40] + "…" if len(text_to_type) > 40 else text_to_type
    log.info(f"type_text: '{preview}' (Enter: {press_enter_after}, Methode: {method})")

    # Methode wählen mit Fehlerbehandlung
    try:
        if method == "write":
            await asyncio.to_thread(_type_write, text_to_type, press_enter_after)
        else:
            await asyncio.to_thread(_type_sync, text_to_type, press_enter_after)
        return {"status": "typed", "length": len(text_to_type), "enter": press_enter_after, "method": method}
    except pyautogui.FailSafeException as e:
        log.warning(f"FailSafeException gefangen: {e} - Versuche erneut...")
        # Retry nach sicherer Position
        await asyncio.sleep(0.2)
        try:
            if method == "write":
                await asyncio.to_thread(_type_write, text_to_type, press_enter_after)
            else:
                await asyncio.to_thread(_type_sync, text_to_type, press_enter_after)
            return {"status": "typed", "length": len(text_to_type), "enter": press_enter_after, "method": method, "retry": True}
        except Exception as e2:
            log.error(f"Retry fehlgeschlagen: {e2}")
            raise Exception(f"Typ-Operation fehlgeschlagen: {e2}")
    except Exception as e:
        log.error(f"Typ-Operation fehlgeschlagen: {e}")
        raise Exception(f"Typ-Operation fehlgeschlagen: {e}")

@tool(
    name="scroll",
    description="Scrollt den Bildschirm um den angegebenen Betrag.",
    parameters=[
        P("amount", "integer", "Scroll-Betrag (positiv = hoch, negativ = runter)"),
    ],
    capabilities=["mouse", "interaction"],
    category=C.MOUSE
)
async def scroll(amount: int) -> dict:
    _ensure_pyautogui_ok()
    log.info(f"scroll: {amount}")
    try:
        await asyncio.to_thread(_scroll_sync, amount)
        return {"status": "scrolled", "amount": amount}
    except pyautogui.FailSafeException as e:
        log.warning(f"FailSafeException in scroll: {e} - Maus in sicherer Position...")
        _ensure_safe_mouse_position()
        try:
            await asyncio.to_thread(_scroll_sync, amount)
            return {"status": "scrolled", "amount": amount, "retry": True}
        except Exception as e2:
            raise Exception(f"Scroll-Operation fehlgeschlagen: {e2}")
    except Exception as e:
        raise Exception(f"Scroll-Operation fehlgeschlagen: {e}")

@tool(
    name="click_and_focus",
    description="Robuster Klick mit Fokus-Garantie (mehrfache Klicks). Für schwierige Felder wie ChatGPT, die normalen Klick ignorieren.",
    parameters=[
        P("x", "integer", "X-Koordinate (relativ)"),
        P("y", "integer", "Y-Koordinate (relativ)"),
    ],
    capabilities=["mouse", "interaction"],
    category=C.MOUSE
)
async def click_and_focus(x: int, y: int) -> dict:
    """
    Robuster Klick mit Fokus-Garantie (mehrfache Klicks).
    Für schwierige Felder wie ChatGPT, die normalen Klick ignorieren.
    """
    _ensure_pyautogui_ok()
    abs_x, abs_y = convert_relative_to_absolute(x, y)
    log.info(f"click_and_focus: relativ ({x},{y}) → absolut ({abs_x},{abs_y})")
    try:
        await asyncio.to_thread(_click_and_focus_sync, abs_x, abs_y)
        return {"status": "clicked_and_focused", "absolute": (abs_x, abs_y), "clicks": 2}
    except pyautogui.FailSafeException as e:
        log.warning(f"FailSafeException in click_and_focus: {e} - Maus in sicherer Position...")
        _ensure_safe_mouse_position()
        try:
            await asyncio.to_thread(_click_and_focus_sync, abs_x, abs_y)
            return {"status": "clicked_and_focused", "absolute": (abs_x, abs_y), "clicks": 2, "retry": True}
        except Exception as e2:
            raise Exception(f"Click_and_focus fehlgeschlagen: {e2}")
    except Exception as e:
        raise Exception(f"Click_and_focus fehlgeschlagen: {e}")

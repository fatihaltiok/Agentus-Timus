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
from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool
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
        return Error(code=-32000, message=f"PyAutoGUI nicht verfügbar: {_import_error}")
    try:
        pyautogui.size()
    except Exception as e:
        return Error(code=-32001, message=f"Kein GUI-Display erreichbar: {e}")
    return None

def _clamp_coords(x: int, y: int) -> Tuple[int, int]:
    """Begrenzt Koordinaten auf primären Bildschirm."""
    width, height = pyautogui.size()
    return max(0, min(int(x), width - 1)), max(0, min(int(y), height - 1))

# Synchrone Worker (in Threads ausführen)
def _move_sync(x: int, y: int, duration: float):
    pyautogui.FAILSAFE = True
    x, y = _clamp_coords(x, y)
    pyautogui.moveTo(x, y, duration=max(0.0, duration))

def _click_sync(x: int, y: int, button: str):
    pyautogui.FAILSAFE = True
    x, y = _clamp_coords(x, y)
    pyautogui.moveTo(x, y, duration=0.05)
    pyautogui.click(x=x, y=y, button=button)

def _type_write(text: str, press_enter: bool):
    """Direktes Tippen Zeichen für Zeichen (robust, funktioniert ohne perfekten Fokus)."""
    pyautogui.FAILSAFE = True
    # pyautogui.write() unterstützt Unicode besser als typewrite()
    pyautogui.write(text, interval=0.03)
    if press_enter:
        pyautogui.press('enter')

def _type_sync(text: str, press_enter: bool):
    pyautogui.FAILSAFE = True
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
            return
    pyautogui.hotkey('ctrl', 'v')
    if press_enter:
        pyautogui.press('enter')

def _scroll_sync(amount: int):
    pyautogui.FAILSAFE = True
    pyautogui.scroll(int(amount))

def _click_and_focus_sync(x: int, y: int):
    """Klickt mehrfach bis Fokus gewährleistet (für hartnäckige Felder wie ChatGPT)."""
    pyautogui.FAILSAFE = True
    x, y = _clamp_coords(x, y)

    # Mehrfach-Klick-Strategie für schwierige Felder
    pyautogui.moveTo(x, y, duration=0.1)
    pyautogui.click(x=x, y=y, clicks=1)  # Erster Klick
    import time
    time.sleep(0.1)
    pyautogui.click(x=x, y=y, clicks=1)  # Sicherheits-Klick
    time.sleep(0.1)

# Asynchrone RPC-Methoden
@method
async def move_mouse(x: int, y: int, duration: float = 0.05):
    ok = _ensure_pyautogui_ok()
    if ok: return ok
    abs_x, abs_y = convert_relative_to_absolute(x, y)
    log.info(f"move_mouse: relativ ({x},{y}) → absolut ({abs_x},{abs_y})")
    await asyncio.to_thread(_move_sync, abs_x, abs_y, duration)
    return Success({"status": "moved", "absolute": (abs_x, abs_y)})

@method
async def click_at(x: int, y: int, button_name: str = 'left'):
    ok = _ensure_pyautogui_ok()
    if ok: return ok
    abs_x, abs_y = convert_relative_to_absolute(x, y)
    log.info(f"click_at '{button_name}' bei relativ ({x},{y}) → absolut ({abs_x},{abs_y})")
    await asyncio.to_thread(_click_sync, abs_x, abs_y, button_name)
    return Success({"status": "clicked", "absolute": (abs_x, abs_y), "button": button_name})

@method
async def type_text(text_to_type: str, press_enter_after: bool = False, method: str = "auto"):
    """
    Tippt Text ein. Unterstützt 3 Methoden:
    - "auto" (default): Versucht Zwischenablage, Fallback zu write
    - "clipboard": Zwischenablage + Ctrl+V (schnell, für Umlaute)
    - "write": Direktes Tippen Zeichen für Zeichen (robust, langsam)
    """
    ok = _ensure_pyautogui_ok()
    if ok: return ok
    preview = text_to_type[:40] + "…" if len(text_to_type) > 40 else text_to_type
    log.info(f"type_text: '{preview}' (Enter: {press_enter_after}, Methode: {method})")

    # Methode wählen
    if method == "write":
        await asyncio.to_thread(_type_write, text_to_type, press_enter_after)
    else:
        await asyncio.to_thread(_type_sync, text_to_type, press_enter_after)

    return Success({"status": "typed", "length": len(text_to_type), "enter": press_enter_after, "method": method})

@method
async def scroll(amount: int):
    ok = _ensure_pyautogui_ok()
    if ok: return ok
    log.info(f"scroll: {amount}")
    await asyncio.to_thread(_scroll_sync, amount)
    return Success({"status": "scrolled", "amount": amount})

@method
async def click_and_focus(x: int, y: int):
    """
    Robuster Klick mit Fokus-Garantie (mehrfache Klicks).
    Für schwierige Felder wie ChatGPT, die normalen Klick ignorieren.
    """
    ok = _ensure_pyautogui_ok()
    if ok: return ok
    abs_x, abs_y = convert_relative_to_absolute(x, y)
    log.info(f"click_and_focus: relativ ({x},{y}) → absolut ({abs_x},{abs_y})")
    await asyncio.to_thread(_click_and_focus_sync, abs_x, abs_y)
    return Success({"status": "clicked_and_focused", "absolute": (abs_x, abs_y), "clicks": 2})

# Registrierung
register_tool("move_mouse", move_mouse)
register_tool("click_at", click_at)
register_tool("click_and_focus", click_and_focus)
register_tool("type_text", type_text)
register_tool("scroll", scroll)

log.info("mouse_tool_fixed.py registriert – einheitliche Monitor-Logik aktiv")
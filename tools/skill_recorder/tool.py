# tools/skill_recorder/tool.py
"""
Skill Recorder - Zeichnet Benutzeraktionen auf und generiert Skills.
Mit echtem Event-Listening für Maus und Tastatur.
"""
import logging
import asyncio
import threading
import yaml
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger("skill_recorder")

# Pfade
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_FILE = PROJECT_ROOT / "agent" / "skills.yml"
RECORDINGS_DIR = PROJECT_ROOT / "data" / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# pynput Import
try:
    from pynput import mouse, keyboard
    from pynput.keyboard import Key
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    log.warning("⚠️ pynput nicht installiert. Event-Listening deaktiviert.")

# Screenshot Import
try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

# =============================================================================
# GLOBALER ZUSTAND
# =============================================================================

recording_state = {
    "active": False,
    "skill_name": None,
    "description": None,
    "actions": [],
    "start_time": None,
    "current_text_buffer": "",  # Sammelt getippten Text
    "listeners": None,
    "stop_key_combo": {keyboard.Key.ctrl, keyboard.Key.shift},  # Ctrl+Shift zum Stoppen
    "pressed_keys": set()
}

# =============================================================================
# EVENT LISTENER KLASSE
# =============================================================================

class ActionRecorder:
    """Zeichnet Maus- und Tastaturaktionen auf mit OCR-Kontext."""

    def __init__(self):
        self.mouse_listener = None
        self.keyboard_listener = None
        self.running = False
        self.text_buffer = ""
        self.last_click_time = 0
        self.pressed_keys = set()

        # OCR Engine
        self.ocr_engine = None
        self._init_ocr()

    def _init_ocr(self):
        """Initialisiert die OCR-Engine."""
        try:
            # Versuche die zentrale OCR-Engine zu nutzen
            import sys
            sys.path.insert(0, str(PROJECT_ROOT))
            from ocr_engine import OCREngine
            self.ocr_engine = OCREngine()
            log.info("✅ OCR-Engine für Recording geladen")
        except Exception as e:
            log.warning(f"⚠️ OCR-Engine nicht verfügbar: {e}")
            # Fallback: EasyOCR direkt
            try:
                import easyocr
                self.ocr_reader = easyocr.Reader(['de', 'en'], gpu=True)
                log.info("✅ EasyOCR als Fallback geladen")
            except:
                self.ocr_reader = None
                log.warning("⚠️ Keine OCR verfügbar - Kontext wird nicht erfasst")

    def start(self):
        """Startet die Listener."""
        if not PYNPUT_AVAILABLE:
            log.error("pynput nicht verfügbar!")
            return False

        self.running = True
        self.text_buffer = ""
        self.pressed_keys = set()

        # Maus-Listener
        self.mouse_listener = mouse.Listener(
            on_click=self._on_click
        )

        # Tastatur-Listener
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )

        self.mouse_listener.start()
        self.keyboard_listener.start()
        log.info("🎤 Event-Listener gestartet (mit OCR-Kontext)")
        return True

    def stop(self):
        """Stoppt die Listener."""
        self.running = False

        # Flush remaining text buffer
        if self.text_buffer:
            self._flush_text_buffer()

        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()

        log.info("🛑 Event-Listener gestoppt")

    def _on_click(self, x, y, button, pressed):
        """Mausklick aufzeichnen mit OCR-Kontext."""
        if not self.running or not pressed:
            return

        # Debounce - ignoriere Doppelklicks < 100ms
        now = time.time()
        if now - self.last_click_time < 0.1:
            return
        self.last_click_time = now

        # Flush Text-Buffer vor Klick
        if self.text_buffer:
            self._flush_text_buffer()

        # OCR-Kontext erfassen
        context, nearby_text = self._get_click_context_with_ocr(int(x), int(y))

        action = {
            "type": "click",
            "params": {
                "x": int(x),
                "y": int(y),
                "button": str(button).split(".")[-1]
            },
            "context": context,
            "nearby_text": nearby_text,  # Für intelligente Skill-Generierung
            "timestamp": datetime.now().isoformat()
        }

        recording_state["actions"].append(action)
        log.info(f"🖱️ Klick: ({x}, {y}) - '{context}'")

    def _on_key_press(self, key):
        """Tastendruck aufzeichnen."""
        if not self.running:
            return

        self.pressed_keys.add(key)

        # Check für Stop-Kombination (Ctrl+Shift+S)
        if self._check_stop_combo():
            log.info("⏹️ Stop-Kombination erkannt!")
            recording_state["stop_requested"] = True
            return

        try:
            char = key.char
            if char:
                self.text_buffer += char
        except AttributeError:
            if key == Key.space:
                self.text_buffer += " "
            elif key == Key.enter:
                self._flush_text_buffer(enter_pressed=True)
            elif key == Key.backspace:
                self.text_buffer = self.text_buffer[:-1]
            elif key == Key.tab:
                self._flush_text_buffer()
                self._record_hotkey(["tab"])

    def _on_key_release(self, key):
        """Taste losgelassen."""
        if key in self.pressed_keys:
            self.pressed_keys.discard(key)

        # Hotkey erkennen
        if key in (Key.ctrl_l, Key.ctrl_r) and self.pressed_keys:
            remaining = [k for k in self.pressed_keys
                        if k not in (Key.ctrl_l, Key.ctrl_r, Key.shift, Key.alt_l, Key.alt_r)]
            if remaining:
                self._flush_text_buffer()
                hotkey = ["ctrl"]
                if Key.shift in self.pressed_keys:
                    hotkey.append("shift")
                for k in remaining:
                    try:
                        hotkey.append(k.char)
                    except:
                        hotkey.append(k.name if hasattr(k, 'name') else str(k))
                self._record_hotkey(hotkey)

    def _check_stop_combo(self):
        """Prüft ob Ctrl+Shift+S gedrückt wurde."""
        has_ctrl = Key.ctrl_l in self.pressed_keys or Key.ctrl_r in self.pressed_keys
        has_shift = Key.shift in self.pressed_keys

        for key in self.pressed_keys:
            try:
                if hasattr(key, 'char') and key.char == 's':
                    if has_ctrl and has_shift:
                        return True
            except:
                pass
        return False

    def _flush_text_buffer(self, enter_pressed=False):
        """Speichert gesammelten Text als Aktion."""
        if not self.text_buffer.strip():
            self.text_buffer = ""
            return

        action = {
            "type": "type",
            "params": {
                "text": self.text_buffer,
                "enter": enter_pressed
            },
            "context": f"Text: {self.text_buffer[:30]}",
            "timestamp": datetime.now().isoformat()
        }

        recording_state["actions"].append(action)
        log.info(f"⌨️ Text: '{self.text_buffer[:50]}'")
        self.text_buffer = ""

    def _record_hotkey(self, keys: List[str]):
        """Zeichnet eine Tastenkombination auf."""
        action = {
            "type": "hotkey",
            "params": {"keys": keys},
            "context": f"Hotkey: {'+'.join(keys)}",
            "timestamp": datetime.now().isoformat()
        }
        recording_state["actions"].append(action)
        log.info(f"⌨️ Hotkey: {'+'.join(keys)}")

    def _get_click_context_with_ocr(self, x: int, y: int) -> tuple:
        """
        Erfasst OCR-Kontext um den Klickpunkt.
        Returns: (context_string, nearby_text_list)
        """
        if not MSS_AVAILABLE:
            return f"Klick bei ({x}, {y})", []

        try:
            import mss
            from PIL import Image

            # Screenshot eines Bereichs um den Klick (200x100 Pixel)
            region_width = 300
            region_height = 100

            with mss.mss() as sct:
                # Bestimme Monitor
                monitor = None
                for m in sct.monitors[1:]:
                    if m["left"] <= x < m["left"] + m["width"]:
                        if m["top"] <= y < m["top"] + m["height"]:
                            monitor = m
                            break

                if not monitor:
                    monitor = sct.monitors[1]

                # Region um Klickpunkt
                region = {
                    "left": max(monitor["left"], x - region_width // 2),
                    "top": max(monitor["top"], y - region_height // 2),
                    "width": region_width,
                    "height": region_height
                }

                screenshot = sct.grab(region)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            # OCR durchführen
            nearby_texts = []

            if self.ocr_engine:
                # Nutze zentrale OCR-Engine
                import numpy as np
                img_array = np.array(img)
                results = self.ocr_engine.reader.readtext(img_array)
                nearby_texts = [r[1] for r in results if r[2] > 0.5]  # Confidence > 50%

            elif hasattr(self, 'ocr_reader') and self.ocr_reader:
                # Fallback EasyOCR
                import numpy as np
                img_array = np.array(img)
                results = self.ocr_reader.readtext(img_array)
                nearby_texts = [r[1] for r in results if r[2] > 0.5]

            # Besten Kontext wählen
            if nearby_texts:
                # Finde Text der am nächsten zum Klickpunkt ist
                context = nearby_texts[0]  # Vereinfacht: erster erkannter Text
                return context, nearby_texts
            else:
                return f"Klick bei ({x}, {y})", []

        except Exception as e:
            log.debug(f"OCR-Kontext fehlgeschlagen: {e}")
            return f"Klick bei ({x}, {y})", []


# Globale Recorder-Instanz
recorder = ActionRecorder()

# =============================================================================
# RPC METHODEN
# =============================================================================

@tool(
    name="start_skill_recording",
    description="Startet die Aufzeichnung eines neuen Skills. Zum Stoppen: Ctrl+Shift+S oder stop_skill_recording aufrufen.",
    parameters=[
        P("skill_name", "string", "Name des zu erstellenden Skills (z.B. github_login)"),
        P("description", "string", "Beschreibung was der Skill tut", required=False, default=""),
    ],
    capabilities=["automation", "recording"],
    category=C.AUTOMATION
)
async def start_skill_recording(skill_name: str, description: str = "") -> dict:
    """
    Startet die Aufzeichnung eines neuen Skills.

    Args:
        skill_name: Name des zu erstellenden Skills (z.B. "github_login")
        description: Beschreibung was der Skill tut

    Zum Stoppen: Drücke Ctrl+Shift+S oder rufe stop_skill_recording auf.
    """
    global recording_state, recorder

    if not PYNPUT_AVAILABLE:
        raise Exception("pynput nicht installiert. Führe aus: pip install pynput")

    if recording_state["active"]:
        raise Exception(f"Aufzeichnung läuft bereits für '{recording_state['skill_name']}'")

    # Validiere Skill-Name
    skill_name = skill_name.lower().replace(" ", "_").replace("-", "_")

    recording_state = {
        "active": True,
        "skill_name": skill_name,
        "description": description or f"Automatisch gelernter Skill: {skill_name}",
        "actions": [],
        "start_time": datetime.now().isoformat(),
        "stop_requested": False
    }

    # Starte Event-Listener in separatem Thread
    success = recorder.start()

    if not success:
        recording_state["active"] = False
        raise Exception("Event-Listener konnten nicht gestartet werden")

    log.info(f"🎬 Skill-Aufzeichnung gestartet: '{skill_name}'")

    return {
        "status": "recording_started",
        "skill_name": skill_name,
        "message": "Aufzeichnung läuft! Führe jetzt die Aktionen aus. Drücke Ctrl+Shift+S zum Beenden."
    }


@tool(
    name="stop_skill_recording",
    description="Beendet die Aufzeichnung und generiert optional den Skill.",
    parameters=[
        P("save", "boolean", "Wenn True, wird der Skill gespeichert", required=False, default=True),
    ],
    capabilities=["automation", "recording"],
    category=C.AUTOMATION
)
async def stop_skill_recording(save: bool = True) -> dict:
    """
    Beendet die Aufzeichnung und generiert optional den Skill.

    Args:
        save: Wenn True, wird der Skill gespeichert
    """
    global recording_state, recorder

    if not recording_state["active"]:
        raise Exception("Keine Aufzeichnung aktiv")

    # Stoppe Listener
    recorder.stop()

    skill_name = recording_state["skill_name"]
    actions = recording_state["actions"].copy()
    description = recording_state["description"]

    # Reset state
    recording_state = {
        "active": False,
        "skill_name": None,
        "description": None,
        "actions": [],
        "start_time": None,
        "stop_requested": False
    }

    if not actions:
        raise Exception("Keine Aktionen aufgezeichnet")

    # Speichere Rohdaten als JSON
    raw_file = RECORDINGS_DIR / f"{skill_name}_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
    with open(raw_file, 'w', encoding='utf-8') as f:
        yaml.dump({
            "skill_name": skill_name,
            "description": description,
            "recorded_at": datetime.now().isoformat(),
            "actions": actions
        }, f, allow_unicode=True)
    log.info(f"📁 Rohdaten gespeichert: {raw_file}")

    if save:
        # Generiere und speichere Skill
        result = await _generate_skill_from_actions(skill_name, description, actions)
        return result

    return {
        "status": "recording_stopped",
        "skill_name": skill_name,
        "action_count": len(actions),
        "raw_file": str(raw_file),
        "saved": False
    }


@tool(
    name="get_recording_status",
    description="Gibt den aktuellen Aufzeichnungsstatus zurück.",
    parameters=[],
    capabilities=["automation", "recording"],
    category=C.AUTOMATION
)
async def get_recording_status() -> dict:
    """Gibt den aktuellen Aufzeichnungsstatus zurück."""
    return {
        "active": recording_state["active"],
        "skill_name": recording_state.get("skill_name"),
        "action_count": len(recording_state.get("actions", [])),
        "last_actions": recording_state.get("actions", [])[-5:],
        "pynput_available": PYNPUT_AVAILABLE
    }


@tool(
    name="list_recordings",
    description="Listet alle gespeicherten Aufzeichnungen.",
    parameters=[],
    capabilities=["automation", "recording"],
    category=C.AUTOMATION
)
async def list_recordings() -> dict:
    """Listet alle gespeicherten Aufzeichnungen."""
    recordings = list(RECORDINGS_DIR.glob("*.yaml"))
    return {
        "recordings": [
            {"name": r.stem, "path": str(r), "size": r.stat().st_size}
            for r in sorted(recordings, reverse=True)
        ]
    }


@tool(
    name="replay_recording_to_skill",
    description="Konvertiert eine gespeicherte Aufzeichnung nachträglich zu einem Skill.",
    parameters=[
        P("recording_name", "string", "Name der Aufzeichnung"),
    ],
    capabilities=["automation", "recording"],
    category=C.AUTOMATION
)
async def replay_recording_to_skill(recording_name: str) -> dict:
    """
    Konvertiert eine gespeicherte Aufzeichnung nachträglich zu einem Skill.
    """
    recording_file = RECORDINGS_DIR / f"{recording_name}.yaml"
    if not recording_file.exists():
        # Versuche mit Prefix
        matches = list(RECORDINGS_DIR.glob(f"{recording_name}*.yaml"))
        if matches:
            recording_file = matches[0]
        else:
            raise Exception(f"Aufzeichnung '{recording_name}' nicht gefunden")

    with open(recording_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    result = await _generate_skill_from_actions(
        data["skill_name"],
        data["description"],
        data["actions"]
    )
    return result


# =============================================================================
# SKILL GENERIERUNG
# =============================================================================

async def _generate_skill_from_actions(skill_name: str, description: str, actions: List[Dict]) -> dict:
    """Generiert einen Skill aus aufgezeichneten Aktionen."""

    try:
        steps = []
        params_needed = {}

        for i, action in enumerate(actions):
            step = _convert_action_to_step(action, params_needed, i)
            if step:
                if isinstance(step, list):
                    steps.extend(step)
                else:
                    steps.append(step)

        if not steps:
            raise Exception("Keine gültigen Schritte generiert")

        # Erstelle Skill-Definition
        skill_def = {
            "meta": {
                "description": description,
                "params": params_needed if params_needed else {},
                "learned_at": datetime.now().isoformat(),
                "auto_generated": True
            },
            "steps": steps
        }

        # Lade existierende Skills
        if SKILLS_FILE.exists():
            with open(SKILLS_FILE, 'r', encoding='utf-8') as f:
                skills = yaml.safe_load(f) or {}
        else:
            skills = {}

        # Füge neuen Skill hinzu
        skills[skill_name] = skill_def

        # Speichere
        with open(SKILLS_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(skills, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        log.info(f"✅ Skill '{skill_name}' gespeichert mit {len(steps)} Schritten")

        return {
            "status": "skill_created",
            "skill_name": skill_name,
            "steps_count": len(steps),
            "params": list(params_needed.keys()),
            "message": f"Skill '{skill_name}' erfolgreich erstellt! Nutze: run_skill('{skill_name}', ...)"
        }

    except Exception as e:
        log.error(f"Fehler beim Generieren des Skills: {e}", exc_info=True)
        raise Exception(f"Skill-Generierung fehlgeschlagen: {e}")


def _convert_action_to_step(action: Dict, params_needed: Dict, index: int) -> Optional[Dict | List[Dict]]:
    """Konvertiert eine aufgezeichnete Aktion in einen Skill-Step."""

    action_type = action.get("type", "")
    params = action.get("params", {})
    context = action.get("context", "")
    nearby_text = action.get("nearby_text", [])

    if action_type == "click":
        x = params.get("x", 0)
        y = params.get("y", 0)

        # Wenn OCR-Text gefunden wurde, nutze text-basiertes Klicken
        if nearby_text and len(nearby_text) > 0 and nearby_text[0] != f"Klick bei ({x}, {y})":
            click_text = nearby_text[0]
            return [
                {
                    "method": "find_text_coordinates",
                    "params": {"text_to_find": click_text},
                    "register_result_as": f"coords_{index}"
                },
                {
                    "method": "click_at",
                    "params": {
                        "x": "{{ (coords_" + str(index) + ".bbox.x1 + coords_" + str(index) + ".bbox.x2) // 2 }}",
                        "y": "{{ (coords_" + str(index) + ".bbox.y1 + coords_" + str(index) + ".bbox.y2) // 2 }}"
                    }
                }
            ]
        else:
            # Fallback: Absolute Koordinaten
            return {
                "method": "click_at",
                "params": {"x": x, "y": y}
            }

    elif action_type == "type":
        text = params.get("text", "")
        enter = params.get("enter", False)

        # Kurzer Text = wahrscheinlich ein Parameter
        if len(text) < 50:
            param_name = f"input_{index}"
            params_needed[param_name] = f"Eingabe (Standard: '{text[:20]}')"
            return {
                "method": "type_text",
                "params": {
                    "text_to_type": "{{" + param_name + "}}",
                    "press_enter_after": enter
                }
            }
        else:
            return {
                "method": "type_text",
                "params": {
                    "text_to_type": text,
                    "press_enter_after": enter
                }
            }

    elif action_type == "hotkey":
        keys = params.get("keys", [])
        return {
            "method": "hotkey",
            "params": {"keys": keys}
        }

    return None

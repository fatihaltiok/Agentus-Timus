# agent/visual_agent.py
# -*- coding: utf-8 -*-
"""
VisualAgent v2.1 V4.5 - UI-Automation mit Claude Vision + SoM + Mouse Feedback.

Features:
- Claude Sonnet 4.5 für Vision & Kontext-Verständnis
- Set-of-Mark (SoM) für Grob-Lokalisierung
- Mouse Feedback Tool für Fein-Lokalisierung (NEU!)
- Cursor-Typ als Echtzeit-Feedback
- Automatische Textfeld-Suche bei ungenauen Koordinaten
- Multi-Monitor Support
- Verification nach Aktionen
- Loop-Detection

Architektur:
  Claude Vision → Versteht Kontext, plant Aktionen
  SoM Tool → Grob-Koordinaten (±50px)
  Mouse Feedback → Fein-Koordinaten via Cursor-Typ (±5px)
  Moondream → GPU-beschleunigte Objekterkennung

Version: 2.1 (Claude Sonnet 4.5 + SoM + Mouse Feedback)
"""

import logging
import os
import json
import asyncio
import base64
import io
import sys
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

# --- Modulpfad-Korrektur ---
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- Imports ---
from dotenv import load_dotenv
import httpx

# Screenshot Libraries
try:
    import mss
    from PIL import Image
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

# --- Konfiguration ---
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:5000")
DEBUG = os.getenv("VISUAL_AGENT_DEBUG", "1") == "1"
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))

# Claude Konfiguration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
VISION_MODEL = os.getenv("VISION_MODEL", "claude-sonnet-4-5-20250929")

# Mouse Feedback Konfiguration
USE_MOUSE_FEEDBACK = os.getenv("USE_MOUSE_FEEDBACK", "1") == "1"
REFINE_RADIUS = int(os.getenv("MOUSE_REFINE_RADIUS", "80"))

if not ANTHROPIC_API_KEY:
    raise RuntimeError(
        "ANTHROPIC_API_KEY fehlt in der Umgebung.\n"
        "Setze ANTHROPIC_API_KEY in .env"
    )

# --- Logging ---
log = logging.getLogger("visual_agent")
if not log.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if DEBUG else logging.INFO)

log.info(f"👁️ VisualAgent v2.1 | Modell: {VISION_MODEL}")
log.info(f"   Monitor: {ACTIVE_MONITOR} | Mouse Feedback: {USE_MOUSE_FEEDBACK}")

# --- System Prompt ---
VISUAL_SYSTEM_PROMPT = """
Du bist ein präziser visueller Automatisierungs-Agent für Computer-Steuerung.

# DEINE ARCHITEKTUR (3-Stufen Präzision)

```
Stufe 1: SoM Tool        → Findet Elemente, gibt GROBE Koordinaten (±50px)
Stufe 2: Mouse Feedback  → Verfeinert zu EXAKTEN Koordinaten via Cursor-Typ
Stufe 3: Click & Type    → Führt Aktion aus
```

# KRITISCHE REGELN

## 0. NIEMALS OHNE AKTION BEENDEN! ⚠️⚠️⚠️
VERBOTEN: finish_task() in Iteration 1 aufrufen!
VERBOTEN: Behaupten etwas getan zu haben ohne Tool-Aufruf!
VERBOTEN: Den Screenshot als "schon erledigt" interpretieren!

DU MUSST:
✓ IMMER mindestens ein Tool aufrufen (außer finish_task)
✓ Schrittweise vorgehen: scan → click → type → verify
✓ Nur finish_task wenn Observation zeigt "success": true

BEISPIEL FALSCH:
Iteration 1: {"action": {"method": "finish_task", "params": {...}}}  ❌ VERBOTEN!

BEISPIEL RICHTIG:
Iteration 1: {"action": {"method": "start_visual_browser", "params": {...}}}  ✓
Iteration 2: {"action": {"method": "scan_ui_elements", "params": {...}}}  ✓
...
Iteration N: {"action": {"method": "finish_task", "params": {...}}}  ✓

## 1. IMMER Mouse Feedback für Textfelder nutzen!
FALSCH: scan_ui_elements → click_at(500, 300) → Miss!
RICHTIG: scan_ui_elements → refine_and_click(500, 300, "text_field") → Treffer!

## 2. Der Cursor-Typ verrät dir ALLES
- "ibeam" (⌶) = Textfeld! Hier kannst du tippen
- "hand" (👆) = Klickbar! Link oder Button
- "arrow" (➜) = Normaler Bereich, nichts interaktives
- "wait" (⏳) = Laden, warte ab

## 3. Nach erfolgreichem Klick auf Textfeld → SOFORT type_text()
Wenn cursor_type="ibeam" nach Klick:
→ Nächster Schritt MUSS type_text() sein!
→ NIEMALS erneut scannen!

## 4. Bei "nicht gefunden" → Radius erhöhen oder anderen Ansatz
Wenn find_text_field_nearby fehlschlägt:
→ Vergrößere radius auf 120 oder 150
→ Oder nutze search_for_element mit element_type="any"

# STANDARD-WORKFLOW (Schrittweise!)

⚠️ WICHTIG: Jeder Schritt = Eine Aktion = Ein Tool-Aufruf!

**Aufgabe: "Gehe zu ChatGPT und frage XYZ"**

**Schritt 1 - Browser öffnen (FALLS NÖTIG):**
```json
{"thought": "Kein Browser sichtbar. Öffne Browser mit ChatGPT URL.", "action": {"method": "start_visual_browser", "params": {"url": "https://chatgpt.com"}}}
```

**Schritt 2 - UI scannen (nach Browser-Start):**
```json
{"thought": "Browser offen. Scanne nach Chat-Eingabefeld.", "action": {"method": "scan_ui_elements", "params": {"element_types": ["text field", "chat input", "message box"]}}}
```

**Schritt 3 - Klicken:**
```json
{"thought": "Feld bei (500, 300) gefunden. Klicke sofort.", "action": {"method": "click_immediately", "params": {"x": 500, "y": 300}}}
```

**Schritt 4 - Text eingeben:**
```json
{"thought": "Klick erfolgreich. Tippe Frage direkt ein (ohne Zwischenablage).", "action": {"method": "type_text", "params": {"text_to_type": "Was ist die Hauptstadt von Frankreich?", "press_enter_after": true, "method": "write"}}}
```

**WICHTIG: Bei ChatGPT/Web-Interfaces → IMMER method="write" verwenden!**
- "write" = Direktes Tippen (sichtbar, robust, funktioniert ohne perfekten Fokus)
- Standard (ohne method) = Zwischenablage (schnell, aber erfordert perfekten Fokus)

**Schritt 5 - Fertig:**
```json
{"thought": "Frage gesendet. Aufgabe erledigt.", "action": {"method": "finish_task", "params": {"message": "Frage an ChatGPT gesendet"}}}
```

# VERFÜGBARE TOOLS

## SoM (Set-of-Mark) - Grob-Lokalisierung
- scan_ui_elements(element_types) → Findet [1], [2], [3]...
- get_element_coordinates(element_id) → x,y für ID
- find_and_click_element(element_type) → Sucht und gibt Koordinaten

## Klick-Optionen (priorisiert nach Geschwindigkeit)
1. **click_immediately(x, y)** → ⚡ SCHNELLSTER Klick, für Buttons/Links
2. **click_and_focus(x, y)** → 🎯 ROBUSTER Klick (2x) für hartnäckige Eingabefelder (ChatGPT!)
3. **refine_and_click(x, y, element_type)** → 🔍 Verfeinert Position (5s Timeout) + klickt
4. **click_at(x, y)** → 🖱️ Einfacher Klick (letztes Mittel)

## Mouse Feedback - Erweiterte Suche (optional)
- find_text_field_nearby(x, y, radius) → Sucht Textfeld via Cursor
- search_for_element(x, y, radius, element_type) → Spiral-Suche
- move_with_feedback(x, y) → Bewegt mit Cursor-Feedback
- get_cursor_at_position(x, y) → Prüft Cursor-Typ

## Tastatur & Scroll
- type_text(text_to_type, press_enter_after, method="write") → Tippt Text
  • method="write" = Direktes Tippen Zeichen für Zeichen (EMPFOHLEN für ChatGPT/Web!)
  • method="clipboard" = Zwischenablage + Ctrl+V (schnell, braucht perfekten Fokus)
  • Ohne method = Auto (probiert Zwischenablage, Fallback zu write)
- scroll(direction, amount) → Scrollt

## Browser & Apps
- start_visual_browser(url) → Browser mit URL öffnen
- open_application(app_name) → App starten

# ELEMENT-TYPEN

Für scan_ui_elements:
- Standard: button, text field, input field, search bar, icon, link
- Chat: chat input, message box, textbox, send button

Für refine_and_click / search_for_element:
- text_field → Sucht Cursor "ibeam"
- clickable → Sucht Cursor "hand"
- any → Jedes interaktive Element

# ANTWORTFORMAT
IMMER JSON: {"thought": "...", "action": {"method": "...", "params": {...}}}
NUR EINE Aktion pro Antwort!

# BEISPIEL: Chat-Eingabe in Gemini

User: "Schreibe 'Hallo' in das Gemini Chat-Feld"

Schritt 1:
{"thought": "Suche Chat-Eingabefeld", "action": {"method": "scan_ui_elements", "params": {"element_types": ["chat input", "text field", "textbox"]}}}

Observation: {"elements": [{"id": 3, "type": "chat input", "x": 895, "y": 517}]}

Schritt 2 (OPTION A - Schneller Klick):
{"thought": "Element [3] bei (895, 517). SoM ist meist präzise, nutze SOFORT-KLICK.", "action": {"method": "click_immediately", "params": {"x": 895, "y": 517}}}

Schritt 2 (OPTION B - Wenn unsicher über Position):
{"thought": "Element [3] bei (895, 517). Unsichere Position, verfeinere zuerst.", "action": {"method": "refine_and_click", "params": {"x": 895, "y": 517, "element_type": "text_field"}}}

Observation: {"success": true, "x": 895, "y": 517, "cursor_type": "ibeam", "clicked": true}

Schritt 3:
{"thought": "Klick erfolgreich, Cursor ist ibeam. Jetzt tippen!", "action": {"method": "type_text", "params": {"text_to_type": "Hallo", "press_enter_after": false}}}

Observation: {"success": true}

Schritt 4:
{"thought": "Text eingegeben. Fertig!", "action": {"method": "finish_task", "params": {"message": "Hallo wurde in das Gemini Chat-Feld eingegeben."}}}
"""


# --- Claude Vision Client ---
class ClaudeVisionClient:
    """Async Client für Claude Vision API."""
    
    def __init__(self):
        self.api_key = ANTHROPIC_API_KEY
        self.model = VISION_MODEL
        self.base_url = "https://api.anthropic.com/v1/messages"
    
    async def chat_with_image(
        self,
        messages: List[Dict[str, Any]],
        system: str = "",
        image_base64: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.1
    ) -> str:
        """Sendet Nachricht mit optionalem Bild an Claude."""
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        # Messages für Anthropic Format konvertieren
        converted_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                continue
            
            if isinstance(content, list):
                converted_content = []
                for item in content:
                    if item.get("type") == "text":
                        converted_content.append({
                            "type": "text",
                            "text": item.get("text", "")
                        })
                    elif item.get("type") == "image_url":
                        url = item.get("image_url", {}).get("url", "")
                        if url.startswith("data:image"):
                            parts = url.split(",", 1)
                            media_type = parts[0].split(";")[0].replace("data:", "")
                            b64_data = parts[1] if len(parts) > 1 else ""
                            converted_content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_data
                                }
                            })
                converted_messages.append({"role": role, "content": converted_content})
            else:
                converted_messages.append({"role": role, "content": content})
        
        if image_base64 and converted_messages:
            last_msg = converted_messages[-1]
            if last_msg["role"] == "user":
                if isinstance(last_msg["content"], str):
                    last_msg["content"] = [
                        {"type": "text", "text": last_msg["content"]},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_base64
                            }
                        }
                    ]
                elif isinstance(last_msg["content"], list):
                    last_msg["content"].append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_base64
                        }
                    })
        
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": converted_messages
        }
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                content = data.get("content", [])
                if content and isinstance(content, list):
                    return content[0].get("text", "").strip()
                return ""
                
        except httpx.TimeoutException:
            log.error("Claude Vision API Timeout")
            return '{"thought": "API Timeout", "action": {"method": "finish_task", "params": {"message": "API Timeout"}}}'
        except httpx.HTTPStatusError as e:
            log.error(f"Claude Vision HTTP Fehler: {e.response.status_code}")
            return f'{{"thought": "HTTP Error", "action": {{"method": "finish_task", "params": {{"message": "HTTP {e.response.status_code}"}}}}}}'
        except Exception as e:
            log.error(f"Claude Vision Fehler: {e}")
            return f'{{"thought": "Error", "action": {{"method": "finish_task", "params": {{"message": "{e}"}}}}}}'


# Globaler Client
claude_client = ClaudeVisionClient()


# --- Screenshot ---
def get_screenshot_base64() -> str:
    """Erstellt Screenshot als Base64."""
    if not MSS_AVAILABLE:
        log.error("mss/PIL nicht verfügbar")
        return ""
    
    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            if ACTIVE_MONITOR < len(monitors):
                monitor = monitors[ACTIVE_MONITOR]
            else:
                monitor = monitors[1] if len(monitors) > 1 else monitors[0]
            
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        img.thumbnail((1280, 720))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode()
        
        log.debug(f"Screenshot: {img.size[0]}x{img.size[1]}")
        return b64
        
    except Exception as e:
        log.error(f"Screenshot-Fehler: {e}")
        return ""


# --- Tool-Aufruf ---
async def call_tool(method: str, params: Optional[dict] = None, timeout: int = 60) -> dict:
    """Async RPC zum MCP-Server."""
    params = params or {}
    log.info(f"🔧 Tool: {method} | {str(params)[:100]}")
    
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": os.urandom(4).hex()
    }
    
    try:
        async with httpx.AsyncClient(timeout=float(timeout)) as client:
            response = await client.post(MCP_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                error = data["error"]
                msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                return {"error": msg}
            
            return data.get("result", {})
            
    except Exception as e:
        return {"error": f"RPC-Fehler: {e}"}


# --- Refine and Click (NEU!) ---
async def refine_and_click(x: int, y: int, element_type: str = "text_field", radius: int = REFINE_RADIUS) -> dict:
    """
    Kombiniert Mouse Feedback + Klick in einem Schritt.
    
    1. Nutzt find_text_field_nearby oder search_for_element
    2. Klickt wenn gefunden
    3. Gibt Cursor-Info zurück
    
    Args:
        x: Grob-Koordinate X (von SoM)
        y: Grob-Koordinate Y (von SoM)
        element_type: "text_field", "clickable", "any"
        radius: Suchradius
    
    Returns:
        Refined position, cursor_type, click success
    """
    if not USE_MOUSE_FEEDBACK:
        # Fallback: Direkter Klick ohne Refinement
        result = await call_tool("click_at", {"x": x, "y": y})
        return {
            "success": not result.get("error"),
            "refined_x": x,
            "refined_y": y,
            "cursor_type": "unknown",
            "clicked": True,
            "method": "direct_click"
        }
    
    # Mouse Feedback nutzen (mit Timeout)
    try:
        if element_type == "text_field":
            result = await asyncio.wait_for(
                call_tool("find_text_field_nearby", {"x": x, "y": y, "radius": radius}),
                timeout=5.0  # Max 5 Sekunden für Suche
            )
        else:
            result = await asyncio.wait_for(
                call_tool("search_for_element", {
                    "center_x": x,
                    "center_y": y,
                    "radius": radius,
                    "element_type": element_type
                }),
                timeout=5.0  # Max 5 Sekunden für Suche
            )
    except asyncio.TimeoutError:
        log.warning(f"⚠️ Mouse Feedback Timeout nach 5s! Fallback zu direktem Klick.")
        result = {"found": False, "timeout": True}
    
    if result.get("found") or result.get("found_interactive"):
        refined_x = result.get("x", x)
        refined_y = result.get("y", y)
        cursor_type = result.get("cursor_type", "unknown")

        # Direkter Klick ohne Verifikation (schneller und zuverlässiger)
        log.info(f"🎯 Refinement erfolgreich: ({refined_x}, {refined_y}), Cursor: {cursor_type}")
        log.info(f"🖱️ Führe DIREKTEN Klick aus (ohne Verifikation)")
        click_result = await call_tool("click_at", {"x": refined_x, "y": refined_y})

        # Kurze Pause nach Klick
        await asyncio.sleep(0.3)

        return {
            "success": True,
            "refined_x": refined_x,
            "refined_y": refined_y,
            "cursor_type": cursor_type,
            "clicked": not click_result.get("error"),
            "was_text_field": cursor_type == "ibeam",
            "was_clickable": cursor_type in ["ibeam", "hand"],
            "method": "mouse_feedback_direct_click"
        }
    else:
        # Nicht gefunden - trotzdem versuchen mit direktem Klick auf ursprüngliche Koordinaten
        log.warning(f"⚠️ Element nicht in Radius {radius}px gefunden oder Timeout.")
        log.info(f"🖱️ FALLBACK: Direkter Klick auf ursprüngliche Koordinaten ({x}, {y})")

        click_result = await call_tool("click_at", {"x": x, "y": y})
        click_success = not click_result.get("error")

        # Kurze Pause
        await asyncio.sleep(0.3)

        # Cursor danach prüfen
        cursor_result = await call_tool("get_cursor_at_position", {})

        return {
            "success": click_success,  # True wenn Klick erfolgreich war
            "refined_x": x,
            "refined_y": y,
            "cursor_type": cursor_result.get("cursor_type", "unknown"),
            "clicked": click_success,
            "was_text_field": cursor_result.get("is_text_field", False),
            "method": "fallback_direct_click",
            "message": f"Refinement fehlgeschlagen, direkter Klick auf ({x}, {y})"
        }


# --- Direct Click (NEU für schnelles Klicken) ---
async def click_immediately(x: int, y: int) -> dict:
    """
    Direkter Klick ohne Refinement oder Verifikation.

    Nutze dies wenn:
    - Die Koordinaten bereits präzise sind
    - Schnelligkeit wichtiger ist als Präzision
    - Mouse Feedback zu langsam ist

    Args:
        x: X-Koordinate
        y: Y-Koordinate

    Returns:
        Klick-Ergebnis
    """
    log.info(f"⚡ SOFORT-KLICK auf ({x}, {y}) ohne Refinement")

    result = await call_tool("click_at", {"x": x, "y": y})
    success = not result.get("error")

    await asyncio.sleep(0.2)

    # Cursor-Status nach Klick
    cursor_result = await call_tool("get_cursor_at_position", {})

    return {
        "success": success,
        "x": x,
        "y": y,
        "clicked": success,
        "cursor_type": cursor_result.get("cursor_type", "unknown"),
        "method": "immediate_click"
    }


# --- Smart Action Executor ---
async def execute_smart_action(method: str, params: dict) -> dict:
    """
    Führt Aktion intelligent aus mit automatischem Mouse Feedback.

    Ersetzt einfache click_at durch refine_and_click wenn sinnvoll.
    """
    # Spezial-Handling für refine_and_click
    if method == "refine_and_click":
        return await refine_and_click(
            x=params.get("x", 0),
            y=params.get("y", 0),
            element_type=params.get("element_type", "text_field"),
            radius=params.get("radius", REFINE_RADIUS)
        )

    # Spezial-Handling für click_immediately
    if method == "click_immediately":
        return await click_immediately(
            x=params.get("x", 0),
            y=params.get("y", 0)
        )

    # Smart Click: Wenn click_at auf vermutetes Textfeld, nutze Refinement
    # DEAKTIVIERT: Zu aggressiv, führt zu unerwünschtem Verhalten
    # Stattdessen: Agent soll explizit refine_and_click oder click_immediately nutzen

    # Standard Tool-Aufruf
    return await call_tool(method, params)


# --- Verification Helpers ---
async def verify_action(method: str) -> Tuple[bool, str]:
    """Verifiziert ob Aktion erfolgreich war."""
    needs_verify = ["click_at", "type_text", "refine_and_click", "click_with_verification"]
    if method not in needs_verify:
        return True, "no_verification_needed"
    
    result = await call_tool("verify_action_result", {"timeout": 5.0})
    success = result.get("success", False)
    
    if success:
        change = result.get("change_percentage", 0)
        log.info(f"✅ Verifiziert: {change:.1f}% Änderung")
        return True, f"verified_{change:.0f}pct_change"
    else:
        msg = result.get("message", "unknown")
        log.warning(f"⚠️ Nicht verifiziert: {msg}")
        return False, msg


async def wait_stable():
    """Wartet auf UI-Stabilität."""
    await call_tool("wait_until_stable", {"timeout": 3.0})


# --- Parsing ---
def parse_action(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """Extrahiert Action aus LLM-Antwort."""
    
    # Zeilenweise nach JSON suchen
    for line in text.strip().split('\n'):
        line = line.strip()
        if line.startswith('{') and line.endswith('}'):
            try:
                data = json.loads(line)
                if "action" in data:
                    return data["action"], None
                if "method" in data:
                    return data, None
            except json.JSONDecodeError:
                continue
    
    # Regex Patterns
    patterns = [
        r'```json\s*({[\s\S]*?})\s*```',
        r'"action"\s*:\s*({[^{}]*"method"[^{}]*})',
        r'({[^{}]*"method"[^{}]*})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                json_str = re.sub(r',\s*([\}\]])', r'\1', match.group(1).strip())
                data = json.loads(json_str)
                if "action" in data:
                    return data["action"], None
                if "method" in data:
                    return data, None
            except json.JSONDecodeError:
                continue
    
    # Versuche gesamten Text als JSON
    try:
        data = json.loads(text.strip())
        if "action" in data:
            return data["action"], None
        if "method" in data:
            return data, None
    except:
        pass
    
    return None, "Kein gültiges JSON gefunden"


# --- Loop Detection ---
@dataclass
class ActionTracker:
    """Trackt Aktionen für Loop-Detection."""
    history: List[str] = field(default_factory=list)
    max_history: int = 20
    max_repeats: int = 3
    
    def add(self, method: str, params: dict) -> bool:
        """Fügt Aktion hinzu. Gibt True zurück wenn Loop erkannt."""
        # Ignoriere bestimmte Parameter für Vergleich
        clean_params = {k: v for k, v in params.items() if not k.startswith("_")}
        key = f"{method}:{json.dumps(clean_params, sort_keys=True)}"
        
        count = self.history.count(key)
        if count >= self.max_repeats - 1:
            log.warning(f"⚠️ Loop erkannt ({count + 1}x): {method}")
            return True
        
        self.history.append(key)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        
        return False
    
    def reset(self):
        """Reset nach erfolgreichem Schritt."""
        self.history = []


# --- Context Tracker ---
@dataclass
class ContextTracker:
    """Trackt Kontext für intelligente Entscheidungen."""
    last_scan_elements: List[dict] = field(default_factory=list)
    last_clicked_type: Optional[str] = None
    last_cursor_type: Optional[str] = None
    successful_clicks: int = 0
    failed_clicks: int = 0
    
    def update_from_scan(self, elements: List[dict]):
        """Aktualisiert nach scan_ui_elements."""
        self.last_scan_elements = elements
    
    def update_from_click(self, result: dict):
        """Aktualisiert nach Klick."""
        if result.get("success") or result.get("clicked"):
            self.successful_clicks += 1
            self.last_cursor_type = result.get("cursor_type")
            if result.get("was_text_field") or self.last_cursor_type == "ibeam":
                self.last_clicked_type = "text_field"
            elif result.get("was_clickable") or self.last_cursor_type == "hand":
                self.last_clicked_type = "clickable"
        else:
            self.failed_clicks += 1
    
    def should_type_next(self) -> bool:
        """Prüft ob als nächstes getippt werden sollte."""
        return self.last_cursor_type == "ibeam" or self.last_clicked_type == "text_field"


# --- Haupt-Agent ---
async def run_visual_task(task: str, max_iterations: int = 30) -> str:
    """Führt eine visuelle Automatisierungs-Aufgabe aus."""
    log.info(f"👁️ VisualAgent v2.1 startet: {task}")
    log.info(f"   Mouse Feedback: {'AKTIV' if USE_MOUSE_FEEDBACK else 'DEAKTIVIERT'}")
    
    if not MSS_AVAILABLE:
        return "Fehler: mss/PIL nicht installiert. Screenshots nicht möglich."
    
    # State
    history = [
        {"role": "user", "content": f"AUFGABE: {task}"}
    ]
    action_tracker = ActionTracker()
    context = ContextTracker()
    
    for iteration in range(max_iterations):
        log.info(f"\n{'='*60}")
        log.info(f"Iteration {iteration + 1}/{max_iterations}")
        log.info(f"{'='*60}")
        
        # Screenshot machen
        screenshot = await asyncio.to_thread(get_screenshot_base64)
        if not screenshot:
            return "Fehler: Screenshot nicht möglich"
        
        # Kontext-Hinweise für LLM
        context_hints = []
        if context.should_type_next():
            context_hints.append("HINWEIS: Letzter Klick war auf Textfeld (ibeam). Jetzt type_text() nutzen!")
        if context.failed_clicks > 2:
            context_hints.append(f"HINWEIS: {context.failed_clicks} fehlgeschlagene Klicks. Versuche anderen Ansatz!")
        
        context_text = "\n".join(context_hints) if context_hints else ""
        
        # Aktuelle Nachricht mit Screenshot
        user_content = "Aktueller Screenshot. Nächster Schritt?"
        if context_text:
            user_content = f"{context_text}\n\n{user_content}"
        
        current_msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": user_content},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot}"}}
            ]
        }
        
        messages = history + [current_msg]
        
        # Claude Vision aufrufen
        reply = await claude_client.chat_with_image(
            messages=messages,
            system=VISUAL_SYSTEM_PROMPT,
            max_tokens=1500,
            temperature=0.1
        )
        
        log.debug(f"🧠 Antwort: {reply[:300]}...")
        
        # Final Answer Check
        if "Final Answer:" in reply:
            return reply.split("Final Answer:")[1].strip()
        
        # Action parsen
        action, err = parse_action(reply)
        
        if not action:
            log.warning(f"Parse-Fehler: {err}")
            history.append({"role": "assistant", "content": reply})
            history.append({"role": "user", "content": f"Fehler: {err}. Sende gültiges JSON."})
            continue
        
        method = action.get("method", "")
        params = action.get("params", {})

        log.info(f"📋 Action: {method}({params})")

        # Anti-Hallucination: Verhindere finish_task in Iteration 1
        if method == "finish_task" and iteration == 0:
            log.warning("⚠️ WARNUNG: finish_task in Iteration 1 ist VERBOTEN!")
            history.append({"role": "assistant", "content": reply})
            history.append({
                "role": "user",
                "content": "❌ FEHLER: Du kannst nicht in Iteration 1 die Aufgabe beenden!\n\n"
                          "Du MUSST zuerst Aktionen durchführen:\n"
                          "1. start_visual_browser(url) - Wenn Browser nötig\n"
                          "2. scan_ui_elements() - Finde UI-Elemente\n"
                          "3. click_immediately() oder refine_and_click() - Klicke\n"
                          "4. type_text() - Gib Text ein\n"
                          "5. Erst DANN: finish_task()\n\n"
                          "Beginne JETZT mit Schritt 1!"
            })
            continue

        # finish_task Check (nur wenn nicht Iteration 1)
        if method == "finish_task":
            msg = params.get("message", "Aufgabe abgeschlossen")
            log.info(f"✅ Aufgabe beendet: {msg}")
            return msg
        
        # Loop Detection
        if action_tracker.add(method, params):
            history.append({"role": "assistant", "content": reply})
            history.append({
                "role": "user",
                "content": "⚠️ Loop erkannt! Versuche eine ANDERE Strategie:\n"
                          "1. Nutze refine_and_click statt click_at\n"
                          "2. Vergrößere den radius Parameter\n"
                          "3. Nutze search_for_element mit element_type='any'"
            })
            continue

        # Before-Screenshot für Verifikation (bei bestimmten Aktionen)
        verification_methods = ["click_at", "type_text", "refine_and_click", "click_immediately", "click_with_verification"]
        if method in verification_methods:
            await call_tool("capture_screen_before_action", {})

        # Action ausführen
        result = await execute_smart_action(method, params)

        # Kontext aktualisieren
        if method == "scan_ui_elements":
            elements = result.get("elements", [])
            context.update_from_scan(elements)
        elif method in ["click_at", "refine_and_click", "click_with_verification"]:
            context.update_from_click(result)
        
        # Verification für wichtige Aktionen
        if method in ["click_at", "type_text", "refine_and_click"]:
            verified, verify_msg = await verify_action(method)
            
            if not verified and method != "type_text":
                context.failed_clicks += 1
                history.append({"role": "assistant", "content": reply})
                history.append({
                    "role": "user",
                    "content": f"⚠️ Aktion nicht verifiziert: {verify_msg}\n"
                              "Versuche:\n"
                              "1. refine_and_click mit größerem radius (120)\n"
                              "2. search_for_element zum Finden des Elements\n"
                              "3. Anderen Bereich des Bildschirms"
                })
                continue
            
            # Warte auf Stabilität
            await wait_stable()
            
            # Reset Loop-Tracker nach erfolgreichem Schritt
            action_tracker.reset()
        
        # History aktualisieren
        history.append({"role": "assistant", "content": reply})
        
        # Observation formatieren
        obs_str = json.dumps(result, ensure_ascii=False)
        if len(obs_str) > 1000:
            obs_str = obs_str[:1000] + "..."
        
        # Zusätzliche Hinweise basierend auf Ergebnis
        hints = []
        if method == "refine_and_click" and result.get("was_text_field"):
            hints.append("✅ Textfeld gefunden und geklickt! Nächster Schritt: type_text()")
        if method == "scan_ui_elements" and result.get("count", 0) == 0:
            hints.append("⚠️ Keine Elemente gefunden. Versuche anderen element_type oder scroll.")
        
        obs_content = f"Observation: {obs_str}"
        if hints:
            obs_content += "\n\n" + "\n".join(hints)
        
        history.append({"role": "user", "content": obs_content})
        
        # Kurze Pause
        await asyncio.sleep(0.3)
    
    return f"Max Iterationen ({max_iterations}) erreicht."


# --- Sync Wrapper ---
def run_visual_task_sync(task: str, max_iterations: int = 30) -> str:
    """Sync Wrapper für run_visual_task."""
    return asyncio.run(run_visual_task(task, max_iterations))


# --- CLI ---
if __name__ == "__main__":
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        result = run_visual_task_sync(task)
        
        print("\n" + "=" * 80)
        print("👁️ FINALE ANTWORT DES VISUAL-AGENTEN:")
        print("=" * 80)
        print(result)
        print("=" * 80)
    else:
        print("\n👁️ Timus VisualAgent v2.1")
        print(f"   Modell: {VISION_MODEL}")
        print(f"   Monitor: {ACTIVE_MONITOR}")
        print(f"   Mouse Feedback: {'AKTIV' if USE_MOUSE_FEEDBACK else 'DEAKTIVIERT'}")
        print("\nFeatures:")
        print("  ✓ Claude Sonnet 4.5 Vision")
        print("  ✓ SoM für Grob-Lokalisierung")
        print("  ✓ Mouse Feedback für Fein-Lokalisierung")
        print("  ✓ Cursor-Typ als Echtzeit-Feedback")
        print("  ✓ Auto-Refinement bei Textfeld-Klicks")
        print("\nBeispiele:")
        print("  python visual_agent.py \"Öffne Firefox und gehe zu google.com\"")
        print("  python visual_agent.py \"Schreibe 'Hallo' in das Chat-Feld\"")
        print("  python visual_agent.py \"Klicke auf den Login-Button\"")

"""
VisualNemotronAgent v4 - Desktop-Automatisierung mit echten Maus-Tools.

Features:
- Nemotron für strikte JSON-Aktionen
- SoM (Set-of-Mark) für UI-Element-Erkennung
- PyAutoGUI für echte Maus/Klick-Aktionen
- GPT-4 Vision als Fallback
- Desktop + Browser Support

Unterschied zu v3:
- v3: Playwright (nur Browser)
- v4: PyAutoGUI + SoM (ganzer Desktop - Browser, Apps, alles!)

Author: Timus Agent
Version: 4.0 (Desktop Edition)
"""

import os
import sys
import json
import asyncio
import logging
import time
import re
import subprocess
import base64
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from io import BytesIO
from PIL import Image
import httpx

from dotenv import load_dotenv
from openai import OpenAI

# Setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)

# Shared Utilities
from agent.shared.mcp_client import MCPClient as _SharedMCPClient
from agent.shared.screenshot import capture_screenshot_image as _shared_screenshot_image
from agent.shared.action_parser import parse_action as _shared_parse_action

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s'
)
log = logging.getLogger("VisualNemotronV4")

# Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
NEMOTRON_MODEL = os.getenv("REASONING_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
MCP_URL = os.getenv("MCP_SERVER_URL", "http://localhost:5000")
# Feature-Flag: Florence-2 als primärer Vision-Pfad (FLORENCE2_ENABLED=false → alter Pfad)
FLORENCE2_ENABLED = os.getenv("FLORENCE2_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
# LLM-Fallback für Decision-Layer (nur NemotronClient, NICHT Florence-Detection)
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "")        # z.B. http://localhost:1234/v1
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "")    # z.B. Qwen/Qwen2.5-7B-Instruct


# ============================================================================
# TOOL CLIENTS
# ============================================================================

class MCPToolClient:
    """Client fuer MCP-Server Tools (mouse, som, etc.).

    Delegiert Basis-RPC an agent.shared.mcp_client.MCPClient.
    Convenience-Methoden (click_at, type_text, ...) bleiben hier.
    """

    def __init__(self, mcp_url: str = MCP_URL):
        self._shared = _SharedMCPClient(url=mcp_url, timeout=60.0)

    async def call_tool(self, method: str, params: Dict = None) -> Dict:
        """Ruft ein MCP Tool auf (delegiert an shared MCPClient)."""
        return await self._shared.call(method, params)

    # Mouse Tool Methods
    async def click_at(self, x: int, y: int, button: str = 'left') -> Dict:
        return await self.call_tool("click_at", {"x": x, "y": y, "button_name": button})
    
    async def move_mouse(self, x: int, y: int, duration: float = 0.05) -> Dict:
        return await self.call_tool("move_mouse", {"x": x, "y": y, "duration": duration})
    
    async def type_text(self, text: str, press_enter: bool = False, method: str = "auto") -> Dict:
        return await self.call_tool("type_text", {
            "text_to_type": text,
            "press_enter_after": press_enter,
            "method": method
        })
    
    async def scroll(self, amount: int) -> Dict:
        return await self.call_tool("scroll", {"amount": amount})
    
    async def click_and_focus(self, x: int, y: int) -> Dict:
        return await self.call_tool("click_and_focus", {"x": x, "y": y})
    
    # SoM Tool Methods
    async def scan_ui_elements(self, element_types: List[str] = None, use_zoom: bool = True) -> Dict:
        return await self.call_tool("scan_ui_elements", {
            "element_types": element_types or ["button", "text field", "search bar"],
            "use_zoom": use_zoom
        })
    
    async def find_and_click_element(self, element_type: str) -> Dict:
        return await self.call_tool("find_and_click_element", {"element_type": element_type})
    
    async def get_element_coordinates(self, element_id: int) -> Dict:
        return await self.call_tool("get_element_coordinates", {"element_id": element_id})
    
    async def describe_screen_elements(self) -> Dict:
        return await self.call_tool("describe_screen_elements", {})
    
    async def save_annotated_screenshot(self, filename: str = "som_v4.png") -> Dict:
        return await self.call_tool("save_annotated_screenshot", {"filename": filename})


# ============================================================================
# DESKTOP CONTROLLER (ersetzt BrowserController)
# ============================================================================

class DesktopController:
    """
    Steuert den Desktop via PyAutoGUI (MCP Tools).
    Unterstützt Browser UND Desktop-Apps.
    """
    
    def __init__(self, mcp_client: MCPToolClient):
        self.mcp = mcp_client
        self.elements: List[Dict] = []  # Gescannte UI-Elemente
        self.last_screenshot: Optional[Image.Image] = None
    
    async def start(self):
        """Initialisiert Desktop (kein Browser-Start nötig)."""
        log.info("✅ Desktop Controller initialisiert (PyAutoGUI)")
        log.info("   Unterstützt: Browser, Desktop-Apps, alle UI-Elemente")
    
    async def stop(self):
        """Cleanup (nicht viel zu tun bei Desktop)."""
        log.info("🛑 Desktop Controller beendet")
    
    async def scan_elements(self, types: List[str] = None) -> List[Dict]:
        """Scannt UI-Elemente auf dem Bildschirm."""
        result = await self.mcp.scan_ui_elements(types)
        if "elements" in result:
            self.elements = result["elements"]
            log.info(f"   🔍 {len(self.elements)} UI-Elemente gescannt")
            return self.elements
        return []
    
    async def screenshot(self) -> Image.Image:
        """Macht Screenshot (delegiert an agent.shared.screenshot)."""
        img = _shared_screenshot_image()
        if img is not None:
            self.last_screenshot = img
            return img
        raise RuntimeError("Screenshot fehlgeschlagen: mss/PIL nicht verfuegbar")
    
    async def find_element_by_type(self, element_type: str) -> Optional[Tuple[int, int]]:
        """Findet Element nach Typ und gibt Koordinaten zurück."""
        # Zuerst scannen
        elements = await self.scan_elements([element_type])
        
        for elem in elements:
            if elem.get("type") == element_type:
                x = elem.get("x", elem.get("click_x"))
                y = elem.get("y", elem.get("click_y"))
                if x and y:
                    log.info(f"   📍 {element_type} gefunden bei ({x}, {y})")
                    return (int(x), int(y))
        
        return None
    
    async def find_element_by_description(self, description: str, screenshot: Image.Image) -> Optional[Tuple[int, int]]:
        """
        Nutzt GPT-4 Vision um Element zu finden - PRIMARY Methode!
        Viel zuverlässiger als SoM/Moondream.
        """
        if not OPENAI_API_KEY:
            return None
        
        # Bild zu Base64 (kleiner für schnellere API)
        buffer = BytesIO()
        img_small = screenshot.resize((768, 432), Image.Resampling.LANCZOS)
        img_small.save(buffer, format='JPEG', quality=85)
        b64 = base64.b64encode(buffer.getvalue()).decode()
        
        prompt = f"""Finde "{description}" auf dem Screenshot.

WICHTIG:
1. Suche das Element visuell auf dem Bild
2. Schätze den MITTELPUNKT (center point)
3. Gib Koordinaten im JSON-Format zurück
4. Das Bild ist 768x432px

Antworte NUR mit JSON:
{{"x": 400, "y": 200, "found": true}}

ODER wenn nicht gefunden:
{{"found": false}}

KEIN Code, KEINE Erklärung - nur JSON!"""
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json={
                        "model": "gpt-4o-mini",  # Schnell & günstig
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                            ]
                        }],
                        "max_tokens": 150,
                        "temperature": 0.1  # Präzise Koordinaten
                    }
                )
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                
                # Extrahiere JSON
                json_match = re.search(r'\{[^}]*"x"\s*:\s*\d+[^}]*\}', content)
                if json_match:
                    coords = json.loads(json_match.group())
                    if coords.get("found") and coords.get("x", 0) > 0:
                        # Skaliere zurück auf Originalgröße
                        orig_width, orig_height = screenshot.size
                        scale_x = orig_width / 768
                        scale_y = orig_height / 432
                        real_x = int(coords["x"] * scale_x)
                        real_y = int(coords["y"] * scale_y)
                        log.info(f"   📍 GPT-4 Vision: {description} bei ({real_x}, {real_y}) [skaliert von ({coords['x']}, {coords['y']})]")
                        return (real_x, real_y)
                
                log.warning(f"   ⚠️ Element nicht gefunden: {description}")
                return None
                
        except Exception as e:
            log.warning(f"   ⚠️ GPT-4 Vision Fehler: {e}")
            return None
    
    async def execute_action(self, action: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Führt eine Aktion aus - NUTZT GPT-4 VISION für Koordinaten!
        Returns: (done, error)
        """
        act_type = action.get("action", "").lower()
        target = action.get("target", {})
        coords = action.get("coordinates", {})
        
        try:
            if act_type == "click":
                x, y = coords.get("x", 0), coords.get("y", 0)
                target_desc = target.get("description", "")
                target_type = target.get("element_type", "")
                search_term = target_desc if target_desc else target_type

                # Hybrid Gate: DOM-first, Vision-Fallback
                from utils.dom_vision_gate import try_dom_first

                async def _dom_click(a):
                    """DOM-Klick via click_by_text (wenn Text vorhanden)."""
                    if search_term:
                        return await self.mcp.call_tool("click_by_text", {"text": search_term})
                    return {"error": "Kein DOM-Target verfuegbar"}

                async def _vision_click(a):
                    """Vision-Fallback: Florence-2 detect_ui für lokale Koordinaten."""
                    vx, vy = x, y
                    if not vx or not vy:
                        log.info(f"   🔍 Suche mit Florence-2 detect_ui: '{search_term}'")
                        temp_path = "/tmp/v4_click_search.png"
                        screenshot = await self.screenshot()
                        await asyncio.to_thread(screenshot.save, temp_path)

                        result = await self.mcp.call_tool(
                            "florence2_detect_ui",
                            {"image_path": temp_path},
                        )
                        if isinstance(result, dict) and result.get("error"):
                            return {"error": f"Florence-2 detect_ui Fehler: {result['error']}"}

                        term = (search_term or "").lower().strip()
                        candidates = (
                            e for e in result.get("elements", [])
                            if term and term in e.get("label", "").lower()
                        )
                        best = min(
                            candidates,
                            key=lambda e: len(e.get("label", "")),
                            default=None,
                        )
                        if best and best.get("center"):
                            vx, vy = best["center"]
                        else:
                            return {"error": f"Element nicht gefunden (Florence-2): {search_term}"}
                    return await self.mcp.click_at(int(vx), int(vy))

                result, method_used = await try_dom_first(action, _dom_click, _vision_click)
                if isinstance(result, dict) and result.get("error"):
                    err_msg = result["error"]
                    if isinstance(err_msg, dict):
                        err_msg = err_msg.get("message", "Klick fehlgeschlagen")
                    return False, str(err_msg)
                log.info(f"   🖱️  Klick bei ({x}, {y}) via {method_used}")
                
            elif act_type == "click_and_focus":
                x, y = coords.get("x", 0), coords.get("y", 0)
                
                if not x or not y:
                    # Auch hier lokal mit Florence-2 statt GPT-4-Koordinatensuche.
                    target_desc = target.get("description", target.get("element_type", "input"))
                    temp_path = "/tmp/v4_focus_search.png"
                    screenshot = await self.screenshot()
                    await asyncio.to_thread(screenshot.save, temp_path)
                    result = await self.mcp.call_tool(
                        "florence2_detect_ui",
                        {"image_path": temp_path},
                    )
                    if isinstance(result, dict) and result.get("error"):
                        return False, f"Florence-2 detect_ui Fehler: {result['error']}"

                    term = (target_desc or "").lower().strip()
                    candidates = (
                        e for e in result.get("elements", [])
                        if term and term in e.get("label", "").lower()
                    )
                    best = min(
                        candidates,
                        key=lambda e: len(e.get("label", "")),
                        default=None,
                    )
                    if best and best.get("center"):
                        x, y = best["center"]
                    else:
                        return False, f"Kein Fokus-Element gefunden (Florence-2): {target_desc}"
                
                if x and y:
                    await self.mcp.click_and_focus(int(x), int(y))
                    log.info(f"   🖱️  Fokus-Klick bei ({x}, {y})")
                else:
                    return False, "Koordinaten fehlen für click_and_focus"
                    
            elif act_type == "type":
                text = action.get("text_input", "")
                press_enter = action.get("press_enter", False)
                
                result = await self.mcp.type_text(text, press_enter)
                if "error" in result:
                    return False, result["error"].get("message", "Tippen fehlgeschlagen")
                log.info(f"   ⌨️  Getippt: {text[:30]}{'...' if len(text) > 30 else ''}")
                
            elif act_type == "press":
                key = action.get("key", "Enter")
                # Für einfache Tasten direkt PyAutoGUI
                if key.lower() in ["enter", "return"]:
                    result = await self.mcp.type_text("", press_enter=True)
                else:
                    # Andere Tasten via subprocess (xte oder ähnlich)
                    try:
                        subprocess.run(["xdotool", "key", key], check=True, timeout=5)
                        log.info(f"   ⌨️  Taste: {key}")
                    except:
                        log.warning(f"   ⚠️ Taste {key} nicht unterstützt")
                        return False, f"Taste {key} nicht unterstützt"
                        
            elif act_type == "scroll_up":
                await self.mcp.scroll(500)
                log.info("   📜 Scroll up")
                
            elif act_type == "scroll_down":
                await self.mcp.scroll(-500)
                log.info("   📜 Scroll down")
                
            elif act_type == "wait":
                secs = action.get("seconds", 1.5)
                await asyncio.sleep(secs)
                log.info(f"   ⏳ Warte {secs}s")
                
            elif act_type == "navigate":
                # Für Browser: URL öffnen via xdg-open oder direkt
                url = action.get("url", "")
                if url:
                    try:
                        # Versuche Chrome/Chromium direkt
                        subprocess.Popen(
                            ["google-chrome", "--new-window", url],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        log.info(f"   🌐 Öffne: {url}")
                        await asyncio.sleep(3)  # Zeit zum Laden
                    except:
                        # Fallback zu xdg-open
                        subprocess.Popen(
                            ["xdg-open", url],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        log.info(f"   🌐 Öffne (fallback): {url}")
                        await asyncio.sleep(3)
                        
            elif act_type == "scan":
                # Explizites Scan-Kommando
                element_types = action.get("element_types", ["button", "text field"])
                await self.scan_elements(element_types)
                log.info(f"   🔍 Scan: {element_types}")
                
            elif act_type == "extract":
                # Extrahiere Text von Screen via OCR oder Vision
                log.info("   📄 Extrahiere (not implemented in v4)")
                
            elif act_type == "done":
                log.info("   ✅ Task abgeschlossen!")
                return True, None
                
            elif act_type == "ask_user":
                reason = action.get("reason", "Input benötigt")
                log.info(f"   ❓ Benutzer-Input nötig: {reason}")
                return False, f"ASK_USER:{reason}"
            
            await asyncio.sleep(0.3)  # Kurze Pause für UI
            return False, None
            
        except Exception as e:
            error_msg = str(e)
            log.error(f"   ❌ Aktion fehlgeschlagen: {error_msg}")
            return False, error_msg


# ============================================================================
# NEMOTRON CLIENT (aus v3 übernommen)
# ============================================================================

class NemotronClient:
    """
    Client für Nemotron (Decision-Layer) mit lokalem LLM-Fallback.

    Priorität:
      1. Nemotron via OpenRouter (OPENROUTER_API_KEY)
      2. Lokaler OpenAI-kompatibler Endpoint (LOCAL_LLM_URL + LOCAL_LLM_MODEL)

    Hinweis: Fallback gilt NUR für den Decision-Layer.
             Florence-2 (Vision-Layer) hat einen eigenen Fallback-Pfad in VisionClient.
    """

    MAX_RETRIES = 3

    def __init__(self):
        self.client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        # Lokaler Fallback-Client (optional)
        self.fallback_client: Optional[OpenAI] = None
        self.fallback_model: str = LOCAL_LLM_MODEL
        if LOCAL_LLM_URL and LOCAL_LLM_MODEL:
            self.fallback_client = OpenAI(
                api_key="local",
                base_url=LOCAL_LLM_URL,
            )
            log.info(f"   🔄 LLM-Fallback konfiguriert: {LOCAL_LLM_URL} ({LOCAL_LLM_MODEL})")

    def _call_llm(self, system_prompt: str, user_prompt: str, use_fallback: bool = False) -> str:
        """Ruft Nemotron oder den lokalen Fallback auf."""
        if use_fallback and self.fallback_client:
            client = self.fallback_client
            model = self.fallback_model
            log.info(f"   🔄 Nutze LLM-Fallback: {model}")
        else:
            client = self.client
            model = NEMOTRON_MODEL

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1500,
        )
        return response.choices[0].message.content.strip()

    def _extract_json(self, text: str) -> Dict:
        """Extrahiere JSON aus Nemotron-Antwort (nutzt shared parser als Fallback)."""
        # Versuche zuerst spezifisches Nemotron-Parsing
        matches = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        for m in matches:
            try:
                return json.loads(m)
            except Exception:
                continue

        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass

        return {"actions": [], "status": "error", "error": "No valid JSON"}
    
    async def generate_step(
        self,
        screenshot_description: str,
        task_description: str,
        step_history: List[Dict],
        available_elements: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Generiert nächsten Schritt mit Desktop-spezifischem Prompt.
        """
        
        elements_str = ""
        if available_elements:
            elements_str = "\nVERFÜGBARE UI-ELEMENTE:\n"
            for e in available_elements[:10]:  # Max 10 Elemente
                elements_str += f"  - [{e.get('id', '?')}] {e.get('type', 'element')} bei ({e.get('x', '?')}, {e.get('y', '?')})\n"
        
        system_prompt = f"""Du bist ein Desktop-Automation-Experte.

AUFGABE:
Analysiere den Desktop/Screenshot und entscheide die nächste Aktion.

REGELN:
1. Gib IMMER valides JSON zurück (zwischen ```json und ```)
2. Koordinaten sind Bildschirm-Koordinaten (Pixel)
3. Wenn Elemente bekannt sind, nutze deren Koordinaten direkt
4. "scan" Aktion um UI-Elemente zu finden (am Anfang wichtig!)
5. "done" nur wenn Task wirklich komplett

VERFÜGBARE AKTIONEN:
- click: Klicke auf Element (mit Koordinaten x, y)
- click_and_focus: Doppelter Klick für Fokus (für hartnäckige Felder)
- type: Tippe Text ein (text_input + optional press_enter)
- press: Drücke Taste (key: Enter, Tab, Escape)
- scroll_up/down: Scrolle
- wait: Warte X Sekunden
- navigate: Öffne URL im Browser (xdg-open)
- scan: Scanne UI-Elemente (element_types Array)
- done: Task abgeschlossen

WICHTIG: Antworte NUR mit JSON im Format:
```json
{{
  "task_analysis": {{
    "current_state": "Beschreibung",
    "available_elements": 5,
    "next_step_reasoning": "Warum diese Aktion?"
  }},
  "actions": [
    {{
      "action": "click",
      "coordinates": {{"x": 750, "y": 400}},
      "target": {{"element_type": "button", "description": "Such-Button"}},
      "reason": "Warum?"
    }}
  ],
  "status": "in_progress"
}}
```"""

        user_prompt = f"""TASK: {task_description}

SCREENSHOT BESCHREIBUNG:
{screenshot_description}
{elements_str}

BISHERIGE SCHRITTE ({len(step_history)}):
{json.dumps(step_history[-3:], indent=2) if step_history else "Noch keine Schritte"}

ENTSCHEIDE DEN NÄCHSTEN SCHRITT (nur JSON, keine Erklärungen):"""

        last_error: Optional[str] = None
        for attempt in range(self.MAX_RETRIES):
            use_fallback = attempt > 0  # Erster Versuch: Nemotron; danach Fallback
            try:
                result_text = await asyncio.to_thread(
                    self._call_llm, system_prompt, user_prompt, use_fallback
                )
                result_json = self._extract_json(result_text)

                if "actions" not in result_json:
                    result_json["actions"] = []
                if "status" not in result_json:
                    result_json["status"] = "in_progress"

                source = "Fallback" if use_fallback else "Nemotron"
                log.info(f"   🤖 {source}: {len(result_json['actions'])} Aktionen geplant")
                return result_json

            except Exception as e:
                last_error = str(e)
                if use_fallback or not self.fallback_client:
                    log.error(f"   ❌ LLM Fehler (Versuch {attempt + 1}): {e}")
                else:
                    log.warning(f"   ⚠️ Nemotron Fehler (Versuch {attempt + 1}): {e} → Fallback")

        log.error(f"   ❌ Alle {self.MAX_RETRIES} LLM-Versuche fehlgeschlagen: {last_error}")
        return {
            "actions": [{"action": "scan", "element_types": ["button", "text field"]}],
            "status": "in_progress",
            "error": last_error,
        }


# ============================================================================
# LOOP DETECTOR (aus v3 übernommen)
# ============================================================================

class LoopDetector:
    """Erkennt wiederholte Zustaende mit Perceptual Hashing und Proximity-Check."""

    def __init__(self, max_similar_screenshots: int = 3):
        self.screenshot_hashes: List[str] = []
        self.action_history: List[str] = []
        self.max_similar = max_similar_screenshots

    def _perceptual_hash(self, img: Image.Image) -> str:
        """Average-Hash: robust gegen kleine Pixel-Aenderungen."""
        small = img.resize((8, 8)).convert('L')
        pixels = list(small.getdata())
        avg = sum(pixels) / len(pixels)
        return ''.join('1' if p > avg else '0' for p in pixels)

    def _actions_similar(self, a1: str, a2: str) -> bool:
        """Prueft ob zwei Aktionen aehnlich sind (Koordinaten-Proximity)."""
        try:
            d1, d2 = json.loads(a1), json.loads(a2)
            if d1.get("action") == d2.get("action") == "click":
                c1 = d1.get("coordinates", {})
                c2 = d2.get("coordinates", {})
                dx = abs(c1.get("x", 0) - c2.get("x", 0))
                dy = abs(c1.get("y", 0) - c2.get("y", 0))
                return dx <= 30 and dy <= 30
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        return a1 == a2

    def add_state(self, screenshot: Image.Image, action: Dict) -> bool:
        """True wenn Loop erkannt."""
        img_hash = self._perceptual_hash(screenshot)
        action_str = json.dumps(action, sort_keys=True)

        self.screenshot_hashes.append(img_hash)
        self.action_history.append(action_str)

        if len(self.screenshot_hashes) >= self.max_similar:
            recent_hashes = self.screenshot_hashes[-self.max_similar:]
            recent_actions = self.action_history[-self.max_similar:]

            # Perceptual Hashes vergleichen (identisch = gleicher Screen)
            hashes_same = len(set(recent_hashes)) == 1

            # Aktionen via Proximity vergleichen
            actions_same = all(
                self._actions_similar(recent_actions[0], a)
                for a in recent_actions[1:]
            )

            if hashes_same and actions_same:
                log.warning(f"   LOOP ERKANNT! {self.max_similar}x identisch/aehnlich")
                return True

        return False

    def get_unique_states(self) -> int:
        return len(set(self.screenshot_hashes))


# ============================================================================
# VISION CLIENT (aus v3 übernommen, angepasst)
# ============================================================================

class VisionClient:
    """
    Screenshot-Analyse mit dreistufigem Fallback-Pfad:

    1. Florence-2 (lokal, PRIMARY wenn FLORENCE2_ENABLED=true)
       ~1-3s auf GPU, gibt strukturierten summary_prompt für Nemotron zurück.
    2. GPT-4 Vision (API, ~3-5s)
    3. Qwen-VL (lokal, ~60s+)
    """

    def __init__(self, mcp_url: str = MCP_URL):
        self.mcp_url = mcp_url
        self.use_gpt4_primary = True
        self.florence2_timeout = 90.0   # Erstes Laden dauert länger (Modell-Download)
        self.gpt4_timeout = 10.0
        self.qwen_timeout = 120.0

    def _resize_for_qwen(self, img: Image.Image) -> Image.Image:
        return img.resize((512, 288), Image.Resampling.LANCZOS)

    async def analyze(self, img: Image.Image, task: str) -> str:
        """
        Screenshot → strukturierte Beschreibung für Nemotron.

        Pfad-Reihenfolge (abhängig von Flags und API-Keys):
          Florence-2 (lokal) → GPT-4 Vision (API) → Qwen-VL (lokal)
        """
        # PRIMARY: Florence-2 (lokal, kein API-Key nötig)
        if FLORENCE2_ENABLED:
            try:
                result = await self._florence2_analyze(img, task)
                if result and not result.startswith("["):
                    log.info("   🌸 Florence-2 (lokal) erfolgreich")
                    return result
            except Exception as e:
                log.warning(f"   Florence-2 failed: {e} -> Fallback zu GPT-4")

        # FALLBACK 1: GPT-4 Vision (schnell, ~3-5s)
        if self.use_gpt4_primary and OPENAI_API_KEY:
            try:
                result = await self._gpt4_analyze(img, task)
                if result and not result.startswith("["):
                    log.info("   🚀 GPT-4 Vision (Fallback) erfolgreich")
                    return result
            except Exception as e:
                log.warning(f"   GPT-4 failed: {e} -> Fallback zu Qwen-VL")

        # FALLBACK 2: Qwen-VL (langsam, ~60s+)
        log.info("   🐌 Nutze Qwen-VL (Fallback, 60s+ Timeout)...")
        return await self._qwen_analyze(img, task)

    async def _florence2_analyze(self, img: Image.Image, task: str) -> str:
        """
        Florence-2 via MCP florence2_hybrid_analysis.
        Speichert Screenshot temporär, ruft Tool auf, gibt summary_prompt zurück.
        Fallback bei Fehler: florence2_full_analysis.
        """
        temp_path = "/tmp/v4_florence2_screen.png"
        await asyncio.to_thread(img.save, temp_path)

        try:
            async with httpx.AsyncClient(timeout=self.florence2_timeout) as client:
                async def _rpc(method: str, request_id: int) -> Dict[str, Any]:
                    resp = await client.post(
                        self.mcp_url,
                        json={
                            "jsonrpc": "2.0",
                            "method": method,
                            "params": {"image_path": temp_path},
                            "id": request_id,
                        },
                    )
                    return resp.json()

                used_method = "florence2_hybrid_analysis"
                data = await _rpc(used_method, 1)

                has_rpc_error = "error" in data
                has_result_error = isinstance(data.get("result"), dict) and "error" in data["result"]
                if has_rpc_error or has_result_error:
                    log.warning("   ⚠️ florence2_hybrid_analysis fehlgeschlagen -> fallback zu florence2_full_analysis")
                    used_method = "florence2_full_analysis"
                    data = await _rpc(used_method, 2)

            if "result" in data:
                r = data["result"]
                if "error" in r:
                    return f"[Florence-2 Error: {r['error']}]"
                summary = r.get("summary_prompt", "")
                if summary:
                    log.info(
                        f"   🌸 Florence-2 ({used_method}): {r.get('element_count', 0)} UI-Elemente, "
                        f"text={r.get('text_count', '?')}, ocr={r.get('ocr_backend', 'florence2')}, "
                        f"device={r.get('device', '?')}"
                    )
                    return summary
                return "[Florence-2: leerer summary_prompt]"

            if "error" in data:
                return f"[Florence-2 RPC Error: {data['error'].get('message', 'Unknown')}]"

        except Exception as e:
            return f"[Florence-2 failed: {e}]"
        return "[Florence-2: kein Ergebnis]"

    async def _qwen_analyze(self, img: Image.Image, task: str) -> str:
        """Qwen-VL Fallback mit langem Timeout."""
        temp_path = "/tmp/v4_screenshot.png"
        small_img = self._resize_for_qwen(img)
        small_img.save(temp_path, quality=85)

        prompt = f"""Analyze this desktop/browser screenshot.
TASK: {task}

Describe:
1. All visible UI elements (buttons, inputs, links) with positions
2. Main application in focus
3. Any popups, cookie banners, dialogs
4. Current page state (loading, ready, error)
5. Interactive elements that can be clicked

Focus on actionable details for automation."""

        try:
            async with httpx.AsyncClient(timeout=self.qwen_timeout) as client:
                resp = await client.post(
                    self.mcp_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "qwen_analyze_screenshot",
                        "params": {
                            "screenshot_path": temp_path,
                            "task": prompt,
                            "include_history": False
                        },
                        "id": 1
                    }
                )
                data = resp.json()

                if "result" in data:
                    result = data["result"]
                    if "raw_response" in result:
                        return result["raw_response"]
                    elif "actions" in result:
                        desc = "UI Elements:\n"
                        for a in result["actions"][:5]:
                            desc += f"- {a.get('action', 'element')}"
                            if a.get('x') and a.get('y'):
                                desc += f" at ({a['x']}, {a['y']})"
                            desc += "\n"
                        return desc

                if "error" in data:
                    return f"[Qwen-VL Error: {data['error'].get('message', 'Unknown')}]"

        except Exception as e:
            return f"[Vision failed: {e}]"
    
    async def _gpt4_analyze(self, img: Image.Image, task: str) -> str:
        """
        GPT-4 Vision mit DEBUG-Logging.
        Speichert Screenshots und Analysen für Nachprüfung.
        """
        if not OPENAI_API_KEY:
            return "[No OpenAI key]"
        
        # DEBUG: Screenshot speichern
        debug_dir = Path("/tmp/v4_debug")
        debug_dir.mkdir(exist_ok=True)
        timestamp = int(time.time())
        screenshot_path = debug_dir / f"screenshot_{timestamp}.png"
        img.save(screenshot_path)
        log.info(f"   📸 Screenshot: {screenshot_path}")
        
        buf = BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        
        try:
            async with httpx.AsyncClient(timeout=self.gpt4_timeout) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"""BESCHREIBE diesen Screenshot für Web-Automation. NICHT programmieren - nur beschreiben!

Task: {task}

Beschreibe:
1. Welche Webseite ist das? (Amazon, Google, etc.)
2. Welche UI-Elemente siehst du? (Suchfeld, Buttons, Links)
3. Wo befinden sich die Elemente? (Positionen in Pixeln)
4. Was ist der aktuelle Zustand? (Ladebildschirm, Hauptseite, Ergebnisse)

Beispiel: "Amazon.de Homepage. Suchfeld oben mittig bei (950, 180). Cookie-Banner unten mit 'Akzeptieren' Button bei (850, 950)."

NUR beschreiben - kein Code!"""},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                            ]
                        }],
                        "max_tokens": 500  # Kürzer = präziser
                    }
                )
                data = resp.json()
                result = data["choices"][0]["message"]["content"]
                
                # DEBUG: Analyse speichern
                analysis_path = debug_dir / f"analysis_{timestamp}.txt"
                analysis_path.write_text(f"Task: {task}\n\nGPT-4 Analysis:\n{result}")
                log.info(f"   📝 Analyse: {analysis_path}")
                
                # Kurze Zusammenfassung loggen
                preview = result[:150].replace('\n', ' ')
                log.info(f"   🔍 Vision: {preview}...")
                
                return result
        except Exception as e:
            raise e


# ============================================================================
# HAUPT AGENT
# ============================================================================

@dataclass
class StepResult:
    step: int
    action: Dict
    success: bool
    error: Optional[str] = None


class VisualNemotronAgentV4:
    """
    Desktop-Automatisierung Agent v4.
    Nutzt echte Maus/Klick-Tools statt Playwright.
    """
    
    def __init__(self, mcp_url: str = MCP_URL):
        self.mcp = MCPToolClient(mcp_url)
        self.vision = VisionClient(mcp_url)
        self.nemotron = NemotronClient()
        self.desktop = DesktopController(self.mcp)
        self.loop_detector = LoopDetector()
        self.history: List[StepResult] = []
    
    async def execute_task(
        self,
        url: Optional[str],
        task_description: str,
        headless: bool = False,  # Ignoriert bei Desktop
        max_steps: int = 15
    ) -> Dict[str, Any]:
        """
        Führt einen Desktop-Task aus.
        
        Args:
            url: Optional - URL zum Öffnen (für Browser-Tasks)
            task_description: Was zu tun ist
            max_steps: Maximale Iterationen
        """
        log.info("="*60)
        log.info("🚀 VisualNemotronAgent v4 - Desktop Edition")
        log.info("="*60)
        log.info(f"   Task: {task_description[:60]}{'...' if len(task_description) > 60 else ''}")
        log.info(f"   Max Steps: {max_steps}")
        
        await self.desktop.start()
        
        try:
            # Optional: URL öffnen
            if url:
                log.info(f"\n🌐 Öffne URL: {url}")
                await self.desktop.execute_action({
                    "action": "navigate",
                    "url": url
                })
                await asyncio.sleep(2)
            
            # Erster Scan für UI-Elemente
            log.info("\n🔍 Initialer Scan...")
            elements = await self.desktop.scan_elements()
            
            for step in range(1, max_steps + 1):
                log.info(f"\n{'='*50}")
                log.info(f"STEP {step}/{max_steps}")
                log.info(f"{'='*50}")
                
                # 1. Screenshot
                screenshot = await self.desktop.screenshot()
                
                # 2. Vision-Analyse
                log.info("🧠 Analysiere Screenshot...")
                vision_desc = await self.vision.analyze(screenshot, task_description)
                log.info(f"   {vision_desc[:80]}...")
                
                # 3. Nemotron -> Aktionen
                log.info("🤖 Generiere Aktionen...")
                history_dict = [{"step": h.step, "action": h.action, "success": h.success} for h in self.history]
                
                nemotron_result = await self.nemotron.generate_step(
                    screenshot_description=vision_desc,
                    task_description=task_description,
                    step_history=history_dict,
                    available_elements=self.desktop.elements
                )
                
                # 4. Status prüfen
                status = nemotron_result.get("status", "in_progress")
                
                if status == "completed":
                    log.info("✅ Task von Nemotron als abgeschlossen markiert")
                    return self._result(True)
                
                if status == "blocked":
                    log.error("❌ Task blockiert")
                    return self._result(False, "Blocked by Nemotron")
                
                # 5. Aktionen ausführen
                actions = nemotron_result.get("actions", [])
                log.info(f"🎯 Führe {len(actions)} Aktion(en) aus...")
                
                step_success = True
                step_error = None
                
                for action in actions:
                    # Loop-Erkennung vor Ausführung
                    is_loop = self.loop_detector.add_state(screenshot, action)
                    if is_loop:
                        log.error("🔄 LOOP! Breche ab.")
                        return self._result(False, "Loop detected")

                    # Post-Action-Verify fuer click/type Aktionen
                    act_type = action.get("action", "").lower()
                    if act_type in ("click", "click_and_focus", "type"):
                        from utils.post_action_verify import verified_action
                        _, verify_summary = await verified_action(
                            capture_before_fn=lambda: self.desktop.mcp.call_tool("capture_screen_before_action", {}),
                            action_fn=lambda a=action: self.desktop.execute_action(a),
                            verify_after_fn=lambda timeout=5.0: self.desktop.mcp.call_tool("verify_action_result", {"timeout": timeout}),
                            check_errors_fn=lambda: self.desktop.mcp.call_tool("check_for_errors", {}),
                            action_name=act_type,
                        )
                        # execute_action gibt (done, error) zurueck
                        action_result = _ if isinstance(_, tuple) else (False, None)
                        done = action_result[0] if isinstance(action_result, tuple) else False
                        error = action_result[1] if isinstance(action_result, tuple) else None
                    else:
                        done, error = await self.desktop.execute_action(action)

                    if done:
                        return self._result(True)

                    if error and error.startswith("ASK_USER"):
                        return self._result(False, error)

                    if act_type in ("click", "click_and_focus") and not error:
                        await asyncio.sleep(0.8)  # UI Zeit zum Reagieren
                        self.desktop.elements = await self.desktop.scan_elements()

                    if error:
                        step_success = False
                        step_error = error
                        log.warning(f"   ⚠️ Aktion fehlgeschlagen: {error}")
                
                # Speichere Ergebnis
                self.history.append(StepResult(
                    step=step,
                    action=actions[0] if actions else {},
                    success=step_success,
                    error=step_error
                ))
                
                await asyncio.sleep(0.5)
            
            return self._result(False, "Max steps reached")
            
        except Exception as e:
            log.error(f"❌ Kritischer Fehler: {e}", exc_info=True)
            return self._result(False, str(e))
        
        finally:
            await self.desktop.stop()
    
    def _result(self, success: bool, error: Optional[str] = None) -> Dict:
        return {
            "success": success,
            "error": error,
            "steps": len(self.history),
            "unique_states": self.loop_detector.get_unique_states(),
            "history": [
                {
                    "step": h.step,
                    "action": h.action,
                    "success": h.success,
                    "error": h.error
                }
                for h in self.history
            ]
        }


# ============================================================================
# API
# ============================================================================

async def run_desktop_task(
    task: str,
    url: Optional[str] = None,
    max_steps: int = 15
) -> Dict[str, Any]:
    """
    Haupt-API für Desktop-Tasks.
    
    Beispiel:
        result = await run_desktop_task(
            task="Suche nach NVIDIA Grafikkarten",
            url="https://amazon.de"
        )
    """
    agent = VisualNemotronAgentV4()
    return await agent.execute_task(url, task, max_steps=max_steps)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Visual Nemotron Agent v4 (Desktop)")
    parser.add_argument("--task", required=True, help="Task-Beschreibung")
    parser.add_argument("--url", help="Optional: URL zum Öffnen")
    parser.add_argument("--max-steps", type=int, default=15, help="Maximale Schritte")
    
    args = parser.parse_args()
    
    result = asyncio.run(run_desktop_task(
        task=args.task,
        url=args.url,
        max_steps=args.max_steps
    ))
    
    print("\n" + "="*70)
    print(json.dumps(result, indent=2, ensure_ascii=False))

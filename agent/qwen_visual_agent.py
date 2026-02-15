# agent/qwen_visual_agent.py
# -*- coding: utf-8 -*-
"""
Qwen2-VL Visual Agent für Web-Automation mit lokaler GPU (RTX 3090).

Features:
- Qwen2-VL für Vision & UI-Understanding (lokal auf RTX 3090)
- Playwright für Browser-Steuerung
- PyAutoGUI für präzise Maus-Steuerung
- Strukturierte JSON-Aktionen (click, type, press, scroll, wait)
- Action-History für Kontext
- Retry-Logik bei Fehlern

Verfügbare Modelle:
    export QWEN_VL_MODEL=Qwen/Qwen2-VL-2B-Instruct  # Schnell, ~5GB VRAM (Default)
    export QWEN_VL_MODEL=Qwen/Qwen2-VL-7B-Instruct  # Besser, ~15GB VRAM

Benötigt:
    export QWEN_VL_ENABLED=1
    
Optional (für HuggingFace Download):
    export HF_TOKEN=dein_token_hier
"""

import os
import sys
import json
import time
import asyncio
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from io import BytesIO

from PIL import Image
from dotenv import load_dotenv

# --- Modulpfad-Korrektur ---
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Playwright
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# PyAutoGUI für Maus-Steuerung
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

# Qwen-VL Engine
from tools.engines.qwen_vl_engine import qwen_vl_engine_instance, UIAction
from tools.shared_context import log

# DOM-First Browser Controller Components
try:
    from tools.browser_controller.dom_parser import DOMParser
    from tools.browser_controller.state_tracker import UIStateTracker
    DOM_CONTROLLER_AVAILABLE = True
except ImportError:
    DOM_CONTROLLER_AVAILABLE = False
    log.warning("⚠️ Browser Controller nicht verfügbar — nur Vision-Modus")

# --- Konfiguration ---
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# Screenshot Konfiguration
SCREENSHOT_PATH = PROJECT_ROOT / "data" / "qwen_screenshots"
SCREENSHOT_PATH.mkdir(parents=True, exist_ok=True)

MAX_RETRIES = int(os.getenv("QWEN_MAX_RETRIES", "3"))
MAX_ITERATIONS = int(os.getenv("QWEN_MAX_ITERATIONS", "10"))
WAIT_BETWEEN_ACTIONS = float(os.getenv("QWEN_WAIT_BETWEEN_ACTIONS", "1.0"))

# Browser Konfiguration
HEADLESS = os.getenv("QWEN_HEADLESS", "0") == "1"
BROWSER_TYPE = os.getenv("QWEN_BROWSER", "chromium")  # chromium, firefox, webkit


@dataclass
class AgentStep:
    """Ein Schritt im Agent-Workflow"""
    iteration: int
    screenshot_path: str
    actions: List[Dict]
    success: bool
    error: Optional[str] = None
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class QwenVisualAgent:
    """
    Visual Agent für Web-Automation mit Qwen2.5-VL.
    Nutzt lokale RTX 3090 für schnelle Inference.
    """
    
    def __init__(self):
        self.engine = qwen_vl_engine_instance
        self.action_history: List[Dict] = []
        self.step_history: List[AgentStep] = []
        self.browser = None
        self.page = None
        self.playwright = None

        # Status
        self.is_running = False

        # Loop Detection
        self._prev_screenshot_hash: Optional[str] = None
        self._prev_actions_key: Optional[str] = None
        self._repeat_count: int = 0
        self._max_repeats: int = 2  # Nach 2 identischen Iterationen abbrechen

        # DOM-First Components
        if DOM_CONTROLLER_AVAILABLE:
            self.dom_parser = DOMParser()
            self.state_tracker = UIStateTracker(max_history=20)
            log.info("✅ DOM-First Modus aktiviert (DOMParser + StateTracker)")
        else:
            self.dom_parser = None
            self.state_tracker = None

        # Cookie-Banner Selectors
        self.cookie_selectors = [
            "button#onetrust-accept-btn-handler",
            "button[aria-label='Alle akzeptieren']",
            "button[aria-label='Accept all']",
            ".cmpboxbtnyes",
            ".fc-cta-consent",
            "[data-testid='cookie-banner-accept']",
            "button[data-accept-action='all']",
            "button:has-text('Accept')",
            "button:has-text('Akzeptieren')",
            "button:has-text('Alle akzeptieren')",
            "button:has-text('Zustimmen')",
        ]

        # Statistics
        self.stats = {'dom_actions': 0, 'vision_actions': 0, 'fallbacks': 0}

        if not self.engine.is_initialized():
            log.warning("⚠️ Qwen-VL Engine nicht initialisiert! Führe initialize() aus...")
            self.engine.initialize()
    
    def start_browser(self, headless: bool = False, browser_type: str = "chromium"):
        """Startet Playwright Browser"""
        log.info(f"🌐 Starte {browser_type} Browser (headless={headless})...")
        
        self.playwright = sync_playwright().start()
        
        if browser_type == "firefox":
            browser_launcher = self.playwright.firefox
        elif browser_type == "webkit":
            browser_launcher = self.playwright.webkit
        else:
            browser_launcher = self.playwright.chromium
        
        self.browser = browser_launcher.launch(headless=headless)
        self.page = self.browser.new_page()
        self.page.set_viewport_size({"width": 1920, "height": 1080})
        
        log.info("✅ Browser gestartet (Viewport: 1920x1080)")
    
    def stop_browser(self):
        """Stoppt Browser"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        log.info("🛑 Browser gestoppt")
    
    def take_screenshot(self, filename: Optional[str] = None) -> str:
        """Macht Screenshot der aktuellen Seite"""
        if filename is None:
            filename = f"screenshot_{len(self.step_history):03d}_{int(time.time())}.png"
        
        path = SCREENSHOT_PATH / filename
        self.page.screenshot(path=str(path), full_page=False)
        log.info(f"📸 Screenshot gespeichert: {path}")
        return str(path)
    
    def get_screenshot_pil(self) -> Image.Image:
        """Gibt aktuellen Screenshot als PIL Image zurück"""
        png_bytes = self.page.screenshot(full_page=False)
        return Image.open(BytesIO(png_bytes)).convert("RGB")
    
    def _handle_cookies(self):
        """Versucht Cookie-Banner automatisch zu schliessen (DOM-First)."""
        if not self.page:
            return
        for selector in self.cookie_selectors:
            try:
                elem = self.page.locator(selector)
                if elem.count() > 0 and elem.first.is_visible():
                    elem.first.click(timeout=2000)
                    log.info(f"🍪 Cookie-Banner akzeptiert: {selector}")
                    time.sleep(0.5)
                    return
            except Exception:
                continue

    def _get_dom_elements_summary(self) -> str:
        """Parst DOM und gibt eine kompakte Zusammenfassung interaktiver Elemente zurueck."""
        if not self.dom_parser or not self.page:
            return ""
        try:
            html = self.page.content()
            elements = self.dom_parser.parse(html)
            if not elements:
                return ""

            lines = []
            for i, el in enumerate(elements[:25]):  # Max 25 Elemente
                desc = el.tag
                if el.text:
                    desc += f" '{el.text[:40]}'"
                elif el.aria_label:
                    desc += f" label='{el.aria_label[:40]}'"
                elif el.placeholder:
                    desc += f" placeholder='{el.placeholder[:40]}'"
                if el.selector:
                    desc += f"  [{el.selector}]"
                lines.append(f"  {i+1}. {desc}")

            return "INTERAKTIVE DOM-ELEMENTE:\n" + "\n".join(lines)
        except Exception as e:
            log.debug(f"DOM-Parsing fehlgeschlagen: {e}")
            return ""

    def _try_dom_click(self, action: UIAction) -> bool:
        """
        Versucht Click via DOM (Playwright Selector) statt Koordinaten.
        Returns True wenn erfolgreich, False wenn Fallback noetig.
        """
        if not self.dom_parser or not self.page:
            return False

        try:
            html = self.page.content()
            self.dom_parser.parse(html)

            # Strategie 1: Suche nach Text in der Naehe des Klick-Ziels
            if action.text:
                matches = self.dom_parser.find_by_text(action.text, fuzzy=True)
                if matches:
                    selector = matches[0].selector
                    self.page.locator(selector).first.click(timeout=3000)
                    log.info(f"🎯 DOM-Click: {selector} (Text-Match: '{action.text}')")
                    self.stats['dom_actions'] += 1
                    return True

            # Strategie 2: Finde klickbare Elemente und waehle das naechste zu (x,y)
            if action.x is not None and action.y is not None:
                # Versuche Playwright locator.click an den Koordinaten
                try:
                    self.page.mouse.click(action.x, action.y)
                    log.info(f"🎯 DOM-Click: Playwright mouse.click({action.x}, {action.y})")
                    self.stats['dom_actions'] += 1
                    return True
                except Exception:
                    pass

            return False
        except Exception as e:
            log.debug(f"DOM-Click fehlgeschlagen: {e}")
            return False

    def _try_dom_type(self, action: UIAction) -> bool:
        """
        Versucht Type via DOM (Playwright) statt PyAutoGUI.
        Returns True wenn erfolgreich, False wenn Fallback noetig.
        """
        if not self.dom_parser or not self.page or not action.text:
            return False

        try:
            # Finde aktives/fokussiertes Element und tippe direkt
            self.page.keyboard.type(action.text, delay=50)
            log.info(f"⌨️  DOM-Type: '{action.text[:50]}' (Playwright keyboard)")
            self.stats['dom_actions'] += 1
            return True
        except Exception as e:
            log.debug(f"DOM-Type fehlgeschlagen: {e}")
            return False

    def _extract_search_terms(self, task: str) -> List[str]:
        """Extrahiert Suchbegriffe aus der Aufgabe fuer DOM-Rescue."""
        import re
        terms = []
        # "suche nach X", "hotels in X", "finde X"
        patterns = [
            r'(?:suche?\s+(?:nach\s+)?|finde?\s+|search\s+(?:for\s+)?)(.+?)(?:\s+auf\s+|\s+on\s+|$)',
            r'(?:hotels?\s+in\s+|flights?\s+to\s+|fluege?\s+nach\s+)(\w+)',
            r'(?:schau\s+nach\s+|look\s+for\s+)(.+?)(?:\s+auf\s+|\s+on\s+|$)',
        ]
        for p in patterns:
            m = re.search(p, task.lower())
            if m:
                terms.append(m.group(1).strip())
        # Fallback: alles nach "nach" oder "for"
        if not terms:
            m = re.search(r'(?:nach|for)\s+(.+?)(?:\s*$)', task.lower())
            if m:
                terms.append(m.group(1).strip())
        return terms

    def _dom_rescue(self, task: str) -> bool:
        """
        DOM-Rescue: Wenn Vision versagt, suche das Eingabefeld direkt im DOM
        und fuehre die Aufgabe via Playwright aus.

        Returns:
            True wenn Rescue erfolgreich, False wenn nicht
        """
        if not self.dom_parser or not self.page:
            return False

        try:
            log.info("🆘 DOM-Rescue: Suche Eingabefeld direkt im DOM...")
            html = self.page.content()
            elements = self.dom_parser.parse(html)

            # Finde Input/Textarea/Search-Elemente
            input_elements = [
                e for e in elements
                if e.tag in ('input', 'textarea')
                or e.role in ('searchbox', 'combobox', 'textbox')
            ]

            if not input_elements:
                log.warning("🆘 Keine Eingabefelder im DOM gefunden")
                return False

            log.info(f"🆘 {len(input_elements)} Eingabefelder gefunden:")
            for i, el in enumerate(input_elements):
                desc = self.dom_parser.describe_element(el)
                log.info(f"   {i+1}. {desc}  [{el.selector}]")

            # Waehle bestes Element: bevorzuge searchbox/combobox, dann placeholder-Match
            search_terms = self._extract_search_terms(task)
            best = None

            # Prioritaet 1: Rolle ist searchbox/combobox
            for el in input_elements:
                if el.role in ('searchbox', 'combobox'):
                    best = el
                    break

            # Prioritaet 2: Placeholder enthaelt relevante Woerter
            if not best:
                search_hints = ['such', 'search', 'reiseziel', 'destination', 'wohin', 'where', 'ort', 'city']
                for el in input_elements:
                    ph = (el.placeholder or '').lower()
                    aria = (el.aria_label or '').lower()
                    text = (el.text or '').lower()
                    combined = f"{ph} {aria} {text}"
                    if any(h in combined for h in search_hints):
                        best = el
                        break

            # Prioritaet 3: Erstes Input-Element
            if not best:
                best = input_elements[0]

            selector = best.selector
            log.info(f"🎯 DOM-Rescue: Klicke auf {self.dom_parser.describe_element(best)} [{selector}]")

            # Klick auf das Element
            try:
                self.page.locator(selector).first.click(timeout=3000)
            except Exception:
                # Fallback: click_by_text fuer Playwright
                if best.aria_label:
                    self.page.get_by_label(best.aria_label).first.click(timeout=3000)
                elif best.placeholder:
                    self.page.get_by_placeholder(best.placeholder).first.click(timeout=3000)
                else:
                    log.warning("🆘 Konnte Element nicht klicken")
                    return False

            time.sleep(0.5)

            # Text eingeben
            if search_terms:
                search_text = search_terms[0]
                log.info(f"⌨️  DOM-Rescue: Tippe '{search_text}'")
                self.page.keyboard.type(search_text, delay=50)
                time.sleep(1.0)

                # Enter druecken
                self.page.keyboard.press("Enter")
                log.info("⌨️  DOM-Rescue: Enter gedrueckt")
                time.sleep(2.0)

                self.stats['dom_actions'] += 3  # click + type + enter
                log.info("✅ DOM-Rescue erfolgreich!")
                return True
            else:
                log.warning("🆘 Keine Suchbegriffe aus Aufgabe extrahiert")
                self.stats['dom_actions'] += 1
                return True  # Zumindest geklickt

        except Exception as e:
            log.error(f"❌ DOM-Rescue fehlgeschlagen: {e}")
            return False

    def _observe_state(self):
        """Erfasst aktuellen UI-State fuer Loop-Detection."""
        if not self.state_tracker or not self.page:
            return
        try:
            html = self.page.content()
            url = self.page.url
            elements = []
            if self.dom_parser:
                parsed = self.dom_parser.parse(html)
                elements = [e.selector for e in parsed[:50]]
            self.state_tracker.observe(url=url, dom_content=html, visible_elements=elements)
        except Exception as e:
            log.debug(f"State-Observation fehlgeschlagen: {e}")

    def execute_action(self, action: UIAction) -> bool:
        """
        Fuehrt eine einzelne UI-Aktion aus.
        DOM-First: Versucht Playwright-Selectors, faellt zurueck auf PyAutoGUI.

        Returns:
            bool: True wenn Aktion "done" (Aufgabe erledigt), False sonst
        """
        act_type = action.action.lower()

        try:
            if act_type == "click":
                if action.x is None and action.y is None:
                    log.warning("⚠️  Click Aktion ohne Koordinaten")
                    return False

                # DOM-First: Playwright click
                if self._try_dom_click(action):
                    pass  # Erfolgreich via DOM
                elif PYAUTOGUI_AVAILABLE:
                    # Vision-Fallback: PyAutoGUI
                    pyautogui.moveTo(action.x, action.y, duration=0.2)
                    pyautogui.click()
                    log.info(f"🖱️  Vision-Click: ({action.x}, {action.y})")
                    self.stats['vision_actions'] += 1
                    self.stats['fallbacks'] += 1
                else:
                    self.page.mouse.click(action.x, action.y)
                    log.info(f"🖱️  Playwright-Click: ({action.x}, {action.y})")

            elif act_type == "type":
                if not action.text:
                    log.warning("⚠️  Type Aktion ohne Text")
                    return False

                # DOM-First: Playwright keyboard
                if self._try_dom_type(action):
                    pass  # Erfolgreich via DOM
                elif PYAUTOGUI_AVAILABLE:
                    pyautogui.write(action.text, interval=0.05)
                    log.info(f"⌨️  Vision-Type: '{action.text[:50]}'")
                    self.stats['vision_actions'] += 1
                    self.stats['fallbacks'] += 1
                else:
                    self.page.keyboard.type(action.text)
                    log.info(f"⌨️  Playwright-Type: '{action.text[:50]}'")

            elif act_type == "press":
                key = action.key or "Enter"
                # Press immer via Playwright (zuverlaessiger als PyAutoGUI)
                try:
                    self.page.keyboard.press(key)
                except Exception:
                    if PYAUTOGUI_AVAILABLE:
                        pyautogui.press(key.lower())
                log.info(f"⌨️  Press: {key}")

            elif act_type == "scroll_up":
                amount = action.y or 300
                self.page.mouse.wheel(0, -amount)
                log.info(f"📜 Scroll up: {amount}")

            elif act_type == "scroll_down":
                amount = action.y or 300
                self.page.mouse.wheel(0, amount)
                log.info(f"📜 Scroll down: {amount}")

            elif act_type == "wait":
                secs = action.seconds or 2.0
                log.info(f"⏳ Wait: {secs}s")
                time.sleep(secs)

            elif act_type == "done":
                log.info("✅ Aufgabe als erledigt markiert")
                return True

            else:
                log.warning(f"⚠️  Nicht unterstuetzte Aktion: {act_type}")
                return False

            # Kurze Pause nach jeder Aktion
            time.sleep(WAIT_BETWEEN_ACTIONS)
            return False  # Nicht done

        except Exception as e:
            log.error(f"❌ Fehler bei Aktion {act_type}: {e}")
            return False
    
    def run_task(
        self, 
        url: str, 
        task: str, 
        max_iterations: int = MAX_ITERATIONS,
        headless: bool = HEADLESS,
        browser_type: str = BROWSER_TYPE
    ) -> Dict[str, Any]:
        """
        Haupt-Methode: Führt eine Web-Automation Aufgabe aus.
        
        Args:
            url: Start-URL
            task: Aufgabenbeschreibung (z.B. "Klicke auf Login und gib Email ein")
            max_iterations: Maximale Anzahl Iterationen
            headless: Browser im Hintergrund starten
            browser_type: chromium, firefox, webkit
            
        Returns:
            Dict mit Ergebnis, History und Status
        """
        if not self.engine.is_initialized():
            return {
                "success": False,
                "error": "Qwen-VL Engine nicht initialisiert",
                "steps": []
            }
        
        self.is_running = True
        self.action_history = []
        self.step_history = []
        
        try:
            # Browser starten
            self.start_browser(headless=headless, browser_type=browser_type)
            
            # Zu URL navigieren
            log.info(f"🌐 Navigiere zu: {url}")
            self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(2)  # Warte auf initiales Rendering

            # Cookie-Banner automatisch handlen
            self._handle_cookies()

            # Initiale State-Observation
            self._observe_state()
            
            # Haupt-Loop
            done = False
            for iteration in range(1, max_iterations + 1):
                if not self.is_running:
                    log.info("🛑 Agent gestoppt")
                    break
                
                log.info(f"\n=== Iteration {iteration}/{max_iterations} ===")
                
                # Screenshot machen
                screenshot = self.get_screenshot_pil()
                screenshot_path = self.take_screenshot(f"step_{iteration:03d}.png")

                # Loop Detection: Screenshot-Hash pruefen
                img_hash = hashlib.md5(screenshot.tobytes()).hexdigest()
                if img_hash == self._prev_screenshot_hash:
                    self._repeat_count += 1
                    log.warning(f"⚠️  Identischer Screenshot erkannt ({self._repeat_count}/{self._max_repeats})")
                    if self._repeat_count >= self._max_repeats:
                        log.warning("🔄 Loop erkannt — starte DOM-Rescue statt Abbruch...")
                        if self._dom_rescue(task):
                            self._repeat_count = 0
                            self._prev_screenshot_hash = None
                            self._prev_actions_key = None
                            continue  # Naechste Iteration mit neuem Screenshot
                        else:
                            log.warning("🛑 DOM-Rescue fehlgeschlagen. Breche ab.")
                            break
                else:
                    self._repeat_count = 0
                self._prev_screenshot_hash = img_hash

                # DOM-Elemente als Kontext fuer Qwen-VL
                dom_summary = self._get_dom_elements_summary()

                # Qwen-VL Analyse (mit DOM-Kontext)
                log.info("🧠 Analysiere mit Qwen-VL...")
                enhanced_task = task
                if dom_summary:
                    enhanced_task = f"{task}\n\n{dom_summary}"
                result = self.engine.analyze_screenshot(
                    image=screenshot,
                    task=enhanced_task,
                    history=self.action_history
                )
                
                if not result["success"]:
                    log.error(f"❌ Analyse fehlgeschlagen: {result.get('error', 'Unbekannter Fehler')}")
                    step = AgentStep(
                        iteration=iteration,
                        screenshot_path=screenshot_path,
                        actions=[],
                        success=False,
                        error=result.get("error")
                    )
                    self.step_history.append(step)
                    continue
                
                # Aktionen extrahieren
                actions = result["actions"]
                log.info(f"📋 Gefundene Aktionen: {len(actions)}")
                for i, act in enumerate(actions):
                    log.info(f"   {i+1}. {act.action}" +
                             (f" ({act.x}, {act.y})" if act.x and act.y else "") +
                             (f" '{act.text}'" if act.text else ""))

                # Loop Detection: Gleiche Aktionen wie vorher?
                actions_dict = [asdict(a) for a in actions]
                actions_key = json.dumps([(a["action"], a.get("x"), a.get("y"), a.get("text")) for a in actions_dict])
                if actions_key == self._prev_actions_key:
                    self._repeat_count += 1
                    log.warning(f"⚠️  Identische Aktionen wie vorherige Iteration ({self._repeat_count}/{self._max_repeats})")
                    if self._repeat_count >= self._max_repeats:
                        log.warning("🔄 Actions-Loop erkannt — starte DOM-Rescue...")
                        if self._dom_rescue(task):
                            self._repeat_count = 0
                            self._prev_screenshot_hash = None
                            self._prev_actions_key = None
                            continue  # Naechste Iteration
                        else:
                            log.warning("🛑 DOM-Rescue fehlgeschlagen. Breche ab.")
                            break
                self._prev_actions_key = actions_key
                step = AgentStep(
                    iteration=iteration,
                    screenshot_path=screenshot_path,
                    actions=actions_dict,
                    success=True
                )
                self.step_history.append(step)
                
                for action in actions:
                    is_done = self.execute_action(action)
                    self.action_history.append(asdict(action))
                    
                    if is_done:
                        done = True
                        break
                
                if done:
                    log.info("✅ Aufgabe erfolgreich abgeschlossen!")
                    break

                # State nach Aktionen beobachten
                self._observe_state()

                # DOM-basierte Loop-Detection (zusaetzlich zu Screenshot-Hash)
                if self.state_tracker and self.state_tracker.detect_loop(window=3):
                    log.warning("🔄 DOM-Loop erkannt — starte DOM-Rescue...")
                    if self._dom_rescue(task):
                        self.state_tracker.clear_history()
                        continue
                    else:
                        log.warning("🛑 DOM-Rescue fehlgeschlagen. Breche ab.")
                        break

                # Warte auf Seiten-Update
                time.sleep(1.5)
            
            else:
                log.warning(f"⚠️  Maximale Iterationen ({max_iterations}) erreicht")
            
            # Stats loggen
            log.info(f"📊 Statistik: DOM={self.stats['dom_actions']} | Vision={self.stats['vision_actions']} | Fallbacks={self.stats['fallbacks']}")

            return {
                "success": done,
                "completed": done,
                "iterations": len(self.step_history),
                "steps": [asdict(s) for s in self.step_history],
                "final_url": self.page.url if self.page else None,
                "stats": self.stats
            }
            
        except Exception as e:
            log.error(f"❌ Kritischer Fehler: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "steps": [asdict(s) for s in self.step_history]
            }
        
        finally:
            self.is_running = False
            self.stop_browser()
    
    def stop(self):
        """Stoppt den Agent"""
        self.is_running = False


def run_web_automation(
    url: str, 
    task: str,
    headless: bool = False,
    max_iterations: int = 10
) -> Dict[str, Any]:
    """
    Einfache Funktion für Web-Automation mit Qwen-VL.
    
    Beispiel:
        result = run_web_automation(
            url="https://www.t-online.de",
            task="Finde den Login-Button oben rechts und klicke darauf"
        )
    """
    agent = QwenVisualAgent()
    return agent.run_task(
        url=url,
        task=task,
        headless=headless,
        max_iterations=max_iterations
    )


if __name__ == "__main__":
    # Beispiel-Ausführung
    import argparse
    
    parser = argparse.ArgumentParser(description="Qwen2.5-VL Visual Agent für Web-Automation")
    parser.add_argument("--url", default="https://www.google.com", help="Start-URL")
    parser.add_argument("--task", required=True, help="Aufgabenbeschreibung")
    parser.add_argument("--headless", action="store_true", help="Headless-Modus")
    parser.add_argument("--iterations", type=int, default=10, help="Max. Iterationen")
    
    args = parser.parse_args()
    
    # Führe Aufgabe aus
    result = run_web_automation(
        url=args.url,
        task=args.task,
        headless=args.headless,
        max_iterations=args.iterations
    )
    
    # Ergebnis ausgeben
    print("\n" + "="*60)
    print("ERGEBNIS:")
    print("="*60)
    print(json.dumps(result, indent=2, default=str))
    
    if result["success"]:
        print("\n✅ Aufgabe erfolgreich abgeschlossen!")
    else:
        print("\n❌ Aufgabe nicht abgeschlossen.")

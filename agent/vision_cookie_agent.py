# agent/vision_cookie_agent.py
"""
Vision Cookie Agent - Qwen-VL Vision + Cookie-Handling + Stabilitäts-Checks.

Features:
- Automatisches Cookie-Banner Handling
- Stabilitäts-Checks (Browser-Context Überwachung)
- Auto-Retry bei geschlossenem Browser
- Screenshot-Backup für jeden Schritt
"""

import os
import sys
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from io import BytesIO
from datetime import datetime

from PIL import Image

# Setup
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# Playwright
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

# Qwen-VL
from tools.engines.qwen_vl_engine import qwen_vl_engine_instance, UIAction

# Cookie Handler
from tools.cookie_banner_tool.tool import (
    wait_for_and_handle_cookie_banner,
    dismiss_overlays_and_popups
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s'
)
log = logging.getLogger("VisionCookieAgent")


@dataclass
class AgentStep:
    iteration: int
    screenshot_path: str
    actions: List[Dict]
    success: bool
    error: Optional[str] = None
    timestamp: float = 0.0


class VisionCookieAgent:
    """
    Vision Agent mit Cookie-Handling und Stabilitäts-Checks.
    """

    def __init__(self):
        self.qwen_engine = qwen_vl_engine_instance
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.action_history: List[Dict] = []
        self.step_history: List[AgentStep] = []
        self.screenshot_dir = PROJECT_ROOT / "data" / "vision_cookie_screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """Initialisiert Qwen-VL (nur falls nicht bereits vom MCP geladen)"""
        # Prüfe ob bereits vom MCP-Server initialisiert
        if self.qwen_engine.is_initialized():
            log.info("✅ Qwen-VL bereits vom MCP-Server geladen - nutze bestehende Instanz")
            info = self.qwen_engine.get_model_info()
            log.info(f"   Modell: {info['model_name']}, VRAM: {info['vram_used_gb']:.1f} GB")
            return
        
        # Nur initialisieren wenn nicht bereits geladen
        log.info("🚀 Initialisiere Qwen-VL...")
        self.qwen_engine.initialize()
        if self.qwen_engine.is_initialized():
            info = self.qwen_engine.get_model_info()
            log.info(f"✅ Qwen-VL bereit ({info['model_name']}, {info['vram_used_gb']:.1f} GB)")
        else:
            raise RuntimeError("Qwen-VL Initialisierung fehlgeschlagen")

    async def start_browser(self, headless: bool = False) -> bool:
        """
        Startet Browser mit verbesserten Stabilitäts-Settings.

        Returns:
            bool: True wenn erfolgreich
        """
        log.info(f"🌐 Starte Chromium (headless={headless})...")

        try:
            self.playwright = await async_playwright().start()

            # Browser mit Stabilitäts-Args - Firefox für mehr Stabilität
            browser_type = os.getenv("PLAYWRIGHT_BROWSER", "firefox")
            
            if browser_type == "firefox":
                log.info("🦊 Verwende Firefox (stabiler für Media-Seiten)")
                browser_launcher = self.playwright.firefox
            elif browser_type == "webkit":
                log.info("🧭 Verwende WebKit (Safari-Engine)")
                browser_launcher = self.playwright.webkit
            else:
                log.info("🌐 Verwende Chromium")
                browser_launcher = self.playwright.chromium
            
            self.browser = await browser_launcher.launch(
                headless=headless
            )

            # Context mit realistischem User-Agent
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1536, "height": 864},
                locale="de-DE",
                timezone_id="Europe/Berlin",
            )

            self.page = await self.context.new_page()

            # Event-Handler für Crashes
            self.page.on("crash", lambda: log.error("❌ Browser-Tab abgestürzt!"))
            self.page.on("close", lambda: log.warning("⚠️ Browser-Tab geschlossen"))

            log.info("✅ Browser bereit (1536x864, de-DE)")
            return True

        except Exception as e:
            log.error(f"❌ Browser-Start fehlgeschlagen: {e}")
            return False

    async def stop_browser(self):
        """Stoppt Browser sicher"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            log.info("🛑 Browser gestoppt")
        except Exception as e:
            log.warning(f"Browser-Stop Fehler (ignoriert): {e}")

    async def safe_screenshot(self, filename: str) -> str:
        """
        Macht Screenshot mit Fehler-Handling.

        Returns:
            Pfad zum Screenshot oder leerer String bei Fehler
        """
        try:
            if not self.page or self.page.is_closed():
                log.error("❌ Seite geschlossen, kein Screenshot möglich")
                return ""

            path = self.screenshot_dir / filename
            await self.page.screenshot(path=str(path), full_page=False)
            log.info(f"📸 Screenshot: {path.name}")
            return str(path)

        except Exception as e:
            log.error(f"❌ Screenshot fehlgeschlagen: {e}")
            return ""

    async def check_page_alive(self) -> bool:
        """Prüft ob die Seite noch lebt"""
        try:
            if not self.page:
                return False
            if self.page.is_closed():
                return False
            # Einfacher JS-Check
            await self.page.evaluate("1")
            return True
        except:
            return False

    async def analyze_with_vision(self, task: str) -> Dict[str, Any]:
        """Analysiert mit Qwen-VL"""
        try:
            # Screenshot
            png_bytes = await self.page.screenshot(full_page=False)
            image = Image.open(BytesIO(png_bytes)).convert("RGB")

            # Prompt - vermeide Kollisionen mit JSON-Formatierung
            system_prompt = """Du bist ein UI-Automatisierungs-Experte.

Aufgabe: """ + task + """

Koordinaten-Bereich: 0-1535 (x), 0-863 (y)

WICHTIGE REGELN:
1. Identifiziere exakte Element-Positionen
2. Cookie-Banner: Akzeptiere oder ignoriere
3. Gib präzise (x,y) für Klicks
4. Keine Erklärungen, nur JSON

ANTWORT (nur JSON-Array):
[{"action": "click", "x": 750, "y": 400}, {"action": "done"}]"""

            result = self.qwen_engine.analyze_screenshot(
                image=image,
                task=task,
                history=self.action_history,
                system_prompt=system_prompt
            )

            return result

        except Exception as e:
            log.error(f"❌ Vision-Analyse fehlgeschlagen: {e}")
            return {"success": False, "error": str(e), "actions": []}

    async def execute_action(self, action: UIAction) -> bool:
        """Führt Aktion aus mit Checks"""
        act_type = action.action.lower()

        try:
            # Prüfe Seite
            if not await self.check_page_alive():
                log.error("❌ Seite nicht mehr verfügbar")
                return False

            if act_type == "click":
                if action.x is not None and action.y is not None:
                    await self.page.mouse.click(action.x, action.y)
                    log.info(f"🖱️  Click ({action.x}, {action.y})")

            elif act_type == "type":
                if action.text:
                    await self.page.keyboard.type(action.text)
                    log.info(f"⌨️  Type: {action.text[:30]}...")

            elif act_type == "press":
                key = action.key or "Enter"
                await self.page.keyboard.press(key)
                log.info(f"⌨️  Press: {key}")

            elif act_type == "wait":
                secs = action.seconds or 1.5
                await asyncio.sleep(secs)
                log.info(f"⏳ Wait {secs}s")

            elif act_type == "done":
                log.info("✅ Done!")
                return True

            await asyncio.sleep(0.5)
            return False

        except Exception as e:
            log.error(f"❌ Aktion fehlgeschlagen: {e}")
            return False

    async def run_task(
        self,
        url: str,
        task: str,
        max_iterations: int = 10,
        headless: bool = False,
        auto_cookies: bool = True,
        cookie_wait: int = 5
    ) -> Dict[str, Any]:
        """
        Haupt-Methode mit Cookie-Handling.
        """
        await self.initialize()

        self.action_history = []
        self.step_history = []

        try:
            # 1. Browser starten
            if not await self.start_browser(headless=headless):
                return {"success": False, "error": "Browser konnte nicht starten"}

            # 2. Zu URL navigieren
            log.info(f"🌐 Navigiere zu: {url}")
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                log.warning(f"⚠️ Navigations-Fehler: {e}, versuche weiter...")

            await asyncio.sleep(2)

            # 3. Cookie-Banner behandeln
            if auto_cookies:
                cookie_result = await wait_for_and_handle_cookie_banner(
                    self.page,
                    auto_accept=True,
                    max_wait_seconds=cookie_wait
                )
                if cookie_result["handled"]:
                    log.info("✅ Cookie-Banner automatisch akzeptiert")
                    await asyncio.sleep(1)

            # 4. Weitere Overlays schließen
            await dismiss_overlays_and_popups(self.page)

            # 5. Haupt-Loop
            done = False
            for iteration in range(1, max_iterations + 1):
                log.info(f"\n=== Iteration {iteration}/{max_iterations} ===")

                # Prüfe Seite
                if not await self.check_page_alive():
                    log.error("❌ Seite geschlossen, breche ab")
                    break

                # Screenshot
                timestamp = datetime.now().strftime("%H%M%S")
                screenshot_path = await self.safe_screenshot(f"step_{iteration:03d}_{timestamp}.png")

                # Vision-Analyse
                log.info("🧠 Vision-Analyse...")
                analysis = await self.analyze_with_vision(task)

                if not analysis["success"]:
                    error_msg = analysis.get("error", "Unbekannter Fehler")
                    log.error(f"❌ Analyse: {error_msg}")

                    step = AgentStep(
                        iteration=iteration,
                        screenshot_path=screenshot_path,
                        actions=[],
                        success=False,
                        error=error_msg
                    )
                    self.step_history.append(step)

                    # Bei OOM: Versuche zu bereinigen und weiter
                    if "out of memory" in error_msg.lower():
                        log.warning("⚠️ OOM erkannt, versuche Cache-Leerung...")
                        import torch
                        torch.cuda.empty_cache()
                        await asyncio.sleep(2)
                        continue
                    break

                # Aktionen ausführen
                actions = analysis["actions"]
                log.info(f"📋 {len(actions)} Aktionen gefunden")

                step = AgentStep(
                    iteration=iteration,
                    screenshot_path=screenshot_path,
                    actions=[{"action": a.action, "x": a.x, "y": a.y, "text": a.text} for a in actions],
                    success=True
                )
                self.step_history.append(step)

                for action in actions:
                    is_done = await self.execute_action(action)
                    self.action_history.append({
                        "action": action.action,
                        "x": action.x,
                        "y": action.y,
                        "text": action.text
                    })
                    if is_done:
                        done = True
                        break

                if done:
                    break

                await asyncio.sleep(1)

            return {
                "success": done,
                "completed": done,
                "iterations": len(self.step_history),
                "steps": [
                    {
                        "iteration": s.iteration,
                        "screenshot": s.screenshot_path,
                        "actions": s.actions,
                        "success": s.success,
                        "error": s.error
                    }
                    for s in self.step_history
                ],
                "final_url": self.page.url if self.page else None
            }

        except Exception as e:
            log.error(f"❌ Kritischer Fehler: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "steps": []
            }

        finally:
            await self.stop_browser()


async def run_vision_cookie_task(
    url: str,
    task: str,
    headless: bool = False,
    max_iterations: int = 10
) -> Dict[str, Any]:
    """Einfache Wrapper-Funktion"""
    agent = VisionCookieAgent()
    return await agent.run_task(
        url=url,
        task=task,
        headless=headless,
        max_iterations=max_iterations
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    result = asyncio.run(run_vision_cookie_task(
        url=args.url,
        task=args.task,
        headless=args.headless
    ))
    print(json.dumps(result, indent=2, default=str))

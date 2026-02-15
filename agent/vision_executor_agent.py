# agent/vision_executor_agent.py
"""
VisionExecutorAgent - Kombiniert Qwen-VL (Vision) mit Executor (Aktionen).

Konzept:
- Qwen-VL analysiert Screenshots und gibt präzise Koordinaten
- Executor führt die Aktionen mit PyAutoGUI/Playwright aus
- Best of both worlds: Präzision + Zuverlässigkeit

Features:
- Qwen2-VL für Pixel-genaues UI-Understanding
- Lokale GPU (RTX 3090) - keine API-Latenz
- Automatische Fehlerkorrektur
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

from PIL import Image

# Setup
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# Playwright
from playwright.async_api import async_playwright

# Qwen-VL Engine
try:
    from tools.engines.qwen_vl_engine import qwen_vl_engine_instance, UIAction
    QWEN_AVAILABLE = True
except ImportError:
    QWEN_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s'
)
log = logging.getLogger("VisionExecutorAgent")


@dataclass
class VisionStep:
    """Ein Schritt mit Vision-Analyse"""
    iteration: int
    screenshot_path: str
    actions: List[Dict]
    success: bool
    error: Optional[str] = None


class VisionExecutorAgent:
    """
    Agent der Qwen-VL für Vision und Executor für Aktionen nutzt.
    """

    def __init__(self):
        self.qwen_engine = qwen_vl_engine_instance if QWEN_AVAILABLE else None
        self.browser = None
        self.page = None
        self.playwright = None
        self.action_history: List[Dict] = []
        self.step_history: List[VisionStep] = []

    async def initialize(self):
        """
        Prüft Qwen-VL Verfügbarkeit.
        WICHTIG: Nutzt das MCP-Tool 'qwen_web_automation' statt direktes Laden,
        da der Vision Agent in einem SEPARATEN Prozess läuft als der MCP-Server!
        """
        # Prüfe ob Qwen-VL im MCP-Server verfügbar ist (via Health Check)
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:5000",
                    json={"jsonrpc": "2.0", "method": "qwen_vl_health", "id": 1},
                    timeout=5.0
                )
                data = response.json()
                if data.get("result", {}).get("status") == "healthy":
                    log.info("✅ Qwen-VL im MCP-Server verfügbar - nutze via RPC")
                    self.use_mcp_tool = True
                    return
        except Exception:
            pass
        
        # Fallback: Lokale Instanz (nur wenn im selben Prozess wie MCP)
        if self.qwen_engine and self.qwen_engine.is_initialized():
            log.info("✅ Qwen-VL bereits geladen (selber Prozess)")
            self.use_mcp_tool = False
        else:
            log.error("❌ Qwen-VL nicht verfügbar - MCP-Server läuft nicht oder Modell nicht geladen")
            raise RuntimeError("Bitte MCP-Server zuerst starten: python server/mcp_server.py")

    async def start_browser(self, headless: bool = False):
        """Startet Browser"""
        log.info(f"🌐 Starte Browser (headless={headless})...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=headless)
        self.page = await self.browser.new_page()
        await self.page.set_viewport_size({"width": 1536, "height": 864})
        log.info("✅ Browser bereit (1536x864)")

    async def stop_browser(self):
        """Stoppt Browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        log.info("🛑 Browser gestoppt")

    async def take_screenshot(self) -> Image.Image:
        """Macht Screenshot"""
        png_bytes = await self.page.screenshot(full_page=False)
        return Image.open(BytesIO(png_bytes)).convert("RGB")

    async def analyze_with_qwen(self, task: str) -> Dict[str, Any]:
        """
        Analysiert Screenshot mit Qwen-VL.

        Args:
            task: Beschreibung was zu tun ist

        Returns:
            Dict mit actions, success, error
        """
        if not self.qwen_engine or not self.qwen_engine.is_initialized():
            return {"success": False, "error": "Qwen-VL nicht verfügbar", "actions": []}

        try:
            screenshot = await self.take_screenshot()

            # Prompt optimiert für Koordinaten-Extraktion
            system_prompt = f"""Du bist ein präziser UI-Analyst. Analysiere den Screenshot.

Aufgabe: {task}

WICHTIG - Gib EXAKTE Koordinaten zurück:
1. Identifiziere das Ziel-Element
2. Gib die MITTE des Elements als (x, y) zurück
3. Koordinatenbereich: 0-1535 (x), 0-863 (y)

ANTWORT FORMAT (nur JSON):
[
  {{"action": "click", "x": 750, "y": 400}},
  {{"action": "type", "text": "Beispieltext"}},
  {{"action": "press", "key": "Enter"}},
  {{"action": "done"}}
]

Regeln:
- "click" braucht x, y
- "type" braucht text
- "press" braucht key (Enter, Tab)
- "done" markiert Aufgabe erledigt
- Maximal 3 Aktionen pro Schritt
- KEINE Erklärungen, nur JSON!"""

            result = self.qwen_engine.analyze_screenshot(
                image=screenshot,
                task=task,
                history=self.action_history,
                system_prompt=system_prompt
            )

            return result

        except Exception as e:
            log.error(f"❌ Qwen-Analyse fehlgeschlagen: {e}")
            return {"success": False, "error": str(e), "actions": []}

    async def execute_action(self, action: UIAction) -> bool:
        """
        Führt eine Aktion mit Playwright aus.

        Returns:
            True wenn done, False sonst
        """
        act_type = action.action.lower()

        try:
            if act_type == "click":
                if action.x is not None and action.y is not None:
                    await self.page.mouse.click(action.x, action.y)
                    log.info(f"🖱️  Click bei ({action.x}, {action.y})")

            elif act_type == "type":
                if action.text:
                    await self.page.keyboard.type(action.text)
                    log.info(f"⌨️  Type: {action.text[:30]}{'...' if len(action.text) > 30 else ''}")

            elif act_type == "press":
                key = action.key or "Enter"
                await self.page.keyboard.press(key)
                log.info(f"⌨️  Press: {key}")

            elif act_type == "scroll_up":
                await self.page.mouse.wheel(0, -300)
                log.info("📜 Scroll up")

            elif act_type == "scroll_down":
                await self.page.mouse.wheel(0, 300)
                log.info("📜 Scroll down")

            elif act_type == "wait":
                secs = action.seconds or 1.5
                await asyncio.sleep(secs)
                log.info(f"⏳ Wait {secs}s")

            elif act_type == "done":
                log.info("✅ Aufgabe erledigt!")
                return True

            # Kurze Pause nach Aktion
            await asyncio.sleep(0.5)
            return False

        except Exception as e:
            log.error(f"❌ Fehler bei Aktion {act_type}: {e}")
            return False

    async def run_task(
        self,
        url: str,
        task: str,
        max_iterations: int = 8,
        headless: bool = False
    ) -> Dict[str, Any]:
        """
        Haupt-Methode: Vision + Execution.

        Args:
            url: Start-URL
            task: Aufgabenbeschreibung
            max_iterations: Max. Schritte
            headless: Browser sichtbar?

        Returns:
            Ergebnis-Dict
        """
        if not QWEN_AVAILABLE:
            return {"success": False, "error": "Qwen-VL nicht verfügbar"}

        await self.initialize()

        self.action_history = []
        self.step_history = []

        try:
            await self.start_browser(headless=headless)

            # Zu URL navigieren
            log.info(f"🌐 Navigiere zu: {url}")
            await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2)

            done = False
            for iteration in range(1, max_iterations + 1):
                log.info(f"\n=== Iteration {iteration}/{max_iterations} ===")

                # 1. Qwen-VL analysiert Screenshot
                log.info("🧠 Qwen-VL analysiert Bildschirm...")
                analysis = await self.analyze_with_qwen(task)

                if not analysis["success"]:
                    log.error(f"❌ Analyse fehlgeschlagen: {analysis.get('error')}")
                    step = VisionStep(
                        iteration=iteration,
                        screenshot_path="",
                        actions=[],
                        success=False,
                        error=analysis.get("error")
                    )
                    self.step_history.append(step)
                    continue

                # 2. Aktionen ausführen
                actions = analysis["actions"]
                log.info(f"📋 Gefundene Aktionen: {len(actions)}")

                for i, act in enumerate(actions):
                    log.info(f"   {i+1}. {act.action}" +
                             (f" ({act.x}, {act.y})" if act.x and act.y else "") +
                             (f" '{act.text}'" if act.text else ""))

                step = VisionStep(
                    iteration=iteration,
                    screenshot_path="",
                    actions=[{"action": a.action, "x": a.x, "y": a.y, "text": a.text} for a in actions],
                    success=True
                )
                self.step_history.append(step)

                # 3. Jede Aktion ausführen
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
                        "actions": s.actions,
                        "success": s.success,
                        "error": s.error
                    }
                    for s in self.step_history
                ],
                "final_url": self.page.url
            }

        except Exception as e:
            log.error(f"❌ Kritischer Fehler: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "steps": [
                    {
                        "iteration": s.iteration,
                        "actions": s.actions,
                        "success": s.success
                    }
                    for s in self.step_history
                ]
            }

        finally:
            await self.stop_browser()


# Globaler Agent für einfachen Zugriff
vision_agent = VisionExecutorAgent()


async def run_vision_task(
    url: str,
    task: str,
    headless: bool = False,
    max_iterations: int = 8
) -> Dict[str, Any]:
    """
    Einfache Funktion für Vision-basierte Tasks.

    Beispiel:
        result = await run_vision_task(
            url="https://www.t-online.de",
            task="Klicke auf E-Mail Login oben rechts"
        )
    """
    agent = VisionExecutorAgent()
    return await agent.run_task(
        url=url,
        task=task,
        headless=headless,
        max_iterations=max_iterations
    )


if __name__ == "__main__":
    # Test
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://www.google.com")
    parser.add_argument("--task", required=True)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    result = asyncio.run(run_vision_task(
        url=args.url,
        task=args.task,
        headless=args.headless
    ))
    print(json.dumps(result, indent=2, default=str))

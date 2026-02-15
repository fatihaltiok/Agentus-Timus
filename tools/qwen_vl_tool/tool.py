# tools/qwen_vl_tool/tool.py
"""
Qwen2.5-VL Tool für MCP-Server Integration.

Ermöglicht Web-Automation mit lokalem Qwen2.5-VL Modell auf RTX 3090.

Features:
- Lokale GPU-Inference (keine API-Kosten)
- Strukturierte UI-Aktionen
- Screenshot-Analyse
- Multi-Step Workflows
"""

import logging
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
import asyncio

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# --- Setup ---
log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Qwen Visual Agent importieren
sys.path.insert(0, str(PROJECT_ROOT))
try:
    from agent.qwen_visual_agent import QwenVisualAgent, run_web_automation
    from tools.engines.qwen_vl_engine import qwen_vl_engine_instance
    QWEN_AGENT_AVAILABLE = True
except ImportError as e:
    QWEN_AGENT_AVAILABLE = False
    log.warning(f"⚠️ Qwen Visual Agent nicht verfügbar: {e}")


@tool(
    name="qwen_vl_health",
    description="Health-Check für das Qwen-VL Tool. Gibt Status der Qwen-VL Engine zurück.",
    parameters=[],
    capabilities=["vision", "qwen"],
    category=C.VISION
)
async def qwen_vl_health() -> dict:
    """
    Health-Check für das Qwen-VL Tool.

    Returns:
        Status der Qwen-VL Engine
    """
    try:
        if not QWEN_AGENT_AVAILABLE:
            raise Exception("Qwen Visual Agent nicht verfügbar.")

        engine = qwen_vl_engine_instance

        return {
            "status": "healthy" if engine.is_initialized() else "not_initialized",
            "available": QWEN_AGENT_AVAILABLE,
            "model_info": engine.get_model_info() if engine.is_initialized() else None
        }

    except Exception as e:
        raise Exception(f"Health-Check fehlgeschlagen: {e}")


@tool(
    name="qwen_web_automation",
    description="Führt Web-Automation mit Qwen2.5-VL aus. Nutzt lokales Vision-Language-Modell (RTX 3090) für Screenshot-Analyse, UI-Element-Erkennung und Multi-Step Navigation.",
    parameters=[
        P("url", "string", "Start-URL der Webseite", required=True),
        P("task", "string", "Aufgabenbeschreibung (z.B. 'Klicke auf Login-Button oben rechts')", required=True),
        P("headless", "boolean", "Browser unsichtbar starten", required=False, default=False),
        P("max_iterations", "integer", "Maximale Anzahl Schritte", required=False, default=10),
        P("wait_between_actions", "number", "Pause zwischen Aktionen in Sekunden", required=False, default=1.0),
    ],
    capabilities=["vision", "qwen"],
    category=C.VISION
)
async def qwen_web_automation(
    url: str,
    task: str,
    headless: bool = False,
    max_iterations: int = 10,
    wait_between_actions: float = 1.0
) -> dict:
    """
    Führt Web-Automation mit Qwen2.5-VL aus.

    Nutzt lokales Vision-Language-Modell (RTX 3090) für:
    - Screenshot-Analyse
    - UI-Element-Erkennung
    - Koordinaten-Extraktion
    - Multi-Step Navigation

    Args:
        url: Start-URL der Webseite
        task: Aufgabenbeschreibung (z.B. "Klicke auf Login-Button oben rechts")
        headless: Browser unsichtbar starten (default: False)
        max_iterations: Maximale Anzahl Schritte (default: 10)
        wait_between_actions: Pause zwischen Aktionen in Sekunden (default: 1.0)

    Returns:
        dict mit Ergebnis

    Beispiel:
        qwen_web_automation(
            url="https://www.t-online.de",
            task="Finde den E-Mail-Login-Bereich, klicke darauf und gib 'test@example.de' ein",
            headless=false,
            max_iterations=8
        )
    """
    try:
        if not QWEN_AGENT_AVAILABLE:
            raise Exception("Qwen Visual Agent nicht verfügbar. Engine nicht geladen?")

        engine = qwen_vl_engine_instance
        if not engine.is_initialized():
            raise Exception("Qwen-VL Engine nicht initialisiert. Setze QWEN_VL_ENABLED=1 und starte Server neu.")

        # Setze temporäre Konfiguration
        os.environ["QWEN_WAIT_BETWEEN_ACTIONS"] = str(wait_between_actions)

        log.info(f"🚀 Qwen Web Automation startet...")
        log.info(f"   URL: {url}")
        log.info(f"   Task: {task[:80]}...")

        # Führe Automation aus (in Thread-Pool für Non-Blocking)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_web_automation(
                url=url,
                task=task,
                headless=headless,
                max_iterations=max_iterations
            )
        )

        if result.get("success"):
            return {
                "success": True,
                "completed": result.get("completed", False),
                "iterations": result.get("iterations", 0),
                "steps": result.get("steps", []),
                "final_url": result.get("final_url"),
                "message": "Automation erfolgreich abgeschlossen"
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unbekannter Fehler"),
                "steps": result.get("steps", []),
                "completed": False
            }

    except Exception as e:
        log.error(f"❌ Fehler in qwen_web_automation: {e}", exc_info=True)
        raise Exception(f"Automation fehlgeschlagen: {str(e)}")


@tool(
    name="qwen_analyze_screenshot",
    description="Analysiert einen Screenshot mit Qwen2.5-VL und gibt erkannte UI-Aktionen zurück.",
    parameters=[
        P("screenshot_path", "string", "Pfad zum Screenshot-Bild", required=True),
        P("task", "string", "Aufgabenbeschreibung für Kontext", required=True),
        P("include_history", "boolean", "Ob Aktions-History einbezogen werden soll", required=False, default=False),
    ],
    capabilities=["vision", "qwen"],
    category=C.VISION
)
async def qwen_analyze_screenshot(
    screenshot_path: str,
    task: str,
    include_history: bool = False
) -> dict:
    """
    Analysiert einen Screenshot mit Qwen2.5-VL.

    Args:
        screenshot_path: Pfad zum Screenshot-Bild
        task: Aufgabenbeschreibung für Kontext
        include_history: Ob Aktions-History einbezogen werden soll

    Returns:
        dict mit erkannten Aktionen
    """
    try:
        if not QWEN_AGENT_AVAILABLE:
            raise Exception("Qwen Visual Agent nicht verfügbar")

        engine = qwen_vl_engine_instance
        if not engine.is_initialized():
            raise Exception("Qwen-VL Engine nicht initialisiert")

        from PIL import Image

        # Lade Bild
        image = Image.open(screenshot_path).convert("RGB")

        # Analysiere
        result = engine.analyze_screenshot(
            image=image,
            task=task,
            history=[] if not include_history else None
        )

        if result["success"]:
            actions = [
                {
                    "action": a.action,
                    "x": a.x,
                    "y": a.y,
                    "text": a.text,
                    "key": a.key,
                    "seconds": a.seconds
                }
                for a in result["actions"]
            ]

            return {
                "success": True,
                "actions": actions,
                "raw_response": result["raw_response"]
            }
        else:
            raise Exception(f"Analyse fehlgeschlagen: {result.get('error')}")

    except Exception as e:
        # Bei OOM: Versuche Cache zu leeren für nächsten Aufruf
        if "out of memory" in str(e).lower() or "CUDA" in str(e):
            try:
                import torch
                import gc
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()
                    log.warning("🧹 CUDA Cache geleert nach OOM")
            except:
                pass
        raise Exception(f"Screenshot-Analyse fehlgeschlagen: {e}")

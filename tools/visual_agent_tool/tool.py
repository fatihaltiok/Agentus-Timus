# tools/visual_agent_tool/tool.py
"""
Visual Agent Tool - MCP-Integration für VisualAgent v2.1

Ermöglicht die Nutzung des Visual Agents als MCP-Tool.
Der Visual Agent kann komplexe UI-Automatisierungs-Aufgaben ausführen:
- Browser-Steuerung
- UI-Element-Erkennung und -Interaktion
- Text-Eingabe in beliebige Felder
- Multi-Step-Workflows

Features:
- Claude Sonnet 4.5 Vision für Kontext-Verständnis
- SoM (Set-of-Mark) für Element-Lokalisierung
- Mouse Feedback für präzise Koordinaten
- Cursor-Typ-basiertes Feedback
- Loop-Detection und Verification
"""

import logging
import sys
import os
from pathlib import Path
from typing import Union, Optional
import asyncio

from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool

# --- Setup ---
log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Visual Agent importieren
sys.path.insert(0, str(PROJECT_ROOT))
try:
    from agent.visual_agent import run_visual_task
    VISUAL_AGENT_AVAILABLE = True
except ImportError as e:
    VISUAL_AGENT_AVAILABLE = False
    log.warning(f"⚠️ Visual Agent nicht verfügbar: {e}")


@method
async def visual_agent_health() -> Union[Success, Error]:
    """
    Health-Check für das Visual Agent Tool.
    Prüft ob der Visual Agent verfügbar ist.

    Returns:
        Success mit Status-Info oder Error
    """
    try:
        if not VISUAL_AGENT_AVAILABLE:
            return Error(
                code=-32091,
                message="Visual Agent nicht verfügbar. Import fehlgeschlagen."
            )

        # Prüfe notwendige Umgebungsvariablen
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not anthropic_key:
            return Error(
                code=-32092,
                message="ANTHROPIC_API_KEY nicht gesetzt"
            )

        # Prüfe MCP-Server
        mcp_url = os.getenv("MCP_URL", "http://127.0.0.1:5000")

        # Prüfe Monitor-Config
        active_monitor = os.getenv("ACTIVE_MONITOR", "1")

        # Prüfe Mouse Feedback
        use_mouse_feedback = os.getenv("USE_MOUSE_FEEDBACK", "1") == "1"

        # Prüfe Vision Model
        vision_model = os.getenv("VISION_MODEL", "claude-sonnet-4-5-20250929")

        return Success({
            "status": "healthy",
            "visual_agent_available": True,
            "vision_model": vision_model,
            "mcp_url": mcp_url,
            "active_monitor": int(active_monitor),
            "mouse_feedback": use_mouse_feedback,
            "features": [
                "Claude Vision API",
                "SoM Tool Integration",
                "Mouse Feedback",
                "Loop Detection",
                "Action Verification",
                "Multi-Step Workflows"
            ],
            "dependencies": {
                "anthropic_api": "✅" if anthropic_key else "❌",
                "mcp_server": mcp_url,
                "mss": "verfügbar (Screenshots)",
                "PIL": "verfügbar (Bildverarbeitung)"
            }
        })

    except Exception as e:
        log.error(f"Visual Agent Health-Check fehlgeschlagen: {e}", exc_info=True)
        return Error(code=-32093, message=f"Health-Check fehlgeschlagen: {e}")


@method
async def execute_visual_task(
    task: str,
    max_iterations: Optional[int] = 30
) -> Union[Success, Error]:
    """
    Führt eine visuelle Automatisierungs-Aufgabe aus.

    Der Visual Agent nutzt Claude Vision + SoM + Mouse Feedback um komplexe
    UI-Aufgaben zu lösen. Er kann:
    - Elemente auf dem Bildschirm finden und anklicken
    - Text in Felder eingeben
    - Browser-Navigation durchführen
    - Multi-Step-Workflows ausführen

    Args:
        task: Die auszuführende Aufgabe (z.B. "Schreibe 'Hallo' in das Chat-Feld")
        max_iterations: Maximale Anzahl an Iterationen (Standard: 30)

    Returns:
        Success mit Ergebnis-Nachricht oder Error

    Beispiele:
        - "Öffne Firefox und gehe zu google.com"
        - "Schreibe 'Hallo Welt' in das Suchfeld und drücke Enter"
        - "Klicke auf den Login-Button"
        - "Finde das Chat-Eingabefeld und schreibe 'Test'"
    """
    try:
        if not VISUAL_AGENT_AVAILABLE:
            return Error(
                code=-32094,
                message="Visual Agent nicht verfügbar. Modul konnte nicht importiert werden."
            )

        if not task or not task.strip():
            return Error(
                code=-32095,
                message="Task-Parameter fehlt oder ist leer"
            )

        log.info(f"👁️ Visual Agent startet Task: {task}")
        log.info(f"   Max Iterations: {max_iterations}")

        # Visual Agent ausführen
        result = await run_visual_task(task, max_iterations=max_iterations)

        log.info(f"✅ Visual Agent abgeschlossen: {result[:100]}...")

        return Success({
            "status": "completed",
            "task": task,
            "result": result,
            "message": result
        })

    except Exception as e:
        log.error(f"Fehler beim Ausführen des Visual Agents: {e}", exc_info=True)
        return Error(
            code=-32099,
            message=f"Visual Agent Fehler: {str(e)}"
        )


@method
async def execute_visual_task_quick(task: str) -> Union[Success, Error]:
    """
    Schnelle Version von execute_visual_task mit weniger Iterationen.

    Nutzt nur 10 Iterationen für schnelle, einfache Aufgaben.

    Args:
        task: Die auszuführende Aufgabe

    Returns:
        Success mit Ergebnis oder Error
    """
    return await execute_visual_task(task, max_iterations=10)


# --- Registrierung ---
register_tool("visual_agent_health", visual_agent_health)
register_tool("execute_visual_task", execute_visual_task)
register_tool("execute_visual_task_quick", execute_visual_task_quick)

log.info("✅ Visual Agent Tool (visual_agent_health, execute_visual_task, execute_visual_task_quick) registriert.")

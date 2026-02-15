# tools/reflection_tool/tool.py
import os
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import textwrap
import asyncio

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger(__name__)

# Definiere den Pfad zum Logbuch
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    LEARNING_LOG_FILE = LOG_DIR / "logbuch.md"
    log.info(f"Logbuch wird nach '{LEARNING_LOG_FILE}' geschrieben.")
except Exception as e:
    log.error(f"Konnte Log-Verzeichnis nicht erstellen: {e}")
    LEARNING_LOG_FILE = None


def _write_log_sync(entry_content: str):
    """
    Synchrone Hilfsfunktion, die die eigentliche Schreiboperation ausführt.
    Diese wird in einem separaten Thread aufgerufen.
    """
    if not LEARNING_LOG_FILE:
        raise IOError("Pfad zum Logbuch ist nicht konfiguriert.")

    with open(LEARNING_LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + entry_content.strip() + "\n")

@tool(
    name="log_learning_entry",
    description="Erstellt einen strukturierten Eintrag im Logbuch asynchron.",
    parameters=[
        P("goal", "string", "Das Ziel des Eintrags", required=True),
        P("outcome", "string", "Das Ergebnis (z.B. SUCCESS, FAILURE)", required=True),
        P("details", "object", "Details als Dictionary", required=True),
        P("learning", "string", "Erkenntnis / Gelerntes", required=True),
    ],
    capabilities=["memory", "reflection", "learning"],
    category=C.MEMORY
)
async def log_learning_entry(
    goal: str,
    outcome: str,
    details: Dict[str, Any],
    learning: str
) -> dict:
    """
    Erstellt einen strukturierten Eintrag im Logbuch asynchron.
    """
    if not LEARNING_LOG_FILE:
        raise Exception("Pfad zum Logbuch ist nicht konfiguriert.")

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = textwrap.dedent(f"""
        ---
        ### Logbuch-Eintrag: {timestamp}

        **🎯 Ziel:**
        {goal}

        **🏁 Ergebnis:** `{outcome.upper()}`

        **⚙️ Details:**
        ```json
        {json.dumps(details, indent=2, ensure_ascii=False)}
        ```

        **🧠 Erkenntnis / Gelerntes:**
        {learning}
        """)

        # Führe die blockierende Schreiboperation in einem Thread aus
        await asyncio.to_thread(_write_log_sync, entry)

        log.info("Eintrag ins Logbuch erfolgreich geschrieben.")
        return {"status": "logged"}

    except Exception as e:
        log.error(f"Fehler beim Schreiben ins Logbuch: {e}", exc_info=True)
        return {"status": "error", "message": f"Fehler beim Schreiben ins Logbuch: {e}"}

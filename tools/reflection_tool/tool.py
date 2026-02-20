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


def _engine():
    from memory.reflection_engine import get_reflection_engine

    return get_reflection_engine()


@tool(
    name="reflection_analyze_visual_patterns",
    description="Analysiert Debug-Artefakte und erstellt adaptive Vision-Vorschlaege (nur pending, keine Auto-Aktivierung).",
    parameters=[
        P("debug_dir", "string", "Optionaler Pfad zu Debug-Artefakten (JSON).", required=False, default=None),
        P("config_path", "string", "Optionaler Pfad zur vision_adaptive_config.json.", required=False, default=None),
        P("min_occurrences", "integer", "Minimale Wiederholungen fuer einen Vorschlag.", required=False, default=2),
        P("limit", "integer", "Maximale Anzahl analysierter Artefakte.", required=False, default=300),
    ],
    capabilities=["memory", "reflection", "vision", "adaptive"],
    category=C.MEMORY,
)
async def reflection_analyze_visual_patterns(
    debug_dir: str | None = None,
    config_path: str | None = None,
    min_occurrences: int = 2,
    limit: int = 300,
) -> dict:
    return await asyncio.to_thread(
        _engine().analyze_visual_failures,
        debug_dir,
        config_path,
        min_occurrences,
        limit,
    )


@tool(
    name="reflection_list_pending_adaptations",
    description="Listet alle pending Vision-Anpassungen auf, die eine manuelle Freigabe brauchen.",
    parameters=[
        P("config_path", "string", "Optionaler Pfad zur vision_adaptive_config.json.", required=False, default=None),
    ],
    capabilities=["memory", "reflection", "vision", "adaptive"],
    category=C.MEMORY,
)
async def reflection_list_pending_adaptations(config_path: str | None = None) -> dict:
    pending = await asyncio.to_thread(_engine().list_pending_vision_adaptations, config_path)
    return {"count": len(pending), "pending_changes": pending}


@tool(
    name="reflection_approve_adaptation",
    description="Genehmigt einen pending Vision-Vorschlag und aktiviert ihn im active Config-Bereich.",
    parameters=[
        P("change_id", "string", "ID des pending Vorschlags.", required=True),
        P("approved_by", "string", "Freigebende Person oder Rolle.", required=True),
        P("notes", "string", "Optionaler Freigabe-Kommentar.", required=False, default=""),
        P("config_path", "string", "Optionaler Pfad zur vision_adaptive_config.json.", required=False, default=None),
    ],
    capabilities=["memory", "reflection", "vision", "adaptive"],
    category=C.MEMORY,
)
async def reflection_approve_adaptation(
    change_id: str,
    approved_by: str,
    notes: str = "",
    config_path: str | None = None,
) -> dict:
    return await asyncio.to_thread(
        _engine().approve_vision_adaptation,
        change_id,
        approved_by,
        config_path,
        notes,
    )


@tool(
    name="reflection_reject_adaptation",
    description="Lehnt einen pending Vision-Vorschlag ab (keine Aktivierung).",
    parameters=[
        P("change_id", "string", "ID des pending Vorschlags.", required=True),
        P("rejected_by", "string", "Ablehnende Person oder Rolle.", required=True),
        P("reason", "string", "Optionaler Ablehnungsgrund.", required=False, default=""),
        P("config_path", "string", "Optionaler Pfad zur vision_adaptive_config.json.", required=False, default=None),
    ],
    capabilities=["memory", "reflection", "vision", "adaptive"],
    category=C.MEMORY,
)
async def reflection_reject_adaptation(
    change_id: str,
    rejected_by: str,
    reason: str = "",
    config_path: str | None = None,
) -> dict:
    return await asyncio.to_thread(
        _engine().reject_vision_adaptation,
        change_id,
        rejected_by,
        reason,
        config_path,
    )

# tools/timing_tool/tool.py

import logging
import asyncio

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger(__name__)

@tool(
    name="wait",
    description="Pausiert die Ausfuehrung fuer eine angegebene Anzahl von Sekunden.",
    parameters=[
        P("seconds", "integer", "Anzahl der Sekunden zum Warten", required=True),
    ],
    capabilities=["system", "timing"],
    category=C.SYSTEM
)
async def wait(seconds: int) -> dict:
    """
    Pausiert die Ausführung für eine angegebene Anzahl von Sekunden.
    """
    if not isinstance(seconds, int) or seconds <= 0:
        raise Exception("Parameter 'seconds' muss eine positive ganze Zahl sein.")

    try:
        log.info(f"Warte für {seconds} Sekunde(n)...")
        await asyncio.sleep(seconds)
        log.info("Wartezeit beendet.")
        return {"status": "wait_completed", "duration_seconds": seconds}
    except Exception as e:
        log.error(f"Fehler im 'wait'-Tool: {e}", exc_info=True)
        raise Exception(f"Ein unerwarteter Fehler ist beim Warten aufgetreten: {e}")

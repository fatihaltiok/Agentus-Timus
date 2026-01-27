# tools/timing_tool/tool.py

import logging
import asyncio
from typing import Union

from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool

log = logging.getLogger(__name__)

@method
async def wait(seconds: int) -> Union[Success, Error]:
    """
    Pausiert die Ausführung für eine angegebene Anzahl von Sekunden.
    """
    if not isinstance(seconds, int) or seconds <= 0:
        return Error(code=-32602, message="Parameter 'seconds' muss eine positive ganze Zahl sein.")
    
    try:
        log.info(f"Warte für {seconds} Sekunde(n)...")
        await asyncio.sleep(seconds)
        log.info("Wartezeit beendet.")
        return Success({"status": "wait_completed", "duration_seconds": seconds})
    except Exception as e:
        log.error(f"Fehler im 'wait'-Tool: {e}", exc_info=True)
        return Error(code=-32000, message=f"Ein unerwarteter Fehler ist beim Warten aufgetreten: {e}")

register_tool("wait", wait)
log.info("✅ Timing-Tool (wait) registriert.")
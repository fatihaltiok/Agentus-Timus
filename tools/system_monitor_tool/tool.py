# tools/system_monitor_tool/tool.py

import logging
import psutil
import asyncio

# V2 Tool Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# Logger für dieses spezifische Tool
log = logging.getLogger(__name__)

def _get_system_usage_sync():
    """
    Diese synchrone Funktion kapselt die blockierende psutil-Logik.
    """
    try:
        # CPU-Auslastung über 1 Sekunde messen. Dies ist ein blockierender Aufruf.
        cpu_usage = psutil.cpu_percent(interval=1)

        # Speicher-Infos holen
        memory_info = psutil.virtual_memory()

        # Festplatten-Infos für das Root-Verzeichnis holen
        disk_info = psutil.disk_usage('/')

        # Daten in einem Dictionary zurückgeben
        return {
            'cpu_percent': cpu_usage,
            'memory': {
                'total_mb': round(memory_info.total / (1024 ** 2)),
                'used_mb': round(memory_info.used / (1024 ** 2)),
                'percent': memory_info.percent
            },
            'disk': {
                'total_gb': round(disk_info.total / (1024 ** 3)),
                'used_gb': round(disk_info.used / (1024 ** 3)),
                'percent': disk_info.percent
            }
        }
    except Exception as e:
        # Wenn hier ein Fehler passiert, wird er an den aufrufenden Thread weitergegeben
        log.error(f"Fehler beim Abrufen der System-Metriken: {e}", exc_info=True)
        raise e

@tool(
    name="get_system_usage",
    description="Ruft die aktuelle CPU-, Speicher- und Festplattenauslastung des Systems ab.",
    parameters=[],
    capabilities=["system", "monitoring"],
    category=C.SYSTEM
)
async def get_system_usage() -> dict:
    """
    Ruft die aktuelle CPU-, Speicher- und Festplattenauslastung des Systems ab.
    Diese Funktion ist als asynchroner RPC-Endpunkt verfügbar.
    """
    log.info("Rufe Systemauslastung ab...")
    try:
        # Führe die blockierende synchrone Funktion in einem separaten Thread aus,
        # um den Server nicht anzuhalten.
        usage_data = await asyncio.to_thread(_get_system_usage_sync)

        return usage_data

    except Exception as e:
        log.error(f"Konnte Systemauslastung nicht abrufen: {e}", exc_info=True)
        raise Exception(f"Fehler im System Monitor Tool: {e}")

# Der if __name__ == "__main__"-Block ist super für schnelle, isolierte Tests.
if __name__ == '__main__':
    async def main_test():
        print("Führe isolierten Test für get_system_usage aus...")
        # Simuliere den asynchronen Aufruf
        result = await get_system_usage()
        # Drucke das Ergebnis im JSON-Format
        import json
        print(json.dumps(result, indent=2))

    # Führe den asynchronen Test aus
    asyncio.run(main_test())

# tools/system_monitor_tool/tool.py

import logging
import psutil
import asyncio
from typing import Union

from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool

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

@method
async def get_system_usage() -> Union[Success, Error]:
    """
    Ruft die aktuelle CPU-, Speicher- und Festplattenauslastung des Systems ab.
    Diese Funktion ist als asynchroner RPC-Endpunkt verfügbar.
    """
    log.info("📊 Rufe Systemauslastung ab...")
    try:
        # Führe die blockierende synchrone Funktion in einem separaten Thread aus,
        # um den Server nicht anzuhalten.
        usage_data = await asyncio.to_thread(_get_system_usage_sync)
        
        return Success(usage_data)
        
    except Exception as e:
        log.error(f"Konnte Systemauslastung nicht abrufen: {e}", exc_info=True)
        # Gib einen standardisierten JSON-RPC-Fehler zurück
        return Error(code=-32015, message=f"Fehler im System Monitor Tool: {e}")

# Registriere das Tool beim Server
register_tool("get_system_usage", get_system_usage)

log.info("✅ System Monitor Tool (get_system_usage) registriert.")

# Der if __name__ == "__main__"-Block ist super für schnelle, isolierte Tests.
if __name__ == '__main__':
    async def main_test():
        print("Führe isolierten Test für get_system_usage aus...")
        # Simuliere den asynchronen Aufruf
        result = await get_system_usage()
        # Drucke das Ergebnis im JSON-Format
        import json
        if isinstance(result, Success):
            print(json.dumps(result.result, indent=2))
        else:
            print(json.dumps(result.data, indent=2))

    # Führe den asynchronen Test aus
    asyncio.run(main_test())
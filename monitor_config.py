# ~/dev/timus/monitor_config.py
"""
Zentrale Monitor-Konfiguration für Timus.

Stellt einheitliche Funktionen bereit, um:
- Den aktiven Monitor zu ermitteln
- Monitor-Grenzen abzurufen
- Relative Koordinaten in absolute umzuwandeln (für PyAutoGUI)

Wird von mouse_tool, som_tool, verification_tool und VisualAgent importiert.
"""

import os
import logging
from typing import Dict, Tuple
import mss

log = logging.getLogger(__name__)

# Aktiver Monitor aus .env (Standard: 1)
def get_active_monitor() -> int:
    """Gibt die ID des aktiven Monitors zurück."""
    monitor_id = int(os.getenv("ACTIVE_MONITOR", "1"))
    log.debug(f"Aktiver Monitor aus .env: {monitor_id}")
    return monitor_id

def get_monitor_bounds(monitor_id: int = None) -> Dict[str, int]:
    """
    Gibt die Grenzen des angegebenen Monitors zurück.
    
    Args:
        monitor_id: Optional – falls None, wird ACTIVE_MONITOR verwendet
    
    Returns:
        Dict mit left, top, width, height
    """
    if monitor_id is None:
        monitor_id = get_active_monitor()
    
    try:
        with mss.mss() as sct:
            if monitor_id < len(sct.monitors):
                mon = sct.monitors[monitor_id]
            else:
                mon = sct.monitors[1]  # Fallback auf primären Monitor
                log.warning(f"Monitor {monitor_id} nicht gefunden → Fallback auf Monitor 1")
            
            bounds = {
                "left": mon["left"],
                "top": mon["top"],
                "width": mon["width"],
                "height": mon["height"]
            }
            log.debug(f"Monitor {monitor_id} Bounds: {bounds}")
            return bounds
    except Exception as e:
        log.error(f"Fehler beim Abruf der Monitor-Bounds: {e}")
        # Fallback: Annahme eines einzelnen Monitors bei (0,0)
        return {"left": 0, "top": 0, "width": 1920, "height": 1200}

def convert_relative_to_absolute(x: int, y: int, monitor_id: int = None) -> Tuple[int, int]:
    """
    Wandelt relative Koordinaten (bezogen auf den Monitor) in absolute um.
    
    Wichtig für PyAutoGUI, das absolute Koordinaten über alle Monitore erwartet.
    """
    bounds = get_monitor_bounds(monitor_id)
    abs_x = x + bounds["left"]
    abs_y = y + bounds["top"]
    log.debug(f"Relative ({x}, {y}) → Absolute ({abs_x}, {abs_y}) [Monitor {monitor_id or get_active_monitor()}]")
    return abs_x, abs_y

log.info("monitor_config.py geladen – zentrale Monitor-Logik bereit")
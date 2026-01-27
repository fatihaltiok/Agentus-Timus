# tools/visual_browser_tool/tool.py

import logging
import subprocess
import sys
import platform
import shutil
import time
import asyncio
from typing import Optional, Union

from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool

log = logging.getLogger("visual_browser_tool")

# --- Globale Prozess-Verwaltung ---
# Wir speichern die Prozesse, um sie später schließen zu können
active_browsers = {}

def _get_browser_command(browser_type: str, url: Optional[str] = None) -> list[str]:
    """
    Ermittelt den korrekten Startbefehl für das Betriebssystem.
    """
    system = platform.system().lower()
    
    # Standardisierung des Namens
    if "chrome" in browser_type.lower():
        target = "chrome"
    elif "firefox" in browser_type.lower():
        target = "firefox"
    else:
        target = "default"

    cmd = []
    
    if system == "windows":
        # Windows nutzt "start", aber subprocess braucht hier shell=True
        if target == "chrome":
            cmd = ["start", "chrome", "--new-window"]
        elif target == "firefox":
            cmd = ["start", "firefox", "--new-window"]
        else:
            cmd = ["start"]
            
    elif system == "darwin": # macOS
        if target == "chrome":
            cmd = ["open", "-a", "Google Chrome", "--args", "--new-window"]
        elif target == "firefox":
            cmd = ["open", "-a", "Firefox", "--args", "--new-window"]
        else:
            cmd = ["open"]
            
    else: # Linux
        if target == "chrome":
            # Versuche verschiedene gängige Namen
            exe = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
            if exe:
                cmd = [exe, "--new-window"]
        elif target == "firefox":
            exe = shutil.which("firefox")
            if exe:
                cmd = [exe, "--new-window"]
        
        # Fallback wenn nichts gefunden wurde
        if not cmd:
            cmd = ["xdg-open"]

    # URL anhängen
    if url:
        cmd.append(url)
    elif target != "default" and not url:
        # Manche Browser brauchen eine Start-URL oder about:blank, um nicht die letzte Session zu laden
        cmd.append("about:blank")

    return cmd

@method
async def start_visual_browser(url: str = "https://www.google.com", browser_type: str = "firefox") -> dict:
    """
    Startet einen SICHTBAREN Webbrowser auf dem Desktop.
    
    Args:
        url: Die zu öffnende URL.
        browser_type: 'firefox', 'chrome' oder 'default'.
    """
    log.info(f"🚀 Starte visuellen Browser ({browser_type}) mit URL: {url}")
    
    # Prüfe ob bereits ein Browser dieses Typs von uns verwaltet wird
    if browser_type in active_browsers:
        proc = active_browsers[browser_type]
        if proc.poll() is None: # Läuft noch
            log.info(f"Browser {browser_type} läuft bereits. Öffne URL dort.")
            return await open_url_in_visual_browser(url)

    try:
        cmd = _get_browser_command(browser_type, url)
        
        if not cmd:
             return Error(code=-32001, message=f"Konnte keinen Befehl für Browser '{browser_type}' finden.")

        log.info(f"Ausführen des Befehls: {cmd}")
        
        # Windows 'start' benötigt shell=True
        use_shell = (platform.system().lower() == "windows")
        
        # Prozess starten
        proc = subprocess.Popen(cmd, shell=use_shell)
        
        # Prozess speichern
        active_browsers[browser_type] = proc
        
        # Wichtig: Dem Browser Zeit geben, sichtbar zu werden, bevor der Agent den nächsten Screenshot macht
        await asyncio.sleep(3)
        
        return Success({
            "status": "started", 
            "message": f"Browser ({browser_type}) gestartet und URL {url} geladen.",
            "pid": proc.pid
        })
        
    except Exception as e:
        log.error(f"Fehler beim Browser-Start: {e}", exc_info=True)
        return Error(code=-32000, message=f"Browser konnte nicht gestartet werden: {str(e)}")

@method
async def open_url_in_visual_browser(url: str) -> dict:
    """
    Öffnet eine URL im Standard-Browser des Systems (oder einem neuen Tab).
    Dies ist robuster als zu versuchen, in die Adressleiste zu klicken.
    """
    import webbrowser
    log.info(f"🌐 Öffne URL via System-Call: {url}")
    
    try:
        # Wir nutzen Python's webbrowser modul, das ist extrem robust
        # Es findet automatisch den laufenden Browser und öffnet einen Tab
        await asyncio.to_thread(webbrowser.open, url, new=2)
        
        # Warten auf Laden der Seite
        await asyncio.sleep(2)
        
        return Success({
            "status": "opened", 
            "url": url, 
            "message": "URL wurde an den aktiven Browser gesendet."
        })
    except Exception as e:
        return Error(code=-32002, message=f"Konnte URL nicht öffnen: {e}")

@method
async def close_visual_browser(browser_type: str = "firefox") -> dict:
    """Versucht, den vom Agenten gestarteten Browser zu schließen."""
    if browser_type in active_browsers:
        proc = active_browsers[browser_type]
        try:
            if platform.system().lower() == "windows":
                subprocess.run(f"taskkill /PID {proc.pid} /T /F", shell=True)
            else:
                proc.terminate()
            
            del active_browsers[browser_type]
            return Success({"status": "closed", "browser": browser_type})
        except Exception as e:
            return Error(code=-32003, message=f"Fehler beim Schließen: {e}")
    
    return Error(code=-32004, message="Browser nicht gefunden oder nicht von mir gestartet.")

# Registrierung
register_tool("start_visual_browser", start_visual_browser)
register_tool("open_url_in_visual_browser", open_url_in_visual_browser)
register_tool("close_visual_browser", close_visual_browser)
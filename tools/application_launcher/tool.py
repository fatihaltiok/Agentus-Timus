# tools/application_launcher/tool.py

import os
import sys
import asyncio
import logging
import subprocess
import shutil
import platform

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger("application_launcher")

# Erweiterte Liste für verschiedene Betriebssysteme
APPLICATION_COMMANDS = {
    # Browser
    "firefox": ["firefox", "firefox.exe"],
    "chrome": ["google-chrome", "chrome", "chrome.exe", "chromium"],
    "edge": ["msedge", "microsoft-edge"],

    # System
    "calculator": ["gnome-calculator", "calc", "calc.exe", "kcalc", "open -a Calculator"],
    "terminal": ["gnome-terminal", "cmd.exe", "powershell.exe", "open -a Terminal", "konsole"],
    "explorer": ["nautilus", "explorer.exe", "open .", "dolphin"],
    "file manager": ["nautilus", "explorer.exe", "open .", "dolphin", "thunar"],

    # Tools
    "editor": ["gedit", "notepad.exe", "notepad", "code", "TextEdit"],
    "notepad": ["notepad.exe", "notepad"],
    "vscode": ["code"],
}

@tool(
    name="open_application",
    description="Startet eine Anwendung auf dem Desktop (Cross-Platform).",
    parameters=[
        P("app_name", "string", "Name der zu startenden Anwendung", required=True),
        P("wait_for_start", "boolean", "Ob auf den Start gewartet werden soll", required=False, default=True),
    ],
    capabilities=["system", "application"],
    category=C.SYSTEM
)
async def open_application(app_name: str, wait_for_start: bool = True) -> dict:
    """
    Startet eine Anwendung auf dem Desktop (Cross-Platform).
    """
    log.info(f"🚀 Versuche Anwendung zu starten: '{app_name}'")

    app_key = app_name.lower().strip()
    candidates = []

    # 1. Suche in der bekannten Liste
    if app_key in APPLICATION_COMMANDS:
        candidates.extend(APPLICATION_COMMANDS[app_key])

    # 2. Suche Teilübereinstimmungen
    for key, cmds in APPLICATION_COMMANDS.items():
        if app_key in key:
            candidates.extend(cmds)

    # 3. Versuche den Namen direkt
    candidates.append(app_name)

    # Bereinigen
    unique_candidates = list(dict.fromkeys(candidates))

    for cmd in unique_candidates:
        # Argumente splitten, aber vorsichtig bei Strings mit Leerzeichen
        cmd_parts = cmd.split()
        executable = cmd_parts[0]

        # Prüfen ob ausführbar (shutil.which ist cross-platform!)
        if not shutil.which(executable):
            continue

        try:
            log.info(f"🔧 Starte: {cmd}")

            # Windows-spezifische Flags
            creationflags = 0
            preexec_fn = None

            if platform.system() == "Windows":
                # DETACHED_PROCESS flag
                creationflags = 0x00000008
            else:
                # Unix: Setsid um Prozess vom Terminal zu lösen
                preexec_fn = os.setsid

            process = subprocess.Popen(
                cmd_parts,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                preexec_fn=preexec_fn,
                shell=(platform.system() == "Windows") # Shell bei Windows oft nötig für Startmenü-Apps
            )

            if wait_for_start:
                await asyncio.sleep(2)
                if process.poll() is None:
                    log.info(f"✅ '{app_name}' erfolgreich gestartet (PID: {process.pid})")
                    return {"status": "launched", "app": app_name, "pid": process.pid}
            else:
                return {"status": "launched_async", "app": app_name}

        except Exception as e:
            log.warning(f"Fehler bei Versuch '{cmd}': {e}")
            continue

    raise Exception(f"Konnte '{app_name}' nicht starten. Keine passende Anwendung gefunden.")

@tool(
    name="list_applications",
    description="Listet verfügbare Anwendungen auf.",
    parameters=[],
    capabilities=["system", "application"],
    category=C.SYSTEM
)
async def list_applications() -> dict:
    """Listet verfügbare Anwendungen auf."""
    available = []
    for category, cmds in APPLICATION_COMMANDS.items():
        for cmd in cmds:
            exe = cmd.split()[0]
            if shutil.which(exe):
                available.append(category)
                break
    return {"available_apps": available}

# tools/reflection_tool/tool.py
import os
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Union, Dict, Any
import textwrap # Wichtig: textwrap importieren

from jsonrpcserver import method, Success, Error

log = logging.getLogger(__name__)

# Definiere den Pfad zum Lerntagebuch
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    LEARNING_LOG_FILE = LOG_DIR / "lerntagebuch.md"
    log.info(f"Lerntagebuch wird nach '{LEARNING_LOG_FILE}' geschrieben.")
except Exception as e:
    log.error(f"Konnte Log-Verzeichnis nicht erstellen: {e}")
    LEARNING_LOG_FILE = None

@method
def log_learning_entry(
    goal: str, 
    outcome: str, 
    details: Dict[str, Any], 
    learning: str
) -> Union[Success, Error]:
    """
    Erstellt einen strukturierten Eintrag im Lerntagebuch.
    """
    if not LEARNING_LOG_FILE:
        return Error(code=-32070, message="Pfad zum Lerntagebuch ist nicht konfiguriert.")

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # KORREKTUR: Verwende textwrap.dedent für einen sauberen, mehrzeiligen String
        entry = textwrap.dedent(f"""
        ---
        ### Lerntagebuch-Eintrag: {timestamp}

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

        # Füge den Eintrag an die Log-Datei an
        with open(LEARNING_LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + entry.strip() + "\n") # Füge eine Leerzeile hinzu und entferne überflüssige Whitespaces
            
        log.info("Eintrag ins Lerntagebuch erfolgreich geschrieben.")
        return Success({"status": "logged"})

    except Exception as e:
        log.error(f"Fehler beim Schreiben ins Lerntagebuch: {e}", exc_info=True)
        return Error(code=-32071, message=f"Fehler beim Schreiben ins Lerntagebuch: {e}")
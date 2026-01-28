# agent/deep_research_agent.py (VERSION 3.0 - v5.0 Compatible)
"""
Deep Research Agent v3.0 - Compatible with Deep Research Engine v5.0.

NEU in v3.0:
- Unterstützung für v5.0 Academic Excellence Features
- Erwähnung der neuen Quellenqualitäts- und Bias-Analysen
- These-Antithese-Synthese Framework im Prompt
- Optimiert für druckreife akademische Reports

v2.0 Fixes (beibehalten):
1. Korrekte Parameter-Namen für generate_research_report
2. Robustere JSON-Extraktion
3. Bessere Fehlerbehandlung
4. Konsistente Session-ID Weitergabe
"""

import logging
import os
import json
import textwrap
import requests
import sys
import re
from datetime import datetime
import time
from pathlib import Path

# --- Modulpfad-Korrektur ---
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai import OpenAI
from dotenv import load_dotenv

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
script_logger = logging.getLogger("deep_research_agent")

# --- Konfiguration ---
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:5000")
load_dotenv()

# Modell-Wahl
MODEL_NAME = os.getenv("SMART_MODEL", os.getenv("MAIN_LLM_MODEL", "gpt-4o"))

# OpenAI Client
try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if client.api_key is None:
        raise ValueError("OPENAI_API_KEY nicht gefunden.")
except Exception as e:
    script_logger.error(f"FATAL: OpenAI-Client konnte nicht initialisiert werden: {e}")
    sys.exit(1)


# ==============================================================================
# SYSTEM PROMPT (FIXED)
# ==============================================================================
SYSTEM_PROMPT = f"""# IDENTITÄT & MISSION
Du bist der Deep Research Agent von Timus v3.0. Deine Mission ist es, eine umfassende akademische Tiefenrecherche durchzuführen und dann einen druckreifen Bericht zu erstellen.

# AKTUELLES DATUM
{datetime.now().strftime("%d.%m.%Y")}

# DEEP RESEARCH ENGINE v5.0 - ACADEMIC EXCELLENCE
Du nutzt die neue Deep Research Engine v5.0 mit folgenden Features:
- 🎓 These-Antithese-Synthese Framework (dialektische Analyse)
- 📊 Quellenqualitäts-Bewertung (Authority, Bias, Transparency, Citations)
- 🔬 Erweiterte Fakten-Verifikation mit fact_corroborator
- 📄 Druckreife Reports im wissenschaftlichen Stil
- ⚖️ Kritische Analyse & Limitationen-Tracking

# WERKZEUGKASTEN

1. `start_deep_research` - Startet die akademische Tiefenrecherche (v5.0)
   Parameter:
   - query (string, required): Die Hauptsuchanfrage
   - focus_areas (list[string], optional): Fokusthemen wie ["Technologie", "Wirtschaft"]
   - verification_mode (string, optional): "strict" (default, ≥3 Quellen), "moderate" (≥2 Quellen), oder "light"
   - max_depth (int, optional): Recherche-Tiefe 1-5 (default: 3)

   Ausgabe (v5.0):
   - session_id: Für Report-Generierung
   - verified_count: Verifizierte Fakten
   - thesis_analyses_count: These-Antithese-Synthese Analysen
   - source_quality_summary: Qualitätsverteilung der Quellen
   - bias_summary: Bias-Verteilung
   - report_filepath: Pfad zum automatisch erstellten Report

2. `generate_research_report` - Erstellt den akademischen Abschlussbericht (v5.0)
   Parameter:
   - session_id (string, required): Die Session-ID aus Schritt 1
   - format (string, optional): "markdown" (default) oder "text"

   Report-Struktur (v5.0):
   - Executive Summary
   - Methodik-Sektion
   - Kern-Erkenntnisse mit Confidence-Scores
   - These-Antithese-Synthese Analysen
   - Quellenqualitäts-Tabellen
   - Kritische Diskussion
   - Limitationen & Unsicherheiten
   - Quellenverzeichnis mit Qualitätsbewertung

# WORKFLOW (STRIKT BEFOLGEN!)

1. **RECHERCHIEREN:** Rufe `start_deep_research` mit query und optionalen focus_areas auf
2. **MERKEN:** Merke dir die `session_id` aus der Observation
3. **BERICHTEN:** Rufe `generate_research_report` mit der gemerkten session_id auf
4. **ABSCHLIESSEN:** Gib eine Final Answer mit Zusammenfassung

# ANTWORTFORMAT

Für Tool-Aufrufe:
Thought: [Deine Überlegung]
Action: {{"method": "tool_name", "params": {{"param1": "value1"}}}}

Für Abschluss:
Final Answer: [Zusammenfassung der Recherche]

# BEISPIEL-ABLAUF (v5.0)

User: Recherchiere zu KI-Sicherheit

Thought: Ich starte eine akademische Tiefenrecherche zu KI-Sicherheit mit v5.0 Features (Quellenqualität, These-Antithese-Synthese).
Action: {{"method": "start_deep_research", "params": {{"query": "KI Sicherheit aktuelle Entwicklungen 2024", "focus_areas": ["Risiken", "Regulierung", "Ethik"], "verification_mode": "strict", "max_depth": 3}}}}

Observation: {{"session_id": "research_20260128_143022_abc123", "status": "completed", "version": "5.0", "facts_extracted": 47, "verified_count": 23, "thesis_analyses_count": 3, "source_quality_summary": {{"excellent": 5, "good": 10, "medium": 3}}, "report_filepath": "/results/DeepResearch_Academic_research_..."}}

Thought: Recherche abgeschlossen! v5.0 hat 23 verifizierte Fakten, 3 These-Antithese-Synthese Analysen und einen druckreifen Report erstellt. 83% der Quellen sind excellent/good. Der Report wurde bereits automatisch erstellt, ich könnte aber auch manuell einen neuen generieren.
Action: {{"method": "generate_research_report", "params": {{"session_id": "research_20260128_143022_abc123", "format": "markdown"}}}}

Observation: {{"status": "report_created", "version": "5.0", "filepath": "/results/DeepResearch_Academic_...", "format": "markdown"}}

Final Answer: Die akademische Tiefenrecherche zu KI-Sicherheit wurde mit v5.0 erfolgreich abgeschlossen:

📊 Recherche-Ergebnis:
- 47 Fakten extrahiert, 23 durch ≥3 Quellen verifiziert
- 3 These-Antithese-Synthese Analysen durchgeführt
- 18 Quellen analysiert: 28% excellent, 55% good, 17% medium
- Druckreifer akademischer Report mit Executive Summary, Methodik, Quellenqualitäts-Analyse und kritischer Diskussion

Der vollständige wissenschaftliche Bericht wurde gespeichert und kann gedruckt werden.

# WICHTIGE REGELN
- Verwende IMMER die exakten Parameter-Namen wie oben dokumentiert
- Die session_id aus start_deep_research MUSS an generate_research_report übergeben werden
- Warte auf jede Observation bevor du fortfährst
- Bei Fehlern: Beschreibe das Problem in der Final Answer
"""


# ==============================================================================
# HILFSFUNKTIONEN
# ==============================================================================

def call_tool(method: str, params: dict | None = None) -> dict:
    """Ruft ein Tool über den MCP-Server auf."""
    params = params or {}
    script_logger.info(f"🔧 Tool-Aufruf: {method}")
    script_logger.debug(f"   Parameter: {params}")
    
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": os.urandom(4).hex()
    }
    
    try:
        # Langer Timeout für Deep Research (30 Min)
        response = requests.post(MCP_URL, json=payload, timeout=1800)
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            error_info = data.get("error", {})
            error_msg = error_info.get("message", str(error_info)) if isinstance(error_info, dict) else str(error_info)
            return {"error": error_msg}
        
        return data.get("result", {})
        
    except requests.exceptions.Timeout:
        return {"error": "Timeout: Die Recherche hat länger als 30 Minuten gedauert."}
    except requests.exceptions.ConnectionError:
        return {"error": f"Verbindungsfehler: MCP-Server unter {MCP_URL} nicht erreichbar."}
    except Exception as e:
        return {"error": f"Kommunikationsfehler: {e}"}


def llm(messages: list) -> str:
    """Ruft das LLM auf."""
    try:
        kwargs = {
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": 0.1
        }
        
        # Parameter für verschiedene Modelle
        if any(x in MODEL_NAME.lower() for x in ["gpt-5", "gpt-4", "o1", "o3"]):
            kwargs["max_completion_tokens"] = 2000
        else:
            kwargs["max_tokens"] = 2000
        
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        script_logger.error(f"LLM Fehler: {e}")
        return f"Error: LLM API Fehler - {e}"


def extract_json_safely(text: str) -> tuple[dict | None, str | None]:
    """
    Robuster Parser für JSON aus LLM-Antworten.
    Sucht nach Action-Blöcken in verschiedenen Formaten.
    """
    # Methode 1: JSON in ```json ... ``` Blöcken
    match = re.search(r'```json\s*([\s\S]*?)\s*```', text, re.DOTALL)
    
    # Methode 2: Action: {...} Format
    if not match:
        match = re.search(r'Action:\s*(\{[\s\S]*?\})\s*(?:\n|$)', text, re.DOTALL)
    
    # Methode 3: Rohes JSON {...}
    if not match:
        match = re.search(r'(\{[^{}]*"method"[^{}]*\})', text, re.DOTALL)
    
    # Methode 4: Verschachteltes JSON
    if not match:
        match = re.search(r'(\{[\s\S]*\})', text, re.DOTALL)
    
    if not match:
        return None, "Kein JSON-Block gefunden."
    
    try:
        json_str = match.group(1).strip()
        
        # Bereinigungen
        json_str = re.sub(r',\s*([\}\]])', r'\1', json_str)  # Trailing Commas
        json_str = json_str.replace('\n', ' ')  # Newlines
        
        data = json.loads(json_str)
        
        # Verschiedene Formate akzeptieren
        if "action" in data:
            return data["action"], None
        if "method" in data:
            return data, None
        
        return None, "JSON enthält keinen 'method'-Schlüssel."
        
    except json.JSONDecodeError as e:
        return None, f"JSON-Parse-Fehler: {e}"


# ==============================================================================
# REACT LOOP (FIXED)
# ==============================================================================

def react_loop(user_query: str, max_steps: int = 8) -> str:
    """
    Führt die ReAct-Schleife für Deep Research durch.
    
    Args:
        user_query: Die Benutzeranfrage
        max_steps: Maximale Anzahl Schritte
    
    Returns:
        Die finale Antwort
    """
    script_logger.info(f"🚀 Starte Deep-Research (Modell: {MODEL_NAME})")
    script_logger.info(f"   Query: '{user_query}'")
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query}
    ]
    
    # Session-ID speichern für Konsistenz
    research_session_id: str | None = None
    
    for step in range(1, max_steps + 1):
        script_logger.info(f"\n{'='*60}")
        script_logger.info(f"⚙️ Schritt {step}/{max_steps}")
        script_logger.info(f"{'='*60}")
        
        # LLM aufrufen
        llm_reply = llm(messages)
        
        if llm_reply.startswith("Error:"):
            return f"Fehler bei LLM-Aufruf: {llm_reply}"
        
        script_logger.info(f"🧠 Agent-Antwort:\n{llm_reply[:500]}...")
        
        # Prüfe auf Final Answer
        if "Final Answer:" in llm_reply:
            final_answer = llm_reply.split("Final Answer:", 1)[1].strip()
            script_logger.info("✅ Final Answer erhalten")
            return final_answer
        
        messages.append({"role": "assistant", "content": llm_reply})
        
        # Action extrahieren
        action_dict, error_msg = extract_json_safely(llm_reply)
        
        if not action_dict:
            script_logger.warning(f"⚠️ Konnte Action nicht parsen: {error_msg}")
            messages.append({
                "role": "user",
                "content": f"System: Ungültiges Format ({error_msg}). Bitte sende eine Action im korrekten JSON-Format:\n"
                          f'Action: {{"method": "tool_name", "params": {{"key": "value"}}}}'
            })
            continue
        
        method = action_dict.get("method", "")
        params = action_dict.get("params", {})
        
        script_logger.info(f"🔧 Erkannte Action: {method}")
        script_logger.debug(f"   Params: {params}")
        
        # --- SPEZIELLE BEHANDLUNG ---
        
        # 1. Session-ID aus start_deep_research speichern
        if method == "start_deep_research":
            action_result = call_tool(method, params)
            
            if isinstance(action_result, dict) and "session_id" in action_result:
                research_session_id = action_result["session_id"]
                script_logger.info(f"✅ Session-ID gesichert: {research_session_id}")
        
        # 2. Report-Generierung mit korrekten Parametern
        elif method in ["generate_research_report", "generate_report", "create_report"]:
            # Methode normalisieren
            method = "generate_research_report"
            
            # FIX: Korrekte Parameter-Namen verwenden
            # Der Agent könnte verschiedene Namen verwenden
            session_id = (
                params.get("session_id") or 
                params.get("session_id_to_report") or 
                research_session_id
            )
            
            if not session_id:
                action_result = {
                    "error": "Keine Session-ID gefunden. Bitte erst 'start_deep_research' aufrufen."
                }
            else:
                # Korrekte Parameter für das Tool
                clean_params = {
                    "session_id": session_id,
                    "format": params.get("format", params.get("report_format_type", "markdown"))
                }
                script_logger.info(f"📄 Erstelle Report für Session: {session_id}")
                action_result = call_tool(method, clean_params)
        
        # 3. Andere Tools direkt durchreichen
        else:
            action_result = call_tool(method, params)
        
        # Ergebnis loggen (gekürzt)
        result_str = json.dumps(action_result, ensure_ascii=False)
        if len(result_str) > 800:
            result_str = result_str[:800] + "... [gekürzt]"
        script_logger.info(f"📋 Ergebnis: {result_str}")
        
        # Observation an Messages anhängen
        messages.append({
            "role": "user",
            "content": f"Observation: {json.dumps(action_result, ensure_ascii=False)}"
        })
    
    return "⚠️ Maximale Schritte erreicht ohne Final Answer."


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    """Haupteinstiegspunkt."""
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        # Interaktiver Modus
        print("\n" + "="*60)
        print("🔬 TIMUS DEEP RESEARCH AGENT")
        print("="*60)
        query = input("\nRecherche-Anfrage: ").strip()
        
        if not query:
            print("Keine Anfrage eingegeben.")
            return
    
    # Recherche starten
    final_answer = react_loop(query)
    
    # Ergebnis ausgeben
    print("\n" + "="*60)
    print("💡 ERGEBNIS:")
    print("="*60)
    print(textwrap.fill(str(final_answer), width=80))
    print("="*60)


if __name__ == "__main__":
    main()

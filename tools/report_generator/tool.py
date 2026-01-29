# tools/report_generator/tool.py

import json
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import asyncio

from jsonrpcserver import method, Success, Error
from openai import OpenAI
from utils.openai_compat import prepare_openai_params
from dotenv import load_dotenv

# Interne Imports
from tools.universal_tool_caller import register_tool
from tools.planner.planner_helpers import call_tool_internal
import os 

# --- Setup ---
logger = logging.getLogger("report_generator")
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# HINWEIS: Wir entfernen den lokalen `session_data`-Speicher.
# Der Report wird jetzt immer direkt aus der übergebenen Session generiert.

# ==============================================================================
# KORRIGIERTES HAUPT-TOOL
# ==============================================================================

@method
async def generate_report_from_session(
    session_id: str,
    query: str,
    report_format: str = "markdown",
    language: str = "de"
) -> Union[Success, Error]:
    """
    Erstellt einen umfassenden Bericht aus einer abgeschlossenen Deep-Research-Session.

    Args:
        session_id: Die ID der Recherche-Session, aus der der Bericht erstellt werden soll.
        query: Die ursprüngliche Nutzeranfrage für den Kontext.
        report_format: Gewünschtes Format ("markdown", "html", "json").
        language: Sprache des Berichts ('de' oder 'en').
    """
    try:
        logger.info(f"📝 Erstelle Bericht aus Session '{session_id}' für Query '{query}'...")

        # Schritt 1: Hole die Session-Daten aus dem deep_research_tool.
        # WICHTIG: Das deep_research_tool muss eine Methode bereitstellen, um diese Daten abzurufen.
        # Wir nehmen an, es gibt eine (noch zu erstellende) Methode `get_session_data`.
        
        # Um zyklische Imports zu vermeiden, greifen wir direkt auf die globale Variable zu.
        # Das ist nicht ideal, aber die pragmatischste Lösung in dieser Architektur.
        from tools.deep_research.tool import research_sessions
        session = research_sessions.get(session_id)

        if not session:
            return Error(code=-32002, message=f"Recherche-Session mit ID '{session_id}' nicht gefunden.")

        # Schritt 2: Sammle die Daten aus der Session-Instanz.
        
        # ==================== KORREKTUR ====================
        # Wir fügen die fehlenden Schlüssel hinzu, damit der Report sie verwenden kann.
        collected_data = {
            "all_sources": [{"title": node.title, "url": node.url} for node in session.research_tree],
            "key_findings": session.all_extracted_facts_raw,
            "verified_facts": session.verified_facts,
            "unverified_claims": session.unverified_claims, # <--- FEHLENDER SCHLÜSSEL
            "start_time": getattr(session, 'start_time', datetime.now().isoformat()) # Sicherer Zugriff
        }
        # ===================================================

        if not collected_data["key_findings"]:
            msg = f"Session '{session_id}' enthält keine extrahierten Fakten."
            logger.warning(msg)
            return Error(code=-32001, message=msg)

        # Schritt 3: Führe die KI-Analyse durch (unverändert).
        ai_analysis = await _analyze_research_data(collected_data, query)

        # Schritt 4: Erstelle den Bericht (unverändert).
        report_content: Union[str, Dict]
        if report_format.lower() == "markdown":
            report_content = await _create_markdown_report(collected_data, ai_analysis, query, language)
        else:
            return Error(code=-32602, message=f"Ungültiges Format '{report_format}'.")

        # Schritt 5: Speichere den Bericht (unverändert).
        save_result = await _save_report(report_content, query, report_format)
        
        return Success({
            "summary_of_report": ai_analysis.get("main_conclusions", ["Bericht erstellt."])[0],
            "saved_as_filename": save_result.get("filename"),
            "statistics": {
                "sources_referenced": len(collected_data["all_sources"]),
                "key_findings_count": len(collected_data["key_findings"])
            }
        })
    except Exception as e:
        logger.error(f"❌ Kritischer Fehler bei der Berichterstellung: {e}", exc_info=True)
        return Error(code=-32000, message=f"Interner Fehler: {e}")

async def _save_report(content: str, query: str, report_format: str) -> Dict:
    """
    Speichert den Bericht über das 'save_research_result'-Tool.
    Gibt ein Dictionary mit dem Dateinamen oder einem Fehler zurück.
    """
    logger.info(f"Versuche, Bericht (Format: {report_format}) zu speichern...")
    try:
        safe_query = "".join(c for c in query[:40] if c.isalnum() or c in " _-").rstrip().replace(" ", "_")
        title = f"Recherche_Bericht_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_query}"
        
        # Dieser Aufruf ist entscheidend. Wir stellen sicher, dass alle Parameter korrekt sind.
        save_result = await call_tool_internal(
            "save_research_result", 
            {
                "title": title, 
                "content": content, 
                "format": report_format.lower()
            }
        )
        
        if isinstance(save_result, dict) and save_result.get("filename"):
            logger.info(f"✅ Bericht erfolgreich gespeichert: {save_result.get('filepath')}")
            # Gib das gesamte erfolgreiche Ergebnis zurück
            return save_result
        else:
            # Wenn das Tool keinen Dateinamen zurückgibt, war es ein Fehler
            error_msg = f"Tool 'save_research_result' gab keinen Dateinamen zurück. Antwort: {save_result}"
            logger.error(error_msg)
            return {"error": error_msg}
            
    except Exception as e:
        error_msg = f"Kritischer Fehler in _save_report: {e}"
        logger.error(error_msg, exc_info=True)
        return {"error": error_msg}
    

# ==============================================================================
# INTERNE HILFSFUNKTIONEN
# ==============================================================================

async def _analyze_research_data(data: Dict, query: str) -> Dict:
    """Analysiert die gesammelten Daten mit GPT für eine Meta-Zusammenfassung."""
    if not client.api_key: return {"main_conclusions": ["KI-Analyse übersprungen."]}

    sources_summary = "\n".join([f"- {s.get('title')}" for s in data["all_sources"][:10]])
   # ==================== FINALE ANPASSUNG ====================
    # Begrenze die Anzahl der Erkenntnisse, die an das LLM gesendet werden, um Ratenbegrenzungen zu vermeiden.
    # Wir nehmen die ersten 30 als repräsentative Stichprobe.
    findings_for_prompt = data.get("key_findings", [])[:30]
    findings_summary = "\n".join([f"- {str(f.get('fact', ''))[:100]}..." for f in findings_for_prompt])
    # ==========================================================
    
    prompt = f"""
    Analysiere die folgenden Recherche-Ergebnisse zur Anfrage: "{query}"

    QUELLEN (Auszug):
    {sources_summary}

    ERKENNTNISSE (Auszug aus {len(data.get('key_findings',[]))} insgesamt):
    {findings_summary}

    Bitte erstelle eine strukturierte Analyse auf Deutsch. Antworte ausschließlich als valides JSON-Objekt mit den folgenden Schlüsseln:
    - "main_conclusions": (Liste von Strings) 3-5 zentrale Schlussfolgerungen.
    - "identified_knowledge_gaps": (Liste von Strings) Informationslücken oder offene Fragen.
    """
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Du bist ein Experte für Recherche-Analyse. Antworte immer als valides JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3, max_tokens=1500, response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content or "{}")
    except Exception as e:
        logger.error(f"GPT-Analyse fehlgeschlagen: {e}")
        return {"main_conclusions": [f"Fehler bei der KI-Analyse: {e}"]}

async def _create_markdown_report(data: Dict, analysis: Dict, query: str, language: str) -> str:
    """Erstellt den finalen Bericht im Markdown-Format."""
    texts = _get_language_texts(language)
    start_time = data.get("start_time")
    processing_time = _calculate_processing_time(start_time)
    
    report_parts = [f"# {texts['report_title']}: {query}\n"]
    report_parts.append(f"**{texts['created_on']}:** {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    report_parts.append(f"**{texts['analyzed_sources']}:** {len(data['all_sources'])}")
    report_parts.append(f"**{texts['processing_time']}:** {processing_time}\n---\n")
    
    report_parts.append(f"## {texts['summary_section']}\n")
    for conclusion in analysis.get("main_conclusions", []):
        report_parts.append(f"- {conclusion}")

    report_parts.append(f"\n## {texts['key_findings_section']}\n")
    if data["verified_facts"]:
        report_parts.append("### Verifizierte Fakten\n")
        for fact in data["verified_facts"]:
            report_parts.append(f"- ✅ **{fact.get('fact')}** (Belege: {fact.get('source_count')})")
    if data["unverified_claims"]:
        report_parts.append("\n### Unverifizierte Behauptungen\n")
        for claim in data["unverified_claims"][:20]: # Zeige nur die ersten 20
             report_parts.append(f"- ❓ {claim.get('fact')} (Quelle: {claim.get('example_source_url')})")

    report_parts.append(f"\n## {texts['appendix_sources_section']}\n")
    for i, source in enumerate(data["all_sources"], 1):
        report_parts.append(f"{i}. {source.get('title', 'Unbekannter Titel')} ({source.get('url')})")
        
    return "\n".join(report_parts)

async def _save_report(content: str, query: str, report_format: str) -> Dict:
    """Speichert den Bericht über das 'save_research_result'-Tool."""
    logger.info(f"Versuche, Bericht (Format: {report_format}) zu speichern...")
    try:
        safe_query = "".join(c for c in query[:40] if c.isalnum() or c in " _-").rstrip().replace(" ", "_")
        title = f"Recherche_Bericht_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_query}"
        
        save_result = await call_tool_internal("save_research_result", {
            "title": title, "content": content, "format": report_format.lower()
        })
        
        if isinstance(save_result, dict) and save_result.get("filename"):
            logger.info(f"✅ Bericht erfolgreich gespeichert: {save_result.get('filepath')}")
            return save_result
        else:
            error_msg = f"Tool 'save_research_result' gab keinen Dateinamen zurück. Antwort: {save_result}"
            logger.error(error_msg)
            return {"error": error_msg}
    except Exception as e:
        error_msg = f"Kritischer Fehler in _save_report: {e}"
        logger.error(error_msg, exc_info=True)
        return {"error": error_msg}

def _calculate_processing_time(start_time_iso: Optional[str]) -> str:
    if start_time_iso:
        try:
            start = datetime.fromisoformat(start_time_iso)
            duration = (datetime.now() - start).total_seconds()
            return f"{int(duration // 60)} Min, {int(duration % 60)} Sek"
        except (TypeError, ValueError):
            return "Unbekannt"
    return "Unbekannt"

def _get_language_texts(lang: str) -> Dict[str, str]:
    return {
        "report_title": "Recherche-Bericht", "created_on": "Erstellt am",
        "analyzed_sources": "Referenzierte Quellen", "processing_time": "Bearbeitungszeit",
        "summary_section": "Zentrale Analyse & Schlussfolgerungen",
        "key_findings_section": "Wichtigste Erkenntnisse & Fakten",
        "appendix_sources_section": "Anhang: Referenzierte Quellen"
    }

# --- Registrierung der Tools ---
register_tool("generate_report_from_session", generate_report_from_session)
logger.info("✅ Session-basierter Report Generator registriert.")


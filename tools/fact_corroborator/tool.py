
# tools/fact_corroborator/tool.py
"""
Tool zur aktiven Korrelation und Verifizierung von Fakten durch gezielte Websuchen und Inhaltsanalyse.
"""
import asyncio # Import für asyncio.sleep und asyncio.to_thread
import json
import logging
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse
from datetime import datetime
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from tools.planner.planner_helpers import call_tool_internal

from openai import OpenAI
from utils.openai_compat import prepare_openai_params
from dotenv import load_dotenv
import os

# Logger für dieses Modul
logger = logging.getLogger("fact_corroborator_tool")
if not logger.hasHandlers(): # Standard-Logging-Setup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s",
    )

# OpenAI Client initialisieren
load_dotenv(override=True)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if not client.api_key:
    logger.warning("OPENAI_API_KEY nicht in .env gefunden. Fakt-Korrelationstool wird nicht voll funktionsfähig sein.")

# Konfiguration
MAX_CORROBORATION_SOURCES_PER_FACT = 3
MAX_SEARCH_RESULTS_PER_CORROBORATION_QUERY = 5
# MIN_CONFIDENCE_THRESHOLD = 0.7 # Wird derzeit nicht aktiv verwendet, aber gut für spätere Logik

# Cache für bereits verifizierte Fakten
verified_facts_cache: Dict[str, Dict[str, Any]] = {} # Typ-Hint für den Cache hinzugefügt

class FactVerificationResult:
    """Klasse zur Strukturierung von Verifikationsergebnissen"""
    def __init__(self, fact: str):
        self.fact = fact
        self.status: str = "unverified"  # verified, disputed, unverified
        self.confidence: float = 0.0
        self.supporting_sources: List[Dict[str, Any]] = []
        self.contradicting_sources: List[Dict[str, Any]] = []
        self.analysis: str = ""
        self.timestamp: str = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact": self.fact,
            "status": self.status,
            "confidence": self.confidence,
            "supporting_sources": self.supporting_sources,
            "contradicting_sources": self.contradicting_sources,
            "analysis": self.analysis,
            "timestamp": self.timestamp
        }

@tool(
    name="verify_fact",
    description="Verifiziert einen einzelnen Fakt durch gezielte Websuchen.",
    parameters=[
        P("fact", "string", "Der zu verifizierende Fakt"),
        P("context", "string", "Optionaler Kontext der Recherche", required=False),
        P("search_depth", "integer", "Anzahl der Suchanfragen (Standard: 2)", required=False, default=2),
        P("require_multiple_sources", "boolean", "Erfordert mehrere Quellen zur Verifikation", required=False, default=True),
    ],
    capabilities=["analysis", "fact_check"],
    category=C.ANALYSIS
)
async def verify_fact(
    fact: str,
    context: Optional[str] = None,
    search_depth: int = 2, # Standardmäßig 2 Suchanfragen versuchen
    require_multiple_sources: bool = True
) -> dict:
    """
    Verifiziert einen einzelnen Fakt durch gezielte Websuchen.
    """
    try:
        logger.info(f"🔍 Starte Faktenverifizierung: {fact[:100]}...")
        cache_key = f"{fact}_{context or ''}" # Stelle sicher, dass context nie None im Key ist
        if cache_key in verified_facts_cache:
            logger.info(f"✅ Fakt '{fact[:50]}...' aus Cache geladen.")
            return verified_facts_cache[cache_key]

        verification_result_obj = FactVerificationResult(fact)
        corroboration_queries = await _generate_corroboration_queries(fact, context or "")

        if not corroboration_queries:
            logger.warning(f"Keine Suchanfragen für Fakt '{fact[:50]}...' generiert. Status: error.")
            # Gib das Ergebnisobjekt mit Fehlerstatus zurück, anstatt nur ein einfaches Dict
            verification_result_obj.status = "error"
            verification_result_obj.analysis = "Fehler: Keine Suchanfragen konnten generiert werden."
            return verification_result_obj.to_dict()

        logger.info(f"📋 Generierte {len(corroboration_queries)} Suchanfragen für Fakt '{fact[:50]}...'.")
        all_found_sources = []
        for query_str in corroboration_queries[:search_depth]: # Limitiere auf search_depth
            extracted_sources = await _search_and_extract_sources(query_str)
            all_found_sources.extend(extracted_sources)
            await asyncio.sleep(0.2) # Kleine Pause zwischen den Suchen

        unique_relevant_sources = _deduplicate_by_domain(all_found_sources)
        logger.info(f"📚 {len(unique_relevant_sources)} einzigartige Quellen nach Deduplizierung gefunden für Fakt '{fact[:50]}...'.")

        source_analysis_results = []
        tasks_for_analysis = []
        for source_item in unique_relevant_sources[:MAX_CORROBORATION_SOURCES_PER_FACT]: # Limitiere Anzahl analysierter Quellen
            tasks_for_analysis.append(_analyze_source_for_fact(source_item, fact, context))

        # Parallele Analyse der Quellen
        if tasks_for_analysis:
            analysis_outputs = await asyncio.gather(*tasks_for_analysis, return_exceptions=True)
            for output in analysis_outputs:
                if isinstance(output, dict): # Erfolgreiche Analyse
                    source_analysis_results.append(output)
                elif isinstance(output, Exception):
                    logger.error(f"Fehler bei paralleler Quellenanalyse: {output}")

        final_verification_dict = _evaluate_verification_results(verification_result_obj, source_analysis_results, require_multiple_sources)

        # Evidence Pack anfuegen
        try:
            from utils.evidence_pack import EvidencePack
            final_verification_dict["evidence_pack"] = EvidencePack.from_fact_verification(final_verification_dict).to_dict()
        except Exception as ep_err:
            logger.warning(f"Evidence Pack konnte nicht erstellt werden: {ep_err}")

        verified_facts_cache[cache_key] = final_verification_dict # Cache das Ergebnis
        logger.info(f"🏁 Faktenverifizierung für '{fact[:50]}...' abgeschlossen. Status: {final_verification_dict.get('status')}")
        return final_verification_dict

    except Exception as e:
        logger.error(f"❌ Schwerwiegender Fehler bei Faktenverifizierung für '{fact[:50]}...': {e}", exc_info=True)
        # Erstelle ein Fehlerobjekt im Standardformat
        error_result = FactVerificationResult(fact)
        error_result.status = "error"
        error_result.analysis = f"Interner Fehler: {str(e)}"
        return error_result.to_dict() # Gib immer noch dict zurück, aber mit Fehler im Payload

@tool(
    name="verify_multiple_facts",
    description="Verifiziert mehrere Fakten gleichzeitig.",
    parameters=[
        P("facts", "array", "Liste von Fakten-Strings zur Verifikation"),
        P("context", "string", "Optionaler Kontext", required=False),
        P("parallel", "boolean", "Parallel verarbeiten (Standard: true)", required=False, default=True),
    ],
    capabilities=["analysis", "fact_check"],
    category=C.ANALYSIS
)
async def verify_multiple_facts(
    facts: List[str],
    context: Optional[str] = None,
    parallel: bool = True # Standardmäßig parallel
) -> dict:
    """
    Verifiziert mehrere Fakten gleichzeitig.
    """
    try:
        logger.info(f"🔍 Verifiziere {len(facts)} Fakten (parallel: {parallel}). Kontext: {context or 'Kein Kontext'}")
        individual_results = []

        if parallel:
            verification_tasks = [verify_fact(fact_item, context) for fact_item in facts]
            task_outputs = await asyncio.gather(*verification_tasks, return_exceptions=True)
        else:
            task_outputs = []
            for fact_item in facts:
                task_outputs.append(await verify_fact(fact_item, context))
                await asyncio.sleep(0.5) # Kleine Pause bei sequenzieller Verarbeitung

        for i, output_item in enumerate(task_outputs):
            if isinstance(output_item, Exception):
                logger.error(f"❌ Fehler bei Verifizierung von Fakt {i} ('{facts[i][:50]}...'): {output_item}")
                error_res = FactVerificationResult(facts[i])
                error_res.status = "error"
                error_res.analysis = f"Fehler während der Verifizierung: {str(output_item)}"
                individual_results.append(error_res.to_dict())
            elif isinstance(output_item, dict):
                individual_results.append(output_item)
            else: # Unerwarteter Rückgabetyp
                logger.warning(f"Unerwarteter Rückgabetyp für Fakt {i}: {type(output_item)}")
                error_res = FactVerificationResult(facts[i])
                error_res.status = "error"
                error_res.analysis = "Unerwarteter Rückgabetyp vom Verifizierungsprozess."
                individual_results.append(error_res.to_dict())

        overall_summary = _create_verification_summary(individual_results)
        logger.info(f"🏁 Mehrfach-Faktenverifizierung abgeschlossen. Verifiziert: {overall_summary.get('verified_count')}, Bestritten: {overall_summary.get('disputed_count')}")
        return {
            "facts_results": individual_results, # Umbenannt für Klarheit
            "summary": overall_summary
        }

    except Exception as e:
        logger.error(f"❌ Schwerwiegender Fehler bei Mehrfach-Faktenverifizierung: {e}", exc_info=True)
        raise Exception(f"Interner Fehler bei Mehrfach-Verifizierung: {str(e)}")


async def _generate_corroboration_queries(fact_to_verify: str, main_query_context: str) -> List[str]:
    """
    Generiert spezifische Suchanfragen, um einen gegebenen Fakt zu verifizieren oder zu widerlegen.
    """
    if not client.api_key:
        logger.warning("Kein OpenAI API Key für Query-Generierung, verwende Fallback.")
        base_query = fact_to_verify.replace(".", "").replace(",", "").strip()
        # Einfache, aber oft effektive Fallback-Queries
        return [
            f"{base_query} Faktencheck",
            f"Quellen für \"{base_query}\"",
            f"Ist \"{base_query}\" wahr?",
            f"Widerlegung \"{base_query}\""
        ][:3] # Limitiere auf 3 Fallback-Queries

    prompt = f"""
    Basierend auf dem folgenden Fakt und dem ursprünglichen Recherchekontext, erstelle 2-3 präzise und unterschiedliche Google-Suchanfragen auf Deutsch,
    die darauf abzielen, diesen Fakt zu bestätigen oder zu widerlegen. Die Suchanfragen sollten so formuliert sein,
    dass sie wahrscheinlich zu Quellen führen, die den Fakt direkt adressieren.
    Gib Variationen, die sowohl bestätigende als auch widerlegende Perspektiven suchen.

    Fakt zu verifizieren: "{fact_to_verify}"
    Kontext der ursprünglichen Recherche (optional): "{main_query_context}"

    Beispiele für Suchanfragen könnten sein:
    - Suche nach offiziellen Berichten oder Studien.
    - Suche nach Faktencheck-Websites.
    - Suche nach Gegenargumenten oder Kritik.
    - Suche nach aktuellen Nachrichten oder Updates zum Thema.

    Gib nur eine JSON-Liste von Strings zurück, z.B.:
    ["Suchanfrage 1", "Suchanfrage 2", "Suchanfrage 3"]
    """
    try:
        logger.debug(f"Generiere Suchanfragen für Fakt: {fact_to_verify[:70]}...")
        response = await asyncio.to_thread( # Nutze asyncio.to_thread für blockierende SDK-Aufrufe
            client.chat.completions.create,
            model="gpt-4o", # Oder ein günstigeres/schnelleres Modell, falls Tokens ein Problem sind
            messages=[
                {"role": "system", "content": "Du bist ein Experte für Faktenverifizierung und erstellst präzise Suchanfragen auf Deutsch. Antworte immer nur als JSON-Liste."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2, # Niedrige Temperatur für konsistentere Anfragen
            max_tokens=200,  # Sollte für 2-3 Queries reichen
            response_format={"type": "json_object"} # Fordere JSON-Format an
        )
        await asyncio.sleep(0.5) # Kleine Pause nach dem API-Aufruf, um Rate Limits zu respektieren

        content = response.choices[0].message.content.strip() if response.choices and response.choices[0].message else "{}"

        # Versuche, JSON zu parsen
        # In _generate_corroboration_queries

        content = response.choices[0].message.content.strip()
        try:
            # Zuerst versuchen, als direktes Array zu parsen
            parsed_json = json.loads(content)
            if isinstance(parsed_json, list):
                queries = parsed_json
            # Dann versuchen, als Objekt mit einem "queries" oder ähnlichem Schlüssel zu parsen
            elif isinstance(parsed_json, dict):
                key_found = False
                for key_candidate in ["queries", "search_queries", "results"]: # Mögliche Schlüssel
                    if key_candidate in parsed_json and isinstance(parsed_json[key_candidate], list):
                        queries = parsed_json[key_candidate]
                        key_found = True
                        break
                if not key_found:
                    logger.warning(f"OpenAI gab ein Dictionary ohne erwartetes Listen-Element zurück: {content}")
                    queries = []
            else:
                logger.warning(f"OpenAI gab weder Liste noch erwartetes Dictionary zurück: {content}")
                queries = []

            if all(isinstance(q, str) for q in queries):
                logger.info(f"Erfolgreich {len(queries)} Suchanfragen von OpenAI generiert.")
                return queries[:3]
            else:
                logger.warning(f"Ungültiges Format für Suchanfragen in der generierten Liste: {queries}")
                return []
        except json.JSONDecodeError:
            logger.error(f"JSONDecodeError bei Query-Generierung. OpenAI-Antwort war kein valides JSON: '{content}'")
            return []
    except Exception as e:
        logger.error(f"Allgemeiner Fehler bei OpenAI Query-Generierung: {e}", exc_info=True)
        return []


async def _search_and_extract_sources(query: str) -> List[Dict[str, Any]]:
    """
    Führt eine Websuche durch und extrahiert relevante Quellen.
    """
    try:
        logger.info(f"Führe Websuche durch für: '{query}'")
        search_result_payload = await call_tool_internal("search_web", {
            "query": query,
            "max_results": MAX_SEARCH_RESULTS_PER_CORROBORATION_QUERY
        })
        await asyncio.sleep(0.2) # Kleine Pause nach der Websuche

        # search_result_payload ist das Ergebnis des Tools, was bei Erfolg eine Liste sein sollte,
        # oder ein Dict mit "error".
        if isinstance(search_result_payload, dict) and search_result_payload.get("error"):
            logger.warning(f"Fehler vom search_web Tool für Query '{query}': {search_result_payload['error']}")
            return []

        if not isinstance(search_result_payload, list):
            logger.warning(f"Unerwartetes Suchergebnisformat für Query '{query}': {type(search_result_payload)}")
            return []

        extracted_sources = []
        for result_item in search_result_payload:
            if isinstance(result_item, dict) and result_item.get("url"):
                try:
                    domain_name = urlparse(result_item["url"]).netloc
                except Exception: # Fallback, falls URL-Parsing fehlschlägt
                    domain_name = "unbekannt"
                extracted_sources.append({
                    "url": result_item["url"],
                    "title": result_item.get("title", "Kein Titel"),
                    "snippet": result_item.get("snippet", ""),
                    "domain": domain_name,
                    "retrieved_for_query": query # Behalte Suchanfrage für Kontext
                })
        logger.info(f"{len(extracted_sources)} Quellen aus Suche für '{query}' extrahiert.")
        return extracted_sources

    except Exception as e:
        logger.error(f"Fehler während _search_and_extract_sources für '{query}': {e}", exc_info=True)
        return []

def _deduplicate_by_domain(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Entfernt Duplikate basierend auf Domain, bevorzugt dabei Quellen mit längeren Snippets.
    """
    domain_map: Dict[str, Dict[str, Any]] = {}
    for source_item in sources:
        domain = source_item.get("domain")
        if not domain or not isinstance(domain, str): # Prüfe ob Domain existiert und String ist
            continue
        if domain not in domain_map or \
           len(source_item.get("snippet", "")) > len(domain_map[domain].get("snippet", "")):
            domain_map[domain] = source_item
    return list(domain_map.values())

async def _analyze_source_for_fact(source_details: Dict[str, Any], fact_to_check: str, context: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Analysiert eine einzelne Quelle auf Relevanz zum Fakt.
    """
    source_url = source_details.get("url")
    if not source_url or not isinstance(source_url, str):
        logger.warning("Ungültige URL in source_details, kann Quelle nicht analysieren.")
        return None
    try:
        logger.info(f"Analysiere Quelle für Faktencheck: {source_url}")
        open_result = await call_tool_internal("open_url", {"url": source_url})
        await asyncio.sleep(0.2)

        if isinstance(open_result, dict) and open_result.get("error"):
            logger.warning(f"Fehler beim Öffnen von {source_url}: {open_result['error']}")
            return None

        # Gehe davon aus, dass open_result erfolgreich war, auch wenn es kein "error" hat
        # und nicht notwendigerweise ein 'status' Feld im Erfolgsfall (abhängig vom Tool).

        dismiss_result = await call_tool_internal("dismiss_overlays") # Versuche Overlays zu entfernen
        if isinstance(dismiss_result, dict) and dismiss_result.get("error"):
            logger.debug(f"Fehler beim dismiss_overlays für {source_url}: {dismiss_result['error']} (nicht kritisch)")
        await asyncio.sleep(0.1)

        text_extraction_result = await call_tool_internal("get_text")
        await asyncio.sleep(0.1)

        page_content = ""
        if isinstance(text_extraction_result, dict) and "text" in text_extraction_result:
            page_content = text_extraction_result["text"]
        elif isinstance(text_extraction_result, dict) and text_extraction_result.get("error"):
             logger.warning(f"Fehler beim Extrahieren von Text aus {source_url}: {text_extraction_result['error']}")
             return None # Wenn kein Text extrahiert werden kann, ist Analyse nicht sinnvoll
        else:
            logger.warning(f"Unerwartetes Ergebnis von get_text für {source_url}: {text_extraction_result}")
            return None


        if not page_content.strip():
            logger.info(f"Kein substantieller Inhalt von {source_url} für Analyse gefunden.")
            return {"stance": "neutral", "confidence": 0.1, "evidence": "Kein Inhalt extrahiert.", "reasoning": "Seite lieferte keinen Text.", "source": source_details}


        # Begrenze Inhalt für Analyse, um Kosten und Zeit zu sparen
        content_for_analysis = page_content[:4000] # Max 4000 Zeichen für die Analyse

        if client.api_key:
            analysis_output = await _gpt_analyze_content(content_for_analysis, fact_to_check, source_details)
        else:
            logger.warning(f"Kein OpenAI Key, verwende einfache Inhaltsanalyse für {source_url}.")
            analysis_output = _simple_content_analysis(content_for_analysis, fact_to_check, source_details)

        return analysis_output

    except Exception as e:
        logger.error(f"Fehler bei der Analyse von Quelle {source_url}: {e}", exc_info=True)
        return None # Gib None zurück, um anzuzeigen, dass die Analyse dieser Quelle fehlgeschlagen ist

async def _gpt_analyze_content(content: str, fact: str, source_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nutzt GPT zur Analyse, ob der Content den Fakt unterstützt, widerlegt oder neutral ist.
    """
    prompt = f"""
    Analysiere, ob der folgende Inhalt den gegebenen Fakt UNTERSTÜTZT, WIDERLEGT oder NEUTRAL dazu ist.
    Sei präzise und antworte nur mit dem unten spezifizierten JSON-Format.

    FAKT: "{fact}"

    INHALT (Auszug):
    "{content}"

    Antworte im JSON-Format:
    {{
        "stance": "supports" | "contradicts" | "neutral",
        "confidence": <float, 0.0 bis 1.0, wie sicher du dir bei 'stance' bist>,
        "evidence_quote": "<kurze, direkte Textstelle aus INHALT, die deine 'stance' belegt, max. 200 Zeichen>",
        "reasoning": "<kurze Erklärung deiner Bewertung, 1-2 Sätze>"
    }}
    Wenn der Inhalt den Fakt nicht direkt adressiert oder die Information nicht ausreicht, setze stance auf "neutral".
    """
    try:
        logger.debug(f"Starte GPT-Inhaltsanalyse für Fakt: {fact[:50]}... auf {source_info.get('url')}")
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o", # Oder "gpt-3.5-turbo" für schnellere/günstigere Analyse
            messages=[
                {"role": "system", "content": "Du bist ein Experte für Faktenanalyse und Inhaltsbewertung. Antworte immer nur im spezifizierten JSON-Format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=300, # Angepasst für kürzere JSON-Antwort
            response_format={"type": "json_object"}
        )
        await asyncio.sleep(0.5) # Pause

        analysis_str = response.choices[0].message.content if response.choices and response.choices[0].message else "{}"
        try:
            analysis_data = json.loads(analysis_str)
        except json.JSONDecodeError:
            logger.error(f"JSONDecodeError bei GPT-Inhaltsanalyse. Antwort: '{analysis_str}'")
            # Fallback, falls JSON fehlschlägt
            return {"stance": "neutral", "confidence": 0.2, "evidence_quote": "Fehler bei Analyse.", "reasoning": "GPT-Antwort war kein valides JSON.", "source": source_info}

        # Füge Quelleninfo zur Analyse hinzu
        analysis_data["source"] = {
            "url": source_info.get("url"),
            "title": source_info.get("title"),
            "domain": source_info.get("domain")
        }
        logger.info(f"GPT-Inhaltsanalyse für {source_info.get('url')} abgeschlossen. Stance: {analysis_data.get('stance')}")
        return analysis_data

    except Exception as e:
        logger.error(f"Allgemeiner Fehler bei GPT-Inhaltsanalyse für {source_info.get('url')}: {e}", exc_info=True)
        # Fallback bei generellem Fehler
        return {"stance": "neutral", "confidence": 0.1, "evidence_quote": "Fehler bei Analyse.", "reasoning": f"Ausnahme: {str(e)}", "source": source_info}

def _simple_content_analysis(content: str, fact: str, source_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Einfache Keyword-basierte Analyse als Fallback.
    """
    content_lower = content.lower()
    fact_lower = fact.lower()
    keywords = [word for word in fact_lower.split() if len(word) > 3 and word not in ["der", "die", "das", "ist", "sind", "und", "oder"]] # Stopwörter

    if not keywords: # Falls Fakt zu kurz oder nur Stopwörter enthält
        return {"stance": "neutral", "confidence": 0.2, "evidence_quote": source_info.get("snippet","")[:150], "reasoning": "Fakt zu kurz für Keyword-Analyse.", "source": source_info}

    matches = sum(1 for keyword in keywords if keyword in content_lower)
    match_ratio = matches / len(keywords)
    negations = ["nicht", "kein", "kaum", "falsch", "widerlegt", "mythos", "irrtum", "fehlerhaft", "unwahr"]
    has_negation_near_keywords = False
    if matches > 0:
        for keyword in keywords:
            if keyword in content_lower:
                idx = content_lower.find(keyword)
                # Suche nach Negationen im Umkreis von z.B. 50 Zeichen
                window = content_lower[max(0, idx - 50):min(len(content_lower), idx + len(keyword) + 50)]
                if any(neg in window for neg in negations):
                    has_negation_near_keywords = True
                    break
    stance = "neutral"
    confidence = 0.3 # Grundkonfidenz für einfache Analyse
    if match_ratio > 0.6: # Erfordert eine gute Überlappung
        stance = "contradicts" if has_negation_near_keywords else "supports"
        confidence = min(0.7, match_ratio * 0.8) # Skaliere Konfidenz
    elif match_ratio > 0.3:
        confidence = 0.4 # Leichte Tendenz, aber noch neutral

    return {
        "stance": stance, "confidence": round(confidence,2),
        "evidence_quote": source_info.get("snippet", "")[:150], # Nutze Snippet als "Beweis"
        "reasoning": f"Einfache Keyword-Analyse: {matches}/{len(keywords)} Keywords gefunden. Negation in Nähe: {has_negation_near_keywords}.",
        "source": source_info
    }

def _evaluate_verification_results(
    result_obj: FactVerificationResult,
    source_analyses: List[Optional[Dict[str, Any]]], # Kann None-Elemente enthalten
    require_multiple_sources: bool
) -> Dict[str, Any]:
    """
    Bewertet alle Quellenanalysen und erstellt ein Gesamtergebnis.
    """
    valid_analyses = [ana for ana in source_analyses if isinstance(ana, dict)] # Filtert None-Werte heraus

    supporting = [ana for ana in valid_analyses if ana.get("stance") == "supports"]
    contradicting = [ana for ana in valid_analyses if ana.get("stance") == "contradicts"]

    if supporting and not contradicting:
        avg_confidence = sum(s.get("confidence", 0.0) for s in supporting) / len(supporting)
        if require_multiple_sources and len(supporting) < 2:
            result_obj.status = "unverified"
            result_obj.confidence = avg_confidence * 0.7
            result_obj.analysis = f"Fakt tendenziell unterstützt durch {len(supporting)} Quelle, aber mehrere Quellen gefordert."
        else:
            result_obj.status = "verified"
            result_obj.confidence = avg_confidence
            result_obj.analysis = f"Fakt durch {len(supporting)} Quelle(n) bestätigt."
    elif contradicting and not supporting:
        result_obj.status = "disputed"
        result_obj.confidence = sum(c.get("confidence", 0.0) for c in contradicting) / len(contradicting)
        result_obj.analysis = f"Fakt durch {len(contradicting)} Quelle(n) widerlegt/bestritten."
    elif supporting and contradicting:
        result_obj.status = "disputed"
        support_score = sum(s.get("confidence", 0.0) for s in supporting)
        contradict_score = sum(c.get("confidence", 0.0) for c in contradicting)
        # Einfache Konfidenz basierend auf der stärkeren Seite, wenn gemischt
        result_obj.confidence = max(support_score/len(supporting) if supporting else 0, contradict_score/len(contradicting) if contradicting else 0) * 0.8 # Reduziere bei Konflikt
        result_obj.analysis = f"Fakt ist umstritten: {len(supporting)} unterstützende, {len(contradicting)} widerlegende Quelle(n) gefunden."
    else: # Keine klaren unterstützenden oder widerlegenden Quellen
        result_obj.status = "unverified"
        result_obj.confidence = 0.2 # Niedrige Konfidenz, da keine klaren Beweise
        result_obj.analysis = "Keine ausreichenden oder eindeutigen Belege gefunden (neutral oder Analyse fehlgeschlagen)."

    result_obj.supporting_sources = supporting
    result_obj.contradicting_sources = contradicting
    return result_obj.to_dict()


def _create_verification_summary(results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Erstellt eine Zusammenfassung aller Verifikationsergebnisse.
    """
    if not results_list: return {"total_facts": 0, "verified": 0, "disputed": 0, "unverified": 0, "error_count":0, "average_confidence": 0.0}

    verified_count = sum(1 for r in results_list if r.get("status") == "verified")
    disputed_count = sum(1 for r in results_list if r.get("status") == "disputed")
    unverified_count = sum(1 for r in results_list if r.get("status") == "unverified")
    error_count = sum(1 for r in results_list if r.get("status") == "error")

    confidences = [r.get("confidence", 0.0) for r in results_list if isinstance(r.get("confidence"), (float, int)) and r.get("status") != "error"]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "total_facts_processed": len(results_list),
        "verified_count": verified_count,
        "disputed_count": disputed_count,
        "unverified_count": unverified_count,
        "error_count": error_count,
        "average_confidence_of_non_error": round(avg_conf, 2),
    }

@tool(
    name="clear_fact_cache",
    description="Leert den Cache für verifizierte Fakten.",
    parameters=[],
    capabilities=["analysis", "fact_check"],
    category=C.ANALYSIS
)
async def clear_fact_cache() -> dict:
    """ Leert den Cache für verifizierte Fakten. """
    global verified_facts_cache
    count = len(verified_facts_cache)
    verified_facts_cache.clear() # Verwende clear() für Dictionaries
    logger.info(f"Fakten-Cache mit {count} Einträgen geleert.")
    return {"status": "cache_cleared", "cleared_items": count}

@tool(
    name="get_fact_verification_stats",
    description="Gibt Statistiken über bisherige Verifikationen zurück.",
    parameters=[],
    capabilities=["analysis", "fact_check"],
    category=C.ANALYSIS
)
async def get_fact_verification_stats() -> dict:
    """ Gibt Statistiken über bisherige Verifikationen zurück. """
    # Diese Funktion bleibt im Wesentlichen gleich, aber die Logik
    # zum Zählen der Domains und Konfidenzen wird durch die Struktur
    # der 'verified_facts_cache' und 'FactVerificationResult' beeinflusst.
    stats = {
        "cached_facts_count": len(verified_facts_cache),
        "status_breakdown": {"verified": 0, "disputed": 0, "unverified": 0, "error": 0},
        "average_confidence_in_cache": 0.0,
        "top_supporting_domains": {}, # Beispiel für erweiterte Statistik
        "top_contradicting_domains": {}
    }
    all_confidences_in_cache = []
    supporting_domains_count: Dict[str, int] = {}
    contradicting_domains_count: Dict[str, int] = {}

    for fact_data in verified_facts_cache.values(): # Iteriere über die Dicts im Cache
        status = fact_data.get("status", "unverified")
        stats["status_breakdown"][status] = stats["status_breakdown"].get(status, 0) + 1
        if isinstance(fact_data.get("confidence"), (float, int)):
            all_confidences_in_cache.append(fact_data["confidence"])

        for source_ana in fact_data.get("supporting_sources", []):
            domain = source_ana.get("source", {}).get("domain")
            if domain: supporting_domains_count[domain] = supporting_domains_count.get(domain, 0) + 1
        for source_ana in fact_data.get("contradicting_sources", []):
            domain = source_ana.get("source", {}).get("domain")
            if domain: contradicting_domains_count[domain] = contradicting_domains_count.get(domain, 0) + 1

    if all_confidences_in_cache:
        stats["average_confidence_in_cache"] = round(sum(all_confidences_in_cache) / len(all_confidences_in_cache), 2)

    stats["top_supporting_domains"] = dict(sorted(supporting_domains_count.items(), key=lambda item: item[1], reverse=True)[:5])
    stats["top_contradicting_domains"] = dict(sorted(contradicting_domains_count.items(), key=lambda item: item[1], reverse=True)[:5])

    return stats

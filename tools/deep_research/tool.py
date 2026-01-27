# tools/deep_research/tool.py (FIXED VERSION - Timus Deep Research Engine v4.0)
"""
Vollständig reparierte Deep Research Engine.
Fixes:
1. Korrektes Handling von call_tool_internal Rückgabewerten
2. Parameter-Namen konsistent mit Agent
3. Robuste Fehlerbehandlung
4. Start-Zeit für Session tracking
"""

import asyncio
import json
import logging
import os
import re
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
from dotenv import load_dotenv
from jsonrpcserver import method, Success, Error
from openai import OpenAI, RateLimitError

# Interne Imports
from tools.planner.planner_helpers import call_tool_internal
from tools.universal_tool_caller import register_tool

# Tenacity für Retry-Logik
try:
    from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False

# Numpy für Embeddings - optional
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# --- Setup ---
logger = logging.getLogger("deep_research_tool")
load_dotenv()

# Konstanten
MIN_RELEVANCE_SCORE_FOR_SOURCES = 0.4
MAX_DEPTH_CONFIG = 3
DEFAULT_TIMEOUT_SEARCH = 60

# Modellwahl
SMART_MODEL = os.getenv("SMART_MODEL", "gpt-4o")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# OpenAI Client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Modelle die max_completion_tokens brauchen (statt max_tokens)
NEW_API_MODELS = {"gpt-5", "gpt-4.5", "o1", "o3", "o4", "gpt-5.2"}

def _get_token_param_name(model: str) -> str:
    """Bestimmt ob max_tokens oder max_completion_tokens verwendet werden soll."""
    model_lower = model.lower()
    for prefix in NEW_API_MODELS:
        if prefix in model_lower:
            return "max_completion_tokens"
    return "max_tokens"

# --- Helper: Robuster LLM Aufruf mit optionalem Retry ---
async def _call_llm_for_facts(messages: List[Dict[str, Any]], use_json: bool = True) -> Any:
    """Wrapper für LLM-Aufrufe - mit oder ohne Retry je nach Installation."""
    token_param = _get_token_param_name(SMART_MODEL)
    
    kwargs = {
        "model": SMART_MODEL,
        "messages": messages,
        "temperature": 0.0,
        token_param: 2000,  # Dynamisch max_tokens oder max_completion_tokens
    }
    
    if use_json:
        kwargs["response_format"] = {"type": "json_object"}
    
    logger.debug(f"LLM-Aufruf mit {token_param}=2000, model={SMART_MODEL}")
    
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            **kwargs
        )
        return response
    except RateLimitError as e:
        logger.warning(f"Rate Limit erreicht, warte 30s: {e}")
        await asyncio.sleep(30)
        response = await asyncio.to_thread(
            client.chat.completions.create,
            **kwargs
        )
        return response
    except Exception as e:
        # Bei Parameterfehler automatisch andere Variante versuchen
        if "max_tokens" in str(e) or "max_completion_tokens" in str(e):
            alt_param = "max_completion_tokens" if token_param == "max_tokens" else "max_tokens"
            logger.warning(f"Token-Parameter-Fehler, versuche {alt_param}")
            kwargs.pop(token_param)
            kwargs[alt_param] = 2000
            response = await asyncio.to_thread(
                client.chat.completions.create,
                **kwargs
            )
            return response
        raise

# --- Datenstrukturen ---
class ResearchNode:
    """Repräsentiert eine einzelne Quelle im Recherche-Baum."""
    def __init__(self, url: str, title: str, content_snippet: str, depth: int = 0, parent: Optional['ResearchNode'] = None):
        self.url = url
        self.title = title
        self.content_snippet = content_snippet
        self.depth = depth
        self.parent = parent
        self.children: List['ResearchNode'] = []
        self.relevance_score: float = 0.0
        self.key_facts: List[Dict[str, Any]] = []


class DeepResearchSession:
    """Verwaltet den Zustand einer Tiefenrecherche-Session."""
    def __init__(self, query: str, focus_areas: Optional[List[str]] = None):
        self.query = query
        self.focus_areas = focus_areas if focus_areas is not None else []
        self.research_tree: List[ResearchNode] = []
        self.visited_urls: set[str] = set()
        self.all_extracted_facts_raw: List[Dict[str, Any]] = []
        self.verified_facts: List[Dict[str, Any]] = []
        self.unverified_claims: List[Dict[str, Any]] = []
        self.conflicting_info: List[Dict[str, Any]] = []
        self.start_time: str = datetime.now().isoformat()  # FIX: start_time hinzugefügt

    def add_node(self, node: ResearchNode):
        """Fügt einen Node zum Recherche-Baum hinzu."""
        self.research_tree.append(node)
        if node.parent:
            node.parent.children.append(node)
        self.visited_urls.add(self._get_canonical_url(node.url))

    def _get_canonical_url(self, url: str) -> str:
        """Normalisiert URLs für Deduplizierung."""
        try:
            parsed = urlparse(url)
            # Entferne Tracking-Parameter
            filtered_query = {k: v for k, v in parse_qs(parsed.query).items() 
                           if k not in ['utm_source', 'utm_medium', 'utm_campaign', 'gclid', 'fbclid']}
            return urlunparse(parsed._replace(query=urlencode(filtered_query, doseq=True), fragment=''))
        except Exception:
            return url


# Globaler Session-Speicher
research_sessions: Dict[str, DeepResearchSession] = {}


# ==============================================================================
# 1. SUCHE & KONFIGURATION
# ==============================================================================

def get_adaptive_config(query: str, focus_areas: Optional[List[str]]) -> Dict[str, Any]:
    """Gibt eine adaptive Konfiguration basierend auf der Query zurück."""
    return {
        "max_initial_search_queries": 4,
        "max_results_per_search_query": 8,
        "max_sources_to_deep_dive": 6,
        "max_depth_for_links": 2,
        "max_chunks_per_source_for_facts": 3,
        "parallel_source_analysis_limit": 2  # Reduziert für Stabilität
    }


async def _perform_initial_search(query: str, session: DeepResearchSession) -> List[Dict[str, Any]]:
    """
    Führt die initiale Websuche durch.
    FIX: Korrektes Handling der call_tool_internal Rückgabewerte.
    """
    logger.info(f"🔎 Initiale Suche: '{query}'")
    
    # Erstelle verschiedene Suchvarianten
    queries = [query]
    if session.focus_areas:
        queries.append(f"{query} {' '.join(session.focus_areas[:2])}")
    queries.append(f"{query} Analyse Fakten")
    
    all_results: List[Dict[str, Any]] = []
    
    for q in queries[:3]:  # Maximal 3 Suchen
        try:
            result = await call_tool_internal(
                "search_web",
                {"query": q, "max_results": 8, "engine": "google", "vertical": "organic"},
                timeout=DEFAULT_TIMEOUT_SEARCH
            )
            
            # FIX: Korrektes Handling verschiedener Rückgabetypen
            if isinstance(result, list):
                all_results.extend(result)
            elif isinstance(result, dict):
                if "error" in result:
                    logger.warning(f"Suchfehler für '{q}': {result.get('error')}")
                elif "results" in result:
                    all_results.extend(result.get("results", []))
                else:
                    # Einzelnes Ergebnis
                    all_results.append(result)
            
            # Kurze Pause zwischen Suchen
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Fehler bei Suche '{q}': {e}")
            continue
    
    # Deduplizierung und Scoring
    unique_urls = set()
    final_results: List[Dict[str, Any]] = []
    
    for r in all_results:
        if not isinstance(r, dict):
            continue
            
        url = r.get("url", "")
        if not url or url in unique_urls:
            continue
            
        unique_urls.add(url)
        
        # Heuristisches Scoring
        score = 0.5
        url_lower = url.lower()
        
        # Bonus für vertrauenswürdige Quellen
        if any(domain in url_lower for domain in [".gov", ".edu", ".org"]):
            score += 0.2
        if "wikipedia" in url_lower:
            score += 0.15
        if ".pdf" in url_lower:
            score += 0.1
            
        # Malus für Social Media
        if any(social in url_lower for social in ["facebook.com", "twitter.com", "instagram.com"]):
            score -= 0.2
            
        r["score"] = min(score, 1.0)
        r["canonical_url"] = session._get_canonical_url(url)
        final_results.append(r)
    
    # Sortiere nach Score
    final_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    logger.info(f"✅ {len(final_results)} einzigartige Quellen gefunden")
    return final_results[:20]


async def _evaluate_relevance(
    sources: List[Dict], 
    query: str, 
    focus: List[str], 
    max_sources_to_return: int
) -> List[Tuple[Dict, float]]:
    """Bewertet die Relevanz der Quellen."""
    logger.info(f"⚖️ Bewerte Relevanz von {len(sources)} Quellen...")
    
    # Heuristische Bewertung basierend auf Titel und Snippet
    relevant: List[Tuple[Dict, float]] = []
    
    query_terms = set(query.lower().split())
    focus_terms = set(" ".join(focus).lower().split()) if focus else set()
    all_terms = query_terms | focus_terms
    
    for source in sources:
        base_score = source.get("score", 0.5)
        
        # Erhöhe Score basierend auf Keyword-Matches
        title = source.get("title", "").lower()
        snippet = source.get("snippet", "").lower()
        combined_text = f"{title} {snippet}"
        
        matches = sum(1 for term in all_terms if term in combined_text)
        keyword_bonus = min(matches * 0.05, 0.3)
        
        final_score = base_score + keyword_bonus
        
        if final_score >= MIN_RELEVANCE_SCORE_FOR_SOURCES:
            relevant.append((source, final_score))
    
    # Sortiere und limitiere
    relevant.sort(key=lambda x: x[1], reverse=True)
    return relevant[:max_sources_to_return]


# ==============================================================================
# 2. EXTRAKTION & VERARBEITUNG
# ==============================================================================

async def _fetch_page_content(url: str) -> str:
    """
    Holt den Inhalt einer Seite.
    FIX: Robustes Handling verschiedener Rückgabetypen.
    """
    content = ""
    
    try:
        if url.lower().endswith(".pdf"):
            # PDF-Extraktion
            result = await call_tool_internal("extract_text_from_pdf", {"pdf_url": url}, timeout=60)
            if isinstance(result, dict):
                content = result.get("text", "") or result.get("content", "")
            elif isinstance(result, str):
                content = result
        else:
            # HTML-Seite öffnen
            open_result = await call_tool_internal("open_url", {"url": url}, timeout=30)
            
            if isinstance(open_result, dict) and open_result.get("error"):
                logger.warning(f"Fehler beim Öffnen von {url}: {open_result.get('error')}")
                return ""
            
            # Text extrahieren
            text_result = await call_tool_internal("get_text", {}, timeout=30)
            
            if isinstance(text_result, dict):
                content = text_result.get("text", "") or text_result.get("content", "")
            elif isinstance(text_result, str):
                content = text_result
                
    except Exception as e:
        logger.error(f"Fehler beim Abrufen von {url}: {e}")
        return ""
    
    return content


async def _extract_key_facts(text_content: str, query: str, url: str, config: Dict) -> List[Dict]:
    """Extrahiert Schlüsselfakten aus dem Text mittels LLM."""
    if not text_content or len(text_content) < 100:
        return []
    
    # Text in Chunks aufteilen
    max_chunk_size = 3000
    chunks = [text_content[i:i+max_chunk_size] for i in range(0, len(text_content), max_chunk_size)]
    chunks = chunks[:config.get("max_chunks_per_source_for_facts", 3)]
    
    all_facts: List[Dict] = []
    
    for chunk in chunks:
        prompt = f"""Extrahiere wichtige Fakten zum Thema "{query}" aus dem folgenden Text.

TEXT:
{chunk[:2500]}

Gib die Fakten als JSON zurück:
{{
    "facts": [
        {{
            "fact": "Die konkrete Aussage/Fakt",
            "fact_type": "statistic|statement|quote|date",
            "source_quote": "Originalzitat aus dem Text",
            "confidence": "high|medium|low"
        }}
    ]
}}

Regeln:
- Nur verifizierbare Fakten, keine Meinungen
- Maximal 5 Fakten pro Chunk
- confidence: high = mit Zahlen/Quellen belegt, medium = plausibel, low = unklar"""

        try:
            response = await _call_llm_for_facts([
                {"role": "system", "content": "Du bist ein Fakten-Extraktor. Antworte nur mit validem JSON."},
                {"role": "user", "content": prompt}
            ])
            
            content = response.choices[0].message.content
            data = json.loads(content)
            
            for fact in data.get("facts", []):
                fact["source_url"] = url
                all_facts.append(fact)
                
        except Exception as e:
            logger.warning(f"Fehler bei Fakten-Extraktion: {e}")
            continue
        
        # Rate Limiting
        await asyncio.sleep(0.3)
    
    return all_facts


async def _process_source_safe(
    source_data: Dict, 
    session: DeepResearchSession, 
    semaphore: asyncio.Semaphore,
    config: Dict
):
    """Verarbeitet eine Quelle mit Semaphore-Schutz."""
    async with semaphore:
        url = source_data.get("url", "")
        title = source_data.get("title", "Unbekannt")
        
        logger.info(f"🔄 Verarbeite: {title[:50]}...")
        
        # Inhalt abrufen
        content = await _fetch_page_content(url)
        
        if not content or len(content) < 200:
            logger.warning(f"Zu wenig Inhalt für {url}")
            return
        
        # Prüfe auf JavaScript-Only Seiten
        if "javascript" in content.lower()[:500] and len(content) < 500:
            logger.warning(f"Vermutlich JS-only Seite: {url}")
            return
        
        # Node erstellen
        node = ResearchNode(
            url=url,
            title=title,
            content_snippet=content[:500],
            depth=0
        )
        session.add_node(node)
        
        # Fakten extrahieren
        facts = await _extract_key_facts(content, session.query, url, config)
        node.key_facts = facts
        session.all_extracted_facts_raw.extend(facts)
        
        logger.info(f"✅ {len(facts)} Fakten aus {title[:30]}...")


async def _deep_dive_sources(
    sources_to_analyze: List[Tuple[Dict[str, Any], float]],
    session_instance: DeepResearchSession,
    max_dive_depth: Optional[int],
    verification_mode: str,
    config: Dict[str, Any]
):
    """Die Hauptschleife für die Tiefenanalyse."""
    if not sources_to_analyze:
        logger.warning("Keine Quellen zum Analysieren")
        return
    
    # FIX: max_dive_depth auf Default setzen wenn None
    if max_dive_depth is None:
        max_dive_depth = MAX_DEPTH_CONFIG
    
    semaphore = asyncio.Semaphore(config.get("parallel_source_analysis_limit", 2))
    
    tasks = [
        _process_source_safe(src[0], session_instance, semaphore, config)
        for src in sources_to_analyze
    ]
    
    # Führe Tasks aus und fange Fehler ab
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Logge Fehler
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Fehler bei Quelle {i}: {result}")


# ==============================================================================
# 3. VERIFIZIERUNG & SYNTHESE
# ==============================================================================

async def _get_embeddings(texts: List[str]) -> List[List[float]]:
    """Holt Embeddings für Texte."""
    if not texts or not HAS_NUMPY:
        return []
    
    try:
        response = await asyncio.to_thread(
            client.embeddings.create,
            input=texts[:50],  # Limit
            model=EMBEDDING_MODEL
        )
        return [e.embedding for e in response.data]
    except Exception as e:
        logger.warning(f"Embedding-Fehler: {e}")
        return []


async def _group_similar_facts(facts: List[Dict[str, Any]], threshold: float = 0.85) -> List[List[Dict[str, Any]]]:
    """Gruppiert ähnliche Fakten basierend auf Embeddings."""
    if len(facts) < 2:
        return [[f] for f in facts]
    
    if not HAS_NUMPY:
        # Fallback: Einfache Textähnlichkeit
        return [[f] for f in facts]
    
    texts = [f.get("fact", "") for f in facts]
    embeddings = await _get_embeddings(texts)
    
    if not embeddings or len(embeddings) != len(facts):
        return [[f] for f in facts]
    
    # Ähnlichkeitsmatrix berechnen
    arr = np.array(embeddings)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Division durch 0 verhindern
    normalized = arr / norms
    sim_matrix = np.dot(normalized, normalized.T)
    
    # Clustering
    groups: List[List[Dict[str, Any]]] = []
    processed: set = set()
    
    for i in range(len(facts)):
        if i in processed:
            continue
        
        sim_indices = np.where(sim_matrix[i] >= threshold)[0]
        group = [facts[idx] for idx in sim_indices if idx not in processed]
        processed.update(sim_indices.tolist())
        
        if group:
            groups.append(group)
    
    return groups


async def _verify_facts(session: DeepResearchSession, verification_mode_setting: str) -> Dict[str, Any]:
    """Verifiziert Fakten basierend auf mehreren Quellen."""
    logger.info("🕵️ Starte Fakten-Verifizierung...")
    
    raw_facts = session.all_extracted_facts_raw
    if not raw_facts:
        return {"verified_facts": [], "unverified_claims": [], "conflicts": []}
    
    # Gruppiere ähnliche Fakten
    grouped = await _group_similar_facts(raw_facts)
    
    verified: List[Dict] = []
    unverified: List[Dict] = []
    
    for group in grouped:
        if not group:
            continue
        
        main_fact = group[0]
        sources = set(f.get("source_url") for f in group if f.get("source_url"))
        source_count = len(sources)
        
        # Bewertung basierend auf Quellen-Anzahl
        conf_numeric = 0.4
        status = "unverified"
        conf_text = "low"
        
        if verification_mode_setting == "strict":
            if source_count >= 3:
                status = "verified"
                conf_text = "high"
                conf_numeric = 0.9
            elif source_count == 2:
                status = "verified"
                conf_text = "medium"
                conf_numeric = 0.75
        else:  # moderate oder light
            if source_count >= 2:
                status = "verified"
                conf_text = "high"
                conf_numeric = 0.85
            elif source_count == 1:
                status = "tentatively_verified"
                conf_text = "medium"
                conf_numeric = 0.6
        
        fact_output = {
            "fact": main_fact.get("fact"),
            "status": status,
            "confidence": conf_text,
            "confidence_score_numeric": round(conf_numeric, 2),
            "source_count": source_count,
            "example_source_url": list(sources)[0] if sources else None,
            "supporting_quotes": [main_fact.get("source_quote")] if main_fact.get("source_quote") else []
        }
        
        if status in ["verified", "tentatively_verified"]:
            verified.append(fact_output)
        else:
            unverified.append(fact_output)
    
    session.verified_facts = verified
    session.unverified_claims = unverified
    
    logger.info(f"✅ Verifizierung abgeschlossen: {len(verified)} verifiziert, {len(unverified)} unverifiziert")
    
    return {
        "verified_facts": verified,
        "unverified_claims": unverified,
        "conflicts": []
    }


def _get_research_metadata_summary(session: DeepResearchSession) -> Dict[str, Any]:
    """Erstellt eine Zusammenfassung der Recherche-Metadaten."""
    return {
        "original_query": session.query,
        "focus_areas": session.focus_areas,
        "start_time": session.start_time,
        "total_sources_processed": len(session.visited_urls),
        "total_facts_extracted": len(session.all_extracted_facts_raw),
        "verified_facts_count": len(session.verified_facts),
        "unverified_claims_count": len(session.unverified_claims)
    }


async def _synthesize_findings(session: DeepResearchSession, verification_output: Dict) -> Dict:
    """Erstellt eine KI-Synthese der Erkenntnisse."""
    logger.info("📝 Erstelle Synthese...")
    
    facts = verification_output.get("verified_facts", [])[:30]
    
    if not facts:
        return {
            "executive_summary": "Keine verifizierten Fakten gefunden.",
            "key_findings": [],
            "research_metadata_summary": _get_research_metadata_summary(session)
        }
    
    facts_text = "\n".join([f"- {f.get('fact')}" for f in facts[:20]])
    
    prompt = f"""Erstelle eine strukturierte Analyse für die Recherche "{session.query}".

VERIFIZIERTE FAKTEN:
{facts_text}

Antworte als JSON:
{{
    "executive_summary": "2-3 Sätze Zusammenfassung",
    "key_findings": ["Erkenntnis 1", "Erkenntnis 2", "Erkenntnis 3"],
    "detailed_analysis": "Detaillierte Analyse in 2-3 Absätzen",
    "knowledge_gaps": ["Was noch unklar ist"]
}}"""

    try:
        response = await _call_llm_for_facts([
            {"role": "system", "content": "Du bist ein Forschungsanalyst. Antworte nur mit validem JSON."},
            {"role": "user", "content": prompt}
        ])
        
        data = json.loads(response.choices[0].message.content)
        data["research_metadata_summary"] = _get_research_metadata_summary(session)
        return data
        
    except Exception as e:
        logger.error(f"Synthese-Fehler: {e}")
        return {
            "executive_summary": f"Recherche zu '{session.query}' abgeschlossen.",
            "key_findings": [f.get("fact") for f in facts[:5]],
            "research_metadata_summary": _get_research_metadata_summary(session)
        }


# ==============================================================================
# REPORT FORMATTING
# ==============================================================================

def _create_markdown_report(session: DeepResearchSession, include_source_details: bool = True) -> str:
    """Erstellt einen Markdown-Report."""
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    
    lines = [
        f"# 🔬 Tiefenrecherche: {session.query}",
        f"**Datum:** {now}",
        ""
    ]
    
    if session.focus_areas:
        lines.append(f"**Fokus:** {', '.join(session.focus_areas)}")
        lines.append("")
    
    meta = _get_research_metadata_summary(session)
    lines.append(f"**Analysierte Quellen:** {meta['total_sources_processed']} | "
                f"**Extrahierte Fakten:** {meta['total_facts_extracted']} | "
                f"**Verifiziert:** {meta['verified_facts_count']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Verifizierte Fakten
    lines.append("## ✅ Verifizierte Kernaussagen")
    lines.append("")
    
    if session.verified_facts:
        for i, f in enumerate(session.verified_facts[:15], 1):
            icon = "🟢" if f.get('confidence') == 'high' else "🟡"
            lines.append(f"**{i}. {icon} {f.get('fact')}**")
            lines.append(f"   - Quellen: {f.get('source_count')} | Status: {f.get('status')}")
            if f.get('example_source_url'):
                lines.append(f"   - [Quelle]({f.get('example_source_url')})")
            lines.append("")
    else:
        lines.append("_Keine Fakten verifiziert._")
        lines.append("")
    
    # Unverifizierte Behauptungen
    if session.unverified_claims:
        lines.append("## ⚠️ Unverifizierte Behauptungen")
        lines.append("")
        for i, f in enumerate(session.unverified_claims[:10], 1):
            lines.append(f"- {f.get('fact')} *(nur 1 Quelle)*")
        lines.append("")
    
    # Quellenverzeichnis
    if include_source_details and session.research_tree:
        lines.append("## 📚 Quellenverzeichnis")
        lines.append("")
        for i, node in enumerate(session.research_tree[:15], 1):
            lines.append(f"{i}. [{node.title}]({node.url})")
        lines.append("")
    
    lines.append("---")
    lines.append(f"*Generiert von Timus Deep Research Engine v4.0 • {now}*")
    
    return "\n".join(lines)


def _create_text_report(session: DeepResearchSession, include_source_details: bool = True) -> str:
    """Erstellt einen Text-Report (ohne Markdown)."""
    md = _create_markdown_report(session, include_source_details)
    # Konvertiere Markdown zu Plain Text
    text = md.replace("# ", "=== ").replace("## ", "--- ")
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold entfernen
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'\1 (\2)', text)  # Links
    return text


# ==============================================================================
# ÖFFENTLICHE RPC-METHODEN
# ==============================================================================

@method
async def start_deep_research(
    query: str,
    focus_areas: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    verification_mode: str = "strict"
) -> Union[Success, Error]:
    """
    Startet eine Tiefenrecherche zu einem Thema.
    
    Args:
        query: Die Hauptsuchanfrage
        focus_areas: Optionale Liste von Fokusthemen
        max_depth: Maximale Tiefe der Recherche (1-5)
        verification_mode: "strict", "moderate" oder "light"
    
    Returns:
        Success mit session_id und Analyseergebnissen
    """
    # Session erstellen
    session_id = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    current_session = DeepResearchSession(query, focus_areas)
    research_sessions[session_id] = current_session
    
    try:
        logger.info(f"🔬 Starte Deep Research Session {session_id}: '{query}'")
        config = get_adaptive_config(query, current_session.focus_areas)
        
        # 1. Initiale Suche
        initial_sources = await _perform_initial_search(query, current_session)
        
        if not initial_sources:
            return Success({
                "session_id": session_id,
                "status": "no_results",
                "message": "Keine Suchergebnisse gefunden."
            })
        
        # 2. Relevanz bewerten
        relevant_sources = await _evaluate_relevance(
            initial_sources,
            query,
            current_session.focus_areas,
            config["max_sources_to_deep_dive"]
        )
        
        if not relevant_sources:
            return Success({
                "session_id": session_id,
                "status": "no_relevant_sources",
                "message": "Keine relevanten Quellen gefunden."
            })
        
        # 3. Deep Dive
        await _deep_dive_sources(
            relevant_sources,
            current_session,
            max_depth,
            verification_mode,
            config
        )
        
        # 4. Fakten verifizieren
        verified_data = await _verify_facts(current_session, verification_mode)
        
        # 5. Synthese erstellen
        analysis = await _synthesize_findings(current_session, verified_data)
        
        logger.info(f"✅ Session {session_id} abgeschlossen")
        
        # 6. AUTOMATISCH Report erstellen und speichern
        filepath = None
        try:
            logger.info(f"📄 Erstelle automatisch Report für {session_id}...")
            
            # Markdown Report erstellen
            report_content = _create_markdown_report(current_session, include_source_details=True)
            
            # Direkt speichern (ohne Tool-Aufruf)
            from pathlib import Path
            
            possible_roots = [
                Path(__file__).resolve().parent.parent.parent,
                Path.cwd(),
                Path.home() / "dev" / "timus",
                Path("/home/fatih-ubuntu/dev/timus"),
            ]
            
            for root in possible_roots:
                candidate = root / "results"
                try:
                    candidate.mkdir(parents=True, exist_ok=True)
                    if candidate.exists() and candidate.is_dir():
                        filename = f"DeepResearch_{session_id}.md"
                        filepath = candidate / filename
                        
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(report_content)
                        
                        filepath = str(filepath)
                        logger.info(f"✅ Report gespeichert: {filepath}")
                        break
                except PermissionError:
                    continue
                except Exception as e:
                    logger.warning(f"Konnte nicht in {candidate} speichern: {e}")
                    continue
            
            if not filepath:
                logger.warning("⚠️ Report konnte nicht gespeichert werden - kein schreibbarer Ordner")
                
        except Exception as e:
            logger.error(f"❌ Fehler beim automatischen Speichern: {e}")
        
        return Success({
            "session_id": session_id,
            "status": "completed",
            "facts_extracted": len(current_session.all_extracted_facts_raw),
            "verified_count": len(current_session.verified_facts),
            "sources_analyzed": len(current_session.visited_urls),
            "analysis": analysis,
            "verified_data": verified_data,
            "report_filepath": filepath  # NEU: Pfad zum automatisch erstellten Report
        })
        
    except Exception as e:
        logger.error(f"❌ Fehler in Session {session_id}: {e}", exc_info=True)
        return Error(code=-32000, message=f"Recherche-Fehler: {str(e)}")


@method
async def get_research_status(session_id: str) -> Union[Success, Error]:
    """
    Gibt den Status einer laufenden oder abgeschlossenen Recherche zurück.
    
    Args:
        session_id: Die Session-ID (auch als session_id_param akzeptiert)
    """
    session = research_sessions.get(session_id)
    
    if not session:
        return Error(code=-32602, message=f"Session '{session_id}' nicht gefunden.")
    
    return Success({
        "session_id": session_id,
        "query": session.query,
        "summary": _get_research_metadata_summary(session)
    })


@method
async def generate_research_report(
    session_id: Optional[str] = None,
    session_id_to_report: Optional[str] = None,  # FIX: Alias für Kompatibilität
    format: str = "markdown",
    report_format_type: Optional[str] = None,  # FIX: Alias für Kompatibilität
    include_source_details: bool = True
) -> Union[Success, Error]:
    """
    Erstellt einen Bericht aus einer abgeschlossenen Recherche-Session.
    
    Args:
        session_id: Die Session-ID
        session_id_to_report: Alias für session_id (Kompatibilität)
        format: "markdown" oder "text"
        report_format_type: Alias für format (Kompatibilität)
        include_source_details: Ob Quellen aufgelistet werden sollen
    """
    # FIX: Parameter-Aliases auflösen
    actual_session_id = session_id or session_id_to_report
    actual_format = report_format_type or format
    
    if not actual_session_id:
        return Error(code=-32602, message="session_id ist erforderlich.")
    
    session = research_sessions.get(actual_session_id)
    
    if not session:
        return Error(code=-32602, message=f"Session '{actual_session_id}' nicht gefunden.")
    
    # Report erstellen
    if actual_format.lower() == "markdown":
        content = _create_markdown_report(session, include_source_details)
    else:
        content = _create_text_report(session, include_source_details)
    
    # Report speichern - mit Fallback
    filepath = None
    
    # Methode 1: Über save_research_result Tool
    try:
        save_result = await call_tool_internal("save_research_result", {
            "title": f"DeepResearch_Report_{actual_session_id}",
            "content": content,
            "format": actual_format.lower()
        }, timeout=30)
        
        logger.info(f"save_research_result Ergebnis: {save_result}")
        
        if isinstance(save_result, dict):
            if "error" not in save_result:
                filepath = save_result.get("filepath", save_result.get("filename"))
            else:
                logger.warning(f"save_research_result Fehler: {save_result.get('error')}")
    except Exception as e:
        logger.warning(f"save_research_result fehlgeschlagen: {e}")
    
    # Methode 2: Fallback - Direkt speichern
    if not filepath:
        logger.info("Fallback: Direktes Speichern...")
        try:
            from pathlib import Path
            
            # Versuche verschiedene Pfade
            possible_roots = [
                Path(__file__).resolve().parent.parent.parent,  # tools/deep_research -> project
                Path.cwd(),
                Path.home() / "dev" / "timus",
                Path("/home/fatih-ubuntu/dev/timus"),
            ]
            
            results_dir = None
            for root in possible_roots:
                candidate = root / "results"
                try:
                    candidate.mkdir(parents=True, exist_ok=True)
                    if candidate.exists():
                        results_dir = candidate
                        break
                except Exception:
                    continue
            
            if results_dir:
                ext = "md" if actual_format.lower() == "markdown" else "txt"
                filename = f"DeepResearch_Report_{actual_session_id}.{ext}"
                filepath = results_dir / filename
                
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                
                filepath = str(filepath)
                logger.info(f"✅ Direkt gespeichert: {filepath}")
            else:
                logger.error("Kein schreibbarer results-Ordner gefunden!")
                
        except Exception as e2:
            logger.error(f"Auch Fallback-Speicherung fehlgeschlagen: {e2}")
    
    if filepath:
        return Success({
            "session_id": actual_session_id,
            "status": "report_created",
            "format": actual_format,
            "filepath": filepath,
            "message": "Bericht erfolgreich erstellt.",
            "summary": _get_research_metadata_summary(session)
        })
    else:
        # Letzter Ausweg: Content im Response mitgeben
        return Success({
            "session_id": actual_session_id,
            "status": "report_created_not_saved",
            "format": actual_format,
            "content": content,  # Vollständiger Content
            "message": "Bericht erstellt, aber Speichern fehlgeschlagen. Content im Response.",
            "summary": _get_research_metadata_summary(session)
        })


# --- Registrierung der Tools ---
register_tool("start_deep_research", start_deep_research)
register_tool("get_research_status", get_research_status)
register_tool("generate_research_report", generate_research_report)

logger.info("✅ Deep Research Tool v4.0 (Fixed) registriert.")

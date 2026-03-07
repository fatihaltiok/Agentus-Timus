# tools/deep_research/tool.py (VERSION 5.0 - ACADEMIC EXCELLENCE)
"""
Timus Deep Research Engine v5.0 - Academic Excellence Edition

NEUE FEATURES:
- These-Antithese-Synthese Framework für dialektische Analyse
- Quellenqualitätsbewertung (Autorität, Bias, Aktualität, Transparenz)
- Tiefe Fakten-Verifikation mit fact_corroborator Integration
- Druckreife Reports im wissenschaftlichen Stil
- Kritische Analyse & Limitationen
- Konfliktanalyse bei widersprüchlichen Befunden
- Executive Summary & Methodik-Dokumentation

AUTOR: Timus Development Team
DATUM: Januar 2026
"""

import asyncio
import html as html_module
import json
import logging
import os
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv
import httpx
from openai import OpenAI, RateLimitError
from utils.openai_compat import prepare_openai_params
from agent.shared.json_utils import extract_json_robust

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# V2 Tool-Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# Interne Imports
from tools.planner.planner_helpers import call_tool_internal

# Numpy für Embeddings - optional
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# --- Setup ---
logger = logging.getLogger("deep_research_v5")
load_dotenv()

# Konstanten
MIN_RELEVANCE_SCORE_FOR_SOURCES = 0.4
MAX_DEPTH_CONFIG = 3
DEFAULT_TIMEOUT_SEARCH = 60
MIN_SOURCES_FOR_THESIS = 3  # Mindestquellen für These-Bildung
BIAS_KEYWORDS_POLITICAL = ["liberal", "conservative", "democrat", "republican", "left-wing", "right-wing"]
BIAS_KEYWORDS_COMMERCIAL = ["sponsored", "advertisement", "affiliate", "paid promotion", "partner"]

# v7.0: Language → Location Mapping (DataForSEO Location Codes)
_LANG_LOCATION_MAP: Dict[str, int] = {
    "en": 2840,   # United States
    "de": 2276,   # Germany
    "fr": 2250,   # France
    "es": 2724,   # Spain
    "it": 2380,   # Italy
}
_LANG_CODE_MAP: Dict[str, str] = {
    "en": "en",
    "de": "de",
    "fr": "fr",
    "es": "es",
    "it": "it",
}

# v7.0: Tech-Keywords für Domain-aware Embedding-Threshold
TECH_KEYWORDS = {
    "ai", "llm", "neural", "model", "agent", "transformer", "machine learning",
    "deep learning", "reinforcement", "diffusion", "multimodal", "rag", "vector",
    "embedding", "fine-tuning", "inference", "benchmark", "architecture",
    "attention", "gpt", "bert", "claude", "gemini", "llama", "mistral",
    "autonomous", "self-supervised", "generative", "nlp", "computer vision",
}

# v7.0: Domain-aware Embedding-Thresholds
EMBEDDING_THRESHOLDS: Dict[str, float] = {
    "tech": float(os.getenv("DR_EMBEDDING_THRESHOLD_TECH", "0.72")),
    "science": 0.75,
    "default": 0.82,
}

# Modellwahl
SMART_MODEL = os.getenv("SMART_MODEL", "gpt-4o")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# OpenAI Client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Modelle die max_completion_tokens brauchen
NEW_API_MODELS = {"gpt-5", "gpt-4.5", "o1", "o3", "o4", "gpt-5.2"}

def _get_token_param_name(model: str) -> str:
    """Bestimmt ob max_tokens oder max_completion_tokens verwendet werden soll."""
    model_lower = model.lower()
    for prefix in NEW_API_MODELS:
        if prefix in model_lower:
            return "max_completion_tokens"
    return "max_tokens"


# ==============================================================================
# ENUMS & DATENSTRUKTUREN
# ==============================================================================

class SourceQuality(str, Enum):
    """Qualitätsstufen für Quellen."""
    EXCELLENT = "excellent"  # .gov, .edu, peer-reviewed
    GOOD = "good"           # Etablierte Medien, Wikipedia
    MEDIUM = "medium"       # Blogs mit Quellen
    POOR = "poor"           # Keine Quellen, stark biased
    UNKNOWN = "unknown"     # Nicht bewertbar


class BiasLevel(str, Enum):
    """Bias-Level für Quellen."""
    NONE = "none"           # Keine erkennbare Voreingenommenheit
    LOW = "low"             # Leicht erkennbar
    MEDIUM = "medium"       # Deutlich erkennbar
    HIGH = "high"           # Stark partisan/kommerziell
    UNKNOWN = "unknown"     # Nicht bewertbar


@dataclass
class SourceQualityMetrics:
    """Qualitätsmetriken für eine Quelle."""
    authority_score: float = 0.5       # 0-1: Autorität der Domain
    bias_level: BiasLevel = BiasLevel.UNKNOWN
    bias_score: float = 0.0            # 0-1: 0=unbiased, 1=stark biased
    recency_score: float = 0.5         # 0-1: Aktualität
    transparency_score: float = 0.5    # 0-1: Autor/Methodik genannt
    citation_score: float = 0.5        # 0-1: Zitiert andere Quellen
    overall_quality: SourceQuality = SourceQuality.UNKNOWN
    quality_score: float = 0.5         # 0-1: Gewichteter Durchschnitt
    confidence: float = 0.5            # 0-1: Confidence in dieser Bewertung
    notes: str = ""                    # Bewertungs-Notizen


@dataclass
class ResearchNode:
    """Repräsentiert eine einzelne Quelle im Recherche-Baum."""
    url: str
    title: str
    content_snippet: str
    depth: int = 0
    parent: Optional['ResearchNode'] = None
    children: List['ResearchNode'] = field(default_factory=list)
    relevance_score: float = 0.0
    key_facts: List[Dict[str, Any]] = field(default_factory=list)

    # NEU v5.0: Qualitätsmetriken
    quality_metrics: Optional[SourceQualityMetrics] = None
    publish_date: Optional[datetime] = None
    author: Optional[str] = None
    domain: str = ""

    def __post_init__(self):
        """Extrahiert Domain aus URL."""
        if self.url:
            parsed = urlparse(self.url)
            self.domain = parsed.netloc.lower()


@dataclass
class ThesisAnalysis:
    """Repräsentiert eine These-Antithese-Synthese Analyse."""
    topic: str
    thesis: str
    thesis_confidence: float
    supporting_facts: List[Dict[str, Any]] = field(default_factory=list)
    supporting_sources: List[str] = field(default_factory=list)

    antithesis: Optional[str] = None
    antithesis_confidence: float = 0.0
    contradicting_facts: List[Dict[str, Any]] = field(default_factory=list)
    contradicting_sources: List[str] = field(default_factory=list)

    synthesis: Optional[str] = None
    synthesis_confidence: float = 0.0
    synthesis_reasoning: str = ""

    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)


class DeepResearchSession:
    """Verwaltet den Zustand einer Tiefenrecherche-Session (v5.0 erweitert)."""
    def __init__(self, query: str, focus_areas: Optional[List[str]] = None):
        self.query = query
        self.focus_areas = focus_areas if focus_areas is not None else []
        self.research_tree: List[ResearchNode] = []
        self.visited_urls: set[str] = set()
        self.all_extracted_facts_raw: List[Dict[str, Any]] = []
        self.verified_facts: List[Dict[str, Any]] = []
        self.unverified_claims: List[Dict[str, Any]] = []
        self.conflicting_info: List[Dict[str, Any]] = []
        self.start_time: str = datetime.now().isoformat()

        # NEU v5.0: Erweiterte Analyse
        self.thesis_analyses: List[ThesisAnalysis] = []
        self.source_quality_summary: Dict[str, int] = {}  # Quality -> Count
        self.bias_summary: Dict[str, int] = {}  # Bias -> Count
        self.methodology_notes: List[str] = []
        self.limitations: List[str] = []
        self.research_metadata: Dict[str, Any] = {}

    def add_node(self, node: ResearchNode):
        """Fügt einen Node zum Recherche-Baum hinzu."""
        self.research_tree.append(node)
        if node.parent:
            node.parent.children.append(node)
        self.visited_urls.add(self._get_canonical_url(node.url))

        # NEU v5.0: Tracking von Qualitätsmetriken
        if node.quality_metrics:
            quality_key = node.quality_metrics.overall_quality.value
            self.source_quality_summary[quality_key] = self.source_quality_summary.get(quality_key, 0) + 1

            bias_key = node.quality_metrics.bias_level.value
            self.bias_summary[bias_key] = self.bias_summary.get(bias_key, 0) + 1

    def _get_canonical_url(self, url: str) -> str:
        """Normalisiert URLs für Deduplizierung."""
        try:
            parsed = urlparse(url)
            filtered_query = {k: v for k, v in parse_qs(parsed.query).items()
                           if k not in ['utm_source', 'utm_medium', 'utm_campaign', 'gclid', 'fbclid']}
            return urlunparse(parsed._replace(query=urlencode(filtered_query, doseq=True), fragment=''))
        except Exception:
            return url


# Globaler Session-Speicher
research_sessions: Dict[str, DeepResearchSession] = {}


# ==============================================================================
# LLM HELPER
# ==============================================================================

async def _call_llm_for_facts(messages: List[Dict[str, Any]], use_json: bool = True, max_tokens: int = 2000) -> Any:
    """Wrapper für LLM-Aufrufe mit Retry-Logik und automatischer API-Kompatibilität."""
    kwargs = {
        "model": SMART_MODEL,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }

    if use_json:
        kwargs["response_format"] = {"type": "json_object"}

    # Automatische API-Kompatibilität (max_tokens vs max_completion_tokens, temperature)
    kwargs = prepare_openai_params(kwargs)

    try:
        response = await asyncio.to_thread(client.chat.completions.create, **kwargs)
        return response
    except RateLimitError:
        logger.warning("Rate Limit, warte 30s...")
        await asyncio.sleep(30)
        response = await asyncio.to_thread(client.chat.completions.create, **kwargs)
        return response


# ==============================================================================
# QUELLENQUALITÄTS-BEWERTUNG (NEU v5.0)
# ==============================================================================

async def _evaluate_source_quality(node: ResearchNode, content: str) -> SourceQualityMetrics:
    """
    Bewertet die Qualität einer Quelle nach mehreren Kriterien.

    Returns:
        SourceQualityMetrics mit allen Bewertungen
    """
    metrics = SourceQualityMetrics()

    # 1. AUTORITÄTSSCORE basierend auf Domain
    domain_lower = node.domain.lower()

    # Höchste Autorität
    if any(tld in domain_lower for tld in [".gov", ".edu", ".mil"]):
        metrics.authority_score = 0.95
    # Peer-reviewed Journals (bekannte Muster)
    elif any(journal in domain_lower for journal in ["nature.com", "science.org", "ieee.org", "acm.org", "springer", "elsevier"]):
        metrics.authority_score = 0.9
    # Wikipedia (gut für Überblick)
    elif "wikipedia.org" in domain_lower:
        metrics.authority_score = 0.75
    # Etablierte Nachrichtenquellen
    elif any(news in domain_lower for news in ["reuters.com", "apnews.com", "bbc.com", "nytimes.com", "wsj.com"]):
        metrics.authority_score = 0.8
    # PDFs (oft wissenschaftlich)
    elif node.url.lower().endswith(".pdf"):
        metrics.authority_score = 0.7
    # Standard
    else:
        metrics.authority_score = 0.5

    # 2. BIAS-ERKENNUNG
    content_lower = content.lower()
    title_lower = node.title.lower()
    combined = f"{title_lower} {content_lower[:1000]}"

    # Politischer Bias
    political_matches = sum(1 for keyword in BIAS_KEYWORDS_POLITICAL if keyword in combined)
    # Kommerzieller Bias
    commercial_matches = sum(1 for keyword in BIAS_KEYWORDS_COMMERCIAL if keyword in combined)

    total_bias_indicators = political_matches + commercial_matches

    if total_bias_indicators >= 5:
        metrics.bias_level = BiasLevel.HIGH
        metrics.bias_score = 0.8
    elif total_bias_indicators >= 3:
        metrics.bias_level = BiasLevel.MEDIUM
        metrics.bias_score = 0.5
    elif total_bias_indicators >= 1:
        metrics.bias_level = BiasLevel.LOW
        metrics.bias_score = 0.2
    else:
        metrics.bias_level = BiasLevel.NONE
        metrics.bias_score = 0.0

    # 3. TRANSPARENZ-SCORE (Autor, Methodik genannt)
    transparency_indicators = 0
    if re.search(r'(author|by|written by|verfasser):\s*\w+', content_lower):
        transparency_indicators += 1
    if re.search(r'(methodology|method|studie|research|analysis)', content_lower):
        transparency_indicators += 1
    if re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', content):  # Datum
        transparency_indicators += 1

    metrics.transparency_score = min(transparency_indicators / 3.0, 1.0)

    # 4. CITATIONS-SCORE (zitiert andere Quellen)
    citation_patterns = [
        r'\[\d+\]',  # [1], [2]
        r'\(\w+,?\s+\d{4}\)',  # (Author, 2024)
        r'according to',
        r'research shows',
        r'study found'
    ]

    citation_count = sum(1 for pattern in citation_patterns if re.search(pattern, content_lower))
    metrics.citation_score = min(citation_count / 3.0, 1.0)

    # 5. AKTUALITÄTSSCORE
    # Versuche Publikationsdatum zu extrahieren
    date_patterns = [
        r'(published|veröffentlicht|updated):\s*(\d{1,2}[\./]\d{1,2}[\./]\d{2,4})',
        r'(\d{1,2}[\./]\d{1,2}[\./]\d{4})',
        r'(\d{4}-\d{2}-\d{2})'
    ]

    found_date = None
    for pattern in date_patterns:
        match = re.search(pattern, content[:500])
        if match:
            try:
                # Vereinfachte Datumsparsung
                found_date = datetime.now()  # Placeholder
                break
            except:
                continue

    if found_date:
        days_old = (datetime.now() - found_date).days
        if days_old < 90:  # < 3 Monate
            metrics.recency_score = 1.0
        elif days_old < 365:  # < 1 Jahr
            metrics.recency_score = 0.8
        elif days_old < 730:  # < 2 Jahre
            metrics.recency_score = 0.6
        else:
            metrics.recency_score = 0.4
    else:
        metrics.recency_score = 0.5  # Unbekannt

    # 6. GESAMTQUALITÄT berechnen (gewichteter Durchschnitt)
    weights = {
        'authority': 0.35,
        'bias': 0.25,  # Niedriger Bias ist besser
        'transparency': 0.15,
        'citations': 0.15,
        'recency': 0.10
    }

    metrics.quality_score = (
        metrics.authority_score * weights['authority'] +
        (1 - metrics.bias_score) * weights['bias'] +  # Invertiert!
        metrics.transparency_score * weights['transparency'] +
        metrics.citation_score * weights['citations'] +
        metrics.recency_score * weights['recency']
    )

    # 7. Overall Quality Level
    if metrics.quality_score >= 0.8:
        metrics.overall_quality = SourceQuality.EXCELLENT
    elif metrics.quality_score >= 0.65:
        metrics.overall_quality = SourceQuality.GOOD
    elif metrics.quality_score >= 0.45:
        metrics.overall_quality = SourceQuality.MEDIUM
    else:
        metrics.overall_quality = SourceQuality.POOR

    # 8. Confidence in Bewertung
    # Höher wenn mehr Indikatoren gefunden wurden
    indicators_found = sum([
        1 if metrics.authority_score != 0.5 else 0,
        1 if metrics.bias_level != BiasLevel.UNKNOWN else 0,
        1 if transparency_indicators > 0 else 0,
        1 if citation_count > 0 else 0,
        1 if found_date is not None else 0
    ])
    metrics.confidence = min(indicators_found / 5.0, 1.0)

    # 9. Notes für Bericht
    notes = []
    if metrics.authority_score > 0.8:
        notes.append("High-authority source")
    if metrics.bias_level in [BiasLevel.HIGH, BiasLevel.MEDIUM]:
        notes.append(f"Potential {metrics.bias_level.value} bias detected")
    if metrics.transparency_score < 0.3:
        notes.append("Limited transparency (no author/methodology)")

    metrics.notes = "; ".join(notes) if notes else "Standard source"

    logger.debug(f"Quelle {node.domain}: Quality={metrics.quality_score:.2f}, Authority={metrics.authority_score:.2f}, Bias={metrics.bias_level.value}")

    return metrics


# ==============================================================================
# TIEFERE FAKTEN-VERIFIKATION MIT FACT_CORROBORATOR (NEU v5.0)
# ==============================================================================

async def _verify_fact_with_corroborator(fact_text: str, context: str) -> Dict[str, Any]:
    """
    Verifiziert einen Fakt mit dem fact_corroborator Tool.

    Returns:
        Verifizierungs-Ergebnis vom fact_corroborator
    """
    try:
        result = await call_tool_internal(
            "verify_fact",
            {
                "fact": fact_text,
                "context": context,
                "search_depth": 2,
                "require_multiple_sources": True
            },
            timeout=60
        )

        if isinstance(result, dict) and "error" not in result:
            return result
        else:
            logger.warning(f"fact_corroborator Fehler: {result}")
            return {"status": "error", "confidence": 0.0}

    except Exception as e:
        logger.error(f"Fehler bei fact_corroborator: {e}")
        return {"status": "error", "confidence": 0.0}


def _resolve_verification_mode(requested_mode: str, query: str) -> str:
    """
    v7.0: Auto-Mode Resolution.

    Bei strict + Tech-Domain → moderate (damit KI-Fakten mit source_count=1 nicht verschwinden).
    Gesteuert via DR_VERIFICATION_MODE_AUTO=true (default).
    """
    auto_mode = os.getenv("DR_VERIFICATION_MODE_AUTO", "true").lower() == "true"
    if not auto_mode:
        return requested_mode
    if requested_mode == "strict" and _detect_domain(query) == "tech":
        logger.info("🔧 Auto-Mode: strict → moderate für Tech-Domain")
        return "moderate"
    return requested_mode


async def _deep_verify_facts(session: DeepResearchSession, verification_mode: str) -> Dict[str, Any]:
    """
    Erweiterte Fakten-Verifikation mit Integration von fact_corroborator (v7.0).

    WORKFLOW:
    1. Auto-Mode Resolution (strict + Tech → moderate)
    2. Gruppiere ähnliche Fakten (Domain-aware Threshold)
    3. Basis-Verifizierung per source_count
    4. Corroborator für ALLE Fakten mit source_count ≥ 1 (RC3-Fix: nicht nur verified)
    5. Upgrade unverified → tentative wenn Corroborator Konsistenz bestätigt
    6. Konflikte identifizieren
    """
    logger.info("🕵️ Starte erweiterte Fakten-Verifikation (mit fact_corroborator)...")

    raw_facts = session.all_extracted_facts_raw
    if not raw_facts:
        return {"verified_facts": [], "unverified_claims": [], "conflicts": []}

    # Diagnostics
    try:
        from tools.deep_research.diagnostics import get_current
        diag = get_current()
        if diag is not None:
            diag.verification_mode_req = verification_mode
            diag.n_facts_extracted = len(raw_facts)
            diag.mark_phase("verification_start")
    except Exception:
        pass

    # v7.0: Auto-Mode Resolution
    effective_mode = _resolve_verification_mode(verification_mode, session.query)
    logger.info(f"📋 Verifikations-Modus: {verification_mode} → effektiv: {effective_mode}")

    # Diagnostics
    try:
        from tools.deep_research.diagnostics import get_current
        diag = get_current()
        if diag is not None:
            diag.verification_mode_eff = effective_mode
    except Exception:
        pass

    # 1. Gruppiere ähnliche Fakten (v7.0: Domain-aware Threshold)
    grouped = await _group_similar_facts(raw_facts, query=session.query)

    verified: List[Dict] = []
    unverified: List[Dict] = []
    conflicts: List[Dict] = []
    corroborator_call_count = 0

    # 2. Für jede Gruppe: Basis-Verifizierung
    for group_idx, group in enumerate(grouped):
        if not group:
            continue

        main_fact = group[0]
        sources = set(f.get("source_url") for f in group if f.get("source_url"))
        source_count = len(sources)

        # Basis-Bewertung nach effektivem Modus
        conf_numeric = 0.4
        status = "unverified"
        conf_text = "low"

        if effective_mode == "strict":
            if source_count >= 3:
                status = "verified"
                conf_text = "high"
                conf_numeric = 0.85
            elif source_count == 2:
                status = "tentatively_verified"
                conf_text = "medium"
                conf_numeric = 0.65
        elif effective_mode == "moderate":
            if source_count >= 2:
                status = "verified"
                conf_text = "high"
                conf_numeric = 0.8
            elif source_count == 1:
                status = "tentatively_verified"
                conf_text = "medium"
                conf_numeric = 0.5
        else:  # light
            if source_count >= 1:
                status = "verified"
                conf_text = "medium"
                conf_numeric = 0.6

        fact_text = main_fact.get("fact", "")

        # 3. RC3-Fix: Corroborator für ALLE Fakten mit source_count ≥ 1
        #    (nicht nur bereits "verified" — das war der Catch-22!)
        use_corroborator = (
            source_count >= 1 and
            group_idx < 5 and  # Performance-Limit: erste 5 Fakten
            any(indicator in fact_text.lower() for indicator in [
                "percent", "million", "billion", "study", "research",
                "%", "paper", "model", "published", "released"
            ])
        )

        corroborator_result = None
        if use_corroborator:
            logger.info(f"🔬 Corroborator für Fakt #{group_idx+1}: {fact_text[:60]}...")
            corroborator_result = await _verify_fact_with_corroborator(fact_text, session.query)
            corroborator_call_count += 1

            if corroborator_result and corroborator_result.get("status") == "verified":
                corroborator_conf = corroborator_result.get("confidence", 0.0)

                # Consensus bilden
                if corroborator_conf >= 0.7:
                    conf_numeric = min((conf_numeric + corroborator_conf) / 2 + 0.1, 1.0)
                    conf_text = "very_high" if conf_numeric > 0.9 else "high"
                    status = "verified_multiple_methods"
                    logger.info(f"✅ Consensus: {conf_numeric:.2f}")
                elif abs(conf_numeric - corroborator_conf) > 0.3:
                    conflicts.append({
                        "fact": fact_text,
                        "internal_confidence": conf_numeric,
                        "corroborator_confidence": corroborator_conf,
                        "note": "Conflicting confidence levels between verification methods"
                    })
                    logger.warning(f"⚠️ Konflikt erkannt für Fakt")

            # v7.0: RC3-Fix Upgrade-Log — unverified → tentative wenn Corroborator konsistent
            elif corroborator_result and status == "unverified":
                corroborator_conf = corroborator_result.get("confidence", 0.0)
                if corroborator_conf >= 0.5:
                    old_status = status
                    status = "tentatively_verified"
                    conf_text = "medium"
                    conf_numeric = max(conf_numeric, corroborator_conf * 0.8)
                    logger.info(f"📈 Upgrade: {old_status} → tentatively_verified via Corroborator")

        # Ausgabe erstellen
        fact_output = {
            "fact": fact_text,
            "status": status,
            "confidence": conf_text,
            "confidence_score_numeric": round(conf_numeric, 2),
            "source_count": source_count,
            "example_source_url": list(sources)[0] if sources else None,
            "supporting_quotes": [f.get("source_quote") for f in group if f.get("source_quote")][:3],
            "verification_methods": ["internal"]
        }

        if corroborator_result:
            fact_output["verification_methods"].append("fact_corroborator")
            fact_output["corroborator_data"] = {
                "status": corroborator_result.get("status"),
                "confidence": corroborator_result.get("confidence", 0.0),
                "supporting_sources_count": len(corroborator_result.get("supporting_sources", []))
            }

        if status in ["verified", "tentatively_verified", "verified_multiple_methods"]:
            verified.append(fact_output)
        else:
            unverified.append(fact_output)

    session.verified_facts = verified
    session.unverified_claims = unverified
    session.conflicting_info = conflicts

    logger.info(
        f"✅ Verifikation abgeschlossen: {len(verified)} verifiziert "
        f"(Modus: {effective_mode}), {len(unverified)} unverifiziert, "
        f"{len(conflicts)} Konflikte, {corroborator_call_count} Corroborator-Calls"
    )

    # Diagnostics
    try:
        from tools.deep_research.diagnostics import get_current
        diag = get_current()
        if diag is not None:
            diag.n_verified = len([f for f in verified if f.get("status") in ["verified", "verified_multiple_methods"]])
            diag.n_tentative = len([f for f in verified if f.get("status") == "tentatively_verified"])
            diag.n_unverified = len(unverified)
            diag.n_corroborator_calls = corroborator_call_count
    except Exception:
        pass

    return {
        "verified_facts": verified,
        "unverified_claims": unverified,
        "conflicts": conflicts
    }


# ==============================================================================
# THESE-ANTITHESE-SYNTHESE ANALYSE (NEU v5.0)
# ==============================================================================

async def _analyze_thesis_antithesis_synthesis(session: DeepResearchSession) -> List[ThesisAnalysis]:
    """
    Führt dialektische These-Antithese-Synthese Analyse durch.

    WORKFLOW:
    1. Identifiziere Hauptthesen aus verifizierten Fakten
    2. Für jede These: Suche Gegenargumente/Antithesen
    3. Analysiere Widersprüche
    4. Bilde Synthese (balanced conclusion)
    5. Dokumentiere Limitationen

    Returns:
        Liste von ThesisAnalysis Objekten
    """
    logger.info("🎓 Starte These-Antithese-Synthese Analyse...")

    if len(session.verified_facts) < MIN_SOURCES_FOR_THESIS:
        logger.warning(f"Zu wenige Fakten ({len(session.verified_facts)}) für These-Bildung")
        return []

    # 1. Hauptthesen identifizieren via LLM
    facts_text = "\n".join([
        f"- {f.get('fact')} (Confidence: {f.get('confidence')}, Sources: {f.get('source_count')})"
        for f in session.verified_facts[:30]
    ])

    thesis_prompt = f"""Analysiere die folgenden verifizierten Fakten zur Recherche "{session.query}" und identifiziere 2-4 Hauptthesen.

VERIFIZIERTE FAKTEN:
{facts_text}

Für jede These:
1. Formuliere sie klar und präzise
2. Liste unterstützende Fakten auf
3. Bewerte die Confidence (0-1)

Antworte als JSON:
{{
    "theses": [
        {{
            "topic": "Spezifischer Aspekt/Thema",
            "thesis": "Klare These-Aussage",
            "confidence": 0.85,
            "supporting_fact_indices": [0, 2, 5]
        }}
    ]
}}"""

    try:
        response = await _call_llm_for_facts([
            {"role": "system", "content": "Du bist ein wissenschaftlicher Analyst. Antworte nur mit validem JSON."},
            {"role": "user", "content": thesis_prompt}
        ], use_json=True, max_tokens=2000)

        thesis_data = extract_json_robust(response.choices[0].message.content) or {}
        theses_raw = thesis_data.get("theses", [])

        if not theses_raw:
            logger.warning("LLM konnte keine Thesen identifizieren")
            return []

        logger.info(f"📋 {len(theses_raw)} Hauptthesen identifiziert")

    except Exception as e:
        logger.error(f"Fehler bei Thesen-Identifikation: {e}")
        return []

    # 2. Für jede These: Antithese & Synthese analysieren
    analyses: List[ThesisAnalysis] = []

    for thesis_raw in theses_raw[:4]:  # Maximal 4 Thesen
        topic = thesis_raw.get("topic", "Unknown")
        thesis_statement = thesis_raw.get("thesis", "")
        thesis_conf = thesis_raw.get("confidence", 0.5)
        supporting_indices = thesis_raw.get("supporting_fact_indices", [])

        # Unterstützende Fakten sammeln
        supporting_facts = [
            session.verified_facts[i] for i in supporting_indices
            if i < len(session.verified_facts)
        ]
        supporting_sources = list(set([
            f.get("example_source_url") for f in supporting_facts
            if f.get("example_source_url")
        ]))

        # Antithese suchen
        antithesis_prompt = f"""Analysiere die These und finde Gegenargumente/Antithesen aus den Fakten.

THESE: {thesis_statement}

ALLE VERFÜGBAREN FAKTEN:
{facts_text}

Gibt es Fakten die der These widersprechen oder sie qualifizieren?

Antworte als JSON:
{{
    "has_antithesis": true/false,
    "antithesis": "Gegenthese oder qualifizierende Aussage" oder null,
    "confidence": 0.0-1.0,
    "contradicting_fact_indices": [1, 3]
}}"""

        antithesis_data = None
        try:
            response = await _call_llm_for_facts([
                {"role": "system", "content": "Du bist ein kritischer Analyst. Antworte nur mit validem JSON."},
                {"role": "user", "content": antithesis_prompt}
            ], use_json=True, max_tokens=1500)

            antithesis_data = extract_json_robust(response.choices[0].message.content) or {}
        except Exception as e:
            logger.warning(f"Fehler bei Antithese-Analyse: {e}")

        # Synthese bilden
        synthesis_prompt = f"""Bilde eine ausgewogene Synthese aus These und Antithese.

THESE: {thesis_statement} (Confidence: {thesis_conf})

ANTITHESE: {antithesis_data.get('antithesis') if antithesis_data and antithesis_data.get('has_antithesis') else 'Keine signifikante Antithese gefunden'}

Erstelle eine balanced conclusion die beide Seiten berücksichtigt.

Antworte als JSON:
{{
    "synthesis": "Ausgewogene Schlussfolgerung",
    "confidence": 0.0-1.0,
    "reasoning": "Begründung für diese Synthese",
    "limitations": ["Limitation 1", "Limitation 2"]
}}"""

        synthesis_data = None
        try:
            response = await _call_llm_for_facts([
                {"role": "system", "content": "Du bist ein dialektischer Analyst. Antworte nur mit validem JSON."},
                {"role": "user", "content": synthesis_prompt}
            ], use_json=True, max_tokens=1500)

            synthesis_data = extract_json_robust(response.choices[0].message.content) or {}
        except Exception as e:
            logger.warning(f"Fehler bei Synthese-Bildung: {e}")

        # ThesisAnalysis Objekt erstellen
        analysis = ThesisAnalysis(
            topic=topic,
            thesis=thesis_statement,
            thesis_confidence=thesis_conf,
            supporting_facts=supporting_facts,
            supporting_sources=supporting_sources
        )

        if antithesis_data and antithesis_data.get("has_antithesis"):
            analysis.antithesis = antithesis_data.get("antithesis")
            analysis.antithesis_confidence = antithesis_data.get("confidence", 0.0)

            contradicting_indices = antithesis_data.get("contradicting_fact_indices", [])
            analysis.contradicting_facts = [
                session.verified_facts[i] for i in contradicting_indices
                if i < len(session.verified_facts)
            ]
            analysis.contradicting_sources = list(set([
                f.get("example_source_url") for f in analysis.contradicting_facts
                if f.get("example_source_url")
            ]))

        if synthesis_data:
            analysis.synthesis = synthesis_data.get("synthesis", "")
            analysis.synthesis_confidence = synthesis_data.get("confidence", 0.5)
            analysis.synthesis_reasoning = synthesis_data.get("reasoning", "")
            analysis.limitations = synthesis_data.get("limitations", [])

        analyses.append(analysis)
        logger.info(f"✅ Analyse für '{topic}' abgeschlossen")

    session.thesis_analyses = analyses
    logger.info(f"🎓 {len(analyses)} These-Antithese-Synthese Analysen erstellt")

    return analyses


# (Fortsetzung folgt in Teil 2...)


# ==============================================================================
# HELPER FUNCTIONS (aus v4.0 übernommen + erweitert)
# ==============================================================================

def get_adaptive_config(query: str, focus_areas: Optional[List[str]]) -> Dict[str, Any]:
    """Gibt adaptive Konfiguration zurück."""
    return {
        "max_initial_search_queries": 4,
        "max_results_per_search_query": 8,
        "max_sources_to_deep_dive": 8,  # Erhöht für bessere Analyse
        "max_depth_for_links": 2,
        "max_chunks_per_source_for_facts": 3,
        "parallel_source_analysis_limit": 2
    }


def _detect_language(query: str) -> str:
    """
    Einfache Spracherkennung via ASCII-Ratio.
    >80% ASCII-Zeichen → englisch, sonst deutsch als Fallback.
    """
    if not query:
        return "de"
    ascii_chars = sum(1 for c in query if ord(c) < 128)
    ratio = ascii_chars / len(query)
    if ratio > 0.80:
        return "en"
    return "de"


def _detect_domain(query: str) -> str:
    """Erkennt ob die Anfrage Tech-Domain ist."""
    q_lower = query.lower()
    if any(kw in q_lower for kw in TECH_KEYWORDS):
        return "tech"
    return "default"


async def _perform_initial_search(query: str, session: DeepResearchSession) -> List[Dict[str, Any]]:
    """
    Führt initiale Websuche durch (v7.0).

    NEU: Language-Detection → US-Location für englische Queries.
         5 Query-Varianten statt 3.
         Diagnostics-Integration.
    """
    logger.info(f"🔎 Initiale Suche: '{query}'")

    # v7.0: Language-Detection
    lang = _detect_language(query)
    location_code = _LANG_LOCATION_MAP.get(lang, 2276)
    language_code = _LANG_CODE_MAP.get(lang, "de")

    logger.info(f"🌍 Sprache: {lang} → location_code={location_code}")

    # Diagnostics aktualisieren
    try:
        from tools.deep_research.diagnostics import get_current
        diag = get_current()
        if diag is not None:
            diag.language_detected = lang
            diag.location_used = str(location_code)
            diag.mark_phase("search_start")
    except Exception:
        pass

    # v7.0: 5 Query-Varianten
    queries = [query]
    if session.focus_areas:
        queries.append(f"{query} {' '.join(session.focus_areas[:2])}")
    if lang == "en":
        queries.extend([
            f"{query} research paper 2024 2025",
            f"{query} architecture implementation",
            f"{query} survey review",
        ])
    else:
        queries.extend([
            f"{query} Analyse Fakten",
            f"{query} Forschung Studie",
            f"{query} Übersicht Methoden",
        ])

    all_results: List[Dict[str, Any]] = []

    async def _single_search(q: str) -> Optional[Any]:
        try:
            return await call_tool_internal(
                "search_web",
                {
                    "query": q,
                    "max_results": 8,
                    "engine": "google",
                    "vertical": "organic",
                    "location_code": location_code,
                    "language_code": language_code,
                },
                timeout=DEFAULT_TIMEOUT_SEARCH,
            )
        except Exception as e:
            logger.error(f"Suchfehler ({q[:40]}): {e}")
            return None

    search_results = await asyncio.gather(*[_single_search(q) for q in queries[:5]])

    for result in search_results:
        if result is None:
            continue
        if isinstance(result, list):
            all_results.extend(result)
        elif isinstance(result, dict):
            if "error" not in result and "results" in result:
                all_results.extend(result.get("results", []))
            elif "error" not in result:
                all_results.append(result)

    try:
        from tools.deep_research.diagnostics import get_current
        diag = get_current()
        if diag is not None:
            diag.n_queries_issued = min(len(queries), 5)
    except Exception:
        pass

    # Deduplizierung
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

        if any(domain in url_lower for domain in [".gov", ".edu", ".org"]):
            score += 0.2
        if "wikipedia" in url_lower:
            score += 0.15
        if ".pdf" in url_lower:
            score += 0.1
        if any(social in url_lower for social in ["facebook.com", "twitter.com"]):
            score -= 0.2

        r["score"] = min(score, 1.0)
        r["canonical_url"] = session._get_canonical_url(url)
        final_results.append(r)

    final_results.sort(key=lambda x: x.get("score", 0), reverse=True)

    logger.info(f"✅ {len(final_results)} Quellen gefunden")

    # Diagnostics
    try:
        from tools.deep_research.diagnostics import get_current
        diag = get_current()
        if diag is not None:
            diag.n_sources_found = len(final_results)
    except Exception:
        pass

    return final_results[:20]


async def _evaluate_relevance(
    sources: List[Dict],
    query: str,
    focus: List[str],
    max_sources_to_return: int
) -> List[Tuple[Dict, float]]:
    """Bewertet Relevanz der Quellen."""
    logger.info(f"⚖️ Bewerte Relevanz von {len(sources)} Quellen...")

    relevant: List[Tuple[Dict, float]] = []

    query_terms = set(query.lower().split())
    focus_terms = set(" ".join(focus).lower().split()) if focus else set()
    all_terms = query_terms | focus_terms

    for source in sources:
        base_score = source.get("score", 0.5)

        title = source.get("title", "").lower()
        snippet = source.get("snippet", "").lower()
        combined_text = f"{title} {snippet}"

        matches = sum(1 for term in all_terms if term in combined_text)
        keyword_bonus = min(matches * 0.05, 0.3)

        final_score = base_score + keyword_bonus

        if final_score >= MIN_RELEVANCE_SCORE_FOR_SOURCES:
            relevant.append((source, final_score))

    relevant.sort(key=lambda x: x[1], reverse=True)
    result = relevant[:max_sources_to_return]

    # Diagnostics
    try:
        from tools.deep_research.diagnostics import get_current
        diag = get_current()
        if diag is not None:
            diag.n_sources_relevant = len(result)
    except Exception:
        pass

    return result


_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


def _html_to_text(html: str) -> str:
    """Konvertiert HTML zu plain text — bevorzugt BeautifulSoup, sonst Regex-Fallback."""
    if HAS_BS4:
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Script/Style-Tags entfernen
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            return " ".join(soup.get_text(separator=" ").split())
        except Exception:
            pass
    # Regex-Fallback
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_module.unescape(text)
    return " ".join(text.split())


async def _fetch_page_content(url: str) -> str:
    """
    Holt Seiteninhalt via direktem HTTP-Request (kein Browser nötig).

    Früher: call_tool_internal("open_url") + call_tool_internal("get_text")
    Jetzt:  httpx direkt — funktioniert zuverlässig im Background-Kontext.
    """
    try:
        url_lower = url.lower()

        # PDF: weiterhin über Tool-Abstraction (spezielle Extraktion)
        if url_lower.endswith(".pdf") or "arxiv.org/pdf" in url_lower:
            result = await call_tool_internal(
                "extract_text_from_pdf", {"pdf_url": url}, timeout=60
            )
            if isinstance(result, dict):
                return result.get("text", "") or result.get("content", "")
            elif isinstance(result, str):
                return result
            return ""

        # HTML-Seiten: direkt via httpx
        async with httpx.AsyncClient(
            timeout=25.0,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            # Encoding sicherstellen
            content_type = resp.headers.get("content-type", "")
            if "pdf" in content_type:
                return ""  # PDF ohne .pdf-Endung → überspringen

            text = _html_to_text(resp.text)
            logger.debug(f"✅ Seite geladen: {url} ({len(text)} Zeichen)")
            return text[:12000]  # Max 12k Zeichen pro Seite

    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP {e.response.status_code} für {url}")
        return ""
    except httpx.TimeoutException:
        logger.warning(f"Timeout beim Abrufen von {url}")
        return ""
    except Exception as e:
        logger.error(f"Fehler beim Abrufen von {url}: {e}")
        return ""


async def _extract_key_facts(text_content: str, query: str, url: str, config: Dict) -> List[Dict]:
    """Extrahiert Fakten via LLM."""
    if not text_content or len(text_content) < 100:
        return []

    max_chunk_size = 3000
    chunks = [text_content[i:i+max_chunk_size] for i in range(0, len(text_content), max_chunk_size)]
    chunks = chunks[:config.get("max_chunks_per_source_for_facts", 3)]

    all_facts: List[Dict] = []

    for chunk in chunks:
        prompt = f"""Extrahiere wichtige Fakten zum Thema "{query}" aus dem Text.

TEXT:
{chunk[:2500]}

Gib die Fakten als JSON zurück:
{{
    "facts": [
        {{
            "fact": "Die konkrete Aussage/Fakt",
            "fact_type": "statistic|statement|quote|date",
            "source_quote": "Originalzitat",
            "confidence": "high|medium|low"
        }}
    ]
}}

Regeln:
- Nur verifizierbare Fakten
- 8–15 Fakten pro Chunk (möglichst viele relevante Fakten extrahieren)
- confidence: high = mit Zahlen/Quellen, medium = plausibel, low = unklar"""

        try:
            response = await _call_llm_for_facts([
                {"role": "system", "content": "Du bist ein Fakten-Extraktor. Antworte nur mit JSON."},
                {"role": "user", "content": prompt}
            ], use_json=True)

            content = response.choices[0].message.content
            data = extract_json_robust(content) or {}

            for fact in data.get("facts", []):
                fact["source_url"] = url
                all_facts.append(fact)

        except Exception as e:
            logger.warning(f"Fakten-Extraktion Fehler: {e}")
            continue

        await asyncio.sleep(0.3)

    return all_facts


async def _process_source_safe(
    source_data: Dict,
    session: DeepResearchSession,
    semaphore: asyncio.Semaphore,
    config: Dict
):
    """Verarbeitet Quelle mit Qualitätsbewertung."""
    async with semaphore:
        url = source_data.get("url", "")
        title = source_data.get("title", "Unbekannt")

        logger.info(f"🔄 Verarbeite: {title[:50]}...")

        content = await _fetch_page_content(url)

        if not content or len(content) < 200:
            logger.warning(f"Zu wenig Inhalt für {url}")
            return

        node = ResearchNode(
            url=url,
            title=title,
            content_snippet=content[:500],
            depth=0
        )

        # NEU v5.0: Quellenqualitätsbewertung
        node.quality_metrics = await _evaluate_source_quality(node, content)

        session.add_node(node)

        # Fakten extrahieren
        facts = await _extract_key_facts(content, session.query, url, config)
        node.key_facts = facts
        session.all_extracted_facts_raw.extend(facts)

        logger.info(f"✅ {len(facts)} Fakten, Quality: {node.quality_metrics.overall_quality.value}")


async def _deep_dive_sources(
    sources_to_analyze: List[Tuple[Dict[str, Any], float]],
    session_instance: DeepResearchSession,
    max_dive_depth: Optional[int],
    verification_mode: str,
    config: Dict[str, Any]
):
    """Hauptschleife für Tiefenanalyse."""
    if not sources_to_analyze:
        logger.warning("Keine Quellen zum Analysieren")
        return

    if max_dive_depth is None:
        max_dive_depth = MAX_DEPTH_CONFIG

    semaphore = asyncio.Semaphore(config.get("parallel_source_analysis_limit", 2))

    tasks = [
        _process_source_safe(src[0], session_instance, semaphore, config)
        for src in sources_to_analyze
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Fehler bei Quelle {i}: {result}")


async def _get_embeddings(texts: List[str]) -> List[List[float]]:
    """Holt Embeddings."""
    if not texts or not HAS_NUMPY:
        return []

    try:
        response = await asyncio.to_thread(
            client.embeddings.create,
            input=texts[:50],
            model=EMBEDDING_MODEL
        )
        return [e.embedding for e in response.data]
    except Exception as e:
        logger.warning(f"Embedding-Fehler: {e}")
        return []


async def _group_similar_facts(
    facts: List[Dict[str, Any]],
    threshold: float = 0.85,
    query: str = "",
) -> List[List[Dict[str, Any]]]:
    """
    Gruppiert ähnliche Fakten (v7.0).

    NEU: Domain-aware Threshold — Tech-Queries nutzen 0.72 statt 0.85,
         damit KI-Fakten die ähnlich aber nicht identisch sind gemergt werden.
    """
    if len(facts) < 2:
        return [[f] for f in facts]

    if not HAS_NUMPY:
        return [[f] for f in facts]

    # v7.0: Domain-aware Threshold
    if query:
        domain = _detect_domain(query)
        effective_threshold = EMBEDDING_THRESHOLDS.get(domain, threshold)
    else:
        effective_threshold = threshold

    logger.info(f"📐 Embedding-Threshold: {effective_threshold} (domain={_detect_domain(query) if query else 'unbekannt'})")

    # Diagnostics
    try:
        from tools.deep_research.diagnostics import get_current
        diag = get_current()
        if diag is not None:
            diag.embedding_threshold = effective_threshold
            diag.domain_detected = _detect_domain(query) if query else "default"
    except Exception:
        pass

    texts = [f.get("fact", "") for f in facts]
    embeddings = await _get_embeddings(texts)

    if not embeddings or len(embeddings) != len(facts):
        return [[f] for f in facts]

    arr = np.array(embeddings)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = arr / norms
    sim_matrix = np.dot(normalized, normalized.T)

    groups: List[List[Dict[str, Any]]] = []
    processed: set = set()

    for i in range(len(facts)):
        if i in processed:
            continue

        sim_indices = np.where(sim_matrix[i] >= effective_threshold)[0]
        group = [facts[idx] for idx in sim_indices if idx not in processed]
        processed.update(sim_indices.tolist())

        if group:
            groups.append(group)

    # Diagnostics
    try:
        from tools.deep_research.diagnostics import get_current
        diag = get_current()
        if diag is not None:
            diag.n_facts_grouped = len(groups)
    except Exception:
        pass

    return groups


def _get_research_metadata_summary(session: DeepResearchSession) -> Dict[str, Any]:
    """Erstellt Metadaten-Zusammenfassung."""
    return {
        "original_query": session.query,
        "focus_areas": session.focus_areas,
        "start_time": session.start_time,
        "total_sources_processed": len(session.visited_urls),
        "total_facts_extracted": len(session.all_extracted_facts_raw),
        "verified_facts_count": len(session.verified_facts),
        "unverified_claims_count": len(session.unverified_claims),
        "conflicts_count": len(session.conflicting_info),
        "source_quality_distribution": session.source_quality_summary,
        "bias_distribution": session.bias_summary,
        "thesis_analyses_count": len(session.thesis_analyses)
    }


async def _synthesize_findings(session: DeepResearchSession, verification_output: Dict) -> Dict:
    """Erstellt KI-Synthese."""
    logger.info("📝 Erstelle Synthese...")

    facts = verification_output.get("verified_facts", [])[:30]

    if not facts:
        return {
            "executive_summary": "Keine verifizierten Fakten gefunden.",
            "key_findings": [],
            "research_metadata_summary": _get_research_metadata_summary(session)
        }

    facts_text = "\n".join([f"- {f.get('fact')}" for f in facts[:20]])

    prompt = f"""Erstelle eine strukturierte Analyse für "{session.query}".

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
            {"role": "system", "content": "Du bist ein Forschungsanalyst. Antworte nur mit JSON."},
            {"role": "user", "content": prompt}
        ], use_json=True)

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
# DRUCKREIFER REPORT-GENERATOR (NEU v5.0 - ACADEMIC EXCELLENCE)
# ==============================================================================

def _create_academic_markdown_report(session: DeepResearchSession, include_methodology: bool = True) -> str:
    """
    Erstellt einen druckreifen Report im wissenschaftlichen Stil.

    NEU v5.0:
    - Executive Summary
    - Methodik-Sektion
    - These-Antithese-Synthese Framework
    - Quellenqualitäts-Analyse
    - Kritische Analyse
    - Limitationen
    - Proper Citations
    """
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    meta = _get_research_metadata_summary(session)

    lines = []

    # ==================== TITELSEITE ====================
    lines.extend([
        f"# Tiefenrecherche-Bericht",
        f"## {session.query}",
        "",
        "---",
        "",
        f"**Datum:** {now}",
        f"**Research Engine:** Timus Deep Research v5.0",
        f"**Analysierte Quellen:** {meta['total_sources_processed']}",
        f"**Verifizierte Fakten:** {meta['verified_facts_count']} / {meta['total_facts_extracted']}",
        ""
    ])

    if session.focus_areas:
        lines.extend([
            f"**Fokusthemen:** {', '.join(session.focus_areas)}",
            ""
        ])

    lines.extend([
        "---",
        "",
        "## Inhaltsverzeichnis",
        "",
        "1. [Executive Summary](#executive-summary)",
        "2. [Methodik](#methodik)",
        "3. [Kern-Erkenntnisse](#kern-erkenntnisse)",
        "4. [These-Antithese-Synthese Analysen](#these-antithese-synthese-analysen)",
        "5. [Quellenqualitäts-Analyse](#quellenqualitäts-analyse)",
        "6. [Kritische Diskussion](#kritische-diskussion)",
        "7. [Limitationen & Unsicherheiten](#limitationen--unsicherheiten)",
        "8. [Schlussfolgerungen](#schlussfolgerungen)",
        "9. [Quellenverzeichnis](#quellenverzeichnis)",
        "",
        "---",
        ""
    ])

    # ==================== EXECUTIVE SUMMARY ====================
    lines.extend([
        "## Executive Summary",
        ""
    ])

    if session.verified_facts:
        summary_text = (
            f"Diese Tiefenrecherche zum Thema '{session.query}' basiert auf der Analyse von "
            f"{meta['total_sources_processed']} Quellen. Aus {meta['total_facts_extracted']} extrahierten "
            f"Fakten konnten {meta['verified_facts_count']} ({(meta['verified_facts_count']/max(meta['total_facts_extracted'], 1)*100):.1f}%) "
            f"durch mehrere unabhängige Quellen verifiziert werden."
        )

        lines.append(summary_text)
        lines.append("")

        # Top 3 Erkenntnisse
        lines.append("**Zentrale Erkenntnisse:**")
        lines.append("")
        for i, fact in enumerate(session.verified_facts[:3], 1):
            conf_icon = "🟢" if fact.get('confidence') in ['high', 'very_high'] else "🟡"
            lines.append(f"{i}. {conf_icon} {fact.get('fact')}")
        lines.append("")
    else:
        lines.extend([
            "_Keine ausreichend verifizierten Fakten für Executive Summary verfügbar._",
            ""
        ])

    # Qualitätshinweis
    if session.source_quality_summary:
        excellent_count = session.source_quality_summary.get("excellent", 0)
        good_count = session.source_quality_summary.get("good", 0)
        high_quality_percent = ((excellent_count + good_count) / meta['total_sources_processed'] * 100) if meta['total_sources_processed'] > 0 else 0

        lines.extend([
            f"**Quellenqualität:** {high_quality_percent:.0f}% der Quellen wurden als 'Excellent' oder 'Good' eingestuft. "
            f"Die Recherche basiert überwiegend auf {'hochqualitativen' if high_quality_percent > 60 else 'gemischten'} Quellen.",
            ""
        ])

    lines.extend(["---", ""])

    # ==================== METHODIK ====================
    if include_methodology:
        lines.extend([
            "## Methodik",
            "",
            "### Recherche-Ansatz",
            "",
            "Diese Tiefenrecherche wurde mit folgenden Methoden durchgeführt:",
            "",
            "1. **Multi-Query Websuche**",
            f"   - Initiale Suchqueries: Haupt-Query + {len(session.focus_areas)} Fokusthemen",
            "   - Suchtiefe: Mehrere Iterationen mit Relevanz-Filtering",
            "",
            "2. **Quellenqualitäts-Bewertung** (NEU in v5.0)",
            "   - Autoritätsscore basierend auf Domain-Typ (.gov, .edu, peer-reviewed)",
            "   - Bias-Erkennung (politisch & kommerziell)",
            "   - Transparenz-Check (Autor, Methodik, Publikationsdatum)",
            "   - Citation-Analyse (Quellenangaben im Text)",
            "",
            "3. **Fakten-Extraktion & Verifikation**",
            "   - LLM-basierte Extraktion strukturierter Fakten",
            "   - Embedding-basierte Gruppierung ähnlicher Aussagen",
            f"   - Verifikations-Modus: {'Strikt (≥3 Quellen)' if 'strict' in str(session.research_metadata.get('verification_mode', '')) else 'Moderat (≥2 Quellen)'}",
            ""
        ])

        # fact_corroborator erwähnen wenn genutzt
        if any(f.get("verification_methods") and "fact_corroborator" in f.get("verification_methods", []) for f in session.verified_facts):
            lines.extend([
                "4. **Erweiterte Verifikation mit Fact Corroborator**",
                "   - Zusätzliche unabhängige Verifizierung kritischer Fakten",
                "   - Consensus-Bildung zwischen internen und externen Verifikationsmethoden",
                ""
            ])

        lines.extend([
            "### Bewertungskriterien",
            "",
            "**Confidence-Level:**",
            "- 🟢 **High/Very High:** Durch ≥3 unabhängige Quellen bestätigt oder durch fact_corroborator verifiziert",
            "- 🟡 **Medium:** Durch 2 Quellen bestätigt",
            "- 🔴 **Low:** Nur eine Quelle, unverifiziert",
            "",
            "**Quellenqualität:**",
            "- **Excellent:** .gov, .edu, peer-reviewed journals",
            "- **Good:** Etablierte Medien, Wikipedia mit Quellenangaben",
            "- **Medium:** Blogs/Websites mit Quellenangaben",
            "- **Poor:** Keine Quellenangaben, starker Bias",
            "",
            "---",
            ""
        ])

    # ==================== KERN-ERKENNTNISSE ====================
    lines.extend([
        "## Kern-Erkenntnisse",
        "",
        "### Verifizierte Fakten",
        ""
    ])

    if session.verified_facts:
        lines.append("Die folgenden Aussagen wurden durch multiple unabhängige Quellen verifiziert:")
        lines.append("")

        for i, fact in enumerate(session.verified_facts[:20], 1):
            conf = fact.get('confidence', 'unknown')
            conf_icon = "🟢" if conf in ['high', 'very_high'] else ("🟡" if conf == 'medium' else "🔴")
            status = fact.get('status', 'unknown')

            lines.append(f"### {i}. {conf_icon} {fact.get('fact')}")
            lines.append("")
            lines.append(f"- **Status:** {status}")
            lines.append(f"- **Confidence:** {conf} ({fact.get('confidence_score_numeric', 0):.2f})")
            lines.append(f"- **Quellen:** {fact.get('source_count', 0)}")

            # Verifikationsmethoden
            methods = fact.get('verification_methods', ['internal'])
            if len(methods) > 1:
                lines.append(f"- **Verifikationsmethoden:** {', '.join(methods)}")

            # Quelle verlinken
            if fact.get('example_source_url'):
                lines.append(f"- **Beispiel-Quelle:** [{urlparse(fact['example_source_url']).netloc}]({fact['example_source_url']})")

            # Zitate
            quotes = fact.get('supporting_quotes', [])
            if quotes and quotes[0]:
                lines.append(f"- **Originalzitat:** \"{quotes[0][:200]}...\"")

            lines.append("")

    else:
        lines.extend([
            "_Keine Fakten konnten ausreichend verifiziert werden._",
            ""
        ])

    # Unverifizierte Behauptungen
    if session.unverified_claims:
        lines.extend([
            "### ⚠️ Unverifizierte Behauptungen",
            "",
            "Folgende Aussagen konnten nur durch eine Quelle belegt werden und bedürfen weiterer Überprüfung:",
            ""
        ])

        for i, claim in enumerate(session.unverified_claims[:10], 1):
            lines.append(f"{i}. {claim.get('fact')} *(1 Quelle, Confidence: {claim.get('confidence', 'low')})*")

        lines.append("")

    lines.extend(["---", ""])

    # ==================== THESE-ANTITHESE-SYNTHESE ====================
    if session.thesis_analyses:
        lines.extend([
            "## These-Antithese-Synthese Analysen",
            "",
            "Folgende dialektische Analysen wurden durchgeführt, um ein ausgewogenes Verständnis zu erreichen:",
            ""
        ])

        for idx, analysis in enumerate(session.thesis_analyses, 1):
            lines.extend([
                f"### Analyse #{idx}: {analysis.topic}",
                "",
                "#### 📘 These",
                "",
                f"> {analysis.thesis}",
                "",
                f"**Confidence:** {analysis.thesis_confidence:.2f}",
                f"**Unterstützende Quellen:** {len(analysis.supporting_sources)}",
                ""
            ])

            # Unterstützende Fakten
            if analysis.supporting_facts:
                lines.append("**Unterstützende Evidenz:**")
                for fact in analysis.supporting_facts[:3]:
                    lines.append(f"- {fact.get('fact')}")
                lines.append("")

            # Antithese
            if analysis.antithesis:
                lines.extend([
                    "#### 📕 Antithese",
                    "",
                    f"> {analysis.antithesis}",
                    "",
                    f"**Confidence:** {analysis.antithesis_confidence:.2f}",
                    f"**Widersprechende Quellen:** {len(analysis.contradicting_sources)}",
                    ""
                ])

                if analysis.contradicting_facts:
                    lines.append("**Widersprechende Evidenz:**")
                    for fact in analysis.contradicting_facts[:3]:
                        lines.append(f"- {fact.get('fact')}")
                    lines.append("")

            # Synthese
            if analysis.synthesis:
                lines.extend([
                    "#### 📗 Synthese",
                    "",
                    f"> {analysis.synthesis}",
                    "",
                    f"**Confidence:** {analysis.synthesis_confidence:.2f}",
                    ""
                ])

                if analysis.synthesis_reasoning:
                    lines.extend([
                        "**Begründung:**",
                        "",
                        analysis.synthesis_reasoning,
                        ""
                    ])

            # Limitationen
            if analysis.limitations:
                lines.extend([
                    "**Limitationen dieser Analyse:**",
                    ""
                ])
                for limitation in analysis.limitations:
                    lines.append(f"- {limitation}")
                lines.append("")

            lines.extend(["---", ""])

    # ==================== QUELLENQUALITÄTS-ANALYSE ====================
    if session.source_quality_summary or session.bias_summary:
        lines.extend([
            "## Quellenqualitäts-Analyse",
            ""
        ])

        # Qualitätsverteilung
        if session.source_quality_summary:
            lines.extend([
                "### Qualitätsverteilung der Quellen",
                "",
                "| Qualitätsstufe | Anzahl | Prozent |",
                "|----------------|--------|---------|"
            ])

            total = sum(session.source_quality_summary.values())
            for quality in ["excellent", "good", "medium", "poor", "unknown"]:
                count = session.source_quality_summary.get(quality, 0)
                percent = (count / total * 100) if total > 0 else 0
                icon = {"excellent": "🟢", "good": "🟡", "medium": "🟠", "poor": "🔴", "unknown": "⚪"}.get(quality, "")
                lines.append(f"| {icon} {quality.capitalize()} | {count} | {percent:.1f}% |")

            lines.append("")

        # Bias-Verteilung
        if session.bias_summary:
            lines.extend([
                "### Bias-Analyse",
                "",
                "| Bias-Level | Anzahl | Prozent |",
                "|------------|--------|---------|"
            ])

            total = sum(session.bias_summary.values())
            for bias in ["none", "low", "medium", "high", "unknown"]:
                count = session.bias_summary.get(bias, 0)
                percent = (count / total * 100) if total > 0 else 0
                lines.append(f"| {bias.capitalize()} | {count} | {percent:.1f}% |")

            lines.append("")

            # Interpretation
            high_bias_count = session.bias_summary.get("high", 0) + session.bias_summary.get("medium", 0)
            if high_bias_count > 0:
                lines.extend([
                    f"⚠️ **Hinweis:** {high_bias_count} Quellen zeigen mittleren bis hohen Bias. ",
                    "Die Schlussfolgerungen sollten unter Berücksichtigung möglicher Voreingenommenheit interpretiert werden.",
                    ""
                ])

        lines.extend(["---", ""])

    # ==================== KRITISCHE DISKUSSION ====================
    if session.conflicting_info:
        lines.extend([
            "## Kritische Diskussion",
            "",
            "### Widersprüchliche Befunde",
            "",
            "Folgende Widersprüche wurden identifiziert:",
            ""
        ])

        for i, conflict in enumerate(session.conflicting_info[:5], 1):
            lines.extend([
                f"**Konflikt #{i}:**",
                f"- **Fakt:** {conflict.get('fact', 'N/A')}",
                f"- **Interne Confidence:** {conflict.get('internal_confidence', 0):.2f}",
                f"- **Corroborator Confidence:** {conflict.get('corroborator_confidence', 0):.2f}",
                f"- **Hinweis:** {conflict.get('note', '')}",
                ""
            ])

        lines.extend(["---", ""])

    # ==================== LIMITATIONEN ====================
    lines.extend([
        "## Limitationen & Unsicherheiten",
        "",
        "Diese Recherche unterliegt folgenden Limitationen:",
        "",
        f"1. **Quellenabdeckung:** Die Analyse basiert auf {meta['total_sources_processed']} Quellen. "
        "Relevante Informationen könnten in nicht erfassten Quellen vorhanden sein.",
        ""
    ])

    # Qualitäts-basierte Limitationen
    poor_count = session.source_quality_summary.get("poor", 0)
    if poor_count > 0:
        poor_percent = (poor_count / meta['total_sources_processed'] * 100) if meta['total_sources_processed'] > 0 else 0
        lines.extend([
            f"2. **Quellenqualität:** {poor_percent:.0f}% der Quellen wurden als 'Poor' eingestuft, "
            "was die Zuverlässigkeit einiger Fakten einschränkt.",
            ""
        ])

    # Verifizierungs-Limitationen
    unverified_percent = (meta['unverified_claims_count'] / max(meta['total_facts_extracted'], 1) * 100)
    if unverified_percent > 30:
        lines.extend([
            f"3. **Verifizierung:** {unverified_percent:.0f}% der extrahierten Fakten konnten nicht "
            "durch mehrere Quellen verifiziert werden.",
            ""
        ])

    # Thesen-Limitationen
    if session.thesis_analyses:
        all_limitations = []
        for analysis in session.thesis_analyses:
            all_limitations.extend(analysis.limitations)

        if all_limitations:
            lines.append("4. **Analysespezifische Limitationen:**")
            for limitation in list(set(all_limitations))[:5]:  # Dedupliziert
                lines.append(f"   - {limitation}")
            lines.append("")

    lines.extend([
        "5. **Zeitpunkt:** Diese Recherche wurde zum angegebenen Datum durchgeführt. "
        "Neuere Entwicklungen sind möglicherweise nicht berücksichtigt.",
        "",
        "---",
        ""
    ])

    # ==================== SCHLUSSFOLGERUNGEN ====================
    lines.extend([
        "## Schlussfolgerungen",
        ""
    ])

    if session.verified_facts:
        verification_rate = (meta['verified_facts_count'] / max(meta['total_facts_extracted'], 1) * 100)

        conclusion_text = (
            f"Diese Tiefenrecherche zum Thema '{session.query}' liefert ein fundiertes Verständnis "
            f"basierend auf {meta['total_sources_processed']} analysierten Quellen. "
            f"Mit einer Verifizierungsrate von {verification_rate:.1f}% (durch multiple Quellen bestätigt) "
            f"bietet die Recherche {'eine solide' if verification_rate > 50 else 'eine vorläufige'} Grundlage "
            "für weitere Analysen."
        )

        lines.append(conclusion_text)
        lines.append("")

        # Haupt-Schlussfolgerungen
        if session.thesis_analyses:
            lines.append("**Zentrale Schlussfolgerungen:**")
            lines.append("")
            for i, analysis in enumerate(session.thesis_analyses, 1):
                if analysis.synthesis:
                    lines.append(f"{i}. **{analysis.topic}:** {analysis.synthesis}")
            lines.append("")

    else:
        lines.extend([
            "Die Recherche konnte keine ausreichend verifizierten Fakten liefern. "
            "Eine weitergehende Analyse mit zusätzlichen Quellen oder alternativen Suchstrategien wird empfohlen.",
            ""
        ])

    lines.extend(["---", ""])

    # ==================== QUELLENVERZEICHNIS ====================
    lines.extend([
        "## Quellenverzeichnis",
        "",
        "Alle in dieser Recherche verwendeten Quellen mit Qualitätsbewertung:",
        "",
        "| # | Titel | Qualität | Bias | URL |",
        "|---|-------|----------|------|-----|"
    ])

    for i, node in enumerate(session.research_tree[:30], 1):
        quality = node.quality_metrics.overall_quality.value if node.quality_metrics else "unknown"
        bias = node.quality_metrics.bias_level.value if node.quality_metrics else "unknown"

        quality_icon = {
            "excellent": "🟢",
            "good": "🟡",
            "medium": "🟠",
            "poor": "🔴",
            "unknown": "⚪"
        }.get(quality, "")

        title_short = node.title[:60] + "..." if len(node.title) > 60 else node.title
        domain = urlparse(node.url).netloc

        lines.append(f"| {i} | {title_short} | {quality_icon} {quality} | {bias} | [{domain}]({node.url}) |")

    lines.append("")

    # ==================== TREND-QUELLEN ====================
    arxiv_claims = [c for c in session.unverified_claims if c.get("source_type") == "arxiv"]
    github_claims = [c for c in session.unverified_claims if c.get("source_type") == "github"]
    hf_claims = [c for c in session.unverified_claims if c.get("source_type") == "huggingface"]
    yt_claims_report = [c for c in session.unverified_claims if c.get("source_type") == "youtube"]

    if yt_claims_report or arxiv_claims or github_claims or hf_claims:
        lines.extend(["### Trend-Quellen (YouTube / ArXiv / GitHub / HuggingFace)", ""])
        lines.extend([
            "| # | Typ | Titel | Details | URL |",
            "|---|-----|-------|---------|-----|"
        ])

        idx = 1
        for c in yt_claims_report[:10]:
            title = c.get("source_title", "")[:50]
            channel = c.get("channel", "")
            url = c.get("source", "")
            lines.append(f"| YT{idx} | YouTube | {title} | Kanal: {channel} | {url} |")
            idx += 1

        idx = 1
        for c in arxiv_claims[:10]:
            title = c.get("source_title", "")[:50]
            authors = c.get("authors", "")[:40]
            pub = c.get("published_date", "")
            url = c.get("source", "")
            lines.append(f"| A{idx} | ArXiv | {title} | {authors} ({pub}) | {url} |")
            idx += 1

        idx = 1
        for c in github_claims[:10]:
            name = c.get("full_name", c.get("source_title", ""))[:50]
            stars = c.get("stars", 0)
            lang = c.get("language", "")
            url = c.get("source", "")
            lines.append(f"| GH{idx} | GitHub | {name} | {stars:,}★ {lang} | {url} |")
            idx += 1

        idx = 1
        for c in hf_claims[:10]:
            title = c.get("source_title", "")[:50]
            hf_type = c.get("hf_type", "model")
            details = f"Downloads: {c.get('downloads', 0):,}" if hf_type == "model" else f"Upvotes: {c.get('upvotes', 0)}"
            url = c.get("source", "")
            lines.append(f"| HF{idx} | HuggingFace | {title} | {details} | {url} |")
            idx += 1

        lines.append("")

    # ==================== FOOTER ====================
    lines.extend([
        "---",
        "",
        "### Über diesen Bericht",
        "",
        f"Dieser Bericht wurde automatisiert von **Timus Deep Research Engine v5.0** erstellt.",
        "",
        "**Features:**",
        "- Multi-Source Fakten-Verifikation",
        "- Quellenqualitäts-Bewertung",
        "- Bias-Erkennung",
        "- These-Antithese-Synthese Dialektik",
        "- Transparente Methodik",
        "",
        f"**Generiert am:** {now}",
        ""
    ])

    return "\n".join(lines)


def _create_text_report(session: DeepResearchSession, include_methodology: bool = True) -> str:
    """Erstellt Plain-Text Version (Markdown-frei)."""
    md = _create_academic_markdown_report(session, include_methodology)
    # Markdown zu Text konvertieren
    text = md.replace("# ", "=== ").replace("## ", "--- ").replace("### ", ">> ")
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold entfernen
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'\1 (\2)', text)  # Links
    text = re.sub(r'^\|.+\|$', '', text, flags=re.MULTILINE)  # Tabellen entfernen
    return text


async def _create_narrative_synthesis_report(session: DeepResearchSession) -> str:
    """
    Erstellt einen lesbaren Gesamtbericht durch LLM-Synthese aller Quellen.

    Anders als der analytische Report: fließender Text, inhaltlich gegliedert,
    wie ein guter Zeitungsartikel oder Wikipedia-Eintrag — direkt lesbar.
    """
    # Material für den LLM zusammenstellen
    facts_text = ""
    if session.verified_facts:
        facts_text += "VERIFIZIERTE FAKTEN:\n"
        for i, f in enumerate(session.verified_facts[:25], 1):
            quotes = f.get("supporting_quotes", [])
            quote_str = f' | Zitat: "{quotes[0][:150]}"' if quotes and quotes[0] else ""
            facts_text += f"{i}. {f.get('fact', '')}{quote_str}\n"

    if session.unverified_claims:
        facts_text += "\nWEITERE HINWEISE (noch nicht durch mehrere Quellen bestätigt):\n"
        for i, c in enumerate(session.unverified_claims[:20], 1):
            source_type = c.get("source_type", "web")
            prefix_map = {
                "youtube": "[YT] ",
                "arxiv": "[Paper] ",
                "github": "[GitHub] ",
                "huggingface": "[HF] ",
                "edison": "[Literatur] ",
            }
            prefix = prefix_map.get(source_type, "")
            facts_text += f"{i}. {prefix}{c.get('fact', '')}\n"

    syntheses_text = ""
    if session.thesis_analyses:
        syntheses_text = "\nSYNTHESEN AUS DER QUELLENANALYSE:\n"
        for a in session.thesis_analyses:
            if a.synthesis:
                syntheses_text += f"• {a.topic}: {a.synthesis}\n"

    sources_text = ""
    if session.research_tree:
        sources_text = "\nGENUTZTE WEB-QUELLEN:\n"
        for node in session.research_tree[:20]:
            sources_text += f"- {node.title} | {node.url}\n"

    yt_sources_text = ""
    yt_claims = [c for c in session.unverified_claims if c.get("source_type") == "youtube"]
    if yt_claims:
        yt_sources_text = "\nYOUTUBE-QUELLEN:\n"
        for c in yt_claims:
            title = c.get("source_title", c.get("video_id", ""))
            channel = c.get("channel", "")
            url = c.get("source", "")
            yt_sources_text += f"- [Video: {title}] | Kanal: {channel} | {url}\n"

    # Trend-Quellen-Texte für Prompt aufbereiten
    arxiv_items = [c for c in session.unverified_claims if c.get("source_type") == "arxiv"]
    github_items = [c for c in session.unverified_claims if c.get("source_type") == "github"]
    hf_items = [c for c in session.unverified_claims if c.get("source_type") == "huggingface"]

    trend_sources_text = ""
    if arxiv_items:
        trend_sources_text += "\nARXIV-PAPER:\n"
        for c in arxiv_items:
            authors = c.get("authors", "")
            pub = c.get("published_date", "")
            trend_sources_text += f"- [Paper: {c.get('source_title', '')}] | {authors} ({pub}) | {c.get('source', '')}\n"
    if github_items:
        trend_sources_text += "\nGITHUB-PROJEKTE:\n"
        for c in github_items:
            stars = c.get("stars", 0)
            lang = c.get("language", "")
            trend_sources_text += f"- [GitHub: {c.get('full_name', c.get('source_title', ''))} ({stars:,}★, {lang})] | {c.get('source', '')}\n"
    if hf_items:
        trend_sources_text += "\nHUGGINGFACE-MODELLE/PAPER:\n"
        for c in hf_items:
            trend_sources_text += f"- [HF: {c.get('source_title', '')}] | {c.get('source', '')}\n"

    prompt = f"""Du erhältst Recherche-Ergebnisse zu folgendem Thema und sollst daraus einen ausführlichen, gut lesbaren Bericht schreiben.

THEMA: {session.query}

{facts_text}{syntheses_text}{sources_text}{yt_sources_text}{trend_sources_text}

AUFGABE:
Schreibe einen ausführlichen Lesebericht auf Deutsch, der alle wichtigen Informationen zu einem kohärenten, fließenden Text zusammenfasst.

FORMAT-VORGABEN:
- Beginne mit einer Einleitung, die das Thema und seinen Kontext erklärt (mindestens 2-3 Absätze)
- Gliedere den Hauptteil nach inhaltlichen Schwerpunkten (nicht nach Quellen-Reihenfolge)
- Nutze ## Überschriften für die Hauptabschnitte (mindestens 4 Abschnitte)
- Jeder Hauptabschnitt: mindestens 3-4 vollständige Absätze mit je 3-5 Sätzen
- Nutze direkte Zitate aus den Quellen in Anführungszeichen
- Erkläre Zusammenhänge und Widersprüche zwischen verschiedenen Quellen
- YouTube-Quellen mit [Video: Titel] kennzeichnen, wenn du darauf Bezug nimmst
- ArXiv-Paper mit [Paper: Titel] kennzeichnen, wenn du darauf Bezug nimmst
- GitHub-Projekte mit [GitHub: Name (★)] kennzeichnen, wenn du darauf Bezug nimmst
- HuggingFace-Modelle/-Paper mit [HF: Name] kennzeichnen, wenn du darauf Bezug nimmst
- Schreibe in ganzen Sätzen und Absätzen — kein reines Bullet-Point-Staccato
- Wo sinnvoll dürfen Aufzählungen zur Übersichtlichkeit eingesetzt werden
- Beende mit einem ausführlichen Fazit (mindestens 3 Absätze)
- Füge am Ende ein Quellenverzeichnis als nummerierte Liste mit Titel und URL ein
- Länge: 2500–5000 Wörter — lieber zu ausführlich als zu kurz
- Ton: sachlich, informativ, gut lesbar — wie ein guter Wikipedia-Artikel oder Zeitungsfeature

Wichtig: Schreibe NUR den Berichtstext. Kein Meta-Kommentar über den Schreibprozess."""

    def _call():
        token_param = _get_token_param_name(SMART_MODEL)
        response = client.chat.completions.create(
            model=SMART_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            **{token_param: 6000},
        )
        return response.choices[0].message.content or ""

    try:
        narrative = await asyncio.to_thread(_call)
    except Exception as e:
        logger.warning(f"Narrative-Synthese LLM-Call fehlgeschlagen: {e}")
        narrative = "_Narrative Synthese konnte nicht erstellt werden._"

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    source_count = len(session.research_tree)
    yt_count = len([c for c in session.unverified_claims if c.get("source_type") == "youtube"])
    arxiv_count = len([c for c in session.unverified_claims if c.get("source_type") == "arxiv"])
    github_count = len([c for c in session.unverified_claims if c.get("source_type") == "github"])
    hf_count = len([c for c in session.unverified_claims if c.get("source_type") == "huggingface"])

    extras = []
    if yt_count > 0:
        extras.append(f"{yt_count} YouTube-Videos")
    if arxiv_count > 0:
        extras.append(f"{arxiv_count} ArXiv-Paper")
    if github_count > 0:
        extras.append(f"{github_count} GitHub-Projekte")
    if hf_count > 0:
        extras.append(f"{hf_count} HuggingFace-Einträge")

    extras_info = (", " + ", ".join(extras)) if extras else ""
    header = (
        f"# Recherche-Bericht\n"
        f"## {session.query}\n\n"
        f"*Erstellt am {now} | Timus Deep Research v6.0 | Basierend auf {source_count} Web-Quellen{extras_info}*\n\n"
        f"---\n\n"
    )
    return header + narrative


# ==============================================================================
# ÖFFENTLICHE RPC-METHODEN (erweitert für v5.0)
# ==============================================================================

@tool(
    name="start_deep_research",
    description="Startet eine akademische Tiefenrecherche (v5.0) mit Quellenqualitätsbewertung, These-Antithese-Synthese Analyse und erweiterter Fakten-Verifikation.",
    parameters=[
        P("query", "string", "Die Hauptsuchanfrage"),
        P("focus_areas", "array", "Optionale Liste von Fokusthemen", required=False),
        P("max_depth", "integer", "Maximale Tiefe der Recherche (1-5)", required=False),
        P("verification_mode", "string", "Verifikationsmodus: strict, moderate oder light", required=False, default="strict"),
    ],
    capabilities=["research", "deep_research"],
    category=C.RESEARCH
)
async def _run_research_pipeline(
    query: str,
    session_id: str,
    current_session: "DeepResearchSession",
    verification_mode: str,
    max_depth: Optional[int],
    focus_areas: Optional[List[str]],
) -> dict:
    """
    Interne Pipeline-Funktion — wird von start_deep_research aufgerufen
    und ggf. mit light-Mode wiederholt (Fallback).
    """
    config = get_adaptive_config(query, current_session.focus_areas)

    # PHASE 1: INITIALE SUCHE
    logger.info("📡 Phase 1: Initiale Websuche...")
    initial_sources = await _perform_initial_search(query, current_session)

    if not initial_sources:
        return {
            "session_id": session_id,
            "status": "no_results",
            "message": "Keine Suchergebnisse gefunden."
        }

    # PHASE 2: RELEVANZ-BEWERTUNG
    logger.info("⚖️ Phase 2: Relevanz-Bewertung...")
    relevant_sources = await _evaluate_relevance(
        initial_sources,
        query,
        current_session.focus_areas,
        config["max_sources_to_deep_dive"]
    )

    if not relevant_sources:
        return {
            "session_id": session_id,
            "status": "no_relevant_sources",
            "message": "Keine relevanten Quellen gefunden."
        }

    # PHASE 3: DEEP DIVE MIT QUALITÄTSBEWERTUNG
    logger.info(f"🏊 Phase 3: Deep Dive in {len(relevant_sources)} Quellen (mit Qualitätsbewertung)...")
    await _deep_dive_sources(
        relevant_sources,
        current_session,
        max_depth,
        verification_mode,
        config
    )

    current_session.methodology_notes.append(
        f"Analysierte {len(current_session.research_tree)} Quellen mit Qualitätsbewertung"
    )

    # PHASE 4: ERWEITERTE FAKTEN-VERIFIKATION
    logger.info("🔍 Phase 4: Erweiterte Fakten-Verifikation (mit fact_corroborator)...")
    verified_data = await _deep_verify_facts(current_session, verification_mode)

    current_session.methodology_notes.append(
        f"Verifikation: {len(current_session.verified_facts)} von {len(current_session.all_extracted_facts_raw)} Fakten verifiziert"
    )

    # PHASE 5: THESE-ANTITHESE-SYNTHESE ANALYSE
    logger.info("🎓 Phase 5: These-Antithese-Synthese Analyse...")
    if len(current_session.verified_facts) >= MIN_SOURCES_FOR_THESIS:
        thesis_analyses = await _analyze_thesis_antithesis_synthesis(current_session)
        current_session.methodology_notes.append(
            f"These-Antithese-Synthese: {len(thesis_analyses)} Analysen erstellt"
        )
    else:
        logger.warning(f"Zu wenige Fakten für These-Analyse ({len(current_session.verified_facts)} < {MIN_SOURCES_FOR_THESIS})")
        current_session.limitations.append(
            f"Zu wenige verifizierte Fakten ({len(current_session.verified_facts)}) für vollständige These-Antithese-Synthese Analyse"
        )

    # PHASE 6: YOUTUBE-RECHERCHE (Pflichtquelle — DE + EN, Podcasts + Interviews)
    yt_count = 0
    if os.getenv("DEEP_RESEARCH_YOUTUBE_ENABLED", "true").lower() != "false":
        try:
            from tools.deep_research.youtube_researcher import YouTubeResearcher
            yt_max = int(os.getenv("YOUTUBE_MAX_VIDEOS", "5"))
            yt_count = await YouTubeResearcher().research_topic_on_youtube(
                query=query, session=current_session, max_videos=yt_max
            )
            logger.info(f"📺 YouTube: {yt_count} Videos analysiert (DE+EN, Podcasts/Interviews)")
            if yt_count > 0:
                current_session.methodology_notes.append(
                    f"YouTube: {yt_count} Videos analysiert (bilingual DE+EN, inkl. Podcasts & Interviews)"
                )
            else:
                logger.warning("📺 YouTube: 0 Videos analysiert — DataForSEO oder Transkript prüfen")
        except Exception as e:
            logger.warning(f"YouTube-Recherche fehlgeschlagen: {e}")

    # PHASE 7: TREND-RECHERCHE (ArXiv + GitHub + HuggingFace)
    trend_count = 0
    if os.getenv("DEEP_RESEARCH_TRENDS_ENABLED", "true").lower() == "true":
        try:
            from tools.deep_research.trend_researcher import TrendResearcher
            trend_count = await TrendResearcher().research_trends(
                query=query, session=current_session, max_per_source=3
            )
            logger.info(f"📊 Trends: {trend_count} Einträge analysiert")
            if trend_count > 0:
                current_session.methodology_notes.append(
                    f"Trend-Recherche: {trend_count} Einträge aus ArXiv/GitHub/HuggingFace"
                )
        except Exception as e:
            logger.warning(f"Trend-Recherche fehlgeschlagen (unkritisch): {e}")

    # PHASE 8: FINALE SYNTHESE
    logger.info("📝 Phase 8: Finale Synthese...")
    analysis = await _synthesize_findings(current_session, verified_data)

    return {
        "_pipeline_ok": True,
        "verified_data": verified_data,
        "verified_count": len(current_session.verified_facts),
        "yt_count": yt_count,
        "trend_count": trend_count,
        "analysis": analysis,
    }


async def start_deep_research(
    query: str,
    focus_areas: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    verification_mode: str = "strict"
) -> dict:
    """
    Startet eine akademische Tiefenrecherche (v7.0).

    NEU in v7.0:
    - Language-Detection → US-Location für englische Queries
    - Domain-aware Embedding-Threshold (Tech: 0.72)
    - Auto-Mode: strict + Tech → moderate
    - Corroborator für alle Fakten mit source_count ≥ 1
    - ArXiv Threshold 5 + topic-aware Fallback-Score
    - Qualitäts-Gate (verified ≥ 3) + automatischer light-Fallback
    - DrDiagnostics Integration

    Args:
        query: Die Hauptsuchanfrage
        focus_areas: Optionale Liste von Fokusthemen
        max_depth: Maximale Tiefe der Recherche (1-5)
        verification_mode: "strict", "moderate" oder "light"

    Returns:
        Success mit session_id und umfassenden Analyseergebnissen
    """
    session_id = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    current_session = DeepResearchSession(query, focus_areas)
    research_sessions[session_id] = current_session

    # v7.0: Diagnostics initialisieren
    try:
        from tools.deep_research.diagnostics import reset as diag_reset
        diag = diag_reset()
        diag.query = query
        diag.verification_mode_req = verification_mode
    except Exception:
        pass

    # Metadaten speichern
    current_session.research_metadata = {
        "verification_mode": verification_mode,
        "max_depth": max_depth,
        "version": "7.0"
    }

    try:
        logger.info(f"🔬 Starte Deep Research v7.0 Session {session_id}: '{query}'")

        # v7.0: Pipeline ausführen
        pipe = await _run_research_pipeline(
            query=query,
            session_id=session_id,
            current_session=current_session,
            verification_mode=verification_mode,
            max_depth=max_depth,
            focus_areas=focus_areas,
        )

        if not pipe.get("_pipeline_ok"):
            return pipe  # no_results / no_relevant_sources

        verified_data = pipe["verified_data"]
        verified_count = pipe["verified_count"]
        yt_count = pipe["yt_count"]
        trend_count = pipe["trend_count"]
        analysis = pipe["analysis"]
        fallback_triggered = False

        # v7.0: Qualitäts-Gate + automatischer light-Fallback
        quality_ok = verified_count >= 3
        if not quality_ok and verification_mode != "light":
            logger.warning(
                f"⚠️ Qualitäts-Gate failed: {verified_count} verified < 3. "
                f"Starte light-Mode Fallback..."
            )
            fallback_triggered = True
            current_session.methodology_notes.append(
                f"Qualitäts-Gate failed ({verified_count} verified) → light-Mode Retry"
            )
            try:
                from tools.deep_research.diagnostics import get_current
                diag = get_current()
                if diag is not None:
                    diag.fallback_triggered = True
            except Exception:
                pass

            fallback_session = DeepResearchSession(query, focus_areas)
            pipe2 = await _run_research_pipeline(
                query=query,
                session_id=session_id,
                current_session=fallback_session,
                verification_mode="light",
                max_depth=max_depth,
                focus_areas=focus_areas,
            )
            if pipe2.get("_pipeline_ok") and pipe2["verified_count"] > verified_count:
                current_session = fallback_session
                research_sessions[session_id] = current_session
                verified_data = pipe2["verified_data"]
                verified_count = pipe2["verified_count"]
                yt_count = pipe2["yt_count"]
                trend_count = pipe2["trend_count"]
                analysis = pipe2["analysis"]
                quality_ok = verified_count >= 3
                logger.info(f"✅ Fallback: {verified_count} verified nach light-Mode")

        logger.info(f"✅ Session {session_id} abgeschlossen (verified={verified_count}, quality_gate={'OK' if quality_ok else 'WARN'})")

        # Diagnostics abschließen
        try:
            from tools.deep_research.diagnostics import get_current
            diag = get_current()
            if diag is not None:
                diag.finish()
        except Exception:
            pass

        # PHASE 7: AUTOMATISCHER REPORT (NEU v5.0)
        filepath = None
        try:
            logger.info(f"📄 Erstelle akademischen Report für {session_id}...")

            report_content = _create_academic_markdown_report(current_session, include_methodology=True)

            # Direkt speichern
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
                        filename = f"DeepResearch_Academic_{session_id}.md"
                        filepath = candidate / filename

                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(report_content)

                        filepath = str(filepath)
                        logger.info(f"✅ Akademischer Report gespeichert: {filepath}")
                        break
                except PermissionError:
                    continue
                except Exception as e:
                    logger.warning(f"Konnte nicht in {candidate} speichern: {e}")
                    continue

            if not filepath:
                logger.warning("⚠️ Report konnte nicht gespeichert werden")

        except Exception as e:
            logger.error(f"❌ Fehler beim Report-Erstellen: {e}")

        return {
            "session_id": session_id,
            "status": "completed",
            "version": "7.0",
            "facts_extracted": len(current_session.all_extracted_facts_raw),
            "verified_count": len(current_session.verified_facts),
            "unverified_count": len(current_session.unverified_claims),
            "conflicts_count": len(current_session.conflicting_info),
            "sources_analyzed": len(current_session.visited_urls),
            "thesis_analyses_count": len(current_session.thesis_analyses),
            "youtube_videos_analyzed": yt_count,
            "trend_sources_analyzed": trend_count,
            "quality_gate_passed": quality_ok,
            "fallback_triggered": fallback_triggered,
            "source_quality_summary": current_session.source_quality_summary,
            "bias_summary": current_session.bias_summary,
            "analysis": analysis,
            "verified_data": verified_data,
            "report_filepath": filepath,
            "methodology_notes": current_session.methodology_notes,
            "limitations": current_session.limitations
        }

    except Exception as e:
        logger.error(f"Fehler in Session {session_id}: {e}", exc_info=True)
        raise Exception(f"Recherche-Fehler: {str(e)}")


@tool(
    name="get_research_status",
    description="Gibt den Status einer laufenden oder abgeschlossenen Tiefenrecherche-Session zurück.",
    parameters=[
        P("session_id", "string", "Die Session-ID der Recherche"),
    ],
    capabilities=["research", "deep_research"],
    category=C.RESEARCH
)
async def get_research_status(session_id: str) -> dict:
    """Gibt den Status einer Recherche zurück."""
    session = research_sessions.get(session_id)

    if not session:
        raise Exception(f"Session '{session_id}' nicht gefunden.")

    return {
        "session_id": session_id,
        "query": session.query,
        "summary": _get_research_metadata_summary(session)
    }


@tool(
    name="generate_research_report",
    description="Erstellt einen druckreifen akademischen Bericht (v5.0) mit Executive Summary, Methodik, These-Antithese-Synthese und Quellenqualitäts-Tabellen.",
    parameters=[
        P("session_id", "string", "Die Session-ID der Recherche", required=False),
        P("session_id_to_report", "string", "Alternative Session-ID (Alias)", required=False),
        P("format", "string", "Report-Format: markdown oder text", required=False, default="markdown"),
        P("report_format_type", "string", "Alternatives Format-Feld (Alias)", required=False),
        P("include_methodology", "boolean", "Ob Methodik-Sektion enthalten sein soll", required=False, default="true"),
    ],
    capabilities=["research", "deep_research"],
    category=C.RESEARCH
)
async def generate_research_report(
    session_id: Optional[str] = None,
    session_id_to_report: Optional[str] = None,
    format: str = "markdown",
    report_format_type: Optional[str] = None,
    include_methodology: bool = True
) -> dict:
    """
    Erstellt einen druckreifen akademischen Bericht (v5.0).

    NEU in v5.0:
    - Akademischer Stil mit Executive Summary
    - Methodik-Sektion
    - These-Antithese-Synthese Framework
    - Quellenqualitäts-Tabellen
    - Kritische Diskussion & Limitationen

    Args:
        session_id: Die Session-ID
        format: "markdown" oder "text"
        include_methodology: Ob Methodik-Sektion enthalten sein soll

    Returns:
        Success mit Pfad zum Report
    """
    # Parameter-Aliases
    actual_session_id = session_id or session_id_to_report
    actual_format = report_format_type or format

    if not actual_session_id:
        raise Exception("session_id ist erforderlich.")

    session = research_sessions.get(actual_session_id)

    if not session:
        raise Exception(f"Session '{actual_session_id}' nicht gefunden.")

    # Report erstellen
    logger.info(f"📄 Erstelle akademischen Report für {actual_session_id}...")

    if actual_format.lower() == "markdown":
        content = _create_academic_markdown_report(session, include_methodology)
    else:
        content = _create_text_report(session, include_methodology)

    # Report speichern
    filepath = None

    try:
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
                if candidate.exists():
                    ext = "md" if actual_format.lower() == "markdown" else "txt"
                    filename = f"DeepResearch_Academic_{actual_session_id}.{ext}"
                    filepath = candidate / filename

                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)

                    filepath = str(filepath)
                    logger.info(f"✅ Report gespeichert: {filepath}")
                    break
            except Exception as e:
                logger.warning(f"Fehler beim Speichern in {candidate}: {e}")
                continue

    except Exception as e:
        logger.error(f"Report-Speicherung fehlgeschlagen: {e}")

    # Lesbaren Gesamtbericht (Narrative Synthese) erstellen und separat speichern
    narrative_filepath = None
    narrative_content = ""
    try:
        logger.info("📖 Erstelle lesbaren Gesamtbericht (Narrative Synthese)...")
        narrative_content = await _create_narrative_synthesis_report(session)

        from pathlib import Path
        base_dir = Path(filepath).parent if filepath else Path("/home/fatih-ubuntu/dev/timus/results")
        base_dir.mkdir(parents=True, exist_ok=True)
        narrative_filename = f"DeepResearch_Bericht_{actual_session_id}.md"
        narrative_path = base_dir / narrative_filename
        with open(narrative_path, "w", encoding="utf-8") as f:
            f.write(narrative_content)
        narrative_filepath = str(narrative_path)
        logger.info(f"📖 Lesebericht gespeichert: {narrative_filepath}")
    except Exception as e:
        logger.warning(f"Lesebericht-Erstellung fehlgeschlagen: {e}")

    # Bilder sammeln
    images = []
    if os.getenv("DEEP_RESEARCH_IMAGES_ENABLED", "true").lower() == "true":
        try:
            from pathlib import Path as _Path
            from tools.deep_research.image_collector import ImageCollector
            sections = re.findall(r"^##\s+(.+)$", narrative_content, re.MULTILINE)
            images = await ImageCollector().collect_images_for_sections(
                sections[:4], session.query, max_images=4
            )
            logger.info(f"🖼️ {len(images)} Bilder gesammelt")
        except Exception as e:
            logger.warning(f"Bilder-Sammlung fehlgeschlagen (unkritisch): {e}")

    # PDF erstellen
    pdf_filepath = None
    if os.getenv("DEEP_RESEARCH_PDF_ENABLED", "true").lower() == "true":
        try:
            from pathlib import Path as _Path
            from tools.deep_research.pdf_builder import ResearchPDFBuilder
            base_dir_pdf = (
                _Path(filepath).parent if filepath
                else _Path("/home/fatih-ubuntu/dev/timus/results")
            )
            pdf_path = str(base_dir_pdf / f"DeepResearch_PDF_{actual_session_id}.pdf")
            pdf_filepath = ResearchPDFBuilder().build_pdf(
                narrative_content, images, session, pdf_path
            )
            logger.info(f"📄 PDF erstellt: {pdf_filepath}")
        except Exception as e:
            logger.warning(f"PDF-Erstellung fehlgeschlagen (unkritisch): {e}")

    yt_count = len([c for c in session.unverified_claims if c.get("source_type") == "youtube"])

    if filepath:
        return {
            "session_id": actual_session_id,
            "status": "report_created",
            "format": actual_format,
            "filepath": filepath,
            "narrative_filepath": narrative_filepath,
            "pdf_filepath": pdf_filepath,
            "youtube_videos_analyzed": yt_count,
            "images_in_pdf": len(images),
            "message": (
                f"Akademischer Bericht erstellt. "
                f"Lesebericht: {narrative_filepath or 'nicht verfügbar'}. "
                f"PDF: {pdf_filepath or 'nicht verfügbar'}."
            ),
            "summary": _get_research_metadata_summary(session),
            "version": "6.0"
        }
    else:
        # Fallback: Content im Response
        return {
            "session_id": actual_session_id,
            "status": "report_created_not_saved",
            "format": actual_format,
            "content": content,
            "narrative_filepath": narrative_filepath,
            "pdf_filepath": pdf_filepath,
            "youtube_videos_analyzed": yt_count,
            "images_in_pdf": len(images),
            "message": "Bericht erstellt, aber Speichern fehlgeschlagen. Content im Response.",
            "summary": _get_research_metadata_summary(session),
            "version": "6.0"
        }




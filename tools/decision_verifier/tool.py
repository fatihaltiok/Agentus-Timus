
# tools/decision_verifier/tool.py
"""
Decision & Verification Tool - Intelligente Entscheidungsfindung und Faktenverifikation
"""
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from openai import OpenAI
from utils.openai_compat import prepare_openai_params
from dotenv import load_dotenv
import os
import asyncio

# Logger
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | decision_verifier | %(message)s",
    )

# OpenAI Client
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Verifikations-Strategien
VERIFICATION_STRATEGIES = {
    "cross_reference": "Vergleiche Information über mehrere Quellen",
    "temporal_consistency": "Prüfe zeitliche Konsistenz der Informationen",
    "source_credibility": "Bewerte Glaubwürdigkeit der Quellen",
    "logical_consistency": "Prüfe logische Konsistenz",
    "expert_consensus": "Suche nach Experten-Konsens",
    "empirical_evidence": "Suche nach empirischen Belegen"
}

@tool(
    name="make_research_decision",
    description="Trifft intelligente Entscheidungen über den weiteren Recherche-Verlauf.",
    parameters=[
        P("query", "string", "Original-Anfrage", required=True),
        P("initial_findings", "array", "Bisherige Erkenntnisse als Liste von Dicts", required=True),
        P("research_goals", "array", "Spezifische Recherche-Ziele", required=False, default=None),
    ],
    capabilities=["analysis", "verification"],
    category=C.ANALYSIS
)
async def make_research_decision(
    query: str,
    initial_findings: List[Dict[str, Any]],
    research_goals: Optional[List[str]] = None
) -> dict:
    """
    Trifft intelligente Entscheidungen über den weiteren Recherche-Verlauf.

    Args:
        query: Original-Anfrage
        initial_findings: Bisherige Erkenntnisse
        research_goals: Spezifische Recherche-Ziele

    Returns:
        Entscheidung über nächste Schritte
    """
    try:
        # Analysiere bisherige Erkenntnisse
        analysis = await _analyze_findings(query, initial_findings, research_goals)

        # Identifiziere Wissenslücken
        gaps = await _identify_knowledge_gaps(query, analysis, research_goals)

        # Bewerte Informationsqualität
        quality_score = await _assess_information_quality(initial_findings)

        # Treffe Entscheidung
        decision = await _make_decision(analysis, gaps, quality_score)

        logger.info(f"📊 Entscheidung getroffen: {decision['action']}")

        return {
            "decision": decision,
            "analysis": analysis,
            "knowledge_gaps": gaps,
            "quality_score": quality_score,
            "recommendations": decision.get("next_steps", [])
        }

    except Exception as e:
        logger.error(f"❌ Fehler bei Entscheidungsfindung: {e}")
        return {"status": "error", "message": str(e)}

@tool(
    name="verify_information",
    description="Verifiziert Informationen durch verschiedene Strategien.",
    parameters=[
        P("claims", "array", "Liste von zu verifizierenden Behauptungen", required=True),
        P("sources", "array", "Liste der Quellen", required=True),
        P("verification_level", "string", "Wie streng verifiziert werden soll (light, standard, strict)", required=False, default="standard"),
    ],
    capabilities=["analysis", "verification"],
    category=C.ANALYSIS
)
async def verify_information(
    claims: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    verification_level: str = "standard"  # light, standard, strict
) -> dict:
    """
    Verifiziert Informationen durch verschiedene Strategien.

    Args:
        claims: Liste von zu verifizierenden Behauptungen
        sources: Liste der Quellen
        verification_level: Wie streng verifiziert werden soll

    Returns:
        Verifikationsergebnisse
    """
    try:
        verification_results = []

        for claim in claims:
            # Wähle Verifikationsstrategien basierend auf Level
            strategies = _select_verification_strategies(claim, verification_level)

            # Führe Verifikation durch
            result = await _verify_single_claim(claim, sources, strategies)
            verification_results.append(result)

        # Erstelle Zusammenfassung
        summary = await _create_verification_summary(verification_results)

        return {
            "verified_claims": [r for r in verification_results if r["status"] == "verified"],
            "disputed_claims": [r for r in verification_results if r["status"] == "disputed"],
            "unverifiable_claims": [r for r in verification_results if r["status"] == "unverifiable"],
            "summary": summary,
            "confidence_score": _calculate_overall_confidence(verification_results)
        }

    except Exception as e:
        logger.error(f"❌ Fehler bei Verifikation: {e}")
        return {"status": "error", "message": str(e)}

@tool(
    name="evaluate_source_credibility",
    description="Bewertet die Glaubwürdigkeit einer Quelle.",
    parameters=[
        P("source_url", "string", "URL der Quelle", required=True),
        P("source_content", "string", "Optionaler Inhalt für tiefere Analyse", required=False, default=None),
    ],
    capabilities=["analysis", "verification"],
    category=C.ANALYSIS
)
async def evaluate_source_credibility(
    source_url: str,
    source_content: Optional[str] = None
) -> dict:
    """
    Bewertet die Glaubwürdigkeit einer Quelle.

    Args:
        source_url: URL der Quelle
        source_content: Optionaler Inhalt für tiefere Analyse

    Returns:
        Glaubwürdigkeitsbewertung
    """
    try:
        # Extrahiere Domain-Informationen
        domain_info = _extract_domain_info(source_url)

        # Prüfe bekannte vertrauenswürdige Quellen
        trust_score = _check_trusted_sources(domain_info["domain"])

        # Analysiere Content-Qualität wenn vorhanden
        content_score = 0.5  # Default
        if source_content:
            content_score = await _analyze_content_quality(source_content)

        # Erstelle detaillierte Bewertung
        credibility = {
            "domain": domain_info["domain"],
            "trust_score": trust_score,
            "content_score": content_score,
            "overall_score": (trust_score + content_score) / 2,
            "category": _categorize_source(domain_info["domain"]),
            "warnings": _check_source_warnings(domain_info["domain"])
        }

        return credibility

    except Exception as e:
        logger.error(f"❌ Fehler bei Quellen-Bewertung: {e}")
        return {"status": "error", "message": str(e)}

# Hilfsfunktionen

async def _analyze_findings(
    query: str,
    findings: List[Dict[str, Any]],
    goals: Optional[List[str]]
) -> Dict[str, Any]:
    """Analysiert bisherige Erkenntnisse"""

    prompt = f"""
    Analysiere diese Recherche-Erkenntnisse:

    Ursprüngliche Frage: {query}
    Recherche-Ziele: {', '.join(goals) if goals else 'Keine spezifischen Ziele'}

    Bisherige Erkenntnisse:
    {json.dumps(findings, ensure_ascii=False, indent=2)}

    Bewerte:
    1. Vollständigkeit (0-1): Wie vollständig ist die Antwort?
    2. Konsistenz (0-1): Wie konsistent sind die Informationen?
    3. Relevanz (0-1): Wie relevant sind die Erkenntnisse?
    4. Tiefe (0-1): Wie tiefgehend ist die Analyse?

    Gib eine JSON-Antwort:
    {{
        "completeness": float,
        "consistency": float,
        "relevance": float,
        "depth": float,
        "main_findings": ["finding1", "finding2"],
        "concerns": ["concern1", "concern2"]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Du bist ein Experte für Informationsanalyse."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1000
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        logger.error(f"Fehler bei Analyse: {e}")
        return {
            "completeness": 0.5,
            "consistency": 0.5,
            "relevance": 0.5,
            "depth": 0.5,
            "main_findings": [],
            "concerns": ["Analyse fehlgeschlagen"]
        }

async def _identify_knowledge_gaps(
    query: str,
    analysis: Dict[str, Any],
    goals: Optional[List[str]]
) -> List[Dict[str, str]]:
    """Identifiziert Wissenslücken"""

    prompt = f"""
    Identifiziere Wissenslücken in dieser Recherche:

    Frage: {query}
    Ziele: {goals}
    Analyse: {json.dumps(analysis, ensure_ascii=False)}

    Welche wichtigen Aspekte fehlen noch?
    Gib eine Liste von Wissenslücken im Format:
    [
        {{
            "gap": "Beschreibung der Lücke",
            "importance": "high/medium/low",
            "suggested_action": "Vorgeschlagene Aktion"
        }}
    ]
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Du identifizierst Wissenslücken in Recherchen."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        logger.error(f"Fehler bei Gap-Analyse: {e}")
        return []

async def _assess_information_quality(findings: List[Dict[str, Any]]) -> float:
    """Bewertet die Qualität der gesammelten Informationen"""

    if not findings:
        return 0.0

    # Faktoren für Qualitätsbewertung
    factors = {
        "source_diversity": len(set(f.get("source", "") for f in findings)) / len(findings),
        "has_primary_sources": any("primary" in str(f).lower() for f in findings),
        "has_expert_opinions": any("expert" in str(f).lower() or "professor" in str(f).lower() for f in findings),
        "has_data": any("study" in str(f).lower() or "research" in str(f).lower() for f in findings),
        "recency": _calculate_recency_score(findings)
    }

    # Gewichtete Bewertung
    weights = {
        "source_diversity": 0.25,
        "has_primary_sources": 0.2,
        "has_expert_opinions": 0.2,
        "has_data": 0.2,
        "recency": 0.15
    }

    quality_score = sum(
        factors[key] * weights[key]
        for key in factors
        if key in weights
    )

    return min(1.0, quality_score)

async def _make_decision(
    analysis: Dict[str, Any],
    gaps: List[Dict[str, str]],
    quality_score: float
) -> Dict[str, Any]:
    """Trifft Entscheidung über weiteres Vorgehen"""

    # Entscheidungslogik
    completeness = analysis.get("completeness", 0.5)
    high_priority_gaps = [g for g in gaps if g.get("importance") == "high"]

    if completeness >= 0.8 and quality_score >= 0.7 and not high_priority_gaps:
        return {
            "action": "finalize",
            "reason": "Recherche ist vollständig und qualitativ hochwertig",
            "confidence": 0.9
        }
    elif high_priority_gaps:
        return {
            "action": "deep_dive",
            "reason": f"{len(high_priority_gaps)} wichtige Wissenslücken identifiziert",
            "confidence": 0.8,
            "next_steps": [g["suggested_action"] for g in high_priority_gaps[:3]]
        }
    elif quality_score < 0.5:
        return {
            "action": "expand_sources",
            "reason": "Informationsqualität ist unzureichend",
            "confidence": 0.7,
            "next_steps": ["Suche nach akademischen Quellen", "Experten-Meinungen einholen"]
        }
    else:
        return {
            "action": "refine",
            "reason": "Recherche benötigt Verfeinerung",
            "confidence": 0.6,
            "next_steps": ["Verifiziere Hauptaussagen", "Suche nach Gegenargumenten"]
        }

def _select_verification_strategies(
    claim: Dict[str, Any],
    level: str
) -> List[str]:
    """Wählt passende Verifikationsstrategien"""

    strategies = ["cross_reference"]  # Minimum

    if level in ["standard", "strict"]:
        strategies.extend(["source_credibility", "logical_consistency"])

    if level == "strict":
        strategies.extend(["temporal_consistency", "expert_consensus", "empirical_evidence"])

    # Anpassung basierend auf Claim-Typ
    claim_text = claim.get("claim", "").lower()
    if any(word in claim_text for word in ["study", "research", "data"]):
        strategies.append("empirical_evidence")
    if any(word in claim_text for word in ["expert", "scientist", "professor"]):
        strategies.append("expert_consensus")

    return list(set(strategies))  # Deduplizieren

async def _verify_single_claim(
    claim: Dict[str, Any],
    sources: List[Dict[str, Any]],
    strategies: List[str]
) -> Dict[str, Any]:
    """Verifiziert einen einzelnen Claim"""

    verification_scores = {}

    for strategy in strategies:
        if strategy == "cross_reference":
            score = _cross_reference_check(claim, sources)
        elif strategy == "source_credibility":
            score = await _credibility_check(claim, sources)
        elif strategy == "logical_consistency":
            score = _logical_consistency_check(claim)
        else:
            score = 0.5  # Default für nicht implementierte Strategien

        verification_scores[strategy] = score

    # Gesamtbewertung
    avg_score = sum(verification_scores.values()) / len(verification_scores)

    status = "verified" if avg_score >= 0.7 else "disputed" if avg_score >= 0.4 else "unverifiable"

    supporting = _find_supporting_sources(claim, sources)

    # Evidence Pack anfuegen
    evidence_pack = None
    try:
        from utils.evidence_pack import EvidencePack, EvidenceItem
        pack = EvidencePack()
        for s in supporting:
            pack.add(EvidenceItem(
                claim=claim.get("claim", ""),
                source_url=s.get("url", ""),
                snippet=str(s.get("snippet", s.get("text", "")))[:200],
                confidence=avg_score,
            ))
        evidence_pack = pack.to_dict()
    except Exception:
        pass

    return {
        "claim": claim.get("claim", ""),
        "status": status,
        "confidence": avg_score,
        "verification_scores": verification_scores,
        "supporting_sources": supporting,
        "evidence_pack": evidence_pack,
    }

def _cross_reference_check(claim: Dict[str, Any], sources: List[Dict[str, Any]]) -> float:
    """Prüft ob Claim in mehreren Quellen bestätigt wird"""

    claim_text = claim.get("claim", "").lower()
    confirming_sources = 0

    for source in sources:
        source_text = str(source).lower()
        # Einfache Keyword-Übereinstimmung (könnte mit NLP verbessert werden)
        keywords = claim_text.split()
        matches = sum(1 for kw in keywords if kw in source_text)
        if matches >= len(keywords) * 0.5:  # 50% der Keywords gefunden
            confirming_sources += 1

    return min(1.0, confirming_sources / 3)  # 3 Quellen = volle Punktzahl

async def _credibility_check(claim: Dict[str, Any], sources: List[Dict[str, Any]]) -> float:
    """Prüft Glaubwürdigkeit der Quellen für einen Claim"""

    relevant_sources = _find_supporting_sources(claim, sources)
    if not relevant_sources:
        return 0.0

    credibility_scores = []
    for source in relevant_sources[:3]:  # Top 3 relevante Quellen
        if "url" in source:
            result = await evaluate_source_credibility(source["url"])
            if isinstance(result, dict):
                credibility_scores.append(result.get("overall_score", 0.5))

    return sum(credibility_scores) / len(credibility_scores) if credibility_scores else 0.5

def _logical_consistency_check(claim: Dict[str, Any]) -> float:
    """Prüft logische Konsistenz eines Claims"""
    # Vereinfachte Implementierung
    claim_text = claim.get("claim", "")

    # Prüfe auf offensichtliche Widersprüche
    contradiction_patterns = [
        ("increase", "decrease"),
        ("always", "never"),
        ("all", "none"),
        ("prove", "disprove")
    ]

    for word1, word2 in contradiction_patterns:
        if word1 in claim_text.lower() and word2 in claim_text.lower():
            return 0.3  # Niedriger Score bei Widersprüchen

    return 0.7  # Default für konsistente Claims

def _find_supporting_sources(claim: Dict[str, Any], sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Findet Quellen die einen Claim unterstützen"""

    claim_keywords = set(claim.get("claim", "").lower().split())
    supporting = []

    for source in sources:
        source_text = str(source).lower()
        overlap = len(claim_keywords.intersection(source_text.split()))
        if overlap >= len(claim_keywords) * 0.3:  # 30% Übereinstimmung
            supporting.append(source)

    return supporting[:5]  # Max 5 Quellen

async def _create_verification_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Erstellt Zusammenfassung der Verifikationsergebnisse"""

    verified = [r for r in results if r["status"] == "verified"]
    disputed = [r for r in results if r["status"] == "disputed"]
    unverifiable = [r for r in results if r["status"] == "unverifiable"]

    summary = {
        "total_claims": len(results),
        "verified": len(verified),
        "disputed": len(disputed),
        "unverifiable": len(unverifiable),
        "verification_rate": len(verified) / len(results) if results else 0,
        "average_confidence": sum(r["confidence"] for r in results) / len(results) if results else 0,
        "key_findings": {
            "strongest_claims": sorted(verified, key=lambda x: x["confidence"], reverse=True)[:3],
            "weakest_claims": sorted(results, key=lambda x: x["confidence"])[:3],
            "most_disputed": disputed[:3]
        }
    }

    return summary

def _calculate_overall_confidence(results: List[Dict[str, Any]]) -> float:
    """Berechnet Gesamt-Konfidenz der Verifikation"""
    if not results:
        return 0.0

    # Gewichtete Konfidenz basierend auf Status
    weights = {"verified": 1.0, "disputed": 0.5, "unverifiable": 0.2}

    weighted_sum = sum(
        r["confidence"] * weights.get(r["status"], 0.5)
        for r in results
    )

    return weighted_sum / len(results)

def _extract_domain_info(url: str) -> Dict[str, str]:
    """Extrahiert Domain-Informationen aus URL"""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Entferne www.
    if domain.startswith("www."):
        domain = domain[4:]

    return {
        "domain": domain,
        "subdomain": parsed.netloc.split('.')[0] if '.' in parsed.netloc else "",
        "path": parsed.path,
        "scheme": parsed.scheme
    }

def _check_trusted_sources(domain: str) -> float:
    """Prüft ob Domain in Liste vertrauenswürdiger Quellen"""

    trusted_domains = {
        # Nachrichten
        "reuters.com": 0.9,
        "apnews.com": 0.9,
        "bbc.com": 0.85,
        "theguardian.com": 0.8,
        "nytimes.com": 0.85,
        "washingtonpost.com": 0.85,
        "wsj.com": 0.85,
        "ft.com": 0.85,

        # Wissenschaft
        "nature.com": 0.95,
        "science.org": 0.95,
        "sciencedirect.com": 0.9,
        "pubmed.ncbi.nlm.nih.gov": 0.95,
        "arxiv.org": 0.85,

        # Institutionen
        "who.int": 0.95,
        "cdc.gov": 0.95,
        "nih.gov": 0.95,
        ".edu": 0.8,  # Universitäten
        ".gov": 0.85,  # Regierung

        # Tech
        "ieee.org": 0.9,
        "acm.org": 0.9,
        "stackoverflow.com": 0.7,
        "github.com": 0.75
    }

    # Prüfe exakte Übereinstimmung
    if domain in trusted_domains:
        return trusted_domains[domain]

    # Prüfe Endungen
    for ending, score in trusted_domains.items():
        if ending.startswith(".") and domain.endswith(ending):
            return score

    # Default für unbekannte Quellen
    return 0.5

async def _analyze_content_quality(content: str) -> float:
    """Analysiert die Qualität des Inhalts"""

    prompt = f"""
    Bewerte die Qualität dieses Textes auf einer Skala von 0.0 bis 1.0:

    Text (erste 1000 Zeichen):
    {content[:1000]}

    Kriterien:
    - Sachlichkeit und Objektivität
    - Verwendung von Quellen/Zitaten
    - Argumentationsqualität
    - Fehlen von Clickbait/Sensationalismus

    Gib nur eine Zahl zwischen 0.0 und 1.0 zurück.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Du bewertest Textqualität. Antworte nur mit einer Zahl."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=10
        )

        score = float(response.choices[0].message.content.strip())
        return max(0.0, min(1.0, score))

    except Exception as e:
        logger.error(f"Fehler bei Content-Analyse: {e}")
        return 0.5

def _categorize_source(domain: str) -> str:
    """Kategorisiert eine Quelle"""

    categories = {
        "news": ["reuters", "apnews", "bbc", "cnn", "nytimes", "guardian"],
        "academic": [".edu", "nature", "science", "pubmed", "arxiv", "jstor"],
        "government": [".gov", "who.int", "un.org", "europa.eu"],
        "tech": ["github", "stackoverflow", "ieee", "acm", "techcrunch"],
        "social": ["reddit", "twitter", "facebook", "linkedin"],
        "blog": ["medium", "wordpress", "blogger", "substack"],
        "wiki": ["wikipedia", "wikimedia"]
    }

    domain_lower = domain.lower()

    for category, patterns in categories.items():
        if any(pattern in domain_lower for pattern in patterns):
            return category

    return "other"

def _check_source_warnings(domain: str) -> List[str]:
    """Prüft auf Warnungen bei bestimmten Quellen"""

    warnings = []

    # Bekannte problematische Muster
    if any(pattern in domain.lower() for pattern in ["conspiracy", "truth", "real", "wake"]):
        warnings.append("Mögliche Verschwörungstheorie-Seite")

    if any(pattern in domain.lower() for pattern in ["blog", "personal", "opinion"]):
        warnings.append("Persönlicher Blog - subjektive Meinungen möglich")

    if domain.endswith(".ru") or domain.endswith(".cn"):
        warnings.append("Staatlich kontrollierte Medien möglich")

    if "wiki" in domain and "wikipedia" not in domain:
        warnings.append("Nicht-Wikipedia Wiki - Qualität kann variieren")

    return warnings

def _calculate_recency_score(findings: List[Dict[str, Any]]) -> float:
    """Berechnet Score basierend auf Aktualität der Informationen"""

    current_year = datetime.now().year
    recent_count = 0

    for finding in findings:
        text = str(finding).lower()
        # Suche nach Jahreszahlen
        for year in range(current_year - 2, current_year + 1):
            if str(year) in text:
                recent_count += 1
                break

    return recent_count / len(findings) if findings else 0.0

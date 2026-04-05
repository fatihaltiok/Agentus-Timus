# tools/deep_research/tool.py (VERSION 8.0 - EVIDENCE ENGINE)
"""
Timus Deep Research v8.1 - Evidence Engine

NEUE FEATURES:
- These-Antithese-Synthese Framework für dialektische Analyse
- Quellenqualitätsbewertung (Autorität, Bias, Aktualität, Transparenz)
- Tiefe Fakten-Verifikation mit fact_corroborator Integration
- Druckreife Reports im wissenschaftlichen Stil
- Kritische Analyse & Limitationen
- Konfliktanalyse bei widersprüchlichen Befunden
- Executive Summary & Methodik-Dokumentation
- Claim -> Evidence -> Verdict
- Profile-aware Verifikation
- Runtime-Guardrails mit partial_research

AUTOR: Timus Development Team
DATUM: Januar 2026
"""

import asyncio
import html as html_module
import json
import logging
import mimetypes
import os
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
from dataclasses import asdict, dataclass, field
from enum import Enum
from dotenv import load_dotenv
import httpx
from openai import OpenAI, RateLimitError
from utils.openai_compat import prepare_openai_params
from agent.shared.json_utils import extract_json_robust
from orchestration.ephemeral_workers import WorkerTask, run_worker, run_worker_batch

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# V2 Tool-Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# Interne Imports
from tools.planner.planner_helpers import call_tool_internal
from tools.deep_research.research_contracts import (
    build_domain_scorecards,
    claim_is_on_topic,
    ClaimRecord,
    ClaimVerdict,
    EvidenceRecord,
    EvidenceStance,
    SourceType,
    build_source_record_from_legacy,
    compute_claim_verdict,
    extract_query_anchor_terms,
    infer_country_code,
    infer_domain_from_text,
    infer_source_type,
    is_german_state_affiliated_url,
    initial_research_contract,
    sort_claims_for_report,
    summarize_claims,
)
from tools.social_media_tool.client import (
    fetch_page_text_via_scrapingant,
    get_scrapingant_api_key,
    needs_scrapingant as social_media_needs_scrapingant,
)

# Numpy für Embeddings - optional
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# --- Setup ---
logger = logging.getLogger("deep_research_v5")
load_dotenv(override=True)

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

_QUERY_TERM_ALIASES: Dict[str, List[str]] = {
    "introspective": ["self-reflection", "reflection", "introspection"],
    "autonomous": ["autonomy", "agentic", "planning"],
    "rag": ["retrieval augmented generation", "vector search"],
    "llm": ["large language model", "foundation model"],
    "llms": ["large language models", "foundation models"],
    "agent": ["agentic", "tool use", "workflow"],
    "agents": ["agentic", "tool use", "multi agent"],
    "agenten": ["agentic", "tool use", "multi agent"],
    "tool": ["tool use", "function calling"],
    "tools": ["tool use", "function calling"],
    "benchmark": ["evaluation", "leaderboard"],
    "benchmarks": ["evaluation", "leaderboard"],
}

_GENERIC_ADMIN_RESULT_TERMS = {
    "contact", "contacts", "address", "email", "telefon", "telefonnummer",
    "kontakt", "impressum", "careers", "career", "jobs", "job", "salary",
    "gehalt", "pricing", "price", "preise", "signup", "sign up", "register",
    "registration", "login", "download", "coupon", "discount", "support",
    "customer service", "faq",
}
_TOPIC_ADMIN_PATTERNS = tuple(sorted(_GENERIC_ADMIN_RESULT_TERMS))

_BROAD_SCOPE_MARKERS = {
    "latest", "developments", "trends", "trend", "landscape", "ecosystem", "overview",
    "future", "state", "state-of-the-art", "roadmap", "survey", "report", "developments",
    "status", "outlook", "entwicklung", "entwicklungen", "ueberblick", "lagebild",
    "forschung", "research", "future", "2025", "2026",
}

_SPECIFIC_SCOPE_HINTS = {
    "deepseek", "qwen", "claude", "gpt", "gemini", "llama", "mistral", "kimi",
    "rag", "regulation", "policy", "compliance", "benchmark", "benchmarks",
}

_LANDSCAPE_TECH_TERMS = {
    "agent", "agents", "agentic", "reasoning", "evaluation", "benchmark", "benchmarks",
    "architecture", "autonomy", "autonomous", "planning", "planner", "planer", "runtime",
    "safety", "alignment", "governance", "tool", "tools", "workflow", "model",
    "models", "retrieval", "generation", "rag", "context", "vector", "embedding",
    "orchestration", "orchestrierung",
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


def _artifact_type_for_path(path: str) -> str:
    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if suffix in {".md", ".txt", ".doc", ".docx"}:
        return "document"
    if suffix in {".csv", ".xlsx"}:
        return "data"
    return "file"


def _build_report_artifacts(*paths: Optional[str]) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        if not path:
            continue
        resolved = os.path.abspath(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        mime_type = mimetypes.guess_type(resolved)[0] or "application/octet-stream"
        artifacts.append({
            "type": _artifact_type_for_path(resolved),
            "path": resolved,
            "label": os.path.basename(resolved),
            "mime": mime_type,
            "source": "deep_research",
            "origin": "tool",
        })
    return artifacts


def _normalize_claim_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    normalized = re.sub(r"[\"'`“”‘’]", "", normalized)
    return normalized


def _merge_claim_notes(left: str, right: str) -> str:
    parts: List[str] = []
    seen: set[str] = set()
    for raw in (left, right):
        for part in str(raw or "").split(";"):
            token = part.strip()
            if not token or token in seen:
                continue
            seen.add(token)
            parts.append(token)
    return "; ".join(parts)


def _prefer_claim_record(current: "ClaimRecord", candidate: "ClaimRecord") -> "ClaimRecord":
    current_supports = len(set(current.supports))
    candidate_supports = len(set(candidate.supports))
    current_unknowns = len(current.unknowns)
    candidate_unknowns = len(candidate.unknowns)
    current_legacy = "legacy_status=" in str(current.notes or "")
    candidate_legacy = "legacy_status=" in str(candidate.notes or "")

    if candidate.claim_type == "verified_fact" and current.claim_type != "verified_fact":
        return candidate
    if current.claim_type == "verified_fact" and candidate.claim_type != "verified_fact":
        return current
    if candidate_supports > current_supports:
        return candidate
    if current_supports > candidate_supports:
        return current
    if candidate_unknowns < current_unknowns:
        return candidate
    if current_unknowns < candidate_unknowns:
        return current
    if current_legacy and not candidate_legacy:
        return candidate
    return current


def _dedupe_contract_claims(claims: List["ClaimRecord"]) -> List["ClaimRecord"]:
    deduped: Dict[str, "ClaimRecord"] = {}
    order: List[str] = []

    for claim in claims:
        key = _normalize_claim_text(claim.claim_text)
        if not key:
            continue
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = claim
            order.append(key)
            continue

        preferred = _prefer_claim_record(existing, claim)
        other = claim if preferred is existing else existing
        preferred.supports = list(dict.fromkeys([*preferred.supports, *other.supports]))
        preferred.contradicts = list(dict.fromkeys([*preferred.contradicts, *other.contradicts]))
        preferred.unknowns = list(dict.fromkeys([*preferred.unknowns, *other.unknowns]))
        preferred.notes = _merge_claim_notes(preferred.notes, other.notes)
        deduped[key] = preferred

    return [deduped[key] for key in order]


def _claim_token_set(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-\+\.]*", _normalize_claim_text(text))
        if len(token) >= 4 and not re.fullmatch(r"20\d{2}", token)
    }


def _claim_semantic_signature(claims: List["ClaimRecord"]) -> str:
    return "||".join(sorted(_normalize_claim_text(claim.claim_text) for claim in claims if claim.claim_text))


def _semantic_dedupe_confidence_threshold() -> float:
    raw = os.getenv("DR_WORKER_SEMANTIC_DEDUPE_CONFIDENCE_THRESHOLD", "0.85")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.85
    return min(max(value, 0.0), 1.0)


def _semantic_dedupe_chunk_size() -> int:
    raw = os.getenv("DR_WORKER_SEMANTIC_DEDUPE_CHUNK_SIZE", "10")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 10
    return max(4, min(value, 20))


def _semantic_dedupe_chunk_overlap() -> int:
    raw = os.getenv("DR_WORKER_SEMANTIC_DEDUPE_CHUNK_OVERLAP", "2")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 2
    return max(0, min(value, 5))


def _worker_semantic_dedupe_enabled() -> bool:
    return os.getenv("DR_WORKER_SEMANTIC_DEDUPE_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _worker_conflict_scan_enabled() -> bool:
    return os.getenv("DR_WORKER_CONFLICT_SCAN_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _conflict_scan_confidence_threshold() -> float:
    raw = os.getenv("DR_WORKER_CONFLICT_SCAN_CONFIDENCE_THRESHOLD", "0.83")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.83
    return min(max(value, 0.0), 1.0)


def _claim_report_signal_score(claim: Dict[str, Any]) -> tuple[int, int, int, int, float]:
    verdict = str(claim.get("verdict") or "")
    unknowns = claim.get("unknowns") or []
    contradicts = claim.get("contradicts") or []
    risk = 0
    if verdict in {ClaimVerdict.CONTESTED.value, ClaimVerdict.MIXED_EVIDENCE.value}:
        risk = 3
    elif unknowns or contradicts:
        risk = 2
    elif verdict == ClaimVerdict.LIKELY.value:
        risk = 1
    return (
        risk,
        len(contradicts),
        len(unknowns),
        len(claim.get("supports") or []),
        float(claim.get("confidence") or 0.0),
    )


def _build_conflict_scan_input(session: "DeepResearchSession") -> Dict[str, Any]:
    export = session.export_contract_v2()
    claims = list(export.get("claims") or [])
    relevant_claims = [
        claim for claim in claims
        if str(claim.get("claim_type") or "") in {"verified_fact", "runtime_fact_group"}
        and (
            str(claim.get("verdict") or "") in {
                ClaimVerdict.LIKELY.value,
                ClaimVerdict.CONTESTED.value,
                ClaimVerdict.MIXED_EVIDENCE.value,
            }
            or bool(claim.get("unknowns"))
            or bool(claim.get("contradicts"))
        )
    ]
    selected_claims = sorted(
        relevant_claims,
        key=_claim_report_signal_score,
        reverse=True,
    )[:15]
    conflicting_info = [
        {
            "fact": str(item.get("fact") or "").strip(),
            "note": str(item.get("note") or "").strip(),
            "internal_confidence": float(item.get("internal_confidence") or 0.0),
            "corroborator_confidence": float(item.get("corroborator_confidence") or 0.0),
        }
        for item in list(session.conflicting_info or [])[:8]
        if str(item.get("fact") or "").strip() or str(item.get("note") or "").strip()
    ]
    unknown_pool: List[str] = []
    for claim in selected_claims:
        for item in claim.get("unknowns") or []:
            text = _normalize_space(str(item or ""))
            if text:
                unknown_pool.append(text)
    for item in export.get("open_questions") or []:
        text = _normalize_space(str(item or ""))
        if text:
            unknown_pool.append(text)
    open_questions = _unique_texts(unknown_pool)[:6]

    return {
        "query": session.query,
        "focus_areas": list(session.focus_areas or []),
        "scope_mode": _ensure_research_plan(session).scope_mode,
        "claims": [
            {
                "claim_text": str(claim.get("claim_text") or ""),
                "verdict": str(claim.get("verdict") or ""),
                "confidence": float(claim.get("confidence") or 0.0),
                "supports_count": len(claim.get("supports") or []),
                "contradicts_count": len(claim.get("contradicts") or []),
                "unknowns": list(claim.get("unknowns") or [])[:4],
                "notes": str(claim.get("notes") or "")[:200],
            }
            for claim in selected_claims
        ],
        "conflicting_info": conflicting_info,
        "open_questions": open_questions,
    }


def _normalize_conflict_scan_payload(payload: Any) -> Dict[str, Any]:
    threshold = _conflict_scan_confidence_threshold()
    data = payload if isinstance(payload, dict) else {}

    conflicts_raw = data.get("conflicts")
    conflicts: List[Dict[str, Any]] = []
    if isinstance(conflicts_raw, list):
        for item in conflicts_raw:
            if not isinstance(item, dict):
                continue
            claim_text = _normalize_space(str(item.get("claim_text") or ""))
            issue_type = _normalize_space(str(item.get("issue_type") or ""))
            reason = _normalize_space(str(item.get("reason") or ""))
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < threshold:
                continue
            if not claim_text and not reason:
                continue
            conflicts.append(
                {
                    "claim_text": claim_text,
                    "issue_type": issue_type or "conflict",
                    "reason": reason,
                    "confidence": round(confidence, 4),
                }
            )

    weak_raw = data.get("weak_evidence_flags")
    weak_evidence_flags: List[Dict[str, Any]] = []
    if isinstance(weak_raw, list):
        for item in weak_raw:
            if not isinstance(item, dict):
                continue
            claim_text = _normalize_space(str(item.get("claim_text") or ""))
            reason = _normalize_space(str(item.get("reason") or ""))
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < threshold:
                continue
            if not claim_text and not reason:
                continue
            weak_evidence_flags.append(
                {
                    "claim_text": claim_text,
                    "reason": reason,
                    "confidence": round(confidence, 4),
                }
            )

    questions_raw = data.get("open_questions")
    open_questions: List[str] = []
    if isinstance(questions_raw, list):
        open_questions = _unique_texts([str(item or "") for item in questions_raw])[:8]

    notes_raw = data.get("report_notes")
    report_notes: List[str] = []
    if isinstance(notes_raw, list):
        report_notes = _unique_texts([str(item or "") for item in notes_raw])[:6]

    return {
        "conflicts": conflicts[:6],
        "open_questions": open_questions[:8],
        "weak_evidence_flags": weak_evidence_flags[:6],
        "report_notes": report_notes[:6],
    }


def _get_conflict_scan_report_context(session: "DeepResearchSession") -> Dict[str, Any]:
    meta = session.research_metadata.get("conflict_scan_worker", {})
    if not isinstance(meta, dict) or meta.get("status") != "ok":
        return {
            "conflicts": [],
            "open_questions": [],
            "weak_evidence_flags": [],
            "report_notes": [],
        }
    return {
        "conflicts": list(meta.get("conflicts") or []),
        "open_questions": list(meta.get("open_questions") or []),
        "weak_evidence_flags": list(meta.get("weak_evidence_flags") or []),
        "report_notes": list(meta.get("report_notes") or []),
    }


def _semantic_protected_term_hits(session: "DeepResearchSession", text: str) -> set[str]:
    plan = _ensure_research_plan(session)
    protected = _unique_texts(
        plan.must_have_terms + plan.anchor_terms + plan.focus_terms,
        lowercase=True,
    )
    text_lower = str(text or "").lower()
    return {term for term in protected if term in text_lower}


def _semantic_claim_overlap_ok(left_text: str, right_text: str) -> bool:
    left_norm = _normalize_claim_text(left_text)
    right_norm = _normalize_claim_text(right_text)
    if not left_norm or not right_norm:
        return False
    if left_norm in right_norm or right_norm in left_norm:
        return True
    left_tokens = _claim_token_set(left_norm)
    right_tokens = _claim_token_set(right_norm)
    if not left_tokens or not right_tokens:
        return False
    shared = len(left_tokens & right_tokens)
    coverage = shared / max(1, min(len(left_tokens), len(right_tokens)))
    return coverage >= 0.6


def _semantic_merge_protected_terms_ok(
    session: "DeepResearchSession",
    left_text: str,
    right_text: str,
) -> bool:
    left_hits = _semantic_protected_term_hits(session, left_text)
    right_hits = _semantic_protected_term_hits(session, right_text)
    if not left_hits or not right_hits:
        return True
    return left_hits.issubset(right_hits) or right_hits.issubset(left_hits)


def _filter_semantic_merge_candidates(
    session: "DeepResearchSession",
    claims: List["ClaimRecord"],
    merge_candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    threshold = _semantic_dedupe_confidence_threshold()
    claims_by_key = {
        _normalize_claim_text(claim.claim_text): claim for claim in claims if _normalize_claim_text(claim.claim_text)
    }
    accepted: List[Dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for candidate in merge_candidates:
        if not isinstance(candidate, dict):
            continue
        left_text = str(candidate.get("left_claim_text") or "").strip()
        right_text = str(candidate.get("right_claim_text") or "").strip()
        reason = _normalize_space(str(candidate.get("reason") or ""))
        try:
            confidence = float(candidate.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        left_key = _normalize_claim_text(left_text)
        right_key = _normalize_claim_text(right_text)
        if not left_key or not right_key or left_key == right_key:
            continue
        if confidence < threshold:
            continue
        if left_key not in claims_by_key or right_key not in claims_by_key:
            continue
        if not _semantic_claim_overlap_ok(left_text, right_text):
            continue
        if not _semantic_merge_protected_terms_ok(session, left_text, right_text):
            continue
        pair = tuple(sorted((left_key, right_key)))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        accepted.append(
            {
                "left_claim_text": claims_by_key[left_key].claim_text,
                "right_claim_text": claims_by_key[right_key].claim_text,
                "confidence": round(confidence, 4),
                "reason": reason,
            }
        )
    return accepted


def _merge_claim_record_group(claims: List["ClaimRecord"]) -> "ClaimRecord":
    merged = claims[0]
    for candidate in claims[1:]:
        preferred = _prefer_claim_record(merged, candidate)
        other = candidate if preferred is merged else merged
        preferred.supports = list(dict.fromkeys([*preferred.supports, *other.supports]))
        preferred.contradicts = list(dict.fromkeys([*preferred.contradicts, *other.contradicts]))
        preferred.unknowns = list(dict.fromkeys([*preferred.unknowns, *other.unknowns]))
        preferred.notes = _merge_claim_notes(preferred.notes, other.notes)
        preferred.confidence = max(float(preferred.confidence or 0.0), float(other.confidence or 0.0))
        if not preferred.time_scope and other.time_scope:
            preferred.time_scope = other.time_scope
        merged = preferred
    return merged


def _apply_semantic_merge_candidates(
    claims: List["ClaimRecord"],
    merge_candidates: List[Dict[str, Any]],
) -> List["ClaimRecord"]:
    if not claims or not merge_candidates:
        return claims

    claims_by_key = {
        _normalize_claim_text(claim.claim_text): claim for claim in claims if _normalize_claim_text(claim.claim_text)
    }
    parent = {key: key for key in claims_by_key}

    def _find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def _union(left: str, right: str) -> None:
        left_root = _find(left)
        right_root = _find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for candidate in merge_candidates:
        left_key = _normalize_claim_text(candidate.get("left_claim_text", ""))
        right_key = _normalize_claim_text(candidate.get("right_claim_text", ""))
        if left_key in parent and right_key in parent and left_key != right_key:
            _union(left_key, right_key)

    grouped: Dict[str, List["ClaimRecord"]] = {}
    for key, claim in claims_by_key.items():
        grouped.setdefault(_find(key), []).append(claim)

    ordered_keys = [_normalize_claim_text(claim.claim_text) for claim in claims if _normalize_claim_text(claim.claim_text)]
    emitted_roots: set[str] = set()
    result: List["ClaimRecord"] = []

    for key in ordered_keys:
        root = _find(key)
        if root in emitted_roots:
            continue
        emitted_roots.add(root)
        cluster = grouped.get(root, [])
        if not cluster:
            continue
        result.append(_merge_claim_record_group(cluster))
    return result


def _build_narrative_fallback_report(session: "DeepResearchSession") -> str:
    query = str(session.query or "Recherchethema").strip()
    plan = _ensure_research_plan(session)
    verified = list(session.verified_facts or [])
    unverified = list(session.unverified_claims or [])
    syntheses = [analysis for analysis in (session.thesis_analyses or []) if analysis.synthesis]

    lines: List[str] = [
        "## Einordnung",
        f"Diese Recherche behandelt das Thema **{query}**.",
        (
            "Der folgende Bericht ist ein deterministischer Fallback, weil die freie Narrative-Synthese "
            "leer oder unvollständig geblieben ist. Er fasst die belastbarsten Punkte aus den "
            "gesammelten Quellen in lesbarer Form zusammen."
        ),
        (
            f"In der aktuellen Session wurden {len(session.research_tree)} Web-Quellen, "
            f"{len(verified)} verifizierte Fakten und {len(unverified)} weitere Hinweise verarbeitet."
        ),
        "",
        "## Rechercheplan",
        f"Leitfrage: {plan.primary_question}",
        f"Muss-Begriffe: {', '.join(plan.must_have_terms[:6]) or '-'}",
        f"Teilfragen: {' | '.join(plan.subquestions[:3])}",
        "",
        "## Belastbare Beobachtungen",
    ]

    if verified:
        for idx, fact in enumerate(verified[:8], start=1):
            fact_text = str(fact.get("fact") or "").strip()
            if not fact_text:
                continue
            source_count = int(fact.get("source_count") or 0)
            source_hint = f" (beobachtet in {source_count} Quelle{'n' if source_count != 1 else ''})" if source_count else ""
            lines.append(f"{idx}. {fact_text}{source_hint}.")
    else:
        lines.append(
            "Es liegen derzeit keine mehrfach bestätigten Fakten vor. Die Recherche liefert daher vor allem "
            "vorsichtige Hinweise statt harter, breit abgesicherter Aussagen."
        )

    lines.extend([
        "",
        "## Hinweise und offene Punkte",
    ])
    if unverified:
        for idx, claim in enumerate(unverified[:8], start=1):
            claim_text = str(claim.get("fact") or "").strip()
            if not claim_text:
                continue
            source_type = str(claim.get("source_type") or "web")
            lines.append(f"{idx}. {claim_text} Diese Aussage stammt aktuell aus dem Typ `{source_type}` und ist noch nicht breit bestätigt.")
    else:
        lines.append("Neben den verifizierten Fakten liegen derzeit keine zusätzlichen unbestätigten Hinweise vor.")

    lines.extend([
        "",
        "## Analytische Verdichtung",
    ])
    if syntheses:
        for analysis in syntheses[:4]:
            topic = str(analysis.topic or "Thema").strip()
            synthesis = str(analysis.synthesis or "").strip()
            if synthesis:
                lines.append(f"### {topic}")
                lines.append(synthesis)
                if analysis.limitations:
                    lines.append(
                        "Grenzen: " + "; ".join(str(item).strip() for item in analysis.limitations if str(item).strip())
                    )
                lines.append("")
    else:
        lines.append(
            "Die Quellensynthese liefert noch kein stabiles, mehrperspektivisches Bild fuer alle Teilaspekte. "
            "Das ist typisch, wenn das Thema breit formuliert ist oder die Quellenlage je Teilfrage stark schwankt."
        )
        lines.append(
            "Besonders bei Modellfähigkeiten, Tool-Use und Multi-Agent-Support sollte deshalb zwischen "
            "Produktankündigungen, Paper-Ergebnissen und unabhängigen Benchmarks getrennt werden."
        )

    lines.extend([
        "## Fazit",
        (
            "Als lesbarer Gesamtstand zeigt diese Recherche, welche Punkte bereits greifbar belegt sind "
            "und an welchen Stellen noch Verdichtung oder Nachverifikation fehlt."
        ),
        (
            "Für Entscheidungen oder externe Weitergabe sollte man primär die bestätigten Fakten und die "
            "klar benannten Unsicherheiten verwenden, statt unbestätigte Einzelclaims zu überziehen."
        ),
        "",
        "## Quellenhinweise",
    ])
    if session.research_tree:
        for idx, node in enumerate(session.research_tree[:12], start=1):
            title = str(node.title or node.url or f"Quelle {idx}").strip()
            url = str(node.url or "").strip()
            lines.append(f"{idx}. {title} — {url}")
    else:
        lines.append("1. Keine strukturierten Web-Quellen in der Session vorhanden.")

    return "\n".join(lines).strip()


def _narrative_word_count(text: str) -> int:
    return len(re.findall(r"\w+", str(text or ""), flags=re.UNICODE))


def _trim_narrative_text(value: Any, max_chars: int = 320) -> str:
    text = _normalize_space(str(value or ""))
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rsplit(" ", 1)[0].strip()
    return f"{clipped}..." if clipped else text[:max_chars]


def _build_narrative_source_entries(session: "DeepResearchSession", limit: int = 16) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    seen_urls: set[str] = set()

    def _add(title: str, url: str) -> None:
        cleaned_url = str(url or "").strip()
        if not cleaned_url or cleaned_url in seen_urls:
            return
        seen_urls.add(cleaned_url)
        cleaned_title = _normalize_space(str(title or cleaned_url))
        entries.append((cleaned_title, cleaned_url))

    for node in list(session.research_tree or []):
        _add(getattr(node, "title", "") or getattr(node, "url", ""), getattr(node, "url", ""))
        if len(entries) >= limit:
            return entries

    supplemental_claims = sorted(
        list(session.unverified_claims or []),
        key=lambda claim: (
            int(claim.get("source_count") or 0),
            float(claim.get("confidence_score_numeric") or claim.get("confidence_score") or 0.0),
        ),
        reverse=True,
    )
    for claim in supplemental_claims:
        _add(claim.get("source_title") or claim.get("fact") or claim.get("source"), claim.get("source"))
        if len(entries) >= limit:
            break
    return entries


def _render_narrative_sources_section(session: "DeepResearchSession", limit: int = 16) -> str:
    lines = ["## Quellenhinweise"]
    entries = _build_narrative_source_entries(session, limit=limit)
    if not entries:
        lines.append("1. Keine strukturierten Quellen in der Session vorhanden.")
        return "\n".join(lines).strip()

    for idx, (title, url) in enumerate(entries, start=1):
        lines.append(f"{idx}. {title} — {url}")
    return "\n".join(lines).strip()


def _build_narrative_digest(session: "DeepResearchSession") -> Dict[str, Any]:
    plan = _ensure_research_plan(session)

    verified_candidates = [
        fact for fact in list(session.verified_facts or [])
        if _is_text_on_session_topic(session, str(fact.get("fact") or ""))
    ] or list(session.verified_facts or [])
    verified_candidates = sorted(
        verified_candidates,
        key=lambda fact: (
            int(fact.get("source_count") or 0),
            float(fact.get("confidence_score_numeric") or fact.get("confidence_score") or 0.0),
        ),
        reverse=True,
    )

    verified_lines: List[str] = []
    for idx, fact in enumerate(verified_candidates[:12], start=1):
        fact_text = _trim_narrative_text(fact.get("fact", ""), 320)
        if not fact_text:
            continue
        source_count = int(fact.get("source_count") or 0)
        quote = ""
        quotes = fact.get("supporting_quotes") or []
        if quotes:
            quote = _trim_narrative_text(quotes[0], 160)
        suffix_bits = []
        if source_count:
            suffix_bits.append(f"Quellen={source_count}")
        confidence = fact.get("confidence_score_numeric") or fact.get("confidence_score")
        if confidence not in (None, ""):
            try:
                suffix_bits.append(f"Confidence={float(confidence):.2f}")
            except Exception:
                pass
        suffix = f" ({', '.join(suffix_bits)})" if suffix_bits else ""
        quote_suffix = f' | Zitat: "{quote}"' if quote else ""
        verified_lines.append(f"{idx}. {fact_text}{suffix}{quote_suffix}")

    unverified_candidates = [
        claim for claim in list(session.unverified_claims or [])
        if _is_text_on_session_topic(session, str(claim.get("fact") or ""))
    ] or list(session.unverified_claims or [])
    unverified_candidates = sorted(
        unverified_candidates,
        key=lambda claim: (
            int(claim.get("source_count") or 0),
            float(claim.get("confidence_score_numeric") or claim.get("confidence_score") or 0.0),
        ),
        reverse=True,
    )

    unverified_lines: List[str] = []
    for idx, claim in enumerate(unverified_candidates[:10], start=1):
        claim_text = _trim_narrative_text(claim.get("fact", ""), 320)
        if not claim_text:
            continue
        source_type = str(claim.get("source_type") or "web").strip()
        source_count = int(claim.get("source_count") or 0)
        suffix_bits = [f"Typ={source_type}"]
        if source_count:
            suffix_bits.append(f"Quellen={source_count}")
        unverified_lines.append(f"{idx}. {claim_text} ({', '.join(suffix_bits)})")

    synthesis_lines: List[str] = []
    for idx, analysis in enumerate(list(session.thesis_analyses or [])[:5], start=1):
        synthesis = _trim_narrative_text(getattr(analysis, "synthesis", ""), 520)
        topic = _trim_narrative_text(getattr(analysis, "topic", ""), 120)
        if not synthesis:
            continue
        if topic and _is_text_on_session_topic(session, f"{topic} {synthesis}") is False:
            continue
        limitations = [
            _trim_narrative_text(item, 180)
            for item in list(getattr(analysis, "limitations", []) or [])[:2]
            if _trim_narrative_text(item, 180)
        ]
        limit_suffix = f" | Grenzen: {'; '.join(limitations)}" if limitations else ""
        synthesis_lines.append(f"{idx}. {topic or 'Synthese'}: {synthesis}{limit_suffix}")

    source_lines: List[str] = []
    for idx, (title, url) in enumerate(_build_narrative_source_entries(session, limit=10), start=1):
        source_lines.append(f"{idx}. {title} | {url}")

    conflict_meta = session.research_metadata.get("conflict_scan_worker", {})
    conflict_lines: List[str] = []
    for idx, conflict in enumerate(list(conflict_meta.get("conflicts") or [])[:6], start=1):
        claim_text = _trim_narrative_text(conflict.get("claim_text", ""), 220)
        reason = _trim_narrative_text(conflict.get("reason", ""), 200)
        issue_type = _trim_narrative_text(conflict.get("issue_type", ""), 80)
        if claim_text:
            conflict_lines.append(f"{idx}. {claim_text} | issue={issue_type} | {reason}")

    open_questions = [
        _trim_narrative_text(item, 200)
        for item in list(conflict_meta.get("open_questions") or [])[:6]
        if _trim_narrative_text(item, 200)
    ]
    report_notes = [
        _trim_narrative_text(item, 220)
        for item in list(conflict_meta.get("report_notes") or [])[:6]
        if _trim_narrative_text(item, 220)
    ]

    stats_text = (
        f"Web-Quellen={len(session.research_tree)} | "
        f"verifizierte Fakten={len(session.verified_facts)} | "
        f"weitere Hinweise={len(session.unverified_claims)} | "
        f"These-Antithese-Synthesen={len(session.thesis_analyses)}"
    )
    plan_text = (
        f"Leitfrage: {plan.primary_question}\n"
        f"Scope-Modus: {plan.scope_mode}\n"
        f"Muss-Begriffe: {', '.join(plan.must_have_terms[:6]) or '-'}\n"
        f"Teilfragen: {' | '.join(plan.subquestions[:4]) or '-'}\n"
        f"Topic-Boundaries: {' | '.join(plan.topic_boundaries[:3]) or '-'}"
    )

    return {
        "plan_text": plan_text,
        "stats_text": stats_text,
        "verified_lines": verified_lines,
        "unverified_lines": unverified_lines,
        "synthesis_lines": synthesis_lines,
        "source_lines": source_lines,
        "conflict_lines": conflict_lines,
        "open_questions": open_questions,
        "report_notes": report_notes,
        "sources_section": _render_narrative_sources_section(session),
    }


async def _call_narrative_llm(prompt: str, max_tokens: int, temperature: float = 0.35) -> str:
    kwargs = {
        "model": SMART_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    kwargs = prepare_openai_params(kwargs)
    response = await asyncio.to_thread(client.chat.completions.create, **kwargs)
    return str(response.choices[0].message.content or "").strip()


def _normalize_narrative_section(title: str, text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:markdown)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = re.sub(r"^\s*#\s+.+?\n+", "", cleaned, count=1)
    cleaned = re.sub(r"^\s*##\s+.+?\n+", "", cleaned, count=1)
    cleaned = re.split(r"\n##\s+", cleaned, maxsplit=1)[0].strip()
    cleaned = re.sub(r"\n##\s+Quellenhinweise[\s\S]*$", "", cleaned).strip()
    if not cleaned:
        return ""
    return f"## {title}\n\n{cleaned}".strip()


async def _generate_narrative_section(
    session: "DeepResearchSession",
    title: str,
    digest: Dict[str, Any],
    material_keys: List[str],
    guidance: str,
    target_words: Tuple[int, int],
    max_tokens: int,
) -> str:
    material_blocks: List[str] = []
    for key in material_keys:
        value = digest.get(key)
        if isinstance(value, list) and value:
            label = key.replace("_", " ").upper()
            material_blocks.append(f"{label}:\n" + "\n".join(f"- {item}" for item in value))
        elif isinstance(value, str) and value.strip():
            label = key.replace("_", " ").upper()
            material_blocks.append(f"{label}:\n{value.strip()}")

    if not material_blocks:
        return ""

    prompt = f"""Du schreibst einen einzelnen Abschnitt fuer einen deutschsprachigen Deep-Research-Bericht.

THEMA: {session.query}
ABSCHNITT: {title}

RECHERCHEPLAN:
{digest.get("plan_text", "").strip()}

RELEVANTES MATERIAL:
{chr(10).join(material_blocks)}

ANWEISUNG:
- Schreibe nur den Abschnitt `## {title}`
- Umfang: ca. {target_words[0]} bis {target_words[1]} Woerter
- Nur Material verwenden, das im Input steht
- Off-Topic-Hinweise weglassen
- Wenn Evidenz duenn oder widerspruechlich ist, das klar benennen
- Keine Quellenliste und kein Meta-Kommentar
- Ganze Saetze und gut lesbare Absaetze, keine Bullet-Listen

FOKUS:
{guidance}
"""

    try:
        section = await _call_narrative_llm(prompt, max_tokens=max_tokens, temperature=0.35)
    except Exception as exc:
        logger.warning("Narrative-Abschnitt %s fehlgeschlagen: %s", title, exc)
        return ""
    return _normalize_narrative_section(title, section)


def _is_narrative_readable(section_texts: List[str]) -> bool:
    if len(section_texts) < 3:
        return False
    combined = "\n\n".join(section_texts).strip()
    if _narrative_word_count(combined) < 150:
        return False
    return "## Einordnung" in combined and "## Fazit" in combined


async def _create_compact_narrative_retry(
    session: "DeepResearchSession",
    digest: Dict[str, Any],
    section_drafts: Dict[str, str],
) -> str:
    successful_drafts = [text for text in section_drafts.values() if text]
    draft_block = "\n\n".join(successful_drafts[:4]).strip()

    material_blocks = [
        f"RECHERCHEPLAN:\n{digest.get('plan_text', '').strip()}",
        f"STATISTIK:\n{digest.get('stats_text', '').strip()}",
    ]
    for key in ("verified_lines", "unverified_lines", "synthesis_lines", "conflict_lines", "open_questions", "report_notes"):
        items = digest.get(key) or []
        if items:
            label = key.replace("_", " ").upper()
            material_blocks.append(f"{label}:\n" + "\n".join(f"- {item}" for item in items))
    if draft_block:
        material_blocks.append(f"BISHERIGE ABSCHNITTSENTWUERFE:\n{draft_block}")

    prompt = f"""Du erstellst einen lesbaren Deep-Research-Bericht auf Deutsch.

THEMA: {session.query}

{chr(10).join(material_blocks)}

AUFGABE:
Forme daraus einen kompakten, aber zusammenhaengenden Lesebericht mit genau diesen Ueberschriften:
- ## Einordnung
- ## Belastbare Beobachtungen
- ## Hinweise und offene Punkte
- ## Analytische Verdichtung
- ## Fazit

VORGABEN:
- Nutze nur Material aus dem Input
- Off-Topic-Hinweise weglassen
- Widersprueche und Unsicherheiten klar benennen
- Kein Quellenverzeichnis, das wird spaeter deterministisch angehaengt
- Keine Meta-Hinweise auf den Schreibprozess
- Ziel: 900 bis 1800 Woerter
"""

    try:
        narrative = await _call_narrative_llm(prompt, max_tokens=2600, temperature=0.35)
    except Exception as exc:
        logger.warning("Narrative-Kompakt-Retry fehlgeschlagen: %s", exc)
        return ""

    cleaned = str(narrative or "").strip()
    cleaned = re.sub(r"^```(?:markdown)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = re.sub(r"^\s*#\s+.+?\n+", "", cleaned, count=1)
    cleaned = re.sub(r"\n##\s+Quellenhinweise[\s\S]*$", "", cleaned).strip()
    return cleaned


def _compose_pdf_markdown(narrative_content: str, academic_content: str) -> str:
    narrative = str(narrative_content or "").strip()
    academic = str(academic_content or "").strip()
    narrative_is_readable = bool(narrative) and "0 Wörter" not in narrative and len(narrative.split()) >= 120

    if narrative_is_readable and academic:
        trimmed_academic = re.sub(r"^# .+?\n", "", academic, count=1).strip()
        return (
            f"{narrative}\n\n"
            "## Analytischer Anhang\n\n"
            "Die folgenden Abschnitte enthalten den strukturierten, analytischen Tiefenbericht "
            "mit Claim-Register, Methodik und Scorecards.\n\n"
            f"{trimmed_academic}"
        ).strip()
    if narrative:
        return narrative
    return academic


def _build_research_pdf(
    content: str,
    images: List[Any],
    session: "DeepResearchSession",
    output_dir: str,
    session_id: str,
    require_pdf: bool = True,
) -> Optional[str]:
    """Erstellt den PDF-Artefaktpfad strikt oder tolerant.

    Wenn `require_pdf=True`, wird bei fehlgeschlagener PDF-Erstellung eine Exception
    geworfen statt den Fehler still zu schlucken.
    """
    pdf_enabled = os.getenv("DEEP_RESEARCH_PDF_ENABLED", "true").lower() == "true"
    if not pdf_enabled:
        if require_pdf:
            raise RuntimeError("PDF-Erstellung ist deaktiviert, aber require_pdf=True.")
        return None

    from pathlib import Path as _Path
    from tools.deep_research.pdf_builder import ResearchPDFBuilder

    pdf_path = str(_Path(output_dir) / f"DeepResearch_PDF_{session_id}.pdf")
    try:
        pdf_filepath = ResearchPDFBuilder().build_pdf(content, images, session, pdf_path)
    except Exception as exc:
        if require_pdf:
            raise RuntimeError(f"PDF-Erstellung fehlgeschlagen: {exc}") from exc
        logger.warning("PDF-Erstellung fehlgeschlagen (toleriert): %s", exc)
        return None

    if not pdf_filepath or not _Path(pdf_filepath).exists():
        message = f"PDF-Erstellung fehlgeschlagen: Kein gueltiger PDF-Artefaktpfad fuer Session {session_id}."
        if require_pdf:
            raise RuntimeError(message)
        logger.warning("%s", message)
        return None
    return str(_Path(pdf_filepath))


def _merge_report_images(
    base_images: List[Any],
    image_paths: Optional[List[str]] = None,
    image_captions: Optional[List[str]] = None,
    image_sections: Optional[List[str]] = None,
) -> List[Any]:
    merged = list(base_images or [])
    if not image_paths:
        return merged

    from tools.deep_research.image_collector import ImageResult

    captions = image_captions or []
    sections = image_sections or []
    for idx, raw_path in enumerate(image_paths):
        path = str(raw_path or "").strip()
        if not path:
            continue
        caption = (
            str(captions[idx]).strip()
            if idx < len(captions) and str(captions[idx]).strip()
            else f"Visual {idx + 1}"
        )
        section_title = (
            str(sections[idx]).strip()
            if idx < len(sections) and str(sections[idx]).strip()
            else caption
        )
        merged.append(
            ImageResult(
                local_path=path,
                caption=caption,
                section_title=section_title,
                source="creative",
            )
        )
    return merged


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
    independence_score: float = 0.5    # 0-1: Unabhängigkeit / Distanz zur betroffenen Partei
    bias_level: BiasLevel = BiasLevel.UNKNOWN
    bias_score: float = 0.0            # 0-1: 0=unbiased, 1=stark biased
    recency_score: float = 0.5         # 0-1: Aktualität
    transparency_score: float = 0.5    # 0-1: Autor/Methodik genannt
    citation_score: float = 0.5        # 0-1: Zitiert andere Quellen
    scope_fit_score: float = 0.5       # 0-1: Wie direkt zahlt die Quelle auf die Leitfrage ein
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


@dataclass
class ResearchPlan:
    """Deterministischer Rechercheplan fuer Query-Bildung und Topic-Gating."""

    primary_question: str
    query_language: str
    domain: str
    profile: str
    scope_mode: str = "strict"
    query_variants: List[str] = field(default_factory=list)
    focus_terms: List[str] = field(default_factory=list)
    anchor_terms: List[str] = field(default_factory=list)
    include_terms: List[str] = field(default_factory=list)
    must_have_terms: List[str] = field(default_factory=list)
    exclude_terms: List[str] = field(default_factory=list)
    related_terms: List[str] = field(default_factory=list)
    temporal_terms: List[str] = field(default_factory=list)
    preferred_source_types: List[str] = field(default_factory=list)
    subquestions: List[str] = field(default_factory=list)
    topic_boundaries: List[str] = field(default_factory=list)
    strict_topic: bool = True
    created_at: str = ""


class DeepResearchSession:
    """Verwaltet den Zustand einer Tiefenrecherche-Session (v5.0 erweitert)."""
    def __init__(
        self,
        query: str,
        focus_areas: Optional[List[str]] = None,
        scope_mode: Optional[str] = None,
    ):
        self.query = query
        self.focus_areas = focus_areas if focus_areas is not None else []
        self.requested_scope_mode = str(scope_mode or "auto").strip().lower() or "auto"
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
        self.research_plan: Optional[ResearchPlan] = None
        self.contract_v2 = initial_research_contract(query)

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

    def export_contract_v2(self) -> Dict[str, Any]:
        """Exportiert den neuen allgemeinen Research-Vertrag.

        Die Runtime hängt heute noch nicht vollständig an diesem Vertrag.
        Der Export dient als stabiler Migrationsanker für die nächsten Phasen.
        """
        if self.contract_v2 is None:
            self.contract_v2 = initial_research_contract(self.query)
        sources = []
        seen_urls: set[str] = set()

        for idx, node in enumerate(self.research_tree, start=1):
            canonical = self._get_canonical_url(node.url)
            if not canonical or canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            meta = {
                "has_methodology": (
                    bool(getattr(node, "quality_metrics", None))
                    and getattr(node.quality_metrics, "citation_score", 0.0) > 0.0
                ),
            }
            sources.append(
                build_source_record_from_legacy(
                    source_id=f"src-web-{idx}",
                    url=canonical,
                    title=node.title or canonical,
                    metadata=meta,
                )
            )

        for idx, claim in enumerate(self.unverified_claims, start=1):
            raw_url = str(claim.get("source") or "").strip()
            canonical = self._get_canonical_url(raw_url)
            if not canonical or canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            meta = {
                "is_official": bool(claim.get("is_official")),
                "has_transcript": bool(claim.get("transcript") or claim.get("key_quote")),
                "published_at": str(claim.get("published_date") or ""),
            }
            sources.append(
                build_source_record_from_legacy(
                    source_id=f"src-claim-{idx}",
                    url=canonical,
                    title=str(claim.get("source_title") or canonical),
                    declared_type=str(claim.get("source_type") or ""),
                    metadata=meta,
                )
            )

        existing_sources_by_id = {
            source.source_id: source for source in getattr(self.contract_v2, "sources", []) or []
        }
        for source in sources:
            existing_sources_by_id[source.source_id] = source
        self.contract_v2.sources = list(existing_sources_by_id.values())

        legacy_claims = self._build_contract_claims_v2(self.contract_v2.sources)
        existing_claims_by_id = {
            claim.claim_id: claim for claim in getattr(self.contract_v2, "claims", []) or []
        }
        for claim in legacy_claims:
            existing_claims_by_id.setdefault(claim.claim_id, claim)
        filtered_claims = _filter_session_claims(self, list(existing_claims_by_id.values()))
        self.contract_v2.claims = self._apply_cached_semantic_claim_dedupe(filtered_claims)

        legacy_evidences = self._build_contract_evidences_v2(self.contract_v2.claims, self.contract_v2.sources)
        existing_evidences_by_id = {
            evidence.evidence_id: evidence for evidence in getattr(self.contract_v2, "evidences", []) or []
        }
        for evidence in legacy_evidences:
            existing_evidences_by_id.setdefault(evidence.evidence_id, evidence)
        valid_claim_ids = {claim.claim_id for claim in self.contract_v2.claims}
        self.contract_v2.evidences = [
            evidence for evidence in existing_evidences_by_id.values()
            if evidence.claim_id in valid_claim_ids
        ]

        self._refresh_contract_v2_verdicts()
        self.contract_v2.open_questions = list(dict.fromkeys(self.limitations))
        return self.contract_v2.to_dict()

    def _refresh_contract_v2_verdicts(self) -> None:
        source_by_id = {source.source_id: source for source in self.contract_v2.sources}
        evidences_by_claim: Dict[str, List[EvidenceRecord]] = {}
        for evidence in self.contract_v2.evidences:
            evidences_by_claim.setdefault(evidence.claim_id, []).append(evidence)
        for claim in self.contract_v2.claims:
            claim_evidences = evidences_by_claim.get(claim.claim_id, [])
            claim.verdict = compute_claim_verdict(
                self.contract_v2.question.profile,
                claim_evidences,
                [source_by_id[e.source_id] for e in claim_evidences if e.source_id in source_by_id],
            )
            if claim.verdict == ClaimVerdict.CONFIRMED:
                claim.confidence = 0.9
            elif claim.verdict == ClaimVerdict.LIKELY:
                claim.confidence = 0.7
            elif claim.verdict == ClaimVerdict.VENDOR_CLAIM_ONLY:
                claim.confidence = 0.45
            elif claim.verdict == ClaimVerdict.CONTESTED:
                claim.confidence = 0.35
            elif claim.verdict == ClaimVerdict.MIXED_EVIDENCE:
                claim.confidence = 0.4
            else:
                claim.confidence = 0.2

    def _materialize_verification_claims_v2(
        self,
        grouped_facts: List[List[Dict[str, Any]]],
        verified: List[Dict[str, Any]],
        unverified: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
    ) -> None:
        source_records: Dict[str, Any] = {
            source.source_id: source for source in getattr(self.contract_v2, "sources", []) or []
        }
        claim_records: List[ClaimRecord] = []
        evidence_records: List[EvidenceRecord] = []
        source_id_by_url: Dict[str, str] = {}

        for idx, group in enumerate(grouped_facts, start=1):
            if not group:
                continue
            main_fact = group[0]
            fact_text = str(main_fact.get("fact") or "").strip()
            if not fact_text:
                continue

            candidate_output = next(
                (item for item in verified if item.get("fact") == fact_text),
                None,
            )
            if candidate_output is None:
                candidate_output = next(
                    (item for item in unverified if item.get("fact") == fact_text),
                    None,
                )

            claim_id = f"claim-runtime-{idx}"
            claim = ClaimRecord(
                claim_id=claim_id,
                question_id=self.contract_v2.question.question_id,
                domain=infer_domain_from_text(fact_text),
                subject=self.query[:120],
                claim_text=fact_text,
                claim_type="runtime_fact_group",
                notes=f"source_count={len({f.get('source_url') for f in group if f.get('source_url')})}",
            )
            if not _filter_session_claims(self, [claim]):
                continue

            if candidate_output and candidate_output.get("status") == "verified_multiple_methods":
                claim.confidence = 0.95
            elif candidate_output and candidate_output.get("status") in {"verified", "tentatively_verified"}:
                claim.confidence = float(candidate_output.get("confidence_score_numeric", 0.7))
            else:
                claim.confidence = 0.2

            for ev_idx, fact in enumerate(group, start=1):
                raw_url = str(fact.get("source_url") or "").strip()
                canonical = self._get_canonical_url(raw_url)
                if not canonical:
                    continue
                source_id = source_id_by_url.get(canonical)
                if not source_id:
                    source_id = f"src-runtime-{idx}-{ev_idx}"
                    source_id_by_url[canonical] = source_id
                    source_records[source_id] = build_source_record_from_legacy(
                        source_id=source_id,
                        url=canonical,
                        title=str(fact.get("source_title") or canonical),
                        declared_type=str(fact.get("source_type") or ""),
                        metadata={
                            "has_methodology": True,
                            "published_at": str(fact.get("published_date") or ""),
                        },
                    )
                claim.supports.append(source_id)
                evidence_records.append(
                    EvidenceRecord(
                        evidence_id=f"ev-runtime-{idx}-{ev_idx}",
                        claim_id=claim_id,
                        source_id=source_id,
                        stance=EvidenceStance.SUPPORTS,
                        excerpt=str(fact.get("source_quote") or fact_text[:280]),
                        notes=claim.notes,
                    )
                )

            claim_records.append(claim)

        for idx, conflict in enumerate(conflicts, start=1):
            fact_text = str(conflict.get("fact") or "").strip()
            if not fact_text:
                continue
            matching = next((claim for claim in claim_records if claim.claim_text == fact_text), None)
            if matching is None:
                continue
            conflict_source_id = f"src-conflict-{idx}"
            source_records[conflict_source_id] = build_source_record_from_legacy(
                source_id=conflict_source_id,
                url=f"https://timus.local/conflicts/{idx}",
                title=f"Verification conflict #{idx}",
                declared_type="analysis",
                metadata={"has_methodology": True},
            )
            matching.contradicts.append(conflict_source_id)
            matching.unknowns.append("Konflikt zwischen Verifikationsmethoden")
            matching.notes = (matching.notes + f"; conflict_{idx}=confidence_disagreement").strip("; ")
            evidence_records.append(
                EvidenceRecord(
                    evidence_id=f"ev-conflict-{idx}",
                    claim_id=matching.claim_id,
                    source_id=conflict_source_id,
                    stance=EvidenceStance.CONTRADICTS,
                    excerpt=str(conflict.get("note") or "Verification conflict"),
                )
            )

        self.contract_v2.sources = list(source_records.values())
        self.contract_v2.claims = _filter_session_claims(self, claim_records)
        valid_claim_ids = {claim.claim_id for claim in self.contract_v2.claims}
        self.contract_v2.evidences = [evidence for evidence in evidence_records if evidence.claim_id in valid_claim_ids]
        self._refresh_contract_v2_verdicts()

    def _build_contract_claims_v2_deterministic(self, sources: List[Any]) -> List[ClaimRecord]:
        claims: List[ClaimRecord] = []

        for idx, fact in enumerate(self.verified_facts, start=1):
            text = str(fact.get("fact") or "").strip()
            if not text:
                continue
            source_url = str(fact.get("example_source_url") or "").strip()
            source_id = next((src.source_id for src in sources if src.url == source_url), "")
            claim = ClaimRecord(
                claim_id=f"claim-verified-{idx}",
                question_id=self.contract_v2.question.question_id,
                domain=infer_domain_from_text(text),
                subject=self.query[:120],
                claim_text=text,
                claim_type="verified_fact",
                verdict=ClaimVerdict.LIKELY,
                supports=[source_id] if source_id else [],
                notes=f"legacy_status={fact.get('status', '')}; source_count={int(fact.get('source_count') or 0)}",
            )
            if _filter_session_claims(self, [claim]):
                claims.append(claim)

        for idx, claim in enumerate(self.unverified_claims, start=1):
            text = str(claim.get("fact") or "").strip()
            if not text:
                continue
            source_url = str(claim.get("source") or "").strip()
            source_id = next((src.source_id for src in sources if src.url == self._get_canonical_url(source_url)), "")
            source_type_hint = str(claim.get("source_type") or "")
            domain = infer_domain_from_text(f"{text} {source_type_hint}")
            claim_record = ClaimRecord(
                claim_id=f"claim-unverified-{idx}",
                question_id=self.contract_v2.question.question_id,
                domain=domain,
                subject=self.query[:120],
                claim_text=text,
                claim_type="legacy_claim",
                verdict=ClaimVerdict.INSUFFICIENT_EVIDENCE,
                supports=[source_id] if source_id else [],
                unknowns=["Noch nicht durch mehrere Quellen bestätigt"],
                notes=(
                    f"source_type={claim.get('source_type', '')}; "
                    f"source_count={int(claim.get('source_count') or 0)}"
                ),
            )
            if _filter_session_claims(self, [claim_record]):
                claims.append(claim_record)

        return _dedupe_contract_claims(claims)

    def _apply_cached_semantic_claim_dedupe(self, claims: List[ClaimRecord]) -> List[ClaimRecord]:
        cache = self.research_metadata.get("semantic_claim_dedupe", {})
        if not isinstance(cache, dict):
            return claims
        accepted = cache.get("accepted_merge_candidates")
        if not isinstance(accepted, list) or not accepted:
            return claims
        eligible = [
            claim for claim in claims
            if claim.claim_type in {"verified_fact", "legacy_claim"}
        ]
        if cache.get("signature") != _claim_semantic_signature(eligible):
            return claims

        eligible_by_key = {
            _normalize_claim_text(claim.claim_text): claim
            for claim in eligible
            if _normalize_claim_text(claim.claim_text)
        }
        parent = {key: key for key in eligible_by_key}

        def _find(key: str) -> str:
            while parent[key] != key:
                parent[key] = parent[parent[key]]
                key = parent[key]
            return key

        def _union(left: str, right: str) -> None:
            left_root = _find(left)
            right_root = _find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        for candidate in accepted:
            left_key = _normalize_claim_text(candidate.get("left_claim_text", ""))
            right_key = _normalize_claim_text(candidate.get("right_claim_text", ""))
            if left_key in parent and right_key in parent and left_key != right_key:
                _union(left_key, right_key)

        grouped: Dict[str, List[ClaimRecord]] = {}
        for key, claim in eligible_by_key.items():
            grouped.setdefault(_find(key), []).append(claim)
        merged_by_root = {
            root: _merge_claim_record_group(cluster)
            for root, cluster in grouped.items()
        }

        emitted_roots: set[str] = set()
        merged_claims: List[ClaimRecord] = []
        for claim in claims:
            key = _normalize_claim_text(claim.claim_text)
            if claim.claim_type not in {"verified_fact", "legacy_claim"} or key not in parent:
                merged_claims.append(claim)
                continue
            root = _find(key)
            if root in emitted_roots:
                continue
            emitted_roots.add(root)
            merged_claims.append(merged_by_root[root])
        return merged_claims

    def _build_contract_claims_v2(self, sources: List[Any]) -> List[ClaimRecord]:
        deterministic_claims = self._build_contract_claims_v2_deterministic(sources)
        return self._apply_cached_semantic_claim_dedupe(deterministic_claims)

    def _build_contract_evidences_v2(
        self,
        claims: List[ClaimRecord],
        sources: List[Any],
    ) -> List[EvidenceRecord]:
        evidence_records: List[EvidenceRecord] = []
        source_id_by_url = {source.url: source.source_id for source in sources}

        for claim in claims:
            source_id = claim.supports[0] if claim.supports else ""
            if not source_id:
                continue
            evidence_records.append(
                EvidenceRecord(
                    evidence_id=f"ev-{claim.claim_id}",
                    claim_id=claim.claim_id,
                    source_id=source_id,
                    stance=EvidenceStance.SUPPORTS,
                    excerpt=claim.claim_text[:280],
                )
            )
        return evidence_records

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


def _claim_requires_topic_filter(claim: ClaimRecord) -> bool:
    return claim.claim_type in {"runtime_fact_group", "verified_fact", "legacy_claim"}


def _filter_session_claims(session: DeepResearchSession, claims: List[ClaimRecord]) -> List[ClaimRecord]:
    keep: List[ClaimRecord] = []
    for claim in claims:
        if not _claim_requires_topic_filter(claim):
            keep.append(claim)
            continue
        if _is_text_on_session_topic(session, claim.claim_text):
            keep.append(claim)
    return keep


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

async def _evaluate_source_quality(
    node: ResearchNode,
    content: str,
    *,
    query: str = "",
    plan: Optional[ResearchPlan] = None,
) -> SourceQualityMetrics:
    """
    Bewertet die Qualität einer Quelle nach mehreren Kriterien.

    Returns:
        SourceQualityMetrics mit allen Bewertungen
    """
    metrics = SourceQualityMetrics()

    # 1. AUTORITÄTSSCORE basierend auf Domain
    domain_lower = node.domain.lower()
    active_plan = plan or _build_research_plan(query or f"{node.title} {node.url}", None)
    query_targets_germany = _query_targets_germany(query or active_plan.primary_question)
    source_country = infer_country_code(node.url)
    source_type = infer_source_type(node.url)
    german_state_affiliated = is_german_state_affiliated_url(node.url)

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

    if german_state_affiliated:
        metrics.independence_score = 0.12 if query_targets_germany else 0.28
    elif query_targets_germany and source_country and source_country not in {"", "de"}:
        metrics.independence_score = 0.9
    elif query_targets_germany and not domain_lower.endswith(".de"):
        metrics.independence_score = 0.8
    elif source_type in {SourceType.PAPER, SourceType.BENCHMARK, SourceType.REPOSITORY}:
        metrics.independence_score = 0.82
    elif source_type in {SourceType.PRESS, SourceType.ANALYSIS}:
        metrics.independence_score = 0.74
    elif source_type in {SourceType.OFFICIAL, SourceType.REGULATOR, SourceType.FILING}:
        metrics.independence_score = 0.4
    else:
        metrics.independence_score = 0.5

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

    metrics.scope_fit_score = _estimate_scope_fit(
        node=node,
        content=content,
        query=query or active_plan.primary_question,
        plan=active_plan,
    )

    # 6. GESAMTQUALITÄT berechnen (gewichteter Durchschnitt)
    weights = {
        'authority': 0.21,
        'independence': 0.17,
        'bias': 0.16,  # Niedriger Bias ist besser
        'transparency': 0.10,
        'citations': 0.10,
        'recency': 0.08,
        'scope_fit': 0.18,
    }

    metrics.quality_score = (
        metrics.authority_score * weights['authority'] +
        metrics.independence_score * weights['independence'] +
        (1 - metrics.bias_score) * weights['bias'] +  # Invertiert!
        metrics.transparency_score * weights['transparency'] +
        metrics.citation_score * weights['citations'] +
        metrics.recency_score * weights['recency'] +
        metrics.scope_fit_score * weights['scope_fit']
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
        1 if found_date is not None else 0,
        1 if metrics.scope_fit_score != 0.5 else 0,
        1 if metrics.independence_score != 0.5 else 0,
    ])
    metrics.confidence = min(indicators_found / 7.0, 1.0)

    # 9. Notes für Bericht
    notes = []
    if metrics.authority_score > 0.8:
        notes.append("High-authority source")
    if metrics.bias_level in [BiasLevel.HIGH, BiasLevel.MEDIUM]:
        notes.append(f"Potential {metrics.bias_level.value} bias detected")
    if metrics.transparency_score < 0.3:
        notes.append("Limited transparency (no author/methodology)")
    if metrics.scope_fit_score < 0.35:
        notes.append("Weak topic fit")
    elif metrics.scope_fit_score >= 0.7:
        notes.append("Direct topic fit")
    if german_state_affiliated:
        notes.append("German state-affiliated source")
    elif query_targets_germany and metrics.independence_score >= 0.8:
        notes.append("Foreign independent perspective")

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
    session._materialize_verification_claims_v2(grouped, verified, unverified, conflicts)

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

def get_adaptive_config(
    query: str,
    focus_areas: Optional[List[str]],
    max_depth: Optional[int] = None,
) -> Dict[str, Any]:
    """Gibt adaptive Konfiguration zurück — skaliert mit max_depth."""
    depth = max(1, min(5, int(max_depth or 3)))
    # Skalierungstabelle: depth → (max_queries, max_sources, parallel_limit)
    _DEPTH_SCALE = {
        1: (6,  8,  3),
        2: (9,  15, 4),
        3: (12, 20, 4),
        4: (15, 35, 6),
        5: (20, 50, 8),
    }
    max_queries, max_sources, parallel = _DEPTH_SCALE[depth]
    return {
        "max_initial_search_queries": max_queries,
        "max_results_per_search_query": 15,
        "max_sources_to_deep_dive": max_sources,
        "max_depth_for_links": min(depth, 3),
        "max_chunks_per_source_for_facts": 3,
        "parallel_source_analysis_limit": parallel,
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


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _unique_texts(values: List[str], lowercase: bool = False) -> List[str]:
    unique: List[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _normalize_space(raw)
        if lowercase:
            value = value.lower()
        if not value:
            continue
        if len(value) < 3 and not re.fullmatch(r"20\d{2}", value):
            continue
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _tokenize_query_terms(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-\+\.]*", str(text or "").lower())


def _expand_focus_terms(focus_areas: Optional[List[str]]) -> List[str]:
    terms: List[str] = []
    for focus in focus_areas or []:
        focus_norm = _normalize_space(focus)
        if not focus_norm:
            continue
        terms.append(focus_norm.lower())
        terms.extend(extract_query_anchor_terms(focus_norm))
    return _unique_texts(terms, lowercase=True)


def _extract_temporal_terms(query: str) -> List[str]:
    tokens = _tokenize_query_terms(query)
    terms = [
        token for token in tokens
        if re.fullmatch(r"20\d{2}", token)
        or token in {"aktuell", "neu", "neuste", "neuesten", "latest", "recent", "current", "today"}
    ]
    if terms:
        return _unique_texts(terms, lowercase=True)
    current_year = datetime.now().year
    return [str(current_year - 1), str(current_year)]


def _profile_query_angles(profile: str, lang: str, domain: str, query_terms: List[str]) -> List[str]:
    agentic_focus = any(
        token in {
            "agent", "agents", "agentic", "agenten", "tool", "tools", "function", "calling",
            "multiagent", "multi-agent", "workflow", "workflows", "planung", "planning",
            "orchestration",
        }
        for token in query_terms
    )
    germany_focus = any(
        token in {"deutschland", "deutsch", "germany", "german", "bundesrepublik"}
        for token in query_terms
    )

    if profile == "policy_regulation":
        if germany_focus:
            return [
                "international reporting independent legal analysis",
                "foreign press germany policy scrutiny",
                "official law text with external verification",
            ]
        return [
            "official regulation guidance",
            "law compliance implementation",
            "government documentation analysis",
        ]
    if profile == "news":
        if germany_focus:
            return [
                "foreign press germany developments",
                "independent analysis international reporting",
                "timeline reporting sources",
            ]
        return [
            "official announcement update",
            "latest developments analysis",
            "timeline reporting sources",
        ]
    if profile == "scientific":
        return [
            "peer reviewed paper benchmark",
            "survey review methodology",
            "evaluation replication results",
        ]
    if profile == "vendor_comparison":
        angles = [
            "benchmark evaluation comparison",
            "official documentation release",
            "survey implementation limitations",
        ]
        if agentic_focus:
            angles.insert(1, "tool use function calling multi agent")
        return angles
    # domain == "tech" bekommt topic-neutrale Winkel, die das eigentliche Thema
    # nicht in Richtung Software/AI/Benchmarks verschieben.
    if lang == "de":
        return [
            "offizielle dokumentation analyse",
            "studie evidenz vergleich",
            "anwendung praxis limitierungen",
        ]
    return [
        "official documentation analysis",
        "study evidence comparison",
        "application practice limitations",
    ]


def _profile_source_priority_terms(profile: str, lang: str) -> List[str]:
    if lang == "de":
        if profile == "policy_regulation":
            return [
                "auslaendische presse deutschland unabhaengige analyse",
                "ngo watchdog rechtsanalyse europa international",
                "primaerquelle gesetzestext gericht regulator dokument",
            ]
        if profile == "scientific":
            return [
                "peer reviewed paper systematische uebersicht",
                "benchmark methodik datensatz replizierbarkeit",
                "primaerquelle studie paper review",
            ]
        if profile == "news":
            return [
                "offizielle mitteilung primaerquelle",
                "reuters ap dpa bestaetigte meldung",
                "zeitachse ankundigung statement",
            ]
        if profile == "vendor_comparison":
            return [
                "offizielle dokumentation benchmark unabhaengige analyse",
                "methodik evaluierung limitations",
                "primaerquelle release notes benchmark",
            ]
        if profile == "market_intelligence":
            return [
                "offizielle filing investor relations branche daten",
                "marktbericht annual report industrieanalyse",
                "primaerquelle unternehmensbericht regulator filing",
            ]
        return [
            "primaerquelle offizielle quelle originaldokument",
            "faktencheck belastbare quelle bestaetigung",
            "direkter nachweis offizielle angabe",
        ]
    if profile == "policy_regulation":
        return [
            "foreign press germany independent analysis",
            "ngo watchdog legal analysis international",
            "primary source legislative text court regulator document",
        ]
    if profile == "scientific":
        return [
            "peer reviewed paper systematic review",
            "benchmark methodology dataset reproducibility",
            "primary source study paper review",
        ]
    if profile == "news":
        return [
            "official statement primary source",
            "reuters ap confirmed reporting",
            "timeline announcement statement",
        ]
    if profile == "vendor_comparison":
        return [
            "official documentation benchmark independent analysis",
            "methodology evaluation limitations",
            "primary source release notes benchmark",
        ]
    if profile == "market_intelligence":
        return [
            "official filing investor relations industry data",
            "market report annual report industry analysis",
            "primary source company filing regulator",
        ]
    return [
        "primary source official document",
        "fact check reliable source confirmation",
        "direct evidence official statement",
    ]


def _count_term_matches(terms: List[str], text: str) -> int:
    haystack = str(text or "").lower()
    return sum(1 for term in terms if term and term in haystack)


def _query_targets_germany(query: str) -> bool:
    haystack = f" {_normalize_space(query).lower()} "
    return any(
        token in haystack
        for token in (" deutschland ", " bundesrepublik ", " germany ", " german ")
    ) or "deutsch" in haystack


def _estimate_scope_fit(
    *,
    node: "ResearchNode",
    content: str,
    query: str,
    plan: "ResearchPlan",
) -> float:
    title_text = _normalize_space(node.title).lower()
    body_text = _normalize_space(str(content or "")[:6000]).lower()
    combined = f"{title_text} {body_text}".strip()
    if not combined:
        return 0.0

    must_terms = _unique_texts(list(plan.must_have_terms or []), lowercase=True)
    include_terms = _unique_texts(list(plan.include_terms or []), lowercase=True)
    related_terms = _unique_texts(list(plan.related_terms or []), lowercase=True)
    if not must_terms:
        must_terms = _unique_texts(extract_query_anchor_terms(query), lowercase=True)
    if not include_terms:
        include_terms = list(must_terms)

    must_hits = _count_term_matches(must_terms[:8], combined)
    include_hits = _count_term_matches(include_terms[:12], combined)
    related_hits = _count_term_matches(related_terms[:12], combined)
    title_must_hits = _count_term_matches(must_terms[:8], title_text)
    admin_like = any(pattern in combined[:1800] for pattern in _TOPIC_ADMIN_PATTERNS)

    inferred_source_type = infer_source_type(node.url).value
    preferred_type_match = inferred_source_type in {str(item or "").strip().lower() for item in plan.preferred_source_types}

    score = 0.12
    if must_hits >= 2:
        score = 0.82
    elif must_hits == 1:
        score = 0.66 if include_hits >= 2 else 0.58
    elif include_hits >= 3:
        score = 0.48
    elif include_hits >= 2:
        score = 0.38
    elif related_hits >= 3:
        score = 0.32
    elif include_hits >= 1 or related_hits >= 1:
        score = 0.24

    if title_must_hits:
        score += 0.10
    if preferred_type_match:
        score += 0.06
    if plan.strict_topic and must_terms and must_hits == 0:
        score -= 0.18
    if admin_like and must_hits == 0:
        score -= 0.16

    return max(0.0, min(1.0, score))


def _resolve_scope_mode(
    requested_scope_mode: str,
    query_terms: List[str],
    focus_terms: List[str],
    profile: str,
    domain: str,
) -> str:
    requested = str(requested_scope_mode or "auto").strip().lower()
    if requested in {"strict", "landscape"}:
        return requested

    broad_hits = sum(1 for term in query_terms if term in _BROAD_SCOPE_MARKERS)
    specific_hits = sum(1 for term in query_terms if term in _SPECIFIC_SCOPE_HINTS)
    if profile in {"news", "market_intelligence", "competitive_landscape"}:
        return "landscape"
    if broad_hits >= 2 and not focus_terms:
        return "landscape"
    if broad_hits >= 1 and domain == "tech" and specific_hits == 0:
        return "landscape"
    return "strict"


def _related_landscape_terms(
    anchor_terms: List[str],
    focus_terms: List[str],
    alias_terms: List[str],
    domain: str,
) -> List[str]:
    related = list(alias_terms)
    if domain == "tech":
        related.extend([
            "agent", "agentic", "planning", "reasoning", "evaluation",
            "architecture", "autonomy", "safety", "alignment", "orchestration", "governance",
        ])
    for term in anchor_terms + focus_terms:
        if term == "introspective":
            related.extend(["self-reflection", "reflection", "introspection"])
        elif term == "autonomous":
            related.extend(["autonomy", "agentic", "planning"])
        elif term == "rag":
            related.extend(["retrieval", "generation", "vector search", "context"])
        elif term == "retrieval":
            related.extend(["retriever", "vector", "embedding"])
    return _unique_texts(related, lowercase=True)


def _build_research_plan(query: str, focus_areas: Optional[List[str]], session: Optional[DeepResearchSession] = None) -> ResearchPlan:
    query_norm = _normalize_space(query)
    lang = _detect_language(query_norm)
    domain = _detect_domain(query_norm)
    profile_raw = getattr(getattr(getattr(session, "contract_v2", None), "question", None), "profile", "fact_check")
    profile = getattr(profile_raw, "value", str(profile_raw or "fact_check"))
    germany_focus = _query_targets_germany(query_norm)

    raw_query_terms = _tokenize_query_terms(query_norm)
    anchor_terms = _unique_texts(extract_query_anchor_terms(query_norm), lowercase=True)
    focus_terms = _expand_focus_terms(focus_areas)
    temporal_terms = _extract_temporal_terms(query_norm)

    alias_terms: List[str] = []
    for term in anchor_terms + focus_terms:
        alias_terms.extend(_QUERY_TERM_ALIASES.get(term, []))
    alias_terms = _unique_texts(alias_terms, lowercase=True)

    scope_mode = _resolve_scope_mode(
        requested_scope_mode=getattr(session, "requested_scope_mode", "auto"),
        query_terms=raw_query_terms,
        focus_terms=focus_terms,
        profile=profile,
        domain=domain,
    )

    must_have_terms = _unique_texts(focus_terms[:3] or anchor_terms[:3], lowercase=True)
    include_terms = _unique_texts(anchor_terms + focus_terms + temporal_terms + alias_terms, lowercase=True)
    if (len(must_have_terms) <= 1 or (scope_mode == "landscape" and not focus_terms)) and alias_terms:
        must_have_terms = _unique_texts(must_have_terms + alias_terms[:2], lowercase=True)
    if not must_have_terms:
        must_have_terms = include_terms[:3]
    related_terms = _related_landscape_terms(anchor_terms, focus_terms, alias_terms, domain)

    query_lower = query_norm.lower()
    focus_text = " ".join(focus_areas or []).lower()
    exclude_terms = _unique_texts(
        [
            term for term in _GENERIC_ADMIN_RESULT_TERMS
            if term not in query_lower and term not in focus_text
        ],
        lowercase=True,
    )

    query_angles = _profile_query_angles(profile, lang, domain, raw_query_terms)
    focus_fragment = " ".join(_unique_texts(list(focus_areas or []))[:2])
    temporal_fragment = " ".join(temporal_terms[:2])
    variants = [query_norm]
    if focus_fragment:
        variants.append(f"{query_norm} {focus_fragment}")
    for angle in query_angles[:3]:
        suffix = " ".join(part for part in [focus_fragment, angle, temporal_fragment] if part).strip()
        variants.append(f"{query_norm} {suffix}".strip())
    if alias_terms:
        variants.append(f"{query_norm} {' '.join(alias_terms[:3])}")
    for source_terms in _profile_source_priority_terms(profile, lang)[:3]:
        suffix = " ".join(part for part in [focus_fragment, source_terms, temporal_fragment] if part).strip()
        variants.append(f"{query_norm} {suffix}".strip())
    if germany_focus:
        if lang == "de":
            variants.append(f"{query_norm} internationale presse unabhaengige analyse europa")
            variants.append(f"{query_norm} auslaendische quelle watchdog bericht")
        else:
            variants.append(f"{query_norm} foreign press independent analysis europe")
            variants.append(f"{query_norm} international watchdog report")

    if lang == "de":
        variants.append(f"{query_norm} studie analyse evidenz statistik")
        variants.append(f"{query_norm} marktbericht branchenbericht daten")
        variants.append(f"{query_norm} wissenschaftliche forschung ergebnisse")
        variants.append(f"{query_norm} praxiserfahrung anwendung ergebnis")
    else:
        variants.append(f"{query_norm} study analysis evidence statistics")
        variants.append(f"{query_norm} market report industry data whitepaper")
        variants.append(f"{query_norm} research findings methodology")
        variants.append(f"{query_norm} practical application results implementation")

    subquestions = [
        f"Welche Primaer- oder belastbaren Sekundaerquellen beantworten '{query_norm}' direkt?",
    ]
    for focus in _unique_texts(list(focus_areas or []))[:3]:
        subquestions.append(f"Welche belastbare Evidenz gibt es speziell zu {focus}?")
    subquestions.append("Welche Widersprueche, Grenzen oder offenen Fragen bleiben nach der Recherche uebrig?")

    preferred_source_types = ["official", "paper", "benchmark", "analysis"]
    if profile == "policy_regulation":
        preferred_source_types = ["analysis", "press", "paper", "regulator", "official"]
    elif profile == "news":
        preferred_source_types = ["official", "press", "analysis"]

    topic_boundaries = [
        f"Bleibe beim Kerngegenstand: {query_norm}",
        "Priorisiere Ergebnisse mit direktem Bezug zu den Muss-Begriffen und Teilfragen.",
        "Verwirf administrative, Recruiting-, Preis-, Kontakt- und reine Marketingseiten, sofern nicht explizit angefragt.",
        "Verwirf Seitenthemen ohne klare Ueberschneidung mit den Kernbegriffen der Anfrage.",
    ]
    if germany_focus:
        topic_boundaries.append(
            "Nutze deutsche staatsnahe Quellen hoechstens als Primärkontext; fuer Einordnung und Bestaetigung priorisiere auslaendische, unabhaengige Quellen."
        )

    return ResearchPlan(
        primary_question=query_norm,
        query_language=lang,
        domain=domain,
        profile=profile,
        scope_mode=scope_mode,
        query_variants=_unique_texts(variants)[:12],
        focus_terms=focus_terms,
        anchor_terms=anchor_terms,
        include_terms=include_terms,
        must_have_terms=must_have_terms,
        exclude_terms=exclude_terms,
        related_terms=related_terms,
        temporal_terms=temporal_terms,
        preferred_source_types=preferred_source_types,
        subquestions=subquestions,
        topic_boundaries=topic_boundaries,
        strict_topic=(scope_mode == "strict"),
        created_at=datetime.now().isoformat(),
    )


def _worker_query_variants_enabled() -> bool:
    return os.getenv("DR_WORKER_QUERY_VARIANTS_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _sanitize_worker_query_variants(
    session: DeepResearchSession,
    variants: List[Any],
) -> Tuple[List[str], List[str]]:
    accepted: List[str] = []
    rejected: List[str] = []
    for raw in variants:
        variant = _normalize_space(str(raw or ""))
        if not variant:
            continue
        if len(variant) < 8 or len(variant) > 240:
            rejected.append(variant)
            continue
        if not _is_text_on_session_topic(session, variant):
            rejected.append(variant)
            continue
        accepted.append(variant)
    return _unique_texts(accepted), _unique_texts(rejected)


async def _augment_query_variants_with_worker(
    session: DeepResearchSession,
    *,
    session_id: str,
    max_queries: int,
) -> List[str]:
    plan = _ensure_research_plan(session)
    baseline = _unique_texts(list(plan.query_variants))
    limit = max(1, min(int(max_queries or len(baseline) or 1), 20))
    metadata: Dict[str, Any] = {
        "enabled": _worker_query_variants_enabled(),
        "status": "disabled",
        "provider": "",
        "model": "",
        "accepted_variants": 0,
        "rejected_variants": 0,
        "fallback_used": True,
    }

    if not metadata["enabled"]:
        session.research_metadata["query_variant_worker"] = metadata
        return baseline[:limit]

    if len(baseline) >= limit:
        metadata["status"] = "skipped_no_capacity"
        metadata["fallback_used"] = False
        session.research_metadata["query_variant_worker"] = metadata
        return baseline[:limit]

    available_slots = max(limit - len(baseline), 2)
    worker_task = WorkerTask(
        worker_type="query_variants",
        system_prompt=(
            "Du bist ein leichter Recherche-Worker fuer Timus Deep Research.\n"
            "Erzeuge nur thematisch praezise Suchvarianten fuer die bestehende Anfrage.\n"
            "Erweitere das Thema nicht, fuehre keine Seitenthemen ein und erhalte Muss-Begriffe.\n"
            "Bevorzuge konkrete Query-Varianten mit Fokusterme, Synonymen, Industrie-/Praxiswinkeln "
            "oder belastbaren Evidenz-Hinweisen.\n"
            "Keine Erklaerung ausserhalb des JSON."
        ),
        input_payload={
            "query": plan.primary_question,
            "scope_mode": plan.scope_mode,
            "query_language": plan.query_language,
            "domain": plan.domain,
            "focus_areas": session.focus_areas,
            "baseline_query_variants": baseline[:8],
            "anchor_terms": plan.anchor_terms[:8],
            "focus_terms": plan.focus_terms[:8],
            "must_have_terms": plan.must_have_terms[:6],
            "include_terms": plan.include_terms[:10],
            "exclude_terms": plan.exclude_terms[:10],
            "temporal_terms": plan.temporal_terms[:4],
            "subquestions": plan.subquestions[:4],
            "max_new_variants": min(available_slots, 6),
        },
        response_schema={
            "query_variants": ["<praezise Suchanfrage>", "<weitere praezise Suchanfrage>"],
            "notes": ["<kurze Begruendung pro Variante>"],
        },
    )
    result = await run_worker(
        worker_task,
        profile_prefix="DR_WORKER_QUERY",
        agent="deep_research",
        session_id=session_id,
    )

    metadata.update(
        {
            "status": result.status,
            "provider": result.provider,
            "model": result.model,
            "fallback_used": result.fallback_used,
            "duration_ms": result.duration_ms,
            "max_tokens": result.max_tokens,
        }
    )

    if result.status != "ok":
        if result.error:
            metadata["error"] = result.error
        session.research_metadata["query_variant_worker"] = metadata
        session.methodology_notes.append(
            f"Query-Worker Fallback aktiv: status={result.status}"
        )
        return baseline[:limit]

    raw_variants = result.payload.get("query_variants", [])
    if not isinstance(raw_variants, list):
        metadata["status"] = "invalid_payload"
        metadata["fallback_used"] = True
        metadata["error"] = "query_variants missing or not a list"
        session.research_metadata["query_variant_worker"] = metadata
        session.methodology_notes.append("Query-Worker Fallback aktiv: invalid_payload")
        return baseline[:limit]

    accepted, rejected = _sanitize_worker_query_variants(session, raw_variants)
    combined = _unique_texts(baseline + accepted)[:limit]
    added = max(len(combined) - len(baseline[:limit]), 0)
    metadata["accepted_variants"] = added
    metadata["rejected_variants"] = len(rejected)
    metadata["notes"] = result.payload.get("notes", [])
    metadata["fallback_used"] = False
    if rejected:
        metadata["rejected_examples"] = rejected[:3]
    session.research_metadata["query_variant_worker"] = metadata

    if added > 0:
        session.methodology_notes.append(
            f"Query-Worker ergänzte {added} praezise Query-Varianten "
            f"({result.provider}/{result.model})."
        )
    else:
        session.methodology_notes.append(
            f"Query-Worker lieferte keine zusaetzlich verwertbaren Varianten "
            f"({result.provider}/{result.model})."
        )

    plan.query_variants = combined
    session.research_metadata["research_plan"] = asdict(plan)
    return combined


async def _populate_semantic_claim_dedupe_cache(
    session: DeepResearchSession,
    *,
    session_id: str,
) -> None:
    metadata: Dict[str, Any] = {
        "enabled": _worker_semantic_dedupe_enabled(),
        "status": "disabled",
        "accepted_merge_candidates": [],
        "fallback_used": True,
    }
    if not metadata["enabled"]:
        session.research_metadata["semantic_claim_dedupe"] = metadata
        return

    session.export_contract_v2()
    deterministic_claims = session._build_contract_claims_v2_deterministic(session.contract_v2.sources)
    signature = _claim_semantic_signature(deterministic_claims)
    metadata["signature"] = signature

    if len(deterministic_claims) < 2:
        metadata["status"] = "skipped_too_few_claims"
        metadata["fallback_used"] = False
        session.research_metadata["semantic_claim_dedupe"] = metadata
        return

    cached = session.research_metadata.get("semantic_claim_dedupe", {})
    if (
        isinstance(cached, dict)
        and cached.get("signature") == signature
        and cached.get("status") == "ok"
        and isinstance(cached.get("accepted_merge_candidates"), list)
    ):
        session.research_metadata["semantic_claim_dedupe"] = cached
        return

    sorted_claims = sorted(deterministic_claims, key=lambda claim: _normalize_claim_text(claim.claim_text))
    chunk_size = _semantic_dedupe_chunk_size()
    overlap = min(_semantic_dedupe_chunk_overlap(), max(chunk_size - 1, 0))
    step = max(chunk_size - overlap, 1)
    windows: List[List[ClaimRecord]] = []
    for start in range(0, len(sorted_claims), step):
        window = sorted_claims[start:start + chunk_size]
        if len(window) >= 2:
            windows.append(window)
        if start + chunk_size >= len(sorted_claims):
            break

    tasks: List[WorkerTask] = []
    for index, window in enumerate(windows, start=1):
        tasks.append(
            WorkerTask(
                worker_type="semantic_claim_dedupe",
                system_prompt=(
                    "Du bist ein konservativer semantischer Dedupe-Worker fuer Timus Deep Research.\n"
                    "Markiere nur Claim-Paare als Merge-Kandidaten, wenn sie inhaltlich nahezu gleich sind.\n"
                    "Verschiedene technische Begriffe, Sensorarten, Benchmarks, Modelle oder Architekturen "
                    "duerfen NICHT gemerged werden.\n"
                    "Wenn du unsicher bist, liefere keinen Kandidaten.\n"
                    "Antworte ausschliesslich mit JSON."
                ),
                input_payload={
                    "query": session.query,
                    "focus_areas": session.focus_areas,
                    "scope_mode": _ensure_research_plan(session).scope_mode,
                    "must_have_terms": _ensure_research_plan(session).must_have_terms[:6],
                    "anchor_terms": _ensure_research_plan(session).anchor_terms[:6],
                    "window_index": index,
                    "claims": [
                        {
                            "claim_text": claim.claim_text,
                            "claim_type": claim.claim_type,
                            "supports_count": len(claim.supports),
                            "unknowns_count": len(claim.unknowns),
                        }
                        for claim in window
                    ],
                },
                response_schema={
                    "merge_candidates": [
                        {
                            "left_claim_text": "<claim text>",
                            "right_claim_text": "<claim text>",
                            "reason": "<kurze Begruendung>",
                            "confidence": 0.9,
                        }
                    ],
                    "notes": ["<kurzer Hinweis>"],
                },
            )
        )

    results = await run_worker_batch(
        tasks,
        profile_prefix="DR_WORKER_SEMANTIC_DEDUPE",
        agent="deep_research",
        session_id=session_id,
    )
    raw_candidates: List[Dict[str, Any]] = []
    ok_results = 0
    for result in results:
        if result.status != "ok":
            continue
        ok_results += 1
        candidates = result.payload.get("merge_candidates", [])
        if isinstance(candidates, list):
            raw_candidates.extend(candidate for candidate in candidates if isinstance(candidate, dict))

    accepted = _filter_semantic_merge_candidates(session, deterministic_claims, raw_candidates)
    metadata.update(
        {
            "status": "ok" if ok_results else "fallback_no_worker_result",
            "windows": len(windows),
            "worker_results_ok": ok_results,
            "raw_merge_candidates": len(raw_candidates),
            "accepted_merge_candidates": accepted,
            "accepted_count": len(accepted),
            "fallback_used": ok_results == 0,
        }
    )
    if results:
        metadata["worker_models"] = sorted(
            {
                f"{result.provider}/{result.model}"
                for result in results
                if result.provider and result.model
            }
        )
    if ok_results == 0:
        metadata["error"] = "no successful semantic dedupe worker result"
        session.methodology_notes.append("Semantic-Dedupe-Worker Fallback aktiv: no successful worker result.")
    elif accepted:
        session.methodology_notes.append(
            f"Semantic-Dedupe-Worker schlug {len(accepted)} konservative Merge-Kandidaten vor."
        )
    else:
        session.methodology_notes.append(
            "Semantic-Dedupe-Worker fand keine konservativ akzeptablen Merge-Kandidaten."
        )
    session.research_metadata["semantic_claim_dedupe"] = metadata


async def _populate_conflict_scan_cache(
    session: DeepResearchSession,
    *,
    session_id: str,
) -> None:
    metadata: Dict[str, Any] = {
        "enabled": _worker_conflict_scan_enabled(),
        "status": "disabled",
        "conflicts": [],
        "open_questions": [],
        "weak_evidence_flags": [],
        "report_notes": [],
        "fallback_used": True,
    }
    if not metadata["enabled"]:
        session.research_metadata["conflict_scan_worker"] = metadata
        return

    worker_input = _build_conflict_scan_input(session)
    metadata["input_counts"] = {
        "claims": len(worker_input.get("claims") or []),
        "conflicting_info": len(worker_input.get("conflicting_info") or []),
        "open_questions": len(worker_input.get("open_questions") or []),
    }

    if not (
        worker_input.get("claims")
        or worker_input.get("conflicting_info")
        or worker_input.get("open_questions")
    ):
        metadata["status"] = "skipped_no_material"
        metadata["fallback_used"] = False
        session.research_metadata["conflict_scan_worker"] = metadata
        return

    worker_task = WorkerTask(
        worker_type="conflict_scan",
        system_prompt=(
            "Du bist ein konservativer Conflict-Scan-Worker fuer Timus Deep Research.\n"
            "Analysiere nur offensichtliche Konflikte, Evidenzluecken und offene Fragen zur Leitfrage.\n"
            "Erfinde keine neuen Claims und klassifiziere nur dann einen Konflikt, wenn die Hinweise stark sind.\n"
            "Wenn du unsicher bist, liefere lieber weniger Eintraege.\n"
            "Antworte ausschliesslich mit JSON."
        ),
        input_payload=worker_input,
        response_schema={
            "conflicts": [
                {
                    "claim_text": "<claim text>",
                    "issue_type": "evidence_conflict|method_disagreement|scope_gap|uncertain_transfer",
                    "reason": "<kurze Begruendung>",
                    "confidence": 0.84,
                }
            ],
            "open_questions": ["<offene Frage>"],
            "weak_evidence_flags": [
                {
                    "claim_text": "<claim text>",
                    "reason": "<warum schwach>",
                    "confidence": 0.84,
                }
            ],
            "report_notes": ["<kurzer Report-Hinweis>"],
        },
    )
    result = await run_worker(
        worker_task,
        profile_prefix="DR_WORKER_CONFLICT_SCAN",
        agent="deep_research",
        session_id=session_id,
    )
    metadata.update(
        {
            "status": result.status,
            "provider": result.provider,
            "model": result.model,
            "duration_ms": result.duration_ms,
            "max_tokens": result.max_tokens,
            "fallback_used": result.fallback_used,
        }
    )

    if result.status != "ok":
        if result.error:
            metadata["error"] = result.error
        session.research_metadata["conflict_scan_worker"] = metadata
        session.methodology_notes.append(
            f"Conflict-Scan-Worker Fallback aktiv: status={result.status}."
        )
        return

    normalized = _normalize_conflict_scan_payload(result.payload)
    metadata.update(normalized)
    metadata["status"] = "ok"
    metadata["fallback_used"] = False
    session.research_metadata["conflict_scan_worker"] = metadata

    if normalized["conflicts"] or normalized["open_questions"] or normalized["weak_evidence_flags"]:
        session.methodology_notes.append(
            "Conflict-Scan-Worker identifizierte zusaetzliche Konflikt-/Unknown-Hinweise fuer den Report."
        )
    else:
        session.methodology_notes.append(
            "Conflict-Scan-Worker lieferte keine zusaetzlichen belastbaren Konflikt-Hinweise."
        )


def _ensure_research_plan(session: DeepResearchSession) -> ResearchPlan:
    if session.research_plan is None:
        session.research_plan = _build_research_plan(session.query, session.focus_areas, session=session)
        session.research_metadata["research_plan"] = asdict(session.research_plan)
    return session.research_plan


def _is_text_on_session_topic(session: DeepResearchSession, text: str) -> bool:
    candidate = _normalize_space(text)
    if not candidate:
        return False
    plan = _ensure_research_plan(session)
    candidate_lower = candidate.lower()
    anchor_hits = _count_term_matches(plan.anchor_terms, candidate_lower)
    focus_hits = _count_term_matches(plan.focus_terms, candidate_lower)
    must_hits = _count_term_matches(plan.must_have_terms, candidate_lower)
    include_hits = _count_term_matches(plan.include_terms, candidate_lower)
    exclude_hits = _count_term_matches(plan.exclude_terms, candidate_lower)
    related_hits = _count_term_matches(plan.related_terms, candidate_lower)
    landscape_hits = _count_term_matches(list(_LANDSCAPE_TECH_TERMS), candidate_lower)
    query_gate = claim_is_on_topic(session.query, candidate)

    if exclude_hits >= 2 and anchor_hits == 0 and focus_hits == 0:
        return False
    if plan.scope_mode == "landscape":
        if must_hits >= 1:
            return True
        if focus_hits >= 1 and (anchor_hits >= 1 or related_hits >= 1):
            return True
        if anchor_hits >= 1 and (related_hits >= 1 or landscape_hits >= 1):
            return True
        if related_hits >= 1 and landscape_hits >= 2:
            return True
        if related_hits >= 2 and landscape_hits >= 2:
            return True
        if landscape_hits >= 3:
            return True
        if query_gate and include_hits >= 1:
            return True
        return False

    if must_hits >= 1:
        return True
    if focus_hits >= 1 and anchor_hits >= 1:
        return True
    if anchor_hits >= 2:
        return True
    if query_gate and anchor_hits >= 1 and include_hits >= 1:
        return True
    return query_gate and include_hits >= 1


def _prune_session_findings_to_topic(session: DeepResearchSession) -> Dict[str, int]:
    verified_before = len(session.verified_facts)
    unverified_before = len(session.unverified_claims)

    session.verified_facts = [
        fact for fact in session.verified_facts
        if _is_text_on_session_topic(session, str(fact.get("fact") or ""))
    ]
    session.unverified_claims = [
        claim for claim in session.unverified_claims
        if _is_text_on_session_topic(session, str(claim.get("fact") or ""))
    ]

    removed_verified = verified_before - len(session.verified_facts)
    removed_unverified = unverified_before - len(session.unverified_claims)
    removed_total = removed_verified + removed_unverified
    if removed_total > 0:
        session.methodology_notes.append(
            f"Topic-Gate verwarf {removed_total} off-topic Hinweise/Claims "
            f"({removed_verified} verified, {removed_unverified} unverified)."
        )
    return {
        "removed_verified": removed_verified,
        "removed_unverified": removed_unverified,
        "removed_total": removed_total,
    }


async def _perform_initial_search(query: str, session: DeepResearchSession) -> List[Dict[str, Any]]:
    """
    Führt initiale Websuche durch (v7.0).

    NEU: Language-Detection → US-Location für englische Queries.
         5 Query-Varianten statt 3.
         Diagnostics-Integration.
    """
    logger.info(f"🔎 Initiale Suche: '{query}'")

    plan = _ensure_research_plan(session)
    lang = plan.query_language
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

    queries = plan.query_variants or [query]

    all_results: List[Dict[str, Any]] = []

    async def _single_search(q: str) -> Optional[Any]:
        try:
            return await call_tool_internal(
                "search_web",
                {
                    "query": q,
                    "max_results": 15,
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

    search_results = await asyncio.gather(*[_single_search(q) for q in queries[:12]])

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
            diag.n_queries_issued = min(len(queries), 12)
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

        url_lower = url.lower()
        title = str(r.get("title") or "")
        snippet = str(r.get("snippet") or "")
        combined_text = f"{title} {snippet} {url_lower}".lower()
        anchor_hits = _count_term_matches(plan.anchor_terms, combined_text)
        focus_hits = _count_term_matches(plan.focus_terms, combined_text)
        must_hits = _count_term_matches(plan.must_have_terms, combined_text)
        include_hits = _count_term_matches(plan.include_terms, combined_text)
        exclude_hits = _count_term_matches(plan.exclude_terms, combined_text)
        related_hits = _count_term_matches(plan.related_terms, combined_text)

        score = 0.35

        if any(domain in url_lower for domain in [".gov", ".edu", ".org"]):
            score += 0.18
        if "wikipedia" in url_lower:
            score += 0.12
        if ".pdf" in url_lower:
            score += 0.1
        if any(social in url_lower for social in ["facebook.com", "twitter.com", "instagram.com", "tiktok.com"]):
            score -= 0.22
        if "arxiv.org" in url_lower:
            score += 0.22
        if "github.com" in url_lower:
            score += 0.12
        if any(d in url_lower for d in ["nature.com", "sciencedirect.com", "springer.com", "wiley.com"]):
            score += 0.20
        if any(d in url_lower for d in ["reuters.com", "bloomberg.com", "ft.com"]):
            score += 0.12
        if any(d in url_lower for d in ["statista.com", "gartner.com", "mckinsey.com"]):
            score += 0.15
        if must_hits >= 1:
            score += 0.18
        score += min(anchor_hits * 0.08 + focus_hits * 0.08 + include_hits * 0.04 + related_hits * 0.03, 0.46)
        score -= min(exclude_hits * 0.12, 0.36)
        if plan.scope_mode == "strict" and must_hits == 0 and anchor_hits == 0 and focus_hits == 0 and include_hits < 2:
            score -= 0.16
        elif plan.scope_mode == "landscape" and anchor_hits == 0 and related_hits == 0 and include_hits < 2:
            score -= 0.08

        r["score"] = max(0.0, min(score, 1.0))
        r["canonical_url"] = session._get_canonical_url(url)
        r["plan_hits"] = {
            "anchor": anchor_hits,
            "focus": focus_hits,
            "must": must_hits,
            "include": include_hits,
            "exclude": exclude_hits,
            "related": related_hits,
        }
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

    return final_results[:35]


async def _run_gap_filling_search(
    session: "DeepResearchSession",
    config: Dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> None:
    """
    Phase 3.5: Gap-Filling-Suche — wird aktiviert wenn < 15 Roh-Fakten ODER < 10 Quellen
    im Research-Tree. Führt 5 gezielte Zusatzsuchen durch und verarbeitet bis zu 8 neue Quellen.
    """
    facts_count = len(session.all_extracted_facts_raw)
    tree_count = len(session.research_tree)

    if facts_count >= 15 and tree_count >= 10:
        logger.info(f"✅ Phase 3.5 übersprungen (Fakten={facts_count}, Quellen={tree_count})")
        return

    logger.info(f"🔎 Phase 3.5: Gap-Filling-Suche startet (Fakten={facts_count}, Quellen={tree_count})")

    plan = _ensure_research_plan(session)
    lang = plan.query_language
    location_code = _LANG_LOCATION_MAP.get(lang, 2276)
    language_code = _LANG_CODE_MAP.get(lang, "de")

    gap_queries: List[str] = [
        f"{session.query} expert review analysis",
        f"{session.query} statistics data 2024 2025",
        f"{session.query} case study application",
    ]
    for sq in (plan.subquestions or [])[:2]:
        gap_queries.append(sq)

    async def _single_gap_search(q: str) -> Optional[Any]:
        try:
            return await call_tool_internal(
                "search_web",
                {
                    "query": q,
                    "max_results": 10,
                    "engine": "google",
                    "vertical": "organic",
                    "location_code": location_code,
                    "language_code": language_code,
                },
                timeout=DEFAULT_TIMEOUT_SEARCH,
            )
        except Exception as e:
            logger.error(f"Gap-Search-Fehler ({q[:40]}): {e}")
            return None

    raw_results = await asyncio.gather(*[_single_gap_search(q) for q in gap_queries])

    all_gap: List[Dict[str, Any]] = []
    for result in raw_results:
        if result is None:
            continue
        if isinstance(result, list):
            all_gap.extend(result)
        elif isinstance(result, dict):
            if "error" not in result and "results" in result:
                all_gap.extend(result.get("results", []))
            elif "error" not in result:
                all_gap.append(result)

    new_results: List[Dict[str, Any]] = []
    for r in all_gap:
        if not isinstance(r, dict):
            continue
        url = r.get("url", "")
        if not url:
            continue
        canonical = session._get_canonical_url(url)
        if canonical in session.visited_urls:
            continue
        url_lower = url.lower()
        title = str(r.get("title") or "")
        snippet = str(r.get("snippet") or "")
        combined_text = f"{title} {snippet} {url_lower}".lower()
        anchor_hits = _count_term_matches(plan.anchor_terms, combined_text)
        focus_hits = _count_term_matches(plan.focus_terms, combined_text)
        must_hits = _count_term_matches(plan.must_have_terms, combined_text)
        include_hits = _count_term_matches(plan.include_terms, combined_text)
        exclude_hits = _count_term_matches(plan.exclude_terms, combined_text)
        related_hits = _count_term_matches(plan.related_terms, combined_text)
        score = 0.35
        if any(d in url_lower for d in [".gov", ".edu", ".org"]):
            score += 0.18
        if "wikipedia" in url_lower:
            score += 0.12
        if ".pdf" in url_lower:
            score += 0.10
        if any(s in url_lower for s in ["facebook.com", "twitter.com", "instagram.com", "tiktok.com"]):
            score -= 0.22
        if "arxiv.org" in url_lower:
            score += 0.22
        if "github.com" in url_lower:
            score += 0.12
        if any(d in url_lower for d in ["nature.com", "sciencedirect.com", "springer.com", "wiley.com"]):
            score += 0.20
        if any(d in url_lower for d in ["reuters.com", "bloomberg.com", "ft.com"]):
            score += 0.12
        if any(d in url_lower for d in ["statista.com", "gartner.com", "mckinsey.com"]):
            score += 0.15
        if must_hits >= 1:
            score += 0.18
        score += min(anchor_hits * 0.08 + focus_hits * 0.08 + include_hits * 0.04 + related_hits * 0.03, 0.46)
        score -= min(exclude_hits * 0.12, 0.36)
        r["score"] = max(0.0, min(score, 1.0))
        r["canonical_url"] = canonical
        new_results.append(r)

    new_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    top_new = new_results[:8]

    if not top_new:
        logger.info("Phase 3.5: Keine neuen Quellen gefunden.")
        return

    logger.info(f"Phase 3.5: {len(top_new)} neue Quellen werden verarbeitet...")
    tasks = [_process_source_safe(r, session, semaphore, config) for r in top_new]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Gap-Filling Fehler bei Quelle {i}: {result}")

    session.methodology_notes.append(
        f"Phase 3.5 Gap-Filling: {len(top_new)} neue Quellen analysiert "
        f"(vorher: {facts_count} Fakten, {tree_count} Quellen)"
    )


async def _evaluate_relevance(
    sources: List[Dict],
    session: DeepResearchSession,
    max_sources_to_return: int
) -> List[Tuple[Dict, float]]:
    """Bewertet Relevanz der Quellen."""
    logger.info(f"⚖️ Bewerte Relevanz von {len(sources)} Quellen...")

    relevant: List[Tuple[Dict, float]] = []
    plan = _ensure_research_plan(session)

    for source in sources:
        base_score = source.get("score", 0.5)

        title = source.get("title", "").lower()
        snippet = source.get("snippet", "").lower()
        url = str(source.get("canonical_url") or source.get("url") or "").lower()
        combined_text = f"{title} {snippet} {url}"

        anchor_hits = _count_term_matches(plan.anchor_terms, combined_text)
        focus_hits = _count_term_matches(plan.focus_terms, combined_text)
        must_hits = _count_term_matches(plan.must_have_terms, combined_text)
        include_hits = _count_term_matches(plan.include_terms, combined_text)
        exclude_hits = _count_term_matches(plan.exclude_terms, combined_text)
        related_hits = _count_term_matches(plan.related_terms, combined_text)

        keyword_bonus = min(anchor_hits * 0.08 + focus_hits * 0.08 + include_hits * 0.04 + related_hits * 0.03, 0.48)
        penalty = min(exclude_hits * 0.12, 0.36)
        if plan.scope_mode == "strict" and must_hits == 0 and anchor_hits == 0 and focus_hits == 0 and include_hits < 2:
            penalty += 0.18
        elif plan.scope_mode == "strict" and plan.must_have_terms and must_hits == 0 and anchor_hits + focus_hits <= 1:
            penalty += 0.08
        elif plan.scope_mode == "landscape" and anchor_hits == 0 and related_hits == 0 and include_hits < 2:
            penalty += 0.08

        final_score = base_score + keyword_bonus - penalty
        if _is_text_on_session_topic(session, combined_text) and final_score >= MIN_RELEVANCE_SCORE_FOR_SOURCES:
            source["relevance_breakdown"] = {
                "anchor_hits": anchor_hits,
                "focus_hits": focus_hits,
                "must_hits": must_hits,
                "include_hits": include_hits,
                "exclude_hits": exclude_hits,
                "related_hits": related_hits,
                "base_score": round(float(base_score), 3),
                "final_score": round(float(final_score), 3),
            }
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


def _needs_scrapingant(url: str) -> bool:
    """Rueckwaertskompatibler Wrapper fuer den gemeinsamen Domain-Guard."""
    return social_media_needs_scrapingant(url)


async def _fetch_via_scrapingant(url: str) -> str:
    """Holt Seiteninhalt ueber den gemeinsamen ScrapingAnt-Adapter."""
    result = await fetch_page_text_via_scrapingant(url, render_js=True, max_chars=12000)
    return str(result.get("content") or "")


async def _fetch_page_content(url: str) -> str:
    """
    Holt Seiteninhalt via direktem HTTP-Request (kein Browser nötig).

    Fallback-Kette:
    1. PDF-URLs  → extract_text_from_pdf Tool
    2. Social-Media / JS-heavy → ScrapingAnt (wenn API-Key vorhanden)
    3. Normale HTML-Seiten → direktes httpx
    4. Bei 403/429/Timeout → ScrapingAnt-Fallback
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

        # Social Media / JS-heavy Domains: direkt ScrapingAnt
        if _needs_scrapingant(url):
            return await _fetch_via_scrapingant(url)

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
        status = e.response.status_code
        logger.warning(f"HTTP {status} für {url}")
        # Bei Blockierung: ScrapingAnt-Fallback versuchen
        if status in (403, 429, 503) and get_scrapingant_api_key():
            logger.info(f"ScrapingAnt-Fallback nach HTTP {status}: {url}")
            return await _fetch_via_scrapingant(url)
        return ""
    except httpx.TimeoutException:
        logger.warning(f"Timeout beim Abrufen von {url}")
        if get_scrapingant_api_key():
            logger.info(f"ScrapingAnt-Fallback nach Timeout: {url}")
            return await _fetch_via_scrapingant(url)
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
        plan = _ensure_research_plan(session)
        node.quality_metrics = await _evaluate_source_quality(
            node,
            content,
            query=session.query,
            plan=plan,
        )
        node.relevance_score = node.quality_metrics.scope_fit_score

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
    contract_export = session.export_contract_v2()
    plan = _ensure_research_plan(session)
    claims = contract_export.get("claims", [])
    confirmed_count = sum(1 for claim in claims if claim.get("verdict") == "confirmed")
    likely_count = sum(1 for claim in claims if claim.get("verdict") == "likely")
    mixed_count = sum(1 for claim in claims if claim.get("verdict") in {"mixed_evidence", "contested"})
    vendor_only_count = sum(1 for claim in claims if claim.get("verdict") == "vendor_claim_only")
    insufficient_count = sum(1 for claim in claims if claim.get("verdict") == "insufficient_evidence")
    return {
        "original_query": session.query,
        "focus_areas": session.focus_areas,
        "research_plan": {
            "primary_question": plan.primary_question,
            "query_language": plan.query_language,
            "profile": plan.profile,
            "scope_mode": plan.scope_mode,
            "query_variants": plan.query_variants,
            "subquestions": plan.subquestions,
            "must_have_terms": plan.must_have_terms,
            "exclude_terms": plan.exclude_terms[:10],
            "strict_topic": plan.strict_topic,
        },
        "query_variant_worker": session.research_metadata.get("query_variant_worker", {}),
        "semantic_claim_dedupe": session.research_metadata.get("semantic_claim_dedupe", {}),
        "conflict_scan_worker": session.research_metadata.get("conflict_scan_worker", {}),
        "narrative_report": session.research_metadata.get("narrative_report", {}),
        "start_time": session.start_time,
        "total_sources_processed": len(session.visited_urls),
        "total_facts_extracted": len(session.all_extracted_facts_raw),
        "verified_facts_count": len(session.verified_facts),
        "unverified_claims_count": len(session.unverified_claims),
        "conflicts_count": len(session.conflicting_info),
        "contract_claims_count": len(claims),
        "confirmed_claims_count": confirmed_count,
        "likely_claims_count": likely_count,
        "mixed_claims_count": mixed_count,
        "vendor_only_claims_count": vendor_only_count,
        "insufficient_claims_count": insufficient_count,
        "source_quality_distribution": session.source_quality_summary,
        "bias_distribution": session.bias_summary,
        "thesis_analyses_count": len(session.thesis_analyses)
    }


def _claim_verdict_label(verdict: str) -> str:
    return {
        "confirmed": "Confirmed",
        "likely": "Likely",
        "mixed_evidence": "Mixed Evidence",
        "contested": "Contested",
        "vendor_claim_only": "Vendor Claim Only",
        "insufficient_evidence": "Insufficient Evidence",
    }.get(verdict, verdict.replace("_", " ").title())


def _source_flag_string(source: Any) -> str:
    flags = []
    if getattr(source, "is_primary", False):
        flags.append("primary")
    if getattr(source, "is_official", False):
        flags.append("official")
    if getattr(source, "has_transcript", False):
        flags.append("transcript")
    if getattr(source, "has_methodology", False):
        flags.append("methodology")
    return ", ".join(flags) if flags else "-"


def _research_confidence_snapshot(
    *,
    robust_claim_count: int,
    contract_claims_count: int,
    high_quality_percent: float,
    source_fit_percent: float,
) -> tuple[str, str]:
    reliability_rate = robust_claim_count / max(contract_claims_count, 1)
    if robust_claim_count >= 3 and reliability_rate >= 0.6 and high_quality_percent >= 60 and source_fit_percent >= 70:
        return "Hoch", "mehrere belastbare Claims werden von einer ueberwiegend starken Quellenbasis getragen"
    if robust_claim_count >= 1 and reliability_rate >= 0.3 and source_fit_percent >= 50:
        return "Mittel", "erste belastbare Claims liegen vor, die Evidenz ist aber noch nicht in allen Teilfragen gleich dicht"
    if source_fit_percent < 45:
        return "Niedrig", "ein grosser Teil der Quellen zahlt nicht direkt auf die Leitfrage ein"
    return "Niedrig", "die belastbare Evidenz ist noch zu duenn oder zu ungleichmaessig verteilt"


def _derive_research_state_from_metrics(
    *,
    quality_gate_passed: bool,
    source_count: int,
    claim_count: int,
    robust_claim_count: int,
    methodology_notes_count: int,
) -> str:
    if (
        quality_gate_passed
        and source_count >= 3
        and claim_count >= 3
        and robust_claim_count >= 3
        and methodology_notes_count >= 1
    ):
        return "completed"
    return "partial_research"


def _build_research_telemetry(session: DeepResearchSession) -> Dict[str, Any]:
    session.export_contract_v2()
    contract = session.contract_v2
    claims = list(contract.claims)
    sources = list(contract.sources)
    claim_summary = summarize_claims(claims)
    domain_scorecards = build_domain_scorecards(claims)
    source_tiers: Dict[str, int] = {}
    source_types: Dict[str, int] = {}
    for source in sources:
        source_tiers[source.tier.value] = source_tiers.get(source.tier.value, 0) + 1
        source_types[source.source_type.value] = source_types.get(source.source_type.value, 0) + 1
    return {
        "claim_summary": claim_summary,
        "domain_scorecards": domain_scorecards,
        "source_tiers": source_tiers,
        "source_types": source_types,
        "evidence_count": len(contract.evidences),
        "open_questions_count": len(contract.open_questions),
        "methodology_notes_count": len(session.methodology_notes),
        "limitations_count": len(session.limitations),
        "primary_sources_count": sum(1 for source in sources if source.is_primary),
        "official_sources_count": sum(1 for source in sources if source.is_official),
        "transcript_sources_count": sum(1 for source in sources if source.has_transcript),
        "source_count": len(sources),
    }


def _assess_research_completion(
    session: DeepResearchSession,
    *,
    quality_gate_passed: bool,
    fallback_triggered: bool,
) -> Dict[str, Any]:
    telemetry = _build_research_telemetry(session)
    claim_summary = telemetry["claim_summary"]
    robust_claim_count = int(claim_summary.get("confirmed", 0)) + int(claim_summary.get("likely", 0))
    criteria = {
        "quality_gate_passed": bool(quality_gate_passed),
        "minimum_sources_met": int(telemetry["source_count"]) >= 3,
        "minimum_claims_met": int(claim_summary.get("total", 0)) >= 3,
        "minimum_robust_claims_met": robust_claim_count >= 3,
        "methodology_recorded": int(telemetry["methodology_notes_count"]) >= 1,
    }
    state = _derive_research_state_from_metrics(
        quality_gate_passed=criteria["quality_gate_passed"],
        source_count=int(telemetry["source_count"]),
        claim_count=int(claim_summary.get("total", 0)),
        robust_claim_count=robust_claim_count,
        methodology_notes_count=int(telemetry["methodology_notes_count"]),
    )
    stop_reasons: List[str] = []
    if not criteria["quality_gate_passed"]:
        stop_reasons.append("quality_gate_not_met")
    if not criteria["minimum_sources_met"]:
        stop_reasons.append("insufficient_source_coverage")
    if not criteria["minimum_claims_met"]:
        stop_reasons.append("insufficient_claim_coverage")
    if not criteria["minimum_robust_claims_met"]:
        stop_reasons.append("insufficient_robust_claims")
    if not criteria["methodology_recorded"]:
        stop_reasons.append("methodology_not_recorded")
    if telemetry["open_questions_count"] > 0:
        stop_reasons.append("open_questions_present")
    if claim_summary.get("contested", 0) or claim_summary.get("mixed_evidence", 0):
        stop_reasons.append("conflicting_claims_present")
    return {
        "state": state,
        "criteria": criteria,
        "stop_reasons": stop_reasons,
        "robust_claim_count": robust_claim_count,
        "fallback_triggered": bool(fallback_triggered),
        "open_questions_count": int(telemetry["open_questions_count"]),
        "telemetry": telemetry,
    }


def _source_fit_snapshot(session: DeepResearchSession) -> Dict[str, float]:
    scored_nodes = [
        node for node in list(session.research_tree or [])
        if getattr(node, "quality_metrics", None) is not None
    ]
    if not scored_nodes:
        return {
            "avg_scope_fit": 0.0,
            "direct_fit_percent": 0.0,
            "weak_fit_percent": 0.0,
        }

    scores = [float(node.quality_metrics.scope_fit_score or 0.0) for node in scored_nodes]
    direct_fit_count = sum(1 for score in scores if score >= 0.55)
    weak_fit_count = sum(1 for score in scores if score < 0.35)
    total = max(len(scores), 1)
    return {
        "avg_scope_fit": round(sum(scores) / total, 3),
        "direct_fit_percent": (direct_fit_count / total) * 100,
        "weak_fit_percent": (weak_fit_count / total) * 100,
    }


def _calibrate_negative_evidence_summary(summary: str, source_fit: Dict[str, float]) -> str:
    text = _normalize_space(summary)
    if not text:
        return text
    direct_fit_percent = float(source_fit.get("direct_fit_percent") or 0.0)
    weak_fit_percent = float(source_fit.get("weak_fit_percent") or 0.0)
    if direct_fit_percent >= 45 and weak_fit_percent < 60:
        return text

    lowered = text.lower()
    if any(token in lowered for token in ("falschinformation", "fakenews", "gerücht", "geruecht")):
        text = re.sub(r"\b(falschinformation|fakenews|gerücht|geruecht)\b", "nicht belastbar belegt", text, flags=re.IGNORECASE)
    caution = (
        "Hinweis: Die Quellenbasis ist thematisch nur teilweise passend; "
        "Negativbefunde sind daher als 'in den geprueften Quellen kein belastbarer Beleg' "
        "zu lesen, nicht als vollstaendiger Ausschluss."
    )
    if caution.lower() not in text.lower():
        text = f"{caution} {text}".strip()
    return text


async def _synthesize_findings(session: DeepResearchSession, verification_output: Dict) -> Dict:
    """Erstellt KI-Synthese."""
    logger.info("📝 Erstelle Synthese...")
    plan = _ensure_research_plan(session)
    conflict_scan_context = _get_conflict_scan_report_context(session)
    source_fit = _source_fit_snapshot(session)

    facts = verification_output.get("verified_facts", [])[:30]

    if not facts:
        return {
            "executive_summary": "Keine verifizierten Fakten gefunden.",
            "key_findings": [],
            "research_metadata_summary": _get_research_metadata_summary(session)
        }

    facts_text = "\n".join([f"- {f.get('fact')}" for f in facts[:20]])
    plan_text = (
        f"LEITFRAGE: {plan.primary_question}\n"
        f"SCOPE-MODUS: {plan.scope_mode}\n"
        f"TEILFRAGEN: {' | '.join(plan.subquestions[:4])}\n"
        f"MUSS-BEGRIFFE: {', '.join(plan.must_have_terms[:6])}\n"
        f"AUSSCHLUESSE: {', '.join(plan.exclude_terms[:8])}\n"
    )
    conflict_scan_text = ""
    if (
        conflict_scan_context["conflicts"]
        or conflict_scan_context["open_questions"]
        or conflict_scan_context["weak_evidence_flags"]
        or conflict_scan_context["report_notes"]
    ):
        lines = ["KONFLIKT-SCAN-HINWEISE:"]
        for item in conflict_scan_context["conflicts"][:4]:
            lines.append(
                f"- Konflikt: {item.get('claim_text') or '-'} | "
                f"{item.get('issue_type') or 'conflict'} | {item.get('reason') or '-'}"
            )
        for item in conflict_scan_context["weak_evidence_flags"][:4]:
            lines.append(
                f"- Schwache Evidenz: {item.get('claim_text') or '-'} | {item.get('reason') or '-'}"
            )
        for item in conflict_scan_context["open_questions"][:4]:
            lines.append(f"- Offene Frage: {item}")
        for item in conflict_scan_context["report_notes"][:3]:
            lines.append(f"- Report-Hinweis: {item}")
        conflict_scan_text = "\n".join(lines) + "\n"

    prompt = f"""Erstelle eine strukturierte Analyse für "{session.query}".

RECHERCHEPLAN:
{plan_text}

VERIFIZIERTE FAKTEN:
{facts_text}

{conflict_scan_text}

WICHTIG:
- Bleibe strikt innerhalb des Rechercheplans.
- Verwerfe Randthemen und administrative Details.
- Hebe offene Fragen nur dann hervor, wenn sie direkt zur Leitfrage gehoeren.
- Nutze Konflikt-Scan-Hinweise nur als vorsichtige Report-Signale, nicht als neue Fakten.
- Wenn die Quellenbasis thematisch indirekt oder duenn ist, formuliere Negativbefunde nur als
  "in den geprueften Quellen kein belastbarer Beleg", NICHT als absoluten Ausschluss,
  "Falschinformation" oder endgueltiges Debunking.

QUELLENPASSUNG:
- Direkte Quellenpassung: {source_fit['direct_fit_percent']:.0f}%
- Schwache Quellenpassung: {source_fit['weak_fit_percent']:.0f}%

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
        data["executive_summary"] = _calibrate_negative_evidence_summary(
            str(data.get("executive_summary") or ""),
            source_fit,
        )
        data["research_metadata_summary"] = _get_research_metadata_summary(session)
        return data

    except Exception as e:
        logger.error(f"Synthese-Fehler: {e}")
        return {
            "executive_summary": _calibrate_negative_evidence_summary(
                f"Recherche zu '{session.query}' abgeschlossen.",
                source_fit,
            ),
            "key_findings": [f.get("fact") for f in facts[:5]],
            "research_metadata_summary": _get_research_metadata_summary(session)
        }



# ==============================================================================
# DRUCKREIFER REPORT-GENERATOR (NEU v5.0 - ACADEMIC EXCELLENCE)
# ==============================================================================

def _create_academic_markdown_report(session: DeepResearchSession, include_methodology: bool = True) -> str:
    """
    Erstellt einen druckreifen Report im wissenschaftlichen Stil.

    Phase 5:
    - Executive Verdict Table
    - Domain Scorecards
    - Claim Register
    - Conflicts & Unknowns
    - Quellenanhang mit Tier/Typ/Bias
    """
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    session.export_contract_v2()
    plan = _ensure_research_plan(session)
    contract = session.contract_v2
    meta = _get_research_metadata_summary(session)
    claims = sort_claims_for_report(list(contract.claims))
    claim_summary = summarize_claims(claims)
    scorecards = build_domain_scorecards(claims)
    source_by_id = {source.source_id: source for source in contract.sources}
    confirmed_claims = meta["confirmed_claims_count"]
    likely_claims = meta["likely_claims_count"]
    mixed_claims = meta["mixed_claims_count"]
    vendor_only_claims = meta["vendor_only_claims_count"]
    insufficient_claims = meta["insufficient_claims_count"]
    contract_claims = meta["contract_claims_count"]
    robust_claim_count = confirmed_claims + likely_claims
    excellent_count = session.source_quality_summary.get("excellent", 0)
    good_count = session.source_quality_summary.get("good", 0)
    high_quality_percent = ((excellent_count + good_count) / max(meta["total_sources_processed"], 1) * 100)
    source_fit = _source_fit_snapshot(session)
    confidence_label, confidence_reason = _research_confidence_snapshot(
        robust_claim_count=robust_claim_count,
        contract_claims_count=contract_claims,
        high_quality_percent=high_quality_percent,
        source_fit_percent=source_fit["direct_fit_percent"],
    )
    conflict_claims = [
        claim for claim in claims
        if claim.verdict in {ClaimVerdict.CONTESTED, ClaimVerdict.MIXED_EVIDENCE} or claim.unknowns
    ]
    open_questions = list(dict.fromkeys(contract.open_questions))
    conflict_scan_context = _get_conflict_scan_report_context(session)

    lines: List[str] = []

    lines.extend([
        "# Tiefenrecherche-Bericht",
        f"## {session.query}",
        "",
        "---",
        "",
        f"**Datum:** {now}",
        "**Research Engine:** Timus Deep Research v8.1 - Evidence Engine",
        f"**Analysierte Quellen:** {meta['total_sources_processed']}",
        (
            f"**Claim-Status:** {confirmed_claims} confirmed, {likely_claims} likely, "
            f"{mixed_claims} mixed/contested, {vendor_only_claims} vendor-only, "
            f"{insufficient_claims} insufficient"
        ),
        "",
    ])

    if session.focus_areas:
        lines.extend([
            f"**Fokusthemen:** {', '.join(session.focus_areas)}",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Executive Briefing",
        "",
        f"**Forschungsfrage:** {session.query}",
        "",
    ])

    if claims:
        lines.extend([
            (
                f"**Kurzurteil:** Auf Basis von {meta['total_sources_processed']} Quellen lassen sich "
                f"{robust_claim_count} von {contract_claims} strukturierten Claims als belastbar "
                f"(confirmed/likely) einordnen. Gleichzeitig bleiben "
                f"{mixed_claims + vendor_only_claims + insufficient_claims} Claims strittig, eingeschraenkt "
                f"oder noch nicht tragfaehig belegt."
            ),
            "",
            f"**Confidence:** {confidence_label} - {confidence_reason}.",
            "",
            (
                "**Leserichtung:** Zuerst folgen die Kernthesen, offenen Konflikte und Schlussfolgerungen. "
                "Der anschliessende analytische Teil dokumentiert die Evidenzstruktur, Methodik und das Claim-Register."
            ),
            "",
        ])
    else:
        lines.extend([
            "**Kurzurteil:** Die Recherche hat noch keine ausreichend tragfaehigen strukturierten Claims geliefert.",
            "",
            "**Confidence:** Niedrig - die Evidenzbasis ist fuer ein belastbares Urteil noch zu duenn.",
            "",
        ])

    if session.source_quality_summary:
        lines.extend([
            f"**Quellenqualitaet:** {high_quality_percent:.0f}% der Quellen wurden als 'Excellent' oder 'Good' eingestuft.",
            "",
        ])
    if meta["total_sources_processed"] > 0:
        lines.extend([
            f"**Quellenpassung:** {source_fit['direct_fit_percent']:.0f}% der Quellen zahlen direkt auf die Leitfrage ein.",
            "",
        ])
    if source_fit["direct_fit_percent"] < 45:
        lines.extend([
            (
                "**Einschraenkung:** Ein grosser Teil der Quellen ist thematisch nur indirekt passend. "
                "Negative Befunde sind deshalb vor allem als 'in den geprueften Quellen kein belastbarer Beleg' "
                "zu lesen, nicht als vollstaendiger Ausschluss."
            ),
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Kernthesen",
        "",
    ])

    if claims:
        for idx, claim in enumerate(claims[:5], 1):
            lines.extend([
                f"### These {idx}",
                "",
                f"**Kernaussage:** {claim.claim_text}",
                "",
                (
                    f"**Einordnung:** Verdict {_claim_verdict_label(claim.verdict.value)}, "
                    f"Domain {claim.domain}, Confidence {claim.confidence:.2f}, "
                    f"{len(claim.supports)} unterstuetzende und {len(claim.contradicts)} widersprechende Evidenzen."
                ),
                "",
            ])
            if claim.unknowns:
                lines.append(f"**Grenzen:** {', '.join(claim.unknowns[:4])}")
                lines.append("")
    else:
        lines.extend([
            "_Keine belastbaren Kernthesen verfuegbar._",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Conflicts & Unknowns",
        "",
    ])

    if (
        conflict_claims
        or session.conflicting_info
        or open_questions
        or conflict_scan_context["conflicts"]
        or conflict_scan_context["weak_evidence_flags"]
        or conflict_scan_context["open_questions"]
        or conflict_scan_context["report_notes"]
    ):
        lines.extend([
            "### Konfliktbehaftete Claims",
            "",
        ])
        for idx, claim in enumerate(conflict_claims[:10], 1):
            lines.extend([
                f"**Claim #{idx}:** {claim.claim_text}",
                f"- **Verdict:** {_claim_verdict_label(claim.verdict.value)}",
                f"- **Unknowns:** {', '.join(claim.unknowns[:4]) if claim.unknowns else '-'}",
                f"- **Hinweise:** {claim.notes or '-'}",
                "",
            ])
        if session.conflicting_info:
            lines.extend(["### Laufzeit-Konflikte aus der Verifikation", ""])
            for idx, conflict in enumerate(session.conflicting_info[:5], 1):
                lines.extend([
                    f"**Konflikt #{idx}:**",
                    f"- **Fakt:** {conflict.get('fact', 'N/A')}",
                    f"- **Interne Confidence:** {conflict.get('internal_confidence', 0):.2f}",
                    f"- **Corroborator Confidence:** {conflict.get('corroborator_confidence', 0):.2f}",
                    f"- **Hinweis:** {conflict.get('note', '')}",
                    "",
                ])
        if open_questions:
            lines.extend(["### Offene Fragen", ""])
            for idx, item in enumerate(open_questions[:10], 1):
                lines.append(f"{idx}. {item}")
            lines.append("")
        if (
            conflict_scan_context["conflicts"]
            or conflict_scan_context["weak_evidence_flags"]
            or conflict_scan_context["open_questions"]
            or conflict_scan_context["report_notes"]
        ):
            lines.extend(["### Zusätzliche Conflict-Scan-Hinweise", ""])
            for idx, item in enumerate(conflict_scan_context["conflicts"][:6], 1):
                lines.extend([
                    f"**Scan-Konflikt #{idx}:** {item.get('claim_text') or '-'}",
                    f"- **Typ:** {item.get('issue_type') or 'conflict'}",
                    f"- **Hinweis:** {item.get('reason') or '-'}",
                    f"- **Confidence:** {float(item.get('confidence') or 0.0):.2f}",
                    "",
                ])
            if conflict_scan_context["weak_evidence_flags"]:
                lines.extend(["### Schwache Evidenz-Signale", ""])
                for idx, item in enumerate(conflict_scan_context["weak_evidence_flags"][:6], 1):
                    lines.extend([
                        f"**Signal #{idx}:** {item.get('claim_text') or '-'}",
                        f"- **Hinweis:** {item.get('reason') or '-'}",
                        f"- **Confidence:** {float(item.get('confidence') or 0.0):.2f}",
                        "",
                    ])
            if conflict_scan_context["open_questions"]:
                lines.extend(["### Weitere offene Fragen aus dem Conflict-Scan", ""])
                for idx, item in enumerate(conflict_scan_context["open_questions"][:8], 1):
                    lines.append(f"{idx}. {item}")
                lines.append("")
            if conflict_scan_context["report_notes"]:
                lines.extend(["### Report-Hinweise", ""])
                for item in conflict_scan_context["report_notes"][:6]:
                    lines.append(f"- {item}")
                lines.append("")
    else:
        lines.extend([
            "Derzeit zeigen die strukturierten Claims keine ausgepraegte Konfliktlage; offene Punkte betreffen vor allem Reichweite und Vollstaendigkeit der Evidenz.",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Schlussfolgerungen",
        "",
    ])

    if claims:
        claim_reliability_rate = (robust_claim_count / max(contract_claims, 1) * 100)
        lines.extend([
            (
                f"Die Recherche liefert derzeit {robust_claim_count} belastbare Claims aus {contract_claims} "
                f"strukturierten Claims ({claim_reliability_rate:.1f}% confirmed/likely). "
                "Am belastbarsten sind die Aussagen mit mehreren unterstuetzenden Evidenzen und klarer Domain-Zuordnung."
            ),
            "",
        ])
        if session.thesis_analyses:
            lines.extend(["**Zentrale Schlussfolgerungen:**", ""])
            for idx, analysis in enumerate(session.thesis_analyses, 1):
                if analysis.synthesis:
                    lines.append(f"{idx}. **{analysis.topic}:** {analysis.synthesis}")
            lines.append("")
    else:
        lines.extend([
            "Die Recherche konnte noch keine ausreichend belastbaren Claims liefern; weitere Primaer- oder Vergleichsquellen sind erforderlich.",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Executive Verdict Table",
        "",
        "| Verdict | Count | Bedeutung |",
        "|---------|-------|-----------|",
        f"| Confirmed | {claim_summary['confirmed']} | Mehrere starke, profilkonforme Evidenzen |",
        f"| Likely | {claim_summary['likely']} | Gute, aber noch nicht maximale Evidenzbasis |",
        f"| Mixed / Contested | {claim_summary['mixed_evidence'] + claim_summary['contested']} | Widerspruechliche oder gemischte Evidenz |",
        f"| Vendor Claim Only | {claim_summary['vendor_claim_only']} | Nur Anbieter-/Eigenclaim |",
        f"| Insufficient | {claim_summary['insufficient_evidence']} | Noch keine tragfaehige Evidenz |",
        "",
        "---",
        "",
        "## Domain Scorecards",
        "",
    ])

    if scorecards:
        lines.extend([
            "| Domain | Total | Confirmed | Likely | Mixed | Vendor-only | Insufficient | Avg Confidence |",
            "|--------|-------|-----------|--------|-------|-------------|--------------|----------------|",
        ])
        for row in scorecards:
            lines.append(
                f"| {row['domain']} | {row['total']} | {row['confirmed']} | {row['likely']} | "
                f"{row['mixed']} | {row['vendor_only']} | {row['insufficient']} | {row['avg_confidence']:.2f} |"
            )
        lines.append("")
    else:
        lines.extend([
            "_Noch keine Domain-Scorecards verfuegbar._",
            "",
        ])

    lines.extend(["---", ""])

    if include_methodology:
        lines.extend([
            "## Methodik",
            "",
            "### Recherche-Ansatz",
            "",
            "Diese Tiefenrecherche wurde mit Multi-Query-Websuche, Quellenklassifikation, Claim->Evidence->Verdict-Logik und optionalem Fact-Corroborator durchgefuehrt.",
            "",
            f"- Verifikations-Modus: {'Strikt (≥3 Quellen)' if 'strict' in str(session.research_metadata.get('verification_mode', '')) else 'Moderat (≥2 Quellen)'}",
            f"- Scope-Modus: {plan.scope_mode}",
            f"- Query-Plan: {len(plan.query_variants)} Suchvarianten, {len(plan.subquestions)} Teilfragen",
            f"- Muss-Begriffe: {', '.join(plan.must_have_terms[:6]) or '-'}",
            "- Claim-Verdicts: confirmed, likely, mixed/contested, vendor-only, insufficient",
            "- Profile-aware Beweismassstaebe fuer News, Scientific, Policy, Vendor Comparison usw.",
            "",
            "### Rechercheplan",
            "",
            f"- Leitfrage: {plan.primary_question}",
        ])
        for idx, subquestion in enumerate(plan.subquestions[:4], 1):
            lines.append(f"- Teilfrage {idx}: {subquestion}")
        lines.extend([
            f"- Topic-Boundaries: {' | '.join(plan.topic_boundaries[:3])}",
            "",
            "---",
            "",
        ])

    lines.extend([
        "## Claim Register",
        "",
        "### Belastbare Claims",
        "",
    ])

    if claims:
        for idx, claim in enumerate(claims[:15], 1):
            support_sources = [source_by_id[sid] for sid in claim.supports if sid in source_by_id][:3]
            contradict_sources = [source_by_id[sid] for sid in claim.contradicts if sid in source_by_id][:3]
            support_note = ", ".join(
                f"{urlparse(src.url).netloc or src.title} ({src.tier.value}/{src.source_type.value})"
                for src in support_sources
            ) or "-"
            contrad_note = ", ".join(
                f"{urlparse(src.url).netloc or src.title} ({src.tier.value}/{src.source_type.value})"
                for src in contradict_sources
            ) or "-"

            lines.extend([
                f"### {idx}. {claim.claim_text}",
                "",
                f"- **Verdict:** {_claim_verdict_label(claim.verdict.value)}",
                f"- **Domain:** {claim.domain}",
                f"- **Confidence:** {claim.confidence:.2f}",
                f"- **Unterstuetzende Evidenzen:** {len(claim.supports)}",
                f"- **Widersprechende Evidenzen:** {len(claim.contradicts)}",
                f"- **Beispielquellen:** {support_note}",
            ])
            if claim.notes:
                lines.append(f"- **Hinweise:** {claim.notes}")
            if claim.unknowns:
                lines.append(f"- **Offene Punkte:** {', '.join(claim.unknowns[:4])}")
            if claim.contradicts:
                lines.append(f"- **Gegenevidenz:** {contrad_note}")
            lines.append("")
    else:
        lines.extend([
            "_Keine strukturierten Claims verfuegbar._",
            "",
        ])

    lines.extend(["---", ""])

    if session.thesis_analyses:
        lines.extend([
            "## These-Antithese-Synthese Analysen",
            "",
            "Die folgenden dialektischen Analysen vertiefen die Kernthesen und zeigen, wo die Evidenz robust, widerspruechlich oder noch unsicher ist.",
            "",
        ])
        for idx, analysis in enumerate(session.thesis_analyses, 1):
            lines.extend([
                f"### Analyse #{idx}: {analysis.topic}",
                "",
                "#### These",
                "",
                f"> {analysis.thesis}",
                "",
                f"**Confidence:** {analysis.thesis_confidence:.2f}",
                f"**Unterstuetzende Quellen:** {len(analysis.supporting_sources)}",
                "",
            ])
            if analysis.supporting_facts:
                lines.append("**Unterstuetzende Evidenz:**")
                for fact in analysis.supporting_facts[:3]:
                    lines.append(f"- {fact.get('fact')}")
                lines.append("")
            if analysis.antithesis:
                lines.extend([
                    "#### Antithese",
                    "",
                    f"> {analysis.antithesis}",
                    "",
                    f"**Confidence:** {analysis.antithesis_confidence:.2f}",
                    f"**Widersprechende Quellen:** {len(analysis.contradicting_sources)}",
                    "",
                ])
            if analysis.synthesis:
                lines.extend([
                    "#### Synthese",
                    "",
                    f"> {analysis.synthesis}",
                    "",
                    f"**Confidence:** {analysis.synthesis_confidence:.2f}",
                    "",
                ])
            lines.extend(["---", ""])

    if session.source_quality_summary or session.bias_summary:
        lines.extend(["## Quellenqualitaets-Analyse", ""])
        if session.source_quality_summary:
            lines.extend([
                "### Qualitaetsverteilung der Quellen",
                "",
                "| Qualitaetsstufe | Anzahl | Prozent |",
                "|-----------------|--------|---------|",
            ])
            total = max(1, sum(session.source_quality_summary.values()))
            for quality in ["excellent", "good", "medium", "poor", "unknown"]:
                count = session.source_quality_summary.get(quality, 0)
                percent = count / total * 100
                icon = {"excellent": "🟢", "good": "🟡", "medium": "🟠", "poor": "🔴", "unknown": "⚪"}.get(quality, "")
                lines.append(f"| {icon} {quality.capitalize()} | {count} | {percent:.1f}% |")
            lines.append("")
        if session.bias_summary:
            lines.extend([
                "### Bias-Analyse",
                "",
                "| Bias-Level | Anzahl | Prozent |",
                "|------------|--------|---------|",
            ])
            total = max(1, sum(session.bias_summary.values()))
            for bias in ["none", "low", "medium", "high", "unknown"]:
                count = session.bias_summary.get(bias, 0)
                percent = count / total * 100
                lines.append(f"| {bias.capitalize()} | {count} | {percent:.1f}% |")
            lines.append("")
        lines.extend(["---", ""])

    lines.extend([
        "## Limitationen & Unsicherheiten",
        "",
        "Diese Recherche unterliegt folgenden Limitationen:",
        "",
        f"1. **Quellenabdeckung:** Die Analyse basiert auf {meta['total_sources_processed']} Quellen.",
        "",
    ])
    poor_count = session.source_quality_summary.get("poor", 0)
    if poor_count > 0:
        poor_percent = poor_count / max(meta["total_sources_processed"], 1) * 100
        lines.extend([
            f"2. **Quellenqualitaet:** {poor_percent:.0f}% der Quellen wurden als 'Poor' eingestuft.",
            "",
        ])
    if meta["unverified_claims_count"] > 0:
        lines.extend([
            f"3. **Noch offene Claims:** {meta['unverified_claims_count']} extrahierte Aussagen konnten nicht in confirmed/likely Claims ueberfuehrt werden.",
            "",
        ])
    if open_questions:
        lines.extend([
            f"4. **Offene Fragen:** {len(open_questions)} Punkte bleiben explizit offen.",
            "",
        ])
    lines.extend([
        "5. **Zeitpunkt:** Diese Recherche wurde zum angegebenen Datum durchgefuehrt.",
        "",
        "---",
        "",
        "## Quellenanhang",
        "",
        "Alle im Research-Contract gefuehrten Quellen mit Tier-, Typ- und Bias-Metadaten:",
        "",
        "| # | Tier | Typ | Bias | Flags | Titel | URL |",
        "|---|------|-----|------|-------|-------|-----|",
    ])
    for idx, source in enumerate(sorted(contract.sources, key=lambda s: (s.tier.value, s.source_type.value, s.title.lower()))[:40], 1):
        title_short = source.title[:54] + "..." if len(source.title) > 54 else source.title
        domain = urlparse(source.url).netloc or source.url
        lines.append(
            f"| {idx} | {source.tier.value} | {source.source_type.value} | {source.bias_risk.value} | "
            f"{_source_flag_string(source)} | {title_short} | [{domain}]({source.url}) |"
        )

    lines.extend([
        "",
        "---",
        "",
        "### Ueber diesen Bericht",
        "",
        "Dieser Bericht wurde automatisiert von **Timus Deep Research v8.1 - Evidence Engine** erstellt.",
        "",
        "**Features:**",
        "- Claim -> Evidence -> Verdict",
        "- Profile-aware Verifikation",
        "- Quellenqualitaets-Bewertung",
        "- Bias-Erkennung",
        "- Transparente Methodik",
        "",
        f"**Generiert am:** {now}",
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
    digest = _build_narrative_digest(session)
    narrative_meta = {
        "strategy": "sectioned",
        "sections_attempted": [],
        "sections_completed": [],
        "compact_retry_used": False,
        "fallback_used": False,
    }

    section_specs = [
        {
            "title": "Einordnung",
            "material_keys": ["plan_text", "stats_text", "verified_lines", "source_lines"],
            "guidance": (
                "Ordne das Thema knapp ein, erklaere den Recherchefokus und was die aktuelle Evidenzlage "
                "ueberhaupt hergibt. Keine Detailflut, sondern Orientierung."
            ),
            "target_words": (140, 260),
            "max_tokens": 850,
        },
        {
            "title": "Belastbare Beobachtungen",
            "material_keys": ["verified_lines", "source_lines", "synthesis_lines"],
            "guidance": (
                "Fokussiere auf die tragfaehigsten, am besten belegten Punkte. Benenne Zusammenhaenge "
                "zwischen Fakten und halte dich eng an die Leitfrage."
            ),
            "target_words": (220, 380),
            "max_tokens": 1200,
        },
        {
            "title": "Hinweise und offene Punkte",
            "material_keys": ["unverified_lines", "conflict_lines", "open_questions", "report_notes"],
            "guidance": (
                "Erklaere, welche Hinweise noch duenn, widerspruechlich oder offen sind. "
                "Unsicherheit lieber klar benennen als kuenstlich glätten."
            ),
            "target_words": (180, 320),
            "max_tokens": 950,
        },
        {
            "title": "Analytische Verdichtung",
            "material_keys": ["synthesis_lines", "verified_lines", "conflict_lines", "report_notes"],
            "guidance": (
                "Verdichte die wichtigsten Muster, Grenzen und Spannungen zwischen den Quellen. "
                "Keine Wiederholung des Rohmaterials, sondern Einordnung."
            ),
            "target_words": (220, 380),
            "max_tokens": 1200,
        },
        {
            "title": "Fazit",
            "material_keys": ["stats_text", "verified_lines", "open_questions", "report_notes"],
            "guidance": (
                "Ziehe ein ehrliches Schlussfazit: Was ist belastbar, was bleibt offen, und wofuer reicht "
                "die aktuelle Recherche schon aus oder noch nicht."
            ),
            "target_words": (140, 260),
            "max_tokens": 850,
        },
    ]

    section_drafts: Dict[str, str] = {}
    for spec in section_specs:
        title = spec["title"]
        narrative_meta["sections_attempted"].append(title)
        section_text = await _generate_narrative_section(
            session=session,
            title=title,
            digest=digest,
            material_keys=spec["material_keys"],
            guidance=spec["guidance"],
            target_words=spec["target_words"],
            max_tokens=spec["max_tokens"],
        )
        if section_text and _narrative_word_count(section_text) >= 25:
            section_drafts[title] = section_text
            narrative_meta["sections_completed"].append(title)
        else:
            section_drafts[title] = ""

    section_texts = [section_drafts[spec["title"]] for spec in section_specs if section_drafts.get(spec["title"])]
    if _is_narrative_readable(section_texts):
        narrative = "\n\n".join(section_texts + [digest["sources_section"]]).strip()
    else:
        narrative_meta["compact_retry_used"] = True
        retry_narrative = await _create_compact_narrative_retry(session, digest, section_drafts)
        if (
            retry_narrative
            and _narrative_word_count(retry_narrative) >= 80
            and "## Einordnung" in retry_narrative
            and "## Fazit" in retry_narrative
        ):
            narrative = f"{retry_narrative}\n\n{digest['sources_section']}".strip()
        else:
            logger.warning("Narrative-Synthese blieb leer; nutze deterministischen Fallback.")
            narrative_meta["fallback_used"] = True
            narrative = _build_narrative_fallback_report(session)

    if not str(narrative or "").strip():
        logger.warning("Narrative-Synthese blieb leer; nutze deterministischen Fallback.")
        narrative_meta["fallback_used"] = True
        narrative = _build_narrative_fallback_report(session)
    elif _narrative_word_count(narrative) < 90:
        logger.warning(
            "Narrative-Synthese zu kurz (%s Woerter); erweitere per Fallback.",
            _narrative_word_count(narrative),
        )
        fallback = _build_narrative_fallback_report(session)
        narrative_meta["fallback_used"] = True
        narrative = f"{str(narrative).strip()}\n\n{fallback}".strip()

    session.research_metadata["narrative_report"] = narrative_meta

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
    word_count = _narrative_word_count(narrative)
    header = (
        f"# Recherche-Bericht\n"
        f"## {session.query}\n\n"
        f"*Erstellt am {now} | Timus Deep Research v8.1 - Evidence Engine | Basierend auf {source_count} Web-Quellen{extras_info} | {word_count:,} Wörter*\n\n"
        f"---\n\n"
    )
    return header + narrative


# ==============================================================================
# ÖFFENTLICHE RPC-METHODEN (erweitert für v5.0)
# ==============================================================================

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
    config = get_adaptive_config(query, current_session.focus_areas, max_depth)
    plan = _ensure_research_plan(current_session)
    current_session.research_metadata["research_plan"] = asdict(plan)
    if not any(str(note).startswith("Rechercheplan:") for note in current_session.methodology_notes):
        current_session.methodology_notes.append(
            f"Rechercheplan: {len(plan.query_variants)} Query-Varianten, "
            f"{len(plan.subquestions)} Teilfragen, scope_mode={plan.scope_mode}"
        )
    await _augment_query_variants_with_worker(
        current_session,
        session_id=session_id,
        max_queries=config["max_initial_search_queries"],
    )

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
        current_session,
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

    # PHASE 3.5: GAP-FILLING-SUCHE
    logger.info("🔎 Phase 3.5: Gap-Filling-Suche (bei schwacher Faktenlage)...")
    _gap_semaphore = asyncio.Semaphore(config.get("parallel_source_analysis_limit", 4))
    await _run_gap_filling_search(current_session, config, _gap_semaphore)

    # PHASE 4: ERWEITERTE FAKTEN-VERIFIKATION
    logger.info("🔍 Phase 4: Erweiterte Fakten-Verifikation (mit fact_corroborator)...")
    verified_data = await _deep_verify_facts(current_session, verification_mode)
    _prune_session_findings_to_topic(current_session)
    verified_data = {
        "verified_facts": current_session.verified_facts,
        "unverified_claims": current_session.unverified_claims,
        "conflicts": current_session.conflicting_info,
    }

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

    _prune_session_findings_to_topic(current_session)
    verified_data = {
        "verified_facts": current_session.verified_facts,
        "unverified_claims": current_session.unverified_claims,
        "conflicts": current_session.conflicting_info,
    }
    await _populate_semantic_claim_dedupe_cache(current_session, session_id=session_id)
    current_session.export_contract_v2()
    await _populate_conflict_scan_cache(current_session, session_id=session_id)

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


@tool(
    name="start_deep_research",
    description="Startet Timus Deep Research v8.1 - Evidence Engine mit Claim->Evidence->Verdict, profilgesteuerter Verifikation und Runtime-Guardrails.",
    parameters=[
        P("query", "string", "Die Hauptsuchanfrage"),
        P("focus_areas", "array", "Optionale Liste von Fokusthemen", required=False),
        P("scope_mode", "string", "Scope-Modus: auto, strict oder landscape", required=False, default="auto"),
        P("max_depth", "integer", "Maximale Tiefe der Recherche (1-5)", required=False),
        P("verification_mode", "string", "Verifikationsmodus: strict, moderate oder light", required=False, default="strict"),
    ],
    capabilities=["research", "deep_research"],
    category=C.RESEARCH
)
async def start_deep_research(
    query: str,
    focus_areas: Optional[List[str]] = None,
    scope_mode: str = "auto",
    max_depth: Optional[int] = None,
    verification_mode: str = "strict"
) -> dict:
    """
    Startet Timus Deep Research v8.1 - Evidence Engine.

    Kernmerkmale in v8.1:
    - Language-Detection → US-Location für englische Queries
    - Domain-aware Embedding-Threshold (Tech: 0.72)
    - Auto-Mode: strict + Tech → moderate
    - Corroborator für alle Fakten mit source_count ≥ 1
    - ArXiv Threshold 5 + topic-aware Fallback-Score
    - Qualitäts-Gate (verified ≥ 3) + automatischer light-Fallback
    - DrDiagnostics Integration
    - Claim -> Evidence -> Verdict
    - Profile-aware Beweismaßstäbe
    - Report/PDF aus Claim-Registern
    - partial_research statt falscher Sicherheit

    Args:
        query: Die Hauptsuchanfrage
        focus_areas: Optionale Liste von Fokusthemen
        scope_mode: "auto", "strict" oder "landscape"
        max_depth: Maximale Tiefe der Recherche (1-5)
        verification_mode: "strict", "moderate" oder "light"

    Returns:
        Success mit session_id und umfassenden Analyseergebnissen
    """
    session_id = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    current_session = DeepResearchSession(query, focus_areas, scope_mode=scope_mode)
    plan = _ensure_research_plan(current_session)
    research_sessions[session_id] = current_session

    # v8.1: Diagnostics initialisieren
    try:
        from tools.deep_research.diagnostics import reset as diag_reset
        diag = diag_reset()
        diag.query = query
        diag.verification_mode_req = verification_mode
    except Exception:
        pass

    # Metadaten speichern
    current_session.research_metadata = {
        "session_id": session_id,
        "verification_mode": verification_mode,
        "max_depth": max_depth,
        "version": "8.1",
        "scope_mode": plan.scope_mode,
        "research_plan": asdict(plan),
    }

    try:
        logger.info(f"🔬 Starte Timus Deep Research v8.1 - Evidence Engine Session {session_id}: '{query}'")

        # v8.1: Pipeline ausführen
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

        # v8.1: Qualitäts-Gate + automatischer light-Fallback
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

            fallback_session = DeepResearchSession(query, focus_areas, scope_mode=scope_mode)
            fallback_session.research_metadata = {
                "session_id": session_id,
                "verification_mode": "light",
                "max_depth": max_depth,
                "version": "8.1",
                "scope_mode": _ensure_research_plan(fallback_session).scope_mode,
                "research_plan": asdict(_ensure_research_plan(fallback_session)),
            }
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

        completion_summary = _assess_research_completion(
            current_session,
            quality_gate_passed=quality_ok,
            fallback_triggered=fallback_triggered,
        )
        research_state = completion_summary["state"]
        telemetry = completion_summary["telemetry"]
        if research_state != "completed":
            partial_note = (
                f"Research beendet als partial_research: {', '.join(completion_summary['stop_reasons']) or 'unbekannte_guardrail'}"
            )
            if partial_note not in current_session.limitations:
                current_session.limitations.append(partial_note)
            current_session.methodology_notes.append(
                f"Guardrail-State: {research_state} ({', '.join(completion_summary['stop_reasons']) or 'no_stop_reasons'})"
            )

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
            "status": research_state,
            "version": "8.1",
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
            "completion_summary": completion_summary,
            "telemetry": telemetry,
            "source_quality_summary": current_session.source_quality_summary,
            "bias_summary": current_session.bias_summary,
            "research_plan": asdict(_ensure_research_plan(current_session)),
            "analysis": analysis,
            "verified_data": verified_data,
            "report_filepath": filepath,
            "artifacts": _build_report_artifacts(filepath),
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

    summary = _get_research_metadata_summary(session)
    completion_summary = _assess_research_completion(
        session,
        quality_gate_passed=len(session.verified_facts) >= 3,
        fallback_triggered=False,
    )
    return {
        "session_id": session_id,
        "query": session.query,
        "summary": summary,
        "status": completion_summary["state"],
        "completion_summary": completion_summary,
        "telemetry": completion_summary["telemetry"],
    }


@tool(
    name="generate_research_report",
    description="Erstellt einen druckreifen Bericht aus Timus Deep Research v8.1 - Evidence Engine mit Verdict-Table, Scorecards, Claim-Register und Quellenanhang.",
    parameters=[
        P("session_id", "string", "Die Session-ID der Recherche", required=False),
        P("session_id_to_report", "string", "Alternative Session-ID (Alias)", required=False),
        P("format", "string", "Report-Format: markdown oder text", required=False, default="markdown"),
        P("report_format_type", "string", "Alternatives Format-Feld (Alias)", required=False),
        P("include_methodology", "boolean", "Ob Methodik-Sektion enthalten sein soll", required=False, default="true"),
        P("image_paths", "array", "Optionale Bildpfade fuer den Bericht", required=False),
        P("image_captions", "array", "Optionale Bildunterschriften passend zu image_paths", required=False),
        P("image_sections", "array", "Optionale Abschnittstitel passend zu image_paths", required=False),
        P("require_pdf", "boolean", "Wenn true, gilt fehlende PDF-Erzeugung als Fehler statt als tolerierter Teil-Erfolg.", required=False, default="true"),
    ],
    capabilities=["research", "deep_research"],
    category=C.RESEARCH
)
async def generate_research_report(
    session_id: Optional[str] = None,
    session_id_to_report: Optional[str] = None,
    format: str = "markdown",
    report_format_type: Optional[str] = None,
    include_methodology: bool = True,
    image_paths: Optional[List[str]] = None,
    image_captions: Optional[List[str]] = None,
    image_sections: Optional[List[str]] = None,
    require_pdf: bool = True,
) -> dict:
    """
    Erstellt einen druckreifen Bericht für Timus Deep Research v8.1 - Evidence Engine.

    In v8.1:
    - Executive Verdict Table
    - Domain Scorecards
    - Claim Register
    - Conflicts & Unknowns
    - Quellenanhang mit Tier/Typ/Bias

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

    # Externe Bilder (z.B. vom creative-Agent) integrieren
    if image_paths:
        try:
            images = _merge_report_images(
                images,
                image_paths=image_paths,
                image_captions=image_captions,
                image_sections=image_sections,
            )
        except Exception as e:
            logger.warning(f"Externe Bildintegration fehlgeschlagen (unkritisch): {e}")

    # PDF erstellen
    from pathlib import Path as _Path

    base_dir_pdf = (
        str(_Path(filepath).parent) if filepath
        else "/home/fatih-ubuntu/dev/timus/results"
    )
    pdf_markdown = _compose_pdf_markdown(narrative_content, content)
    pdf_filepath = _build_research_pdf(
        content=pdf_markdown,
        images=images,
        session=session,
        output_dir=base_dir_pdf,
        session_id=actual_session_id,
        require_pdf=require_pdf,
    )
    if pdf_filepath:
        logger.info("📄 PDF erstellt: %s", pdf_filepath)

    yt_count = len([c for c in session.unverified_claims if c.get("source_type") == "youtube"])

    if filepath:
        return {
            "session_id": actual_session_id,
            "status": "report_created",
            "format": actual_format,
            "filepath": filepath,
            "narrative_filepath": narrative_filepath,
            "pdf_filepath": pdf_filepath,
            "artifacts": _build_report_artifacts(filepath, narrative_filepath, pdf_filepath),
            "youtube_videos_analyzed": yt_count,
            "images_in_pdf": len(images),
            "message": (
                f"Akademischer Bericht erstellt. "
                f"Lesebericht: {narrative_filepath or 'nicht verfügbar'}. "
                f"PDF: {pdf_filepath or 'nicht verfügbar'}."
            ),
            "summary": _get_research_metadata_summary(session),
            "version": "8.1"
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
            "artifacts": _build_report_artifacts(narrative_filepath, pdf_filepath),
            "youtube_videos_analyzed": yt_count,
            "images_in_pdf": len(images),
            "message": "Bericht erstellt, aber Speichern fehlgeschlagen. Content im Response.",
            "summary": _get_research_metadata_summary(session),
            "version": "8.1"
        }

"""Shared normalization for Phase E improvement candidates."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Iterable, Mapping


_SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

_TAXONOMY_ALIASES = {
    "routing": "routing",
    "route": "routing",
    "router": "routing",
    "conversation_recall": "memory",
    "recall": "memory",
    "memory": "memory",
    "semantic_recall": "memory",
    "tool": "tool",
    "browser": "tool",
    "visual_browser": "tool",
    "policy": "policy",
    "auth": "policy",
    "approval": "policy",
    "consent": "policy",
    "runtime": "runtime",
    "specialist": "specialist",
    "ux": "ux_handoff",
    "handoff": "ux_handoff",
    "ux_handoff": "ux_handoff",
    "context": "context",
    "topic": "context",
    "followup": "context",
    "follow_up": "context",
    "reflection_pattern": "reflection_pattern",
}

_TOKEN_CATEGORY_HINTS = {
    "routing": {
        "routing",
        "router",
        "misroute",
        "agentwahl",
        "route",
    },
    "context": {
        "context",
        "kontext",
        "followup",
        "follow",
        "topic",
        "rehydration",
        "resume",
        "open_loop",
        "thema",
    },
    "policy": {
        "policy",
        "approval",
        "consent",
        "auth",
        "login",
        "challenge",
        "captcha",
        "passkey",
        "2fa",
        "freigabe",
        "governance",
    },
    "runtime": {
        "runtime",
        "timeout",
        "crash",
        "restart",
        "health",
        "startup",
        "latency",
        "exception",
        "service",
        "recovery",
        "failed",
        "failure",
    },
    "tool": {
        "tool",
        "browser",
        "clipboard",
        "keyboard",
        "mouse",
        "ocr",
        "vision",
        "email",
        "api",
        "qdrant",
        "embedding",
    },
    "specialist": {
        "specialist",
        "executor",
        "research",
        "visual",
        "system",
        "meta",
    },
    "memory": {
        "memory",
        "gedaechtnis",
        "semantic",
        "erinner",
        "langzeit",
        "archiv",
        "recall",
    },
    "ux_handoff": {
        "handoff",
        "workflow",
        "awaiting_user",
        "telegram",
        "canvas",
        "render",
        "reply",
        "resume_hint",
    },
}

_DEDUPE_STOPWORDS = {
    "agent",
    "agents",
    "antwort",
    "antworten",
    "analyse",
    "analysieren",
    "bei",
    "das",
    "der",
    "die",
    "ein",
    "eine",
    "einem",
    "einer",
    "erfolgsrate",
    "fuer",
    "für",
    "gemessene",
    "haeufig",
    "häufig",
    "ist",
    "mit",
    "nur",
    "oder",
    "problem",
    "probleme",
    "quality",
    "qualitaet",
    "quality",
    "routing_qualitaet",
    "schwach",
    "session",
    "tool",
    "und",
    "von",
    "zu",
}


def _clean_text(value: Any, *, limit: int = 240) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _tokenize_text(value: Any) -> list[str]:
    text = str(value or "").strip().lower()
    if not text:
        return []
    text = text.replace("follow-up", "followup")
    text = text.replace("sign in", "signin")
    text = text.replace("log in", "login")
    text = text.replace("konto auswählen", "konto_auswaehlen")
    text = text.replace("konto auswaehlen", "konto_auswaehlen")
    text = re.sub(r"[^a-z0-9_]+", " ", text)
    return [token for token in text.split() if token]


def _normalize_confidence(value: Any, *, default: float = 0.5) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(1.0, confidence))


def _normalize_occurrence_count(value: Any, *, default: int = 1) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = default
    return max(1, count)


def _normalize_severity(value: Any, *, default: str = "medium") -> str:
    severity = str(value or "").strip().lower()
    if severity in _SEVERITY_ORDER:
        return severity
    return default


def normalize_improvement_category(
    raw_category: Any,
    *,
    problem: Any = "",
    target: Any = "",
    proposed_action: Any = "",
) -> str:
    category = _clean_text(raw_category, limit=64).lower()
    if category in _TAXONOMY_ALIASES:
        alias = _TAXONOMY_ALIASES[category]
        if alias != "reflection_pattern":
            return alias

    tokens = set(
        _tokenize_text(problem)
        + _tokenize_text(target)
        + _tokenize_text(proposed_action)
        + _tokenize_text(category)
    )
    for candidate, hints in _TOKEN_CATEGORY_HINTS.items():
        if tokens.intersection(hints):
            return candidate
    if category in _TAXONOMY_ALIASES:
        return _TAXONOMY_ALIASES[category]
    return category or "unknown"


def _candidate_title(*, category: str, target: str, problem: str) -> str:
    if category and target:
        return _clean_text(f"{category}:{target}", limit=120)
    if category:
        return _clean_text(category, limit=120)
    if target:
        return _clean_text(target, limit=120)
    return _clean_text(problem, limit=120)


def _build_candidate_id(prefix: str, raw_id: str, fingerprint: str) -> str:
    safe_prefix = _clean_text(prefix, limit=24).lower() or "candidate"
    safe_raw_id = _clean_text(raw_id, limit=96)
    if safe_raw_id:
        if safe_raw_id.lower().startswith(f"{safe_prefix}:"):
            return safe_raw_id
        return f"{safe_prefix}:{safe_raw_id}"
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12]
    return f"{safe_prefix}:{digest}"


def _reflection_severity(occurrences: int) -> str:
    if occurrences >= 6:
        return "high"
    if occurrences >= 3:
        return "medium"
    return "low"


def _reflection_confidence(occurrences: int) -> float:
    return round(min(0.95, 0.45 + (0.08 * max(1, occurrences))), 3)


def normalize_self_improvement_candidate(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalizes an M12 self-improvement suggestion into the Phase-E candidate shape."""
    payload = dict(raw or {})
    raw_id = _clean_text(payload.get("id"), limit=96)
    target = _clean_text(payload.get("target"), limit=160)
    problem = _clean_text(payload.get("problem") or payload.get("finding"), limit=320)
    proposed_action = _clean_text(
        payload.get("proposed_action") or payload.get("suggestion"),
        limit=320,
    )
    raw_category = _clean_text(payload.get("type"), limit=64).lower() or "unknown"
    category = normalize_improvement_category(
        raw_category,
        problem=problem,
        target=target,
        proposed_action=proposed_action,
    )
    evidence_level = _clean_text(payload.get("evidence_level"), limit=64) or "measured"
    evidence_basis = _clean_text(payload.get("evidence_basis"), limit=96) or "runtime_analytics"
    applied = bool(payload.get("applied"))
    occurrence_count = _normalize_occurrence_count(payload.get("occurrence_count") or payload.get("occurrences"))
    severity = _normalize_severity(payload.get("severity"), default="medium")
    confidence = _normalize_confidence(payload.get("confidence"), default=0.5)
    created_at = _clean_text(payload.get("created_at"), limit=64)
    candidate_id = _build_candidate_id(
        "m12",
        raw_id,
        f"{category}|{target}|{problem}|{proposed_action}|{created_at}",
    )
    return {
        "candidate_id": candidate_id,
        "source": "self_improvement_engine",
        "raw_category": raw_category,
        "category": category,
        "target": target,
        "title": _candidate_title(category=category, target=target, problem=problem),
        "problem": problem,
        "proposed_action": proposed_action,
        "severity": severity,
        "confidence": confidence,
        "evidence_level": evidence_level,
        "evidence_basis": evidence_basis,
        "occurrence_count": occurrence_count,
        "status": "applied" if applied else "open",
    }


def normalize_session_reflection_candidate(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalizes an M8 reflection suggestion into the Phase-E candidate shape."""
    payload = dict(raw or {})
    raw_id = _clean_text(payload.get("id"), limit=96)
    problem = _clean_text(payload.get("problem") or payload.get("pattern"), limit=320)
    proposed_action = _clean_text(
        payload.get("proposed_action") or payload.get("suggestion"),
        limit=320,
    )
    raw_category = "reflection_pattern"
    target = _clean_text(payload.get("target"), limit=160)
    category = normalize_improvement_category(
        raw_category,
        problem=problem,
        target=target,
        proposed_action=proposed_action,
    )
    occurrence_count = _normalize_occurrence_count(payload.get("occurrence_count") or payload.get("occurrences"))
    severity = _normalize_severity(
        payload.get("severity"),
        default=_reflection_severity(occurrence_count),
    )
    confidence = _normalize_confidence(
        payload.get("confidence"),
        default=_reflection_confidence(occurrence_count),
    )
    applied = bool(payload.get("applied"))
    created_at = _clean_text(payload.get("created_at"), limit=64)
    candidate_id = _build_candidate_id(
        "m8",
        raw_id,
        f"{problem}|{proposed_action}|{occurrence_count}|{created_at}",
    )
    return {
        "candidate_id": candidate_id,
        "source": "session_reflection",
        "raw_category": raw_category,
        "category": category,
        "target": target,
        "title": _candidate_title(category=category, target=target, problem=problem),
        "problem": problem,
        "proposed_action": proposed_action,
        "severity": severity,
        "confidence": confidence,
        "evidence_level": _clean_text(payload.get("evidence_level"), limit=64) or "pattern",
        "evidence_basis": _clean_text(payload.get("evidence_basis"), limit=96) or "session_reflection",
        "occurrence_count": occurrence_count,
        "status": "applied" if applied else "open",
    }


def _candidate_dedupe_tokens(candidate: Mapping[str, Any]) -> list[str]:
    tokens = []
    for field in ("category", "target", "problem", "proposed_action", "title"):
        tokens.extend(_tokenize_text(candidate.get(field)))
    filtered = []
    for token in tokens:
        if len(token) <= 2:
            continue
        if token in _DEDUPE_STOPWORDS:
            continue
        filtered.append(token)
    return sorted(set(filtered))


def _candidate_dedupe_key(candidate: Mapping[str, Any]) -> str:
    category = normalize_improvement_category(
        candidate.get("category") or candidate.get("raw_category"),
        problem=candidate.get("problem"),
        target=candidate.get("target"),
        proposed_action=candidate.get("proposed_action"),
    )
    key_terms = _candidate_dedupe_tokens(candidate)[:8]
    if not key_terms:
        key_terms = _tokenize_text(candidate.get("candidate_id") or candidate.get("id"))[:3]
    return f"{category}|{' '.join(key_terms)}"


def _priority_score(item: Mapping[str, Any], *, source_count: int, occurrence_count: int) -> tuple[float, list[str]]:
    severity = _normalize_severity(item.get("severity"), default="medium")
    confidence = _normalize_confidence(item.get("confidence"), default=0.5)
    severity_weight = {
        "critical": 1.0,
        "high": 0.82,
        "medium": 0.58,
        "low": 0.3,
    }.get(severity, 0.5)
    score = severity_weight
    reasons = [f"severity:{severity}"]
    score += round(confidence * 0.35, 3)
    if confidence >= 0.75:
        reasons.append("high_confidence")
    if occurrence_count >= 3:
        score += min(0.22, 0.04 * occurrence_count)
        reasons.append("repeated_pattern")
    if source_count >= 2:
        score += min(0.2, 0.1 * (source_count - 1))
        reasons.append("multi_source")
    return round(score, 3), reasons


def _signal_class(*, source_count: int, occurrence_count: int, severity: str) -> str:
    if source_count >= 2 and occurrence_count >= 3:
        return "structural_issue"
    if severity in {"critical", "high"} and occurrence_count >= 2:
        return "structural_issue"
    if occurrence_count >= 3 or source_count >= 2:
        return "repeated_pattern"
    return "single_outlier"


def consolidate_improvement_candidates(
    candidates: Iterable[Mapping[str, Any]],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        item = dict(candidate)
        item["raw_category"] = _clean_text(item.get("raw_category") or item.get("category"), limit=64).lower()
        item["category"] = normalize_improvement_category(
            item.get("category") or item.get("raw_category"),
            problem=item.get("problem") or item.get("finding"),
            target=item.get("target"),
            proposed_action=item.get("proposed_action") or item.get("suggestion"),
        )
        dedupe_key = _candidate_dedupe_key(item)
        item["dedupe_key"] = dedupe_key
        grouped.setdefault(dedupe_key, []).append(item)

    consolidated: list[dict[str, Any]] = []
    for items in grouped.values():
        ranked = sort_improvement_candidates(items)
        base = dict(ranked[0]) if ranked else {}
        merged_sources = sorted({
            _clean_text(item.get("source"), limit=64)
            for item in items
            if _clean_text(item.get("source"), limit=64)
        })
        merged_ids = sorted({
            _clean_text(item.get("candidate_id") or item.get("id"), limit=96)
            for item in items
            if _clean_text(item.get("candidate_id") or item.get("id"), limit=96)
        })
        merged_occurrences = sum(
            _normalize_occurrence_count(item.get("occurrence_count") or item.get("occurrences"))
            for item in items
        )
        top_severity = min(
            (_normalize_severity(item.get("severity"), default="medium") for item in items),
            key=lambda value: _SEVERITY_ORDER.get(value, 99),
            default=_normalize_severity(base.get("severity"), default="medium"),
        )
        top_confidence = max(
            (_normalize_confidence(item.get("confidence"), default=0.5) for item in items),
            default=_normalize_confidence(base.get("confidence"), default=0.5),
        )
        evidence_levels = sorted({
            _clean_text(item.get("evidence_level"), limit=64)
            for item in items
            if _clean_text(item.get("evidence_level"), limit=64)
        })
        evidence_bases = sorted({
            _clean_text(item.get("evidence_basis"), limit=96)
            for item in items
            if _clean_text(item.get("evidence_basis"), limit=96)
        })
        status = "open" if any(str(item.get("status") or "").strip().lower() != "applied" for item in items) else "applied"
        source_count = len(merged_sources) or 1
        priority_score, priority_reasons = _priority_score(
            {"severity": top_severity, "confidence": top_confidence},
            source_count=source_count,
            occurrence_count=merged_occurrences,
        )
        signal_class = _signal_class(
            source_count=source_count,
            occurrence_count=merged_occurrences,
            severity=top_severity,
        )
        if signal_class == "structural_issue" and "structural_issue" not in priority_reasons:
            priority_reasons.append("structural_issue")
        base.update(
            {
                "category": normalize_improvement_category(
                    base.get("category") or base.get("raw_category"),
                    problem=base.get("problem"),
                    target=base.get("target"),
                    proposed_action=base.get("proposed_action"),
                ),
                "severity": top_severity,
                "confidence": round(top_confidence, 3),
                "occurrence_count": merged_occurrences,
                "status": status,
                "evidence_level": "multi_source" if source_count >= 2 else (evidence_levels[0] if evidence_levels else ""),
                "evidence_basis": ",".join(evidence_bases[:4]),
                "merged_sources": merged_sources,
                "source_count": source_count,
                "merged_candidate_ids": merged_ids,
                "duplicate_count": len(items),
                "priority_score": priority_score,
                "priority_reasons": priority_reasons,
                "signal_class": signal_class,
            }
        )
        consolidated.append(base)
    return sort_improvement_candidates(consolidated, limit=limit)


def sort_improvement_candidates(
    candidates: Iterable[Mapping[str, Any]],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Sorts normalized candidates by severity, confidence, occurrence count and recency."""

    def _created_sort_value(value: Any) -> float:
        try:
            return datetime.fromisoformat(str(value or "")).timestamp()
        except (TypeError, ValueError):
            return 0.0

    normalized = [dict(candidate) for candidate in candidates if isinstance(candidate, Mapping)]
    normalized.sort(
        key=lambda item: (
            -float(item.get("priority_score") or 0.0),
            _SEVERITY_ORDER.get(str(item.get("severity") or "").strip().lower(), 99),
            -_normalize_confidence(item.get("confidence"), default=0.0),
            -_normalize_occurrence_count(item.get("occurrence_count") or item.get("occurrences") or 1),
            -_created_sort_value(item.get("created_at")),
            str(item.get("candidate_id") or item.get("id") or ""),
        ),
    )
    if limit is not None and limit >= 0:
        return normalized[:limit]
    return normalized

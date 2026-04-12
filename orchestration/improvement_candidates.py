"""Shared normalization for Phase E improvement candidates."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
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
    "incident": "runtime",
    "self_healing_incident": "runtime",
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

_SOURCE_FRESHNESS_PROFILES = {
    "autonomy_observation": {"fresh_days": 2.0, "stale_days": 7.0, "min_score": 0.28},
    "self_healing_incident": {"fresh_days": 4.0, "stale_days": 21.0, "min_score": 0.38},
    "session_reflection": {"fresh_days": 10.0, "stale_days": 60.0, "min_score": 0.52},
    "self_improvement_engine": {"fresh_days": 14.0, "stale_days": 75.0, "min_score": 0.58},
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


def _parse_candidate_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_reference_now(reference_now: Any = None) -> datetime:
    if isinstance(reference_now, datetime):
        return reference_now.astimezone(timezone.utc) if reference_now.tzinfo else reference_now.replace(tzinfo=timezone.utc)
    parsed = _parse_candidate_datetime(reference_now)
    if parsed is not None:
        return parsed
    return datetime.now(timezone.utc)


def _freshness_profile(source: Any) -> dict[str, float]:
    normalized = _clean_text(source, limit=64).lower()
    return dict(_SOURCE_FRESHNESS_PROFILES.get(normalized) or {"fresh_days": 7.0, "stale_days": 30.0, "min_score": 0.5})


def _candidate_age_days(value: Any, *, reference_now: Any = None) -> float | None:
    parsed = _parse_candidate_datetime(value)
    if parsed is None:
        return None
    now = _resolve_reference_now(reference_now)
    delta = (now - parsed).total_seconds() / 86400.0
    return max(0.0, round(delta, 3))


def _freshness_score_for_source(source: Any, *, age_days: float | None) -> float:
    if age_days is None:
        return 0.75
    profile = _freshness_profile(source)
    fresh_days = max(0.0, float(profile["fresh_days"]))
    stale_days = max(fresh_days + 0.001, float(profile["stale_days"]))
    min_score = max(0.0, min(1.0, float(profile["min_score"])))
    if age_days <= fresh_days:
        return 1.0
    if age_days >= stale_days:
        return min_score
    fraction = (age_days - fresh_days) / (stale_days - fresh_days)
    return round(1.0 - ((1.0 - min_score) * fraction), 3)


def _freshness_state(score: float) -> str:
    if score >= 0.9:
        return "fresh"
    if score >= 0.6:
        return "aging"
    return "stale"


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
        "source_type": raw_category,
        "title": _candidate_title(category=category, target=target, problem=problem),
        "problem": problem,
        "proposed_action": proposed_action,
        "severity": severity,
        "confidence": confidence,
        "evidence_level": evidence_level,
        "evidence_basis": evidence_basis,
        "occurrence_count": occurrence_count,
        "status": "applied" if applied else "open",
        "created_at": created_at,
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
        "source_type": raw_category,
        "title": _candidate_title(category=category, target=target, problem=problem),
        "problem": problem,
        "proposed_action": proposed_action,
        "severity": severity,
        "confidence": confidence,
        "evidence_level": _clean_text(payload.get("evidence_level"), limit=64) or "pattern",
        "evidence_basis": _clean_text(payload.get("evidence_basis"), limit=96) or "session_reflection",
        "occurrence_count": occurrence_count,
        "status": "applied" if applied else "open",
        "created_at": created_at,
    }


def normalize_self_healing_incident_candidate(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalizes a self-healing incident into the Phase-E candidate shape."""
    payload = dict(raw or {})
    details = payload.get("details")
    if not isinstance(details, Mapping):
        details = {}
    raw_id = _clean_text(payload.get("incident_key") or payload.get("id"), limit=96)
    component = _clean_text(payload.get("component"), limit=96).lower()
    signal = _clean_text(payload.get("signal"), limit=96).lower()
    target = _clean_text(f"{component}:{signal}".strip(":"), limit=160)
    status = _clean_text(payload.get("status"), limit=64).lower() or "open"
    title = _clean_text(payload.get("title"), limit=220)
    if title:
        problem = title
    else:
        problem = _clean_text(
            f"Self-healing incident offen: {component or 'unknown_component'} / {signal or 'unknown_signal'}",
            limit=320,
        )
    proposed_action = _clean_text(
        payload.get("recovery_action")
        or details.get("suggested_action")
        or details.get("next_step")
        or "Incident analysieren, Recovery-Guard pruefen und stabile Wiederholung verhindern.",
        limit=320,
    )
    occurrence_count = _normalize_occurrence_count(
        details.get("failure_streak")
        or details.get("seen_count")
        or details.get("incident_memory_seen_count")
        or details.get("attempt_count")
        or 1
    )
    severity = _normalize_severity(payload.get("severity"), default="medium")
    confidence = _normalize_confidence(payload.get("confidence"), default=0.78 if status == "failed" else 0.72)
    created_at = _clean_text(payload.get("last_seen_at") or payload.get("created_at"), limit=64)
    raw_category = "self_healing_incident"
    category = normalize_improvement_category(
        raw_category,
        problem=problem,
        target=target,
        proposed_action=proposed_action,
    )
    candidate_id = _build_candidate_id(
        "incident",
        raw_id,
        f"{component}|{signal}|{problem}|{proposed_action}|{created_at}",
    )
    return {
        "candidate_id": candidate_id,
        "source": "self_healing_incident",
        "raw_category": raw_category,
        "category": category,
        "target": target,
        "component": component,
        "signal": signal,
        "title": _candidate_title(category=category, target=target, problem=problem),
        "problem": problem,
        "proposed_action": proposed_action,
        "severity": severity,
        "confidence": confidence,
        "evidence_level": "incident",
        "evidence_basis": "self_healing_runtime",
        "occurrence_count": occurrence_count,
        "status": "applied" if status in {"recovered", "archived"} else "open",
        "created_at": created_at,
    }


def normalize_autonomy_observation_candidate(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Normalizes selected autonomy observation events into Phase-E candidates."""
    event = dict(raw or {})
    event_type = _clean_text(event.get("event_type"), limit=96).lower()
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        payload = {}
    payload = dict(payload)
    observed_at = _clean_text(event.get("observed_at"), limit=64)
    raw_id = _clean_text(event.get("id"), limit=96)

    raw_category = "runtime"
    target = ""
    problem = ""
    proposed_action = ""
    severity = "medium"
    confidence = 0.65

    if event_type == "dispatcher_meta_fallback":
        reason = _clean_text(payload.get("reason"), limit=96).lower() or "unknown_reason"
        raw_category = "routing"
        target = f"dispatcher:{reason}"
        problem = f"Dispatcher faellt auf Meta zurueck (reason: {reason})."
        proposed_action = "Dispatcher-Entscheidung und Routing-Kriterien fuer diesen Fall nachschaerfen."
        severity = "high" if reason in {"empty_decision", "uncertain_decision"} else "medium"
        confidence = 0.72
    elif event_type == "chat_request_failed":
        source = _clean_text(payload.get("source"), limit=96).lower() or "unknown_source"
        error_class = _clean_text(payload.get("error_class"), limit=96).lower() or "chat_request_failed"
        raw_category = "runtime"
        target = f"{source}:{error_class}"
        problem = f"Chat-Request scheitert sichtbar fuer Nutzer (source: {source}, error_class: {error_class})."
        proposed_action = "Fehlerpfad reproduzieren, Incident-Trace pruefen und user-visible Failure vermeiden."
        severity = "high"
        confidence = 0.82
    elif event_type == "context_misread_suspected":
        reasons = [
            _clean_text(item, limit=96).lower()
            for item in list(payload.get("risk_reasons") or [])
            if _clean_text(item, limit=96)
        ]
        dominant_turn_type = _clean_text(payload.get("dominant_turn_type"), limit=64).lower()
        raw_category = "context"
        target = dominant_turn_type or "turn_understanding"
        reason_text = ", ".join(reasons[:3]) or "unspecified_context_risk"
        problem = f"Kontext-Fehlgriff vermutet ({reason_text})."
        proposed_action = "Turn-Verstaendnis, Bundle-Rehydration und Follow-up-Bindung fuer diesen Risikofall haerten."
        severity = "high" if len(reasons) >= 2 else "medium"
        confidence = 0.74
    elif event_type == "specialist_signal_emitted":
        signal = _clean_text(payload.get("signal"), limit=96).lower()
        if signal not in {"context_mismatch", "needs_meta_reframe"}:
            return None
        agent = _clean_text(payload.get("agent"), limit=64).lower() or "unknown_agent"
        raw_category = "specialist"
        target = f"{agent}:{signal}"
        if signal == "context_mismatch":
            problem = f"Spezialist meldet Kontext-Mismatch ({agent})."
            proposed_action = "Specialist-Handoff und propagierten Kontext fuer diesen Agenten enger ausrichten."
        else:
            problem = f"Spezialist verlangt Meta-Reframe ({agent})."
            proposed_action = "Meta-Handoff und Strategieauswahl fuer diesen Agenten sauberer reframen."
        severity = "medium"
        confidence = 0.71
    elif event_type in {"communication_task_failed", "send_email_failed"}:
        backend = _clean_text(payload.get("backend"), limit=96).lower() or "unknown_backend"
        channel = _clean_text(payload.get("channel"), limit=96).lower() or "communication"
        raw_category = "tool"
        target = f"{channel}:{backend}"
        problem = f"Communication-Lauf scheitert ({channel}, backend: {backend})."
        proposed_action = "Communication-Backend, Credential-Status und Fehlerrueckgabe in diesem Pfad pruefen."
        severity = "high" if event_type == "send_email_failed" else "medium"
        confidence = 0.77
    elif event_type == "challenge_reblocked":
        service = _clean_text(payload.get("service"), limit=96).lower() or "unknown_service"
        challenge_type = _clean_text(payload.get("challenge_type"), limit=96).lower() or "unknown_challenge"
        raw_category = "policy"
        target = f"{service}:{challenge_type}"
        problem = f"Challenge wird erneut blockiert ({service}, type: {challenge_type})."
        proposed_action = "Challenge-Handover, Resume-Pfad und Nutzeranweisung fuer diesen Auth-Fall haerten."
        severity = "high"
        confidence = 0.8
    elif event_type == "meta_direct_tool_call":
        status = _clean_text(payload.get("status"), limit=64).lower()
        has_error = bool(payload.get("has_error"))
        if status != "error" and not has_error:
            return None
        method = _clean_text(payload.get("method"), limit=96).lower() or "unknown_method"
        raw_category = "tool"
        target = method
        problem = f"Meta-Direkttool-Call scheitert ({method})."
        proposed_action = "Direkttool-Fehler analysieren und entweder Guard, Fallback oder Spezialistenroute haerten."
        severity = "medium"
        confidence = 0.69
    else:
        return None

    category = normalize_improvement_category(
        raw_category,
        problem=problem,
        target=target,
        proposed_action=proposed_action,
    )
    candidate_id = _build_candidate_id(
        "obs",
        raw_id,
        f"{event_type}|{target}|{problem}|{observed_at}",
    )
    return {
        "candidate_id": candidate_id,
        "source": "autonomy_observation",
        "raw_category": raw_category,
        "category": category,
        "target": target,
        "event_type": event_type,
        "component": _clean_text(payload.get("component"), limit=96).lower(),
        "signal": _clean_text(payload.get("signal"), limit=96).lower(),
        "title": _candidate_title(category=category, target=target, problem=problem),
        "problem": problem,
        "proposed_action": proposed_action,
        "severity": _normalize_severity(severity, default="medium"),
        "confidence": _normalize_confidence(confidence, default=0.65),
        "evidence_level": "observation",
        "evidence_basis": "autonomy_observation",
        "occurrence_count": 1,
        "status": "open",
        "created_at": observed_at,
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


def _priority_score(
    item: Mapping[str, Any],
    *,
    source_count: int,
    occurrence_count: int,
    freshness_score: float,
    freshness_state: str,
) -> tuple[float, list[str]]:
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
    freshness_score = max(0.0, min(1.0, float(freshness_score or 0.0)))
    score = round(score * freshness_score, 3)
    if freshness_state == "fresh":
        reasons.append("fresh_signal")
    elif freshness_state == "aging":
        reasons.append("aging_signal")
    else:
        reasons.append("stale_signal")
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
    reference_now: Any = None,
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
        verified_paths = sorted({
            _clean_text(path, limit=200)
            for item in items
            for path in list(item.get("verified_paths") or item.get("target_paths") or item.get("target_files") or [])
            if _clean_text(path, limit=200)
        })
        verified_functions = sorted({
            _clean_text(name, limit=120)
            for item in items
            for name in list(item.get("verified_functions") or [])
            if _clean_text(name, limit=120)
        })
        components = sorted({
            _clean_text(item.get("component"), limit=96).lower()
            for item in items
            if _clean_text(item.get("component"), limit=96)
        })
        signals = sorted({
            _clean_text(item.get("signal"), limit=96).lower()
            for item in items
            if _clean_text(item.get("signal"), limit=96)
        })
        event_types = sorted({
            _clean_text(item.get("event_type"), limit=96).lower()
            for item in items
            if _clean_text(item.get("event_type"), limit=96)
        })
        created_candidates = [
            item for item in items if _parse_candidate_datetime(item.get("created_at")) is not None
        ]
        latest_created_dt = max(
            (_parse_candidate_datetime(item.get("created_at")) for item in created_candidates),
            default=None,
        )
        latest_created_at = latest_created_dt.isoformat() if latest_created_dt is not None else ""
        freshness_samples = []
        for item in items:
            age_days = _candidate_age_days(item.get("created_at"), reference_now=reference_now)
            freshness_samples.append(
                {
                    "source": _clean_text(item.get("source"), limit=64),
                    "age_days": age_days,
                    "score": _freshness_score_for_source(item.get("source"), age_days=age_days),
                }
            )
        freshness_score = max((sample["score"] for sample in freshness_samples), default=0.75)
        freshness_age_days = min(
            (sample["age_days"] for sample in freshness_samples if sample["age_days"] is not None),
            default=None,
        )
        freshness_state = _freshness_state(freshness_score)
        status = "open" if any(str(item.get("status") or "").strip().lower() != "applied" for item in items) else "applied"
        source_count = len(merged_sources) or 1
        priority_score, priority_reasons = _priority_score(
            {"severity": top_severity, "confidence": top_confidence},
            source_count=source_count,
            occurrence_count=merged_occurrences,
            freshness_score=freshness_score,
            freshness_state=freshness_state,
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
                "created_at": latest_created_at,
                "evidence_level": "multi_source" if source_count >= 2 else (evidence_levels[0] if evidence_levels else ""),
                "evidence_basis": ",".join(evidence_bases[:4]),
                "merged_sources": merged_sources,
                "source_count": source_count,
                "merged_candidate_ids": merged_ids,
                "duplicate_count": len(items),
                "verified_paths": verified_paths,
                "verified_functions": verified_functions,
                "components": components,
                "signals": signals,
                "event_types": event_types,
                "freshness_score": round(freshness_score, 3),
                "freshness_state": freshness_state,
                "freshness_age_days": freshness_age_days,
                "priority_score": priority_score,
                "priority_reasons": priority_reasons,
                "signal_class": signal_class,
            }
        )
        consolidated.append(base)
    return sort_improvement_candidates(consolidated, limit=limit)


def build_candidate_operator_view(candidate: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(candidate or {})
    title = _clean_text(item.get("title") or item.get("problem"), limit=160)
    category = _clean_text(item.get("category"), limit=64).lower() or "unknown"
    target = _clean_text(item.get("target"), limit=120)
    if category and target:
        label = f"{category}:{target}"
    elif category:
        label = category
    else:
        label = target or "candidate"
    merged_sources = [
        _clean_text(source, limit=64)
        for source in list(item.get("merged_sources") or [])
        if _clean_text(source, limit=64)
    ]
    if not merged_sources:
        single_source = _clean_text(item.get("source"), limit=64)
        if single_source:
            merged_sources = [single_source]
    priority_reasons = [
        _clean_text(reason, limit=64)
        for reason in list(item.get("priority_reasons") or [])
        if _clean_text(reason, limit=64)
    ]
    summary_parts = [
        f"{label}",
        f"prio={float(item.get('priority_score') or 0.0):.3f}",
        f"freshness={_clean_text(item.get('freshness_state'), limit=32) or 'unknown'}",
        f"signal={_clean_text(item.get('signal_class'), limit=48) or 'unknown'}",
    ]
    if merged_sources:
        summary_parts.append(f"sources={','.join(merged_sources[:4])}")
    return {
        "candidate_id": _clean_text(item.get("candidate_id") or item.get("id"), limit=96),
        "label": label,
        "title": title,
        "priority_score": round(float(item.get("priority_score") or 0.0), 3),
        "freshness_score": round(float(item.get("freshness_score") or 0.0), 3),
        "freshness_state": _clean_text(item.get("freshness_state"), limit=32) or "unknown",
        "signal_class": _clean_text(item.get("signal_class"), limit=48) or "unknown",
        "merged_sources": merged_sources,
        "priority_reasons": priority_reasons,
        "summary": " | ".join(summary_parts),
        "problem": _clean_text(item.get("problem"), limit=220),
        "proposed_action": _clean_text(item.get("proposed_action"), limit=220),
    }


def build_candidate_operator_views(
    candidates: Iterable[Mapping[str, Any]],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    views = [
        build_candidate_operator_view(candidate)
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]
    if limit is not None and limit >= 0:
        return views[:limit]
    return views


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

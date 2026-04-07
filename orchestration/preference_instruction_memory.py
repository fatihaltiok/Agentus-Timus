from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Iterable, Mapping

from utils.stable_hash import stable_text_digest


_GLOBAL_PREFERENCE_HINTS = (
    "immer",
    "grundsaetzlich",
    "grundsätzlich",
    "generell",
    "standardmaessig",
    "standardmäßig",
    "ab jetzt",
)
_SESSION_LOCAL_HINTS = (
    "fuer diesen",
    "für diesen",
    "diesmal",
    "in diesem chat",
    "in dieser sitzung",
    "fuer diese anfrage",
    "für diese anfrage",
    "fuer diesen vergleich",
    "für diesen vergleich",
    "nur hier",
    "nur fuer jetzt",
    "nur für jetzt",
    "heute",
)
_STYLE_PREFERENCE_HINTS = (
    "antworte",
    "schreib",
    "sei",
    "halte antworten",
    "fasse",
    "erkläre",
    "erklaere",
)
_DIRECTIVE_STOPWORDS = (
    "bitte",
    "immer",
    "zuerst",
    "nur",
    "priorisiere",
    "priorisierst",
    "nutze",
    "verwende",
    "bevorzuge",
    "antworte",
    "schreib",
    "halte",
    "sei",
    "sollst",
    "soll",
    "musst",
    "muss",
)
_SOURCE_PRIORITY_HINTS = (
    "agentur",
    "agenturquellen",
    "agenturmeldungen",
    "quelle",
    "quellen",
    "reuters",
    "ap",
    "dpa",
    "afp",
    "primaerquelle",
    "primärquelle",
    "offizielle doku",
    "offizielle dokumentation",
)
_STYLE_SHORT_HINTS = ("kurz", "knapp", "kompakt", "praezise", "präzise")
_STYLE_LONG_HINTS = ("ausfuehrlich", "ausführlich", "detailliert", "tief", "gruendlich", "gründlich")
_FORMAT_HINTS = ("json", "struktur", "strukturiert", "liste", "stichpunkt", "stichpunkte", "format")
_LANGUAGE_HINTS = ("deutsch", "englisch", "sprache", "auf deutsch", "auf englisch")
_SCOPE_CONSTRAINT_HINTS = (
    "deutschland",
    "europa",
    "usa",
    "vergleich",
    "region",
    "land",
    "lokal",
    "weltweit",
)
_SCOPE_PRIORITY = {"session": 3, "topic": 2, "global": 1}


def _normalize_text(value: Any, *, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _tokenize(text: str) -> set[str]:
    return {
        token.strip("_-")
        for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß_-]+", str(text or "").lower())
        if len(token.strip("_-")) >= 3
    }


def _overlap(left: str, right: str) -> int:
    return len(_tokenize(left).intersection(_tokenize(right)))


def _normalize_instruction_core(text: str) -> str:
    cleaned = _normalize_text(text, limit=320)
    lowered = cleaned.lower()
    prefixes = (
        "dann mach das in zukunft so dass du ",
        "mach das in zukunft so dass du ",
        "in zukunft bitte ",
        "bitte ",
        "dann ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            lowered = cleaned.lower()
            break
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned


def _extract_topic_anchor(text: str, fallback_topic: str = "") -> str:
    cleaned = _normalize_instruction_core(text)
    lowered = cleaned.lower()
    pattern = re.compile(
        r"\b(?:bei|für|fuer|zu)\s+([a-z0-9äöüß _-]{2,60}?)(?=\s+(?:"
        + "|".join(re.escape(token) for token in _DIRECTIVE_STOPWORDS)
        + r")\b|$)",
        re.IGNORECASE,
    )
    match = pattern.search(cleaned)
    if match:
        anchor = _normalize_text(match.group(1), limit=80)
        if anchor:
            return anchor
    if fallback_topic and _overlap(fallback_topic, lowered) > 0:
        return _normalize_text(fallback_topic, limit=80)
    return ""


@dataclass(frozen=True, slots=True)
class CapturedPreference:
    scope: str
    instruction: str
    normalized_instruction: str
    topic_anchor: str
    session_id: str
    source_turn_type: str
    response_mode: str
    stability: float
    explicit_global: bool
    preference_family: str
    evidence_count: int = 1

    def to_memory_value(self, *, updated_at: str) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "instruction": self.instruction,
            "normalized_instruction": self.normalized_instruction,
            "topic_anchor": self.topic_anchor,
            "session_id": self.session_id,
            "source_turn_type": self.source_turn_type,
            "response_mode": self.response_mode,
            "stability": round(self.stability, 2),
            "explicit_global": self.explicit_global,
            "preference_family": self.preference_family,
            "evidence_count": self.evidence_count,
            "updated_at": updated_at,
        }


@dataclass(frozen=True, slots=True)
class PreferenceSelectionResult:
    selected: tuple[str, ...]
    selected_details: tuple[dict[str, Any], ...]
    ignored_low_stability: tuple[dict[str, Any], ...]
    conflicts_resolved: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": list(self.selected),
            "selected_details": [dict(item) for item in self.selected_details],
            "ignored_low_stability": [dict(item) for item in self.ignored_low_stability],
            "conflicts_resolved": [dict(item) for item in self.conflicts_resolved],
        }


def _has_any(text: str, hints: Iterable[str]) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in hints)


def _infer_preference_family(text: str, topic_anchor: str = "") -> str:
    lowered = _normalize_instruction_core(text).lower()
    if _has_any(lowered, _SOURCE_PRIORITY_HINTS):
        return "source_policy"
    if _has_any(lowered, _STYLE_SHORT_HINTS) or _has_any(lowered, _STYLE_LONG_HINTS):
        return "response_style"
    if _has_any(lowered, _FORMAT_HINTS):
        return "output_format"
    if _has_any(lowered, _LANGUAGE_HINTS):
        return "language"
    if _has_any(lowered, _SCOPE_CONSTRAINT_HINTS):
        return "scope_constraint"
    if topic_anchor:
        return f"topic:{_normalize_text(topic_anchor, limit=40).lower()}"
    return f"instruction:{stable_text_digest(lowered, hex_chars=6)}"


def _infer_scope(
    *,
    effective_query: str,
    active_topic: str,
) -> tuple[str, str, float, bool]:
    lowered = effective_query.lower()
    topic_anchor = _extract_topic_anchor(effective_query, fallback_topic=active_topic)
    explicit_global = _has_any(lowered, _GLOBAL_PREFERENCE_HINTS)
    style_global = any(lowered.startswith(token) for token in _STYLE_PREFERENCE_HINTS)
    session_local = any(token in lowered for token in _SESSION_LOCAL_HINTS)

    if session_local:
        return "session", topic_anchor, 0.68, False
    if topic_anchor:
        return "topic", topic_anchor, 0.82, False
    if explicit_global:
        return "global", "", 0.93, True
    if style_global:
        return "global", "", 0.78, False
    if active_topic:
        return "topic", _normalize_text(active_topic, limit=80), 0.76, False
    return "session", "", 0.62, False


def derive_captured_preference(
    *,
    effective_query: str,
    session_id: str,
    updated_state: Mapping[str, Any] | None,
    dominant_turn_type: str,
    response_mode: str,
) -> CapturedPreference | None:
    cleaned = _normalize_instruction_core(effective_query)
    if not cleaned:
        return None
    if dominant_turn_type not in {"behavior_instruction", "preference_update"}:
        return None
    if response_mode != "acknowledge_and_store":
        return None

    active_topic = _normalize_text((updated_state or {}).get("active_topic"), limit=120)
    scope, topic_anchor, stability, explicit_global = _infer_scope(
        effective_query=cleaned,
        active_topic=active_topic,
    )
    return CapturedPreference(
        scope=scope,
        instruction=cleaned,
        normalized_instruction=cleaned.lower(),
        topic_anchor=topic_anchor,
        session_id=_normalize_text(session_id, limit=120) or "default",
        source_turn_type=dominant_turn_type,
        response_mode=response_mode,
        stability=stability,
        explicit_global=explicit_global,
        preference_family=_infer_preference_family(cleaned, topic_anchor),
    )


def _preference_memory_key(preference: CapturedPreference) -> str:
    instruction_hash = stable_text_digest(preference.normalized_instruction, hex_chars=10)
    if preference.scope == "global":
        return f"global::{instruction_hash}"
    if preference.scope == "topic":
        topic_hash = stable_text_digest(preference.topic_anchor or "topic", hex_chars=8)
        return f"topic::{topic_hash}::{instruction_hash}"
    session_hash = stable_text_digest(preference.session_id or "session", hex_chars=8)
    return f"session::{session_hash}::{instruction_hash}"


def capture_preference_memory(
    *,
    effective_query: str,
    session_id: str,
    updated_state: Mapping[str, Any] | None,
    dominant_turn_type: str,
    response_mode: str,
    memory_manager: Any,
    updated_at: str = "",
) -> dict[str, Any] | None:
    captured = derive_captured_preference(
        effective_query=effective_query,
        session_id=session_id,
        updated_state=updated_state,
        dominant_turn_type=dominant_turn_type,
        response_mode=response_mode,
    )
    if captured is None or memory_manager is None:
        return None

    try:
        from memory.memory_system import MemoryItem
    except Exception:
        return None

    key = _preference_memory_key(captured)
    existing_count = 0
    try:
        for item in memory_manager.persistent.get_memory_items("preference_memory"):
            if str(getattr(item, "key", "")) != key:
                continue
            value = getattr(item, "value", {}) or {}
            if isinstance(value, Mapping):
                existing_count = int(value.get("evidence_count") or 0)
            break
    except Exception:
        existing_count = 0

    evidence_count = existing_count + 1
    stability = captured.stability
    if captured.scope == "global" and evidence_count >= 2:
        stability = max(stability, 0.95)

    final = CapturedPreference(
        scope=captured.scope,
        instruction=captured.instruction,
        normalized_instruction=captured.normalized_instruction,
        topic_anchor=captured.topic_anchor,
        session_id=captured.session_id,
        source_turn_type=captured.source_turn_type,
        response_mode=captured.response_mode,
        stability=stability,
        explicit_global=captured.explicit_global,
        preference_family=captured.preference_family,
        evidence_count=evidence_count,
    )
    timestamp = _normalize_text(updated_at, limit=64) or datetime.now().isoformat()
    item = MemoryItem(
        category="preference_memory",
        key=key,
        value=final.to_memory_value(updated_at=timestamp),
        importance=0.9 if final.scope == "global" else 0.82 if final.scope == "topic" else 0.68,
        confidence=final.stability,
        reason="d0_preference_capture",
        source="meta_preference_memory",
    )
    memory_manager.store_with_embedding(item)
    return {
        "key": key,
        "scope": final.scope,
        "instruction": final.instruction,
        "topic_anchor": final.topic_anchor,
        "preference_family": final.preference_family,
        "explicit_global": final.explicit_global,
        "stability": round(final.stability, 2),
        "evidence_count": final.evidence_count,
    }


def _render_preference_item(value: Mapping[str, Any]) -> str:
    scope = _normalize_text(value.get("scope"), limit=24).lower() or "session"
    instruction = _normalize_text(value.get("instruction"), limit=220)
    topic_anchor = _normalize_text(value.get("topic_anchor"), limit=80)
    if scope == "topic" and topic_anchor:
        return f"stored_preference:topic[{topic_anchor}] => {instruction}"
    if scope == "global":
        return f"stored_preference:global => {instruction}"
    return f"stored_preference:session => {instruction}"


def _parse_updated_at_rank(value: Any) -> float:
    text = _normalize_text(value, limit=64)
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _scope_priority(scope: str) -> int:
    return _SCOPE_PRIORITY.get(_normalize_text(scope, limit=24).lower(), 0)


def _allow_global_preference(*, stability: float, evidence_count: int, explicit_global: bool) -> bool:
    if explicit_global:
        return True
    if evidence_count >= 2:
        return True
    return stability >= 0.9


def _build_candidate_detail(
    *,
    rendered: str,
    scope: str,
    family: str,
    stability: float,
    evidence_count: int,
) -> dict[str, Any]:
    return {
        "rendered": rendered,
        "scope": scope,
        "family": family,
        "stability": round(stability, 2),
        "evidence_count": evidence_count,
    }


def select_stored_preference_memory_with_summary(
    *,
    effective_query: str,
    conversation_state: Mapping[str, Any] | None,
    turn_type: str,
    memory_manager: Any,
    limit: int = 2,
) -> PreferenceSelectionResult:
    if memory_manager is None:
        return PreferenceSelectionResult((), (), (), ())

    session_id = _normalize_text((conversation_state or {}).get("session_id"), limit=120)
    active_topic = _normalize_text((conversation_state or {}).get("active_topic"), limit=120)
    active_goal = _normalize_text((conversation_state or {}).get("active_goal"), limit=120)
    open_loop = _normalize_text((conversation_state or {}).get("open_loop"), limit=120)
    focus_text = " | ".join(item for item in (effective_query, active_topic, active_goal, open_loop) if item)
    focus_terms = _tokenize(focus_text)

    try:
        items = memory_manager.persistent.get_memory_items("preference_memory")
    except Exception:
        return PreferenceSelectionResult((), (), (), ())

    candidates: list[dict[str, Any]] = []
    ignored_low_stability: list[dict[str, Any]] = []
    for item in items:
        value = getattr(item, "value", {}) or {}
        if not isinstance(value, Mapping):
            continue
        scope = _normalize_text(value.get("scope"), limit=24).lower()
        instruction = _normalize_text(value.get("instruction"), limit=220)
        if not instruction:
            continue
        topic_anchor = _normalize_text(value.get("topic_anchor"), limit=80)
        item_session = _normalize_text(value.get("session_id"), limit=120)
        stability = float(value.get("stability") or 0.0)
        evidence_count = int(value.get("evidence_count") or 1)
        explicit_global = bool(value.get("explicit_global"))
        family = _normalize_text(value.get("preference_family"), limit=64) or _infer_preference_family(
            instruction,
            topic_anchor,
        )
        overlap = max(
            len(focus_terms.intersection(_tokenize(instruction))),
            len(focus_terms.intersection(_tokenize(topic_anchor))),
        )
        rendered = _render_preference_item(value)

        if scope == "session":
            if not session_id or item_session != session_id:
                continue
        elif scope == "topic":
            if overlap <= 0 and topic_anchor and _overlap(topic_anchor, focus_text) <= 0:
                continue
            if evidence_count < 2 and stability < 0.72 and overlap < 2:
                ignored_low_stability.append(
                    {
                        **_build_candidate_detail(
                            rendered=rendered,
                            scope=scope,
                            family=family,
                            stability=stability,
                            evidence_count=evidence_count,
                        ),
                        "reason": "topic_preference_low_stability",
                    }
                )
                continue
        elif scope == "global":
            if not _allow_global_preference(
                stability=stability,
                evidence_count=evidence_count,
                explicit_global=explicit_global,
            ):
                ignored_low_stability.append(
                    {
                        **_build_candidate_detail(
                            rendered=rendered,
                            scope=scope,
                            family=family,
                            stability=stability,
                            evidence_count=evidence_count,
                        ),
                        "reason": "global_requires_repeat_or_explicit",
                    }
                )
                continue
        else:
            continue

        candidates.append(
            {
                "rendered": rendered,
                "scope": scope,
                "family": family,
                "stability": stability,
                "evidence_count": evidence_count,
                "explicit_global": explicit_global,
                "overlap": overlap,
                "updated_at_rank": _parse_updated_at_rank(value.get("updated_at")),
            }
        )

    candidates.sort(
        key=lambda item: (
            -_scope_priority(item["scope"]),
            -int(item["overlap"]),
            -int(item["explicit_global"]),
            -int(item["evidence_count"]),
            -float(item["stability"]),
            -float(item["updated_at_rank"]),
            len(item["rendered"]),
        )
    )

    selected: list[str] = []
    selected_details: list[dict[str, Any]] = []
    conflicts_resolved: list[dict[str, Any]] = []
    winning_family: dict[str, dict[str, Any]] = {}
    for item in candidates:
        family = str(item["family"])
        if family in winning_family:
            kept = winning_family[family]
            if item["rendered"] != kept["rendered"]:
                conflicts_resolved.append(
                    {
                        "family": family,
                        "kept_rendered": kept["rendered"],
                        "kept_scope": kept["scope"],
                        "discarded_rendered": item["rendered"],
                        "discarded_scope": item["scope"],
                        "reason": "narrower_scope_wins"
                        if _scope_priority(kept["scope"]) > _scope_priority(item["scope"])
                        else "higher_stability_wins",
                    }
                )
            continue

        winning_family[family] = item
        selected.append(item["rendered"])
        selected_details.append(
            _build_candidate_detail(
                rendered=item["rendered"],
                scope=item["scope"],
                family=item["family"],
                stability=float(item["stability"]),
                evidence_count=int(item["evidence_count"]),
            )
        )
        if len(selected) >= limit:
            continue

    return PreferenceSelectionResult(
        tuple(selected[:limit]),
        tuple(selected_details[:limit]),
        tuple(ignored_low_stability),
        tuple(conflicts_resolved),
    )


def select_stored_preference_memory(
    *,
    effective_query: str,
    conversation_state: Mapping[str, Any] | None,
    turn_type: str,
    memory_manager: Any,
    limit: int = 2,
) -> list[str]:
    return list(
        select_stored_preference_memory_with_summary(
            effective_query=effective_query,
            conversation_state=conversation_state,
            turn_type=turn_type,
            memory_manager=memory_manager,
            limit=limit,
        ).selected
    )

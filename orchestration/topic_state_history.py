from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping


_SCHEMA_VERSION = 1
_MAX_HISTORY_ITEMS = 24
_ALLOWED_STATUSES = {"active", "historical", "stale", "closed"}
_TOPIC_STOPWORDS = {
    "aber",
    "an",
    "auf",
    "aus",
    "bei",
    "bitte",
    "das",
    "dem",
    "den",
    "der",
    "die",
    "dir",
    "du",
    "eben",
    "ein",
    "eine",
    "einem",
    "einer",
    "eines",
    "erinnern",
    "erinnerst",
    "faden",
    "frage",
    "geantwortet",
    "gearbeitet",
    "gerade",
    "gesagt",
    "gespraech",
    "gespräch",
    "geschrieben",
    "gestern",
    "greif",
    "hatten",
    "ich",
    "ihr",
    "im",
    "kurzlich",
    "kürzlich",
    "letzte",
    "letzten",
    "letzter",
    "letztes",
    "mal",
    "mit",
    "monat",
    "noch",
    "nochmal",
    "schon",
    "sagte",
    "soll",
    "thema",
    "ueber",
    "und",
    "unser",
    "unsere",
    "unterhaltung",
    "vor",
    "vorhin",
    "vom",
    "von",
    "was",
    "wei",
    "weist",
    "weisst",
    "weißt",
    "wieder",
    "wir",
    "woche",
    "woran",
    "woruber",
    "worüber",
    "zu",
    "besprochen",
}
_HISTORICAL_RECALL_PATTERNS = (
    r"\bwei(?:ss|ß)t\s+du\s+noch\b",
    r"\bweisst\s+du\s+noch\b",
    r"\bgreif\b.*\b(?:thema|faden|gespr(?:a|ä)ch)\b",
    r"\bwas\s+habe\s+ich\s+eben\s+gesagt\b",
    r"\bwas\s+haben\s+wir\b.*\bbesprochen\b",
    r"\bworan\s+haben\s+wir\b.*\bgearbeitet\b",
    r"\bnochmal\s+auf\b",
    r"\bwieder\s+aufgreifen\b",
    r"\b(?:von|ueber)\s+gestern\b",
    r"\b(?:von|ueber)\s+letzte(?:r|n)?\s+woche\b",
    r"\bvor\s+einem\s+monat\b",
    r"\bletztes\s+mal\b",
)

_RECENT_MOMENT_TOKENS = ("gerade eben", "eben", "vorhin", "kürzlich", "kurzlich")
_RECENT_MOMENT_CONTEXT_PATTERNS = (
    r"\b(?:von|ueber)\s+(?:gerade\s+eben|eben|vorhin|k[üu]rzlich)\b",
    r"\bwas\s+habe\s+ich\s+(?:gerade\s+eben|eben|vorhin|k[üu]rzlich)\s+gesagt\b",
    r"\bwas\s+hast\s+du\s+(?:gerade\s+eben|eben|vorhin|k[üu]rzlich)\s+gesagt\b",
    r"\berinner(?:st|e)\b.*\b(?:gerade\s+eben|eben|vorhin|k[üu]rzlich)\b",
)

_NUMBER_WORDS = {
    "ein": 1,
    "einem": 1,
    "einen": 1,
    "eins": 1,
    "eine": 1,
    "einer": 1,
    "zwei": 2,
    "drei": 3,
    "vier": 4,
    "fuenf": 5,
    "fünf": 5,
    "sechs": 6,
    "sieben": 7,
    "acht": 8,
    "neun": 9,
    "zehn": 10,
    "elf": 11,
    "zwoelf": 12,
    "zwölf": 12,
    "dreizehn": 13,
    "vierzehn": 14,
    "fuenfzehn": 15,
    "fünfzehn": 15,
    "sechzehn": 16,
    "siebzehn": 17,
    "achtzehn": 18,
    "neunzehn": 19,
    "zwanzig": 20,
    "einundzwanzig": 21,
    "zweiundzwanzig": 22,
    "dreiundzwanzig": 23,
    "vierundzwanzig": 24,
}


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def _normalize_text(value: Any, *, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _normalize_confidence(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(numeric, 1.0))


def _normalize_status(value: Any) -> str:
    lowered = _normalize_text(value, limit=32).lower()
    return lowered if lowered in _ALLOWED_STATUSES else "historical"


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = _normalize_text(value, limit=80)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _reference_now(now: str = "") -> datetime:
    parsed = _parse_iso_datetime(now)
    if parsed is not None:
        return _to_utc(parsed)
    return _to_utc(datetime.now().astimezone())


def _age_days(value: str, *, now: str = "") -> float:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return 0.0
    delta = _reference_now(now) - _to_utc(parsed)
    return max(0.0, delta.total_seconds() / 86400.0)


def _tokenize_topic_terms(text: str) -> set[str]:
    lowered = _normalize_text(text, limit=400).lower()
    return {
        token.strip("_-")
        for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß_-]+", lowered)
        if len(token.strip("_-")) >= 3 and token.strip("_-") not in _TOPIC_STOPWORDS
    }


def _parse_relative_quantity(query: str, *, unit: str) -> int | None:
    lowered = _normalize_text(query, limit=400).lower()
    unit_pattern = r"monat(?:e|en)?"
    if unit == "year":
        unit_pattern = r"jahr(?:e|en)?"
    match = re.search(rf"\bvor\s+([a-z0-9äöüß]+)\s+{unit_pattern}\b", lowered)
    if not match:
        return None
    raw = _normalize_text(match.group(1), limit=24).lower()
    if raw.isdigit():
        try:
            return max(1, min(int(raw), 120))
        except ValueError:
            return None
    return _NUMBER_WORDS.get(raw)


@dataclass(frozen=True, slots=True)
class TopicHistoryEntry:
    schema_version: int
    session_id: str
    topic: str
    goal: str
    open_loop: str
    next_expected_step: str
    status: str
    first_seen_at: str
    last_seen_at: str
    closed_at: str
    topic_confidence: float
    turn_type_hint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "topic": self.topic,
            "goal": self.goal,
            "open_loop": self.open_loop,
            "next_expected_step": self.next_expected_step,
            "status": self.status,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "closed_at": self.closed_at,
            "topic_confidence": self.topic_confidence,
            "turn_type_hint": self.turn_type_hint,
        }


@dataclass(frozen=True, slots=True)
class HistoricalTopicRecallHint:
    requested: bool
    time_label: str
    min_age_days: float
    max_age_days: float
    focus_terms: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "time_label": self.time_label,
            "min_age_days": self.min_age_days,
            "max_age_days": self.max_age_days,
            "focus_terms": list(self.focus_terms),
        }


def _decay_topic_status(entry: TopicHistoryEntry, *, now: str = "") -> TopicHistoryEntry:
    age_days = _age_days(entry.last_seen_at, now=now)
    status = entry.status
    if age_days >= 45:
        status = "stale"
    elif status == "closed" and age_days >= 21:
        status = "stale"
    elif status == "active" and age_days >= 7:
        status = "historical"
    elif status == "active" and age_days >= 3 and not entry.open_loop:
        status = "historical"
    if status == entry.status:
        return entry
    return TopicHistoryEntry(
        schema_version=entry.schema_version,
        session_id=entry.session_id,
        topic=entry.topic,
        goal=entry.goal,
        open_loop=entry.open_loop,
        next_expected_step=entry.next_expected_step,
        status=status,
        first_seen_at=entry.first_seen_at,
        last_seen_at=entry.last_seen_at,
        closed_at=entry.closed_at,
        topic_confidence=entry.topic_confidence,
        turn_type_hint=entry.turn_type_hint,
    )


def normalize_topic_history(
    payload: Iterable[Any] | None,
    *,
    session_id: str,
    limit: int = _MAX_HISTORY_ITEMS,
    now: str = "",
) -> tuple[TopicHistoryEntry, ...]:
    deduped_by_topic: dict[str, TopicHistoryEntry] = {}
    normalized_session_id = _normalize_text(session_id, limit=120) or "default"

    for item in payload or ():
        if not isinstance(item, Mapping):
            continue
        topic = _normalize_text(item.get("topic"))
        if not topic:
            continue
        entry = TopicHistoryEntry(
            schema_version=_SCHEMA_VERSION,
            session_id=_normalize_text(item.get("session_id"), limit=120) or normalized_session_id,
            topic=topic,
            goal=_normalize_text(item.get("goal")),
            open_loop=_normalize_text(item.get("open_loop")),
            next_expected_step=_normalize_text(item.get("next_expected_step")),
            status=_normalize_status(item.get("status")),
            first_seen_at=_normalize_text(item.get("first_seen_at"), limit=64),
            last_seen_at=_normalize_text(item.get("last_seen_at"), limit=64),
            closed_at=_normalize_text(item.get("closed_at"), limit=64),
            topic_confidence=_normalize_confidence(item.get("topic_confidence")),
            turn_type_hint=_normalize_text(item.get("turn_type_hint"), limit=64).lower(),
        )
        decayed = _decay_topic_status(entry, now=now)
        if (
            decayed.status in {"historical", "stale", "closed"}
            and _age_days(decayed.last_seen_at, now=now) > 3650.0
        ):
            continue
        existing = deduped_by_topic.get(decayed.topic)
        if existing is None:
            deduped_by_topic[decayed.topic] = decayed
            continue
        existing_dt = _parse_iso_datetime(existing.last_seen_at) or datetime.min.replace(tzinfo=timezone.utc)
        candidate_dt = _parse_iso_datetime(decayed.last_seen_at) or datetime.min.replace(tzinfo=timezone.utc)
        deduped_by_topic[decayed.topic] = decayed if candidate_dt >= existing_dt else existing

    normalized = list(deduped_by_topic.values())
    normalized.sort(
        key=lambda item: _to_utc(_parse_iso_datetime(item.last_seen_at) or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )
    return tuple(normalized[: max(1, limit)])


def topic_history_to_list(
    payload: Iterable[Any] | None,
    *,
    session_id: str,
    limit: int = _MAX_HISTORY_ITEMS,
    now: str = "",
) -> list[dict[str, Any]]:
    return [entry.to_dict() for entry in normalize_topic_history(payload, session_id=session_id, limit=limit, now=now)]


def update_topic_history(
    payload: Iterable[Any] | None,
    *,
    session_id: str,
    previous_state: Mapping[str, Any] | None,
    updated_state: Mapping[str, Any] | None,
    topic_transition: Mapping[str, Any] | None,
    updated_at: str,
    limit: int = _MAX_HISTORY_ITEMS,
) -> list[dict[str, Any]]:
    history = list(topic_history_to_list(payload, session_id=session_id, limit=limit, now=updated_at))
    previous = dict(previous_state or {})
    current = dict(updated_state or {})
    transition = dict(topic_transition or {})
    previous_topic = _normalize_text(previous.get("active_topic"))
    current_topic = _normalize_text(current.get("active_topic"))
    timestamp = _normalize_text(updated_at, limit=64) or _iso_now()

    def _find(topic: str) -> dict[str, Any] | None:
        for entry in history:
            if _normalize_text(entry.get("topic")) == topic:
                return entry
        return None

    if previous_topic and bool(transition.get("topic_shift_detected")):
        previous_entry = _find(previous_topic)
        if previous_entry is None:
            previous_entry = {
                "schema_version": _SCHEMA_VERSION,
                "session_id": session_id,
                "topic": previous_topic,
                "goal": _normalize_text(previous.get("active_goal")),
                "open_loop": _normalize_text(previous.get("open_loop")),
                "next_expected_step": _normalize_text(previous.get("next_expected_step")),
                "first_seen_at": _normalize_text(previous.get("updated_at"), limit=64) or timestamp,
                "last_seen_at": _normalize_text(previous.get("updated_at"), limit=64) or timestamp,
                "closed_at": "",
                "topic_confidence": _normalize_confidence(previous.get("topic_confidence")),
                "turn_type_hint": _normalize_text(previous.get("turn_type_hint"), limit=64).lower(),
                "status": "historical",
            }
            history.append(previous_entry)
        previous_entry["status"] = "closed"
        previous_entry["closed_at"] = timestamp
        previous_entry["last_seen_at"] = timestamp

    if current_topic:
        current_entry = _find(current_topic)
        if current_entry is None:
            current_entry = {
                "schema_version": _SCHEMA_VERSION,
                "session_id": session_id,
                "topic": current_topic,
                "goal": "",
                "open_loop": "",
                "next_expected_step": "",
                "first_seen_at": timestamp,
                "last_seen_at": timestamp,
                "closed_at": "",
                "topic_confidence": 0.0,
                "turn_type_hint": "",
                "status": "active",
            }
            history.append(current_entry)

        current_entry["goal"] = _normalize_text(current.get("active_goal")) or _normalize_text(current_entry.get("goal"))
        current_entry["open_loop"] = _normalize_text(current.get("open_loop"))
        current_entry["next_expected_step"] = _normalize_text(current.get("next_expected_step"))
        current_entry["last_seen_at"] = timestamp
        current_entry["topic_confidence"] = max(
            _normalize_confidence(current_entry.get("topic_confidence")),
            _normalize_confidence(current.get("topic_confidence")),
        )
        current_entry["turn_type_hint"] = (
            _normalize_text(current.get("turn_type_hint"), limit=64).lower()
            or _normalize_text(current_entry.get("turn_type_hint"), limit=64).lower()
        )
        current_entry["status"] = "active"
        if not _normalize_text(current_entry.get("first_seen_at"), limit=64):
            current_entry["first_seen_at"] = timestamp
        if previous_topic != current_topic:
            current_entry["closed_at"] = ""

    return topic_history_to_list(history, session_id=session_id, limit=limit, now=updated_at)


def parse_historical_topic_recall_hint(query: str) -> HistoricalTopicRecallHint:
    cleaned = _normalize_text(query, limit=400)
    lowered = cleaned.lower()
    requested = any(re.search(pattern, lowered) for pattern in _HISTORICAL_RECALL_PATTERNS)
    recent_moment_requested = any(re.search(pattern, lowered) for pattern in _RECENT_MOMENT_CONTEXT_PATTERNS)

    time_label = "recent_history"
    min_age_days = 0.0
    max_age_days = 3650.0
    if recent_moment_requested or (
        requested
        and any(token in lowered for token in _RECENT_MOMENT_TOKENS)
    ):
        time_label = "recent_moment"
        min_age_days = 0.0
        max_age_days = 0.25
        requested = True
    elif "vorgestern" in lowered:
        time_label = "day_before_yesterday"
        min_age_days = 1.0
        max_age_days = 3.2
        requested = True
    elif "gestern" in lowered:
        time_label = "yesterday"
        min_age_days = 0.4
        max_age_days = 2.2
        requested = True
    elif any(token in lowered for token in ("letzte woche", "letzter woche", "von letzter woche", "vergangene woche")):
        time_label = "last_week"
        min_age_days = 4.0
        max_age_days = 12.5
        requested = True
    else:
        month_quantity = _parse_relative_quantity(lowered, unit="month")
        year_quantity = _parse_relative_quantity(lowered, unit="year")

        if month_quantity is not None:
            time_label = "specific_month_range"
            midpoint = float(month_quantity) * 30.4
            tolerance = max(12.0, midpoint * 0.16)
            min_age_days = max(0.0, midpoint - tolerance)
            max_age_days = midpoint + tolerance
            requested = True
        elif any(token in lowered for token in ("letzten monat", "letzter monat", "vor einem monat", "von letztem monat")):
            time_label = "last_month"
            min_age_days = 20.0
            max_age_days = 45.0
            requested = True
        elif year_quantity is not None:
            time_label = "year_scale"
            midpoint = float(year_quantity) * 365.25
            tolerance = max(45.0, midpoint * 0.16)
            min_age_days = max(0.0, midpoint - tolerance)
            max_age_days = midpoint + tolerance
            requested = True
        elif any(token in lowered for token in ("letztes jahr",)):
            time_label = "year_scale"
            min_age_days = 300.0
            max_age_days = 500.0
            requested = True
        elif any(token in lowered for token in ("letztes mal", "damals", "früher", "frueher")):
            time_label = "previous_session"
            min_age_days = 0.0
            max_age_days = 3650.0
            requested = True
    focus_terms = tuple(sorted(_tokenize_topic_terms(cleaned)))
    return HistoricalTopicRecallHint(
        requested=bool(requested),
        time_label=time_label,
        min_age_days=min_age_days,
        max_age_days=max_age_days,
        focus_terms=focus_terms,
    )


def _time_score_for_history_entry(hint: HistoricalTopicRecallHint, *, age_days: float) -> float:
    if not hint.requested:
        return 0.0
    if hint.time_label == "previous_session":
        return 2.0 if age_days >= 0.0 else 0.0
    if hint.min_age_days <= age_days <= hint.max_age_days:
        return 3.0
    if hint.time_label == "recent_history" and age_days <= 30.0:
        return 1.5
    midpoint = (hint.min_age_days + hint.max_age_days) / 2.0
    tolerance = max(1.0, (hint.max_age_days - hint.min_age_days) / 2.0)
    if abs(age_days - midpoint) <= tolerance:
        return 1.5
    return 0.0


def _render_historical_topic_entry(entry: TopicHistoryEntry, hint: HistoricalTopicRecallHint) -> str:
    parts = [f"topic: {entry.topic}"]
    if entry.goal and entry.goal != entry.topic:
        parts.append(f"goal: {entry.goal}")
    if entry.open_loop:
        parts.append(f"open_loop: {entry.open_loop}")
    if entry.last_seen_at:
        parts.append(f"last_seen: {entry.last_seen_at}")
    parts.append(f"status: {entry.status}")
    return f"historical_topic[{hint.time_label}] => " + " | ".join(parts[:4])


def select_historical_topic_memory(
    payload: Iterable[Any] | None,
    *,
    session_id: str,
    query: str,
    now: str = "",
    limit: int = 2,
) -> tuple[list[str], dict[str, Any]]:
    hint = parse_historical_topic_recall_hint(query)
    history = normalize_topic_history(payload, session_id=session_id, now=now)
    if not hint.requested or not history:
        return [], {
            "requested": hint.requested,
            "time_label": hint.time_label,
            "selected": [],
            "selected_details": [],
            "history_size": len(history),
            "focus_terms": list(hint.focus_terms),
        }

    scored: list[tuple[float, TopicHistoryEntry]] = []
    for entry in history:
        age_days = _age_days(entry.last_seen_at, now=now)
        time_score = _time_score_for_history_entry(hint, age_days=age_days)
        if time_score <= 0.0:
            continue
        text_terms = _tokenize_topic_terms(" | ".join([entry.topic, entry.goal, entry.open_loop, entry.next_expected_step]))
        overlap = len(text_terms.intersection(set(hint.focus_terms)))
        if hint.focus_terms and overlap <= 0 and time_score < 3.0:
            continue
        status_bonus = 0.4 if entry.status in {"closed", "historical", "stale"} else 0.2
        score = (time_score * 10.0) + (overlap * 3.0) + float(entry.topic_confidence) + status_bonus
        scored.append((score, entry))

    scored.sort(key=lambda item: (-item[0], _age_days(item[1].last_seen_at, now=now), item[1].topic))
    selected_entries = [entry for _, entry in scored[: max(1, limit)]]
    selected = [_render_historical_topic_entry(entry, hint) for entry in selected_entries]
    selected_details = [
        {
            "topic": entry.topic,
            "goal": entry.goal,
            "open_loop": entry.open_loop,
            "status": entry.status,
            "last_seen_at": entry.last_seen_at,
            "time_label": hint.time_label,
        }
        for entry in selected_entries
    ]
    return selected, {
        "requested": True,
        "time_label": hint.time_label,
        "selected": list(selected),
        "selected_details": selected_details,
        "history_size": len(history),
        "focus_terms": list(hint.focus_terms),
    }

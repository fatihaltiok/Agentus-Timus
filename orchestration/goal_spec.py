"""Goal-first advisory specification for meta orchestration."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Tuple


_PRICE_HINTS = ("preis", "preise", "pricing", "kosten", "modellpreise", "tokenpreise")
_WEATHER_HINTS = ("wetter", "temperatur", "regen", "schnee", "wind")
_NEWS_HINTS = ("news", "nachrichten", "neuigkeiten", "was gibt es neues", "aktuelle entwicklungen")
_SCIENCE_HINTS = ("wissenschaft", "forschung", "paper", "papers", "studie", "studien")
_PEOPLE_HINTS = ("wer ist", "wie heißt", "wie heisst", "ceo", "präsident", "praesident", "vorstand")
_ENTERTAINMENT_HINTS = ("kino", "film", "filme", "kinoprogramm")
_LOCAL_HINTS = ("nähe", "naehe", "hier", "cafe", "cafes", "cafés", "restaurant", "bar", "apotheke")
_REPORT_HINTS = ("bericht", "zusammenfassung", "fasse", "analysiere", "werte aus")
_TABLE_HINTS = ("tabelle", "vergleichstabelle")
_LIST_HINTS = ("liste", "auflisten")
_ARTIFACT_HINTS = ("datei", "speichere", "exportiere", "erstelle", "artefakt")
_CURRENT_QUERY_MARKER = "# CURRENT USER QUERY"


@dataclass(frozen=True)
class GoalSpec:
    goal_signature: str
    task_type: str
    domain: str
    freshness: str
    evidence_level: str
    output_mode: str
    artifact_format: str | None
    uses_location: bool
    delivery_required: bool
    advisory_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _extract_goal_text(query: str) -> str:
    raw = str(query or "").strip()
    if not raw:
        return ""
    marker = _CURRENT_QUERY_MARKER.lower()
    if marker not in raw.lower():
        return raw
    match = re.search(r"^\s*#\s*CURRENT USER QUERY\s*$", raw, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return raw
    tail = raw[match.end() :].strip()
    return tail or raw


def _contains_any(text: str, hints: Iterable[str]) -> bool:
    return any(hint in text for hint in hints)


def _detect_artifact_format(text: str) -> str | None:
    for fmt in ("xlsx", "csv", "txt", "pdf", "docx"):
        if re.search(rf"\b{re.escape(fmt)}\b", text):
            return fmt
    if "excel" in text:
        return "xlsx"
    return None


def _detect_output_mode(text: str, task_type: str, artifact_format: str | None, delivery_required: bool) -> str:
    if task_type == "location_route":
        return "route"
    if artifact_format or (_contains_any(text, _ARTIFACT_HINTS) and "datei" in text):
        return "artifact"
    if _contains_any(text, _TABLE_HINTS):
        return "table"
    if _contains_any(text, _LIST_HINTS):
        return "list"
    if _contains_any(text, _REPORT_HINTS) or task_type in {"knowledge_research", "youtube_content_extraction", "web_content_extraction"}:
        return "report"
    if delivery_required:
        return "message"
    return "answer"


def _detect_domain(text: str, task_type: str, site_kind: str | None) -> str:
    if task_type == "location_route":
        return "route"
    if task_type == "location_local_search" or _contains_any(text, _LOCAL_HINTS):
        return "local_search"
    if task_type == "system_diagnosis":
        return "system"
    if site_kind == "youtube" or task_type in {"youtube_content_extraction", "youtube_light_research"}:
        return "video_content"
    if task_type in {"knowledge_research", "web_content_extraction"}:
        return "research"
    if _contains_any(text, _PRICE_HINTS):
        return "pricing"
    if _contains_any(text, _WEATHER_HINTS):
        return "weather"
    if _contains_any(text, _NEWS_HINTS) and _contains_any(text, _SCIENCE_HINTS):
        return "science_news"
    if _contains_any(text, _NEWS_HINTS):
        return "news"
    if _contains_any(text, _SCIENCE_HINTS):
        return "science"
    if _contains_any(text, _PEOPLE_HINTS):
        return "identity_lookup"
    if _contains_any(text, _ENTERTAINMENT_HINTS):
        return "entertainment"
    return "general_lookup"


def _detect_freshness(text: str, task_type: str) -> str:
    if task_type in {"simple_live_lookup", "simple_live_lookup_document", "location_local_search", "location_route", "system_diagnosis"}:
        return "live"
    if _contains_any(text, ("aktuell", "aktuelle", "aktuellen", "heute", "jetzt", "live", "neueste", "latest", "current")):
        return "recent"
    if task_type in {"knowledge_research", "youtube_light_research", "youtube_content_extraction", "web_content_extraction"}:
        return "recent"
    return "timeless"


def _detect_evidence_level(text: str, task_type: str) -> str:
    if task_type == "knowledge_research":
        if _contains_any(text, ("tiefenrecherche", "deep research", "quellen", "studie", "studien", "paper", "papers")):
            return "deep"
        return "verified"
    if task_type in {"youtube_content_extraction", "web_content_extraction", "system_diagnosis"}:
        return "verified"
    if task_type in {"simple_live_lookup", "simple_live_lookup_document", "location_local_search", "location_route", "youtube_light_research"}:
        return "light"
    return "light"


def _detect_uses_location(text: str, task_type: str, site_kind: str | None) -> bool:
    if task_type in {"location_local_search", "location_route"}:
        return True
    if site_kind == "maps":
        return True
    return _contains_any(text, ("nähe", "naehe", "hier", "in meiner nähe", "in meiner naehe", "route", "weg nach"))


def _detect_delivery_required(text: str, required_capabilities: Iterable[str]) -> bool:
    if "message_delivery" in set(required_capabilities):
        return True
    return _contains_any(text, ("email", "e-mail", "mail", "sende", "schicke"))


def _build_goal_signature(goal_spec: GoalSpec) -> str:
    artifact = goal_spec.artifact_format or "none"
    return (
        f"{goal_spec.domain}|{goal_spec.freshness}|{goal_spec.evidence_level}|"
        f"{goal_spec.output_mode}|{artifact}|loc={int(goal_spec.uses_location)}|"
        f"deliver={int(goal_spec.delivery_required)}"
    )


def derive_goal_spec(query: str, classification: Dict[str, Any]) -> Dict[str, Any]:
    text = _extract_goal_text(query).lower()
    task_type = str(classification.get("task_type") or "single_lane").strip().lower()
    site_kind = str(classification.get("site_kind") or "").strip().lower() or None
    required_capabilities = classification.get("required_capabilities") or []
    artifact_format = _detect_artifact_format(text)
    delivery_required = _detect_delivery_required(text, required_capabilities)
    goal_spec = GoalSpec(
        goal_signature="",
        task_type=task_type,
        domain=_detect_domain(text, task_type, site_kind),
        freshness=_detect_freshness(text, task_type),
        evidence_level=_detect_evidence_level(text, task_type),
        output_mode=_detect_output_mode(text, task_type, artifact_format, delivery_required),
        artifact_format=artifact_format,
        uses_location=_detect_uses_location(text, task_type, site_kind),
        delivery_required=delivery_required,
    )
    goal_signature = _build_goal_signature(goal_spec)
    return GoalSpec(
        goal_signature=goal_signature,
        task_type=goal_spec.task_type,
        domain=goal_spec.domain,
        freshness=goal_spec.freshness,
        evidence_level=goal_spec.evidence_level,
        output_mode=goal_spec.output_mode,
        artifact_format=goal_spec.artifact_format,
        uses_location=goal_spec.uses_location,
        delivery_required=goal_spec.delivery_required,
        advisory_only=True,
    ).to_dict()

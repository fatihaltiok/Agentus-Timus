from __future__ import annotations

import re
from dataclasses import dataclass


_LOCATION_ONLY_PATTERNS = (
    r"\bwo bin ich\b",
    r"\bwo ist mein standort\b",
    r"\bmein standort\b",
    r"\bwo befinde ich mich\b",
    r"\bwelcher ort ist das\b",
    r"\bin welcher stra[sß]e bin ich\b",
)

_LOCAL_CONTEXT_PATTERNS = (
    r"\bin meiner n(?:ä|ae)he\b",
    r"\bin der n(?:ä|ae)he\b",
    r"\bhier in der n(?:ä|ae)he\b",
    r"\bin meiner umgebung\b",
    r"\bin der umgebung\b",
    r"\bum mich herum\b",
    r"\bhier\b",
    r"\bnear me\b",
    r"\bnearby\b",
    r"\bclose by\b",
    r"\bn(?:ä|ae)chste[nrsm]*\b",
    r"\bnahebei\b",
)

_LOCAL_ACTION_PATTERNS = (
    r"\bwo finde ich\b",
    r"\bwo bekomme ich\b",
    r"\bfinde mir\b",
    r"\bsuche mir\b",
    r"\bsuche\b",
    r"\bsuch\b",
    r"\bzeige mir\b",
    r"\bzeig mir\b",
    r"\bgibt es\b",
    r"\bich brauche\b",
    r"\bich br[aä]uchte\b",
    r"\bbrauch(?:e)?\b",
    r"\bnavigier mich\b",
    r"\bf[uü]hre mich\b",
)

_OPEN_NOW_PATTERNS = (
    r"\boffen\b",
    r"\b24/?7\b",
    r"\brund um die uhr\b",
    r"\bnotdienst\b",
)

_LEADING_REQUEST_PATTERNS = (
    r"^(?:wo finde ich|wo bekomme ich)\b",
    r"^(?:finde|such(?:e)?|zeige|zeig)\s+(?:mir\s+)?\b",
    r"^(?:gibt es(?: hier)?)\b",
    r"^(?:welche[rsmn]?|welcher|welches|welchen)\b",
    r"^(?:was ist hier)\b",
    r"^(?:ich brauche|ich br[aä]uchte|brauch(?:e)?)\b",
    r"^(?:navigier mich(?: bitte)?(?: zu[rm]?)?|f[uü]hre mich(?: bitte)?(?: zu[rm]?)?)\b",
)

_LOCAL_CONTEXT_CLEANUP_PATTERNS = _LOCAL_CONTEXT_PATTERNS + (
    r"\bhier\b",
    r"\bgerade\b",
    r"\bbitte\b",
    r"\bmal\b",
    r"\bnoch\b",
)

_OPEN_NOW_CLEANUP_PATTERNS = (
    r"\bgerade offen\b",
    r"\bnoch offen\b",
    r"\boffen hat\b",
    r"\boffen\b",
    r"\b24/?7\b",
    r"\brund um die uhr\b",
)

_EDGE_FILLER_TOKENS = {
    "eine",
    "einen",
    "einem",
    "einer",
    "ein",
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "zum",
    "zur",
    "zu",
    "mir",
    "hier",
    "bitte",
    "mal",
    "gerade",
    "noch",
    "jetzt",
}

_CATEGORY_PATTERNS = (
    (r"\bitalien(?:isch(?:e|en|er|es)?)?\s+restaurant\b", "italienisches Restaurant"),
    (r"\bvegan(?:e|en|er|es)?\s+caf[eé]\b", "veganes Cafe"),
    (r"\bvegan(?:e|en|er|es)?\s+restaurant\b", "veganes Restaurant"),
    (r"\bpizzeri(?:a|en)?\b|\bpizza\b", "Pizzeria"),
    (r"\bsushi\b", "Sushi Restaurant"),
    (r"\bburger\b", "Burger Restaurant"),
    (r"\bd[öo]ner\b|\bdoener\b", "Doener"),
    (r"\bapothek\w*\b", "Apotheke"),
    (r"\bdrogeri\w*\b", "Drogerie"),
    (r"\bsupermarkt\w*\b|\blebensmittel\w*\b", "Supermarkt"),
    (r"\brestaurant\w*\b", "Restaurant"),
    (r"\bcaf[eé]\w*\b|\bkaffee\b", "Cafe"),
    (r"\bb(?:ä|ae)ck\w*\b", "Baeckerei"),
    (r"\bbar\w*\b", "Bar"),
    (r"\btankstell\w*\b", "Tankstelle"),
    (r"\bbank\b|\bgeldautomat\w*\b|\batm\b", "Bank"),
    (r"\bhotel\w*\b", "Hotel"),
    (r"\barzt\w*\b", "Arzt"),
    (r"\bkrankenhaus\w*\b|\bklinik\w*\b", "Krankenhaus"),
    (r"\bparkplatz\w*\b", "Parkplatz"),
    (r"\btoilett\w*\b|\bwc\b", "Toilette"),
    (r"\bgeschaeft\w*\b|\bgeschäft\w*\b|\bladen\w*\b|\bshop\w*\b", "Geschaefte"),
    (r"\bort\w*\b", "Orte"),
)


@dataclass(frozen=True)
class LocationLocalIntent:
    is_location_relevant: bool
    is_location_only: bool
    maps_query: str
    wants_open_now: bool
    reason: str


def _normalize_text(text: str) -> str:
    normalized = str(text or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _strip_request_wrappers(text: str) -> str:
    cleaned = _normalize_text(text)
    for pattern in _LEADING_REQUEST_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, count=1)
    for pattern in _LOCAL_CONTEXT_CLEANUP_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned)
    for pattern in _OPEN_NOW_CLEANUP_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned)
    cleaned = re.sub(r"[?!,.;:]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    tokens = [token for token in cleaned.split() if token]
    while tokens and tokens[0] in _EDGE_FILLER_TOKENS:
        tokens.pop(0)
    while tokens and tokens[-1] in _EDGE_FILLER_TOKENS:
        tokens.pop()
    return " ".join(tokens).strip()


def _extract_category_query(text: str) -> str:
    source = _normalize_text(text)
    if not source:
        return ""
    for pattern, value in _CATEGORY_PATTERNS:
        if re.search(pattern, source):
            return value
    return ""


def _extract_maps_query(normalized_query: str) -> str:
    cleaned = _strip_request_wrappers(normalized_query)
    category_query = _extract_category_query(cleaned or normalized_query)
    if category_query:
        return category_query

    if not cleaned:
        return ""

    tokens = [token for token in cleaned.split() if token not in _EDGE_FILLER_TOKENS]
    if not tokens:
        return ""
    query = " ".join(tokens[:4]).strip()
    if not query:
        return ""
    return query[0].upper() + query[1:]


def analyze_location_local_intent(query: str) -> LocationLocalIntent:
    normalized = _normalize_text(query)
    if not normalized:
        return LocationLocalIntent(
            is_location_relevant=False,
            is_location_only=False,
            maps_query="",
            wants_open_now=False,
            reason="empty_query",
        )

    if _has_any_pattern(normalized, _LOCATION_ONLY_PATTERNS):
        return LocationLocalIntent(
            is_location_relevant=True,
            is_location_only=True,
            maps_query="",
            wants_open_now=False,
            reason="location_only",
        )

    wants_open_now = _has_any_pattern(normalized, _OPEN_NOW_PATTERNS)
    has_local_context = _has_any_pattern(normalized, _LOCAL_CONTEXT_PATTERNS)
    has_local_action = _has_any_pattern(normalized, _LOCAL_ACTION_PATTERNS)
    category_query = _extract_category_query(normalized)
    maps_query = category_query or _extract_maps_query(normalized)

    if category_query and (has_local_context or has_local_action):
        return LocationLocalIntent(
            is_location_relevant=True,
            is_location_only=False,
            maps_query=maps_query,
            wants_open_now=wants_open_now,
            reason="nearby_search",
        )

    if wants_open_now and has_local_context:
        return LocationLocalIntent(
            is_location_relevant=True,
            is_location_only=False,
            maps_query="Geschaefte",
            wants_open_now=True,
            reason="open_now_nearby",
        )

    return LocationLocalIntent(
        is_location_relevant=False,
        is_location_only=False,
        maps_query="",
        wants_open_now=wants_open_now,
        reason="not_location_local",
    )


def is_location_local_query(query: str) -> bool:
    return analyze_location_local_intent(query).is_location_relevant

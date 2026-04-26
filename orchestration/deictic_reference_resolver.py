"""CCF3: Deictic Reference Resolver.

Bindet deiktische Referenzen wie ``dieses Problem``, ``eben``,
``dafuer``, ``worueber hatte ich`` an den letzten relevanten Anker
(open_loop, pending_followup_prompt, last_assistant, active_topic).

Wird vor der GDK-Entscheidung aufgerufen. Das Ergebnis ist ein
expliziter Resolver-Contract, den Meta nutzen kann, um nicht erneut
mit ``Welches Problem?`` zurueckzufragen.

Datentyp:

    {
        "schema_version": 1,
        "has_reference": bool,
        "reference_kind": str,            # "self_problem", "recall", "topic_continuation", "thread_carry"
        "trigger_phrase": str,            # was im query gematcht hat
        "resolved_reference": str,        # text des aufgeloesten Ankers
        "source_anchor": str,             # "open_loop" | "pending_followup_prompt" | "last_assistant" | "active_topic" | ""
        "confidence": float,
        "fallback_question": str,         # falls confidence niedrig: was Meta fragen darf
    }

Wenn ``confidence`` ueber dem Schwellwert liegt, darf Meta nicht erneut
``Welches Problem?`` o.ae. fragen.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Mapping


# Patterns fuer verschiedene deiktische Klassen.
# Sortiert nach Spezifitaet: spezifischere Pattern werden zuerst geprueft.

# "Welches Problem?" Trigger - der Nutzer beschwert sich ueber Timus selbst
_SELF_PROBLEM_PATTERNS = (
    "kannst du dieses problem beheben",
    "kannst du das problem beheben",
    "behebe dieses problem",
    "loese das problem",
    "loes das problem",
    "fix dieses problem",
    "dieses problem mit dir",
)

# Recall-Fragen, die explizit nach einem Vorturn fragen
_EXPLICIT_RECALL_PATTERNS = (
    "worueber hatte ich dich eben",
    "worueber hatte ich dich gerade",
    "worueber haben wir eben",
    "wonach hatte ich gefragt",
    "was hatte ich eben gefragt",
    "was war meine letzte frage",
    "was wollte ich nochmal",
)

# Generische deiktische Marker (schwaechere Trigger)
_GENERIC_DEICTIC_PATTERNS = (
    " dieses problem",
    " das problem",
    " dieses thema",
    " das thema",
    " du weisst doch wofuer",
    " du weisst doch worum",
    " du weisst doch was",
    " erinner dich",
    " erinnere dich",
    " wie eben besprochen",
    " wie wir eben",
    " wie gerade",
    " genau das",
    " genau dafuer",
    " dafuer",
    " darum geht",
    " darum ging",
)

_NORMALIZATION_MAP = (
    ("ü", "ue"),
    ("ö", "oe"),
    ("ä", "ae"),
    ("ß", "ss"),
)


def _normalize(text: Any) -> str:
    lowered = str(text or "").lower().strip()
    for src, target in _NORMALIZATION_MAP:
        lowered = lowered.replace(src, target)
    return lowered


def _contains_any(text: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        if pattern in text:
            return pattern
    return ""


@dataclass(frozen=True)
class DeicticReferenceResolution:
    schema_version: int
    has_reference: bool
    reference_kind: str
    trigger_phrase: str
    resolved_reference: str
    source_anchor: str
    confidence: float
    fallback_question: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _empty_resolution() -> DeicticReferenceResolution:
    return DeicticReferenceResolution(
        schema_version=1,
        has_reference=False,
        reference_kind="",
        trigger_phrase="",
        resolved_reference="",
        source_anchor="",
        confidence=0.0,
        fallback_question="",
    )


def resolve_deictic_reference(
    *,
    query: str,
    open_loop: str = "",
    pending_followup_prompt: str = "",
    last_assistant: str = "",
    last_user: str = "",
    active_topic: str = "",
    next_step: str = "",
) -> DeicticReferenceResolution:
    """Loese deiktische Referenzen im Query an einen Gespraechsanker.

    Wenn keine Referenz erkannt wird, gibt eine leere Resolution zurueck.
    Sonst wird der staerkste verfuegbare Anker gewaehlt.
    """
    normalized_query = _normalize(query)
    if not normalized_query:
        return _empty_resolution()

    # Padding fuer Pattern-Matching auf Wortgrenzen
    padded = f" {normalized_query} "

    self_problem_match = _contains_any(padded, _SELF_PROBLEM_PATTERNS)
    explicit_recall_match = _contains_any(padded, _EXPLICIT_RECALL_PATTERNS)
    generic_match = _contains_any(padded, _GENERIC_DEICTIC_PATTERNS)

    if not (self_problem_match or explicit_recall_match or generic_match):
        return _empty_resolution()

    # Anker-Quellen in Prioritaetsreihenfolge
    anchors: list[tuple[str, str]] = []
    if open_loop:
        anchors.append(("open_loop", str(open_loop).strip()))
    if pending_followup_prompt:
        anchors.append(("pending_followup_prompt", str(pending_followup_prompt).strip()))
    if last_assistant:
        anchors.append(("last_assistant", str(last_assistant).strip()))
    if active_topic:
        anchors.append(("active_topic", str(active_topic).strip()))
    if next_step:
        anchors.append(("next_expected_step", str(next_step).strip()))
    if last_user:
        anchors.append(("last_user", str(last_user).strip()))

    # Fall A: explicit_recall - der Nutzer fragt explizit nach einem Vorturn.
    # Bestes Anker: last_user (was der Nutzer zuletzt gesagt hatte) oder
    # active_topic. Open-Loop ist hier weniger relevant.
    if explicit_recall_match:
        # Recall-Prioritaet: last_user > active_topic > open_loop
        recall_priority = ("last_user", "active_topic", "open_loop")
        recall_anchors = [
            (key, dict(anchors).get(key))
            for key in recall_priority
            if dict(anchors).get(key)
        ]
        if recall_anchors:
            source, value = recall_anchors[0]
            return DeicticReferenceResolution(
                schema_version=1,
                has_reference=True,
                reference_kind="recall",
                trigger_phrase=explicit_recall_match.strip(),
                resolved_reference=value[:320],
                source_anchor=source,
                confidence=0.85,
                fallback_question="",
            )
        return DeicticReferenceResolution(
            schema_version=1,
            has_reference=True,
            reference_kind="recall",
            trigger_phrase=explicit_recall_match.strip(),
            resolved_reference="",
            source_anchor="",
            confidence=0.4,
            fallback_question="Ich habe gerade keinen frischen Vorturn fuer dich. Was meinst du genau?",
        )

    # Fall B: self_problem - Nutzer beschwert sich ueber Timus' Verhalten.
    # Bestes Anker: das, was zuletzt schiefging - entweder ein erkennbares
    # Meta-Issue oder der vorherige assistant-turn.
    if self_problem_match:
        self_anchors = [a for a in anchors if a[0] in ("last_assistant", "open_loop", "active_topic")]
        if self_anchors:
            source, value = self_anchors[0]
            return DeicticReferenceResolution(
                schema_version=1,
                has_reference=True,
                reference_kind="self_problem",
                trigger_phrase=self_problem_match.strip(),
                resolved_reference=value[:320],
                source_anchor=source,
                confidence=0.8,
                fallback_question="",
            )
        return DeicticReferenceResolution(
            schema_version=1,
            has_reference=True,
            reference_kind="self_problem",
            trigger_phrase=self_problem_match.strip(),
            resolved_reference="",
            source_anchor="",
            confidence=0.3,
            fallback_question=(
                "Welches Problem genau? Bitte nenn mir kurz, was schiefging."
            ),
        )

    # Fall C: generic deictic - kann thread_carry oder topic_continuation sein.
    if generic_match:
        if anchors:
            # Bevorzuge open_loop > pending > last_assistant > active_topic
            source, value = anchors[0]
            return DeicticReferenceResolution(
                schema_version=1,
                has_reference=True,
                reference_kind="thread_carry",
                trigger_phrase=generic_match.strip(),
                resolved_reference=value[:320],
                source_anchor=source,
                confidence=0.75,
                fallback_question="",
            )
        return DeicticReferenceResolution(
            schema_version=1,
            has_reference=True,
            reference_kind="thread_carry",
            trigger_phrase=generic_match.strip(),
            resolved_reference="",
            source_anchor="",
            confidence=0.3,
            fallback_question="Worauf beziehst du dich gerade? Mir fehlt der Kontext.",
        )

    return _empty_resolution()


def parse_deictic_reference_resolution(
    value: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    payload = dict(value or {})
    return {
        "schema_version": int(payload.get("schema_version") or 1),
        "has_reference": bool(payload.get("has_reference")),
        "reference_kind": str(payload.get("reference_kind") or "").strip(),
        "trigger_phrase": str(payload.get("trigger_phrase") or "").strip()[:120],
        "resolved_reference": str(payload.get("resolved_reference") or "").strip()[:320],
        "source_anchor": str(payload.get("source_anchor") or "").strip(),
        "confidence": round(float(payload.get("confidence") or 0.0), 2),
        "fallback_question": str(payload.get("fallback_question") or "").strip()[:240],
    }

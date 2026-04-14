from __future__ import annotations

import re

_FOLLOWUP_MARKER = "# follow-up context"

_TABULAR_DATA_HINTS = (
    ".csv",
    ".xlsx",
    ".xls",
    ".json",
    ".tsv",
    "csv analysieren",
    "xlsx analysieren",
    "excel analysieren",
    "json analysieren",
    "analysiere die csv",
    "analysiere die excel",
    "analysiere die datei",
    "werte die datei aus",
    "datensatz",
    "spalte",
    "zeile",
    "tabelle",
    "korrelation",
    "mittelwert",
    "statistik",
)

_GUIDANCE_HINTS = (
    "erklaer",
    "erklaere",
    "erklär",
    "erkläre",
    "wie fange ich",
    "wie starte ich",
    "wie kann ich",
    "wie komme ich",
    "konkret anfangen",
    "einstiegsplan",
    "was bedeutet",
    "was ist",
    "wie gehe ich",
    "wie baue ich",
    "wie lerne ich",
    "soll ich",
    "koennte ich",
    "könnte ich",
    "lohnt sich",
    "was denkst du",
    "was meinst du",
)

_EVIDENCE_SENSITIVE_TOPICS = (
    "karriere",
    "job",
    "beruf",
    "einstieg",
    "ausbildung",
    "zertifikat",
    "zertifizierung",
    "kurs",
    "weiterbildung",
    "bewerbung",
    "gehalt",
    "gehälter",
    "markt",
    "nachfrage",
    "plattform",
    "plattformen",
    "annotation",
    "labeling",
    "training data",
    "prompt engineering",
    "ai training",
    "ki training",
)


def _normalize(text: str) -> str:
    return str(text or "").strip().lower()


def looks_like_tabular_data_task(task: str) -> bool:
    lowered = _normalize(task)
    if not lowered:
        return False
    if any(token in lowered for token in _TABULAR_DATA_HINTS):
        return True
    return bool(re.search(r"\b[\w./-]+\.(?:csv|xlsx|xls|json|tsv)\b", lowered))


def should_add_evidence_response_guard(task: str) -> bool:
    lowered = _normalize(task)
    if not lowered or looks_like_tabular_data_task(lowered):
        return False
    has_sensitive_topic = any(token in lowered for token in _EVIDENCE_SENSITIVE_TOPICS)
    if not has_sensitive_topic:
        return False
    has_guidance = any(token in lowered for token in _GUIDANCE_HINTS)
    has_followup = _FOLLOWUP_MARKER in lowered
    return has_guidance or has_followup


def build_evidence_response_guard(task: str) -> str:
    if not should_add_evidence_response_guard(task):
        return ""
    return (
        "# EVIDENZ-ANTWORT-GUARD\n"
        "- Trenne sichtbar zwischen:\n"
        "  1. Was aus dem uebergebenen Recherchekontext belastbar ist\n"
        "  2. Was nur allgemeiner praktischer Rat oder Beispiel ist\n"
        "  3. Was zeitkritisch, lokal oder marktseitig neu geprueft werden sollte\n"
        "- Nenne keine exakten Gehalts-, Nachfrage-, Plattform- oder Zertifikatsangaben als harte Fakten, "
        "wenn sie nicht im uebergebenen Kontext belegt sind.\n"
        "- Wenn du Plattformen, Kurse oder Zertifikate erwaehnst, markiere sie als Beispiele oder allgemein "
        "bekannte Optionen, nicht als verifizierte Top-Empfehlung.\n"
        "- Bei Karriere- und Einstiegsthemen Risiken offen nennen: schwankende Bezahlung, regionale Unterschiede, "
        "projektbasierte Arbeit, instabile Verfuegbarkeit.\n"
        "- Klinge nicht sicherer als die Evidenzlage. Wenn die Quellenlage gemischt oder lueckenhaft ist, sag das klar.\n"
    )

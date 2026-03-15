"""ExecutorAgent - Schnelle einfache Tasks."""

from __future__ import annotations

import re
from typing import Any

from agent.base_agent import BaseAgent
from agent.prompts import EXECUTOR_PROMPT_TEMPLATE
from agent.shared.delegation_handoff import DelegationHandoff, parse_delegation_handoff


_LOCATION_ONLY_HINTS = (
    "wo bin ich",
    "mein standort",
    "welcher ort ist das",
    "wo befinde ich mich",
)

_NEARBY_QUERY_HINTS = (
    ("apothek", "Apotheke"),
    ("drogerie", "Drogerie"),
    ("supermarkt", "Supermarkt"),
    ("lebensmittel", "Supermarkt"),
    ("restaurant", "Restaurant"),
    ("cafe", "Cafe"),
    ("kaffee", "Cafe"),
    ("baeck", "Baeckerei"),
    ("bäck", "Baeckerei"),
    ("bar", "Bar"),
    ("tankstelle", "Tankstelle"),
    ("bank", "Bank"),
    ("hotel", "Hotel"),
    ("arzt", "Arzt"),
    ("krankenhaus", "Krankenhaus"),
    ("geschaeft", "Geschaefte"),
    ("geschäft", "Geschaefte"),
    ("laden", "Geschaefte"),
    ("shop", "Geschaefte"),
)

_SMALLTALK_PATTERNS = (
    r"\bhey\b",
    r"\bhi\b",
    r"\bhallo\b",
    r"\bservus\b",
    r"\bmoin\b",
    r"\bwie geht'?s\b",
    r"\bwas geht\b",
    r"\bna\b",
)

_SELF_STATUS_PATTERNS = (
    r"\bwas hast du (fuer|für) probleme\b",
    r"\bwelche probleme hast du\b",
    r"\bwas ist los\b",
    r"\bwo hakt es\b",
    r"\bwelche probleme gibt es\b",
    r"\bsag du es mir\b",
)

_SELF_REMEDIATION_PATTERNS = (
    r"\bwas kannst du dagegen tun\b",
    r"\bund was kannst du dagegen tun\b",
    r"\bwas tust du dagegen\b",
    r"\bwie behebst du das\b",
    r"\bwie willst du das beheben\b",
    r"\bund was jetzt\b",
    r"\bwas machst du jetzt dagegen\b",
)

_SELF_PRIORITY_PATTERNS = (
    r"\bwas davon machst du zuerst\b",
    r"\bwomit faengst du an\b",
    r"\bwomit fängst du an\b",
    r"\bwas zuerst\b",
    r"\bwelchen schritt zuerst\b",
    r"\bwie priorisierst du das\b",
    r"\bwas machst du als erstes\b",
)

_SELF_RECALL_PATTERNS = (
    r"\bwie war nochmal\b",
    r"\bwas war nochmal\b",
    r"\berinner\b",
    r"\bwie hattest du\b",
    r"\bwas hattest du\b",
    r"\bnochmal erklaer\b",
    r"\bnochmal erklär\b",
)

_YOUTUBE_GENERIC_PATTERNS = (
    r"^hey\s+timus[, ]*",
    r"^herr\s+thimus[, ]*",
    r"^herr\s+timus[, ]*",
    r"^timus[, ]*",
    r"\bauf youtube\b",
    r"\bbei youtube\b",
    r"\bin youtube\b",
    r"\byoutube\s+rein\b",
    r"\bmal\b",
    r"\bkurz\b",
    r"\brein\b",
    r"\bso\b",
    r"\bgibt'?s\b",
    r"\bgibt es\b",
    r"\bwas gibt'?s neues\b",
    r"\bwas gibt es neues\b",
    r"\bwas es so\b",
    r"\bschau mal\b",
    r"\bzeig mir\b",
    r"\bfinde mir\b",
    r"\bfuer mich\b",
    r"\bfür mich\b",
    r"\bbitte\b",
    r"\bnur dinge die\b",
    r"\bnur videos die\b",
    r"\bnur inhalte die\b",
    r"\bgeben kann\b",
    r"\binteressant(?:es|e)?\b",
    r"\brelavant(?:e)?\s+sind\b",
    r"\brelevant(?:e)?\s+sind\b",
    r"\bauch\s+englisch(?:[- ]?sprachige?)?\b",
    r"\benglisch[- ]?sprachige?\b",
    r"\bauf englisch\b",
)

_YOUTUBE_EDGE_FILLER_TOKENS = {
    "was",
    "es",
    "die",
    "das",
    "der",
    "den",
    "dem",
    "ein",
    "eine",
    "einer",
    "neues",
    "neu",
    "aktuelles",
    "aktuell",
    "gibt",
    "gibts",
    "gibt's",
    "videos",
    "video",
    "kurz",
    "rein",
    "nur",
    "mich",
    "mir",
    "dinge",
    "inhalte",
    "beitraege",
    "beiträge",
    "relavant",
    "relevant",
    "sprachige",
}

_YOUTUBE_DE_TO_EN_TERMS: dict[str, str] = {
    "ki": "AI",
    "künstliche intelligenz": "artificial intelligence",
    "agenten": "agents",
    "agent": "agent",
    "entwicklungen": "developments",
    "entwicklung": "development",
    "neuigkeiten": "news",
    "nachrichten": "news",
    "modelle": "models",
    "modell": "model",
    "sprachmodell": "language model",
    "sprachmodelle": "language models",
    "selbstlernend": "self-learning",
    "autonomie": "autonomy",
}


_YOUTUBE_EN_FILLER_TOKENS = {
    "schau", "was", "es", "gibt", "neues", "neu", "neue", "aktuell",
    "aktuelles", "bereich", "zum", "thema", "selbst", "und",
    "die", "der", "das", "auch", "im", "in", "an", "auf",
    "mit", "von", "für", "fuer", "zu",
}


def _youtube_translate_query(query: str) -> str:
    """Einfache DE→EN Übersetzung für KI-Kernbegriffe + Bereinigung verbliebener Filler."""
    result = query.lower()
    for de, en in sorted(_YOUTUBE_DE_TO_EN_TERMS.items(), key=lambda x: -len(x[0])):
        result = re.sub(r"\b" + re.escape(de) + r"\b", en, result, flags=re.IGNORECASE)
    # Verbliebene deutsche Filler-Tokens entfernen die nicht übersetzt wurden
    tokens = result.split()
    cleaned = [t for t in tokens if t not in _YOUTUBE_EN_FILLER_TOKENS]
    # Edge-Filler an Wortgrenzen trimmen
    while cleaned and cleaned[0] in _YOUTUBE_EN_FILLER_TOKENS:
        cleaned.pop(0)
    while cleaned and cleaned[-1] in _YOUTUBE_EN_FILLER_TOKENS:
        cleaned.pop()
    return " ".join(cleaned).strip()


def _detect_youtube_language_preference(text: str) -> list[str]:
    """Erkennt ob der Nutzer explizit englische Inhalte möchte."""
    normalized = str(text or "").lower()
    wants_english = any(m in normalized for m in (
        "englisch", "englischsprachig", "english", "auf englisch", "in english",
    ))
    if wants_english:
        return ["de", "en"]
    return ["de"]


class ExecutorAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(EXECUTOR_PROMPT_TEMPLATE, tools_description_string, 30, "executor")

    def _build_executor_handoff_context(self, handoff: DelegationHandoff | None) -> str:
        if not handoff:
            return ""

        lines: list[str] = ["# STRUKTURIERTER EXECUTOR-HANDOFF"]
        if handoff.expected_output:
            lines.append(f"Erwarteter Output: {handoff.expected_output}")
        if handoff.success_signal:
            lines.append(f"Erfolgssignal: {handoff.success_signal}")
        if handoff.constraints:
            lines.append("Constraints: " + " | ".join(handoff.constraints))

        for key, label in (
            ("task_type", "Task-Typ"),
            ("recipe_id", "Rezept"),
            ("stage_id", "Stage"),
            ("site_kind", "Seitenklasse"),
            ("strategy_id", "Strategie"),
            ("strategy_mode", "Strategiemodus"),
            ("error_strategy", "Fehlerstrategie"),
            ("preferred_search_tool", "Bevorzugtes Suchtool"),
            ("preferred_tools", "Bevorzugte Tools"),
            ("fallback_tools", "Fallback-Tools"),
            ("avoid_tools", "Zu vermeidende Tools"),
            ("search_mode", "Suchmodus"),
            ("max_results", "Max Ergebnisse"),
            ("avoid_deep_research", "Deep-Research vermeiden"),
            ("previous_stage_result", "Vorheriges Stage-Ergebnis"),
            ("previous_blackboard_key", "Blackboard-Key"),
        ):
            value = handoff.handoff_data.get(key)
            if value:
                lines.append(f"{label}: {value}")
        return "\n".join(lines)

    @staticmethod
    def _recover_user_query(task_text: str) -> str:
        text = str(task_text or "").strip()
        if not text:
            return ""
        current_query_match = re.search(
            r"#\s*current user query\s*(.+)$",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if current_query_match:
            recovered = current_query_match.group(1).strip()
            if recovered:
                return recovered
        match = re.search(r"nutzeranfrage:\s*(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            recovered = match.group(1).strip()
            if recovered:
                return recovered
        lowered = text.lower()
        if lowered.startswith("antworte ausschliesslich auf deutsch") or lowered.startswith(
            "antworte ausschließlich auf deutsch"
        ):
            return ""
        return text

    @staticmethod
    def _recover_semantic_recall(task_text: str) -> list[str]:
        text = str(task_text or "")
        match = re.search(
            r"semantic_recall:\s*(.+?)(?:\n#\s*current user query|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return []
        raw = match.group(1).strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split("||") if part.strip()]

    @staticmethod
    def _recover_recent_assistant_replies(task_text: str) -> list[str]:
        text = str(task_text or "")
        match = re.search(
            r"recent_assistant_replies:\s*(.+?)(?:\n[#a-z_]+:|\n#\s*current user query|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return []
        raw = match.group(1).strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split("||") if part.strip()]

    @staticmethod
    def _recover_session_summary(task_text: str) -> str:
        text = str(task_text or "")
        match = re.search(
            r"session_summary:\s*(.+?)(?:\n[a-z_]+:|\n#\s*current user query|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""
        return match.group(1).strip()

    @staticmethod
    def _recover_topic_recall(task_text: str) -> list[str]:
        text = str(task_text or "")
        match = re.search(
            r"topic_recall:\s*(.+?)(?:\n[#a-z_]+:|\n#\s*current user query|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return []
        raw = match.group(1).strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split("||") if part.strip()]

    @staticmethod
    def _recover_followup_session_id(task_text: str) -> str:
        text = str(task_text or "")
        match = re.search(r"session_id:\s*([^\n]+)", text, flags=re.IGNORECASE)
        if not match:
            return ""
        return match.group(1).strip()

    @staticmethod
    def _tool_payload(result: dict[str, Any] | Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}
        payload = result.get("data")
        return payload if isinstance(payload, dict) else result

    @staticmethod
    def _tool_list_payload(result: dict[str, Any] | list[Any] | Any) -> list[dict[str, Any]]:
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if not isinstance(result, dict):
            return []
        payload = result.get("data")
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            return [item for item in payload["results"] if isinstance(item, dict)]
        if isinstance(result.get("results"), list):
            return [item for item in result["results"] if isinstance(item, dict)]
        return []

    @staticmethod
    def _record_conversation_recall(
        *,
        session_id: str,
        query: str,
        source: str,
        semantic_recall: list[str],
        recent_assistant_replies: list[str],
        session_summary: str,
    ) -> None:
        try:
            from orchestration.self_improvement_engine import (
                ConversationRecallRecord,
                get_improvement_engine,
            )

            top_agent = ""
            top_role = ""
            top_distance = 0.0
            if semantic_recall:
                header = str(semantic_recall[0]).split("=>", 1)[0].strip()
                if ":" in header:
                    top_role, top_agent = [part.strip() for part in header.split(":", 1)]
                else:
                    top_role = header
            get_improvement_engine().record_conversation_recall(
                ConversationRecallRecord(
                    session_id=session_id,
                    query=query,
                    source=source,
                    semantic_candidates=len(semantic_recall),
                    recent_reply_candidates=len(recent_assistant_replies),
                    used_summary=bool(session_summary),
                    top_agent=top_agent,
                    top_role=top_role,
                    top_distance=top_distance,
                )
            )
        except Exception:
            return

    @staticmethod
    def _format_distance(distance_meters: Any) -> str:
        try:
            value = float(distance_meters)
        except (TypeError, ValueError):
            return ""
        if value >= 1000:
            return f"{value / 1000:.1f} km"
        return f"{int(round(value))} m"

    @staticmethod
    def _format_rating(place: dict[str, Any]) -> str:
        rating = place.get("rating")
        reviews = place.get("reviews")
        if isinstance(rating, (int, float)) and rating > 0:
            if isinstance(reviews, int) and reviews > 0:
                return f"{rating:.1f} ({reviews} Reviews)"
            return f"{rating:.1f}"
        return ""

    @classmethod
    def _location_summary(cls, location: dict[str, Any]) -> str:
        display_name = str(location.get("display_name") or "").strip()
        locality = str(location.get("locality") or "").strip()
        admin_area = str(location.get("admin_area") or "").strip()
        country_name = str(location.get("country_name") or "").strip()

        if display_name:
            return display_name

        parts = [part for part in (locality, admin_area, country_name) if part]
        return ", ".join(parts)

    @classmethod
    def _infer_location_nearby_query(cls, user_task: str) -> str:
        normalized = str(user_task or "").strip().lower()
        if not normalized:
            return ""

        if any(hint in normalized for hint in _LOCATION_ONLY_HINTS):
            return ""

        for token, mapped in _NEARBY_QUERY_HINTS:
            if token in normalized:
                return mapped

        if "offen" in normalized:
            return "Geschaefte"
        if any(
            hint in normalized
            for hint in ("in meiner naehe", "in meiner nähe", "um mich herum", "um mich", "hier")
        ):
            return "Orte"
        return ""

    @staticmethod
    def _is_smalltalk_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 12:
            return False
        return any(re.search(pattern, normalized) for pattern in _SMALLTALK_PATTERNS)

    @staticmethod
    def _smalltalk_response(task: str) -> str:
        normalized = str(task or "").strip().lower()
        if "wie geht" in normalized:
            return (
                "Lauft. Die Systeme stehen gerade wieder, und ich bin einsatzbereit. "
                "Wenn du etwas Konkretes willst, sag es direkt."
            )
        if "was geht" in normalized or "was gibt" in normalized:
            return (
                "Gerade nichts Magisches. Ich bin da, die Systeme laufen, und du kannst mir direkt Arbeit geben."
            )
        return "Ich bin da. Sag direkt, was du brauchst."

    @staticmethod
    def _is_self_status_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 16:
            return False
        return any(re.search(pattern, normalized) for pattern in _SELF_STATUS_PATTERNS)

    @staticmethod
    def _is_self_remediation_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 20:
            return False
        return any(re.search(pattern, normalized) for pattern in _SELF_REMEDIATION_PATTERNS)

    @staticmethod
    def _is_self_priority_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 20:
            return False
        return any(re.search(pattern, normalized) for pattern in _SELF_PRIORITY_PATTERNS)

    @staticmethod
    def _is_self_recall_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 24:
            return False
        return any(re.search(pattern, normalized) for pattern in _SELF_RECALL_PATTERNS)

    @staticmethod
    def _is_topic_followup_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 24:
            return False
        if any(re.search(pattern, normalized) for pattern in _SELF_RECALL_PATTERNS):
            return True
        if "nochmal" in normalized and "mit " in normalized:
            return True
        if ("erklaer" in normalized or "erklär" in normalized) and "mit " in normalized:
            return True
        return False

    @classmethod
    def _format_ops_self_status(cls, ops: dict[str, Any]) -> str:
        state = str(ops.get("state") or "unknown").strip().lower()
        critical = int(ops.get("critical_alerts") or 0)
        warnings = int(ops.get("warnings") or 0)
        failing_services = int(ops.get("failing_services") or 0)
        unhealthy_providers = int(ops.get("unhealthy_providers") or 0)
        alerts = ops.get("alerts") or []
        if not isinstance(alerts, list):
            alerts = []

        if state in {"ok", "healthy", "green"} and critical == 0 and warnings == 0:
            return (
                "Gerade nichts Kritisches. MCP und Dispatcher laufen, und ich sehe im Ops-Bild aktuell keine akute Stoerung."
            )

        lines = [
            "Gerade sehe ich diese Baustellen bei mir:",
            f"- Zustand: {state or 'unknown'}",
            f"- Kritische Alerts: {critical}",
            f"- Warnungen: {warnings}",
        ]
        if failing_services:
            lines.append(f"- Problematische Services: {failing_services}")
        if unhealthy_providers:
            lines.append(f"- Wackelige Provider: {unhealthy_providers}")
        for alert in alerts[:3]:
            if not isinstance(alert, dict):
                continue
            message = str(alert.get("message") or "").strip()
            severity = str(alert.get("severity") or "warn").strip()
            if message:
                lines.append(f"- {severity}: {message}")
        return "\n".join(lines)

    @classmethod
    def _format_ops_remediation(cls, ops: dict[str, Any]) -> str:
        alerts = ops.get("alerts") or []
        if not isinstance(alerts, list):
            alerts = []
        messages = [
            str(alert.get("message") or "").strip().lower()
            for alert in alerts
            if isinstance(alert, dict) and str(alert.get("message") or "").strip()
        ]

        actions: list[str] = []
        if any("routing visual" in message for message in messages):
            actions.append(
                "Visual strenger nur fuer echte UI-Aufgaben verwenden und lockere Text-/Statusfragen davor abfangen."
            )
        if any("routing research" in message for message in messages):
            actions.append(
                "Leichte Recherchefaelle im executor halten und Research erst bei echter Tiefe oder Quellenpflicht zuschalten."
            )
        if int(ops.get("failing_services") or 0) > 0:
            actions.append(
                "Die betroffenen Services gezielt beobachten, Health-Checks schaerfer auswerten und Absturzpfade isolieren."
            )
        if int(ops.get("unhealthy_providers") or 0) > 0:
            actions.append(
                "Instabile Modellpfade auf stabilere Provider umlegen und Fallbacks frueher aktivieren."
            )
        if not actions:
            actions.append("Die aktuellen Warnungen weiter beobachten und die auffaelligen Routing-Pfade gezielt haerten.")

        lines = ["Dagegen kann ich im Moment konkret Folgendes tun:"]
        for action in actions[:4]:
            lines.append(f"- {action}")
        return "\n".join(lines)

    @classmethod
    def _format_ops_priority(cls, ops: dict[str, Any]) -> str:
        alerts = ops.get("alerts") or []
        if not isinstance(alerts, list):
            alerts = []
        messages = [
            str(alert.get("message") or "").strip().lower()
            for alert in alerts
            if isinstance(alert, dict) and str(alert.get("message") or "").strip()
        ]

        first_step = "Zuerst die auffaelligste Warnung isolieren und dann den naechsten Engpass nachziehen."
        reason = "Das reduziert das akute Risiko am schnellsten."

        if any("routing visual" in message for message in messages):
            first_step = (
                "Zuerst den Visual-Pfad haerten und vage Folgefragen strikt aus dem Screen-/UI-Pfad heraushalten."
            )
            reason = "Der Visual-Routing-Fehler ist aktuell der kritischste und fuehrt direkt in Absturzpfade."
        elif any("routing research" in message for message in messages):
            first_step = (
                "Zuerst leichte Recherchefaelle aus Deep-Research herausziehen und im executor deterministisch beantworten."
            )
            reason = "Damit sinken Last, Latenz und Fehlrouting gleichzeitig."
        elif int(ops.get("failing_services") or 0) > 0:
            first_step = "Zuerst die betroffenen Services stabilisieren und Health-Checks enger auswerten."
            reason = "Wenn Services wackeln, bringt Optimierung auf höherer Ebene wenig."
        elif int(ops.get("unhealthy_providers") or 0) > 0:
            first_step = "Zuerst den instabilsten Modellpfad auf einen robusteren Provider umlegen."
            reason = "Ein instabiler Provider zieht sonst weitere Fehlerketten nach sich."

        return "\n".join(
            [
                "Als Erstes wuerde ich das hier angehen:",
                f"- {first_step}",
                f"- Warum zuerst: {reason}",
            ]
        )

    @classmethod
    def _format_semantic_recall_response(
        cls,
        user_task: str,
        recall_lines: list[str],
        session_summary: str = "",
    ) -> str:
        if not recall_lines and not session_summary:
            return ""

        primary = recall_lines[0] if recall_lines else session_summary[:240]
        if "visual" in str(user_task or "").lower():
            return "\n".join(
                [
                    "Daran erinnere ich mich aus dem bisherigen Verlauf:",
                    f"- {primary}",
                    "- Das ist weiter mein relevanter Bezugspunkt fuer den Visual-Pfad.",
                ]
            )
        return "\n".join(
            [
                "Daran erinnere ich mich aus dem bisherigen Verlauf:",
                f"- {primary}",
            ]
        )

    @staticmethod
    def _infer_topic_focus_label(user_task: str) -> str:
        normalized = str(user_task or "").strip().lower()
        match = re.search(
            r"\bmit\s+(?:dem|der|den|des|die|das)?\s*([a-zA-Z0-9äöüÄÖÜß_-]+)",
            normalized,
        )
        if match:
            token = match.group(1).strip(" -_")
            if token:
                return token
        return ""

    @classmethod
    def _format_topic_recall_response(cls, user_task: str, topic_lines: list[str]) -> str:
        if not topic_lines:
            return ""

        primary = str(topic_lines[0]).strip()
        if not primary:
            return ""

        normalized = str(user_task or "").strip().lower()
        focus = cls._infer_topic_focus_label(user_task)

        if "erklaer" in normalized or "erklär" in normalized:
            if focus:
                return f"Klar. Mit {focus} meinte ich: {primary}"
            return f"Klar. Damit meinte ich: {primary}"

        if focus:
            return f"Mit {focus} war gemeint: {primary}"

        return f"Damit war gemeint: {primary}"

    @staticmethod
    def _infer_youtube_search_query(user_task: str) -> str:
        normalized = str(user_task or "").strip().lower()
        if not normalized:
            return "trending deutschland"

        query = normalized
        for pattern in _YOUTUBE_GENERIC_PATTERNS:
            query = re.sub(pattern, " ", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+", " ", query).strip(" ,.!?:;")

        # Separator-Extraktion: Inhalt nach typischen Einleitungsphrasen
        for separator in (" zu ", " ueber ", " über ", " fuer ", " für ", " sind ", " über das thema ", " zum thema "):
            padded = f" {query} "
            if separator in padded:
                tail = query.split(separator.strip(), 1)[1].strip(" ,.!?:;")
                # Tail nur nehmen wenn er mehr Inhalt hat als das was davor war
                if tail and len(tail.split()) >= 2:
                    query = tail
                    break

        # Zweite Bereinigungsrunde nach Separator-Split
        for pattern in _YOUTUBE_GENERIC_PATTERNS:
            query = re.sub(pattern, " ", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+", " ", query).strip(" ,.!?:;")

        tokens = [token for token in query.split() if token]
        while tokens and tokens[0] in _YOUTUBE_EDGE_FILLER_TOKENS:
            tokens.pop(0)
        while tokens and tokens[-1] in _YOUTUBE_EDGE_FILLER_TOKENS:
            tokens.pop()
        query = " ".join(tokens).strip()

        if not query or len(query) < 3:
            return "trending deutschland"
        if query in {"youtube", "neu", "neues", "aktuell", "aktuelle videos"}:
            return "trending deutschland"
        return query

    @classmethod
    def _format_views(cls, views: Any) -> str:
        try:
            value = int(views)
        except (TypeError, ValueError):
            return ""
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f} Mio. Aufrufe"
        if value >= 1_000:
            return f"{value / 1_000:.1f} Tsd. Aufrufe"
        return f"{value} Aufrufe"

    @classmethod
    def _format_youtube_light_response(
        cls,
        *,
        user_task: str,
        search_query: str,
        results: list[dict[str, Any]],
    ) -> str:
        if not results:
            return (
                f"Ich habe auf YouTube gerade keine brauchbaren Treffer fuer '{search_query}' gefunden. "
                "Wenn du willst, nenne mir ein konkretes Thema oder einen Kanal."
            )

        generic_request = search_query == "trending deutschland"
        if generic_request:
            lines = ["Auf YouTube fallen gerade diese aktuellen Treffer auf:"]
        else:
            lines = [f"Auf YouTube habe ich zu '{search_query}' gerade diese Treffer gefunden:"]

        for item in results[:5]:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            parts = [title]
            channel_name = str(item.get("channel_name") or "").strip()
            if channel_name:
                parts.append(channel_name)
            views = cls._format_views(item.get("views_count"))
            if views:
                parts.append(views)
            url = str(item.get("url") or "").strip()
            if url:
                parts.append(url)
            lines.append("- " + " | ".join(parts))

        if generic_request and any(token in str(user_task or "").lower() for token in ("neu", "neues", "aktuell")):
            lines.append("Wenn du willst, filtere ich das direkt weiter nach Thema, Kanal oder nur deutschsprachigen Videos.")
        return "\n".join(lines)

    @classmethod
    def _format_location_response(
        cls,
        *,
        user_task: str,
        location: dict[str, Any],
        maps_results: list[dict[str, Any]],
        maps_query: str,
    ) -> str:
        location_summary = cls._location_summary(location)
        if not location_summary:
            location_summary = "deinem aktuellen Mobil-Standort"

        lines = [f"Du bist gerade bei {location_summary}."]

        if not maps_query:
            maps_url = str(location.get("maps_url") or "").strip()
            if maps_url:
                lines.append(f"Google Maps: {maps_url}")
            return " ".join(lines)

        if not maps_results:
            lines.append(
                f"Ich habe auf Google Maps gerade keine klaren Treffer fuer '{maps_query}' in deiner unmittelbaren Naehe gefunden."
            )
            return " ".join(lines)

        lines.append(f"In deiner Naehe habe ich fuer '{maps_query}' diese Treffer gefunden:")
        for place in maps_results[:5]:
            title = str(place.get("title") or "").strip()
            if not title:
                continue
            parts = [title]
            distance = cls._format_distance(place.get("distance_meters"))
            if distance:
                parts.append(distance)
            hours = str(place.get("hours_summary") or "").strip()
            if hours:
                parts.append(hours)
            rating = cls._format_rating(place)
            if rating:
                parts.append(f"Rating {rating}")
            address = str(place.get("address") or "").strip()
            if address:
                parts.append(address)
            lines.append("- " + " | ".join(parts))

        if "offen" in str(user_task or "").lower():
            lines.append("Oeffnungszeiten sind, sofern vorhanden, direkt aus Google Maps uebernommen.")
        return "\n".join(lines)

    async def _run_location_local_search(self, handoff: DelegationHandoff) -> str:
        user_task = self._recover_user_query(
            (
            handoff.handoff_data.get("original_user_task")
            or handoff.handoff_data.get("query")
            or handoff.goal
            or ""
            )
        )
        location_result = await self._call_tool("get_current_location_context", {})
        if isinstance(location_result, dict) and location_result.get("error"):
            return f"Ich konnte den aktuellen Standort nicht laden: {location_result['error']}"

        location_payload = self._tool_payload(location_result)
        has_location = bool(location_payload.get("has_location"))
        location = location_payload.get("location")
        if not has_location or not isinstance(location, dict):
            return (
                "Ich habe aktuell keinen synchronisierten Handy-Standort. "
                "Oeffne in der App Home > Standort und aktualisiere ihn, dann kann ich lokale Orte ueber Google Maps finden."
            )

        maps_query = self._infer_location_nearby_query(user_task)
        if not maps_query:
            return self._format_location_response(
                user_task=user_task,
                location=location,
                maps_results=[],
                maps_query="",
            )

        maps_result = await self._call_tool(
            "search_google_maps_places",
            {"query": maps_query, "max_results": 5, "language_code": "de"},
        )
        if isinstance(maps_result, dict) and maps_result.get("error"):
            return (
                self._format_location_response(
                    user_task=user_task,
                    location=location,
                    maps_results=[],
                    maps_query="",
                )
                + f" Die Google-Maps-Suche ist gerade fehlgeschlagen: {maps_result['error']}"
            )

        maps_payload = self._tool_payload(maps_result)
        maps_results = maps_payload.get("results")
        if not isinstance(maps_results, list):
            maps_results = []
        return self._format_location_response(
            user_task=user_task,
            location=location,
            maps_results=maps_results,
            maps_query=maps_query,
        )

    async def _run_youtube_light_research(self, handoff: DelegationHandoff) -> str:
        raw_task = (
            handoff.handoff_data.get("original_user_task")
            or handoff.handoff_data.get("query")
            or handoff.goal
            or ""
        )
        user_task = self._recover_user_query(raw_task)
        preferred_search_tool = str(handoff.handoff_data.get("preferred_search_tool") or "search_youtube").strip()
        max_results = handoff.handoff_data.get("max_results") or 5
        try:
            max_results_int = max(1, min(int(max_results), 10))
        except (TypeError, ValueError):
            max_results_int = 5
        search_mode = str(handoff.handoff_data.get("search_mode") or "live").strip() or "live"
        search_query = self._infer_youtube_search_query(user_task)
        lang_prefs = _detect_youtube_language_preference(user_task)

        # P2: Referenz-Fortsetzung — kurze Query + topic_recall im vollen Task-Text
        # Beispiel: "mach damit eine youtube suche" → user_task ist kurz, kein verwertbares Thema
        if search_query == "trending deutschland" or len(search_query.split()) <= 2:
            topic_recall = self._recover_topic_recall(raw_task)
            if topic_recall:
                # Ersten Recall-Eintrag als Query-Basis nehmen
                recall_text = topic_recall[0]
                recall_query = self._infer_youtube_search_query(recall_text)
                if recall_query and recall_query != "trending deutschland":
                    search_query = recall_query
                    lang_prefs = _detect_youtube_language_preference(recall_text)

        seen_ids: set[str] = set()
        combined_results: list[dict] = []

        async def _fetch(query: str, lang: str) -> list[dict]:
            res = await self._call_tool(
                preferred_search_tool,
                {
                    "query": query,
                    "max_results": max_results_int,
                    "language_code": lang,
                    "mode": search_mode,
                },
            )
            if isinstance(res, dict) and res.get("error"):
                return []
            return self._tool_list_payload(res)

        def _dedup_add(items: list[dict]) -> None:
            for item in items:
                vid = str(item.get("video_id") or "").strip()
                if vid:
                    if vid not in seen_ids:
                        seen_ids.add(vid)
                        combined_results.append(item)
                else:
                    # Kein video_id (z.B. Mock-Daten) → anhand Titel deduplizieren
                    title_key = str(item.get("title") or "").strip().lower()
                    if title_key and title_key not in seen_ids:
                        seen_ids.add(title_key)
                        combined_results.append(item)
                    elif not title_key:
                        combined_results.append(item)

        # DE-Suche immer
        _dedup_add(await _fetch(search_query, "de"))

        # EN-Suche wenn Nutzer englische Inhalte wollte
        if "en" in lang_prefs:
            en_query = _youtube_translate_query(search_query)
            if en_query and en_query != search_query:
                _dedup_add(await _fetch(en_query, "en"))

        if not combined_results:
            return (
                f"Die YouTube-Suche ist gerade fehlgeschlagen oder lieferte keine Treffer fuer '{search_query}'. "
                "Wenn du willst, versuche ich es gleich mit einer praeziseren Suchanfrage nochmal."
            )

        return self._format_youtube_light_response(
            user_task=user_task,
            search_query=search_query,
            results=combined_results,
        )

    async def _run_self_status_probe(self) -> str:
        ops_result = await self._call_tool("get_ops_observability", {"days": 7, "limit": 4})
        if isinstance(ops_result, dict) and ops_result.get("error"):
            return (
                f"Ich kann meinen aktuellen Ops-Zustand gerade nicht sauber lesen: {ops_result['error']}"
            )
        payload = self._tool_payload(ops_result)
        return self._format_ops_self_status(payload)

    async def _run_self_remediation_probe(self) -> str:
        ops_result = await self._call_tool("get_ops_observability", {"days": 7, "limit": 4})
        if isinstance(ops_result, dict) and ops_result.get("error"):
            return (
                f"Ich kann meine Gegenmassnahmen gerade nicht sauber ableiten: {ops_result['error']}"
            )
        payload = self._tool_payload(ops_result)
        return self._format_ops_remediation(payload)

    async def _run_self_priority_probe(self) -> str:
        ops_result = await self._call_tool("get_ops_observability", {"days": 7, "limit": 4})
        if isinstance(ops_result, dict) and ops_result.get("error"):
            return (
                f"Ich kann meine Priorisierung gerade nicht sauber ableiten: {ops_result['error']}"
            )
        payload = self._tool_payload(ops_result)
        return self._format_ops_priority(payload)

    @staticmethod
    def _recover_resolved_proposal(task_text: str) -> dict | None:
        """P4: Parst RESOLVED_PROPOSAL-Block aus dem Task-Text."""
        text = str(task_text or "")
        if "# RESOLVED_PROPOSAL" not in text:
            return None
        kind_match = re.search(r"^kind:\s*(\S+)", text, re.MULTILINE)
        query_match = re.search(r"^suggested_query:\s*(.+)$", text, re.MULTILINE)
        raw_match = re.search(r"^raw_proposal:\s*(.+)$", text, re.MULTILINE)
        if not kind_match or not query_match:
            return None
        return {
            "kind": kind_match.group(1).strip(),
            "suggested_query": query_match.group(1).strip(),
            "raw_proposal": raw_match.group(1).strip() if raw_match else "",
        }

    async def run(self, task: str) -> str:
        handoff = parse_delegation_handoff(task)
        plain_task = self._recover_user_query(task)
        semantic_recall = self._recover_semantic_recall(task)
        recent_assistant_replies = self._recover_recent_assistant_replies(task)
        topic_recall = self._recover_topic_recall(task)
        session_summary = self._recover_session_summary(task)
        followup_session_id = self._recover_followup_session_id(task)

        # P4: RESOLVED_PROPOSAL — Angebot direkt ausführen ohne LLM-Runde
        resolved_proposal = self._recover_resolved_proposal(task)
        if resolved_proposal:
            kind = resolved_proposal.get("kind", "generic_action")
            suggested_query = resolved_proposal.get("suggested_query", "")
            if kind == "youtube_search" and suggested_query:
                from agent.shared.delegation_handoff import DelegationHandoff
                synthetic_handoff = DelegationHandoff(
                    goal=suggested_query,
                    expected_output="YouTube-Videos zu dem angefragten Thema",
                    handoff_data={
                        "task_type": "youtube_light_research",
                        "query": suggested_query,
                        "original_user_task": suggested_query,
                        "search_mode": "live",
                        "max_results": 5,
                    },
                )
                return await self._run_youtube_light_research(synthetic_handoff)

        if handoff and handoff.handoff_data.get("task_type") == "location_local_search":
            return await self._run_location_local_search(handoff)
        if handoff and handoff.handoff_data.get("task_type") == "youtube_light_research":
            return await self._run_youtube_light_research(handoff)
        if not handoff and self._is_self_status_query(plain_task):
            return await self._run_self_status_probe()
        if not handoff and self._is_self_remediation_query(plain_task):
            return await self._run_self_remediation_probe()
        if not handoff and self._is_self_priority_query(plain_task):
            return await self._run_self_priority_probe()
        if not handoff and self._is_self_recall_query(plain_task):
            recall_basis = semantic_recall or recent_assistant_replies
            recall_source = (
                "semantic"
                if semantic_recall
                else "recent_assistant"
                if recent_assistant_replies
                else "summary"
                if session_summary
                else "none"
            )
            self._record_conversation_recall(
                session_id=followup_session_id,
                query=plain_task,
                source=recall_source,
                semantic_recall=semantic_recall,
                recent_assistant_replies=recent_assistant_replies,
                session_summary=session_summary,
            )
            formatted_recall = self._format_semantic_recall_response(
                plain_task,
                recall_basis,
                session_summary=session_summary,
            )
            if formatted_recall:
                return formatted_recall
        if not handoff and topic_recall and self._is_topic_followup_query(plain_task):
            self._record_conversation_recall(
                session_id=followup_session_id,
                query=plain_task,
                source="topic_recall",
                semantic_recall=[],
                recent_assistant_replies=topic_recall,
                session_summary=session_summary,
            )
            formatted_topic_recall = self._format_topic_recall_response(plain_task, topic_recall)
            if formatted_topic_recall:
                return formatted_topic_recall
        if not handoff and self._is_smalltalk_query(plain_task):
            return self._smalltalk_response(plain_task)
        effective_task = handoff.goal if handoff and handoff.goal else task
        handoff_context = self._build_executor_handoff_context(handoff)
        enriched_task = "\n\n".join(part for part in (effective_task, handoff_context) if part)
        return await super().run(enriched_task)

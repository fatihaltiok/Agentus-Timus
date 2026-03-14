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

_YOUTUBE_GENERIC_PATTERNS = (
    r"^hey\s+timus[, ]*",
    r"^herr\s+thimus[, ]*",
    r"^herr\s+timus[, ]*",
    r"^timus[, ]*",
    r"\bauf youtube\b",
    r"\bbei youtube\b",
    r"\bmal\b",
    r"\bso\b",
    r"\bgibt'?s\b",
    r"\bgibt es\b",
    r"\bwas gibt'?s neues\b",
    r"\bwas gibt es neues\b",
    r"\bschau mal\b",
    r"\bzeig mir\b",
    r"\bfinde mir\b",
    r"\bfuer mich\b",
    r"\bbitte\b",
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
}


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

    @staticmethod
    def _infer_youtube_search_query(user_task: str) -> str:
        normalized = str(user_task or "").strip().lower()
        if not normalized:
            return "trending deutschland"

        query = normalized
        for pattern in _YOUTUBE_GENERIC_PATTERNS:
            query = re.sub(pattern, " ", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+", " ", query).strip(" ,.!?:;")

        for separator in (" zu ", " ueber ", " über ", " fuer ", " für "):
            if separator in f" {query} ":
                tail = query.split(separator, 1)[1].strip(" ,.!?:;")
                if tail:
                    query = tail
                    break

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
        user_task = self._recover_user_query(
            (
            handoff.handoff_data.get("original_user_task")
            or handoff.handoff_data.get("query")
            or handoff.goal
            or ""
            )
        )
        preferred_search_tool = str(handoff.handoff_data.get("preferred_search_tool") or "search_youtube").strip()
        max_results = handoff.handoff_data.get("max_results") or 5
        try:
            max_results_int = max(1, min(int(max_results), 10))
        except (TypeError, ValueError):
            max_results_int = 5
        search_mode = str(handoff.handoff_data.get("search_mode") or "live").strip() or "live"
        search_query = self._infer_youtube_search_query(user_task)

        search_result = await self._call_tool(
            preferred_search_tool,
            {
                "query": search_query,
                "max_results": max_results_int,
                "language_code": "de",
                "mode": search_mode,
            },
        )
        if isinstance(search_result, dict) and search_result.get("error"):
            return (
                f"Die YouTube-Suche ist gerade fehlgeschlagen: {search_result['error']}. "
                "Wenn du willst, versuche ich es gleich mit einer praeziseren Suchanfrage nochmal."
            )

        results = self._tool_list_payload(search_result)
        return self._format_youtube_light_response(
            user_task=user_task,
            search_query=search_query,
            results=results,
        )

    async def _run_self_status_probe(self) -> str:
        ops_result = await self._call_tool("get_ops_observability", {"days": 7, "limit": 4})
        if isinstance(ops_result, dict) and ops_result.get("error"):
            return (
                f"Ich kann meinen aktuellen Ops-Zustand gerade nicht sauber lesen: {ops_result['error']}"
            )
        payload = self._tool_payload(ops_result)
        return self._format_ops_self_status(payload)

    async def run(self, task: str) -> str:
        handoff = parse_delegation_handoff(task)
        plain_task = self._recover_user_query(task)
        if handoff and handoff.handoff_data.get("task_type") == "location_local_search":
            return await self._run_location_local_search(handoff)
        if handoff and handoff.handoff_data.get("task_type") == "youtube_light_research":
            return await self._run_youtube_light_research(handoff)
        if not handoff and self._is_self_status_query(plain_task):
            return await self._run_self_status_probe()
        if not handoff and self._is_smalltalk_query(plain_task):
            return self._smalltalk_response(plain_task)
        effective_task = handoff.goal if handoff and handoff.goal else task
        handoff_context = self._build_executor_handoff_context(handoff)
        enriched_task = "\n\n".join(part for part in (effective_task, handoff_context) if part)
        return await super().run(enriched_task)

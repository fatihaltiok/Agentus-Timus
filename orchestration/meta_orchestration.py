"""Meta-Orchestrierungsmodell fuer Faehigkeiten und Task-Klassifikation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Tuple

from orchestration.adaptive_plan_memory import get_adaptive_plan_memory
from orchestration.adaptive_planner import build_adaptive_plan
from orchestration.capability_graph import build_capability_graph
from orchestration.diagnosis_records import (
    build_diagnosis_records,
    compile_developer_task_brief,
    select_lead_diagnosis,
)
from orchestration.goal_spec import derive_goal_spec
from orchestration.root_cause_tasks import build_root_cause_task_payload
from utils.location_local_intent import is_location_local_query, is_location_route_query


@dataclass(frozen=True)
class AgentCapabilityProfile:
    agent: str
    capabilities: Tuple[str, ...]
    strengths: Tuple[str, ...]
    typical_outputs: Tuple[str, ...]
    handoff_fields: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


@dataclass(frozen=True)
class OrchestrationRecipeStage:
    stage_id: str
    agent: str
    goal: str
    expected_output: str
    handoff_fields: Tuple[str, ...]
    optional: bool = False

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["handoff_fields"] = list(self.handoff_fields)
        return payload


@dataclass(frozen=True)
class OrchestrationRecipeRecovery:
    failed_stage_id: str
    recovery_stage_id: str
    agent: str
    goal: str
    expected_output: str
    handoff_fields: Tuple[str, ...]
    terminal: bool = True

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["handoff_fields"] = list(self.handoff_fields)
        return payload


_AGENT_PROFILES: Dict[str, AgentCapabilityProfile] = {
    "executor": AgentCapabilityProfile(
        agent="executor",
        capabilities=("quick_tool_execution", "light_search", "live_lookup", "youtube_discovery", "short_summaries"),
        strengths=("casual_requests", "fast_search_flows", "lightweight_followups", "location_aware_lookup"),
        typical_outputs=("top_results", "quick_summary", "source_urls"),
        handoff_fields=("goal", "expected_output", "success_signal", "constraints", "handoff_data"),
    ),
    "meta": AgentCapabilityProfile(
        agent="meta",
        capabilities=("planning", "delegation", "workflow_orchestration", "handoff_synthesis"),
        strengths=("multi_step_tasks", "cross_agent_coordination", "result_synthesis"),
        typical_outputs=("plan", "delegation_chain", "final_response"),
        handoff_fields=("goal", "task_type", "expected_output", "constraints", "success_signal", "handoff_data"),
    ),
    "visual": AgentCapabilityProfile(
        agent="visual",
        capabilities=("browser_navigation", "ui_interaction", "form_filling", "state_verification"),
        strengths=("multi_step_web_flows", "login_flows", "site_interaction"),
        typical_outputs=("page_state", "ui_result", "captured_context"),
        handoff_fields=("goal", "expected_state", "success_signal", "browser_plan"),
    ),
    "research": AgentCapabilityProfile(
        agent="research",
        capabilities=("content_extraction", "web_research", "fact_verification", "report_synthesis"),
        strengths=("youtube_analysis", "source_comparison", "summaries", "reports"),
        typical_outputs=("summary", "report", "sources", "artifacts"),
        handoff_fields=("goal", "source_urls", "captured_context", "expected_output"),
    ),
    "document": AgentCapabilityProfile(
        agent="document",
        capabilities=("pdf_creation", "docx_creation", "structured_exports"),
        strengths=("reports", "exports", "artifacts"),
        typical_outputs=("pdf", "docx", "xlsx"),
        handoff_fields=("goal", "source_material", "format", "artifacts"),
    ),
    "communication": AgentCapabilityProfile(
        agent="communication",
        capabilities=("email", "message_drafting", "delivery"),
        strengths=("email_with_attachments", "formal_messages"),
        typical_outputs=("email_body", "message", "delivery_status"),
        handoff_fields=("goal", "recipient", "attachment_path", "message_body"),
    ),
    "system": AgentCapabilityProfile(
        agent="system",
        capabilities=("diagnostics", "log_analysis", "service_inspection"),
        strengths=("incident_triage", "health_analysis"),
        typical_outputs=("status_report", "incident_summary"),
        handoff_fields=("goal", "signals", "success_signal"),
    ),
    "shell": AgentCapabilityProfile(
        agent="shell",
        capabilities=("terminal_execution", "service_control", "script_execution"),
        strengths=("controlled_runtime_actions", "service_restart", "command_execution"),
        typical_outputs=("command_output", "service_state"),
        handoff_fields=("goal", "command", "constraints", "success_signal"),
    ),
}


_ORCHESTRATION_RECIPES: Dict[str, Tuple[OrchestrationRecipeStage, ...]] = {
    "simple_live_lookup": (
        OrchestrationRecipeStage(
            stage_id="live_lookup_scan",
            agent="executor",
            goal=(
                "Fuehre eine kompakte aktuelle Live-Recherche mit direkten Suchtools aus, "
                "nutze vorhandenen Standortkontext automatisch fuer lokale Anfragen und "
                "bleibe auf schnelle verifizierbare Treffer fokussiert."
            ),
            expected_output="quick_summary, top_results, source_urls",
            handoff_fields=("goal", "expected_output", "success_signal", "query", "preferred_search_tool"),
        ),
    ),
    "simple_live_lookup_document": (
        OrchestrationRecipeStage(
            stage_id="live_lookup_scan",
            agent="executor",
            goal=(
                "Fuehre eine kompakte aktuelle Live-Recherche mit direkten Suchtools aus, "
                "extrahiere belastbare Kerndaten oder Tabellenmaterial und bereite das Ergebnis "
                "fuer den nachfolgenden Dokumentschritt vor."
            ),
            expected_output="structured_lookup_result, source_urls, table_material",
            handoff_fields=("goal", "expected_output", "success_signal", "query", "preferred_search_tool"),
        ),
        OrchestrationRecipeStage(
            stage_id="document_output",
            agent="document",
            goal=(
                "Erzeuge aus dem Lookup-Ergebnis die angeforderte Tabelle oder Datei im passenden "
                "Format und liefere einen knappen Preview-Hinweis mit Artefaktpfad."
            ),
            expected_output="xlsx/txt/csv artifact",
            handoff_fields=("goal", "source_material", "format", "artifacts"),
        ),
    ),
    "knowledge_research": (
        OrchestrationRecipeStage(
            stage_id="research_discovery",
            agent="research",
            goal=(
                "Recherchiere externe Fakten, Quellen und belastbare Hintergrundinformationen "
                "ohne UI-Automation und liefere eine verifizierte Zusammenfassung."
            ),
            expected_output="summary, sources, extracted_content",
            handoff_fields=("goal", "source_urls", "captured_context", "expected_output"),
        ),
    ),
    "youtube_light_research": (
        OrchestrationRecipeStage(
            stage_id="youtube_search_scan",
            agent="executor",
            goal=(
                "Durchsuche YouTube leichtgewichtig mit Suchtools und liefere die relevantesten Videos "
                "mit kurzer Einordnung, ohne Deep Research zu starten."
            ),
            expected_output="top_videos, quick_summary, source_urls",
            handoff_fields=("goal", "expected_output", "success_signal", "query", "preferred_search_tool"),
        ),
    ),
    "location_local_search": (
        OrchestrationRecipeStage(
            stage_id="location_context_scan",
            agent="executor",
            goal=(
                "Nutze den aktuellen Mobil-Standort, ordne ihn auf Google Maps ein und liefere "
                "lokalen Kontext oder nearby Places ohne schweren Research-Pfad."
            ),
            expected_output="location_context, nearby_places, quick_summary, source_urls",
            handoff_fields=("goal", "expected_output", "success_signal", "query", "preferred_search_tool"),
        ),
    ),
    "location_route": (
        OrchestrationRecipeStage(
            stage_id="location_route_plan",
            agent="executor",
            goal=(
                "Nutze den aktuellen Mobil-Standort als Startpunkt, erstelle eine echte Google-Maps-Route "
                "zum Ziel und liefere ETA, Distanz, Schritte und Route-URL ohne freie Schaetzwerte."
            ),
            expected_output="route_summary, eta, distance, steps, route_url",
            handoff_fields=("goal", "expected_output", "success_signal", "query", "preferred_search_tool"),
        ),
    ),
    "youtube_content_extraction": (
        OrchestrationRecipeStage(
            stage_id="visual_access",
            agent="visual",
            goal="YouTube-Quelle oeffnen, Video- oder Suchkontext erreichen und belastbare Seitensignale sammeln.",
            expected_output="source_url, page_state, page_title, captured_context",
            handoff_fields=("goal", "expected_state", "success_signal", "captured_context"),
        ),
        OrchestrationRecipeStage(
            stage_id="research_synthesis",
            agent="research",
            goal="Maximalen Video-Inhalt aus Metadaten, Beschreibung, Captions oder Transcript ableiten und mit Kontextquellen verdichten.",
            expected_output="summary, sources, extracted_content",
            handoff_fields=("goal", "source_urls", "captured_context", "expected_output"),
        ),
        OrchestrationRecipeStage(
            stage_id="document_output",
            agent="document",
            goal="Falls ein Bericht oder Artefakt gefordert ist, das Research-Ergebnis in das gewünschte Format ueberfuehren.",
            expected_output="pdf/docx/xlsx artifact",
            handoff_fields=("goal", "source_material", "format", "artifacts"),
            optional=True,
        ),
    ),
    "booking_search": (
        OrchestrationRecipeStage(
            stage_id="visual_search_setup",
            agent="visual",
            goal="Booking-Suche vorbereiten: Ziel, Reisedaten, Gaeste und interaktive UI-Zustaende erreichen.",
            expected_output="search_form_state, filled_inputs, browser_plan",
            handoff_fields=("goal", "expected_state", "success_signal", "browser_plan"),
        ),
        OrchestrationRecipeStage(
            stage_id="visual_results_capture",
            agent="visual",
            goal="Suchlauf abschliessen und die Ergebnisseite mit verifizierten Treffern erreichen.",
            expected_output="results_url, result_signals, captured_context",
            handoff_fields=("goal", "expected_state", "success_signal", "captured_context"),
        ),
    ),
    "system_diagnosis": (
        OrchestrationRecipeStage(
            stage_id="system_observe",
            agent="system",
            goal="Service-, Log- und Health-Signale korrelieren und den Incident fachlich einordnen.",
            expected_output="incident_summary, health_signals, suspected_root_cause",
            handoff_fields=("goal", "signals", "success_signal"),
        ),
        OrchestrationRecipeStage(
            stage_id="shell_remediation",
            agent="shell",
            goal="Nur wenn noetig und explizit erlaubt, kontrollierte Laufzeitaktionen oder Service-Kommandos ausfuehren.",
            expected_output="command_output, service_state",
            handoff_fields=("goal", "command", "constraints", "success_signal"),
            optional=True,
        ),
    ),
    "youtube_research_only": (
        OrchestrationRecipeStage(
            stage_id="research_discovery",
            agent="research",
            goal="Nutze Suchbegriffe, bekannte Quellen und vorhandenen Kontext, um YouTube-Inhalt ohne direkten UI-Zugriff konservativ zu recherchieren.",
            expected_output="summary, sources, extracted_content",
            handoff_fields=("goal", "source_urls", "captured_context", "expected_output"),
        ),
        OrchestrationRecipeStage(
            stage_id="document_output",
            agent="document",
            goal="Falls ein Bericht oder Artefakt gefordert ist, das Research-Ergebnis in das gewünschte Format ueberfuehren.",
            expected_output="pdf/docx/xlsx artifact",
            handoff_fields=("goal", "source_material", "format", "artifacts"),
            optional=True,
        ),
    ),
    "youtube_search_then_visual": (
        OrchestrationRecipeStage(
            stage_id="research_discovery",
            agent="research",
            goal="Sammle zuerst Suchbegriffe, bekannte Quellen und moegliche Video-Hinweise, bevor der UI-Zugriff versucht wird.",
            expected_output="source_urls, query_variants, captured_context",
            handoff_fields=("goal", "source_urls", "captured_context", "expected_output"),
        ),
        OrchestrationRecipeStage(
            stage_id="visual_access",
            agent="visual",
            goal="Nutze die vorbereiteten Suchsignale, um die passende YouTube-Seite oder Videoseite gezielt zu erreichen.",
            expected_output="source_url, page_state, page_title, captured_context",
            handoff_fields=("goal", "expected_state", "success_signal", "captured_context"),
        ),
        OrchestrationRecipeStage(
            stage_id="research_synthesis",
            agent="research",
            goal="Verdichte Video-Inhalt, Beschreibungen und weitere Signale zu einer belastbaren Zusammenfassung.",
            expected_output="summary, sources, extracted_content",
            handoff_fields=("goal", "source_urls", "captured_context", "expected_output"),
        ),
        OrchestrationRecipeStage(
            stage_id="document_output",
            agent="document",
            goal="Falls ein Bericht oder Artefakt gefordert ist, das Research-Ergebnis in das gewünschte Format ueberfuehren.",
            expected_output="pdf/docx/xlsx artifact",
            handoff_fields=("goal", "source_material", "format", "artifacts"),
            optional=True,
        ),
    ),
    "web_visual_research_summary": (
        OrchestrationRecipeStage(
            stage_id="visual_access",
            agent="visual",
            goal="Erreiche die relevante Webseite, den Thread oder den Inhaltskontext und sammle belastbare Seitensignale.",
            expected_output="source_url, page_state, page_title, captured_context",
            handoff_fields=("goal", "expected_state", "success_signal", "captured_context"),
        ),
        OrchestrationRecipeStage(
            stage_id="research_synthesis",
            agent="research",
            goal="Verdichte den erreichbaren Web-Inhalt zu einer verifizierten Zusammenfassung oder Inhaltsanalyse.",
            expected_output="summary, sources, extracted_content",
            handoff_fields=("goal", "source_urls", "captured_context", "expected_output"),
        ),
    ),
    "web_research_only": (
        OrchestrationRecipeStage(
            stage_id="research_discovery",
            agent="research",
            goal="Recherchiere den Web-Inhalt konservativ über bekannte Quellen, Snippets und vorhandenen Kontext ohne direkten UI-Zugriff.",
            expected_output="summary, sources, extracted_content",
            handoff_fields=("goal", "source_urls", "captured_context", "expected_output"),
        ),
    ),
    "system_shell_probe_first": (
        OrchestrationRecipeStage(
            stage_id="shell_runtime_probe",
            agent="shell",
            goal="Fuehre sichere Runtime-Probes aus, um Service-, Prozess- und Portzustand kontrolliert zu ermitteln.",
            expected_output="command_output, service_state",
            handoff_fields=("goal", "command", "constraints", "success_signal"),
        ),
        OrchestrationRecipeStage(
            stage_id="system_validation",
            agent="system",
            goal="Korrigiere die Diagnose auf Basis der Probe-Ausgaben und liefere eine belastbare Incident-Einordnung.",
            expected_output="incident_summary, health_signals, suspected_root_cause",
            handoff_fields=("goal", "signals", "success_signal"),
        ),
    ),
}


_ORCHESTRATION_RECIPE_RECOVERIES: Dict[str, Tuple[OrchestrationRecipeRecovery, ...]] = {
    "youtube_content_extraction": (
        OrchestrationRecipeRecovery(
            failed_stage_id="visual_access",
            recovery_stage_id="research_context_recovery",
            agent="research",
            goal=(
                "Wenn der direkte UI-Zugriff scheitert, nutze Originalanfrage, bekannte Quelle, "
                "Suchbegriffe und vorhandene Kontextsignale, um den YouTube-Inhalt konservativ "
                "direkt zu recherchieren und zusammenzufassen."
            ),
            expected_output="summary, sources, extracted_content",
            handoff_fields=("goal", "source_urls", "captured_context", "expected_output"),
            terminal=False,
        ),
    ),
    "web_visual_research_summary": (
        OrchestrationRecipeRecovery(
            failed_stage_id="visual_access",
            recovery_stage_id="research_context_recovery",
            agent="research",
            goal=(
                "Wenn der direkte Web-Zugriff scheitert, nutze Anfrage, bekannte Quelle und "
                "vorhandene Kontextsignale fuer eine konservative Inhaltsrecherche."
            ),
            expected_output="summary, sources, extracted_content",
            handoff_fields=("goal", "source_urls", "captured_context", "expected_output"),
            terminal=False,
        ),
    ),
    "system_diagnosis": (
        OrchestrationRecipeRecovery(
            failed_stage_id="system_observe",
            recovery_stage_id="shell_runtime_probe",
            agent="shell",
            goal=(
                "Wenn die Systemanalyse fehlschlaegt, fuehre sichere Runtime-Probes aus, "
                "um Service-, Prozess- und Portzustand kontrolliert zu ermitteln."
            ),
            expected_output="command_output, service_state",
            handoff_fields=("goal", "command", "constraints", "success_signal"),
            terminal=True,
        ),
    ),
}


_ORCHESTRATION_RECIPE_AGENT_CHAINS: Dict[str, Tuple[str, ...]] = {
    "simple_live_lookup": ("meta", "executor"),
    "simple_live_lookup_document": ("meta", "executor", "document"),
    "knowledge_research": ("meta", "research"),
    "youtube_light_research": ("meta", "executor"),
    "location_local_search": ("meta", "executor"),
    "location_route": ("meta", "executor"),
    "youtube_content_extraction": ("meta", "visual", "research", "document"),
    "youtube_search_then_visual": ("meta", "research", "visual", "research", "document"),
    "youtube_research_only": ("meta", "research", "document"),
    "web_visual_research_summary": ("meta", "visual", "research"),
    "web_research_only": ("meta", "research"),
    "booking_search": ("meta", "visual"),
    "system_diagnosis": ("meta", "system", "shell"),
    "system_shell_probe_first": ("meta", "shell", "system"),
}

_ADAPTIVE_PLAN_SAFE_TASK_TYPES = {
    "simple_live_lookup",
    "simple_live_lookup_document",
    "knowledge_research",
    "youtube_content_extraction",
    "web_content_extraction",
    "location_local_search",
    "location_route",
}
_ADAPTIVE_PLAN_MIN_CONFIDENCE = 0.78
_ADAPTIVE_PLAN_MAX_CHAIN_LENGTH = 4
_RUNTIME_GOAL_GAP_ALLOWED_PREVIOUS_AGENTS = {"executor", "research"}
_RUNTIME_DELIVERY_ALLOWED_PREVIOUS_AGENTS = {"executor", "research", "document"}
_RUNTIME_VERIFICATION_ALLOWED_PREVIOUS_AGENTS = {"executor"}


_BROWSER_HINTS = (
    "browser",
    "webseite",
    "website",
    "gehe auf",
    "gehe zu",
    "oeffne",
    "oeffne",
    "öffne",
    "navigiere",
    "klicke",
    "tippe",
    "wähle",
    "waehle",
    "formular",
    "login",
    "anmelden",
)

_EXTRACTION_HINTS = (
    "inhalt",
    "extrahiere",
    "maximal viel",
    "fasse zusammen",
    "zusammenfassung",
    "bericht",
    "analysiere",
    "werte aus",
)

_BROAD_RESEARCH_HINTS = (
    "recherchiere",
    "recherche",
    "recherchier",
    "finde heraus",
    "informiere mich über",
    "sammle informationen",
    "erkunde das internet",
    "erkunde das web",
    "erkunde das netz",
    "erkunde ",
    "erforsche",
    "erkundige",
    "stöbere im",
    "stöbern im",
    "im internet stöbern",
    "im web stöbern",
    "im netz stöbern",
    "internet erkunden",
    "web erkunden",
    "netz erkunden",
)

_STRICT_RESEARCH_HINTS = (
    "tiefenrecherche",
    "tiefen recherche",
    "tiefe recherche",
    "deep research",
    "fakten",
    "quellen",
    "aktuelle entwicklungen",
    "neueste erkenntnisse",
    "was gibt es neues",
    "news zu",
    "nachrichten",
    "studie",
    "studien",
    "paper",
    "papers",
)

_SIMPLE_LIVE_LOOKUP_DIRECT_HINTS = (
    "wetter",
    "temperatur",
    "regen",
    "news",
    "nachrichten",
    "neuigkeiten",
    "wissenschaft",
    "kino",
    "film",
    "filme",
    "kinoprogramm",
    "programm im kino",
    "preise",
    "preis",
    "pricing",
    "kosten",
    "vergleich",
    "liste",
    "tabelle",
    "modellpreise",
    "tokenpreise",
    "wer ist",
    "wie heißt",
    "wie heisst",
    "ceo",
    "präsident",
    "praesident",
    "vorstand",
    "cafe",
    "cafés",
    "cafes",
    "kaffee",
    "restaurant",
    "restaurants",
    "bar",
    "apotheke",
    "supermarkt",
)

_SIMPLE_LIVE_LOOKUP_FRESHNESS_HINTS = (
    "aktuell",
    "aktuelle",
    "aktuellen",
    "heute",
    "jetzt",
    "live",
    "neueste",
    "neuester",
    "neuste",
    "current",
    "latest",
    "gerade",
)

_HARD_RESEARCH_HINTS = (
    "tiefenrecherche",
    "tiefen recherche",
    "tiefe recherche",
    "deep research",
    "quellen",
    "fakten",
    "studie",
    "studien",
    "paper",
    "papers",
)

_YOUTUBE_LIGHT_HINTS = (
    "schau mal",
    "was gibt",
    "was geht",
    "gib mir einen überblick",
    "gib mir einen ueberblick",
    "durchsuche youtube",
    "youtube trends",
    "auf youtube so",
    "auf youtube gerade",
    "auf youtube aktuell",
)

_LOCAL_SEARCH_HINTS = (
    "in meiner nähe",
    "in meiner naehe",
    "um mich herum",
    "hier in der nähe",
    "hier in der naehe",
    "in der umgebung",
    "in meiner umgebung",
    "wo bin ich",
    "wo ist hier",
    "google maps",
    "landkarte",
    "nächste ",
    "naechste ",
)

_DOCUMENT_HINTS = (
    "pdf",
    "docx",
    "txt",
    "xlsx",
    "excel",
    "csv",
    "datei",
    "tabelle",
    "bericht",
    "dokument",
    "exportiere",
    "speichere",
)

_DELIVERY_HINTS = (
    "email",
    "e-mail",
    "mail",
    "sende",
    "schicke",
)

_SYSTEM_HINTS = (
    "logs",
    "systemstatus",
    "service status",
    "journalctl",
    "systemctl",
    "restart",
    "neu starten",
    "prozess",
)

_SEMANTIC_BUSINESS_STRATEGY_HINTS = (
    "eroeffnen",
    "eröffnen",
    "gruenden",
    "gründen",
    "unternehmen",
    "business",
    "welches land",
    "welches ist am besten geeignet",
    "am besten geeignet",
    "welches land ist am besten",
)

_SEMANTIC_WEALTH_HINTS = (
    "reich",
    "reich machen",
    "geld verdienen",
    "vermoegen",
    "vermögen",
    "finanziell frei",
)

_SEMANTIC_PERSONAL_PREFERENCE_HINTS = (
    "kaffee",
    "tee",
    "trinken",
    "was meinst du",
)

_SEMANTIC_LOCATION_STATE_UPDATE_HINTS = (
    "standort aktualisiert",
    "handy standort aktualisiert",
    "du musst das registrieren",
    "neu pruefen",
    "neu prüfen",
    "stimmt nicht mehr",
    "aktualisiert",
)

_FOLLOWUP_CONTEXT_FIELD_NAMES = (
    "last_agent",
    "session_id",
    "last_user",
    "last_assistant",
    "session_summary",
    "recent_agents",
    "recent_user_queries",
    "recent_assistant_replies",
    "topic_recall",
    "inherited_topic_recall",
    "semantic_recall",
    "pending_followup_prompt",
)

_CONTEXT_ANCHORED_FOLLOWUP_HINTS = (
    "wie kannst du mir dabei",
    "wie kannst du mir damit",
    "wie kannst du mir helfen",
    "wie kannst du mir behilflich sein",
    "wie wuerdest du mir helfen",
    "wie würdest du mir helfen",
    "womit sollte ich anfangen",
    "was waere der erste schritt",
    "was wäre der erste schritt",
    "und was jetzt",
    "mach weiter damit",
    "weiter damit",
)

_CONTEXT_ANCHORED_REFERENCE_TOKENS = (
    "dabei",
    "damit",
    "darauf",
    "daran",
    "diesem",
    "dieser",
    "diesen",
)

_META_CONSTRAINT_BUDGET_ZERO_HINTS = (
    "budget 0",
    "0 euro",
    "0 eur",
    "0€",
    "kein budget",
    "ohne budget",
    "kein finanzielles polster",
)

_META_CONSTRAINT_MOBILITY_HINTS = (
    "mobil",
    "ortsunabhaengig",
    "ortsunabhängig",
)

_META_CONSTRAINT_SOLO_HINTS = (
    "ohne team",
    "ganz allein",
    "allein",
    "solo",
)

_META_COMPRESSED_FOLLOWUP_HINTS = (
    "budget",
    "stunden",
    "stunde",
    "tage",
    "tag",
    "wochen",
    "woche",
    "monate",
    "monat",
    "ki-consulting",
    "ki consulting",
    "ki-tools",
    "ki tools",
    "selbststaendig",
    "selbständig",
    "beratung",
    "brasilien",
)


def get_agent_capability_map() -> Dict[str, Dict[str, Any]]:
    return {agent: profile.to_dict() for agent, profile in _AGENT_PROFILES.items()}


def meta_agent_chain_key(agent_chain: Iterable[str]) -> str:
    """Stabile Key-Repräsentation einer Agentenkette für Outcome-Lernen."""
    cleaned = [str(agent or "").strip().lower() for agent in agent_chain if str(agent or "").strip()]
    return "__".join(cleaned[:8])


def meta_site_recipe_key(site_kind: str | None, recipe_id: str | None) -> str:
    """Stabile Repräsentation eines Rezepts innerhalb einer Seitenklasse."""
    site = str(site_kind or "").strip().lower()
    recipe = str(recipe_id or "").strip().lower()
    if not site or not recipe:
        return ""
    return f"{site}::{recipe}"


def build_meta_feedback_targets(classification: Dict[str, Any]) -> List[Dict[str, str]]:
    """Leitet konservative Feedback-Ziele aus Meta-Klassifikation ab."""
    targets: List[Dict[str, str]] = []

    task_type = str(classification.get("task_type") or "").strip().lower()
    if task_type:
        targets.append({"namespace": "meta_task_type", "key": task_type})

    recipe_id = str(classification.get("recommended_recipe_id") or "").strip().lower()
    if recipe_id:
        targets.append({"namespace": "meta_recipe", "key": recipe_id})
        site_recipe_key = meta_site_recipe_key(classification.get("site_kind"), recipe_id)
        if site_recipe_key:
            targets.append({"namespace": "meta_site_recipe", "key": site_recipe_key})

    chain_key = meta_agent_chain_key(classification.get("recommended_agent_chain") or [])
    if chain_key:
        targets.append({"namespace": "meta_agent_chain", "key": chain_key})

    unique: Dict[Tuple[str, str], Dict[str, str]] = {}
    for item in targets:
        unique[(item["namespace"], item["key"])] = item
    return list(unique.values())


def _resolve_primary_recipe_id(task_type: str, site_kind: str | None = None) -> str | None:
    if task_type == "simple_live_lookup":
        return "simple_live_lookup"
    if task_type == "simple_live_lookup_document":
        return "simple_live_lookup_document"
    if task_type == "knowledge_research":
        return "knowledge_research"
    if task_type == "youtube_light_research":
        return "youtube_light_research"
    if task_type == "location_local_search":
        return "location_local_search"
    if task_type == "location_route":
        return "location_route"
    if task_type == "youtube_content_extraction":
        return "youtube_content_extraction"
    if task_type == "web_content_extraction":
        return "web_visual_research_summary"
    if task_type == "system_diagnosis":
        return "system_diagnosis"
    if site_kind == "booking" and task_type == "multi_stage_web_task":
        return "booking_search"
    return None


def _build_recipe_payload(recipe_id: str) -> Dict[str, Any] | None:
    if recipe_id not in _ORCHESTRATION_RECIPES:
        return None
    stages = [stage.to_dict() for stage in _ORCHESTRATION_RECIPES[recipe_id]]
    recoveries = [stage.to_dict() for stage in _ORCHESTRATION_RECIPE_RECOVERIES.get(recipe_id, ())]
    return {
        "recipe_id": recipe_id,
        "recipe_stages": stages,
        "recipe_recoveries": recoveries,
        "recommended_agent_chain": list(_ORCHESTRATION_RECIPE_AGENT_CHAINS.get(recipe_id, ())),
    }


def resolve_orchestration_recipe(task_type: str, site_kind: str | None = None) -> Dict[str, Any] | None:
    recipe_id = _resolve_primary_recipe_id(task_type, site_kind)
    if not recipe_id:
        return None
    return _build_recipe_payload(recipe_id)


def resolve_orchestration_alternative_recipes(
    task_type: str,
    site_kind: str | None = None,
) -> List[Dict[str, Any]]:
    primary_recipe = _resolve_primary_recipe_id(task_type, site_kind)
    candidates: List[str] = []
    if task_type == "simple_live_lookup":
        candidates.extend([])
    elif task_type == "simple_live_lookup_document":
        candidates.extend([])
    elif task_type == "youtube_content_extraction":
        candidates.extend(["youtube_search_then_visual", "youtube_research_only"])
    elif task_type == "youtube_light_research":
        candidates.extend([])
    elif task_type == "location_local_search":
        candidates.extend([])
    elif task_type == "location_route":
        candidates.extend([])
    elif task_type == "web_content_extraction":
        candidates.append("web_research_only")
    elif task_type == "system_diagnosis":
        candidates.append("system_shell_probe_first")

    results: List[Dict[str, Any]] = []
    for recipe_id in candidates:
        if recipe_id == primary_recipe:
            continue
        payload = _build_recipe_payload(recipe_id)
        if payload:
            results.append(payload)
    return results


def _normalize_agent_chain(chain: Iterable[str]) -> List[str]:
    cleaned: List[str] = []
    for agent in chain:
        value = str(agent or "").strip().lower()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def build_meta_diagnosis_resolution(
    raw_records: Iterable[Dict[str, Any]] | None,
    *,
    existing_paths: Iterable[str] | None = None,
) -> Dict[str, Any]:
    records = build_diagnosis_records(list(raw_records or []), existing_paths=existing_paths)
    resolution = select_lead_diagnosis(records)
    return {
        "records": [item.to_dict() for item in records],
        **resolution.to_dict(),
    }


def compile_meta_developer_task_payload(
    raw_records: Iterable[Dict[str, Any]] | None,
    *,
    existing_paths: Iterable[str] | None = None,
) -> Dict[str, Any]:
    records = build_diagnosis_records(list(raw_records or []), existing_paths=existing_paths)
    resolution = select_lead_diagnosis(records)
    brief = compile_developer_task_brief(resolution)
    root_cause_payload = build_root_cause_task_payload(resolution)
    return {
        "diagnosis_records": [item.to_dict() for item in records],
        "diagnosis_resolution": resolution.to_dict(),
        "developer_task_brief": brief.to_dict(),
        "root_cause_tasks": root_cause_payload.to_dict(),
    }


def resolve_adaptive_plan_adoption(classification: Dict[str, Any]) -> Dict[str, Any]:
    adaptive_plan = dict(classification.get("adaptive_plan") or {})
    current_recipe_id = str(classification.get("recommended_recipe_id") or "").strip()
    current_chain = _normalize_agent_chain(classification.get("recommended_agent_chain") or [])
    confidence = adaptive_plan.get("confidence")
    confidence_value = float(confidence or 0.0)
    baseline = {
        "state": "fallback_current",
        "reason": "adaptive_plan_unavailable",
        "confidence": round(confidence_value, 2),
        "adopted_recipe_id": current_recipe_id or None,
        "adopted_chain": current_chain,
    }

    if str(adaptive_plan.get("planner_mode") or "").strip().lower() != "advisory":
        return baseline

    task_type = str(classification.get("task_type") or "").strip().lower()
    if task_type not in _ADAPTIVE_PLAN_SAFE_TASK_TYPES:
        return {
            **baseline,
            "state": "rejected",
            "reason": "unsupported_task_type",
        }

    recommended_chain = _normalize_agent_chain(adaptive_plan.get("recommended_chain") or [])
    if not recommended_chain:
        return {
            **baseline,
            "state": "rejected",
            "reason": "missing_recommended_chain",
        }
    if len(recommended_chain) > _ADAPTIVE_PLAN_MAX_CHAIN_LENGTH:
        return {
            **baseline,
            "state": "rejected",
            "reason": "chain_too_long",
            "adopted_chain": recommended_chain,
        }
    if current_chain and recommended_chain[0] != current_chain[0]:
        return {
            **baseline,
            "state": "rejected",
            "reason": "entry_agent_mismatch",
            "adopted_chain": recommended_chain,
        }
    if confidence_value < _ADAPTIVE_PLAN_MIN_CONFIDENCE:
        return {
            **baseline,
            "state": "rejected",
            "reason": "low_confidence",
            "adopted_chain": recommended_chain,
        }

    recipe_hint = str(adaptive_plan.get("recommended_recipe_hint") or "").strip()
    if not recipe_hint:
        return {
            **baseline,
            "state": "rejected",
            "reason": "missing_recipe_hint",
            "adopted_chain": recommended_chain,
        }

    available_payloads: Dict[str, Dict[str, Any]] = {}
    if current_recipe_id:
        current_payload = _build_recipe_payload(current_recipe_id)
        if current_payload:
            available_payloads[current_recipe_id] = current_payload
    for candidate in classification.get("alternative_recipes") or []:
        recipe_id = str(candidate.get("recipe_id") or "").strip()
        if recipe_id:
            available_payloads[recipe_id] = {
                "recipe_id": recipe_id,
                "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
            }

    candidate_payload = available_payloads.get(recipe_hint)
    if not candidate_payload:
        return {
            **baseline,
            "state": "rejected",
            "reason": "recipe_hint_unavailable",
            "adopted_chain": recommended_chain,
        }

    candidate_chain = _normalize_agent_chain(candidate_payload.get("recommended_agent_chain") or [])
    if candidate_chain != recommended_chain:
        return {
            **baseline,
            "state": "rejected",
            "reason": "recipe_chain_mismatch",
            "adopted_recipe_id": recipe_hint,
            "adopted_chain": recommended_chain,
        }

    if recipe_hint == current_recipe_id and candidate_chain == current_chain:
        return {
            **baseline,
            "reason": "current_recipe_already_matches_plan",
            "adopted_chain": current_chain,
        }

    return {
        "state": "adopted",
        "reason": "adaptive_plan_preferred",
        "confidence": round(confidence_value, 2),
        "adopted_recipe_id": recipe_hint,
        "adopted_chain": candidate_chain,
        "recipe_payload": candidate_payload,
    }


def resolve_runtime_goal_gap_stage(
    goal_spec: Dict[str, Any],
    *,
    current_stage_ids: Iterable[str],
    current_stage_agents: Iterable[str],
    previous_stage_status: str,
    previous_stage_agent: str,
    has_result_material: bool,
) -> Dict[str, Any] | None:
    output_mode = str(goal_spec.get("output_mode") or "").strip().lower()
    artifact_format = str(goal_spec.get("artifact_format") or "").strip().lower()
    evidence_level = str(goal_spec.get("evidence_level") or "").strip().lower()
    delivery_required = bool(goal_spec.get("delivery_required"))
    normalized_stage_ids = {str(item or "").strip().lower() for item in current_stage_ids if str(item or "").strip()}
    normalized_stage_agents = {
        str(item or "").strip().lower() for item in current_stage_agents if str(item or "").strip()
    }
    previous_agent = str(previous_stage_agent or "").strip().lower()
    previous_status_clean = str(previous_stage_status or "").strip().lower()

    if previous_status_clean != "success":
        return None
    if not has_result_material:
        return None

    if (
        evidence_level in {"verified", "deep"}
        and previous_agent in _RUNTIME_VERIFICATION_ALLOWED_PREVIOUS_AGENTS
        and not any(agent in normalized_stage_agents for agent in ("research", "system"))
    ):
        return {
            "stage_id": "verification_output",
            "agent": "research",
            "goal": (
                "Validiere das bisherige Ergebnis mit belastbaren Quellen, schliesse erkennbare "
                "Evidenzluecken und liefere ein verifiziertes Ergebnis fuer die naechste Stage."
            ),
            "expected_output": "validated_summary, sources, source_confidence",
            "optional": False,
            "adaptive": True,
            "adaptive_reason": "runtime_goal_gap_verification",
        }

    if output_mode in {"artifact", "table"} or artifact_format:
        if (
            previous_agent in _RUNTIME_GOAL_GAP_ALLOWED_PREVIOUS_AGENTS
            and "document_output" not in normalized_stage_ids
            and "document" not in normalized_stage_agents
        ):
            expected_output = f"{artifact_format} artifact" if artifact_format else "structured table artifact"
            if output_mode == "table" and not artifact_format:
                expected_output = "structured table artifact"
            goal_text = (
                "Erzeuge aus dem bereits vorliegenden Ergebnis die noch fehlende Tabelle oder Datei im angeforderten Format."
            )
            if output_mode == "artifact" and artifact_format:
                goal_text = (
                    "Erzeuge aus dem bereits vorliegenden Ergebnis das noch fehlende Ausgabe-Artefakt "
                    "im angeforderten Format."
                )
            return {
                "stage_id": "document_output",
                "agent": "document",
                "goal": goal_text,
                "expected_output": expected_output,
                "optional": False,
                "adaptive": True,
                "adaptive_reason": "runtime_goal_gap_document",
            }

    if (
        delivery_required
        and previous_agent in _RUNTIME_DELIVERY_ALLOWED_PREVIOUS_AGENTS
        and "communication" not in normalized_stage_agents
        and "communication_output" not in normalized_stage_ids
    ):
        return {
            "stage_id": "communication_output",
            "agent": "communication",
            "goal": (
                "Bereite aus dem vorliegenden Ergebnis die noch fehlende Nachricht oder Auslieferung vor "
                "und nutze vorhandene Artefakte als Anhang, wenn sie bereits erzeugt wurden."
            ),
            "expected_output": "message or delivery_status",
            "optional": False,
            "adaptive": True,
            "adaptive_reason": "runtime_goal_gap_delivery",
        }

    return None


def _has_any(text: str, hints: Iterable[str]) -> bool:
    return any(hint in text for hint in hints)


def _site_kind(text: str) -> str | None:
    if "youtube" in text or "youtu.be" in text:
        return "youtube"
    if (
        "google maps" in text
        or "landkarte" in text
        or _has_any(text, _LOCAL_SEARCH_HINTS)
        or is_location_local_query(text)
        or is_location_route_query(text)
    ):
        return "maps"
    if "booking.com" in text:
        return "booking"
    if "x.com" in text or "twitter" in text:
        return "x"
    if "linkedin" in text:
        return "linkedin"
    if "outlook" in text:
        return "outlook"
    if "github.com/login" in text or "github login" in text:
        return "github_login"
    return None


def _derive_semantic_review_payload(
    text: str,
    *,
    has_simple_live_lookup: bool,
    has_local_search: bool,
) -> Dict[str, Any]:
    hints: List[str] = []

    if _has_any(text, _SEMANTIC_PERSONAL_PREFERENCE_HINTS) and _has_any(text, _SEMANTIC_WEALTH_HINTS):
        hints.append("mixed_personal_preference_and_wealth_strategy")

    if (
        _has_any(text, _SEMANTIC_BUSINESS_STRATEGY_HINTS)
        and any(token in text for token in ("cafe", "cafes", "cafés", "restaurant", "bar"))
        and (has_local_search or has_simple_live_lookup)
    ):
        hints.append("business_strategy_vs_local_lookup")

    if (
        "standort" in text
        and _has_any(text, _SEMANTIC_LOCATION_STATE_UPDATE_HINTS)
    ):
        hints.append("user_reported_location_state_update")

    return {
        "semantic_ambiguity_hints": hints,
        "semantic_review_recommended": bool(hints),
    }


def _apply_semantic_review_override(
    classification: Dict[str, Any],
    semantic_review: Dict[str, Any],
) -> Dict[str, Any]:
    hints = [str(item or "").strip().lower() for item in semantic_review.get("semantic_ambiguity_hints") or [] if str(item or "").strip()]
    if not hints:
        return classification

    override_reason = ""
    if "user_reported_location_state_update" in hints:
        override_reason = "semantic_state_update_review"
    elif "business_strategy_vs_local_lookup" in hints:
        override_reason = "semantic_business_strategy_review"
    elif "mixed_personal_preference_and_wealth_strategy" in hints:
        override_reason = "semantic_multi_intent_dialogue_review"
    if not override_reason:
        return classification

    return {
        **classification,
        "task_type": "single_lane",
        "required_capabilities": ["workflow_orchestration"],
        "recommended_entry_agent": "meta",
        "recommended_agent_chain": ["meta"],
        "needs_structured_handoff": False,
        "reason": override_reason,
        "recommended_recipe_id": None,
        "recipe_stages": [],
        "recipe_recoveries": [],
        "alternative_recipes": [],
    }


def _extract_meta_followup_field(raw: str, field_name: str) -> str:
    source = str(raw or "")
    key = str(field_name or "").strip()
    if not source or not key:
        return ""
    other_fields = [name for name in _FOLLOWUP_CONTEXT_FIELD_NAMES if name != key]
    boundary = "|".join(re.escape(name) for name in other_fields)
    pattern = (
        rf"(?:^|\n|\s){re.escape(key)}:\s*(.*?)"
        rf"(?=(?:\n\s*(?:{boundary})\s*:)|(?:\s(?:{boundary})\s*:)|(?:\n?\s*#\s*CURRENT USER QUERY\b)|$)"
    )
    match = re.search(pattern, source, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    value = str(match.group(1) or "").strip()
    return re.sub(r"\s+", " ", value).strip()


def _clean_meta_state_fragment(text: str, *, max_chars: int = 320) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip().strip("'\"")
    return cleaned[:max_chars]


def _dedupe_meta_state_fragments(items: Iterable[str], *, limit: int = 3, max_chars: int = 320) -> List[str]:
    deduped: List[str] = []
    for item in items:
        cleaned = _clean_meta_state_fragment(item, max_chars=max_chars)
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
        if len(deduped) >= limit:
            break
    return deduped


def _extract_meta_constraints_from_text(raw: str) -> List[str]:
    text = _clean_meta_state_fragment(raw, max_chars=400)
    normalized = text.lower()
    constraints: List[str] = []

    for match in re.finditer(r"\b(\d+)\s*(stunden?|tage?|wochen?|monate?|jahre?)\b", normalized):
        constraints.append(match.group(0))

    if any(hint in normalized for hint in _META_CONSTRAINT_BUDGET_ZERO_HINTS):
        if "kein finanzielles polster" in normalized:
            constraints.append("kein finanzielles polster")
        elif "kein budget" in normalized or "ohne budget" in normalized:
            constraints.append("kein budget")
        else:
            constraints.append("budget 0")

    if any(hint in normalized for hint in _META_CONSTRAINT_MOBILITY_HINTS):
        constraints.append("mobil")

    if any(hint in normalized for hint in _META_CONSTRAINT_SOLO_HINTS):
        constraints.append("ohne team")

    return _dedupe_meta_state_fragments(constraints, limit=6, max_chars=80)


def _extract_meta_interest_fragments(raw: str) -> List[str]:
    source = _clean_meta_state_fragment(raw, max_chars=400)
    if not source:
        return []
    parts = re.split(r"[,;/|]", source)
    filtered: List[str] = []
    for part in parts:
        cleaned = _clean_meta_state_fragment(part, max_chars=120)
        if not cleaned:
            continue
        if _extract_meta_constraints_from_text(cleaned):
            continue
        if re.fullmatch(r"[\d\s€$.,:=-]+", cleaned):
            continue
        filtered.append(cleaned)
    return _dedupe_meta_state_fragments(filtered, limit=3, max_chars=120)


def _looks_like_compressed_meta_followup(text: str) -> bool:
    cleaned = _clean_meta_state_fragment(text, max_chars=240)
    lowered = cleaned.lower()
    if not cleaned:
        return False
    if len(cleaned.split()) > 16:
        return False
    if any(token in lowered for token in ("http://", "https://", "www.", "booking.com", "youtube")):
        return False
    has_compact_separator = any(sep in cleaned for sep in (",", ";", "/", "|"))
    has_constraint = bool(_extract_meta_constraints_from_text(cleaned))
    has_hint = any(hint in lowered for hint in _META_COMPRESSED_FOLLOWUP_HINTS)
    return (has_compact_separator or has_constraint) and has_hint


def extract_effective_meta_query(query: str) -> str:
    """Bewertet bei Follow-up-Kapseln nur die eigentliche Nutzerfrage.

    Andernfalls koennen Recall-/Statuszeilen wie "system stabil" oder
    "health 200 OK" die Task-Klassifikation auf system_diagnosis ziehen.
    """
    raw = str(query or "").strip()
    if not raw:
        return ""

    marker = "# CURRENT USER QUERY"
    if marker.lower() not in raw.lower():
        return raw

    match = re.search(r"^\s*#\s*CURRENT USER QUERY\s*$", raw, flags=re.IGNORECASE | re.MULTILINE)
    if match:
        extracted = raw[match.end() :].strip()
        return extracted or raw

    inline_match = re.search(r"#\s*CURRENT USER QUERY\b", raw, flags=re.IGNORECASE)
    if not inline_match:
        return raw

    extracted = raw[inline_match.end() :].strip()
    extracted = re.sub(r"^[\s:>\-]+", "", extracted).strip()
    extracted = re.sub(r"\s+\Z", "", extracted).strip()
    extracted = re.sub(r"['\"}]+\Z", "", extracted).strip()
    return extracted or raw


def extract_meta_context_anchor(query: str) -> str:
    raw = str(query or "").strip()
    if not raw or "# current user query" not in raw.lower():
        return ""

    parts: List[str] = []
    last_user = _extract_meta_followup_field(raw, "last_user")
    if last_user:
        parts.append(last_user)
    else:
        recent_users = _extract_meta_followup_field(raw, "recent_user_queries")
        if recent_users:
            recent_parts = [item.strip() for item in recent_users.split("||") if item.strip()]
            if recent_parts:
                parts.append(recent_parts[-1])

    pending_followup_prompt = _extract_meta_followup_field(raw, "pending_followup_prompt")
    if pending_followup_prompt:
        parts.append(pending_followup_prompt)
    elif not parts:
        topic_recall = _extract_meta_followup_field(raw, "topic_recall")
        if topic_recall:
            parts.append(topic_recall)

    deduped: List[str] = []
    for item in parts:
        cleaned = _clean_meta_state_fragment(item)
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return " | ".join(deduped[:2])


def extract_meta_dialog_state(query: str) -> Dict[str, Any]:
    raw = str(query or "").strip()
    effective_query = extract_effective_meta_query(raw)
    context_anchor = extract_meta_context_anchor(raw)
    last_user = _extract_meta_followup_field(raw, "last_user")
    pending_followup_prompt = _extract_meta_followup_field(raw, "pending_followup_prompt")
    topic_recall = _extract_meta_followup_field(raw, "topic_recall")
    session_summary = _extract_meta_followup_field(raw, "session_summary")
    recent_users_raw = _extract_meta_followup_field(raw, "recent_user_queries")
    recent_users = [item.strip() for item in recent_users_raw.split("||") if item.strip()]

    compressed_followup_parsed = _looks_like_compressed_meta_followup(effective_query)
    active_topic_candidates: List[str] = []
    open_goal_candidates: List[str] = []

    if context_anchor:
        active_topic_candidates.append(context_anchor)
    elif last_user:
        active_topic_candidates.append(last_user)
    elif recent_users:
        active_topic_candidates.append(recent_users[-1])

    if not active_topic_candidates and compressed_followup_parsed:
        interest_fragments = _extract_meta_interest_fragments(effective_query)
        if interest_fragments:
            active_topic_candidates.extend(interest_fragments[:2])
        else:
            active_topic_candidates.append(effective_query)

    if not active_topic_candidates and topic_recall:
        active_topic_candidates.append(topic_recall)
    if not active_topic_candidates and session_summary:
        active_topic_candidates.append(session_summary)

    if pending_followup_prompt:
        open_goal_candidates.append(pending_followup_prompt)
    if last_user:
        open_goal_candidates.append(last_user)
    elif recent_users:
        open_goal_candidates.append(recent_users[-1])

    if compressed_followup_parsed:
        open_goal_candidates.append(effective_query)

    active_topic_parts = _dedupe_meta_state_fragments(active_topic_candidates, limit=2, max_chars=220)
    active_topic = " | ".join(active_topic_parts)
    open_goal_parts = _dedupe_meta_state_fragments(open_goal_candidates, limit=2, max_chars=220)
    open_goal = " | ".join(open_goal_parts)

    constraints = _dedupe_meta_state_fragments(
        [
            *(_extract_meta_constraints_from_text(effective_query)),
            *(_extract_meta_constraints_from_text(last_user)),
            *(_extract_meta_constraints_from_text(pending_followup_prompt)),
            *(_extract_meta_constraints_from_text(context_anchor)),
        ],
        limit=6,
        max_chars=80,
    )

    next_step = ""
    lowered_query = effective_query.lower()
    if any(
        token in lowered_query
        for token in (
            "wie kannst du mir",
            "wie wuerdest du mir",
            "wie würdest du mir",
            "womit sollte ich anfangen",
            "was waere der erste schritt",
            "was wäre der erste schritt",
            "und was jetzt",
            "naechster schritt",
            "nächster schritt",
        )
    ):
        next_step = _clean_meta_state_fragment(effective_query, max_chars=180)
    elif pending_followup_prompt:
        next_step = _clean_meta_state_fragment(pending_followup_prompt, max_chars=180)

    active_topic_reused = bool(active_topic and (context_anchor or compressed_followup_parsed))
    return {
        "active_topic": active_topic or None,
        "open_goal": open_goal or None,
        "constraints": constraints,
        "next_step": next_step or None,
        "compressed_followup_parsed": compressed_followup_parsed,
        "active_topic_reused": active_topic_reused,
    }


def _should_apply_meta_context_anchor(current_query: str, context_anchor: str) -> bool:
    text = str(current_query or "").strip().lower()
    anchor = str(context_anchor or "").strip()
    if not text or not anchor:
        return False
    if len(text.split()) > 18:
        return False
    if any(hint in text for hint in _CONTEXT_ANCHORED_FOLLOWUP_HINTS):
        return True
    has_reference_token = any(token in text for token in _CONTEXT_ANCHORED_REFERENCE_TOKENS)
    asks_for_guidance = any(
        token in text for token in ("wie ", "womit ", "was ", "kannst du ", "hilf", "helfen", "behilflich")
    )
    if has_reference_token and asks_for_guidance:
        return True
    if text.startswith("und ") and asks_for_guidance:
        return True
    return False


def classify_meta_task(query: str, *, action_count: int = 0) -> Dict[str, Any]:
    effective_query = extract_effective_meta_query(query)
    context_anchor = extract_meta_context_anchor(query)
    dialog_state = extract_meta_dialog_state(query)
    active_topic = str(dialog_state.get("active_topic") or "").strip()
    open_goal = str(dialog_state.get("open_goal") or "").strip()
    dialog_constraints = [str(item or "").strip() for item in dialog_state.get("constraints") or [] if str(item or "").strip()]
    compressed_followup_parsed = bool(dialog_state.get("compressed_followup_parsed"))
    active_topic_reused = bool(dialog_state.get("active_topic_reused"))
    context_anchor_applied = _should_apply_meta_context_anchor(effective_query, context_anchor)
    normalized_source = effective_query
    if context_anchor_applied:
        normalized_source = f"{effective_query}\ncontext_anchor: {context_anchor}"
        if active_topic:
            normalized_source += f"\nactive_topic: {active_topic}"
        if open_goal and open_goal != active_topic:
            normalized_source += f"\nopen_goal: {open_goal}"
        if dialog_constraints:
            normalized_source += f"\nconstraints: {' | '.join(dialog_constraints)}"
    normalized = normalized_source.lower()
    current_normalized = effective_query.lower()
    site_kind = _site_kind(current_normalized)
    has_route_request = site_kind == "maps" and is_location_route_query(current_normalized)
    has_browser = _has_any(current_normalized, _BROWSER_HINTS)
    has_summary_request = ("fasse" in current_normalized and "zusammen" in current_normalized) or "wichtigsten punkte" in current_normalized
    has_extraction = _has_any(current_normalized, _EXTRACTION_HINTS) or has_summary_request
    has_broad_research = _has_any(current_normalized, _BROAD_RESEARCH_HINTS)
    has_strict_research = _has_any(current_normalized, _STRICT_RESEARCH_HINTS)
    has_hard_research = _has_any(current_normalized, _HARD_RESEARCH_HINTS)
    has_youtube_light = site_kind == "youtube" and _has_any(current_normalized, _YOUTUBE_LIGHT_HINTS)
    has_local_search = site_kind == "maps" and (
        _has_any(current_normalized, _LOCAL_SEARCH_HINTS) or is_location_local_query(current_normalized)
    ) and not has_route_request
    has_simple_live_lookup = (
        (
            _has_any(current_normalized, _SIMPLE_LIVE_LOOKUP_DIRECT_HINTS)
            or (
                _has_any(current_normalized, _SIMPLE_LIVE_LOOKUP_FRESHNESS_HINTS)
                and any(
                    marker in current_normalized
                    for marker in (
                        "preis",
                        "preise",
                        "pricing",
                        "kosten",
                        "vergleich",
                        "tabelle",
                        "liste",
                        "news",
                        "nachrichten",
                        "wissenschaft",
                        "wetter",
                        "kino",
                        "film",
                        "filme",
                    )
                )
            )
        )
        and not has_hard_research
        and not has_route_request
        and not has_local_search
        and site_kind not in {"youtube", "booking", "x", "linkedin", "outlook", "github_login"}
    )
    has_document = _has_any(current_normalized, _DOCUMENT_HINTS)
    has_delivery = _has_any(current_normalized, _DELIVERY_HINTS)
    has_system = _has_any(current_normalized, _SYSTEM_HINTS)
    has_login = any(token in current_normalized for token in ("login", "log in", "sign in", "anmelden", "einloggen"))
    has_multistep_browser = has_browser and (
        action_count >= 2
        or has_login
        or any(token in current_normalized for token in ("und dann", "danach", "anschließend", "anschliessend"))
    )

    required_capabilities: List[str] = []
    recommended_chain: List[str] = []
    task_type = "single_lane"
    reason = "single_lane"

    if has_system:
        required_capabilities.extend(["diagnostics"])
        recommended_chain = ["meta", "system"]
        task_type = "system_diagnosis"
        reason = "system_signals"
        if "systemctl" in normalized or "journalctl" in normalized or "sudo" in normalized:
            required_capabilities.append("terminal_execution")
            recommended_chain.append("shell")
    elif has_route_request:
        required_capabilities.extend(["location_context", "route_planning"])
        recommended_chain = ["meta", "executor"]
        task_type = "location_route"
        reason = "device_location_route"
    elif has_local_search:
        required_capabilities.extend(["location_context", "local_maps_search"])
        recommended_chain = ["meta", "executor"]
        task_type = "location_local_search"
        reason = "device_location_local_search"
    elif has_simple_live_lookup and not has_delivery and not has_system:
        required_capabilities.extend(["live_lookup", "light_search"])
        if has_document:
            recommended_chain = ["meta", "executor", "document"]
            task_type = "simple_live_lookup_document"
            reason = "simple_live_lookup_document"
        else:
            recommended_chain = ["meta", "executor"]
            task_type = "simple_live_lookup"
            reason = "simple_live_lookup"
    elif site_kind == "youtube" and has_youtube_light and not has_extraction and not has_multistep_browser:
        required_capabilities.extend(["youtube_search", "lightweight_summary"])
        recommended_chain = ["meta", "executor"]
        task_type = "youtube_light_research"
        reason = "youtube_light_discovery"
    elif site_kind == "youtube" and has_extraction:
        required_capabilities.extend(["browser_navigation", "content_extraction"])
        recommended_chain = ["meta", "visual", "research"]
        task_type = "youtube_content_extraction"
        reason = "youtube_content"
    elif has_browser and has_extraction:
        required_capabilities.extend(["browser_navigation", "content_extraction"])
        recommended_chain = ["meta", "visual", "research"]
        task_type = "web_content_extraction"
        reason = "browser_plus_extraction"
    elif has_browser:
        required_capabilities.append("browser_navigation")
        if site_kind in {"booking", "youtube", "x", "linkedin", "outlook", "github_login"} and has_multistep_browser:
            recommended_chain = ["meta", "visual"]
            task_type = "multi_stage_web_task"
            reason = "interactive_site_profile"
        else:
            recommended_chain = ["visual"]
            task_type = "ui_navigation"
            reason = "browser_navigation"
    elif has_broad_research or has_strict_research:
        required_capabilities.extend(["content_extraction", "source_research"])
        task_type = "knowledge_research"
        if has_broad_research and not has_strict_research:
            recommended_chain = ["meta", "research"]
            reason = "broad_research_orchestration"
        else:
            recommended_chain = ["research"]
            reason = "direct_research_request"
    elif has_extraction:
        required_capabilities.append("content_extraction")
        recommended_chain = ["research"]
        task_type = "knowledge_research"
        reason = "research_only"

    if has_document and "document" not in required_capabilities:
        required_capabilities.append("document_creation")
        if task_type == "simple_live_lookup":
            if not recommended_chain:
                recommended_chain = ["meta", "executor"]
        elif task_type == "simple_live_lookup_document":
            if not recommended_chain:
                recommended_chain = ["meta", "executor", "document"]
        elif recommended_chain:
            if recommended_chain[0] != "meta":
                recommended_chain = ["meta"] + recommended_chain
            if "document" not in recommended_chain:
                recommended_chain.append("document")
        else:
            recommended_chain = ["meta", "document"]
        if task_type == "single_lane":
            task_type = "document_generation"
            reason = "document_request"

    if has_delivery and "message_delivery" not in required_capabilities:
        required_capabilities.append("message_delivery")
        if recommended_chain:
            if recommended_chain[0] != "meta":
                recommended_chain = ["meta"] + recommended_chain
            if "communication" not in recommended_chain:
                recommended_chain.append("communication")
        else:
            recommended_chain = ["meta", "communication"]
        if task_type == "single_lane":
            task_type = "communication_task"
            reason = "delivery_request"

    if not recommended_chain:
        if context_anchor_applied:
            recommended_chain = ["meta"]
            reason = "context_anchored_followup"
        elif compressed_followup_parsed or active_topic_reused:
            recommended_chain = ["meta"]
            reason = "compressed_advisory_followup" if compressed_followup_parsed else "active_topic_followup"
        else:
            recommended_chain = ["meta"] if ("und dann" in normalized or "danach" in normalized) else ["executor"]

    # Reihenfolge deduplizieren, ohne den Ablauf umzubauen.
    deduped_chain: List[str] = []
    for agent in recommended_chain:
        if agent not in deduped_chain:
            deduped_chain.append(agent)

    recipe = resolve_orchestration_recipe(task_type, site_kind)
    alternatives = resolve_orchestration_alternative_recipes(task_type, site_kind)
    semantic_review = _derive_semantic_review_payload(
        current_normalized,
        has_simple_live_lookup=has_simple_live_lookup,
        has_local_search=has_local_search,
    )
    classification = {
        "task_type": task_type,
        "site_kind": site_kind,
        "required_capabilities": sorted(set(required_capabilities)),
        "recommended_entry_agent": deduped_chain[0],
        "recommended_agent_chain": deduped_chain,
        "needs_structured_handoff": len(deduped_chain) > 1,
        "reason": reason,
        "recommended_recipe_id": None if not recipe else recipe["recipe_id"],
        "recipe_stages": [] if not recipe else recipe["recipe_stages"],
        "recipe_recoveries": [] if not recipe else recipe.get("recipe_recoveries", []),
        "alternative_recipes": alternatives,
        "effective_query": effective_query,
        "context_anchor": context_anchor or None,
        "context_anchor_applied": context_anchor_applied,
        "active_topic": active_topic or None,
        "open_goal": open_goal or None,
        "dialog_constraints": dialog_constraints,
        "next_step": dialog_state.get("next_step"),
        "active_topic_reused": active_topic_reused,
        "compressed_followup_parsed": compressed_followup_parsed,
    }
    classification = _apply_semantic_review_override(classification, semantic_review)
    classification.update(semantic_review)
    goal_spec = derive_goal_spec(query, classification)
    capability_graph = build_capability_graph(
        goal_spec,
        get_agent_capability_map(),
        current_chain=deduped_chain,
        required_capabilities=classification["required_capabilities"],
    )
    learned_chain_stats: List[Dict[str, Any]] = []
    try:
        learned_chain_stats = get_adaptive_plan_memory().get_goal_chain_stats(
            str(goal_spec.get("goal_signature") or ""),
        )
    except Exception:
        learned_chain_stats = []
    adaptive_plan = build_adaptive_plan(
        goal_spec,
        capability_graph,
        classification,
        learned_chain_stats=learned_chain_stats,
    )
    return {
        **classification,
        "goal_spec": goal_spec,
        "capability_graph": capability_graph,
        "learned_chain_stats": learned_chain_stats,
        "adaptive_plan": adaptive_plan,
    }

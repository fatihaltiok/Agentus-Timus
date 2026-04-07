"""Meta-Orchestrierungsmodell fuer Faehigkeiten und Task-Klassifikation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from orchestration.adaptive_plan_memory import get_adaptive_plan_memory
from orchestration.adaptive_planner import build_adaptive_plan
from orchestration.capability_graph import build_capability_graph
from orchestration.conversation_state import derive_topic_state_transition
from orchestration.diagnosis_records import (
    build_diagnosis_records,
    compile_developer_task_brief,
    select_lead_diagnosis,
)
from orchestration.goal_spec import derive_goal_spec
from orchestration.root_cause_tasks import build_root_cause_task_payload
from orchestration.turn_understanding import (
    build_turn_understanding_input,
    interpret_turn,
)
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


@dataclass(frozen=True)
class MetaContextSlot:
    slot: str
    priority: int
    content: str
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot": self.slot,
            "priority": self.priority,
            "content": self.content,
            "source": self.source,
        }


@dataclass(frozen=True)
class MetaContextBundle:
    schema_version: int
    current_query: str
    bundle_reason: str
    active_topic: str
    active_goal: str
    open_loop: str
    next_expected_step: str
    turn_type: str
    response_mode: str
    context_slots: Tuple[MetaContextSlot, ...]
    suppressed_context: Tuple[Dict[str, str], ...]
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "current_query": self.current_query,
            "bundle_reason": self.bundle_reason,
            "active_topic": self.active_topic,
            "active_goal": self.active_goal,
            "open_loop": self.open_loop,
            "next_expected_step": self.next_expected_step,
            "turn_type": self.turn_type,
            "response_mode": self.response_mode,
            "context_slots": [slot.to_dict() for slot in self.context_slots],
            "suppressed_context": [dict(item) for item in self.suppressed_context],
            "confidence": self.confidence,
        }


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
                "bleibe auf schnelle verifizierbare Treffer fokussiert und "
                "ziehe Standortkontext nur dann heran, wenn die aktuelle Anfrage klar lokal ist."
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

_CLAIM_CHECK_HINTS = (
    "stimmt das",
    "stimmt es",
    "ist das wahr",
    "ob das stimmt",
    "ob es wahr ist",
    "wirklich",
    "faktencheck",
    "fact check",
    "behauptung",
    "behauptet",
    "das ist falsch",
)

_LEGAL_POLICY_RESEARCH_HINTS = (
    "gesetz",
    "gesetzes",
    "gesetzesentwurf",
    "gesetzesinitiative",
    "gesetzesinitiativen",
    "bestrebung",
    "bestrebungen",
    "bundestag",
    "bundesrat",
    "verordnung",
    "regelung",
    "regelungen",
    "pflicht",
    "genehmigung",
    "genehmigungspflicht",
    "deutschland",
    "ausreise",
    "ausreisen",
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

_YOUTUBE_FACT_CHECK_HINTS = (
    "überprüfe",
    "ueberpruefe",
    "überpruefe",
    "prüfe",
    "pruefe",
    "verifiziere",
    "verify",
    "ob es wahr ist",
    "ist das wahr",
    "ob da etwas wahres dran ist",
    "ob da was wahres dran ist",
    "wahres dran",
    "wahr ist",
    "ob das stimmt",
    "stimmt das",
    "stimmt es",
    "faktencheck",
    "fact check",
    "behauptung",
    "behauptet",
    "gerücht",
    "geruecht",
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

_SEMANTIC_BEHAVIOR_ALIGNMENT_FUTURE_HINTS = (
    "in zukunft",
    "künftig",
    "kuenftig",
    "ab jetzt",
    "von jetzt an",
)

_SEMANTIC_BEHAVIOR_ALIGNMENT_DIRECTIVE_HINTS = (
    "mach das",
    "mach es",
    "greif",
    "nutze",
    "verwende",
    "bevorzuge",
    "berücksichtige",
    "beruecksichtige",
    "achte darauf",
    "stell sicher",
    "sorge dafür",
    "sorge dafuer",
    "merk dir",
    "merke dir",
    "behalte im kopf",
)

_SEMANTIC_DIALOGUE_CLARIFICATION_PATTERNS = (
    r"^\s*(?:(?:ich\s+)?muss|muss\s+ich)\s+(?:mir\s+)?(?:das\s+)?noch\s+(?:überlegen|ueberlegen|uberlegen)\s*[.!]?\s*$",
    r"^\s*(?:ich\s+)?(?:überlege|ueberlege|uberlege)\s+(?:mir\s+)?(?:das\s+)?noch\s*[.!]?\s*$",
    r"^\s*(?:dar(?:ü|ue)ber\s+)?muss\s+ich\s+(?:noch\s+)?nachdenken\s*[.!]?\s*$",
    r"^\s*(?:ich\s+)?denke\s+(?:noch\s+)?dar(?:ü|ue)ber\s+nach\s*[.!]?\s*$",
    r"^\s*(?:ich\s+)?bin\s+mir\s+(?:noch\s+)?nicht\s+sicher\s*[.!]?\s*$",
    r"^\s*(?:das\s+)?weiss\s+ich\s+(?:noch\s+)?nicht\s*[.!]?\s*$",
    r"^\s*(?:das\s+)?weiß\s+ich\s+(?:noch\s+)?nicht\s*[.!]?\s*$",
    r"^\s*wie\s+meinst\s+du\s+das\s*[.!?]?\s*$",
    r"^\s*was\s+meinst\s+du\s+genau\s*[.!?]?\s*$",
    r"^\s*was\s+genau\s+meinst\s+du\s*[.!?]?\s*$",
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
    "conversation_state_active_topic",
    "conversation_state_active_goal",
    "conversation_state_open_loop",
    "conversation_state_next_expected_step",
    "conversation_state_turn_type_hint",
    "conversation_state_preferences",
    "conversation_state_recent_corrections",
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
    "ja mach das",
    "mach das",
    "ok fang an",
    "fang an",
    "ok leg los",
    "leg los",
    "muss ich mir noch überlegen",
    "ich muss noch überlegen",
    "ich überlege noch",
    "ich ueberlege noch",
    "darüber muss ich nachdenken",
    "darueber muss ich nachdenken",
    "ich denke noch darüber nach",
    "ich denke noch darueber nach",
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

_META_CONTEXT_SCHEMA_VERSION = 1


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


def looks_like_meta_clarification_turn(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    if len(normalized.split()) > 14:
        return False
    return any(re.search(pattern, normalized) for pattern in _SEMANTIC_DIALOGUE_CLARIFICATION_PATTERNS)


def _looks_like_meta_behavior_alignment_turn(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not normalized:
        return False
    has_future_hint = any(token in normalized for token in _SEMANTIC_BEHAVIOR_ALIGNMENT_FUTURE_HINTS)
    has_directive_hint = any(token in normalized for token in _SEMANTIC_BEHAVIOR_ALIGNMENT_DIRECTIVE_HINTS)
    if has_future_hint and has_directive_hint:
        return True
    return bool(
        re.search(
            r"^\s*(?:dann\s+)?mach\s*das\b.*\bso\b.*\bdass?\s+du\b",
            normalized,
        )
    )


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


def _has_direct_youtube_url(text: str) -> bool:
    lowered = str(text or "").lower()
    return "youtu.be/" in lowered or "youtube.com/watch" in lowered


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

    if _looks_like_meta_behavior_alignment_turn(text):
        hints.append("behavior_preference_alignment")

    if looks_like_meta_clarification_turn(text):
        hints.append("conversational_clarification_needed")

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
    elif "behavior_preference_alignment" in hints:
        override_reason = "semantic_preference_alignment"
    elif "business_strategy_vs_local_lookup" in hints:
        override_reason = "semantic_business_strategy_review"
    elif "mixed_personal_preference_and_wealth_strategy" in hints:
        override_reason = "semantic_multi_intent_dialogue_review"
    elif "conversational_clarification_needed" in hints:
        override_reason = "semantic_clarification_turn"
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


def _apply_turn_understanding_override(
    classification: Dict[str, Any],
    turn_interpretation: Any,
) -> Dict[str, Any]:
    route_bias = str(getattr(turn_interpretation, "route_bias", "") or "").strip().lower()
    dominant_turn_type = str(getattr(turn_interpretation, "dominant_turn_type", "") or "").strip().lower()
    if route_bias != "meta_only":
        return classification
    if dominant_turn_type not in {
        "approval_response",
        "auth_response",
        "handover_resume",
        "correction",
        "behavior_instruction",
        "preference_update",
        "complaint_about_last_answer",
        "clarification",
    }:
        return classification

    if (
        str(classification.get("task_type") or "").strip().lower() == "single_lane"
        and list(classification.get("recommended_agent_chain") or []) == ["meta"]
        and not bool(classification.get("needs_structured_handoff"))
    ):
        return classification

    return {
        **classification,
        "task_type": "single_lane",
        "required_capabilities": ["workflow_orchestration"],
        "recommended_entry_agent": "meta",
        "recommended_agent_chain": ["meta"],
        "needs_structured_handoff": False,
        "reason": f"turn_understanding:{dominant_turn_type}",
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


def _extract_meta_followup_list(raw: str, field_name: str, *, limit: int = 3) -> List[str]:
    value = _extract_meta_followup_field(raw, field_name)
    if not value:
        return []
    delimiter = "||" if "||" in value else "|"
    items = [item.strip() for item in value.split(delimiter) if item.strip()]
    return _dedupe_meta_state_fragments(items, limit=limit, max_chars=220)


def _extract_meta_followup_conversation_state(raw: str) -> Dict[str, Any]:
    active_topic = _extract_meta_followup_field(raw, "conversation_state_active_topic")
    active_goal = _extract_meta_followup_field(raw, "conversation_state_active_goal")
    open_loop = _extract_meta_followup_field(raw, "conversation_state_open_loop")
    next_expected_step = _extract_meta_followup_field(raw, "conversation_state_next_expected_step")
    turn_type_hint = _extract_meta_followup_field(raw, "conversation_state_turn_type_hint")
    preferences = _extract_meta_followup_list(raw, "conversation_state_preferences", limit=4)
    recent_corrections = _extract_meta_followup_list(raw, "conversation_state_recent_corrections", limit=4)
    payload = {
        "active_topic": _clean_meta_state_fragment(active_topic, max_chars=220),
        "active_goal": _clean_meta_state_fragment(active_goal, max_chars=220),
        "open_loop": _clean_meta_state_fragment(open_loop, max_chars=220),
        "next_expected_step": _clean_meta_state_fragment(next_expected_step, max_chars=220),
        "turn_type_hint": _clean_meta_state_fragment(turn_type_hint, max_chars=64).lower(),
        "preferences": preferences,
        "recent_corrections": recent_corrections,
    }
    return {key: value for key, value in payload.items() if value}


def _meta_context_slot_text(label: str, parts: Iterable[str]) -> str:
    cleaned = [str(item or "").strip() for item in parts if str(item or "").strip()]
    if not cleaned:
        return ""
    return f"{label}: " + " | ".join(cleaned[:4])


def _append_meta_context_slot(
    slots: List[MetaContextSlot],
    *,
    slot: str,
    priority: int,
    content: str,
    source: str,
) -> None:
    cleaned = _clean_meta_state_fragment(content, max_chars=320)
    if not cleaned:
        return
    slots.append(
        MetaContextSlot(
            slot=slot,
            priority=priority,
            content=cleaned,
            source=_clean_meta_state_fragment(source, max_chars=64),
        )
    )


def _tokenize_meta_context_terms(text: str) -> List[str]:
    normalized = str(text or "").lower()
    tokens = re.findall(r"[a-zA-Z0-9äöüÄÖÜß_-]+", normalized)
    cleaned: List[str] = []
    for token in tokens:
        stripped = token.strip("_-")
        if len(stripped) < 3:
            continue
        cleaned.append(stripped)
    return cleaned


def _meta_context_overlap_size(left: str, right: str) -> int:
    left_terms = set(_tokenize_meta_context_terms(left))
    right_terms = set(_tokenize_meta_context_terms(right))
    if not left_terms or not right_terms:
        return 0
    return len(left_terms.intersection(right_terms))


def _normalize_meta_context_fragments(
    items: Iterable[Any] | None,
    *,
    limit: int = 2,
    max_chars: int = 220,
) -> List[str]:
    normalized: List[str] = []
    for item in items or ():
        rendered = ""
        if isinstance(item, Mapping):
            text = _clean_meta_state_fragment(
                item.get("text") or item.get("content") or item.get("value"),
                max_chars=max_chars,
            )
            if not text:
                continue
            role = _clean_meta_state_fragment(item.get("role"), max_chars=32).lower()
            agent = _clean_meta_state_fragment(item.get("agent"), max_chars=32).lower()
            label = ""
            if role and agent:
                label = f"{role}:{agent}"
            elif role:
                label = role
            elif agent:
                label = agent
            rendered = f"{label} => {text}" if label else text
        else:
            rendered = _clean_meta_state_fragment(item, max_chars=max_chars)
        if not rendered or rendered in normalized:
            continue
        normalized.append(rendered)
        if len(normalized) >= limit:
            break
    return normalized


def _select_relevant_topic_memory(
    *,
    raw_query: str,
    effective_query: str,
    dialog_state: Mapping[str, Any],
    conversation_state: Mapping[str, Any],
    provided_hits: Iterable[Any] | None,
) -> List[str]:
    if provided_hits is not None:
        return _normalize_meta_context_fragments(provided_hits, limit=2)

    try:
        from memory.memory_system import memory_manager
    except Exception:
        return []

    focus_parts = [
        effective_query,
        str(conversation_state.get("active_topic") or ""),
        str(conversation_state.get("active_goal") or ""),
        str(conversation_state.get("open_loop") or ""),
        str(dialog_state.get("active_topic") or ""),
        str(dialog_state.get("open_goal") or ""),
        _extract_meta_followup_field(raw_query, "topic_recall"),
    ]
    recall_query = " | ".join(
        item for item in _dedupe_meta_state_fragments(focus_parts, limit=5, max_chars=160) if item
    ).strip()
    if not recall_query:
        recall_query = effective_query

    focus_terms = set(_tokenize_meta_context_terms(recall_query))
    if not focus_terms:
        focus_terms = set(_tokenize_meta_context_terms(effective_query))

    try:
        related = memory_manager.find_related_memories(recall_query, n_results=6)
    except Exception:
        return []

    scored: List[Tuple[int, float, str]] = []
    for item in related:
        if not isinstance(item, Mapping):
            continue
        category = _clean_meta_state_fragment(item.get("category"), max_chars=64).lower()
        if category in {"self_model", "user_profile"}:
            continue
        content = _clean_meta_state_fragment(item.get("content"), max_chars=220)
        if not content:
            continue
        rendered = f"{category or 'memory'} => {content}"
        overlap = len(focus_terms.intersection(_tokenize_meta_context_terms(content)))
        relevance = float(item.get("relevance") or 0.0)
        if overlap <= 0 and relevance < 0.45:
            continue
        scored.append((overlap, relevance, rendered))

    scored.sort(key=lambda row: (-row[0], -row[1], len(row[2])))
    return _normalize_meta_context_fragments((row[2] for row in scored), limit=2)


def _select_relevant_preference_memory(
    *,
    effective_query: str,
    conversation_state: Mapping[str, Any],
    turn_type: str,
    provided_hits: Iterable[Any] | None,
) -> List[str]:
    if provided_hits is not None:
        return _normalize_meta_context_fragments(provided_hits, limit=2)

    try:
        from memory.memory_system import memory_manager
    except Exception:
        return []

    focus_parts = [
        effective_query,
        str(conversation_state.get("active_topic") or ""),
        str(conversation_state.get("active_goal") or ""),
        str(conversation_state.get("open_loop") or ""),
    ]
    focus_text = " | ".join(item for item in _dedupe_meta_state_fragments(focus_parts, limit=4, max_chars=120) if item)
    focus_terms = set(_tokenize_meta_context_terms(focus_text))
    normalized_query = focus_text.lower()
    preference_mode = turn_type in {"behavior_instruction", "preference_update", "complaint_about_last_answer"}

    candidates: List[str] = []
    try:
        for hook in memory_manager.get_behavior_hooks()[:6]:
            candidates.append(f"hook => {hook}")
    except Exception:
        pass
    try:
        self_model = str(memory_manager.get_self_model_prompt() or "").strip()
        for line in self_model.splitlines():
            cleaned = _clean_meta_state_fragment(line, max_chars=200)
            if cleaned:
                candidates.append(f"self_model => {cleaned}")
    except Exception:
        pass
    try:
        profile_items = memory_manager.persistent.get_memory_items("user_profile")
        for item in profile_items[:10]:
            key = _clean_meta_state_fragment(getattr(item, "key", ""), max_chars=48).lower()
            value = _clean_meta_state_fragment(getattr(item, "value", ""), max_chars=180)
            if not value:
                continue
            if key in {"preference", "goal"} or "preference" in key or "goal" in key:
                candidates.append(f"user_profile:{key or 'memory'} => {value}")
    except Exception:
        pass

    scored: List[Tuple[int, float, str]] = []
    for candidate in candidates:
        cleaned = _clean_meta_state_fragment(candidate, max_chars=220)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        overlap = len(focus_terms.intersection(_tokenize_meta_context_terms(cleaned)))
        bonus = 0.0
        if any(token in normalized_query for token in ("news", "nachrichten", "weltlage", "agentur", "quelle", "beleg", "aktuell")):
            if any(token in lowered for token in ("quelle", "beleg", "verifiz", "agentur", "halluz", "fakten")):
                bonus += 1.5
        if any(token in normalized_query for token in ("kurz", "knapp", "struktur", "json", "deutsch")):
            if any(token in lowered for token in ("kurz", "präzise", "praezise", "struktur", "json", "deutsch")):
                bonus += 1.0
        if preference_mode and any(token in lowered for token in ("hook =>", "self_model =>", "user_profile:preference")):
            bonus += 0.5
        if overlap <= 0 and bonus <= 0:
            continue
        scored.append((overlap, bonus, cleaned))

    scored.sort(key=lambda row: (-row[0], -row[1], len(row[2])))
    return _normalize_meta_context_fragments((row[2] for row in scored), limit=2)


def _select_relevant_recent_user_turns(
    raw_query: str,
    *,
    effective_query: str,
    recent_user_turns: Iterable[str] | None = None,
) -> List[str]:
    candidates = list(recent_user_turns or [])
    if not candidates:
        candidates = _extract_meta_followup_list(raw_query, "recent_user_queries", limit=3)
    last_user = _extract_meta_followup_field(raw_query, "last_user")
    if last_user:
        candidates.append(last_user)
    effective_clean = _clean_meta_state_fragment(effective_query, max_chars=220).lower()
    selected: List[str] = []
    for item in reversed(candidates):
        cleaned = _clean_meta_state_fragment(item, max_chars=220)
        if not cleaned:
            continue
        if cleaned.lower() == effective_clean:
            continue
        if cleaned in selected:
            continue
        selected.append(cleaned)
        if len(selected) >= 3:
            break
    return selected


def _select_relevant_recent_assistant_turns(
    raw_query: str,
    *,
    recent_assistant_turns: Iterable[str] | None = None,
) -> List[str]:
    candidates = list(recent_assistant_turns or [])
    if not candidates:
        candidates = _extract_meta_followup_list(raw_query, "recent_assistant_replies", limit=3)
    last_assistant = _extract_meta_followup_field(raw_query, "last_assistant")
    if last_assistant:
        candidates.append(last_assistant)
    selected: List[str] = []
    for item in reversed(candidates):
        cleaned = _clean_meta_state_fragment(item, max_chars=220)
        if not cleaned or cleaned in selected:
            continue
        selected.append(cleaned)
        if len(selected) >= 3:
            break
    return selected


def _select_open_loop_payload(
    *,
    conversation_state: Mapping[str, Any],
    dialog_state: Mapping[str, Any],
    effective_query: str,
    turn_type: str,
    response_mode: str,
) -> str:
    open_loop = _clean_meta_state_fragment(
        conversation_state.get("open_loop") or dialog_state.get("open_goal"),
        max_chars=220,
    )
    next_step = _clean_meta_state_fragment(
        conversation_state.get("next_expected_step") or dialog_state.get("next_step"),
        max_chars=220,
    )
    if turn_type in {"followup", "handover_resume", "approval_response", "auth_response", "clarification"}:
        return next_step or open_loop
    if response_mode in {"resume_open_loop", "acknowledge_and_store"}:
        return next_step or open_loop
    selected = open_loop if len(open_loop.split()) <= 12 else next_step
    if turn_type == "new_task" and selected and _meta_context_overlap_size(selected, effective_query) == 0:
        return ""
    return selected


def _suppress_low_priority_context(
    *,
    current_query: str,
    recent_user_turns: Iterable[str],
    recent_assistant_turns: Iterable[str],
    topic_memory: Iterable[str] = (),
    preference_memory: Iterable[str] = (),
) -> List[Dict[str, str]]:
    suppressed: List[Dict[str, str]] = []
    user_turns = [str(item or "").strip() for item in recent_user_turns if str(item or "").strip()]
    assistant_turns = [str(item or "").strip() for item in recent_assistant_turns if str(item or "").strip()]
    topic_items = [str(item or "").strip() for item in topic_memory if str(item or "").strip()]
    preference_items = [str(item or "").strip() for item in preference_memory if str(item or "").strip()]
    normalized_query = str(current_query or "").strip().lower()
    if user_turns and assistant_turns:
        suppressed.append(
            {
                "source": "assistant_reply",
                "reason": "lower_priority_than_recent_user_turn",
                "content_preview": assistant_turns[0][:140],
            }
        )
    if not is_location_local_query(normalized_query) and not is_location_route_query(normalized_query):
        for item in assistant_turns[:2]:
            lowered = item.lower()
            if any(token in lowered for token in ("maps", "standort", "route", "naehe", "nähe", "offenbach")):
                suppressed.append(
                    {
                        "source": "assistant_reply",
                        "reason": "location_context_without_current_evidence",
                        "content_preview": item[:140],
                    }
                )
                break
    if assistant_turns:
        reference_topics = [current_query, *user_turns[:2], *topic_items[:1]]
        for item in assistant_turns[:2]:
            best_overlap = max((_meta_context_overlap_size(item, ref) for ref in reference_topics if ref), default=0)
            if best_overlap > 0:
                continue
            suppressed.append(
                {
                    "source": "assistant_reply",
                    "reason": "topic_mismatch_with_current_query",
                    "content_preview": item[:140],
                }
            )
            break
    if preference_items and not any(
        token in normalized_query
        for token in (
            "bevorzug",
            "präferenz",
            "praeferenz",
            "merk dir",
            "merke dir",
            "in zukunft",
            "kuenftig",
            "künftig",
            "antwort",
            "news",
            "nachrichten",
            "weltlage",
            "quelle",
            "quellen",
            "fakten",
            "beleg",
        )
    ):
        for item in preference_items[:2]:
            if _meta_context_overlap_size(item, current_query) > 0:
                continue
            suppressed.append(
                {
                    "source": "preference_memory",
                    "reason": "preference_not_relevant_for_current_topic",
                    "content_preview": item[:140],
                }
            )
            break
    unique: List[Dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in suppressed:
        key = (
            str(item.get("source") or ""),
            str(item.get("reason") or ""),
            str(item.get("content_preview") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:4]


def build_meta_context_bundle(
    *,
    raw_query: str,
    effective_query: str,
    dialog_state: Mapping[str, Any] | None = None,
    conversation_state: Mapping[str, Any] | None = None,
    turn_understanding: Mapping[str, Any] | None = None,
    session_summary: str = "",
    recent_user_turns: Iterable[str] | None = None,
    recent_assistant_turns: Iterable[str] | None = None,
    topic_memory_hits: Iterable[Any] | None = None,
    preference_memory_hits: Iterable[Any] | None = None,
    semantic_recall_hits: Iterable[Any] | None = None,
) -> MetaContextBundle:
    raw = str(raw_query or "")
    dialog = dict(dialog_state or {})
    explicit_state = dict(conversation_state or {})
    followup_state = _extract_meta_followup_conversation_state(raw)
    merged_state = {
        "active_topic": explicit_state.get("active_topic")
        or followup_state.get("active_topic")
        or dialog.get("active_topic")
        or "",
        "active_goal": explicit_state.get("active_goal")
        or followup_state.get("active_goal")
        or dialog.get("open_goal")
        or "",
        "open_loop": explicit_state.get("open_loop")
        or followup_state.get("open_loop")
        or "",
        "next_expected_step": explicit_state.get("next_expected_step")
        or followup_state.get("next_expected_step")
        or dialog.get("next_step")
        or "",
        "turn_type_hint": explicit_state.get("turn_type_hint")
        or followup_state.get("turn_type_hint")
        or "",
        "preferences": explicit_state.get("preferences")
        or followup_state.get("preferences")
        or (),
        "recent_corrections": explicit_state.get("recent_corrections")
        or followup_state.get("recent_corrections")
        or (),
        "topic_confidence": explicit_state.get("topic_confidence") or 0.0,
    }
    turn = dict(turn_understanding or {})
    turn_type = str(turn.get("dominant_turn_type") or "").strip().lower() or str(
        merged_state.get("turn_type_hint") or ""
    ).strip().lower()
    response_mode = str(turn.get("response_mode") or "").strip().lower()
    recent_users = _select_relevant_recent_user_turns(
        raw,
        effective_query=effective_query,
        recent_user_turns=recent_user_turns,
    )
    recent_assistant = _select_relevant_recent_assistant_turns(
        raw,
        recent_assistant_turns=recent_assistant_turns,
    )
    semantic_recall = _normalize_meta_context_fragments(semantic_recall_hits, limit=2)
    topic_memory = _select_relevant_topic_memory(
        raw_query=raw,
        effective_query=effective_query,
        dialog_state=dialog,
        conversation_state=merged_state,
        provided_hits=topic_memory_hits,
    )
    preference_memory = _select_relevant_preference_memory(
        effective_query=effective_query,
        conversation_state=merged_state,
        turn_type=turn_type,
        provided_hits=preference_memory_hits,
    )
    selected_open_loop = _select_open_loop_payload(
        conversation_state=merged_state,
        dialog_state=dialog,
        effective_query=effective_query,
        turn_type=turn_type,
        response_mode=response_mode,
    )
    slots: List[MetaContextSlot] = []
    _append_meta_context_slot(
        slots,
        slot="current_query",
        priority=1,
        content=_clean_meta_state_fragment(effective_query, max_chars=240),
        source="current_user_query",
    )
    state_slot = _meta_context_slot_text(
        "conversation_state",
        [
            merged_state.get("active_topic"),
            merged_state.get("active_goal"),
            merged_state.get("turn_type_hint"),
            *list(merged_state.get("preferences") or ())[:2],
            *list(merged_state.get("recent_corrections") or ())[:2],
        ],
    )
    _append_meta_context_slot(
        slots,
        slot="conversation_state",
        priority=2,
        content=state_slot,
        source="conversation_state",
    )
    _append_meta_context_slot(
        slots,
        slot="open_loop",
        priority=3,
        content=_meta_context_slot_text(
            "open_loop",
            [selected_open_loop, merged_state.get("next_expected_step")],
        ),
        source="open_loop",
    )
    for idx, item in enumerate(recent_users[:2], start=4):
        _append_meta_context_slot(
            slots,
            slot="recent_user_turn",
            priority=idx,
            content=item,
            source="recent_user_queries",
        )
    for idx, item in enumerate(topic_memory, start=6):
        _append_meta_context_slot(
            slots,
            slot="topic_memory",
            priority=idx,
            content=item,
            source="topic_memory",
        )
    for idx, item in enumerate(preference_memory, start=8):
        _append_meta_context_slot(
            slots,
            slot="preference_memory",
            priority=idx,
            content=item,
            source="preference_memory",
        )
    if not recent_users and recent_assistant:
        _append_meta_context_slot(
            slots,
            slot="assistant_fallback_context",
            priority=max(len(slots) + 1, 4),
            content=recent_assistant[0],
            source="recent_assistant_replies",
        )
    if session_summary and len(slots) < 4:
        _append_meta_context_slot(
            slots,
            slot="session_summary",
            priority=max(len(slots) + 1, 4),
            content=session_summary,
            source="session_summary",
        )
    if semantic_recall and len(slots) < 5:
        _append_meta_context_slot(
            slots,
            slot="semantic_recall",
            priority=max(len(slots) + 1, 5),
            content=semantic_recall[0],
            source="semantic_recall",
        )
    suppressed_context = _suppress_low_priority_context(
        current_query=effective_query,
        recent_user_turns=recent_users,
        recent_assistant_turns=recent_assistant,
        topic_memory=topic_memory,
        preference_memory=preference_memory,
    )
    confidence = max(
        float(turn.get("confidence") or 0.0),
        float(merged_state.get("topic_confidence") or 0.0),
    )
    return MetaContextBundle(
        schema_version=_META_CONTEXT_SCHEMA_VERSION,
        current_query=_clean_meta_state_fragment(effective_query, max_chars=240),
        bundle_reason="meta_context_rehydration",
        active_topic=_clean_meta_state_fragment(merged_state.get("active_topic"), max_chars=220),
        active_goal=_clean_meta_state_fragment(merged_state.get("active_goal"), max_chars=220),
        open_loop=_clean_meta_state_fragment(selected_open_loop, max_chars=220),
        next_expected_step=_clean_meta_state_fragment(merged_state.get("next_expected_step"), max_chars=220),
        turn_type=turn_type,
        response_mode=response_mode,
        context_slots=tuple(sorted(slots, key=lambda item: item.priority)),
        suppressed_context=tuple(suppressed_context),
        confidence=round(max(0.0, min(confidence or 0.0, 1.0)), 2),
    )


def render_meta_context_bundle(bundle: MetaContextBundle | Mapping[str, Any] | None) -> str:
    payload = bundle.to_dict() if isinstance(bundle, MetaContextBundle) else dict(bundle or {})
    slots = payload.get("context_slots") or []
    lines = ["# META CONTEXT BUNDLE"]
    lines.append(f"current_query: {str(payload.get('current_query') or '').strip()}")
    if payload.get("turn_type"):
        lines.append(f"turn_type: {payload['turn_type']}")
    if payload.get("response_mode"):
        lines.append(f"response_mode: {payload['response_mode']}")
    if payload.get("active_topic"):
        lines.append(f"active_topic: {payload['active_topic']}")
    if payload.get("active_goal"):
        lines.append(f"active_goal: {payload['active_goal']}")
    if payload.get("open_loop"):
        lines.append(f"open_loop: {payload['open_loop']}")
    if payload.get("next_expected_step"):
        lines.append(f"next_expected_step: {payload['next_expected_step']}")
    if slots:
        lines.append("context_slots:")
        for item in slots[:6]:
            if not isinstance(item, Mapping):
                continue
            lines.append(
                f"- {str(item.get('priority') or '')}:{str(item.get('slot') or '').strip()} => "
                f"{str(item.get('content') or '').strip()}"
            )
    return "\n".join(lines)


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


def classify_meta_task(
    query: str,
    *,
    action_count: int = 0,
    conversation_state: Mapping[str, Any] | None = None,
    recent_user_turns: Iterable[str] | None = None,
    recent_assistant_turns: Iterable[str] | None = None,
    session_summary: str = "",
    topic_memory_hits: Iterable[Any] | None = None,
    preference_memory_hits: Iterable[Any] | None = None,
    semantic_recall_hits: Iterable[Any] | None = None,
) -> Dict[str, Any]:
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
    has_claim_check = _has_any(current_normalized, _CLAIM_CHECK_HINTS)
    has_legal_policy_research = _has_any(current_normalized, _LEGAL_POLICY_RESEARCH_HINTS)
    if has_claim_check and has_legal_policy_research:
        has_strict_research = True
    has_hard_research = _has_any(current_normalized, _HARD_RESEARCH_HINTS)
    has_youtube_light = site_kind == "youtube" and _has_any(current_normalized, _YOUTUBE_LIGHT_HINTS)
    has_direct_youtube_url = site_kind == "youtube" and _has_direct_youtube_url(current_normalized)
    has_youtube_fact_check = site_kind == "youtube" and (
        _has_any(current_normalized, _YOUTUBE_FACT_CHECK_HINTS)
        or (has_direct_youtube_url and has_strict_research)
    )
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
    semantic_review = _derive_semantic_review_payload(
        current_normalized,
        has_simple_live_lookup=has_simple_live_lookup,
        has_local_search=has_local_search,
    )
    turn_input = build_turn_understanding_input(
        raw_query=query,
        effective_query=effective_query,
        dialog_state=dialog_state,
        semantic_review_hints=semantic_review.get("semantic_ambiguity_hints") or [],
        conversation_state=conversation_state,
        context_anchor_applied=context_anchor_applied,
    )
    turn_interpretation = interpret_turn(turn_input)
    meta_context_bundle = build_meta_context_bundle(
        raw_query=query,
        effective_query=effective_query,
        dialog_state=dialog_state,
        conversation_state=conversation_state,
        turn_understanding=turn_interpretation.to_dict(),
        session_summary=session_summary,
        recent_user_turns=recent_user_turns,
        recent_assistant_turns=recent_assistant_turns,
        topic_memory_hits=topic_memory_hits,
        preference_memory_hits=preference_memory_hits,
        semantic_recall_hits=semantic_recall_hits,
    )
    active_topic = meta_context_bundle.active_topic or active_topic
    open_goal = meta_context_bundle.active_goal or open_goal or meta_context_bundle.open_loop
    next_step = meta_context_bundle.next_expected_step or dialog_state.get("next_step")
    topic_transition = derive_topic_state_transition(
        conversation_state,
        session_id=str((conversation_state or {}).get("session_id") or "default"),
        dominant_turn_type=turn_interpretation.dominant_turn_type,
        response_mode=turn_interpretation.response_mode,
        state_effects=turn_interpretation.state_effects.to_dict(),
        effective_query=effective_query,
        active_topic=active_topic,
        active_goal=open_goal,
        next_step=str(next_step or ""),
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
    elif site_kind == "youtube" and has_direct_youtube_url and has_youtube_fact_check:
        required_capabilities.extend(["content_extraction", "source_research", "fact_verification"])
        recommended_chain = ["meta", "research"]
        task_type = "youtube_content_extraction"
        reason = "youtube_fact_check"
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

    prefer_youtube_research_only = (
        task_type == "youtube_content_extraction"
        and has_direct_youtube_url
        and has_youtube_fact_check
        and not has_browser
    )
    recipe = resolve_orchestration_recipe(task_type, site_kind)
    alternatives = resolve_orchestration_alternative_recipes(task_type, site_kind)
    if prefer_youtube_research_only:
        preferred_recipe = _build_recipe_payload("youtube_research_only")
        if preferred_recipe:
            recipe = preferred_recipe
            alternatives = []
            for candidate_id in ("youtube_content_extraction", "youtube_search_then_visual"):
                payload = _build_recipe_payload(candidate_id)
                if payload and payload["recipe_id"] != preferred_recipe["recipe_id"]:
                    alternatives.append(payload)
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
        "next_step": next_step,
        "active_topic_reused": active_topic_reused,
        "compressed_followup_parsed": compressed_followup_parsed,
        "dominant_turn_type": turn_interpretation.dominant_turn_type,
        "turn_signals": list(turn_interpretation.turn_signals),
        "response_mode": turn_interpretation.response_mode,
        "state_effects": turn_interpretation.state_effects.to_dict(),
        "turn_understanding": turn_interpretation.to_dict(),
        "topic_shift_detected": topic_transition.topic_shift_detected,
        "topic_state_transition": topic_transition.to_dict(),
        "meta_context_bundle": meta_context_bundle.to_dict(),
        "meta_context_slot_types": [slot.slot for slot in meta_context_bundle.context_slots],
        "meta_context_suppressed_count": len(meta_context_bundle.suppressed_context),
    }
    classification = _apply_semantic_review_override(classification, semantic_review)
    classification = _apply_turn_understanding_override(classification, turn_interpretation)
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

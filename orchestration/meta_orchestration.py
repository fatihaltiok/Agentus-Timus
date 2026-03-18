"""Meta-Orchestrierungsmodell fuer Faehigkeiten und Task-Klassifikation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Tuple

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
        capabilities=("quick_tool_execution", "light_search", "youtube_discovery", "short_summaries"),
        strengths=("casual_requests", "fast_search_flows", "lightweight_followups"),
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
    "recherchiere",
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
    if task_type == "youtube_content_extraction":
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
    if not match:
        return raw

    extracted = raw[match.end() :].strip()
    return extracted or raw


def classify_meta_task(query: str, *, action_count: int = 0) -> Dict[str, Any]:
    normalized = extract_effective_meta_query(query).lower()
    site_kind = _site_kind(normalized)
    has_route_request = site_kind == "maps" and is_location_route_query(normalized)
    has_browser = _has_any(normalized, _BROWSER_HINTS)
    has_summary_request = ("fasse" in normalized and "zusammen" in normalized) or "wichtigsten punkte" in normalized
    has_extraction = _has_any(normalized, _EXTRACTION_HINTS) or has_summary_request
    has_youtube_light = site_kind == "youtube" and _has_any(normalized, _YOUTUBE_LIGHT_HINTS)
    has_local_search = site_kind == "maps" and (
        _has_any(normalized, _LOCAL_SEARCH_HINTS) or is_location_local_query(normalized)
    ) and not has_route_request
    has_document = _has_any(normalized, _DOCUMENT_HINTS)
    has_delivery = _has_any(normalized, _DELIVERY_HINTS)
    has_system = _has_any(normalized, _SYSTEM_HINTS)
    has_login = any(token in normalized for token in ("login", "log in", "sign in", "anmelden", "einloggen"))
    has_multistep_browser = has_browser and (
        action_count >= 2
        or has_login
        or any(token in normalized for token in ("und dann", "danach", "anschließend", "anschliessend"))
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
    elif has_extraction:
        required_capabilities.append("content_extraction")
        recommended_chain = ["research"]
        task_type = "knowledge_research"
        reason = "research_only"

    if has_document and "document" not in required_capabilities:
        required_capabilities.append("document_creation")
        if recommended_chain:
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
        recommended_chain = ["meta"] if ("und dann" in normalized or "danach" in normalized) else ["executor"]

    # Reihenfolge deduplizieren, ohne den Ablauf umzubauen.
    deduped_chain: List[str] = []
    for agent in recommended_chain:
        if agent not in deduped_chain:
            deduped_chain.append(agent)

    recipe = resolve_orchestration_recipe(task_type, site_kind)
    alternatives = resolve_orchestration_alternative_recipes(task_type, site_kind)
    return {
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
    }

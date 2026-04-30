"""Meta-Orchestrierungsmodell fuer Faehigkeiten und Task-Klassifikation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from orchestration.adaptive_plan_memory import get_adaptive_plan_memory
from orchestration.adaptive_planner import build_adaptive_plan
from orchestration.capability_graph import build_capability_graph
from orchestration.meta_clarity_contract import (
    apply_meta_clarity_to_bundle,
    build_meta_clarity_contract,
    parse_meta_clarity_contract,
)
from orchestration.general_decision_kernel import build_general_decision_kernel
from orchestration.general_decision_kernel import resolve_low_confidence_controller
from orchestration.meta_context_authority import build_meta_context_authority
from orchestration.meta_context_authority import classify_meta_context_slot, summarize_meta_context_classes
from orchestration.meta_interaction_mode import MetaInteractionMode, build_meta_interaction_mode
from orchestration.conversation_state import (
    derive_topic_state_transition,
    is_generic_followup_prompt,
    normalize_pending_followup_prompt,
)
from orchestration.diagnosis_records import (
    build_diagnosis_records,
    compile_developer_task_brief,
    select_lead_diagnosis,
)
from orchestration.direct_response_intent import looks_like_direct_response_instruction
from orchestration.meta_plan_compiler import build_meta_execution_plan
from orchestration.preference_instruction_memory import select_stored_preference_memory_with_summary
from orchestration.meta_request_frame import (
    apply_meta_request_frame_context_admission,
    apply_meta_request_frame_routing,
    build_meta_request_frame,
    infer_meta_task_domain_hint,
)
from orchestration.meta_response_policy import MetaPolicyDecision, build_meta_policy_input, resolve_meta_response_policy
from orchestration.specialist_context import build_specialist_context_payload
from orchestration.task_decomposition_contract import build_task_decomposition
from orchestration.topic_state_history import parse_historical_topic_recall_hint, select_historical_topic_memory
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
    evidence_class: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot": self.slot,
            "priority": self.priority,
            "content": self.content,
            "source": self.source,
            "evidence_class": self.evidence_class or classify_meta_context_slot(self.slot),
        }


@dataclass(frozen=True)
class MetaContextBundle:
    schema_version: int
    current_query: str
    bundle_reason: str
    active_topic: str
    active_goal: str
    active_domain: str
    open_loop: str
    next_expected_step: str
    turn_type: str
    response_mode: str
    context_slots: Tuple[MetaContextSlot, ...]
    suppressed_context: Tuple[Dict[str, str], ...]
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        evidence_classes, class_counts = summarize_meta_context_classes(
            {"context_slots": [slot.to_dict() for slot in self.context_slots]}
        )
        return {
            "schema_version": self.schema_version,
            "current_query": self.current_query,
            "bundle_reason": self.bundle_reason,
            "active_topic": self.active_topic,
            "active_goal": self.active_goal,
            "active_domain": self.active_domain,
            "open_loop": self.open_loop,
            "next_expected_step": self.next_expected_step,
            "turn_type": self.turn_type,
            "response_mode": self.response_mode,
            "context_slots": [slot.to_dict() for slot in self.context_slots],
            "suppressed_context": [dict(item) for item in self.suppressed_context],
            "evidence_classes": list(evidence_classes),
            "context_class_counts": dict(class_counts),
            "primary_evidence_class": evidence_classes[0] if evidence_classes else "",
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
    "creative": AgentCapabilityProfile(
        agent="creative",
        capabilities=("image_generation", "creative_generation", "prompt_refinement"),
        strengths=("direct_image_requests", "visual_style_execution", "creative_artifacts"),
        typical_outputs=("image_path", "artifact_metadata", "prompt_summary"),
        handoff_fields=("goal", "prompt", "style_constraints", "expected_output", "query"),
    ),
    "developer": AgentCapabilityProfile(
        agent="developer",
        capabilities=("code_inspection", "debugging", "implementation_guidance", "test_planning"),
        strengths=("stacktrace_analysis", "repo_changes", "focused_code_fixes"),
        typical_outputs=("root_cause", "code_change_plan", "patch_summary"),
        handoff_fields=("goal", "error_context", "expected_output", "query"),
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
    "setup_build_probe": (
        OrchestrationRecipeStage(
            stage_id="setup_build_probe",
            agent="executor",
            goal=(
                "Pruefe vorhandene Repo- und Konfigurationsvorbereitungen fuer die angefragte "
                "Setup-/Integrationsaufgabe, fuehre nichts aus und liefere nur den belastbaren Ist-Stand."
            ),
            expected_output="repo_findings, existing_preparations, real_gaps",
            handoff_fields=("goal", "expected_output", "success_signal", "query"),
        ),
    ),
    "setup_build_execution": (
        OrchestrationRecipeStage(
            stage_id="setup_build_execution",
            agent="executor",
            goal=(
                "Pruefe vorhandene Repo- und Konfigurationsvorbereitungen fuer die angefragte "
                "Setup-/Integrationsaufgabe und leite daraus den konkreten ersten "
                "Umsetzungsschritt oder echten Blocker ab. Keine freie Meta-Hilfe, "
                "keine parallelen Scans."
            ),
            expected_output="repo_findings, existing_preparations, real_gaps, first_execution_step",
            handoff_fields=("goal", "expected_output", "success_signal", "query"),
        ),
    ),
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
    "document_analysis": (
        OrchestrationRecipeStage(
            stage_id="document_analysis",
            agent="document",
            goal=(
                "Lies die angegebene lokale Dokumentdatei, extrahiere den relevanten Inhalt "
                "und liefere die angeforderte Zusammenfassung oder Analyse ohne Web-Recherche."
            ),
            expected_output="document_summary, extracted_key_points, source_path",
            handoff_fields=("goal", "source_path", "expected_output", "query"),
        ),
    ),
    "email_send": (
        OrchestrationRecipeStage(
            stage_id="email_send",
            agent="executor",
            goal=(
                "Bereite den explizit adressierten E-Mail-Versand vor oder fuehre ihn mit dem "
                "verfuegbaren E-Mail-Tool aus, ohne in freie Beratung oder Recherche abzudriften."
            ),
            expected_output="delivery_status, recipient, subject, body",
            handoff_fields=("goal", "recipient", "subject", "body", "query"),
        ),
    ),
    "image_generation": (
        OrchestrationRecipeStage(
            stage_id="creative_image_generation",
            agent="creative",
            goal=(
                "Erzeuge fuer die direkte Bildanfrage ein hochwertiges Bildartefakt. "
                "Nutze die komplette Nutzerbeschreibung als Prompt-Anker und blockiere nicht "
                "mit Modus- oder Beratungshinweisen, solange die Anfrage eine klare Bildgenerierung ist."
            ),
            expected_output="image artifact path, prompt summary, generation status",
            handoff_fields=("goal", "prompt", "style_constraints", "expected_output", "query"),
        ),
    ),
    "creative_text_optimization": (
        OrchestrationRecipeStage(
            stage_id="creative_text_optimization",
            agent="creative",
            goal=(
                "Optimiere den angefragten Prompt oder Kreativtext direkt. "
                "Liefere eine verbesserte Version und, wenn hilfreich, kurze Hinweise zur Anwendung."
            ),
            expected_output="optimized_prompt, concise_usage_notes",
            handoff_fields=("goal", "prompt", "expected_output", "query"),
        ),
    ),
    "code_troubleshooting": (
        OrchestrationRecipeStage(
            stage_id="developer_error_triage",
            agent="developer",
            goal=(
                "Analysiere den uebergebenen Fehler- oder Codekontext und benenne die wahrscheinlich "
                "noetige Codeaenderung. Keine breite Recherche, wenn der Fehler aus dem lokalen Kontext "
                "ableitbar ist."
            ),
            expected_output="likely_root_cause, code_change_needed, files_or_missing_context",
            handoff_fields=("goal", "error_context", "expected_output", "query"),
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
    "setup_build_probe": ("meta", "executor"),
    "setup_build_execution": ("meta", "executor"),
    "simple_live_lookup": ("meta", "executor"),
    "simple_live_lookup_document": ("meta", "executor", "document"),
    "knowledge_research": ("meta", "research"),
    "document_analysis": ("meta", "document"),
    "email_send": ("meta", "executor"),
    "image_generation": ("meta", "creative"),
    "creative_text_optimization": ("meta", "creative"),
    "code_troubleshooting": ("meta", "developer"),
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
    "document_analysis",
    "email_send",
    "image_generation",
    "creative_text_optimization",
    "code_troubleshooting",
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
    "aussage stimmt",
    "stimmt diese aussage",
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
    "uhrzeit",
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

_SIMPLE_LIVE_LOOKUP_FRESHNESS_TOPICS = (
    "meetup",
    "meetups",
    "veranstaltung",
    "veranstaltungen",
    "event",
    "events",
    "community",
    "communities",
)

_PUBLIC_INFORMATION_LOOKUP_CUES = (
    "aktuell",
    "aktuelle",
    "aktuellen",
    "heute",
    "morgen",
    "dieses jahr",
    "kommende",
    "anstehende",
    "neueste",
    "neuste",
    "gerade",
    "stehen an",
    "steht an",
    "finden statt",
    "findet statt",
    "gibt es",
)

_PUBLIC_INFORMATION_LOOKUP_TOPICS = (
    "arbeitsmarkt",
    "markt",
    "branche",
    "gesetz",
    "gesetze",
    "regelung",
    "regelungen",
    "preise",
    "preis",
    "kosten",
    "messen",
    "messe",
    "konferenz",
    "konferenzen",
    "kongress",
    "kongresse",
    "summit",
    "expo",
    "meetup",
    "meetups",
    "veranstaltung",
    "veranstaltungen",
    "event",
    "events",
    "förderung",
    "foerderung",
    "anbieter",
    "produkt",
    "produkte",
    "tool",
    "tools",
)

_PUBLIC_INFORMATION_LOOKUP_QUESTION_PATTERN = re.compile(
    r"\b(?:welche|welcher|welches|wann|wo|wer|was\s+gibt(?:'s|\s+es)?|wie\s+(?:ist|steht|sieht|entwickelt|laeuft|läuft|der|die|das))\b"
)

_SIMPLE_LIVE_LOOKUP_DIRECT_PATTERNS = (
    re.compile(r"\b(?:was|wieviel|wie\s+viel)\s+kostet\b"),
    re.compile(r"\b(?:bitcoin|btc|ethereum|eth)\b.*\b(?:kurs|preis)\b"),
    re.compile(r"\b(?:kurs|preis)\s+(?:von|fuer|für)\s+(?:bitcoin|btc|ethereum|eth)\b"),
    re.compile(r"\b(?:aktienkurs|wechselkurs)\b"),
    re.compile(r"\bwie\s+(?:spät|spaet)\s+(?:ist\s+es\s+)?(?:in|auf|am)\b"),
    re.compile(r"\bwie\s+viel\s+uhr\s+(?:ist\s+es\s+)?(?:in|auf|am)\b"),
    re.compile(r"\buhrzeit\s+(?:in|auf|am)\b"),
)

_LIVE_TRAVEL_DISCOVERY_HINTS = (
    "ausflugsziel",
    "ausflugsziele",
    "kulturziel",
    "kulturziele",
    "sehenswuerdigkeit",
    "sehenswürdigkeit",
    "sehenswuerdigkeiten",
    "sehenswürdigkeiten",
    "museum",
    "museen",
    "veranstaltung",
    "veranstaltungen",
    "event",
    "events",
)

_LIVE_TRAVEL_PLAN_OUTPUT_HINTS = (
    "tagesplan",
    "wochenendplan",
    "ausflugsplan",
    "reiseplan",
    "mach daraus einen plan",
    "mache daraus einen plan",
    "plan daraus",
)

_LIVE_TRAVEL_LOOKUP_INTENT_HINTS = (
    "such",
    "suche",
    "finde",
    "recherchiere",
    "empfiehl",
    "empfehle",
    "schlag mir",
    "vorschlaege",
    "vorschläge",
)

_LOCAL_DOCUMENT_ANALYSIS_HINTS = (
    "fasse",
    "zusammen",
    "zusammenfassung",
    "analysiere",
    "analyse",
    "lies",
    "lese",
    "extrahiere",
)

_EMAIL_SEND_ACTION_HINTS = (
    "sende",
    "schick",
    "schicke",
    "versende",
    "send ",
)

_EMAIL_ADDRESS_PATTERN = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_OWNER_EMAIL_REFERENCE_PATTERN = re.compile(
    r"\b(?:an\s+)?meine(?:r|m|n)?\s+(?:e[\s-]?(?:mail|meil)|mail)(?:\s+adresse)?\b"
)
_EMAIL_CONTENT_REFERENCE_HINTS = (
    "bericht",
    "recherche",
    "report",
    "pdf",
    "datei",
    "dokument",
    "zusammenfassung",
    "ergebnis",
    "es",
    "das",
    "ihn",
    "sie",
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

_NO_RESEARCH_HINTS = (
    "ohne recherche",
    "keine recherche",
    "nicht recherchieren",
    "nicht ins internet",
    "ohne internet",
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
    "checkliste",
    "bericht",
    "dokument",
    "exportiere",
    "speichere",
)

_LOCAL_FILE_TRANSFORM_HINTS = (
    "wandle",
    "umwandeln",
    "wandle um",
    "konvertiere",
    "konvertieren",
    "convert",
    "exportiere",
    "exportieren",
    "mach daraus",
    "mach daraud",
)

_LOCAL_FILE_OPERATION_HINTS = (
    "benenne",
    "benenn",
    "copy",
    "cp ",
    "entpacke",
    "entpacken",
    "extrahiere",
    "extrahieren",
    "erstelle einen ordner",
    "erstelle ordner",
    "kopiere",
    "kopieren",
    "mkdir",
    "neuen ordner",
    "ordner anlegen",
    "ordner erstellen",
    "rename",
    "unzip",
    "verschiebe",
    "verschieben",
)

_IMAGE_GENERATION_ACTION_HINTS = (
    "erstelle",
    "erstell ",
    "erzeuge",
    "generiere",
    "mach ",
    "mache ",
    "male",
    "zeichne",
    "visualisiere",
    "create",
    "generate",
)

_IMAGE_GENERATION_OBJECT_PATTERNS = (
    re.compile(r"\b[\wäöüß-]*bild(?:er)?\b"),
    re.compile(r"\b(?:image|illustration|foto|photo|poster|coverbild|avatar|grafik|skizze|zeichnung|diagramm)\b"),
    re.compile(r"\b(?:portrait|portraet|porträt)\b"),
)

_IMAGE_NON_GENERATION_HINTS = (
    "beschreibe dieses bild",
    "beschreib dieses bild",
    "analysiere dieses bild",
    "analysier dieses bild",
    "was siehst du",
    "bildbeschreibung",
)

_CREATIVE_TEXT_OPTIMIZATION_HINTS = (
    "optimiere diesen prompt",
    "verbessere diesen prompt",
    "ueberarbeite diesen prompt",
    "überarbeite diesen prompt",
    "prompt optimieren",
)

_DEVELOPER_TROUBLESHOOTING_HINTS = (
    "lies diesen fehler",
    "lies den fehler",
    "code geändert werden muss",
    "code geaendert werden muss",
    "im code geändert",
    "im code geaendert",
    "stack trace",
    "stacktrace",
    "debugge",
)

_LOCAL_FILE_SOURCE_EXTENSIONS = (
    "csv",
    "doc",
    "docx",
    "html",
    "md",
    "odp",
    "ods",
    "odt",
    "pdf",
    "ppt",
    "pptx",
    "rtf",
    "txt",
    "xls",
    "xlsx",
)

_LOCAL_FILE_TARGET_FORMATS = (
    "csv",
    "doc",
    "docx",
    "excel",
    "html",
    "odt",
    "pdf",
    "txt",
    "xlsx",
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
    "speichere dir",
    "antworte mir",
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
    "vergiss",
    "loesch",
    "lösch",
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
    "conversation_state_active_domain",
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
_META_CONTEXT_STOPWORDS = {
    "aber",
    "aktuelle",
    "aktuellen",
    "alle",
    "auch",
    "bitte",
    "bzw",
    "dann",
    "danach",
    "darauf",
    "darin",
    "darueber",
    "darüber",
    "das",
    "dass",
    "dem",
    "den",
    "der",
    "des",
    "die",
    "du",
    "dir",
    "doch",
    "dort",
    "dich",
    "drei",
    "eine",
    "einer",
    "eines",
    "einen",
    "einem",
    "etwas",
    "fuer",
    "für",
    "genau",
    "hier",
    "http",
    "https",
    "ich",
    "immer",
    "mir",
    "mich",
    "jetzt",
    "kann",
    "kannst",
    "koennte",
    "könnte",
    "mach",
    "mehr",
    "mein",
    "meine",
    "mit",
    "nach",
    "neuen",
    "noch",
    "oder",
    "ohne",
    "ueber",
    "über",
    "sagt",
    "gesagt",
    "schon",
    "sein",
    "sind",
    "soll",
    "sollst",
    "statt",
    "the",
    "und",
    "uns",
    "unter",
    "use",
    "was",
    "weil",
    "weiter",
    "welche",
    "wenn",
    "wie",
    "wir",
    "wird",
    "wirst",
    "hast",
    "wollen",
    "wollen",
    "you",
    "zum",
    "zur",
}
_META_CONTEXT_DEPENDENT_MARKERS = (
    "da ",
    "damit",
    "daran",
    "darauf",
    "darueber",
    "darüber",
    "dort",
    "erste option",
    "fuss fassen",
    "fuß fassen",
    "hier",
    "kann ich da",
    "koennte ich da",
    "könnte ich da",
    "setz fort",
    "weiter",
)

_META_CONTEXT_LOCATION_MARKERS = (
    "maps",
    "standort",
    "route",
    "naehe",
    "nähe",
    "offenbach",
    "marktplatz",
    "latitude",
    "longitude",
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
    if task_type == "setup_build_probe":
        return "setup_build_probe"
    if task_type == "setup_build_execution":
        return "setup_build_execution"
    if task_type == "simple_live_lookup":
        return "simple_live_lookup"
    if task_type == "simple_live_lookup_document":
        return "simple_live_lookup_document"
    if task_type == "knowledge_research":
        return "knowledge_research"
    if task_type == "document_analysis":
        return "document_analysis"
    if task_type == "email_send":
        return "email_send"
    if task_type == "image_generation":
        return "image_generation"
    if task_type == "creative_text_optimization":
        return "creative_text_optimization"
    if task_type == "code_troubleshooting":
        return "code_troubleshooting"
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


def _looks_like_simple_live_lookup_direct_query(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    if _has_any(normalized, _SIMPLE_LIVE_LOOKUP_DIRECT_HINTS):
        return True
    return any(pattern.search(normalized) for pattern in _SIMPLE_LIVE_LOOKUP_DIRECT_PATTERNS)


def _looks_like_public_information_lookup_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    has_question_shape = bool(_PUBLIC_INFORMATION_LOOKUP_QUESTION_PATTERN.search(normalized))
    has_public_topic = _has_any(normalized, _PUBLIC_INFORMATION_LOOKUP_TOPICS)
    if not (has_question_shape and has_public_topic):
        return False
    return _has_any(normalized, _PUBLIC_INFORMATION_LOOKUP_CUES) or any(
        token in normalized
        for token in (
            "deutschland",
            "schweiz",
            "europa",
            "usa",
            "frankfurt",
            "berlin",
            "muenchen",
            "münchen",
            "hamburg",
            "koeln",
            "köln",
        )
    )


def _looks_like_live_travel_plan_document_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    return (
        _has_any(normalized, _LIVE_TRAVEL_LOOKUP_INTENT_HINTS)
        and _has_any(normalized, _LIVE_TRAVEL_DISCOVERY_HINTS)
        and _has_any(normalized, _LIVE_TRAVEL_PLAN_OUTPUT_HINTS)
    )


def _looks_like_local_document_analysis_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    has_local_pdf_path = bool(re.search(r"(?:^|\s)(?:~|/)[^\s\"']+\.pdf(?:\b|$)", normalized))
    return has_local_pdf_path and _has_any(normalized, _LOCAL_DOCUMENT_ANALYSIS_HINTS)


def _looks_like_email_send_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    has_owner_email_reference = bool(_OWNER_EMAIL_REFERENCE_PATTERN.search(normalized))
    has_mail_anchor = has_owner_email_reference or any(
        token in normalized for token in ("email", "e-mail", "e meil", "e-meil", "mail")
    )
    if not has_mail_anchor:
        return False
    if _EMAIL_ADDRESS_PATTERN.search(normalized):
        return _has_any(normalized, _EMAIL_SEND_ACTION_HINTS)
    if has_owner_email_reference and _has_any(normalized, _EMAIL_CONTENT_REFERENCE_HINTS):
        return True
    return False


def _looks_like_local_file_transform_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False

    source_ext = "|".join(re.escape(item) for item in _LOCAL_FILE_SOURCE_EXTENSIONS)
    target_formats = "|".join(re.escape(item) for item in _LOCAL_FILE_TARGET_FORMATS)
    has_source_file = bool(re.search(rf"\.(?:{source_ext})(?:\b|$)", normalized))
    if not has_source_file:
        return False

    has_local_path = bool(re.search(rf"(?:^|\s)(?:~|/)[^\s\"']+\.(?:{source_ext})(?:\b|$)", normalized))
    has_file_anchor = has_local_path or "datei" in normalized or "file" in normalized
    if not has_file_anchor:
        return False

    has_target_format = bool(
        re.search(rf"\b(?:{target_formats})\b", normalized)
        or re.search(rf"\b(?:in|als|nach|zu)\s+(?:eine\s+|ein\s+)?(?:{target_formats})\b", normalized)
    )
    if not has_target_format:
        return False

    if _has_any(normalized, _LOCAL_FILE_TRANSFORM_HINTS):
        return True
    return bool(
        re.search(rf"\b(?:erstelle|erzeuge)\s+(?:eine\s+|ein\s+)?(?:{target_formats})\s+(?:aus|von)\b", normalized)
        or re.search(rf"\b(?:in|als|nach|zu)\s+(?:eine\s+|ein\s+)?(?:{target_formats})\b", normalized)
    )


def _looks_like_local_file_operation_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False

    has_local_path = bool(re.search(r"(?:^|\s)(?:~|/)[^\s\"']+", normalized))
    if not has_local_path:
        return False

    return _has_any(normalized, _LOCAL_FILE_OPERATION_HINTS)


def _looks_like_image_generation_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    if _has_any(normalized, _IMAGE_NON_GENERATION_HINTS):
        return False
    has_generation_action = _has_any(normalized, _IMAGE_GENERATION_ACTION_HINTS)
    if not has_generation_action:
        return False
    return any(pattern.search(normalized) for pattern in _IMAGE_GENERATION_OBJECT_PATTERNS)


def _looks_like_creative_text_optimization_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    if not _has_any(normalized, _CREATIVE_TEXT_OPTIMIZATION_HINTS):
        return False
    return "prompt" in normalized or "kreativ-agent" in normalized or "creative agent" in normalized


def _looks_like_developer_troubleshooting_request(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    if _has_any(normalized, _DEVELOPER_TROUBLESHOOTING_HINTS):
        return True
    has_error_anchor = any(token in normalized for token in ("fehler", "error", "exception", "traceback"))
    has_code_anchor = any(token in normalized for token in ("code", "datei", "repo", "repository", "stacktrace"))
    has_fix_intent = any(token in normalized for token in ("änd", "aend", "fix", "beheb", "debug", "muss"))
    return has_error_anchor and has_code_anchor and has_fix_intent


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
    if re.search(
        r"\b(?:vergiss|l[öo]sch(?:e)?|loesch(?:e)?)\b.*\b(?:letzte\s+)?(?:praeferenz|präferenz|praferenz|preference|vorgabe|regel)\b",
        normalized,
    ):
        return True
    if re.search(
        r"\bwenn\s+ich\b.*\bsage\b.*\b(?:nutze|verwende|nimm|bevorzuge|priorisiere)\b",
        normalized,
    ):
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

    if looks_like_meta_clarification_turn(text) and not has_simple_live_lookup and not has_local_search:
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
        if dominant_turn_type == "correction" and str(classification.get("reason") or "").strip().lower() != (
            f"turn_understanding:{dominant_turn_type}"
        ):
            return {
                **classification,
                "reason": f"turn_understanding:{dominant_turn_type}",
            }
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
    active_domain = _extract_meta_followup_field(raw, "conversation_state_active_domain")
    open_loop = _extract_meta_followup_field(raw, "conversation_state_open_loop")
    next_expected_step = _extract_meta_followup_field(raw, "conversation_state_next_expected_step")
    turn_type_hint = _extract_meta_followup_field(raw, "conversation_state_turn_type_hint")
    preferences = _extract_meta_followup_list(raw, "conversation_state_preferences", limit=4)
    recent_corrections = _extract_meta_followup_list(raw, "conversation_state_recent_corrections", limit=4)
    plan_blocked_by_raw = _extract_meta_followup_field(raw, "conversation_plan_blocked_by")
    plan_blocked_by = [item.strip() for item in plan_blocked_by_raw.split("||") if item.strip()]
    plan_step_count_raw = _extract_meta_followup_field(raw, "conversation_plan_step_count")
    try:
        plan_step_count = max(0, min(int(plan_step_count_raw), 32))
    except (TypeError, ValueError):
        plan_step_count = 0
    active_plan = {
        "plan_id": _extract_meta_followup_field(raw, "conversation_plan_id"),
        "plan_mode": _extract_meta_followup_field(raw, "conversation_plan_mode"),
        "goal": _extract_meta_followup_field(raw, "conversation_plan_goal"),
        "goal_satisfaction_mode": _extract_meta_followup_field(raw, "conversation_plan_goal_satisfaction_mode"),
        "next_step_id": _extract_meta_followup_field(raw, "conversation_plan_next_step_id"),
        "next_step_title": _extract_meta_followup_field(raw, "conversation_plan_next_step_title"),
        "next_step_agent": _extract_meta_followup_field(raw, "conversation_plan_next_step_agent"),
        "last_completed_step_id": _extract_meta_followup_field(raw, "conversation_plan_last_completed_step_id"),
        "last_completed_step_title": _extract_meta_followup_field(raw, "conversation_plan_last_completed_step_title"),
        "blocked_by": plan_blocked_by,
        "step_count": plan_step_count,
        "status": _extract_meta_followup_field(raw, "conversation_plan_status"),
    }
    if not any(
        active_plan.get(key)
        for key in (
            "plan_id",
            "goal",
            "next_step_id",
            "next_step_title",
            "last_completed_step_id",
        )
    ) and not active_plan.get("blocked_by") and not active_plan.get("step_count"):
        active_plan = {}
    payload = {
        "active_topic": _clean_meta_state_fragment(active_topic, max_chars=220),
        "active_goal": _clean_meta_state_fragment(active_goal, max_chars=220),
        "active_domain": _clean_meta_state_fragment(active_domain, max_chars=64).lower(),
        "open_loop": _clean_meta_state_fragment(open_loop, max_chars=220),
        "next_expected_step": _clean_meta_state_fragment(next_expected_step, max_chars=220),
        "turn_type_hint": _clean_meta_state_fragment(turn_type_hint, max_chars=64).lower(),
        "preferences": preferences,
        "recent_corrections": recent_corrections,
        "active_plan": active_plan,
    }
    return {key: value for key, value in payload.items() if value}


def _meta_context_slot_text(label: str, parts: Iterable[str]) -> str:
    cleaned = [str(item or "").strip() for item in parts if str(item or "").strip()]
    if not cleaned:
        return ""
    return f"{label}: " + " | ".join(cleaned[:4])


def _session_domain_family(domain: str) -> str:
    normalized = str(domain or "").strip().lower()
    if normalized in {"travel_advisory", "topic_advisory", "life_advisory"}:
        return "advisory"
    return normalized


def _session_domains_compatible(current_domain: str, session_domain: str) -> bool:
    current = str(current_domain or "").strip().lower()
    session = str(session_domain or "").strip().lower()
    if not current or not session:
        return True
    if current == session:
        return True
    current_family = _session_domain_family(current)
    session_family = _session_domain_family(session)
    if current_family == "advisory" and session_family == "advisory":
        if current == "topic_advisory" or session == "topic_advisory":
            return True
    return False


def _align_meta_frame_to_reason_domain(
    *,
    meta_request_frame,
    final_reason: str,
    effective_query: str,
    dominant_turn_type: str,
    final_response_mode: str,
    answer_shape: str,
    final_task_type: str,
    active_topic: str,
    open_goal: str,
    next_step: str,
    active_domain: str,
    final_chain: Iterable[str],
    active_plan: Mapping[str, Any] | None,
):
    reason_text = str(final_reason or "").strip().lower()
    if not reason_text.startswith("frame:"):
        return meta_request_frame

    reason_domain = reason_text.split("frame:", 1)[1].strip()
    if not reason_domain or reason_domain == str(meta_request_frame.task_domain or "").strip().lower():
        return meta_request_frame
    if reason_domain not in {"travel_advisory", "life_advisory", "topic_advisory"}:
        return meta_request_frame
    if str(meta_request_frame.task_domain or "").strip().lower() not in {"topic_advisory", "general_task"}:
        return meta_request_frame

    repaired = build_meta_request_frame(
        effective_query=effective_query,
        dominant_turn_type=dominant_turn_type,
        response_mode=final_response_mode,
        answer_shape=answer_shape,
        task_type=final_task_type,
        active_topic=active_topic,
        open_goal=open_goal,
        next_step=next_step,
        active_domain=reason_domain or active_domain,
        recommended_agent_chain=final_chain,
        active_plan=active_plan,
    )
    return repaired


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
            evidence_class=classify_meta_context_slot(slot),
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
        if stripped in _META_CONTEXT_STOPWORDS:
            continue
        if stripped.isdigit():
            continue
        cleaned.append(stripped)
    return cleaned


def _meta_context_overlap_size(left: str, right: str) -> int:
    left_terms = set(_tokenize_meta_context_terms(left))
    right_terms = set(_tokenize_meta_context_terms(right))
    if not left_terms or not right_terms:
        return 0
    return len(left_terms.intersection(right_terms))


def _is_context_dependent_meta_query(
    query: str,
    *,
    turn_type: str = "",
    conversation_state: Mapping[str, Any] | None = None,
) -> bool:
    lowered = str(query or "").strip().lower()
    if not lowered:
        return False
    if turn_type in {
        "followup",
        "clarification",
        "correction",
        "handover_resume",
        "approval_response",
        "auth_response",
    }:
        return True
    if any(marker in lowered for marker in _META_CONTEXT_DEPENDENT_MARKERS):
        return True

    terms = _tokenize_meta_context_terms(lowered)
    if len(terms) > 6:
        return False

    state = dict(conversation_state or {})
    return any(
        str(state.get(field) or "").strip()
        for field in ("active_topic", "active_goal", "open_loop", "next_expected_step")
    )


def _build_meta_context_reference_texts(
    *,
    current_query: str,
    dialog_state: Mapping[str, Any],
    conversation_state: Mapping[str, Any],
    recent_user_turns: Iterable[str] | None = None,
    turn_type: str = "",
) -> List[str]:
    refs = _dedupe_meta_state_fragments(
        [current_query],
        limit=1,
        max_chars=220,
    )
    if not _is_context_dependent_meta_query(
        current_query,
        turn_type=turn_type,
        conversation_state=conversation_state,
    ):
        return refs

    bridge_parts = [
        conversation_state.get("active_topic"),
        conversation_state.get("active_goal"),
        conversation_state.get("open_loop"),
        conversation_state.get("next_expected_step"),
        dialog_state.get("active_topic"),
        dialog_state.get("open_goal"),
        *(recent_user_turns or ()),
    ]
    refs.extend(
        item
        for item in _dedupe_meta_state_fragments(bridge_parts, limit=4, max_chars=220)
        if item and item not in refs
    )
    return refs[:5]


def _meta_context_reference_overlap(item: str, reference_texts: Iterable[str]) -> int:
    best = 0
    for ref in reference_texts:
        overlap = _meta_context_overlap_size(item, ref)
        if overlap > best:
            best = overlap
    return best


def _looks_like_location_meta_context(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in _META_CONTEXT_LOCATION_MARKERS)


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
    recent_user_turns: Iterable[str] | None,
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
    reference_texts = _build_meta_context_reference_texts(
        current_query=effective_query,
        dialog_state=dialog_state,
        conversation_state=conversation_state,
        recent_user_turns=recent_user_turns,
        turn_type=turn_type,
    )

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
        reference_overlap = _meta_context_reference_overlap(content, reference_texts)
        relevance = float(item.get("relevance") or 0.0)
        if reference_overlap <= 0:
            if _looks_like_location_meta_context(rendered) and not (
                is_location_local_query(effective_query.lower()) or is_location_route_query(effective_query.lower())
            ):
                continue
            if relevance < 0.8:
                continue
        scored.append(((reference_overlap * 2) + overlap + (1 if relevance >= 0.8 else 0), relevance, rendered))

    scored.sort(key=lambda row: (-row[0], -row[1], len(row[2])))
    return _normalize_meta_context_fragments((row[2] for row in scored), limit=2)


def _select_relevant_preference_memory(
    *,
    effective_query: str,
    dialog_state: Mapping[str, Any],
    conversation_state: Mapping[str, Any],
    recent_user_turns: Iterable[str] | None,
    turn_type: str,
    provided_hits: Iterable[Any] | None,
) -> Tuple[List[str], Dict[str, Any]]:
    if provided_hits is not None:
        selected = _normalize_meta_context_fragments(provided_hits, limit=2)
        return selected, {
            "selected": list(selected),
            "selected_details": [],
            "ignored_low_stability": [],
            "conflicts_resolved": [],
        }

    try:
        from memory.memory_system import memory_manager
    except Exception:
        return [], {
            "selected": [],
            "selected_details": [],
            "ignored_low_stability": [],
            "conflicts_resolved": [],
        }

    stored_selection = select_stored_preference_memory_with_summary(
        effective_query=effective_query,
        conversation_state=conversation_state,
        turn_type=turn_type,
        memory_manager=memory_manager,
        limit=2,
    )
    stored_candidates = list(stored_selection.selected)
    selection_summary = stored_selection.to_dict()
    prioritized = _normalize_meta_context_fragments(stored_candidates, limit=2)
    if len(prioritized) >= 2:
        selection_summary["selected"] = list(prioritized)
        return prioritized, selection_summary

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
    reference_texts = _build_meta_context_reference_texts(
        current_query=effective_query,
        dialog_state=dialog_state,
        conversation_state=conversation_state,
        recent_user_turns=recent_user_turns,
        turn_type=turn_type,
    )

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
        if lowered.startswith("stored_preference:"):
            bonus += 2.0
        if preference_mode and any(token in lowered for token in ("hook =>", "self_model =>", "user_profile:preference")):
            bonus += 0.5
        if overlap <= 0 and bonus <= 0:
            continue
        scored.append((overlap, bonus, cleaned))

    scored.sort(key=lambda row: (-row[0], -row[1], len(row[2])))
    selected = list(prioritized)
    seen = set(selected)
    for _, _, cleaned in scored:
        if cleaned in seen:
            continue
        selected.append(cleaned)
        seen.add(cleaned)
        if len(selected) >= 2:
            break
    explicit_preference_turn = any(
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
            "quellen",
            "news",
            "nachrichten",
        )
    )
    filtered_selected = [
        item
        for item in selected
        if (
            explicit_preference_turn
            or _meta_context_reference_overlap(item, reference_texts) > 0
            or any(
                token in item.lower()
                for token in (
                    "response_style",
                    "output_format",
                    "language",
                    "kurz",
                    "praezise",
                    "präzise",
                    "deutsch",
                    "json",
                    "struktur",
                )
            )
        )
    ]
    normalized_selected = _normalize_meta_context_fragments(filtered_selected, limit=2)
    selection_summary["selected"] = list(normalized_selected)
    selection_summary["filtered_irrelevant"] = [
        item for item in selected if item not in normalized_selected
    ]
    return normalized_selected, selection_summary


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
        if is_generic_followup_prompt(cleaned):
            continue
        selected.append(cleaned)
        if len(selected) >= 3:
            break
    return selected


def _select_recent_historical_topic_fallback(
    *,
    effective_query: str,
    recent_user_turns: Iterable[str],
    recent_assistant_turns: Iterable[str],
    conversation_state: Mapping[str, Any],
    limit: int = 2,
) -> Tuple[List[str], Dict[str, Any]]:
    hint = parse_historical_topic_recall_hint(effective_query)
    if not hint.requested or hint.time_label not in {"recent_moment", "recent_history"}:
        return [], {
            "requested": hint.requested,
            "time_label": hint.time_label,
            "selected": [],
            "selected_details": [],
            "history_size": 0,
            "focus_terms": list(hint.focus_terms),
            "fallback_applied": False,
        }

    lowered_query = _clean_meta_state_fragment(effective_query, max_chars=220).lower()
    wants_assistant_recall = "du" in lowered_query and any(
        token in lowered_query for token in ("gesagt", "geantwortet", "antwort", "geschrieben")
    )
    candidates: List[Tuple[float, str, str]] = []

    for index, item in enumerate(recent_user_turns):
        cleaned = _clean_meta_state_fragment(item, max_chars=220)
        if not cleaned:
            continue
        overlap = _meta_context_overlap_size(cleaned, effective_query)
        if hint.focus_terms and overlap <= 0 and index > 0:
            continue
        score = float((overlap * 3) + max(0, 4 - index) + 0.6)
        candidates.append((score, "recent_user_turn", cleaned))

    if wants_assistant_recall:
        for index, item in enumerate(recent_assistant_turns):
            cleaned = _clean_meta_state_fragment(item, max_chars=220)
            if not cleaned:
                continue
            overlap = _meta_context_overlap_size(cleaned, effective_query)
            score = float((overlap * 3) + max(0, 4 - index) + 1.2)
            candidates.append((score, "recent_assistant_turn", cleaned))

    state_preview = _meta_context_slot_text(
        "conversation_state",
        [
            conversation_state.get("active_topic"),
            conversation_state.get("active_goal"),
            conversation_state.get("open_loop"),
        ],
    )
    if state_preview:
        overlap = _meta_context_overlap_size(state_preview, effective_query)
        candidates.append((float((overlap * 3) + 1.0), "conversation_state", state_preview))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    selected: List[str] = []
    selected_details: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for score, source, content in candidates:
        if content in seen:
            continue
        seen.add(content)
        if source == "recent_assistant_turn":
            rendered = f"historical_topic[{hint.time_label}] => recent_assistant_turn: {content}"
        elif source == "conversation_state":
            rendered = f"historical_topic[{hint.time_label}] => {content}"
        else:
            rendered = f"historical_topic[{hint.time_label}] => recent_user_turn: {content}"
        selected.append(rendered)
        selected_details.append(
            {
                "source": source,
                "content_preview": content[:180],
                "time_label": hint.time_label,
                "score": round(float(score), 2),
            }
        )
        if len(selected) >= max(1, limit):
            break

    return selected, {
        "requested": hint.requested,
        "time_label": hint.time_label,
        "selected": list(selected),
        "selected_details": selected_details,
        "history_size": 0,
        "focus_terms": list(hint.focus_terms),
        "fallback_applied": bool(selected),
        "fallback_source": selected_details[0]["source"] if selected_details else "",
    }


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
    if is_generic_followup_prompt(open_loop):
        open_loop = ""
    if is_generic_followup_prompt(next_step):
        next_step = ""
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
                "evidence_class": "conversation_state",
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
                        "evidence_class": "conversation_state",
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
                    "evidence_class": "conversation_state",
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
                    "evidence_class": "preference_profile",
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
    provisional_task_domain: str = "",
    dialog_state: Mapping[str, Any] | None = None,
    conversation_state: Mapping[str, Any] | None = None,
    turn_understanding: Mapping[str, Any] | None = None,
    session_summary: str = "",
    recent_user_turns: Iterable[str] | None = None,
    recent_assistant_turns: Iterable[str] | None = None,
    topic_history: Iterable[Any] | None = None,
    topic_memory_hits: Iterable[Any] | None = None,
    preference_memory_hits: Iterable[Any] | None = None,
    semantic_recall_hits: Iterable[Any] | None = None,
) -> Tuple[MetaContextBundle, Dict[str, Any], Dict[str, Any]]:
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
        "active_domain": explicit_state.get("active_domain")
        or followup_state.get("active_domain")
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
        "active_plan": explicit_state.get("active_plan")
        or followup_state.get("active_plan")
        or {},
        "topic_confidence": explicit_state.get("topic_confidence") or 0.0,
    }
    active_session_domain = str(merged_state.get("active_domain") or "").strip().lower()
    requested_domain = str(provisional_task_domain or "").strip().lower()
    session_domain_filtered = bool(
        requested_domain
        and active_session_domain
        and not _session_domains_compatible(requested_domain, active_session_domain)
    )
    if session_domain_filtered:
        merged_state["active_topic"] = ""
        merged_state["active_goal"] = ""
        merged_state["open_loop"] = ""
        merged_state["next_expected_step"] = ""
        merged_state["active_plan"] = {}
        merged_state["topic_confidence"] = 0.0
        merged_state["active_domain"] = requested_domain
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
    semantic_recall = [] if session_domain_filtered else _normalize_meta_context_fragments(semantic_recall_hits, limit=2)
    topic_memory = _select_relevant_topic_memory(
        raw_query=raw,
        effective_query=effective_query,
        dialog_state=dialog,
        conversation_state=merged_state,
        recent_user_turns=recent_users,
        turn_type=turn_type,
        provided_hits=topic_memory_hits,
    )
    if session_domain_filtered:
        topic_memory = []
    preference_memory, preference_selection = _select_relevant_preference_memory(
        effective_query=effective_query,
        dialog_state=dialog,
        conversation_state=merged_state,
        recent_user_turns=recent_users,
        turn_type=turn_type,
        provided_hits=preference_memory_hits,
    )
    historical_topic_memory, historical_topic_selection = select_historical_topic_memory(
        topic_history,
        session_id=str((conversation_state or {}).get("session_id") or "default"),
        query=effective_query,
    )
    if session_domain_filtered:
        historical_topic_memory = []
        historical_topic_selection = {
            **dict(historical_topic_selection or {}),
            "selected": [],
            "selected_details": [],
            "domain_filtered": True,
        }
    if not historical_topic_memory:
        historical_topic_memory, historical_topic_selection = _select_recent_historical_topic_fallback(
            effective_query=effective_query,
            recent_user_turns=recent_users,
            recent_assistant_turns=recent_assistant,
            conversation_state=merged_state,
        )
        if session_domain_filtered:
            historical_topic_memory = []
            historical_topic_selection = {
                **dict(historical_topic_selection or {}),
                "selected": [],
                "selected_details": [],
                "domain_filtered": True,
            }
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
            merged_state.get("active_domain"),
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
    next_priority = 4
    for item in historical_topic_memory[:2]:
        _append_meta_context_slot(
            slots,
            slot="historical_topic_memory",
            priority=next_priority,
            content=item,
            source="topic_history",
        )
        next_priority += 1
    for item in recent_users[:2]:
        _append_meta_context_slot(
            slots,
            slot="recent_user_turn",
            priority=next_priority,
            content=item,
            source="recent_user_queries",
        )
        next_priority += 1
    for item in topic_memory:
        _append_meta_context_slot(
            slots,
            slot="topic_memory",
            priority=next_priority,
            content=item,
            source="topic_memory",
        )
        next_priority += 1
    for item in preference_memory:
        _append_meta_context_slot(
            slots,
            slot="preference_memory",
            priority=next_priority,
            content=item,
            source="preference_memory",
        )
        next_priority += 1
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
    if session_domain_filtered:
        suppressed_context.append(
            {
                "source": "conversation_state",
                "evidence_class": "conversation_state",
                "reason": f"session_domain_filtered:{active_session_domain}->{requested_domain}",
                "content_preview": (
                    str(explicit_state.get("active_topic") or "")
                    or str(followup_state.get("active_topic") or "")
                    or active_session_domain
                )[:140],
            }
        )
    suppressed_pairs = []
    for item in suppressed_context:
        suppressed_source = str(item.get("source") or "").strip()
        preview = str(item.get("content_preview") or "").strip().lower()
        if not suppressed_source or not preview:
            continue
        if suppressed_source == "assistant_reply":
            allowed_sources = {"recent_assistant_replies"}
        else:
            allowed_sources = {suppressed_source}
        suppressed_pairs.append((allowed_sources, preview))
    if suppressed_pairs:
        filtered_slots: List[MetaContextSlot] = []
        for slot in slots:
            source = str(slot.source or "").strip()
            content = str(slot.content or "").strip().lower()
            should_skip = False
            for allowed_sources, preview in suppressed_pairs:
                if source not in allowed_sources or not preview:
                    continue
                if preview in content or content in preview:
                    should_skip = True
                    break
            if not should_skip:
                filtered_slots.append(slot)
        slots = filtered_slots
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
        active_domain=_clean_meta_state_fragment(merged_state.get("active_domain"), max_chars=64).lower(),
        open_loop=_clean_meta_state_fragment(selected_open_loop, max_chars=220),
        next_expected_step=_clean_meta_state_fragment(merged_state.get("next_expected_step"), max_chars=220),
        turn_type=turn_type,
        response_mode=response_mode,
        context_slots=tuple(sorted(slots, key=lambda item: item.priority)),
        suppressed_context=tuple(suppressed_context),
        confidence=round(max(0.0, min(confidence or 0.0, 1.0)), 2),
    ), preference_selection, historical_topic_selection


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
    if payload.get("active_domain"):
        lines.append(f"active_domain: {payload['active_domain']}")
    if payload.get("open_loop"):
        lines.append(f"open_loop: {payload['open_loop']}")
    if payload.get("next_expected_step"):
        lines.append(f"next_expected_step: {payload['next_expected_step']}")
    evidence_classes = list(payload.get("evidence_classes") or [])
    if evidence_classes:
        lines.append("evidence_classes: " + ", ".join(str(item) for item in evidence_classes))
    if slots:
        lines.append("context_slots:")
        for item in slots[:6]:
            if not isinstance(item, Mapping):
                continue
            evidence_suffix = ""
            evidence_class = str(item.get("evidence_class") or "").strip()
            if evidence_class:
                evidence_suffix = f" [{evidence_class}]"
            lines.append(
                f"- {str(item.get('priority') or '')}:{str(item.get('slot') or '').strip()} => "
                f"{str(item.get('content') or '').strip()}{evidence_suffix}"
            )
    return "\n".join(lines)


def _apply_meta_clarity_to_preference_selection(
    selection: Mapping[str, Any] | None,
    clarity_contract: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    payload = dict(selection or {})
    contract = parse_meta_clarity_contract(clarity_contract or {})
    if not payload or not contract:
        return payload

    allowed_slots = {
        str(item or "").strip()
        for item in (contract.get("allowed_context_slots") or [])
        if str(item or "").strip()
    }
    forbidden_slots = {
        str(item or "").strip()
        for item in (contract.get("forbidden_context_slots") or [])
        if str(item or "").strip()
    }
    preference_allowed = "preference_memory" not in forbidden_slots and (
        not allowed_slots or "preference_memory" in allowed_slots
    )
    if preference_allowed:
        return payload

    filtered_irrelevant = list(payload.get("filtered_irrelevant") or [])
    for item in payload.get("selected") or []:
        rendered = _clean_meta_state_fragment(item, max_chars=220)
        if not rendered:
            continue
        filtered_irrelevant.append(
            {
                "rendered": rendered,
                "reason": "clarity_contract_filtered_preference_memory",
            }
        )
    payload["selected"] = []
    payload["selected_details"] = []
    if filtered_irrelevant:
        payload["filtered_irrelevant"] = filtered_irrelevant[:8]
    return payload


def _normalize_authoritative_meta_context_bundle(
    bundle: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    payload = dict(bundle or {})
    normalized_slots = []
    for item in (payload.get("context_slots") or []):
        if not isinstance(item, Mapping):
            continue
        slot_payload = dict(item)
        slot_payload["evidence_class"] = str(
            slot_payload.get("evidence_class") or classify_meta_context_slot(slot_payload.get("slot"))
        ).strip().lower()
        normalized_slots.append(slot_payload)
    payload["context_slots"] = normalized_slots
    for item in (payload.get("suppressed_context") or []):
        if not isinstance(item, Mapping):
            continue
        if str(item.get("evidence_class") or "").strip():
            continue
        item["evidence_class"] = classify_meta_context_slot(item.get("source"))

    slot_names = {
        str(item.get("slot") or "").strip()
        for item in (payload.get("context_slots") or [])
        if isinstance(item, Mapping) and str(item.get("slot") or "").strip()
    }
    evidence_classes, class_counts = summarize_meta_context_classes(payload)
    payload["evidence_classes"] = list(evidence_classes)
    payload["context_class_counts"] = dict(class_counts)
    payload["primary_evidence_class"] = evidence_classes[0] if evidence_classes else ""
    if not slot_names:
        payload["active_topic"] = ""
        payload["active_goal"] = ""
        payload["active_domain"] = ""
        payload["open_loop"] = ""
        payload["next_expected_step"] = ""
        return payload

    if not slot_names.intersection({"conversation_state", "topic_memory", "historical_topic_memory"}):
        payload["active_topic"] = ""
        payload["active_goal"] = ""
        payload["active_domain"] = ""
    if not slot_names.intersection({"open_loop", "conversation_state"}):
        payload["open_loop"] = ""
    if not slot_names.intersection({"open_loop", "conversation_state"}):
        payload["next_expected_step"] = ""
    return payload


def _build_authoritative_meta_context_view(
    *,
    meta_request_frame: Mapping[str, Any] | None,
    clarity_contract: Mapping[str, Any] | None,
    meta_context_bundle: Mapping[str, Any] | None,
    preference_memory_selection: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    admitted = apply_meta_request_frame_context_admission(
        meta_request_frame,
        bundle=meta_context_bundle,
        preference_memory_selection=preference_memory_selection,
    )
    filtered_bundle = apply_meta_clarity_to_bundle(
        admitted.get("meta_context_bundle") or {},
        clarity_contract,
    )
    normalized_bundle = _normalize_authoritative_meta_context_bundle(filtered_bundle)
    filtered_preferences = _apply_meta_clarity_to_preference_selection(
        admitted.get("preference_memory_selection") or {},
        clarity_contract,
    )
    return {
        "meta_context_bundle": normalized_bundle,
        "preference_memory_selection": filtered_preferences,
    }


def _build_authoritative_specialist_context_seed(
    *,
    meta_context_bundle: Mapping[str, Any] | None,
    preference_memory_selection: Mapping[str, Any] | None,
    conversation_state: Mapping[str, Any] | None,
    clarity_contract: Mapping[str, Any] | None,
    turn_type: str,
    response_mode: str,
) -> Dict[str, Any]:
    bundle = dict(meta_context_bundle or {})
    slot_names = {
        str(item.get("slot") or "").strip()
        for item in (bundle.get("context_slots") or [])
        if isinstance(item, Mapping) and str(item.get("slot") or "").strip()
    }
    conversation_state_map = dict(conversation_state or {})
    contract = parse_meta_clarity_contract(clarity_contract or {})
    evidence_classes, _ = summarize_meta_context_classes(bundle)
    allowed_slots = {
        str(item or "").strip()
        for item in (contract.get("allowed_context_slots") or [])
        if str(item or "").strip()
    }
    forbidden_slots = {
        str(item or "").strip()
        for item in (contract.get("forbidden_context_slots") or [])
        if str(item or "").strip()
    }

    def _slot_allowed(name: str) -> bool:
        if name in forbidden_slots:
            return False
        return not allowed_slots or name in allowed_slots

    topical_context_allowed = bool(
        {
            slot
            for slot in ("conversation_state", "topic_memory", "historical_topic_memory")
            if _slot_allowed(slot)
        }
    )
    open_loop_allowed = _slot_allowed("open_loop") or _slot_allowed("conversation_state")
    next_step_allowed = open_loop_allowed or _slot_allowed("conversation_state")
    preference_allowed = _slot_allowed("preference_memory")
    conversation_state_allowed = _slot_allowed("conversation_state")

    return build_specialist_context_payload(
        current_topic=(bundle.get("active_topic") if topical_context_allowed else "") or "",
        active_goal=(bundle.get("active_goal") if topical_context_allowed else "") or "",
        open_loop=(bundle.get("open_loop") if open_loop_allowed else "") or "",
        next_expected_step=(bundle.get("next_expected_step") if next_step_allowed else "") or "",
        turn_type=turn_type,
        response_mode=response_mode,
        user_preferences=list((preference_memory_selection or {}).get("selected") or [])
        if preference_allowed
        else [],
        recent_corrections=list(conversation_state_map.get("recent_corrections") or [])
        if conversation_state_allowed
        else [],
        evidence_classes=evidence_classes,
        primary_evidence_class=(evidence_classes[0] if evidence_classes else ""),
    )


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

    pending_followup_prompt = normalize_pending_followup_prompt(
        _extract_meta_followup_field(raw, "pending_followup_prompt")
    )
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
    pending_followup_prompt = normalize_pending_followup_prompt(
        _extract_meta_followup_field(raw, "pending_followup_prompt")
    )
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


def _looks_like_plan_resume_query(query: str) -> bool:
    lowered = str(query or "").strip().lower()
    if not lowered:
        return False
    return any(
        token in lowered
        for token in (
            "weiter",
            "weiter machen",
            "mach weiter",
            "naechster schritt",
            "nächster schritt",
            "next step",
            "und jetzt",
            "was jetzt",
            "setz fort",
            "fortsetzen",
            "ueberspring",
            "überspring",
        )
    )


def classify_meta_task(
    query: str,
    *,
    action_count: int = 0,
    conversation_state: Mapping[str, Any] | None = None,
    recent_user_turns: Iterable[str] | None = None,
    recent_assistant_turns: Iterable[str] | None = None,
    session_summary: str = "",
    topic_history: Iterable[Any] | None = None,
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

    # CCF3: Deictic Reference Resolver - bindet "dieses Problem", "eben",
    # "worueber hatte ich" an einen frischen Anker, bevor Frame/GDK
    # die Entscheidung trifft.
    from orchestration.deictic_reference_resolver import resolve_deictic_reference
    raw_query_text = str(query or "")
    last_user_raw = _extract_meta_followup_field(raw_query_text, "last_user")
    last_assistant_raw = _extract_meta_followup_field(raw_query_text, "last_assistant")
    pending_followup_prompt_raw = _extract_meta_followup_field(
        raw_query_text, "pending_followup_prompt"
    )
    open_loop_raw = _extract_meta_followup_field(
        raw_query_text, "conversation_state_open_loop"
    )
    next_step_raw = _extract_meta_followup_field(
        raw_query_text, "conversation_state_next_expected_step"
    )
    deictic_resolution = resolve_deictic_reference(
        query=effective_query,
        open_loop=open_loop_raw,
        pending_followup_prompt=pending_followup_prompt_raw,
        last_assistant=last_assistant_raw,
        last_user=last_user_raw,
        active_topic=active_topic,
        next_step=next_step_raw,
    ).to_dict()
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
    has_no_research_instruction = _has_any(current_normalized, _NO_RESEARCH_HINTS)
    has_broad_research = _has_any(current_normalized, _BROAD_RESEARCH_HINTS) and not has_no_research_instruction
    has_strict_research = _has_any(current_normalized, _STRICT_RESEARCH_HINTS) and not has_no_research_instruction
    has_claim_check = _has_any(current_normalized, _CLAIM_CHECK_HINTS) and not has_no_research_instruction
    has_legal_policy_research = _has_any(current_normalized, _LEGAL_POLICY_RESEARCH_HINTS)
    if has_claim_check and has_legal_policy_research:
        has_strict_research = True
    has_hard_research = _has_any(current_normalized, _HARD_RESEARCH_HINTS) and not has_no_research_instruction
    has_youtube_light = site_kind == "youtube" and _has_any(current_normalized, _YOUTUBE_LIGHT_HINTS)
    has_direct_youtube_url = site_kind == "youtube" and _has_direct_youtube_url(current_normalized)
    has_youtube_fact_check = site_kind == "youtube" and (
        _has_any(current_normalized, _YOUTUBE_FACT_CHECK_HINTS)
        or (has_direct_youtube_url and has_strict_research)
    )
    has_local_search = site_kind == "maps" and (
        _has_any(current_normalized, _LOCAL_SEARCH_HINTS) or is_location_local_query(current_normalized)
    ) and not has_route_request
    has_live_travel_plan_document = _looks_like_live_travel_plan_document_request(current_normalized)
    has_simple_live_lookup = (
        (
            _looks_like_simple_live_lookup_direct_query(current_normalized)
            or _looks_like_public_information_lookup_request(current_normalized)
            or has_live_travel_plan_document
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
                        *_SIMPLE_LIVE_LOOKUP_FRESHNESS_TOPICS,
                    )
                )
            )
        )
        and not has_no_research_instruction
        and not has_hard_research
        and not has_route_request
        and not has_local_search
        and site_kind not in {"youtube", "booking", "x", "linkedin", "outlook", "github_login"}
    )
    has_document = _has_any(current_normalized, _DOCUMENT_HINTS) or has_live_travel_plan_document
    has_local_file_transform = False
    has_local_document_analysis = False
    has_local_file_operation = False
    has_image_generation = _looks_like_image_generation_request(current_normalized)
    has_creative_text_optimization = _looks_like_creative_text_optimization_request(current_normalized)
    has_developer_troubleshooting = _looks_like_developer_troubleshooting_request(current_normalized)
    has_delivery = _has_any(current_normalized, _DELIVERY_HINTS)
    has_email_send = _looks_like_email_send_request(current_normalized)
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
        recent_user_turns=recent_user_turns,
        recent_assistant_turns=recent_assistant_turns,
        context_anchor_applied=context_anchor_applied,
    )
    turn_interpretation = interpret_turn(turn_input)
    carried_domain = str((conversation_state or {}).get("active_domain") or "").strip().lower()
    provisional_task_type = "single_lane"
    provisional_task_domain, _, _ = infer_meta_task_domain_hint(
        effective_query=effective_query,
        active_topic=active_topic,
        open_goal=open_goal,
        task_type=provisional_task_type,
        carried_domain=carried_domain,
    )
    meta_context_bundle, preference_memory_selection, historical_topic_selection = build_meta_context_bundle(
        raw_query=query,
        effective_query=effective_query,
        provisional_task_domain=provisional_task_domain,
        dialog_state=dialog_state,
        conversation_state=conversation_state,
        turn_understanding=turn_interpretation.to_dict(),
        session_summary=session_summary,
        recent_user_turns=recent_user_turns,
        recent_assistant_turns=recent_assistant_turns,
        topic_history=topic_history,
        topic_memory_hits=topic_memory_hits,
        preference_memory_hits=preference_memory_hits,
        semantic_recall_hits=semantic_recall_hits,
    )
    active_topic = meta_context_bundle.active_topic or active_topic
    open_goal = meta_context_bundle.active_goal or open_goal or meta_context_bundle.open_loop
    next_step = meta_context_bundle.next_expected_step or dialog_state.get("next_step")
    active_plan = dict((conversation_state or {}).get("active_plan") or {})
    if _looks_like_plan_resume_query(effective_query):
        plan_goal = str(active_plan.get("goal") or "").strip()
        plan_next_step = str(active_plan.get("next_step_title") or active_plan.get("goal") or "").strip()
        if plan_goal and not open_goal:
            open_goal = plan_goal
        if plan_next_step:
            next_step = plan_next_step
    local_file_transform_focus = " ".join(
        str(item or "")
        for item in (
            effective_query,
            active_topic,
            open_goal,
            next_step,
            context_anchor,
            (conversation_state or {}).get("active_topic"),
            (conversation_state or {}).get("active_goal"),
            (conversation_state or {}).get("open_loop"),
            (conversation_state or {}).get("next_expected_step"),
            dialog_state.get("active_topic"),
            dialog_state.get("open_goal"),
            dialog_state.get("next_step"),
        )
        if str(item or "").strip()
    )
    has_local_file_transform = _looks_like_local_file_transform_request(local_file_transform_focus)
    if has_local_file_transform:
        has_document = True
    has_local_document_analysis = _looks_like_local_document_analysis_request(local_file_transform_focus)
    if has_local_document_analysis:
        has_document = True
    has_local_file_operation = _looks_like_local_file_operation_request(local_file_transform_focus)
    has_direct_response_instruction = looks_like_direct_response_instruction(effective_query)
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

    if has_direct_response_instruction:
        recommended_chain = ["meta"]
        task_type = "single_lane"
        reason = "direct_response_instruction"
    elif has_developer_troubleshooting:
        required_capabilities.extend(["code_inspection", "debugging"])
        recommended_chain = ["meta", "developer"]
        task_type = "code_troubleshooting"
        reason = "developer_troubleshooting"
    elif has_system:
        required_capabilities.extend(["diagnostics"])
        recommended_chain = ["meta", "system"]
        task_type = "system_diagnosis"
        reason = "system_signals"
        if "systemctl" in normalized or "journalctl" in normalized or "sudo" in normalized:
            required_capabilities.append("terminal_execution")
            recommended_chain.append("shell")
    elif has_local_file_transform:
        required_capabilities.extend(["document_creation", "file_transform"])
        recommended_chain = ["meta", "document"]
        task_type = "document_generation"
        reason = "local_file_transform"
    elif has_local_document_analysis:
        required_capabilities.extend(["document_analysis", "file_read"])
        recommended_chain = ["meta", "document"]
        task_type = "document_analysis"
        reason = "local_document_analysis"
    elif has_email_send:
        required_capabilities.extend(["email", "message_delivery"])
        recommended_chain = ["meta", "executor"]
        task_type = "email_send"
        reason = "email_send_request"
    elif has_image_generation:
        required_capabilities.extend(["image_generation", "creative_generation"])
        recommended_chain = ["meta", "creative"]
        task_type = "image_generation"
        reason = "image_generation_request"
    elif has_creative_text_optimization:
        required_capabilities.extend(["creative_generation", "prompt_refinement"])
        recommended_chain = ["meta", "creative"]
        task_type = "creative_text_optimization"
        reason = "creative_text_optimization"
    elif has_local_file_operation:
        required_capabilities.extend(["terminal_execution", "file_operation"])
        recommended_chain = ["meta", "shell"]
        task_type = "file_operation"
        reason = "local_file_operation"
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
    elif has_claim_check and turn_interpretation.dominant_turn_type not in {"correction", "clarification"}:
        required_capabilities.extend(["content_extraction", "source_research", "fact_verification"])
        recommended_chain = ["meta", "research"]
        task_type = "knowledge_research"
        reason = "claim_verification"
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

    if has_document and task_type != "file_operation" and "document" not in required_capabilities:
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
        elif turn_interpretation.dominant_turn_type == "followup":
            recommended_chain = ["meta"]
            reason = "stateful_followup"
        else:
            recommended_chain = ["meta"] if ("und dann" in normalized or "danach" in normalized) else ["executor"]

    # Reihenfolge deduplizieren, ohne den Ablauf umzubauen.
    deduped_chain: List[str] = []
    for agent in recommended_chain:
        if agent not in deduped_chain:
            deduped_chain.append(agent)

    kernel_seed = build_general_decision_kernel(
        effective_query=effective_query,
        dominant_turn_type=turn_interpretation.dominant_turn_type,
        response_mode=turn_interpretation.response_mode,
        active_topic=active_topic,
        open_goal=str(open_goal or ""),
        next_step=str(next_step or ""),
        active_domain=str(meta_context_bundle.active_domain or carried_domain or provisional_task_domain or ""),
        has_active_plan=bool(active_plan),
        recent_user_turns=recent_user_turns,
        recent_assistant_turns=recent_assistant_turns,
        meta_request_frame=None,
        meta_interaction_mode=None,
    )
    advisory_constraint_summary = str(kernel_seed.constraint_summary or "").strip()
    if (
        advisory_constraint_summary
        and kernel_seed.turn_kind in {"constraint_update", "inform"}
        and kernel_seed.topic_family in {"travel", "advisory", "personal_productivity"}
    ):
        open_goal = advisory_constraint_summary
        next_step = advisory_constraint_summary
        if not str(active_topic or "").strip():
            active_topic = advisory_constraint_summary
    gdk_generic_task_types = {
        "single_lane",
        "general_task",
        "knowledge_research",
        "simple_live_lookup",
        "simple_live_lookup_document",
        "location_local_search",
    }
    kernel_turn_type = turn_interpretation.dominant_turn_type
    kernel_response_mode = turn_interpretation.response_mode
    if kernel_seed.turn_kind in {"resume", "constraint_update"} and kernel_turn_type not in {"followup", "correction"}:
        kernel_turn_type = "followup"
    if (
        kernel_seed.answer_ready
        and kernel_seed.interaction_mode == "think_partner"
        and kernel_turn_type not in {"followup", "correction"}
        and any(str(item or "").strip() for item in (active_topic, open_goal, next_step))
    ):
        kernel_turn_type = "followup"
    if (
        kernel_seed.turn_kind in {"resume", "constraint_update"}
        and kernel_response_mode
        not in {"resume_open_loop", "correct_previous_path", "acknowledge_and_store"}
    ):
        kernel_response_mode = "resume_open_loop"
    if (
        kernel_seed.turn_kind == "inform"
        and kernel_seed.answer_ready
        and kernel_seed.interaction_mode == "think_partner"
        and kernel_seed.topic_family in {"travel", "advisory", "personal_productivity"}
    ):
        kernel_response_mode = "summarize_state"
    low_confidence_controller = resolve_low_confidence_controller(
        kernel_seed.to_dict(),
        has_state_anchor=bool(active_topic or open_goal or next_step or active_plan),
    )
    # RCF2: Spezialrouten (youtube, location, knowledge_research) duerfen nicht
    # durch den Low-Confidence-Controller oder execution_permission=forbidden
    # auf single_lane gedrueckt werden. Controller begrenzt Execution, loescht
    # aber nicht die Route.
    _PROTECTED_TASK_TYPES = {
        "youtube_content_extraction",
        "youtube_light_research",
        "location_local_search",
        "knowledge_research",
        "document_analysis",
        "email_send",
        "image_generation",
        "creative_text_optimization",
        "code_troubleshooting",
        "web_content_extraction",
        "multi_stage_web_task",
        "ui_navigation",
    }
    _lookup_first_route = has_simple_live_lookup and kernel_turn_type not in {
        "approval_response",
        "auth_response",
        "followup",
        "handover_resume",
        "correction",
        "clarification",
        "behavior_instruction",
        "preference_update",
    }
    _is_protected_route = (
        task_type in _PROTECTED_TASK_TYPES
        or has_local_file_transform
        or has_local_document_analysis
        or has_email_send
        or has_image_generation
        or has_creative_text_optimization
        or has_developer_troubleshooting
        or has_local_file_operation
        or has_direct_response_instruction
        or _lookup_first_route
    )
    if low_confidence_controller.get("active"):
        if not _is_protected_route:
            deduped_chain = [
                str(item or "").strip()
                for item in (low_confidence_controller.get("recommended_agent_chain") or ["meta"])
                if str(item or "").strip()
            ] or ["meta"]
            controller_task_type = str(low_confidence_controller.get("task_type") or "").strip()
            task_type = controller_task_type or "single_lane"
            required_capabilities = []
        # acknowledge_and_store fuer behavior_instruction / preference_update
        # darf nicht ueberschrieben werden - sonst geht die Preference-Capture-
        # Pipeline kaputt, auch wenn der Kernel low confidence hat.
        if kernel_response_mode != "acknowledge_and_store":
            kernel_response_mode = (
                str(low_confidence_controller.get("response_mode") or "clarify_before_execute").strip()
                or "clarify_before_execute"
            )
        reason = f"gdk4:{low_confidence_controller.get('reason') or 'low_confidence_fail_small'}"
    elif kernel_seed.execution_permission == "forbidden":
        if not _is_protected_route:
            deduped_chain = ["meta"]
            if (
                task_type in gdk_generic_task_types
                or kernel_seed.turn_kind in {"think", "inform", "resume", "constraint_update", "clarify"}
            ):
                task_type = "single_lane"
        if not str(reason or "").strip() or str(reason or "").strip() in {
            "single_lane",
            "current_chain_satisfies_goal",
        }:
            reason = f"gdk:{kernel_seed.turn_kind}"
    elif kernel_seed.clarify_if_below_threshold and task_type in gdk_generic_task_types and not _is_protected_route:
        deduped_chain = ["meta"]
        task_type = "single_lane"
        # acknowledge_and_store fuer behavior_instruction / preference_update darf
        # nicht ueberschrieben werden - sonst geht die Preference-Capture-Pipeline kaputt.
        if kernel_response_mode != "acknowledge_and_store":
            kernel_response_mode = "clarify_before_execute"
            reason = "gdk:clarify_low_confidence"
    if has_local_file_transform and kernel_response_mode != "acknowledge_and_store":
        kernel_response_mode = "execute"
    if has_local_document_analysis and kernel_response_mode != "acknowledge_and_store":
        kernel_response_mode = "execute"
    if has_email_send and kernel_response_mode != "acknowledge_and_store":
        kernel_response_mode = "execute"
    if has_image_generation and kernel_response_mode != "acknowledge_and_store":
        kernel_response_mode = "execute"
    if has_creative_text_optimization and kernel_response_mode != "acknowledge_and_store":
        kernel_response_mode = "execute"
    if has_developer_troubleshooting and kernel_response_mode != "acknowledge_and_store":
        kernel_response_mode = "execute"
    if has_local_file_operation and kernel_response_mode != "acknowledge_and_store":
        kernel_response_mode = "execute"
    if (
        has_simple_live_lookup
        and kernel_response_mode != "acknowledge_and_store"
        and kernel_turn_type
        not in {
            "approval_response",
            "auth_response",
            "handover_resume",
            "correction",
            "clarification",
            "behavior_instruction",
            "preference_update",
        }
    ):
        kernel_response_mode = "execute"
    if has_direct_response_instruction and kernel_response_mode != "acknowledge_and_store":
        kernel_response_mode = "summarize_state"

    pre_policy_frame = build_meta_request_frame(
        effective_query=effective_query,
        dominant_turn_type=kernel_turn_type,
        response_mode=kernel_response_mode,
        answer_shape="",
        task_type=task_type,
        active_topic=active_topic,
        open_goal=str(open_goal or ""),
        next_step=str(next_step or ""),
        active_domain=str(meta_context_bundle.active_domain or carried_domain or provisional_task_domain or ""),
        recommended_agent_chain=tuple(deduped_chain),
        active_plan=active_plan,
    )
    admitted_context = apply_meta_request_frame_context_admission(
        pre_policy_frame.to_dict(),
        bundle=meta_context_bundle.to_dict(),
        preference_memory_selection=preference_memory_selection,
    )
    admitted_bundle = dict(admitted_context.get("meta_context_bundle") or {})
    meta_context_bundle = MetaContextBundle(
        schema_version=int(admitted_bundle.get("schema_version") or _META_CONTEXT_SCHEMA_VERSION),
        current_query=str(admitted_bundle.get("current_query") or ""),
        bundle_reason=str(admitted_bundle.get("bundle_reason") or "meta_context_rehydration"),
        active_topic=str(admitted_bundle.get("active_topic") or ""),
        active_goal=str(admitted_bundle.get("active_goal") or ""),
        active_domain=str(admitted_bundle.get("active_domain") or ""),
        open_loop=str(admitted_bundle.get("open_loop") or ""),
        next_expected_step=str(admitted_bundle.get("next_expected_step") or ""),
        turn_type=str(admitted_bundle.get("turn_type") or ""),
        response_mode=str(admitted_bundle.get("response_mode") or ""),
        context_slots=tuple(
            MetaContextSlot(
                slot=str(item.get("slot") or ""),
                priority=int(item.get("priority") or 0),
                content=str(item.get("content") or ""),
                source=str(item.get("source") or ""),
                evidence_class=str(
                    item.get("evidence_class") or classify_meta_context_slot(item.get("slot"))
                ),
            )
            for item in (admitted_bundle.get("context_slots") or [])
            if isinstance(item, Mapping)
        ),
        suppressed_context=tuple(
            dict(item)
            for item in (admitted_bundle.get("suppressed_context") or [])
            if isinstance(item, Mapping)
        ),
        confidence=float(admitted_bundle.get("confidence") or 0.0),
    )
    if (
        advisory_constraint_summary
        and kernel_seed.turn_kind in {"constraint_update", "inform"}
        and kernel_seed.topic_family in {"travel", "advisory", "personal_productivity"}
    ):
        rewritten_slots: List[MetaContextSlot] = []
        open_loop_rewritten = False
        for slot in meta_context_bundle.context_slots:
            if slot.slot == "open_loop":
                rewritten_slots.append(
                    MetaContextSlot(
                        slot="open_loop",
                        priority=slot.priority,
                        content=advisory_constraint_summary,
                        source="constraint_summary",
                        evidence_class="conversation_state",
                    )
                )
                open_loop_rewritten = True
            else:
                rewritten_slots.append(slot)
        if not open_loop_rewritten:
            rewritten_slots.append(
                MetaContextSlot(
                    slot="open_loop",
                    priority=max(1, len(rewritten_slots) + 1),
                    content=advisory_constraint_summary,
                    source="constraint_summary",
                    evidence_class="conversation_state",
                )
            )
        meta_context_bundle = MetaContextBundle(
            schema_version=meta_context_bundle.schema_version,
            current_query=meta_context_bundle.current_query,
            bundle_reason=meta_context_bundle.bundle_reason,
            active_topic=meta_context_bundle.active_topic or advisory_constraint_summary,
            active_goal=advisory_constraint_summary,
            active_domain=meta_context_bundle.active_domain,
            open_loop=advisory_constraint_summary,
            next_expected_step=advisory_constraint_summary,
            turn_type=meta_context_bundle.turn_type,
            response_mode=meta_context_bundle.response_mode,
            context_slots=tuple(rewritten_slots),
            suppressed_context=meta_context_bundle.suppressed_context,
            confidence=meta_context_bundle.confidence,
        )
    preference_memory_selection = dict(admitted_context.get("preference_memory_selection") or {})
    frame_routing = apply_meta_request_frame_routing(
        pre_policy_frame.to_dict(),
        task_type=task_type,
        recommended_chain=deduped_chain,
        reason=reason,
        required_capabilities=required_capabilities,
    )
    task_type = str(frame_routing.get("task_type") or task_type).strip() or task_type
    reason = str(frame_routing.get("reason") or reason).strip() or reason
    required_capabilities = [
        str(item or "").strip()
        for item in (frame_routing.get("required_capabilities") or required_capabilities)
        if str(item or "").strip()
    ]
    deduped_chain = [
        str(item or "").strip()
        for item in (frame_routing.get("recommended_agent_chain") or deduped_chain)
        if str(item or "").strip()
    ]

    policy_input = build_meta_policy_input(
        effective_query=effective_query,
        dominant_turn_type=kernel_turn_type,
        baseline_response_mode=kernel_response_mode,
        task_type=task_type,
        active_topic=active_topic,
        open_goal=str(open_goal or ""),
        next_step=str(next_step or ""),
        recommended_agent_chain=tuple(deduped_chain),
        meta_context_bundle=meta_context_bundle.to_dict(),
        preference_memory_selection=preference_memory_selection,
        topic_state_transition=topic_transition.to_dict(),
        meta_request_frame=pre_policy_frame.to_dict(),
    )
    policy_decision = resolve_meta_response_policy(policy_input)
    if (
        kernel_seed.answer_ready
        and kernel_seed.interaction_mode == "think_partner"
        and kernel_seed.topic_family in {"travel", "advisory", "personal_productivity"}
    ):
        policy_decision = MetaPolicyDecision(
            response_mode="summarize_state",
            policy_reason="general_decision_answer_ready",
            policy_confidence=max(kernel_seed.confidence, 0.84),
            answer_shape="direct_recommendation",
            should_delegate=False,
            should_store_preference=False,
            should_resume_open_loop=False,
            should_summarize_state=True,
            self_model_bound_applied=False,
            policy_signals=("general_decision_kernel_answer_ready",),
            override_applied=True,
            agent_chain_override=("meta",),
            task_type_override="single_lane",
            recipe_enabled=False,
        )
    final_task_type = task_type
    final_reason = reason
    final_chain = list(deduped_chain)
    final_response_mode = kernel_response_mode
    if policy_decision.override_applied:
        final_response_mode = policy_decision.response_mode
        policy_signals = tuple(str(item or "") for item in (policy_decision.policy_signals or ()))
        policy_reason = policy_decision.policy_reason
        if "next_step_summary_language" in policy_signals:
            policy_reason = "next_step_summary_request"
        elif "state_summary_language" in policy_signals:
            policy_reason = "state_summary_request"
        final_reason = f"meta_policy:{policy_reason}"
        if policy_decision.task_type_override:
            final_task_type = policy_decision.task_type_override
        if policy_decision.agent_chain_override:
            final_chain = list(policy_decision.agent_chain_override)
    if not final_chain:
        final_chain = ["meta"]

    meta_request_frame = build_meta_request_frame(
        effective_query=effective_query,
        dominant_turn_type=kernel_turn_type,
        response_mode=final_response_mode,
        answer_shape=policy_decision.answer_shape,
        task_type=final_task_type,
        active_topic=active_topic,
        open_goal=str(open_goal or ""),
        next_step=str(next_step or ""),
        active_domain=str(meta_context_bundle.active_domain or carried_domain or provisional_task_domain or ""),
        recommended_agent_chain=final_chain,
        active_plan=active_plan,
    )
    meta_interaction_mode = build_meta_interaction_mode(
        effective_query=effective_query,
        meta_request_frame=meta_request_frame.to_dict(),
        policy_decision=policy_decision.to_dict(),
    )
    if meta_interaction_mode.mode == "think_partner" and meta_interaction_mode.explicit_override:
        final_task_type = "single_lane"
        final_chain = ["meta"]
        final_reason = "interaction_mode:think_partner"
        final_response_mode = "summarize_state"
        meta_request_frame = build_meta_request_frame(
            effective_query=effective_query,
            dominant_turn_type=kernel_turn_type,
            response_mode=final_response_mode,
            answer_shape="direct_recommendation",
            task_type=final_task_type,
            active_topic=active_topic,
            open_goal=str(open_goal or ""),
            next_step=str(next_step or ""),
            active_domain=str(meta_context_bundle.active_domain or carried_domain or provisional_task_domain or ""),
            recommended_agent_chain=final_chain,
            active_plan=active_plan,
        )
        meta_interaction_mode = build_meta_interaction_mode(
            effective_query=effective_query,
            meta_request_frame=meta_request_frame.to_dict(),
            policy_decision={
                **policy_decision.to_dict(),
                "answer_shape": "direct_recommendation",
                "policy_reason": "explicit_think_partner_override",
            },
        )
    elif (
        meta_interaction_mode.mode == "inspect"
        and str(meta_request_frame.task_domain or "").strip().lower() == "setup_build"
    ):
        final_task_type = "setup_build_probe"
        final_chain = ["meta", "executor"]
        final_reason = "interaction_mode:inspect_setup_build_probe"
        final_response_mode = "execute"
        meta_request_frame = build_meta_request_frame(
            effective_query=effective_query,
            dominant_turn_type=kernel_turn_type,
            response_mode=final_response_mode,
            answer_shape=policy_decision.answer_shape,
            task_type=final_task_type,
            active_topic=active_topic,
            open_goal=str(open_goal or ""),
            next_step=str(next_step or ""),
            active_domain=str(meta_context_bundle.active_domain or carried_domain or provisional_task_domain or ""),
            recommended_agent_chain=final_chain,
            active_plan=active_plan,
        )
        meta_interaction_mode = build_meta_interaction_mode(
            effective_query=effective_query,
            meta_request_frame=meta_request_frame.to_dict(),
            policy_decision={
                **policy_decision.to_dict(),
                "policy_reason": "inspect_fast_path_setup_build",
            },
        )
        meta_interaction_mode = MetaInteractionMode(
            schema_version=1,
            mode="inspect",
            mode_reason="explicit_inspect_fast_path_setup_build",
            explicit_override=True,
            answer_style="report_findings",
            execution_policy="bounded_evidence_only",
            completion_expectation="existing_preparations_or_gap_named",
        )
    elif (
        meta_interaction_mode.mode == "assist"
        and str(meta_request_frame.task_domain or "").strip().lower() == "setup_build"
    ):
        final_task_type = "setup_build_execution"
        final_chain = ["meta", "executor"]
        final_reason = "interaction_mode:assist_setup_build_execution"
        final_response_mode = "execute"
        meta_request_frame = build_meta_request_frame(
            effective_query=effective_query,
            dominant_turn_type=kernel_turn_type,
            response_mode=final_response_mode,
            answer_shape=policy_decision.answer_shape,
            task_type=final_task_type,
            active_topic=active_topic,
            open_goal=str(open_goal or ""),
            next_step=str(next_step or ""),
            active_domain=str(meta_context_bundle.active_domain or carried_domain or provisional_task_domain or ""),
            recommended_agent_chain=final_chain,
            active_plan=active_plan,
        )
        meta_interaction_mode = build_meta_interaction_mode(
            effective_query=effective_query,
            meta_request_frame=meta_request_frame.to_dict(),
            policy_decision={
                **policy_decision.to_dict(),
                "policy_reason": "assist_fast_path_setup_build_execution",
            },
        )

    if (
        meta_interaction_mode.mode == "inspect"
        and final_response_mode == "execute"
        and final_task_type in {"simple_live_lookup", "simple_live_lookup_document"}
        and len(final_chain) >= 2
        and final_chain[:2] == ["meta", "executor"]
    ):
        meta_interaction_mode = MetaInteractionMode(
            schema_version=1,
            mode="assist",
            mode_reason=f"executable_lookup_route:{final_task_type}",
            explicit_override=False,
            answer_style="action_or_plan",
            execution_policy="plan_delegate_or_execute",
            completion_expectation="concrete_next_action_or_result",
        )

    if (
        kernel_seed.confidence >= 0.7
        and kernel_seed.interaction_mode != meta_interaction_mode.mode
        and not has_local_file_transform
        and not has_local_document_analysis
        and not has_email_send
        and not has_image_generation
        and not has_creative_text_optimization
        and not has_developer_troubleshooting
        and final_task_type
        not in {
            "file_operation",
            "simple_live_lookup",
            "simple_live_lookup_document",
            "document_analysis",
            "email_send",
            "image_generation",
            "creative_text_optimization",
            "code_troubleshooting",
        }
    ):
        if kernel_seed.interaction_mode == "think_partner":
            meta_interaction_mode = MetaInteractionMode(
                schema_version=1,
                mode="think_partner",
                mode_reason=f"general_decision_kernel:{kernel_seed.turn_kind}",
                explicit_override=False,
                answer_style="reason_with_user",
                execution_policy="no_research_no_execution",
                completion_expectation="insight_or_options_given",
            )
            if final_chain != ["meta"]:
                final_chain = ["meta"]
        elif kernel_seed.interaction_mode == "inspect":
            meta_interaction_mode = MetaInteractionMode(
                schema_version=1,
                mode="inspect",
                mode_reason=f"general_decision_kernel:{kernel_seed.turn_kind}",
                explicit_override=False,
                answer_style="report_findings",
                execution_policy="bounded_evidence_only",
                completion_expectation="findings_or_gaps_reported",
            )
        elif kernel_seed.interaction_mode == "assist":
            meta_interaction_mode = MetaInteractionMode(
                schema_version=1,
                mode="assist",
                mode_reason=f"general_decision_kernel:{kernel_seed.turn_kind}",
                explicit_override=False,
                answer_style="action_or_plan",
                execution_policy="plan_delegate_or_execute",
                completion_expectation="concrete_next_action_or_result",
            )

    meta_request_frame = _align_meta_frame_to_reason_domain(
        meta_request_frame=meta_request_frame,
        final_reason=final_reason,
        effective_query=effective_query,
        dominant_turn_type=kernel_turn_type,
        final_response_mode=final_response_mode,
        answer_shape=policy_decision.answer_shape,
        final_task_type=final_task_type,
        active_topic=active_topic,
        open_goal=str(open_goal or ""),
        next_step=str(next_step or ""),
        active_domain=str(meta_context_bundle.active_domain or carried_domain or provisional_task_domain or ""),
        final_chain=final_chain,
        active_plan=active_plan,
    )
    if str(final_reason or "").startswith("gdk:") and str(meta_request_frame.task_domain or "").strip().lower() not in {
        "",
        "topic_advisory",
        "general_task",
    }:
        final_reason = f"frame:{str(meta_request_frame.task_domain or '').strip().lower()}"

    prefer_youtube_research_only = (
        final_task_type == "youtube_content_extraction"
        and has_direct_youtube_url
        and has_youtube_fact_check
        and not has_browser
    )
    recipe = resolve_orchestration_recipe(final_task_type, site_kind) if policy_decision.recipe_enabled else None
    alternatives = (
        resolve_orchestration_alternative_recipes(final_task_type, site_kind)
        if policy_decision.recipe_enabled
        else []
    )
    if prefer_youtube_research_only:
        preferred_recipe = _build_recipe_payload("youtube_research_only")
        if preferred_recipe:
            recipe = preferred_recipe
            alternatives = []
            for candidate_id in ("youtube_content_extraction", "youtube_search_then_visual"):
                payload = _build_recipe_payload(candidate_id)
                if payload and payload["recipe_id"] != preferred_recipe["recipe_id"]:
                    alternatives.append(payload)
    plan_handoff_payload = {
        "task_type": final_task_type,
        "site_kind": site_kind,
        "response_mode": final_response_mode,
        "required_capabilities": sorted(set(required_capabilities)),
        "recommended_agent_chain": final_chain,
        "frame_kind": meta_request_frame.frame_kind,
        "frame_task_domain": meta_request_frame.task_domain,
        "frame_execution_mode": meta_request_frame.execution_mode,
        "frame_completion_contract": meta_request_frame.completion_contract,
        "recommended_recipe_id": None if not recipe else recipe["recipe_id"],
        "recipe_stages": [] if not recipe else recipe["recipe_stages"],
        "recipe_recoveries": [] if not recipe else recipe.get("recipe_recoveries", []),
    }
    task_decomposition = build_task_decomposition(
        source_query=effective_query,
        orchestration_policy=plan_handoff_payload,
    )
    if active_plan and _looks_like_plan_resume_query(effective_query):
        task_decomposition["planning_needed"] = True
        task_decomposition["planning_reason"] = "resume_active_plan"
        if str(active_plan.get("goal") or "").strip():
            task_decomposition["goal"] = str(active_plan.get("goal") or "").strip()
    if meta_request_frame.execution_mode == "answer_directly":
        task_decomposition["intent_family"] = "single_step"
        task_decomposition["planning_needed"] = False
        task_decomposition["planning_reason"] = "frame_answer_directly"
        task_decomposition["goal_satisfaction_mode"] = "answer_or_artifact_ready"
        task_decomposition["subtasks"] = [
            {
                "id": "respond",
                "title": "Direkt auf die Anfrage antworten",
                "kind": "response",
                "status": "pending",
                "depends_on": [],
                "optional": False,
                "completion_signals": ["answer_delivered"],
            }
        ]
        task_decomposition["completion_signals"] = ["answer_delivered"]
    meta_execution_plan = build_meta_execution_plan(
        source_query=effective_query,
        handoff_payload=plan_handoff_payload,
        task_decomposition=task_decomposition,
    )
    if active_plan and _looks_like_plan_resume_query(effective_query):
        if str(active_plan.get("plan_id") or "").strip():
            meta_execution_plan["plan_id"] = str(active_plan.get("plan_id") or "").strip()
        if str(active_plan.get("goal") or "").strip():
            meta_execution_plan["goal"] = str(active_plan.get("goal") or "").strip()
        if str(active_plan.get("plan_mode") or "").strip():
            meta_execution_plan["plan_mode"] = str(active_plan.get("plan_mode") or "").strip()
        if str(active_plan.get("next_step_id") or "").strip():
            meta_execution_plan["next_step_id"] = str(active_plan.get("next_step_id") or "").strip()
        if not any(
            str(step.get("id") or "").strip() == str(active_plan.get("next_step_id") or "").strip()
            for step in (meta_execution_plan.get("steps") or [])
            if isinstance(step, dict)
        ) and str(active_plan.get("next_step_id") or "").strip():
            meta_execution_plan["steps"] = [
                {
                    "id": str(active_plan.get("next_step_id") or "").strip(),
                    "title": str(active_plan.get("next_step_title") or active_plan.get("goal") or "").strip(),
                    "step_kind": "resume",
                    "assigned_agent": str(active_plan.get("next_step_agent") or "meta").strip().lower() or "meta",
                    "status": "pending",
                    "depends_on": [],
                    "optional": False,
                    "completion_signals": ["step_completed"],
                    "recipe_stage_id": "",
                    "expected_output": "",
                    "source_subtask_id": "",
                    "delegation_mode": "resume_active_plan",
                },
                *list(meta_execution_plan.get("steps") or []),
            ]
    if meta_request_frame.execution_mode == "answer_directly":
        meta_execution_plan["plan_mode"] = "direct_response"
        meta_execution_plan["intent_family"] = "single_step"
        meta_execution_plan["planning_needed"] = False
        meta_execution_plan["summary"] = "direct_response ueber 1 Schritt fuer single_step"
        meta_execution_plan["steps"] = [
            {
                "id": "plan_respond",
                "title": "Direkt auf die Anfrage antworten",
                "step_kind": "response",
                "assigned_agent": "meta",
                "status": "pending",
                "depends_on": [],
                "optional": False,
                "completion_signals": ["answer_delivered"],
                "recipe_stage_id": "",
                "expected_output": "",
                "source_subtask_id": "respond",
                "delegation_mode": "meta_only",
            }
        ]
        meta_execution_plan["next_step_id"] = "plan_respond"
        meta_execution_plan["status"] = "active"
    clarity_contract = build_meta_clarity_contract(
        effective_query=effective_query,
        response_mode=final_response_mode,
        policy_decision=policy_decision.to_dict(),
        interaction_mode=meta_interaction_mode.to_dict(),
        task_type=final_task_type,
        goal_spec={},
        task_decomposition=task_decomposition,
        meta_execution_plan=meta_execution_plan,
    )
    authoritative_context = _build_authoritative_meta_context_view(
        meta_request_frame=meta_request_frame.to_dict(),
        clarity_contract=clarity_contract.to_dict(),
        meta_context_bundle=meta_context_bundle.to_dict(),
        preference_memory_selection=preference_memory_selection,
    )
    filtered_meta_context_bundle = dict(authoritative_context.get("meta_context_bundle") or {})
    preference_memory_selection = dict(authoritative_context.get("preference_memory_selection") or {})
    specialist_context_seed = _build_authoritative_specialist_context_seed(
        meta_context_bundle=filtered_meta_context_bundle,
        preference_memory_selection=preference_memory_selection,
        conversation_state=conversation_state,
        clarity_contract=clarity_contract.to_dict(),
        turn_type=turn_interpretation.dominant_turn_type,
        response_mode=final_response_mode,
    )
    general_decision_kernel = build_general_decision_kernel(
        effective_query=effective_query,
        dominant_turn_type=kernel_turn_type,
        response_mode=final_response_mode,
        active_topic=active_topic,
        open_goal=str(open_goal or ""),
        next_step=str(next_step or ""),
        active_domain=str(meta_request_frame.task_domain or meta_context_bundle.active_domain or carried_domain or provisional_task_domain or ""),
        has_active_plan=bool(active_plan),
        recent_user_turns=recent_user_turns,
        recent_assistant_turns=recent_assistant_turns,
        meta_request_frame=meta_request_frame.to_dict(),
        meta_interaction_mode=meta_interaction_mode.to_dict(),
    )
    low_confidence_controller = resolve_low_confidence_controller(
        general_decision_kernel.to_dict(),
        has_state_anchor=bool(active_topic or open_goal or next_step or active_plan),
    )
    if not low_confidence_controller.get("active") and str(final_reason or "").startswith("gdk4:"):
        final_reason = f"frame:{str(meta_request_frame.task_domain or final_task_type or 'single_lane').strip().lower()}"
    elif low_confidence_controller.get("active"):
        final_reason = f"gdk4:{low_confidence_controller.get('reason') or 'low_confidence_fail_small'}"
    resolved_dominant_turn_type = turn_interpretation.dominant_turn_type
    if (
        resolved_dominant_turn_type
        not in {"correction", "behavior_instruction", "approval_response", "auth_response", "handover_resume"}
        and kernel_turn_type == "followup"
    ):
        resolved_dominant_turn_type = "followup"
    resolved_active_domain = (
        str(meta_request_frame.task_domain or meta_context_bundle.active_domain or provisional_task_domain or "").strip()
        or None
    )
    if resolved_active_domain:
        filtered_meta_context_bundle["active_domain"] = resolved_active_domain

    classification = {
        "task_type": final_task_type,
        "site_kind": site_kind,
        "required_capabilities": sorted(set(required_capabilities)),
        "recommended_entry_agent": final_chain[0],
        "recommended_agent_chain": final_chain,
        "needs_structured_handoff": len(final_chain) > 1,
        "reason": final_reason,
        "recommended_recipe_id": None if not recipe else recipe["recipe_id"],
        "recipe_stages": [] if not recipe else recipe["recipe_stages"],
        "recipe_recoveries": [] if not recipe else recipe.get("recipe_recoveries", []),
        "alternative_recipes": alternatives,
        "effective_query": effective_query,
        "context_anchor": context_anchor or None,
        "context_anchor_applied": context_anchor_applied,
        "deictic_reference": deictic_resolution,
        "active_topic": active_topic or None,
        "open_goal": open_goal or None,
        "active_domain": resolved_active_domain,
        "dialog_constraints": dialog_constraints,
        "next_step": next_step,
        "active_topic_reused": active_topic_reused,
        "compressed_followup_parsed": compressed_followup_parsed,
        "dominant_turn_type": resolved_dominant_turn_type,
        "turn_signals": list(turn_interpretation.turn_signals),
        "response_mode": final_response_mode,
        "state_effects": turn_interpretation.state_effects.to_dict(),
        "turn_understanding": turn_interpretation.to_dict(),
        "task_decomposition": task_decomposition,
        "meta_execution_plan": meta_execution_plan,
        "meta_policy_decision": policy_decision.to_dict(),
        "meta_request_frame": meta_request_frame.to_dict(),
        "meta_interaction_mode": meta_interaction_mode.to_dict(),
        "general_decision_kernel": general_decision_kernel.to_dict(),
        "low_confidence_controller": low_confidence_controller,
        "topic_shift_detected": topic_transition.topic_shift_detected,
        "topic_state_transition": topic_transition.to_dict(),
        "meta_context_bundle": filtered_meta_context_bundle,
        "preference_memory_selection": preference_memory_selection,
        "historical_topic_selection": historical_topic_selection,
        "specialist_context_seed": specialist_context_seed,
        "meta_context_slot_types": [
            str(item.get("slot") or "").strip()
            for item in (filtered_meta_context_bundle.get("context_slots") or [])
            if str(item.get("slot") or "").strip()
        ],
        "meta_context_suppressed_count": len(filtered_meta_context_bundle.get("suppressed_context") or []),
    }
    classification = _apply_semantic_review_override(classification, semantic_review)
    classification = _apply_turn_understanding_override(classification, turn_interpretation)
    classification.update(semantic_review)
    goal_spec = derive_goal_spec(query, classification)
    clarity_contract = build_meta_clarity_contract(
        effective_query=effective_query,
        response_mode=final_response_mode,
        policy_decision=policy_decision.to_dict(),
        interaction_mode=meta_interaction_mode.to_dict(),
        task_type=final_task_type,
        goal_spec=goal_spec,
        task_decomposition=task_decomposition,
        meta_execution_plan=meta_execution_plan,
    )
    capability_graph = build_capability_graph(
        goal_spec,
        get_agent_capability_map(),
        current_chain=final_chain,
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
    _is_session_followup = bool(
        compressed_followup_parsed
        or active_topic_reused
        or resolved_dominant_turn_type == "followup"
    )
    # CCF4: Personal Assessment Gate - erkennt explizite Personalisierungsanfrage
    from orchestration.personal_assessment_gate import detect_personal_assessment
    _personal_gate = detect_personal_assessment(effective_query).to_dict()
    _is_personal_assessment = bool(_personal_gate.get("is_personal_assessment"))
    meta_context_authority = build_meta_context_authority(
        meta_request_frame=meta_request_frame.to_dict(),
        meta_interaction_mode=meta_interaction_mode.to_dict(),
        meta_clarity_contract=clarity_contract.to_dict(),
        meta_context_bundle=filtered_meta_context_bundle,
        general_decision_kernel=general_decision_kernel.to_dict(),
        is_session_followup=_is_session_followup,
        is_personal_assessment=_is_personal_assessment,
    )
    return {
        **classification,
        "goal_spec": goal_spec,
        "meta_clarity_contract": clarity_contract.to_dict(),
        "meta_context_authority": meta_context_authority.to_dict(),
        "personal_assessment_gate": _personal_gate,
        "capability_graph": capability_graph,
        "learned_chain_stats": learned_chain_stats,
        "adaptive_plan": adaptive_plan,
    }

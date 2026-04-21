"""BaseAgent Klasse mit Multi-Provider Support.

Enthaelt die Basisklasse fuer alle Timus-Agenten mit:
- Multi-Provider LLM Calls
- Loop-Detection
- Screen-Change-Gate
- ROI Management
- Strukturierte Navigation
- Post-Task Reflection (v2.0)
"""

import logging
import os
import json
import asyncio
import base64
import re
import subprocess
import platform
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Callable

import httpx

from agent.providers import (
    ModelProvider,
    AgentModelConfig,
    get_provider_client,
    resolve_model_provider_env,
)
from agent.shared.mcp_client import MCPClient
from agent.shared.screenshot import capture_screenshot_base64
from agent.shared.action_parser import parse_action
from agent.shared.vision_formatter import build_openai_vision_message
from agent.shared.json_utils import extract_json_robust
from agent.shared.delegation_handoff import parse_delegation_handoff

from utils.openai_compat import prepare_openai_params
from utils.policy_gate import (
    audit_policy_decision,
    evaluate_policy_gate,
)
from agent.dynamic_tool_mixin import DynamicToolMixin
from tools.tool_registry_v2 import registry_v2, ValidationError
from orchestration.lane_manager import lane_manager, Lane, LaneStatus
from orchestration.meta_clarity_contract import (
    filter_working_memory_context,
    parse_meta_clarity_contract,
)
from orchestration.llm_budget_guard import (
    BudgetModelOverride,
    LLMBudgetDecision,
    evaluate_llm_budget,
    resolve_soft_budget_model_override,
)
from orchestration.self_improvement_engine import LLMUsageRecord, ToolUsageRecord, get_improvement_engine
from utils.context_guard import ContextGuard, ContextStatus
from utils.dashscope_native import (
    build_dashscope_native_payload,
    dashscope_native_generation_url,
    extract_dashscope_native_reasoning,
    extract_dashscope_native_text,
)
from utils.headless_service_guard import desktop_open_block_reason
from utils.llm_usage import build_usage_payload

log = logging.getLogger("TimusAgent-v4.4")

MCP_URL = "http://127.0.0.1:5000"
IMAGE_MODEL_NAME = os.getenv("IMAGE_GENERATION_MODEL", "gpt-image-1.5-2025-12-16")
_RESTART_INTENT_KEYWORDS = (
    "restart",
    "neustart",
    "neu starten",
    "wieder hoch",
    "hochfahren",
    "bring zurueck",
    "bring zurück",
)
_RESTART_TARGET_PATTERN = re.compile(
    r"\b(timus|mcp|dispatcher|server|dienst|service)\b"
)
_RESTART_VERB_PATTERN = re.compile(
    r"\b(restart|neustart|neu starten|starte|starten|fahre|fahr|bringe|bring)\b"
)
_RESTART_QUALIFIER_PATTERN = re.compile(
    r"\b(neu|wieder|erneut|hoch|zurueck|zurück)\b"
)
_META_DOC_STATUS_PATTERNS = (
    "docs/",
    "changelog",
    "phase_",
    "phase ",
    "plan.md",
    "naechstes ansteht",
    "nächstes ansteht",
    "next step",
    "wo stehen wir",
    "status",
)
_META_SETUP_BUILD_PATTERNS = (
    "twilio",
    "inworld",
    "anruffunktion",
    "einrichten",
    "setup",
    "konfigurier",
    "integration",
    "verbinde",
    "api key",
    "lennart",
)
_META_MIGRATION_WORK_PATTERNS = (
    "kanada",
    "canada",
    "auswand",
    "einwander",
    "visa",
    "visum",
    "arbeiten",
    "arbeit",
    "job",
    "beruf",
    "fuss fassen",
    "fuß fassen",
    "leben aufbauen",
)
_META_RESEARCH_ADVISORY_PATTERNS = (
    "mach dich schlau ueber",
    "mach dich schlau über",
    "informier dich ueber",
    "informier dich über",
    "lies dich in",
    "arbeite dich in",
    "recherchiere ueber",
    "recherchiere über",
    "recherchiere zu",
    "hilf mir dann",
    "und hilf mir dann",
    "steh mir hilfreich zur seite",
    "steh mir hilfreich zur Seite",
    "hilfreich zur seite",
    "hilfreich zur Seite",
)
_META_LOCATION_ROUTE_PATTERNS = (
    "route",
    "weg nach",
    "anfahrt",
    "anfahrt",
    "maps",
    "google maps",
    "travel_mode",
    "destination_query",
    "mit dem auto",
    "driving",
    "offenbach",
    "münster",
    "muenster",
)
_META_SKILL_RESPONSE_PATTERNS = (
    "skill-creator",
    "skill creator",
    "run_skill(",
    "meta-skill",
    "meta skill",
    "verfuegbare skills",
    "verfügbare skills",
    "skill-struktur",
    "skill struktur",
    "skill-architektur",
    "skill architektur",
    "improvement-workflow",
)
_META_GENERIC_HELP_PATTERNS = (
    "ich sehe hier einen meta orchestration handoff",
    "ich sehe zwar den system-kontext",
    "ich sehe, dass du mich aufgerufen hast",
    "ich sehe, dass der system-kontext geladen wurde",
    "mir fehlt die konkrete benutzeranfrage",
    "deine eigentliche nachricht oder frage fehlt",
    "du hast mir aber noch keine konkrete frage oder aufgabe gestellt",
    "was moechtest du?",
    "was möchtest du?",
    "was moechtest du bauen oder einrichten",
    "was möchtest du bauen oder einrichten",
    "was kann ich fuer dich tun",
    "was kann ich für dich tun",
    "sag mir, was du brauchst",
    "schnelluebersicht was ich tun kann",
)
_META_FILE_READ_METHODS = {
    "read_file",
    "read_text_file",
    "get_text",
    "fetch_url",
}
_META_LOCATION_METHODS = {
    "get_google_maps_route",
    "search_google_maps_places",
    "get_current_location",
    "get_live_location_context",
}


AGENT_CAPABILITY_MAP = {
    # ── Bestehende Agenten (praezisiert) ─────────────────────────────
    "executor": [
        "search", "web",                         # Websuche
        "social_media", "fetch",                 # Social-Media + JS-Seiten (ScrapingAnt)
        "file", "filesystem", "results",         # Dateien + Speichern
        "memory",                                # Kontext
        "voice", "speech",                       # Sprachausgabe
        "document", "pdf", "txt", "summarize",  # Einfache Dokumente
        "tasks", "planning", "automation",       # Aufgaben-Verwaltung
        "analysis", "data",                      # Basisanalyse + CSV/XLSX lesen
    ],
    "research": [
        "search", "web", "deep_research",        # Suche + Tiefenrecherche
        "document", "report", "summarize",       # Ausgabe + Zusammenfassung
        "memory",                                # Kontext
        "analysis", "fact_check", "verification",# Verifikation
        "file", "results",                       # Speichern
    ],
    "reasoning": [
        # Kein "research" / "deep_research" — verhindert dass start_deep_research
        # in der Tool-Liste des Reasoning-Agenten auftaucht. Delegation via Prompt.
        "search", "web",                         # einfache Websuche (search_web)
        "document", "report",                    # Ausgabe
        "memory",                                # Kontext
        "code", "development",                   # Code-Analyse
        "analysis", "fact_check", "verification",# Pruefung
        "file", "results",                       # Speichern
    ],
    "creative": [
        "creative", "image",                     # Bild-Erstellung
        "document", "txt", "pdf",               # Text-Ausgabe
        "voice", "speech",                       # Sprachausgabe
        "file", "results",                       # Speichern
        "memory",                                # Kontext
    ],
    "meta": [
        "meta", "orchestration",                 # Orchestrierung + delegation_tool
        "planning", "automation", "tasks",       # Workflow-Planung
        "memory", "reflection", "curation",     # Kontext + Lernen
        "skills",                               # Skill-Verwaltung
        # Meta ist Orchestrator, kein Spezialist:
        # keine Search-/Document-/File-/System-Caps, damit Fach-Tools gar nicht
        # erst im normalen Tool-Sichtfeld auftauchen.
    ],
    "visual": [
        "browser", "dom", "navigation",         # Browser-Steuerung
        "interaction", "mouse", "feedback",     # Maus + Tastatur
        "vision", "ocr", "grounding",          # Bilderkennung
        "ui", "ui_detection", "screen",        # UI-Elemente
        "som", "detection", "segmentation",    # Objekt-Erkennung
        "annotation", "template_matching",      # Matching
        "opencv", "verification", "fallback",   # Fallback-Erkennung
        "automation", "application",            # Apps + Automatisierung
        "adaptive", "timing",                   # Timing-Anpassung
        "memory", "results",                    # Kontext + Speichern
        "fetch", "http",                        # Web-Fetch (JS-Seiten via Playwright)
    ],
    "development": [
        "code", "development", "inception",     # Code schreiben + Inception-API
        "file", "filesystem",                   # Dateizugriff
        "search", "web",                        # Recherche
        "memory", "results",                    # Kontext + Speichern
        "analysis", "debug",                    # Analyse + Debugging
    ],
    # ── M1: Daten + Dokumente ─────────────────────────────────────────
    "data": [
        "data",                                 # data_tool (read_data_file, analyze_data)
        "file", "filesystem",                   # Dateizugriff
        "document", "pdf", "xlsx", "csv",      # Ausgabe-Formate
        "analysis", "fact_check",              # Analyse
        "results", "report",                   # Speichern
        "memory",                              # Kontext
        "fetch", "http",                        # Web-Fetch (CSV/JSON von URLs laden)
    ],
    "document": [
        "document", "pdf", "docx",             # Haupt-Ausgabe-Formate
        "xlsx", "csv", "txt",                  # Tabellen + Plaintext
        "file", "filesystem",                  # Dateizugriff
        "results", "report",                   # Speichern
        "memory",                              # Kontext
        "analysis",                            # Inhaltspruefung
    ],
    # ── M2: Kommunikation ─────────────────────────────────────────────
    "communication": [
        "communication", "email",               # E-Mail lesen/senden + Status
        "send_email", "read_emails", "status", # explizite Mail-Tool-Caps
        "document", "txt", "docx",             # Ausgabe (Briefe, Anschreiben)
        "file", "filesystem",                  # Dateizugriff
        "results",                             # Speichern
        "memory",                              # Kontext (Fatih-Profil)
    ],
    # ── M3: System-Monitor ────────────────────────────────────────────
    "system": [
        "system", "monitoring",               # system_tool + system_monitor_tool
    ],
    # ── M4: Shell-Operator ────────────────────────────────────────────
    "shell": [
        "shell",                              # shell_tool (alle 5 Funktionen)
    ],
}


class BaseAgent(DynamicToolMixin):
    """Basisklasse fuer alle Agenten mit Multi-Provider Support und DynamicToolMixin."""

    @staticmethod
    def _resolve_env_float(name: str, default: float) -> float:
        raw = str(os.getenv(name, str(default))).strip()
        try:
            return float(raw)
        except ValueError:
            return float(default)

    @classmethod
    def _resolve_tool_http_timeout(cls, method: str, params: dict) -> float:
        base_timeout = cls._resolve_env_float("MCP_TOOL_HTTP_TIMEOUT", 300.0)
        research_timeout = cls._resolve_env_float("RESEARCH_TIMEOUT", 600.0)
        research_buffer = max(
            0.0,
            cls._resolve_env_float("MCP_RESEARCH_HTTP_TIMEOUT_BUFFER_SECONDS", 30.0),
        )

        if method in {"start_deep_research", "generate_research_report"}:
            return max(base_timeout, research_timeout + research_buffer)

        if method == "delegate_to_agent":
            target_agent = str((params or {}).get("agent_type") or "").strip().lower()
            if target_agent == "research":
                return max(base_timeout, research_timeout + research_buffer)

        return base_timeout

    @staticmethod
    def _resolve_model_without_validation(agent_type: str) -> Tuple[str, ModelProvider]:
        if agent_type in AgentModelConfig.AGENT_CONFIGS:
            model_env, provider_env, fallback_model, fallback_provider = AgentModelConfig.AGENT_CONFIGS[agent_type]
            return resolve_model_provider_env(
                model_env=model_env,
                provider_env=provider_env,
                fallback_model=fallback_model,
                fallback_provider=fallback_provider,
            )
        return "gpt-4o", ModelProvider.OPENAI

    @staticmethod
    def _resolve_fallback_model_without_validation(agent_type: str) -> Optional[Tuple[str, ModelProvider]]:
        if agent_type not in AgentModelConfig.AGENT_FALLBACK_CONFIGS:
            return None
        model_env, provider_env, fallback_model, fallback_provider = AgentModelConfig.AGENT_FALLBACK_CONFIGS[agent_type]
        return resolve_model_provider_env(
            model_env=model_env,
            provider_env=provider_env,
            fallback_model=fallback_model,
            fallback_provider=fallback_provider,
        )

    def __init__(
        self,
        system_prompt_template: str,
        tools_description_string: str,
        max_iterations: int = 30,
        agent_type: str = "executor",
        lane_id: Optional[str] = None,
        skip_model_validation: bool = False,
    ):
        self.max_iterations = max_iterations
        self.agent_type = agent_type
        self.lane_id = lane_id
        self._lane: Optional[Lane] = None

        # DynamicToolMixin initialisieren
        capabilities = AGENT_CAPABILITY_MAP.get(agent_type)
        self.init_dynamic_tools(
            capabilities=capabilities, max_iterations=max_iterations
        )
        self.http_client = httpx.AsyncClient(timeout=300.0)
        self.recent_actions: List[str] = []
        self.last_skip_times: Dict[str, float] = {}
        self.action_call_counts: Dict[str, int] = {}
        self._remote_tool_names: set[str] = set()
        self._remote_tools_fetched: bool = False
        self.conversation_session_id: Optional[str] = None
        self._bug_logger = None  # Lazy-Init: erst beim ersten Fehler

        # Multi-Provider Setup
        self.provider_client = get_provider_client()
        if skip_model_validation:
            self.model, self.provider = self._resolve_model_without_validation(agent_type)
            fallback = self._resolve_fallback_model_without_validation(agent_type)
            log.warning(
                "%s | %s | %s | Modellvalidierung absichtlich uebersprungen",
                self.__class__.__name__,
                self.model,
                self.provider.value,
            )
        else:
            self.model, self.provider = AgentModelConfig.get_model_and_provider(agent_type)
            fallback = AgentModelConfig.get_fallback_model_and_provider(agent_type)
        self.fallback_model: Optional[str] = None
        self.fallback_provider: Optional[ModelProvider] = None
        if fallback:
            fallback_model, fallback_provider = fallback
            if (fallback_model, fallback_provider) != (self.model, self.provider):
                self.fallback_model = fallback_model
                self.fallback_provider = fallback_provider

        log.info(f"{self.__class__.__name__} | {self.model} | {self.provider.value}")
        if self.fallback_model and self.fallback_provider:
            log.info(
                "%s | Fallback %s | %s",
                self.__class__.__name__,
                self.fallback_model,
                self.fallback_provider.value,
            )

        self.system_prompt = system_prompt_template.replace(
            "{current_date}", datetime.now().strftime("%d.%m.%Y")
        ).replace("{tools_description}", tools_description_string)

        # Lane-Manager initialisieren
        lane_manager.set_registry(registry_v2)

        # Screen-Change-Gate Support (v1.0)
        self.use_screen_change_gate = (
            os.getenv("USE_SCREEN_CHANGE_GATE", "false").lower() == "true"
        )
        self.cached_screen_state: Optional[Dict] = None
        self.last_screen_analysis_time: float = 0
        self._last_screen_check_time: float = 0.0

        # ROI (Region of Interest) Support (v2.0)
        self.roi_stack: List[Dict] = []
        self.current_roi: Optional[Dict] = None

        # Context-Window-Guard (v3.0)
        self._context_guard = ContextGuard(
            max_tokens=int(os.getenv('MAX_CONTEXT_TOKENS', '128000')),
            max_output_tokens=int(os.getenv('MAX_OUTPUT_TOKENS', '8000')),
        )

        # Multimodal Vision Support
        self._vision_enabled = False
        try:
            import mss as _mss
            from PIL import Image as _PILImage

            self._vision_enabled = True
        except ImportError:
            pass

        # Post-Task Reflection Support (v2.0)
        self._reflection_enabled = os.getenv("REFLECTION_ENABLED", "true").lower() == "true"
        self._reflection_engine = None
        self._task_action_history: List[Dict[str, Any]] = []
        self._working_memory_last_meta: Dict[str, Any] = {}
        self._memory_recall_last_meta: Dict[str, Any] = {}
        self._context_budget_last_meta: Dict[str, Any] = {}
        self._run_started_at: float = 0.0
        self._live_status_enabled = (
            os.getenv("TIMUS_LIVE_STATUS", "true").lower() in {"1", "true", "yes", "on"}
        )
        self._step_trace_enabled = (
            os.getenv("TIMUS_STEP_TRACE", "true").lower() in {"1", "true", "yes", "on"}
        )
        self._audit_step_logger: Optional[Callable[..., None]] = None
        self._active_phase = "idle"
        self._active_tool_name: Optional[str] = None
        self._current_task_text: str = ""

        if self.use_screen_change_gate:
            log.info(f"Screen-Change-Gate AKTIV fuer {self.__class__.__name__}")

    def _emit_live_status(
        self,
        phase: str,
        detail: str = "",
        step: Optional[int] = None,
        total_steps: Optional[int] = None,
        tool_name: Optional[str] = None,
    ) -> None:
        """Kompakte Live-Statusanzeige fuer Terminal-User."""
        self._active_phase = phase
        if tool_name is not None:
            self._active_tool_name = tool_name
        elif not phase.startswith("tool_"):
            # Nur waehrend Tool-Phasen einen aktiven Tool-Namen anzeigen.
            self._active_tool_name = None
        if not self._live_status_enabled:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        step_txt = ""
        if step is not None and total_steps is not None:
            step_txt = f" | Step {step}/{total_steps}"
        tool_txt = ""
        if self._active_tool_name:
            tool_txt = f" | Tool {self._active_tool_name}"
        detail_txt = f" | {detail}" if detail else ""
        print(
            f"   ⏱️ Status [{ts}] | Agent {self.agent_type.upper()} | {phase.upper()}{step_txt}{tool_txt}{detail_txt}"
        )

    def set_audit_step_logger(self, logger_fn: Optional[Callable[..., None]]) -> None:
        """Setzt einen optionalen JSONL-Step-Logger (z.B. AuditLogger.log_step)."""
        self._audit_step_logger = logger_fn

    def _preview_value(self, value: Any, limit: int = 500) -> str:
        """Kompakte, einzeilige Vorschau fuer Logs."""
        try:
            if isinstance(value, str):
                text = value
            else:
                text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
        text = text.replace("\n", "\\n")
        if len(text) > limit:
            return text[:limit] + "...<truncated>"
        return text

    def _emit_step_trace(
        self,
        action: str,
        input_data: Any = None,
        output_data: Any = None,
        status: str = "ok",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Schreibt feingranulare Run-Schritte ins Audit-JSONL (wenn aktiv)."""
        if not self._step_trace_enabled or not self._audit_step_logger:
            return
        try:
            self._audit_step_logger(
                action=action,
                input_data=input_data,
                output_data=output_data,
                status=status,
                metadata=metadata,
            )
        except Exception as e:
            log.debug(f"Step-Trace Logging fehlgeschlagen: {e}")

    # ------------------------------------------------------------------
    # Screenshot + Vision (delegiert an shared utilities)
    # ------------------------------------------------------------------

    def _capture_screenshot_base64(self) -> str:
        """Macht Screenshot und gibt Base64-String zurueck."""
        if not self._vision_enabled:
            return ""
        return capture_screenshot_base64(fmt="JPEG", quality=70)

    def _build_vision_message(self, text: str, screenshot_b64: str) -> dict:
        """Baut eine multimodale User-Message mit Text + Screenshot."""
        return build_openai_vision_message(text, screenshot_b64, detail="low")

    # ------------------------------------------------------------------
    # Observation Sanitizer
    # ------------------------------------------------------------------

    def _sanitize_observation(self, obs: Any) -> Any:
        if isinstance(obs, dict):
            clean = obs.copy()
            for k, v in clean.items():
                if isinstance(v, str) and len(v) > 500:
                    clean[k] = f"<{len(v)} chars>"
                elif isinstance(v, list) and len(v) > 10:
                    clean[k] = v[:10] + [f"... +{len(v) - 10}"]
            return clean
        elif isinstance(obs, str) and len(obs) > 2000:
            return obs[:2000] + "..."
        return obs

    def _compact_message_content_for_budget(self, content: Any, *, max_tokens: int) -> Any:
        if isinstance(content, str):
            return self._context_guard.compress(content, max_tokens=max_tokens)
        if isinstance(content, list):
            compacted: list[Any] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    normalized = dict(item)
                    normalized["text"] = self._context_guard.compress(
                        item["text"],
                        max_tokens=max_tokens,
                    )
                    compacted.append(normalized)
                else:
                    compacted.append(item)
            return compacted
        return content

    def _context_budget_message_cap(
        self,
        message: Dict[str, Any],
        *,
        index: int,
        total: int,
    ) -> int:
        role = str(message.get("role") or "").strip().lower()
        content = message.get("content", "")
        is_recent = index >= max(0, total - 4)
        default_cap = 900 if is_recent else 420
        if role == "assistant":
            default_cap = 700 if is_recent else 320
        if isinstance(content, str) and content.startswith("Observation:"):
            default_cap = min(
                default_cap,
                max(120, int(os.getenv("AGENT_OBSERVATION_HISTORY_MAX_TOKENS", "320"))),
            )
        elif isinstance(content, str) and content.startswith("Fehler:"):
            default_cap = min(default_cap, 220)
        return max(120, default_cap)

    def _build_context_budget_summary_message(
        self,
        middle_messages: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not middle_messages:
            return None
        lines = ["Frueherer Verlauf komprimiert:"]
        for msg in middle_messages[-8:]:
            role = str(msg.get("role") or "user").strip().lower() or "user"
            preview = self._preview_value(msg.get("content", ""), 160)
            if preview:
                lines.append(f"- {role}: {preview}")
        summary_text = "\n".join(lines)
        return {
            "role": "system",
            "content": self._context_guard.compress(
                summary_text,
                max_tokens=max(160, int(os.getenv("AGENT_CONTEXT_SUMMARY_MAX_TOKENS", "320"))),
            ),
        }

    def _enforce_context_budget(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        status = self._context_guard.get_status(messages)
        initial_status = status.value if isinstance(status, ContextStatus) else str(status)
        initial_tokens = int(self._context_guard.stats.total_tokens_used or 0)
        meta: Dict[str, Any] = {
            "initial_status": initial_status,
            "initial_tokens": initial_tokens,
            "actions": [],
            "compressed_messages": 0,
        }
        if status == ContextStatus.OK:
            meta.update(
                {
                    "final_status": initial_status,
                    "final_tokens": initial_tokens,
                    "message_count": len(messages),
                }
            )
            self._context_budget_last_meta = meta
            return messages

        compacted: List[Dict[str, Any]] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            normalized = dict(message)
            if index > 0:
                compacted_content = self._compact_message_content_for_budget(
                    normalized.get("content", ""),
                    max_tokens=self._context_budget_message_cap(
                        normalized,
                        index=index,
                        total=len(messages),
                    ),
                )
                if compacted_content != normalized.get("content", ""):
                    meta["compressed_messages"] = int(meta["compressed_messages"]) + 1
                normalized["content"] = compacted_content
            compacted.append(normalized)

        if int(meta["compressed_messages"]) > 0:
            meta["actions"].append("compress_messages")

        status = self._context_guard.get_status(compacted)
        if status in {ContextStatus.CRITICAL, ContextStatus.OVERFLOW} and len(compacted) > 7:
            prefix = compacted[:2]
            suffix = compacted[-4:]
            middle = compacted[2:-4]
            summary_message = self._build_context_budget_summary_message(middle)
            compacted = prefix + ([summary_message] if summary_message else []) + suffix
            meta["actions"].append("collapse_middle_history")
            status = self._context_guard.get_status(compacted)

        if status == ContextStatus.OVERFLOW and len(compacted) > 3:
            tightened: List[Dict[str, Any]] = []
            for index, message in enumerate(compacted):
                if not isinstance(message, dict):
                    continue
                normalized = dict(message)
                if index > 0:
                    cap = 360 if index >= max(0, len(compacted) - 2) else 220
                    normalized["content"] = self._compact_message_content_for_budget(
                        normalized.get("content", ""),
                        max_tokens=cap,
                    )
                tightened.append(normalized)
            compacted = tightened
            meta["actions"].append("tighten_remaining_messages")
            status = self._context_guard.get_status(compacted)

        final_status = status.value if isinstance(status, ContextStatus) else str(status)
        final_tokens = int(self._context_guard.stats.total_tokens_used or 0)
        meta.update(
            {
                "final_status": final_status,
                "final_tokens": final_tokens,
                "message_count": len(compacted),
            }
        )
        self._context_budget_last_meta = meta
        if meta["actions"]:
            log.warning(
                "ContextGuard fuer %s: %s -> %s tokens | actions=%s",
                self.agent_type,
                initial_tokens,
                final_tokens,
                ",".join(str(item) for item in meta["actions"]),
            )
        return compacted

    @staticmethod
    def _format_jsonrpc_error(error: Any) -> str:
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            code = error.get("code")
            data = error.get("data")

            parts = []
            if code not in (None, ""):
                parts.append(f"code={code}")
            if message:
                parts.append(message)
            if data not in (None, "", [], {}):
                parts.append(str(data))
            if parts:
                return "JSON-RPC Fehler: " + " | ".join(parts)
            return "JSON-RPC Fehler ohne Details"

        text = str(error or "").strip()
        if text:
            return text
        return "JSON-RPC Fehler ohne Details"

    # ------------------------------------------------------------------
    # Implicit Final Answer Detection
    # ------------------------------------------------------------------

    _COMPLETION_PATTERNS = re.compile(
        r"(?:"
        r"aufgabe\s+(?:erfolgreich|abgeschlossen|erledigt)"
        r"|erfolgreich\s+(?:abgeschlossen|erstellt|gespeichert|generiert)"
        r"|(?:bild|datei|cover|ergebnis)\s+(?:wurde|ist)\s+(?:erfolgreich|gespeichert)"
        r"|✅"
        r"|task\s+(?:complete|done|finished)"
        r"|successfully\s+(?:created|saved|completed|generated)"
        r")",
        re.IGNORECASE,
    )
    _PARSE_ERROR_PROGRESS_PATTERNS = re.compile(
        r"^\s*(?:"
        r"ich\s+(?:recherch|pr[üu]f|analys|suche|schaue|lese|hole|arbeite|versuche|denke)"
        r"|einen\s+moment"
        r"|warte\s+kurz"
        r"|ich\s+bin\s+dran"
        r")",
        re.IGNORECASE,
    )
    _PARSE_ERROR_FORMAT_ECHO_PATTERNS = re.compile(
        r"(?:ausschlie(?:ss|ß)lich).*(?:format|final answer|tool aufrufen)"
        r"|^\s*verstanden\.\s*ich\s+antworte\s+ab\s+jetzt"
        r"|^\s*ich\s+antworte\s+ab\s+jetzt",
        re.IGNORECASE | re.DOTALL,
    )
    _SAFE_EMBEDDED_FINAL_ANSWER_ACTION_METHODS = frozenset(
        {
            "search_blackboard",
            "search_log",
            "get_processes",
            "get_system_stats",
            "get_service_status",
            "list_directory",
        }
    )
    _SAFE_EMBEDDED_FINAL_ANSWER_TASK_PATTERNS = re.compile(
        r"\b(?:"
        r"runtime"
        r"|laufzeit"
        r"|betriebszustand"
        r"|systemzustand"
        r"|timus-zustand"
        r"|blackboard"
        r"|diagnos"
        r"|baustell"
        r"|health"
        r"|status"
        r"|service"
        r"|system"
        r"|cpu"
        r"|ram"
        r"|disk"
        r"|speicher"
        r"|log"
        r"|fehler"
        r"|error"
        r"|exception"
        r")\b",
        re.IGNORECASE,
    )
    _SAFE_EMBEDDED_FINAL_ANSWER_EXAMPLE_PATTERNS = re.compile(
        r"(?:beispiel|example|format)\s*:?.{0,120}action\s*:",
        re.IGNORECASE | re.DOTALL,
    )
    _NEGATIVE_EVIDENCE_MARKERS = (
        "keine belastbaren belege",
        "kein belastbarer beleg",
        "in den geprueften quellen kein belastbarer beleg",
        "in den geprüften quellen kein belastbarer beleg",
        "keine belastbare evidenz",
        "nicht sicher belegen",
        "kein belastbarer nachweis",
    )
    _OFF_TOPIC_EVIDENCE_MARKERS = (
        "behandelten komplett andere themen",
        "thematisch nur teilweise passend",
        "nicht direkt auf die leitfrage ein",
        "nur indirekt passend",
        "evidenz ist noch zu duenn",
        "scope-gap",
    )
    _STRONG_DEBUNK_PATTERNS = re.compile(
        r"\b(?:falschinformation|fakenews|gerücht|geruecht)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _looks_like_implicit_final_answer(cls, text: str) -> bool:
        """Erkennt Abschluss-Nachrichten des LLM ohne explizites 'Final Answer:'.

        Bedingungen (beide müssen zutreffen):
        - Kein JSON im Text (kein Tool-Call beabsichtigt)
        - Text enthält typische Abschluss-Formulierungen auf Deutsch oder Englisch
        """
        if "{" in text:
            return False  # JSON vorhanden → normaler Tool-Call-Versuch
        return bool(cls._COMPLETION_PATTERNS.search(text))

    @classmethod
    def _looks_like_salvageable_parse_error_answer(cls, text: str) -> bool:
        """Erkennt laengere Nutzantworten, die trotz fehlendem Action-JSON schon final sind."""
        normalized = str(text or "").strip()
        if not normalized:
            return False
        if "{" in normalized or normalized.startswith("Action:") or "Final Answer:" in normalized:
            return False
        if cls._PARSE_ERROR_FORMAT_ECHO_PATTERNS.search(normalized):
            return False
        if cls._PARSE_ERROR_PROGRESS_PATTERNS.search(normalized):
            return False
        if cls._looks_like_implicit_final_answer(normalized):
            return True
        if len(normalized) < 120 and "\n" not in normalized:
            return False
        has_structure = bool(
            "\n" in normalized
            or normalized.count(". ") >= 2
            or re.search(r"(?m)^\s*(?:[-*]|\d+\.)\s+", normalized)
        )
        return has_structure

    @staticmethod
    def _extract_final_answer_body(text: str) -> str:
        normalized = str(text or "")
        if "Final Answer:" not in normalized:
            return normalized.strip()
        return normalized.split("Final Answer:", 1)[1].strip()

    @classmethod
    def _soften_unproven_verdict_language(cls, text: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return normalized

        lowered = normalized.lower()
        has_negative_evidence_marker = any(
            marker in lowered for marker in cls._NEGATIVE_EVIDENCE_MARKERS
        )
        has_off_topic_marker = any(
            marker in lowered for marker in cls._OFF_TOPIC_EVIDENCE_MARKERS
        )
        if not has_negative_evidence_marker and not has_off_topic_marker:
            return normalized

        softened = normalized
        if cls._STRONG_DEBUNK_PATTERNS.search(softened):
            softened = cls._STRONG_DEBUNK_PATTERNS.sub(
                "nicht belastbar belegt",
                softened,
            )

        softened = re.sub(
            r"(?i)wer das behauptet, sollte quellen vorlegen\s*[—-]\s*und die gibt es nicht\.?",
            (
                "Wer das behauptet, sollte belastbare Primaer- oder Sekundaerquellen "
                "vorlegen. In den geprueften Quellen liegt dafuer derzeit kein belastbarer "
                "Beleg vor."
            ),
            softened,
        )
        softened = re.sub(
            r"(?i)\bund die gibt es nicht\b",
            "und dafuer liegt in den geprueften Quellen derzeit kein belastbarer Beleg vor",
            softened,
        )

        if has_off_topic_marker:
            caution = (
                "Hinweis: Die Quellenlage ist thematisch nur teilweise passend; "
                "Negativbefunde sind hier als 'in den geprueften Quellen kein belastbarer "
                "Beleg' zu lesen, nicht als vollstaendiger Ausschluss."
            )
            if caution.lower() not in softened.lower():
                softened = f"{caution}\n\n{softened}".strip()

        return softened

    @classmethod
    def _should_salvage_embedded_final_answer_action(
        cls,
        task_text: str,
        reply: str,
        action: Optional[dict],
    ) -> bool:
        if not isinstance(action, dict):
            return False

        method = str(action.get("method") or "").strip()
        if method not in cls._SAFE_EMBEDDED_FINAL_ANSWER_ACTION_METHODS:
            return False

        final_body = cls._extract_final_answer_body(reply)
        if "Action:" not in final_body:
            return False
        if cls._PARSE_ERROR_FORMAT_ECHO_PATTERNS.search(final_body):
            return False
        if cls._SAFE_EMBEDDED_FINAL_ANSWER_EXAMPLE_PATTERNS.search(final_body):
            return False

        task_candidates = [
            str(cls._extract_primary_task_text(task_text) or ""),
            str(task_text or ""),
        ]
        return any(
            cls._SAFE_EMBEDDED_FINAL_ANSWER_TASK_PATTERNS.search(candidate)
            for candidate in task_candidates
            if candidate
        )

    # ------------------------------------------------------------------
    # Loop-Detection
    # ------------------------------------------------------------------

    # System-Tools die Agenten NICHT direkt aufrufen sollen
    # (werden vom Dispatcher/System verwaltet)
    SYSTEM_ONLY_TOOLS = {
        "add_interaction",
        "end_session",
        "get_memory_stats",
        "run_tool",
        "communicate",
        "final_answer",
        "task_complete",
        "no_action_needed",
    }
    NAVIGATION_TASK_PATTERNS = (
        r"\bbrowser\b",
        r"\bwebsite\b",
        r"\burl\b",
        r"\bklick(?:e|en|t)?\b",
        r"\bclick\b",
        r"\bbooking\b",
        r"\bgoogle\s+maps\b",
        r"\bgoogle\.(?:com|de)\b",
        r"\bamazon\.(?:com|de)\b",
        r"\bnavigat(?:e|ion)\b",
        r"\boeffne\b",
        r"\böffne\b",
        r"\bgehe\s+zu\b",
    )
    MEMORY_QUERY_PATTERNS = (
        r"\bwas\s+habe\s+ich\b.*\bgesuch\w*\b",
        r"\bwas\s+suche\s+ich\b",
        r"\bwas\s+haben\s+wir\b.*\bgesuch\w*\b",
        r"\bvorhin\b.*\bgesuch\w*\b",
        r"\beben\b.*\bgesuch\w*\b",
        r"\berinner\w*\s+du\s+dich\b",
        r"\bwei(?:ss|ß)t\s+du\s+das\s+nicht\s+mehr\b",
    )

    def should_skip_action(
        self, action_name: str, params: dict
    ) -> Tuple[bool, Optional[str]]:
        # System-Tools sofort blockieren
        if action_name in self.SYSTEM_ONLY_TOOLS:
            reason = (
                f"'{action_name}' ist ein System-Tool und darf nicht direkt aufgerufen werden. "
                f"Konzentriere dich auf die eigentliche Aufgabe. "
                f"Wenn du fertig bist: Final Answer: [deine Antwort]"
            )
            log.warning(f"System-Tool blockiert: {action_name}")
            return True, reason

        action_key = f"{action_name}:{json.dumps(params, sort_keys=True)}"

        # Persistenter Counter (vergisst nie)
        self.action_call_counts[action_key] = self.action_call_counts.get(action_key, 0) + 1
        count = self.action_call_counts[action_key]

        COOLDOWN_ACTIONS = {
            "get_all_screen_text": 8.0,
            "type_text": 6.0,
            "read_text_from_screen": 8.0,
        }
        LOW_VALUE_ACTIONS = {"get_all_screen_text", "read_text_from_screen"}

        now = time.time()
        if action_name in COOLDOWN_ACTIONS:
            last_skip = self.last_skip_times.get(action_key, 0)
            if now - last_skip < COOLDOWN_ACTIONS[action_name]:
                reason = (
                    f"Cooldown active for {action_name} ({COOLDOWN_ACTIONS[action_name]}s). "
                    f"Change strategy or tool before retrying."
                )
                log.warning(reason)
                return True, reason

        if action_name in LOW_VALUE_ACTIONS and count >= 3:
            reason = (
                f"Low-value tool '{action_name}' already used {count}x. "
                f"Switch to higher-signal tools (search_web, open_url, analyze_screen_verified)."
            )
            log.warning(reason)
            self.last_skip_times[action_key] = now
            return True, reason

        if count >= 3:
            reason = (
                f"Loop detected: {action_name} wurde bereits {count}x aufgerufen "
                f"mit denselben Parametern. KRITISCH: Aktion wird uebersprungen. "
                f"Versuche anderen Ansatz!"
            )
            log.error(
                f"Kritischer Loop ({count}x): {action_name} - Aktion wird uebersprungen"
            )
            self.last_skip_times[action_key] = now
            return True, reason

        elif count >= 2:
            reason = (
                f"Loop detected: {action_name} wurde bereits {count}x aufgerufen "
                f"mit denselben Parametern. Versuche andere Parameter oder anderen Ansatz."
            )
            log.warning(f"Loop ({count}x): {action_name} - Warnung an Agent")
            self.recent_actions.append(action_key)
            return False, reason

        self.recent_actions.append(action_key)
        if len(self.recent_actions) > 40:
            self.recent_actions.pop(0)

        return False, None

    # ------------------------------------------------------------------
    # Tool Refinement
    # ------------------------------------------------------------------

    def _refine_tool_call(self, method: str, params: dict) -> Tuple[str, dict]:
        if method == "Image Generation":
            params.setdefault("model", IMAGE_MODEL_NAME)
            params.setdefault("size", "1024x1024")
            params.setdefault("quality", "high")

        corrections = {
            "URL Viewer": "start_visual_browser",
            "start_app": "open_application",
            "click": "click_at",
            "deep_research": "start_deep_research",
        }
        if method in corrections:
            method = corrections[method]

        if method == "start_deep_research" and "topic" in params:
            params["query"] = params.pop("topic")

        if method == "click_at" and "x" in params:
            params["x"] = int(params["x"])
            params["y"] = int(params["y"])

        if method == "delegate_to_agent":
            params = self._normalize_delegate_to_agent_params(params)

        return method, params

    @staticmethod
    def _build_lightweight_executor_handoff(task: str, *, task_type: str) -> str:
        safe_task = str(task or "").strip()
        payload_lines = [
            "# DELEGATION HANDOFF",
            "target_agent: executor",
            f"goal: {safe_task}",
            "expected_output: Aktuelle Treffer und kurze verifizierte Zusammenfassung",
            "success_signal: Leichter Live-Lookup erfolgreich abgeschlossen",
            "constraints: nutze_leichte_live_suche_ohne_deep_research, bleibe_quellengebunden_und_kurz",
            "handoff_data:",
            f"- task_type: {task_type}",
            f"- original_user_task: {safe_task[:500]}",
            f"- query: {safe_task[:500]}",
            "- preferred_search_tool: search_web",
            "- fallback_tools: search_news, fetch_url, search_google_maps_places",
            "- avoid_deep_research: yes",
            "- max_results: 5",
            "",
            "# TASK",
            safe_task,
        ]
        return "\n".join(payload_lines)

    @staticmethod
    def _build_setup_build_executor_handoff(task: str) -> str:
        safe_task = str(task or "").strip()
        workspace_root = os.getcwd()
        payload_lines = [
            "# DELEGATION HANDOFF",
            "target_agent: executor",
            f"goal: {safe_task}",
            "expected_output: Bestehende Vorbereitungen, echte Luecken und naechster Build-Schritt",
            "success_signal: Setup-Stand im Repo belastbar geklaert",
            "constraints: pruefe_repo_artefakte_und_env_zuerst, keine_generische_setup_hilfe, kein_parallelscan",
            "handoff_data:",
            "- task_type: setup_build_probe",
            f"- original_user_task: {safe_task[:500]}",
            f"- query: {safe_task[:500]}",
            f"- workspace_root: {workspace_root}",
            f"- project_root: {workspace_root}",
            "- preferred_tools: read_file, run_command",
            "- avoid_deep_research: yes",
            "",
            "# TASK",
            safe_task,
        ]
        return "\n".join(payload_lines)

    @staticmethod
    def _build_research_advisory_executor_handoff(task: str) -> str:
        safe_task = str(task or "").strip()
        payload_lines = [
            "# DELEGATION HANDOFF",
            "target_agent: executor",
            f"goal: {safe_task}",
            "expected_output: Kompaktes Themen-Briefing mit belastbaren Quellen und naechsten sinnvollen Fragen",
            "success_signal: Bounded topic briefing abgeschlossen",
            "constraints: nutze_leichte_live_suche_ohne_deep_research, bleibe_quellengebunden_und_kompakt, keine_exhaustive_langrecherche",
            "handoff_data:",
            "- task_type: simple_live_lookup",
            f"- original_user_task: {safe_task[:500]}",
            f"- query: {safe_task[:500]}",
            "- preferred_search_tool: search_web",
            "- fallback_tools: search_news, fetch_url",
            "- avoid_deep_research: yes",
            "- max_results: 5",
            "",
            "# TASK",
            safe_task,
        ]
        return "\n".join(payload_lines)

    @staticmethod
    def _build_generic_executor_handoff(task: str, *, task_type: str = "delegated_executor_task") -> str:
        safe_task = str(task or "").strip()
        workspace_root = os.getcwd()
        payload_lines = [
            "# DELEGATION HANDOFF",
            "target_agent: executor",
            f"goal: {safe_task}",
            "expected_output: Strukturierte Diagnose oder direktes Ausfuehrungsergebnis",
            "success_signal: Delegierter Executor-Schritt abgeschlossen",
            "constraints: bleibe_beim_konkreten_auftrag, nutze_projektwurzel_aus_dem_handoff",
            "handoff_data:",
            f"- task_type: {task_type}",
            f"- original_user_task: {safe_task[:500]}",
            f"- query: {safe_task[:500]}",
            f"- workspace_root: {workspace_root}",
            f"- project_root: {workspace_root}",
            "",
            "# TASK",
            safe_task,
        ]
        return "\n".join(payload_lines)

    def _normalize_delegate_to_agent_params(self, params: dict) -> dict:
        if not isinstance(params, dict):
            return params

        refined = dict(params)
        target_agent = str(refined.get("agent_type") or "").strip().lower()
        raw_task = str(refined.get("task") or "").strip()
        if target_agent != "executor" or not raw_task:
            return refined
        if parse_delegation_handoff(raw_task):
            return refined

        current_clarity = self._current_meta_clarity_contract() if self.agent_type == "meta" else {}
        objective_domain = self._detect_meta_objective_domain(
            str(current_clarity.get("primary_objective") or raw_task)
        )

        if self.agent_type == "meta" and objective_domain == "setup_build":
            refined["task"] = self._build_setup_build_executor_handoff(raw_task)
            log.info("Executor-Delegation fuer setup_build mit strukturiertem Probe-Handoff angereichert")
            return refined

        if self.agent_type == "meta" and objective_domain == "research_advisory":
            refined["task"] = self._build_research_advisory_executor_handoff(raw_task)
            log.info("Executor-Delegation fuer research_advisory als bounded topic briefing angereichert")
            return refined

        try:
            from orchestration.meta_orchestration import classify_meta_task

            classification = classify_meta_task(raw_task, action_count=0)
        except Exception as e:
            log.debug("Delegations-Klassifizierung fuer %s fehlgeschlagen: %s", target_agent, e)
            return refined

        task_type = str(classification.get("task_type") or "").strip().lower()
        recommended_chain = [
            str(agent or "").strip().lower()
            for agent in (classification.get("recommended_agent_chain") or [])
            if str(agent or "").strip()
        ]

        if (
            self.agent_type == "meta"
            and task_type == "knowledge_research"
            and "research" in recommended_chain
        ):
            refined["agent_type"] = "research"
            log.warning(
                "Delegation auto-korrigiert: meta wollte executor, Klassifizierung verlangt research | task_type=%s",
                task_type,
            )
            return refined

        if task_type in {"simple_live_lookup", "simple_live_lookup_document", "youtube_light_research"}:
            refined["task"] = self._build_lightweight_executor_handoff(
                raw_task,
                task_type=task_type,
            )
            log.info(
                "Executor-Delegation mit strukturiertem Handoff angereichert | task_type=%s",
                task_type,
            )
        elif self.agent_type == "meta":
            refined["task"] = self._build_generic_executor_handoff(
                raw_task,
                task_type=task_type or "delegated_executor_task",
            )
            log.info(
                "Executor-Delegation mit generischem Handoff angereichert | task_type=%s",
                task_type or "delegated_executor_task",
            )

        return refined

    # ------------------------------------------------------------------
    # File Artifacts
    # ------------------------------------------------------------------

    def _handle_file_artifacts(self, observation: dict):
        if not isinstance(observation, dict):
            return
        if os.getenv("AUTO_OPEN_FILES", "true").lower() != "true":
            return

        file_path, path_source = self._extract_primary_file_path(observation)
        if file_path and os.path.exists(file_path):
            block_reason = desktop_open_block_reason(action_kind="file", target=file_path)
            if block_reason:
                log.warning(
                    "Datei-Auto-Open blockiert: agent=%s path=%s reason=%s",
                    getattr(self, "agent_type", "unknown"),
                    file_path,
                    block_reason,
                )
                return
            if path_source != "artifacts":
                log.warning(
                    "Dateipfad-Fallback genutzt: agent=%s source=%s path=%s",
                    getattr(self, "agent_type", "unknown"),
                    path_source,
                    file_path,
                )
            log.info(f"Oeffne: {file_path}")
            try:
                if platform.system() == "Windows":
                    os.startfile(file_path)
                elif platform.system() == "Darwin":
                    subprocess.call(["open", file_path])
                else:
                    subprocess.call(["xdg-open", file_path])
            except Exception as e:
                log.warning(f"Oeffnen fehlgeschlagen: {e}")

    def _extract_primary_file_path(self, observation: dict) -> Tuple[Optional[str], str]:
        if not isinstance(observation, dict):
            return None, "none"

        artifacts = observation.get("artifacts")
        if isinstance(artifacts, list):
            for item in artifacts:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "").strip()
                if path:
                    return self._resolve_local_path(path), "artifacts"

        metadata = observation.get("metadata")
        if isinstance(metadata, dict):
            for key in ("pdf_filepath", "image_path", "narrative_filepath", "filepath", "file_path", "path", "saved_as"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return self._resolve_local_path(value.strip()), "metadata"

        for key in ("file_path", "saved_as", "filepath", "path"):
            value = observation.get(key)
            if isinstance(value, str) and value.strip():
                return self._resolve_local_path(value.strip()), "legacy"

        return None, "none"

    @staticmethod
    def _resolve_local_path(path: str) -> str:
        if os.path.isabs(path):
            return path
        candidate = os.path.abspath(path)
        return candidate

    # ------------------------------------------------------------------
    # Lane Management
    # ------------------------------------------------------------------

    async def _get_lane(self) -> Lane:
        """Holt oder erstellt die Lane fuer diesen Agenten."""
        if self._lane is None:
            self._lane = await lane_manager.get_or_create_lane(
                self.lane_id or f"{self.agent_type}_{id(self)}"
            )
        return self._lane

    async def _ensure_remote_tool_names(self) -> None:
        """Holt einmalig die Tool-Namen vom Server (lazy)."""
        if self._remote_tools_fetched:
            return

        self._remote_tools_fetched = True
        try:
            resp = await self.http_client.get(
                f"{MCP_URL}/get_tool_schemas/openai",
                timeout=10.0,
            )
            if resp.status_code != 200:
                log.debug(
                    f"Remote-Registry Endpoint antwortet mit Status {resp.status_code}"
                )
                return

            schema_data = resp.json()
            if schema_data.get("status") != "success":
                return

            for tool in schema_data.get("tools", []):
                if not isinstance(tool, dict):
                    continue
                fn = tool.get("function", {})
                if not isinstance(fn, dict):
                    continue
                name = fn.get("name", "")
                if name:
                    self._remote_tool_names.add(name)

            log.info(f"Remote-Registry geladen: {len(self._remote_tool_names)} Tools")
        except Exception as e:
            log.debug(f"Remote-Registry nicht erreichbar (non-critical): {e}")

    # ------------------------------------------------------------------
    # MCP Tool Call (mit Loop-Detection und Lane-Integration)
    # ------------------------------------------------------------------

    def _task_text_for_restart_guard(self) -> str:
        text = self._extract_primary_task_text(str(getattr(self, "_current_task_text", "") or ""))
        for marker in (
            "\n# SHELL-KONTEXT",
            "\n# Bekannte Informationen (Agent-Blackboard):",
            "\nWORKING_MEMORY_CONTEXT",
        ):
            if marker in text:
                text = text.split(marker, 1)[0]
        return text.strip().lower()

    @staticmethod
    def _extract_primary_task_text(task_text: str) -> str:
        """Extrahiert die eigentliche Aufgabe aus Meta-/Memory-angereicherten Tasks.

        Hintergrund:
        Der BaseAgent bekommt haeufig zusaetzliche System-, Skill- und Working-Memory-
        Bloecke vorangestellt. Heuristiken wie Navigationserkennung duerfen nicht auf
        diesem angereicherten Gesamttext laufen, sonst triggern Begriffe wie "browser"
        aus dem Kontext faelschlich den Visual-/Navigation-Pfad.
        """
        text = str(task_text or "").strip()
        if not text:
            return ""

        handoff = parse_delegation_handoff(text)
        if handoff and handoff.goal:
            return str(handoff.goal).strip()

        segment = text
        for marker in (
            "# CURRENT USER QUERY",
            "AKTUELLE_NUTZERANFRAGE:",
            "# AUFGABE",
        ):
            if marker in text:
                segment = text.split(marker, 1)[1].lstrip()
                break

        for stop_marker in (
            "\n\nBearbeite jetzt ausschließlich die aktuelle Nutzeranfrage.",
            "\n\nPrüfe ob verfügbare Skills zur Aufgabe passen und nutze sie entsprechend.",
            "\n\n# INSTRUCTIONS",
            "\n\nUse the above skills when appropriate for this task.",
            "\n\nFollow the skill instructions and use provided scripts/references.",
            "\n\n## DECOMPOSITION-REGEL",
        ):
            if stop_marker in segment:
                segment = segment.split(stop_marker, 1)[0]

        return segment.strip()

    @classmethod
    def _extract_working_memory_query(cls, task_text: str) -> str:
        """Leitet eine kompakte Recall-Query aus dem aktuellen Task ab.

        Der eigentliche Nutzerprompt darf im Agentenlauf reichhaltig bleiben.
        Für Working-Memory-Retrieval ist ein aufgeblähter Meta-/Skill-/Plan-Prompt
        aber kontraproduktiv: er vergrößert Embedding- und Recall-Kosten und
        verwässert die Suchterme. Deshalb bevorzugen wir hier das eigentliche
        Nutzerziel plus optional den aktuellen Planschritt.
        """
        text = str(task_text or "").strip()
        if not text:
            return ""

        primary = cls._extract_primary_task_text(text).strip()
        if not primary:
            primary = text

        meta_query = cls._extract_meta_working_memory_query(primary)
        if meta_query:
            return meta_query

        return primary

    @staticmethod
    def _extract_meta_clarity_contract(task_text: str) -> Dict[str, Any]:
        marker = "# META ORCHESTRATION HANDOFF"
        text = str(task_text or "").strip()
        if marker not in text:
            return {}

        _, after_header = text.split(marker, 1)
        handoff_block = after_header.split("# ORIGINAL USER TASK", 1)[0]
        for raw_line in handoff_block.splitlines():
            stripped = str(raw_line or "").strip()
            if not stripped or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            if key.strip() != "meta_clarity_contract_json":
                continue
            try:
                return parse_meta_clarity_contract(json.loads(value.strip()))
            except Exception:
                return {}
        return {}

    @staticmethod
    def _extract_meta_request_frame(task_text: str) -> Dict[str, Any]:
        marker = "# META ORCHESTRATION HANDOFF"
        text = str(task_text or "").strip()
        if marker not in text:
            return {}

        _, after_header = text.split(marker, 1)
        handoff_block = after_header.split("# ORIGINAL USER TASK", 1)[0]
        for raw_line in handoff_block.splitlines():
            stripped = str(raw_line or "").strip()
            if not stripped or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            if key.strip() != "meta_request_frame_json":
                continue
            try:
                loaded = json.loads(value.strip())
                return loaded if isinstance(loaded, dict) else {}
            except Exception:
                return {}
        return {}

    @classmethod
    def _extract_meta_working_memory_query(cls, task_text: str) -> str:
        marker = "# META ORCHESTRATION HANDOFF"
        text = str(task_text or "").strip()
        if marker not in text:
            return ""

        _, after_header = text.split(marker, 1)
        if "# ORIGINAL USER TASK" in after_header:
            handoff_block, original_task = after_header.split("# ORIGINAL USER TASK", 1)
        else:
            handoff_block, original_task = after_header, ""

        parts: list[str] = []
        seen: set[str] = set()
        clarity_contract = cls._extract_meta_clarity_contract(text)

        def add_part(value: Any, *, prefix: str = "", limit: int = 280) -> None:
            raw = str(value or "").strip()
            if not raw:
                return
            cleaned = re.sub(r"\s+", " ", raw).strip()
            if len(cleaned) > limit:
                clipped = cleaned[:limit].rsplit(" ", 1)[0].strip()
                cleaned = f"{clipped or cleaned[:limit]}..."
            lowered = cleaned.lower()
            if lowered in seen:
                return
            seen.add(lowered)
            if prefix:
                parts.append(f"{prefix}{cleaned}")
            else:
                parts.append(cleaned)

        add_part(clarity_contract.get("primary_objective"), prefix="Pflichtziel: ", limit=320)
        add_part(original_task, limit=420)

        plan_payload: dict[str, Any] = {}
        decomposition_payload: dict[str, Any] = {}
        for raw_line in handoff_block.splitlines():
            stripped = str(raw_line or "").strip()
            if not stripped or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            normalized_key = key.strip()
            normalized_value = value.strip()
            if normalized_key == "meta_execution_plan_json":
                try:
                    loaded = json.loads(normalized_value)
                    if isinstance(loaded, dict):
                        plan_payload = loaded
                except Exception:
                    plan_payload = {}
            elif normalized_key == "task_decomposition_json":
                try:
                    loaded = json.loads(normalized_value)
                    if isinstance(loaded, dict):
                        decomposition_payload = loaded
                except Exception:
                    decomposition_payload = {}

        add_part(decomposition_payload.get("goal"), prefix="Ziel: ")

        next_step_id = str(plan_payload.get("next_step_id") or "").strip().lower()
        next_step: dict[str, Any] = {}
        for step in plan_payload.get("steps") or []:
            if not isinstance(step, dict):
                continue
            step_id = str(step.get("id") or "").strip().lower()
            if next_step_id and step_id == next_step_id:
                next_step = step
                break
        if not next_step and isinstance(plan_payload.get("steps"), list) and plan_payload.get("steps"):
            first_step = plan_payload["steps"][0]
            if isinstance(first_step, dict):
                next_step = first_step

        add_part(next_step.get("title"), prefix="Aktueller Planschritt: ")
        add_part(next_step.get("expected_output"), prefix="Erwartetes Ergebnis: ")

        completion_signals = next_step.get("completion_signals") or []
        if isinstance(completion_signals, list) and completion_signals:
            signal_text = ", ".join(str(item or "").strip() for item in completion_signals if str(item or "").strip())
            add_part(signal_text, prefix="Abschlusssignal: ", limit=180)
        add_part(clarity_contract.get("completion_condition"), prefix="Abschlussbedingung: ", limit=180)

        return "\n".join(parts).strip()

    @staticmethod
    def _detect_meta_objective_domain(text: str) -> str:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return ""
        if any(pattern in lowered for pattern in _META_SKILL_RESPONSE_PATTERNS):
            return "skill_creation"
        if any(pattern in lowered for pattern in _META_DOC_STATUS_PATTERNS):
            return "docs_status"
        if any(pattern in lowered for pattern in _META_SETUP_BUILD_PATTERNS):
            return "setup_build"
        if any(pattern in lowered for pattern in _META_RESEARCH_ADVISORY_PATTERNS):
            return "research_advisory"
        if any(pattern in lowered for pattern in _META_MIGRATION_WORK_PATTERNS):
            return "migration_work"
        if any(pattern in lowered for pattern in _META_LOCATION_ROUTE_PATTERNS):
            return "location_route"
        return ""

    @staticmethod
    def _detect_meta_answer_domain(text: str) -> str:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return ""
        if any(pattern in lowered for pattern in _META_GENERIC_HELP_PATTERNS):
            return "generic_meta_help"
        if any(pattern in lowered for pattern in _META_SKILL_RESPONSE_PATTERNS):
            return "skill_creation"
        if any(pattern in lowered for pattern in _META_DOC_STATUS_PATTERNS):
            return "docs_status"
        if any(pattern in lowered for pattern in _META_SETUP_BUILD_PATTERNS):
            return "setup_build"
        if any(pattern in lowered for pattern in _META_RESEARCH_ADVISORY_PATTERNS):
            return "research_advisory"
        if any(pattern in lowered for pattern in _META_MIGRATION_WORK_PATTERNS):
            return "migration_work"
        if any(pattern in lowered for pattern in _META_LOCATION_ROUTE_PATTERNS):
            return "location_route"
        return ""

    @classmethod
    def _detect_meta_action_domain(cls, method: str, params: dict) -> str:
        method_clean = str(method or "").strip().lower()
        params_map = params if isinstance(params, dict) else {}
        candidate_parts = [method_clean]
        for key in ("task", "query", "goal", "destination_query", "location_query"):
            value = params_map.get(key)
            if value:
                candidate_parts.append(str(value))
        candidate_text = " ".join(candidate_parts).strip()
        candidate_lower = candidate_text.lower()

        if method_clean in _META_LOCATION_METHODS:
            return "location_route"
        if method_clean in _META_FILE_READ_METHODS:
            return "docs_status"
        if method_clean == "delegate_to_agent":
            delegated = cls._detect_meta_objective_domain(candidate_lower)
            if delegated:
                return delegated

        if any(pattern in candidate_lower for pattern in _META_LOCATION_ROUTE_PATTERNS):
            return "location_route"
        if any(pattern in candidate_lower for pattern in _META_DOC_STATUS_PATTERNS):
            return "docs_status"
        if any(pattern in candidate_lower for pattern in _META_SETUP_BUILD_PATTERNS):
            return "setup_build"
        if any(pattern in candidate_lower for pattern in _META_RESEARCH_ADVISORY_PATTERNS):
            return "research_advisory"
        if any(pattern in candidate_lower for pattern in _META_MIGRATION_WORK_PATTERNS):
            return "migration_work"
        return ""

    def _current_meta_clarity_contract(self) -> Dict[str, Any]:
        if str(self.agent_type or "").strip().lower() != "meta":
            return {}
        task_text = str(getattr(self, "_current_task_text", "") or "").strip()
        if not task_text:
            return {}
        return self._extract_meta_clarity_contract(task_text)

    def _current_meta_request_frame(self) -> Dict[str, Any]:
        if str(self.agent_type or "").strip().lower() != "meta":
            return {}
        task_text = str(getattr(self, "_current_task_text", "") or "").strip()
        if not task_text:
            return {}
        return self._extract_meta_request_frame(task_text)

    def _current_meta_delegate_count(self) -> int:
        count = 0
        for item in (self._task_action_history or []):
            if str((item or {}).get("method") or "").strip().lower() != "delegate_to_agent":
                continue
            observation = (item or {}).get("observation")
            blocked_reason = ""
            if isinstance(observation, dict):
                blocked_reason = str(observation.get("blocked_reason") or "").strip().lower()
            if blocked_reason in {
                "meta_clarity_delegate_agent_not_allowed",
                "meta_clarity_objective_mismatch",
            }:
                continue
            count += 1
        return count

    def _build_meta_clarity_closeout_prompt(self, task: str, method: str, obs: Any) -> str | None:
        contract = self._current_meta_clarity_contract()
        if not contract or not bool(contract.get("direct_answer_required")):
            return None
        if not bool(contract.get("force_answer_after_delegate_budget")):
            return None

        max_delegate_raw = contract.get("max_delegate_calls", -1)
        max_delegate_calls = -1 if max_delegate_raw in (None, "") else int(max_delegate_raw)
        blocked_reason = ""
        if isinstance(obs, dict):
            blocked_reason = str(obs.get("blocked_reason") or "").strip().lower()
        if method != "delegate_to_agent" and blocked_reason not in {
            "meta_clarity_delegate_budget_exhausted",
            "meta_clarity_delegate_agent_not_allowed",
        }:
            return None
        if max_delegate_calls < 0:
            return None
        if (
            self._current_meta_delegate_count() < max_delegate_calls
            and blocked_reason not in {
                "meta_clarity_delegate_budget_exhausted",
            }
        ):
            return None

        primary_objective = str(
            contract.get("primary_objective")
            or self._extract_primary_task_text(task)
            or ""
        ).strip()
        completion_condition = str(contract.get("completion_condition") or "").strip()
        answer_obligation = str(contract.get("answer_obligation") or "").strip()
        return (
            "Meta-Clarity Abschlusszwang:\n"
            f"- primary_objective: {primary_objective}\n"
            f"- answer_obligation: {answer_obligation}\n"
            f"- completion_condition: {completion_condition}\n"
            "Die notwendige Evidenz liegt jetzt vor oder weiteres Delegieren ist nicht erlaubt.\n"
            "Kein weiterer Toolcall. Kein delegate_to_agent. Antworte jetzt direkt im Format:\n"
            "Final Answer: ..."
        )

    def _build_meta_clarity_delegate_redirect_prompt(self, task: str, method: str, obs: Any) -> str | None:
        if str(method or "").strip().lower() not in {"delegate_to_agent", "delegate_multiple_agents"}:
            return None
        if not isinstance(obs, dict):
            return None
        blocked_reason = str(obs.get("blocked_reason") or "").strip().lower()
        if blocked_reason not in {
            "meta_clarity_delegate_agent_not_allowed",
            "meta_clarity_parallel_delegation_not_allowed",
        }:
            return None

        contract = self._current_meta_clarity_contract()
        if not contract:
            return None

        max_delegate_raw = contract.get("max_delegate_calls", -1)
        max_delegate_calls = -1 if max_delegate_raw in (None, "") else int(max_delegate_raw)
        if max_delegate_calls >= 0 and self._current_meta_delegate_count() >= max_delegate_calls:
            return None

        allowed_agents = [
            str(item or "").strip().lower()
            for item in (contract.get("allowed_delegate_agents") or ())
            if str(item or "").strip()
        ]
        if not allowed_agents:
            return None

        primary_objective = str(
            contract.get("primary_objective")
            or self._extract_primary_task_text(task)
            or ""
        ).strip()
        return (
            "Meta-Clarity Korrektur:\n"
            f"- primary_objective: {primary_objective}\n"
            f"- erlaubte_delegate_agents: {', '.join(allowed_agents)}\n"
            "Waehle jetzt entweder einen dieser erlaubten Evidenzpfade oder beantworte direkt.\n"
            "Kein anderer delegate_to_agent. Kein delegate_multiple_agents."
        )

    def _build_meta_frame_answer_redirect_prompt(self, task: str, result: str) -> str | None:
        if str(self.agent_type or "").strip().lower() != "meta":
            return None

        clarity_contract = self._current_meta_clarity_contract()
        frame = self._current_meta_request_frame()
        if not clarity_contract and not frame:
            return None

        primary_objective = str(
            (frame or {}).get("primary_objective")
            or clarity_contract.get("primary_objective")
            or self._extract_primary_task_text(task)
            or ""
        ).strip()
        if not primary_objective:
            return None

        objective_domain = str((frame or {}).get("task_domain") or "").strip().lower()
        if not objective_domain:
            objective_domain = self._detect_meta_objective_domain(primary_objective)
        answer_domain = self._detect_meta_answer_domain(result)
        request_kind = str(clarity_contract.get("request_kind") or "").strip().lower()
        frame_kind = str((frame or {}).get("frame_kind") or "").strip().lower()
        execution_mode = str((frame or {}).get("execution_mode") or "").strip().lower()
        direct_answer_required = bool(clarity_contract.get("direct_answer_required"))

        objective_lower = primary_objective.lower()
        if answer_domain == "skill_creation" and (
            objective_domain == "skill_creation"
            or any(pattern in objective_lower for pattern in _META_SKILL_RESPONSE_PATTERNS)
        ):
            return None
        if answer_domain == "setup_build" and objective_domain == "setup_build":
            return None
        if answer_domain == "migration_work" and objective_domain == "migration_work":
            return None
        if answer_domain == "location_route" and objective_domain == "location_route":
            return None
        if answer_domain == "docs_status" and objective_domain == "docs_status":
            return None

        mismatch = False
        if answer_domain in {"skill_creation", "location_route", "setup_build", "migration_work"}:
            mismatch = answer_domain != objective_domain
        elif answer_domain == "generic_meta_help":
            mismatch = (
                direct_answer_required
                or frame_kind in {"direct_answer", "status_summary"}
                or execution_mode == "answer_directly"
                or objective_domain in {"setup_build", "migration_work"}
            )

        if not mismatch:
            return None

        request_hint = request_kind or frame_kind or execution_mode or "unknown"
        completion_condition = str(clarity_contract.get("completion_condition") or "").strip()
        return (
            "Meta-Frame-Korrektur:\n"
            f"- primary_objective: {primary_objective}\n"
            f"- task_domain: {objective_domain or 'unknown'}\n"
            f"- request_kind: {request_hint}\n"
            f"- erkannter_antwort_drift: {answer_domain}\n"
            f"- completion_condition: {completion_condition}\n"
            "Die letzte Antwort ist off-frame und verworfen.\n"
            "Kein Skill-/Workflow-Inventar. Kein Routing-/Standortblock. Keine generische Hilfe.\n"
            "Antworte jetzt nur auf die eigentliche Nutzerfrage im Format:\n"
            "Final Answer: ..."
        )

    def _check_meta_clarity_tool_intent(self, method: str, params: dict) -> Optional[Tuple[str, str]]:
        if str(self.agent_type or "").strip().lower() != "meta":
            return None

        task_text = str(getattr(self, "_current_task_text", "") or "").strip()
        if not task_text:
            return None

        clarity_contract = self._current_meta_clarity_contract()
        if not clarity_contract:
            return None

        primary_objective = str(
            clarity_contract.get("primary_objective")
            or self._extract_primary_task_text(task_text)
            or ""
        ).strip()
        request_kind = str(clarity_contract.get("request_kind") or "").strip().lower()
        objective_domain = self._detect_meta_objective_domain(primary_objective)
        action_domain = self._detect_meta_action_domain(method, params)

        method_clean = str(method or "").strip().lower()

        if method_clean == "delegate_multiple_agents":
            delegation_mode = str(clarity_contract.get("delegation_mode") or "").strip().lower()
            max_delegate_raw = clarity_contract.get("max_delegate_calls", -1)
            max_delegate_calls = -1 if max_delegate_raw in (None, "") else int(max_delegate_raw)
            if request_kind in {
                "direct_recommendation",
                "state_summary",
                "historical_recall",
                "self_model_status",
            } or max_delegate_calls in {0, 1} or delegation_mode in {
                "controlled_orchestration",
                "focused_research",
            }:
                return (
                    "Meta-Clarity blockiert parallele Delegation: "
                    f"fuer request_kind={request_kind or 'unknown'} und delegation_mode="
                    f"{delegation_mode or 'unknown'} ist hoechstens ein einzelner passender "
                    "Evidenzpfad erlaubt. Nutze entweder einen erlaubten Einzelagenten "
                    "oder schliesse direkt ab.",
                    "meta_clarity_parallel_delegation_not_allowed",
                )

        if method_clean == "delegate_to_agent":
            allowed_agents = tuple(
                str(item or "").strip().lower()
                for item in (clarity_contract.get("allowed_delegate_agents") or ())
                if str(item or "").strip()
            )
            delegated_agent = str((params or {}).get("agent_type") or "").strip().lower()
            if allowed_agents and delegated_agent and delegated_agent not in allowed_agents:
                return (
                    "Meta-Clarity blockiert diese Delegation: "
                    f"fuer request_kind={request_kind or 'unknown'} sind nur {', '.join(allowed_agents)} erlaubt, "
                    f"nicht aber {delegated_agent}.",
                    "meta_clarity_delegate_agent_not_allowed",
                )

            max_delegate_raw = clarity_contract.get("max_delegate_calls", -1)
            max_delegate_calls = -1 if max_delegate_raw in (None, "") else int(max_delegate_raw)
            if max_delegate_calls >= 0 and self._current_meta_delegate_count() >= max_delegate_calls:
                return (
                    "Meta-Clarity blockiert weitere Delegation: "
                    f"das Delegationsbudget fuer request_kind={request_kind or 'unknown'} "
                    f"ist mit {max_delegate_calls} Delegation(en) ausgeschoepft. "
                    "Nutze die vorhandene Evidenz und schliesse direkt ab.",
                    "meta_clarity_delegate_budget_exhausted",
                )

        if not objective_domain or not action_domain:
            return None

        if objective_domain == action_domain:
            return None

        if request_kind in {
            "direct_recommendation",
            "state_summary",
            "historical_recall",
            "self_model_status",
        }:
            return (
                "Meta-Clarity blockiert diese Aktion: "
                f"primary_objective verlangt {objective_domain}, "
                f"die geplante Aktion wirkt aber wie {action_domain}. "
                "Bleibe bei der aktuellen Frage und beantworte oder reframe sie direkt.",
                "meta_clarity_objective_mismatch",
            )

        return (
            "Meta-Clarity blockiert diese Aktion wegen Objective-Mismatch: "
            f"primary_objective={objective_domain}, action={action_domain}.",
            "meta_clarity_objective_mismatch",
        )

    def _has_explicit_restart_intent(self) -> bool:
        task_text = self._task_text_for_restart_guard()
        if not task_text:
            return False
        if any(keyword in task_text for keyword in _RESTART_INTENT_KEYWORDS):
            return True
        if _RESTART_TARGET_PATTERN.search(task_text) and _RESTART_VERB_PATTERN.search(task_text):
            return bool(_RESTART_QUALIFIER_PATTERN.search(task_text))
        return False

    def _check_restart_tool_intent(self, method: str, params: dict) -> str | None:
        if method != "restart_timus":
            return None
        mode = str((params or {}).get("mode") or "full").strip().lower()
        if mode == "status":
            return None
        if self._has_explicit_restart_intent():
            return None
        return (
            "restart_timus ist ohne expliziten Neustart-Wunsch im aktuellen Task blockiert. "
            "Diagnose- und Log-Leseaufgaben duerfen Timus nicht selbst neu starten."
        )

    def _current_task_type_for_analytics(self) -> str:
        raw_task_text = str(getattr(self, "_current_task_text", "") or "").strip()
        if not raw_task_text:
            return ""
        handoff = parse_delegation_handoff(raw_task_text)
        if handoff:
            task_type = str(
                handoff.handoff_data.get("task_type")
                or handoff.handoff_data.get("recipe_id")
                or ""
            ).strip()
            if task_type:
                return task_type[:120]
        for line in raw_task_text.splitlines():
            match = re.match(r"^\s*-?\s*task_type:\s*(.+?)\s*$", str(line or ""), re.IGNORECASE)
            if match:
                parsed_task_type = str(match.group(1) or "").strip()
                if parsed_task_type:
                    return parsed_task_type[:120]
        task_text = self._extract_primary_task_text(raw_task_text).strip()
        if not task_text:
            return ""
        first_line = task_text.splitlines()[0].strip()
        return first_line[:120]

    def _record_tool_usage_analytics(
        self,
        *,
        method: str,
        success: bool,
        started_at: float,
        task_type: str = "",
    ) -> None:
        if not os.getenv("AUTONOMY_SELF_IMPROVEMENT_ENABLED", "false").lower() in {"true", "1", "yes"}:
            return
        try:
            duration_ms = max(int(round((time.perf_counter() - started_at) * 1000)), 0)
            get_improvement_engine().record_tool_usage(
                ToolUsageRecord(
                    tool_name=str(method or "").strip() or "unknown_tool",
                    agent=str(getattr(self, "agent_type", "") or "").strip() or "unknown_agent",
                    task_type=str(task_type or "").strip(),
                    success=bool(success),
                    duration_ms=duration_ms,
                )
            )
        except Exception:
            pass

    async def _call_tool(self, method: str, params: dict) -> dict:
        method, params = self._refine_tool_call(method, params)
        tool_started_at = time.perf_counter()
        task_type = self._current_task_type_for_analytics()
        self._emit_live_status(
            phase="tool_active",
            detail=str(params)[:120],
            tool_name=method,
        )

        def _finalize(result: dict, *, success_override: Optional[bool] = None) -> dict:
            success = success_override
            if success is None:
                success = not any(
                    bool(result.get(key))
                    for key in ("error", "blocked_by_policy", "validation_failed", "skipped")
                )
                if str(result.get("status") or "").strip().lower() == "error":
                    success = False
            self._record_tool_usage_analytics(
                method=method,
                success=bool(success),
                started_at=tool_started_at,
                task_type=task_type,
            )
            return result

        restart_guard_reason = self._check_restart_tool_intent(method, params)
        if restart_guard_reason:
            self._emit_live_status(
                phase="tool_blocked",
                detail=restart_guard_reason[:120],
                tool_name=method,
            )
            return _finalize({
                "error": restart_guard_reason,
                "blocked_by_policy": True,
                "blocked_reason": "restart_intent_missing",
            }, success_override=False)

        policy_decision = evaluate_policy_gate(
            gate="tool",
            subject=method,
            payload={"method": method, "params": params, "agent": self.agent_type},
            source=f"agent.base_agent._call_tool:{self.agent_type}",
        )
        audit_policy_decision(policy_decision)
        allowed = bool(policy_decision.get("allowed", True))
        policy_reason = str(policy_decision.get("reason") or "Policy violation")
        if not allowed:
            log.error(f"Tool-Call durch Policy blockiert: {method}")
            self._emit_live_status(
                phase="tool_blocked",
                detail="Policy blockiert",
                tool_name=method,
            )
            if self._bug_logger is None:
                from utils.bug_logger import BugLogger
                self._bug_logger = BugLogger()
            self._bug_logger.log_bug(
                bug_id=f"policy_block_{method}",
                severity="low",
                agent=getattr(self, "agent_type", "unknown"),
                error_msg=f"Policy blockiert: {method} — {policy_reason}",
                context={"method": method, "params": str(params)[:300]},
            )
            return _finalize({"error": policy_reason, "blocked_by_policy": True}, success_override=False)

        clarity_guard = self._check_meta_clarity_tool_intent(method, params)
        if clarity_guard:
            clarity_guard_reason, clarity_guard_code = clarity_guard
            log.warning("Meta-Clarity blockiert %s: %s", method, clarity_guard_reason)
            self._emit_live_status(
                phase="tool_blocked",
                detail="Meta-Clarity blockiert",
                tool_name=method,
            )
            return _finalize(
                {
                    "error": clarity_guard_reason,
                    "blocked_by_policy": True,
                    "blocked_reason": clarity_guard_code,
                },
                success_override=False,
            )

        await self._ensure_remote_tool_names()

        try:
            registry_v2.validate_tool_call(method, **params)
        except ValidationError as e:
            log.error(f"Parameter-Validierungsfehler fuer {method}: {e}")
            self._emit_live_status(
                phase="tool_error",
                detail=f"Validierungsfehler: {e}",
                tool_name=method,
            )
            return _finalize({"error": f"Validierungsfehler: {e}", "validation_failed": True}, success_override=False)
        except ValueError:
            if method not in self._remote_tool_names:
                log.warning(f"Tool '{method}' weder lokal noch remote bekannt")
            else:
                log.debug(f"Tool '{method}' remote bekannt - Server validiert")

        should_skip, loop_reason = self.should_skip_action(method, params)

        if should_skip:
            log.error(f"Tool-Call uebersprungen: {method} (Loop)")
            self._emit_live_status(
                phase="tool_skipped",
                detail=loop_reason or "Loop detected",
                tool_name=method,
            )
            return _finalize(
                {"skipped": True, "reason": loop_reason or "Loop detected", "_loop_warning": loop_reason or "Loop detected"},
                success_override=False,
            )

        if loop_reason:
            log.warning(f"Loop-Warnung fuer {method}: {loop_reason}")

        log.info(f"{method} -> {str(params)[:100]}")

        lane = await self._get_lane()
        log.debug(
            f"Lane {lane.lane_id}: Executing {method} (status={lane.status.value})"
        )

        try:
            request_timeout = self._resolve_tool_http_timeout(method, params)
            resp = await self.http_client.post(
                MCP_URL,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": "1"},
                timeout=request_timeout,
            )
            data = resp.json()

            if "result" in data:
                result = data["result"]
                if loop_reason:
                    if isinstance(result, dict):
                        result["_loop_warning"] = loop_reason
                    else:
                        result = {"value": result, "_loop_warning": loop_reason}
                if isinstance(result, dict):
                    result = registry_v2.normalize_tool_result(method, result)
                self._emit_live_status(
                    phase="tool_done",
                    detail="ok",
                    tool_name=method,
                )
                return _finalize(result, success_override=True)

            if "error" in data:
                error_text = self._format_jsonrpc_error(data["error"])
                self._emit_live_status(
                    phase="tool_error",
                    detail=error_text[:120],
                    tool_name=method,
                )
                return _finalize({"error": error_text}, success_override=False)
            self._emit_live_status(
                phase="tool_error",
                detail="Invalid response",
                tool_name=method,
            )
            return _finalize({"error": "Invalid response"}, success_override=False)
        except Exception as e:
            self._emit_live_status(
                phase="tool_error",
                detail=str(e)[:120],
                tool_name=method,
            )
            if self._bug_logger is None:
                from utils.bug_logger import BugLogger
                self._bug_logger = BugLogger()
            import traceback as _tb
            self._bug_logger.log_bug(
                bug_id=f"tool_exception_{method}",
                severity="high",
                agent=getattr(self, "agent_type", "unknown"),
                error_msg=str(e),
                stack_trace=_tb.format_exc(),
                context={"method": method, "params": str(params)[:300]},
            )
            return _finalize({"error": str(e)}, success_override=False)

    # ------------------------------------------------------------------
    # Screen-Change-Gate
    # ------------------------------------------------------------------

    async def _should_analyze_screen(
        self, roi: Optional[Dict] = None, force: bool = False
    ) -> bool:
        if not self.use_screen_change_gate or force:
            return True

        try:
            now = time.time()
            if now - self._last_screen_check_time > 2.0:
                self._last_screen_check_time = now
                return True

            params = {}
            if roi:
                params["roi"] = roi

            result = await self._call_tool("should_analyze_screen", params)

            if result and result.get("changed"):
                log.debug(
                    f"Screen geaendert - {result.get('info', {}).get('reason', 'unknown')}"
                )
                self._last_screen_check_time = now
                return True
            else:
                log.debug("Screen unveraendert - Cache nutzen")
                return False

        except Exception as e:
            log.warning(f"Screen-Change-Gate Fehler: {e}, analysiere sicherheitshalber")
            return True

    async def _get_screen_state(
        self,
        screen_id: str = "current",
        anchor_specs: Optional[List[Dict]] = None,
        element_specs: Optional[List[Dict]] = None,
        force_analysis: bool = False,
    ) -> Optional[Dict]:
        if not force_analysis and not await self._should_analyze_screen():
            if self.cached_screen_state:
                log.debug("Nutze gecachten ScreenState")
                return self.cached_screen_state

        try:
            self.last_screen_analysis_time = time.time()

            params = {
                "screen_id": screen_id,
                "anchor_specs": anchor_specs or [],
                "element_specs": element_specs or [],
                "extract_ocr": False,
            }

            result = await self._call_tool("analyze_screen_state", params)

            if result and not result.get("error"):
                self.cached_screen_state = result
                log.debug(
                    f"ScreenState analysiert: {len(result.get('elements', []))} Elemente"
                )
                return result
            else:
                log.warning(
                    f"Screen-Analyse fehlgeschlagen: {result.get('error', 'unknown')}"
                )
                return None

        except Exception as e:
            log.error(f"Screen-State Fehler: {e}")
            return None

    # ------------------------------------------------------------------
    # Strukturierte Navigation (v2.0)
    # ------------------------------------------------------------------

    async def _analyze_current_screen(self) -> Optional[Dict]:
        try:
            elements = []

            ocr_result = await self._call_tool("get_all_screen_text", {})
            if ocr_result and ocr_result.get("texts"):
                for i, text_item in enumerate(ocr_result["texts"][:20]):
                    if isinstance(text_item, dict):
                        elements.append(
                            {
                                "name": f"text_{i}",
                                "type": "text",
                                "text": text_item.get("text", ""),
                                "x": text_item.get("x", 0),
                                "y": text_item.get("y", 0),
                                "confidence": text_item.get("confidence", 0.0),
                            }
                        )

            if not elements:
                log.debug("Screen-Analyse: Keine Elemente gefunden")
                return None

            log.info(f"Screen-Analyse: {len(elements)} Elemente gefunden")

            return {
                "screen_id": "current_screen",
                "elements": elements,
                "anchors": [],
            }

        except Exception as e:
            log.error(f"Screen-Analyse fehlgeschlagen: {e}")
            return None

    async def _create_navigation_plan_with_llm(
        self, task: str, screen_state: Dict
    ) -> Optional[Dict]:
        import re as _re

        try:
            elements = screen_state.get("elements", [])
            if not elements:
                log.warning("Keine Elemente fuer ActionPlan verfuegbar")
                return None

            element_list = []
            for i, elem in enumerate(elements[:15]):
                text = elem.get("text", "").strip()
                if text:
                    element_list.append(
                        {
                            "name": elem.get("name", f"elem_{i}"),
                            "text": text[:50],
                            "x": elem.get("x", 0),
                            "y": elem.get("y", 0),
                            "type": elem.get("type", "unknown"),
                        }
                    )

            if not element_list:
                log.warning("Keine Elemente mit Text gefunden")
                return None

            element_summary = "\n".join(
                [
                    f'{i + 1}. {e["name"]}: "{e["text"]}" at ({e["x"]}, {e["y"]})'
                    for i, e in enumerate(element_list)
                ]
            )

            prompt = f"""Erstelle einen ACTION-PLAN fuer diese Aufgabe:

AUFGABE: {task}

VERFUEGBARE ELEMENTE:
{element_summary}

BEISPIEL ACTION-PLAN:
{{
  "task_id": "search_task",
  "description": "Google suchen nach Python",
  "steps": [
    {{"op": "type", "target": "elem_2", "value": "Python", "retries": 2}},
    {{"op": "click", "target": "elem_5", "retries": 2}}
  ]
}}

Antworte NUR mit JSON (keine Markdown, keine Erklaerung):"""

            old_model = self.model
            old_provider = self.provider

            self.model, self.provider = resolve_model_provider_env(
                model_env="REASONING_MODEL",
                provider_env="REASONING_MODEL_PROVIDER",
                fallback_model="qwen/qwq-32b",
                fallback_provider=ModelProvider.OPENROUTER,
            )

            old_thinking = os.environ.get("NEMOTRON_ENABLE_THINKING")
            os.environ["NEMOTRON_ENABLE_THINKING"] = "true"

            try:
                response = await self._call_llm([{"role": "user", "content": prompt}])
            finally:
                self.model = old_model
                self.provider = old_provider
                if old_thinking is not None:
                    os.environ["NEMOTRON_ENABLE_THINKING"] = old_thinking
                else:
                    os.environ.pop("NEMOTRON_ENABLE_THINKING", None)

            plan = extract_json_robust(response)
            if not plan:
                log.warning(f"Kein JSON gefunden in Response: {response[:200]}")
                return None

            if not plan.get("steps") or not isinstance(plan["steps"], list):
                log.warning("ActionPlan hat keine Steps")
                return None

            compatible_plan = {
                "goal": plan.get("description", task),
                "screen_id": screen_state.get("screen_id", "current_screen"),
                "steps": [],
            }

            for step in plan["steps"]:
                compatible_step = {
                    "op": step.get("op", "click"),
                    "target": step.get("target", ""),
                    "params": {},
                    "verify_before": [],
                    "verify_after": [],
                    "retries": step.get("retries", 2),
                }
                if "value" in step:
                    compatible_step["params"]["text"] = step["value"]
                compatible_plan["steps"].append(compatible_step)

            log.info(
                f"ActionPlan erstellt: {compatible_plan['goal']} ({len(compatible_plan['steps'])} Steps)"
            )
            return compatible_plan

        except json.JSONDecodeError as e:
            log.error(f"JSON-Parsing fehlgeschlagen: {e}")
            return None
        except Exception as e:
            log.error(f"ActionPlan-Erstellung fehlgeschlagen: {e}")
            return None

    async def _try_structured_navigation(self, task: str) -> Optional[Dict]:
        try:
            log.info("Versuche strukturierte Navigation...")

            screen_state = await self._analyze_current_screen()
            if not screen_state or not screen_state.get("elements"):
                log.info("Keine Elemente gefunden - nutze regulaeren Flow")
                return None

            action_plan = await self._create_navigation_plan_with_llm(
                task, screen_state
            )
            if not action_plan:
                log.info("ActionPlan-Erstellung fehlgeschlagen - nutze regulaeren Flow")
                return None

            log.info(f"Fuehre ActionPlan aus: {action_plan.get('goal', 'N/A')}")
            result = await self._call_tool(
                "execute_action_plan", {"plan_dict": action_plan}
            )

            if result and result.get("success"):
                return {
                    "success": True,
                    "result": action_plan.get("goal", "Aufgabe erfolgreich"),
                    "state": screen_state,
                }
            else:
                error_msg = "Unknown"
                if isinstance(result, dict):
                    error_msg = (
                        result.get("error")
                        or result.get("error_message")
                        or result.get("message")
                        or "Unknown"
                    )
                log.warning(
                    f"ActionPlan fehlgeschlagen: {error_msg}"
                )
                return None

        except Exception as e:
            log.error(f"Strukturierte Navigation fehlgeschlagen: {e}")
            return None

    def _is_navigation_task(self, task_lower: str) -> bool:
        """Heuristik: Nur echte Navigation/UI-Aufgaben triggern den Screen-Flow."""
        return any(
            re.search(pattern, task_lower) is not None
            for pattern in self.NAVIGATION_TASK_PATTERNS
        )

    def _is_memory_recall_query(self, task_lower: str) -> bool:
        """Erkennt direkte Rückfragen nach bereits besprochenem Inhalt."""
        return any(
            re.search(pattern, task_lower) is not None
            for pattern in self.MEMORY_QUERY_PATTERNS
        )

    async def _try_memory_recall(self, task: str) -> Optional[str]:
        """Fast-Path für Erinnerungsfragen über das Memory-Tool."""
        try:
            self._memory_recall_last_meta = {}
            recall_params: Dict[str, Any] = {"query": task, "n_results": 5}
            if self.conversation_session_id:
                recall_params["session_id"] = self.conversation_session_id
            recall_result = await self._call_tool("recall", recall_params)

            # Rückwärtskompatibel mit älteren Server-Schemas ohne session_id.
            if (
                isinstance(recall_result, dict)
                and recall_result.get("validation_failed")
                and "session_id" in recall_params
            ):
                recall_result = await self._call_tool(
                    "recall",
                    {"query": task, "n_results": 5},
                )
            if not isinstance(recall_result, dict):
                return None

            if recall_result.get("status") != "success":
                return None
            meta = recall_result.get("meta")
            if isinstance(meta, dict):
                self._memory_recall_last_meta = meta

            memories = recall_result.get("memories", [])
            if not memories:
                return "Ich finde dazu gerade keine passende Erinnerung im Gedächtnis."

            lines = []
            for item in memories[:3]:
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                score = item.get("relevance_score")
                if isinstance(score, (int, float)):
                    lines.append(f"- {text} (Relevanz {score:.2f})")
                else:
                    lines.append(f"- {text}")

            if not lines:
                return "Ich habe Erinnerungen gefunden, aber ohne verwertbaren Text."

            return "Das habe ich im Gedächtnis gefunden:\n" + "\n".join(lines)
        except Exception as e:
            log.debug(f"Memory-Recall Fast-Path fehlgeschlagen: {e}")
            return None

    # ------------------------------------------------------------------
    # ROI (Region of Interest) Management (v2.0)
    # ------------------------------------------------------------------

    def _set_roi(self, x: int, y: int, width: int, height: int, name: str = "custom"):
        roi = {"x": x, "y": y, "width": width, "height": height, "name": name}
        self.current_roi = roi
        log.info(f"ROI gesetzt: {name} ({x},{y} {width}x{height})")

    def _clear_roi(self):
        self.current_roi = None
        log.info("ROI geloescht")

    def _push_roi(self, x: int, y: int, width: int, height: int, name: str = "custom"):
        if self.current_roi:
            self.roi_stack.append(self.current_roi)
        self._set_roi(x, y, width, height, name)

    def _pop_roi(self):
        if self.roi_stack:
            self.current_roi = self.roi_stack.pop()
            log.info(f"ROI wiederhergestellt: {self.current_roi['name']}")
        else:
            self._clear_roi()

    async def _detect_dynamic_ui_and_set_roi(self, task: str) -> bool:
        task_lower = task.lower()

        if "google" in task_lower and ("such" in task_lower or "search" in task_lower):
            self._set_roi(x=200, y=100, width=800, height=150, name="google_searchbar")
            log.info(
                "Dynamische UI erkannt: Google Search - ROI auf Suchleiste gesetzt"
            )
            return True

        elif "booking" in task_lower:
            self._set_roi(
                x=100, y=150, width=1000, height=400, name="booking_search_form"
            )
            log.info(
                "Dynamische UI erkannt: Booking.com - ROI auf Suchformular gesetzt"
            )
            return True

        elif "amazon" in task_lower:
            self._set_roi(x=200, y=50, width=900, height=200, name="amazon_search_bar")
            log.info("Dynamische UI erkannt: Amazon - ROI auf Suchleiste gesetzt")
            return True

        return False

    # ------------------------------------------------------------------
    # LLM Calls
    # ------------------------------------------------------------------

    @staticmethod
    def _is_retryable_provider_error_text(text: str) -> bool:
        text = str(text or "").strip().lower()
        if not text:
            return False
        return any(
            needle in text
            for needle in (
                "timeout",
                "timed out",
                "rate limit",
                "429",
                "502",
                "503",
                "504",
                "connection error",
                "connection reset",
                "temporary failure",
                "name resolution",
                "service unavailable",
            )
        )

    @classmethod
    def _is_retryable_provider_error(cls, error: Exception) -> bool:
        return cls._is_retryable_provider_error_text(str(error or ""))

    def _runtime_fallback_override(
        self,
        current_override: Optional[BudgetModelOverride] = None,
    ) -> Optional[BudgetModelOverride]:
        if not self.fallback_model or not self.fallback_provider:
            return None
        effective_provider = current_override.provider if current_override else self.provider
        effective_model = current_override.model if current_override else self.model
        if (effective_model, effective_provider) == (self.fallback_model, self.fallback_provider):
            return None
        return BudgetModelOverride(
            provider=self.fallback_provider,
            model=self.fallback_model,
        )

    async def _execute_llm_call(
        self,
        messages: List[Dict],
        *,
        budget_decision: Optional[LLMBudgetDecision] = None,
        model_override: Optional[BudgetModelOverride] = None,
    ) -> str:
        effective_provider = model_override.provider if model_override else self.provider
        if effective_provider in [
            ModelProvider.OPENAI,
            ModelProvider.ZAI,
            ModelProvider.DASHSCOPE,
            ModelProvider.DEEPSEEK,
            ModelProvider.INCEPTION,
            ModelProvider.NVIDIA,
            ModelProvider.OPENROUTER,
            ModelProvider.GOOGLE,
        ]:
            return await self._call_openai_compatible(
                messages,
                budget_decision=budget_decision,
                model_override=model_override,
            )
        if effective_provider == ModelProvider.DASHSCOPE_NATIVE:
            return await self._call_dashscope_native(
                messages,
                budget_decision=budget_decision,
                model_override=model_override,
            )
        if effective_provider == ModelProvider.ANTHROPIC:
            return await self._call_anthropic(
                messages,
                budget_decision=budget_decision,
                model_override=model_override,
            )
        return f"Error: Provider {effective_provider} nicht unterstuetzt"

    async def _call_llm(self, messages: List[Dict]) -> str:
        try:
            requested_max_tokens = self._get_max_tokens_for_model(self.model)
            budget = evaluate_llm_budget(
                agent=self.agent_type,
                session_id=self.conversation_session_id or "",
                requested_max_tokens=requested_max_tokens,
            )
            if budget.warning:
                log.warning("LLM-Budget %s fuer %s: %s", budget.state, self.agent_type, budget.message)
            if budget.blocked:
                return f"Error: {budget.message}"
            model_override = resolve_soft_budget_model_override(
                agent=self.agent_type,
                provider=self.provider,
                model=self.model,
                decision=budget,
            )
            if model_override:
                log.warning(
                    "LLM-Budget Soft-Limit: downgrade %s/%s -> %s/%s fuer %s",
                    self.provider.value,
                    self.model,
                    model_override.provider.value,
                    model_override.model,
                    self.agent_type,
                )
            try:
                return await self._execute_llm_call(
                    messages,
                    budget_decision=budget,
                    model_override=model_override,
                )
            except Exception as primary_error:
                fallback_override = self._runtime_fallback_override(model_override)
                if fallback_override and self._is_retryable_provider_error(primary_error):
                    log.warning(
                        "LLM-Fallback fuer %s: %s/%s -> %s/%s (%s)",
                        self.agent_type,
                        self.provider.value,
                        self.model,
                        fallback_override.provider.value,
                        fallback_override.model,
                        primary_error,
                    )
                    return await self._execute_llm_call(
                        messages,
                        budget_decision=budget,
                        model_override=fallback_override,
                    )
                raise
        except Exception as e:
            log.error(f"LLM Fehler: {e}")
            return f"Error: {e}"

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """Entfernt <think>...</think> Blöcke aus LLM-Antworten (QwQ, GLM, etc.).

        Behandelt auch unclosed Tags — passiert wenn max_tokens mitten im
        Thinking-Block abschneidet. CrossHair-verifiziert: '<think>' nie im Output.
        """
        if not text or "<think>" not in text:
            return text
        # 1. Vollständige <think>...</think> Blöcke entfernen
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        # 2. Unclosed <think> (kein </think>) — ab <think> bis Ende strippen
        cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    @staticmethod
    def _get_max_tokens_for_model(model: str) -> int:
        """Gibt modell-abhängiges max_tokens zurück.

        Reasoning-Modelle generieren lange <think>-Blöcke vor der eigentlichen
        Action-JSON. 2000 Tokens sind dafür zu knapp — die Antwort wird mitten
        im Thinking-Prozess abgeschnitten, die Action-JSON erscheint nie.
        """
        model_lower = model.lower()
        if any(m in model_lower for m in ["deepseek-reasoner", "deepseek-r1", "qwq", "qvq"]):
            return int(os.getenv("REASONING_MAX_TOKENS", "8000"))
        if "nemotron" in model_lower:
            return int(os.getenv("NEMOTRON_MAX_TOKENS", "4000"))
        return int(os.getenv("DEFAULT_MAX_TOKENS", "2000"))

    def _record_llm_usage(
        self,
        *,
        latency_ms: int,
        success: bool,
        response_payload: Any = None,
        provider_override: Optional[ModelProvider] = None,
        model_override: Optional[str] = None,
    ) -> None:
        try:
            effective_provider = provider_override or self.provider
            effective_model = model_override or self.model
            usage = build_usage_payload(effective_provider, effective_model, response_payload)
            get_improvement_engine().record_llm_usage(
                LLMUsageRecord(
                    trace_id=f"llm-{uuid.uuid4().hex[:12]}",
                    session_id=self.conversation_session_id or "",
                    agent=self.agent_type,
                    provider=effective_provider.value,
                    model=effective_model,
                    input_tokens=int(usage["input_tokens"]),
                    output_tokens=int(usage["output_tokens"]),
                    cached_tokens=int(usage["cached_tokens"]),
                    cost_usd=float(usage["cost_usd"]),
                    latency_ms=max(int(latency_ms or 0), 0),
                    success=bool(success),
                )
            )
        except Exception as e:
            log.debug("LLM-Usage-Aufzeichnung fehlgeschlagen: %s", e)

    async def _call_openai_compatible(
        self,
        messages: List[Dict],
        *,
        budget_decision: Optional[LLMBudgetDecision] = None,
        model_override: Optional[BudgetModelOverride] = None,
    ) -> str:
        effective_provider = model_override.provider if model_override else self.provider
        effective_model = model_override.model if model_override else self.model
        client = self.provider_client.get_client(effective_provider)
        max_tokens = self._get_max_tokens_for_model(self.model)
        if budget_decision and budget_decision.max_tokens_cap:
            max_tokens = min(max_tokens, max(int(budget_decision.max_tokens_cap), 1))

        kwargs = {
            "model": effective_model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": max_tokens,
        }

        if effective_provider == ModelProvider.INCEPTION:
            if os.getenv("MERCURY_DIFFUSING", "false").lower() == "true":
                kwargs["extra_body"] = {"diffusing": True}

        if "nemotron" in self.model.lower():
            enable = os.getenv("NEMOTRON_ENABLE_THINKING", "true").lower() == "true"
            if not enable:
                kwargs["extra_body"] = {
                    "chat_template_kwargs": {"enable_thinking": False}
                }
                kwargs["temperature"] = 0.6
                kwargs["top_p"] = 0.95
            else:
                kwargs["temperature"] = 1.0
                kwargs["top_p"] = 1.0

        if "seed-oss" in self.model.lower():
            budget = int(os.getenv("META_THINKING_BUDGET", "1000"))
            kwargs["extra_body"] = {"thinking_budget": budget}

        if "glm5" in self.model.lower().replace("-", "").replace("/", ""):
            # NVIDIA NIM: Thinking via chat_template_kwargs steuern
            # OpenRouter: Thinking ist automatisch eingebaut, kein extra_body nötig
            if effective_provider == ModelProvider.NVIDIA:
                enable = os.getenv("META_ENABLE_THINKING", "true").lower() == "true"
                kwargs["extra_body"] = {
                    "chat_template_kwargs": {"enable_thinking": enable}
                }
                if enable:
                    kwargs["temperature"] = 1.0

        if effective_provider == ModelProvider.NVIDIA:
            kwargs["timeout"] = int(os.getenv("NVIDIA_TIMEOUT", "120"))

        kwargs = prepare_openai_params(kwargs)

        started = time.perf_counter()
        resp = None
        try:
            resp = await asyncio.to_thread(client.chat.completions.create, **kwargs)
            if not resp.choices or not hasattr(resp.choices[0], "message"):
                self._record_llm_usage(
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    success=False,
                    response_payload=resp,
                    provider_override=effective_provider,
                    model_override=effective_model,
                )
                return ""
            msg = resp.choices[0].message
            content = msg.content

            # deepseek-reasoner: reasoning_content als Fallback wenn content leer.
            # WICHTIG: Kein "Error:" zurückgeben — das würde den Loop sofort beenden.
            # Stattdessen reasoning_content zurückgeben: der Loop schickt dann einen
            # Format-Korrektur-Prompt und das Modell bekommt eine weitere Chance.
            if (not content or not str(content).strip()) and hasattr(msg, "reasoning_content"):
                reasoning = getattr(msg, "reasoning_content", "") or ""
                if reasoning:
                    log.warning("deepseek-reasoner: content leer — gebe reasoning_content zurück (Loop-Retry)")
                    self._record_llm_usage(
                        latency_ms=round((time.perf_counter() - started) * 1000),
                        success=True,
                        response_payload=resp,
                        provider_override=effective_provider,
                        model_override=effective_model,
                    )
                    return self._strip_think_tags(reasoning.strip())

            if isinstance(content, str):
                text = self._strip_think_tags(content)
            elif isinstance(content, list):
                parts: List[str] = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    elif hasattr(item, "text") and isinstance(getattr(item, "text"), str):
                        parts.append(getattr(item, "text"))
                text = self._strip_think_tags("".join(parts).strip())
            else:
                text = self._strip_think_tags(str(content or "").strip())

            self._record_llm_usage(
                latency_ms=round((time.perf_counter() - started) * 1000),
                success=bool(text),
                response_payload=resp,
                provider_override=effective_provider,
                model_override=effective_model,
            )
            return text
        except Exception:
            self._record_llm_usage(
                latency_ms=round((time.perf_counter() - started) * 1000),
                success=False,
                response_payload=resp,
                provider_override=effective_provider,
                model_override=effective_model,
            )
            raise

    async def _call_anthropic(
        self,
        messages: List[Dict],
        *,
        budget_decision: Optional[LLMBudgetDecision] = None,
        model_override: Optional[BudgetModelOverride] = None,
    ) -> str:
        effective_provider = model_override.provider if model_override else ModelProvider.ANTHROPIC
        effective_model = model_override.model if model_override else self.model
        if effective_provider != ModelProvider.ANTHROPIC:
            return await self._call_openai_compatible(
                messages,
                budget_decision=budget_decision,
                model_override=model_override,
            )
        client = self.provider_client.get_client(ModelProvider.ANTHROPIC)
        max_tokens = 2000
        if budget_decision and budget_decision.max_tokens_cap:
            max_tokens = min(max_tokens, max(int(budget_decision.max_tokens_cap), 1))

        system_content = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                chat_messages.append(msg)

        started = time.perf_counter()
        response_payload: Any = None
        try:
            if client:
                resp = await asyncio.to_thread(
                    client.messages.create,
                    model=effective_model,
                    max_tokens=max_tokens,
                    system=system_content,
                    messages=chat_messages,
                )
                response_payload = resp
                text = resp.content[0].text.strip()
            else:
                api_key = self.provider_client.get_api_key(ModelProvider.ANTHROPIC)
                async with httpx.AsyncClient(timeout=120.0) as http:
                    resp = await http.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": api_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": effective_model,
                            "max_tokens": max_tokens,
                            "system": system_content,
                            "messages": chat_messages,
                        },
                    )
                    response_payload = resp.json()
                    text = response_payload["content"][0]["text"].strip()
            self._record_llm_usage(
                latency_ms=round((time.perf_counter() - started) * 1000),
                success=bool(text),
                response_payload=response_payload,
                provider_override=effective_provider,
                model_override=effective_model,
            )
            return text
        except Exception:
            self._record_llm_usage(
                latency_ms=round((time.perf_counter() - started) * 1000),
                success=False,
                response_payload=response_payload,
                provider_override=effective_provider,
                model_override=effective_model,
            )
            raise

    async def _call_dashscope_native(
        self,
        messages: List[Dict],
        *,
        budget_decision: Optional[LLMBudgetDecision] = None,
        model_override: Optional[BudgetModelOverride] = None,
    ) -> str:
        effective_provider = model_override.provider if model_override else ModelProvider.DASHSCOPE_NATIVE
        effective_model = model_override.model if model_override else self.model
        if effective_provider != ModelProvider.DASHSCOPE_NATIVE:
            return await self._call_openai_compatible(
                messages,
                budget_decision=budget_decision,
                model_override=model_override,
            )

        max_tokens = self._get_max_tokens_for_model(effective_model)
        if budget_decision and budget_decision.max_tokens_cap:
            max_tokens = min(max_tokens, max(int(budget_decision.max_tokens_cap), 1))

        response_payload: Any = None
        started = time.perf_counter()
        try:
            provider_client = self.provider_client
            api_key = provider_client.get_api_key(ModelProvider.DASHSCOPE_NATIVE)
            base_url = provider_client.get_base_url(ModelProvider.DASHSCOPE_NATIVE)
            payload = build_dashscope_native_payload(
                model=effective_model,
                messages=messages,
                temperature=0.3,
                max_tokens=max_tokens,
            )
            response = await self.http_client.post(
                dashscope_native_generation_url(base_url, effective_model),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=float(os.getenv("DASHSCOPE_NATIVE_TIMEOUT", "180")),
            )
            try:
                response_payload = response.json()
            except Exception:
                response_payload = None
            response.raise_for_status()

            text = extract_dashscope_native_text(response_payload or {})
            if not text:
                reasoning = extract_dashscope_native_reasoning(response_payload or {})
                if reasoning:
                    text = reasoning
            text = self._strip_think_tags(str(text or "").strip())

            self._record_llm_usage(
                latency_ms=round((time.perf_counter() - started) * 1000),
                success=bool(text),
                response_payload=response_payload,
                provider_override=effective_provider,
                model_override=effective_model,
            )
            return text
        except Exception:
            self._record_llm_usage(
                latency_ms=round((time.perf_counter() - started) * 1000),
                success=False,
                response_payload=response_payload,
                provider_override=effective_provider,
                model_override=effective_model,
            )
            raise

    # ------------------------------------------------------------------
    # Action Parser (delegiert an shared)
    # ------------------------------------------------------------------

    def _parse_action(self, text: str) -> Tuple[Optional[dict], Optional[str]]:
        return parse_action(text)

    @staticmethod
    def _normalize_action_payload(
        action: Any,
        err: Optional[str],
    ) -> Tuple[Optional[dict], Optional[str]]:
        if action is None:
            return None, err
        if isinstance(action, dict):
            return action, err
        return None, err or "Action-JSON muss ein Objekt sein, keine Liste."

    def _format_generate_text_output(self, text: str) -> str:
        """Bereitet generate_text-Ergebnisse nutzerfreundlich auf (falls JSON-Liste)."""
        raw = (text or "").strip()
        if not raw:
            return raw

        cleaned = raw.replace("```json", "").replace("```", "").strip()
        parsed: Any = None
        try:
            parsed = json.loads(cleaned)
        except Exception:
            parsed = None

        cafes: Optional[List[Dict[str, Any]]] = None
        if isinstance(parsed, list):
            cafes = [x for x in parsed if isinstance(x, dict)]
        elif isinstance(parsed, dict):
            value = parsed.get("cafes")
            if isinstance(value, list):
                cafes = [x for x in value if isinstance(x, dict)]

        if not cafes:
            return raw

        lines: List[str] = []
        for idx, cafe in enumerate(cafes[:15], start=1):
            name = str(cafe.get("name", "")).strip()
            desc = str(
                cafe.get("short_description")
                or cafe.get("description")
                or cafe.get("atmosphere")
                or ""
            ).strip()
            if not name:
                continue
            if desc:
                lines.append(f"{idx}. {name} - {desc}")
            else:
                lines.append(f"{idx}. {name}")

        if lines:
            return "\n".join(lines)
        return raw

    def _is_list_request(self, task_lower: str) -> bool:
        """Erkennt, ob der Nutzer explizit eine Liste möchte."""
        patterns = (
            r"\berstelle\s+eine?\s+liste\b",
            r"\bmach\s+eine?\s+liste\b",
            r"\bliste\b",
            r"\blist\b",
            r"\bauflisten\b",
        )
        return any(re.search(p, task_lower) for p in patterns)

    @staticmethod
    def _looks_like_preformatted_list_answer(text: str) -> bool:
        """Bewahrt bereits gut strukturierte Antworten vor erzwungener Umformatierung."""
        stripped = str(text or "").strip()
        if not stripped:
            return False

        if re.search(r"(?m)^\s*(?:[-*]\s+|\d+\.\s+)", stripped):
            return True
        if re.search(r"(?m)^\s{0,3}#{1,6}\s+\S+", stripped):
            return True
        if re.search(r"(?m)^\s*\*\*[^*\n]+\*\*(?:\s*:)?\s*$", stripped):
            return True
        if "\n\n" in stripped and re.search(r"[.!?](?:\s|$)", stripped):
            return True
        return False

    async def _finalize_list_output(self, task: str, result: str) -> str:
        """
        Formatiert Listenanfragen in ein konsistentes Ausgabeformat und speichert sie als Datei.
        """
        primary_task = self._extract_primary_task_text(task)
        task_lower = (primary_task or task or "").lower()
        if not self._is_list_request(task_lower):
            return result

        final_text = (result or "").strip()
        if not final_text:
            return result

        # JSON-Output von generate_text in nummerierte Liste umwandeln.
        if final_text.startswith("[") or final_text.startswith("{") or "```json" in final_text:
            final_text = self._format_generate_text_output(final_text)

        # Falls noch keine klare Listenform vorhanden ist, einfache Zeilen als nummerierte Liste ausgeben.
        if (
            not re.search(r"(?m)^\s*\d+\.\s+", final_text)
            and not self._looks_like_preformatted_list_answer(final_text)
        ):
            raw_lines = [ln.strip(" -\t") for ln in final_text.splitlines() if ln.strip()]
            if raw_lines:
                final_text = "\n".join(
                    f"{i}. {line}" for i, line in enumerate(raw_lines, start=1)
                )

        # Ergebnis zusätzlich persistieren.
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "_", task_lower)[:50].strip("_") or "liste"
        file_path = f"results/{ts}_{slug}.md"
        file_content = f"# Ergebnisliste\n\n{final_text}\n"

        save_obs = await self._call_tool(
            "write_file",
            {"path": file_path, "content": file_content},
        )
        saved_ok = isinstance(save_obs, dict) and save_obs.get("status") == "success"
        self._emit_step_trace(
            action="list_output_persisted",
            output_data={
                "path": file_path,
                "saved": saved_ok,
                "tool_observation_preview": self._preview_value(save_obs, 500),
            },
            status="ok" if saved_ok else "warning",
        )
        if saved_ok:
            return f"{final_text}\n\nGespeichert unter: `{file_path}`"
        return final_text

    async def _finalize_user_output(self, task: str, result: str) -> str:
        softened = self._soften_unproven_verdict_language(result)
        return await self._finalize_list_output(task, softened)

    def _maybe_finalize_after_terminal_tool(self, method: str, obs: Any) -> str | None:
        if method != "restart_timus" or not isinstance(obs, dict):
            return None

        payload = obs
        nested = obs.get("data")
        if isinstance(nested, dict):
            nested_status = str(nested.get("status") or "").strip().lower()
            if nested_status in {"pending_restart", "blocked", "error"}:
                payload = nested

        status = str(payload.get("status") or "").strip().lower()
        mode = str(payload.get("mode") or obs.get("mode") or "").strip() or "full"
        message = str(payload.get("message") or obs.get("message") or "").strip()

        if status == "pending_restart":
            launcher_pid = payload.get("launcher_pid") or obs.get("launcher_pid")
            lines = [
                f"Der Neustart läuft im Hintergrund (Modus: {mode}).",
            ]
            if launcher_pid:
                lines[0] = f"Der Neustart läuft im Hintergrund (Launcher-PID: {launcher_pid}, Modus: {mode})."
            if message:
                lines.append(message)
            lines.append("Die Verbindung kann jetzt kurz unterbrochen sein. Prüfe den Status anschließend erneut.")
            return "\n".join(lines)

        if status in {"blocked", "error"}:
            if message:
                return message
            return f"Neustart konnte nicht gestartet werden (Status: {status})."

        return None

    # ------------------------------------------------------------------
    # Working-Memory Prompt-Injektion
    # ------------------------------------------------------------------

    @staticmethod
    def _env_int_with_aliases(names: List[str], default: int) -> int:
        for name in names:
            raw = str(os.getenv(name, "")).strip()
            if not raw:
                continue
            try:
                return int(raw)
            except ValueError:
                continue
        return default

    @classmethod
    def _resolve_working_memory_settings(cls, task: str) -> Dict[str, int | bool]:
        base_chars = cls._env_int_with_aliases(
            ["WORKING_MEMORY_CHAR_BUDGET", "WM_MAX_CHARS"],
            10000,
        )
        base_related = cls._env_int_with_aliases(
            ["WORKING_MEMORY_MAX_RELATED", "WM_MAX_RELATED"],
            8,
        )
        base_recent_events = cls._env_int_with_aliases(
            ["WORKING_MEMORY_MAX_RECENT_EVENTS", "WM_MAX_EVENTS"],
            15,
        )

        followup_context = any(
            marker in str(task or "")
            for marker in (
                "# FOLLOW-UP CONTEXT",
                "topic_recall:",
                "session_summary:",
                "semantic_recall:",
                "pending_followup_prompt:",
            )
        )

        clarity_contract = cls._extract_meta_clarity_contract(task)
        allowed_sections = tuple(clarity_contract.get("allowed_working_memory_sections") or ())

        if not followup_context:
            settings: Dict[str, int | bool | tuple[str, ...]] = {
                "max_chars": max(600, base_chars),
                "max_related": max(0, base_related),
                "max_recent_events": max(0, base_recent_events),
                "followup_context": False,
                "allowed_sections": allowed_sections,
            }
            clarity_related_raw = clarity_contract.get("max_related_memories", -1)
            clarity_recent_raw = clarity_contract.get("max_recent_events", -1)
            clarity_related = -1 if clarity_related_raw in (None, "") else int(clarity_related_raw)
            clarity_recent = -1 if clarity_recent_raw in (None, "") else int(clarity_recent_raw)
            if clarity_related >= 0:
                settings["max_related"] = clarity_related
            if clarity_recent >= 0:
                settings["max_recent_events"] = clarity_recent
            return settings

        boosted_chars = cls._env_int_with_aliases(
            ["WORKING_MEMORY_FOLLOWUP_CHAR_BUDGET"],
            max(base_chars, min(base_chars + 4000, 18000)),
        )
        boosted_related = cls._env_int_with_aliases(
            ["WORKING_MEMORY_FOLLOWUP_MAX_RELATED"],
            min(max(base_related + 2, base_related), 12),
        )
        boosted_recent = cls._env_int_with_aliases(
            ["WORKING_MEMORY_FOLLOWUP_MAX_RECENT_EVENTS"],
            min(max(base_recent_events + 4, base_recent_events), 24),
        )
        settings = {
            "max_chars": max(600, boosted_chars),
            "max_related": max(0, boosted_related),
            "max_recent_events": max(0, boosted_recent),
            "followup_context": True,
            "allowed_sections": allowed_sections,
        }
        clarity_related_raw = clarity_contract.get("max_related_memories", -1)
        clarity_recent_raw = clarity_contract.get("max_recent_events", -1)
        clarity_related = -1 if clarity_related_raw in (None, "") else int(clarity_related_raw)
        clarity_recent = -1 if clarity_recent_raw in (None, "") else int(clarity_recent_raw)
        if clarity_related >= 0:
            settings["max_related"] = clarity_related
        if clarity_recent >= 0:
            settings["max_recent_events"] = clarity_recent
        return settings

    async def _build_working_memory_context(self, task: str) -> str:
        enabled = os.getenv("WORKING_MEMORY_INJECTION_ENABLED", "true").lower()
        if enabled not in {"1", "true", "yes", "on"}:
            self._working_memory_last_meta = {
                "enabled": False,
                "reason": "disabled_by_env",
                "context_chars": 0,
            }
            return ""

        settings = self._resolve_working_memory_settings(task)
        max_chars = int(settings["max_chars"])
        max_related = int(settings["max_related"])
        max_recent_events = int(settings["max_recent_events"])
        clarity_contract = self._extract_meta_clarity_contract(task)
        memory_query = self._extract_working_memory_query(task) or task

        try:
            from memory.memory_system import memory_manager

            context = await asyncio.to_thread(
                memory_manager.build_working_memory_context,
                memory_query,
                max_chars,
                max_related,
                max_recent_events,
                self.conversation_session_id,
            )
            wm_stats: Dict[str, Any] = {}
            if hasattr(memory_manager, "get_last_working_memory_stats"):
                wm_stats = memory_manager.get_last_working_memory_stats()
            memory_snapshot: Dict[str, Any] = {}
            if hasattr(memory_manager, "get_runtime_memory_snapshot"):
                try:
                    snapshot = memory_manager.get_runtime_memory_snapshot(
                        session_id=self.conversation_session_id
                    )
                    if isinstance(snapshot, dict):
                        memory_snapshot = snapshot
                except Exception:
                    memory_snapshot = {}
            filtered_context = filter_working_memory_context(context or "", clarity_contract)
            self._working_memory_last_meta = {
                "enabled": True,
                "context_chars": len(filtered_context or ""),
                "settings": {
                    "max_chars": max_chars,
                    "max_related": max_related,
                    "max_recent_events": max_recent_events,
                    "followup_context": bool(settings["followup_context"]),
                    "allowed_sections": list(settings.get("allowed_sections") or ()),
                },
                "memory_stats": wm_stats,
                "memory_snapshot": memory_snapshot,
                "meta_clarity_contract": clarity_contract,
                "memory_query_preview": self._preview_value(memory_query, 400),
            }
            if filtered_context:
                log.info(f"Working-Memory-Kontext injiziert ({len(filtered_context)} chars)")
            return filtered_context or ""
        except Exception as e:
            log.debug(f"Working-Memory-Kontext nicht verfügbar (non-critical): {e}")
            self._working_memory_last_meta = {
                "enabled": True,
                "error": str(e),
                "context_chars": 0,
            }
            return ""

    def _inject_working_memory_into_task(self, task: str, working_memory_context: str) -> str:
        if not working_memory_context:
            return task
        return (
            f"{working_memory_context}\n\n"
            f"AKTUELLE_NUTZERANFRAGE:\n{task}\n\n"
            "Bearbeite jetzt ausschließlich die aktuelle Nutzeranfrage."
        )

    def get_runtime_telemetry(self) -> Dict[str, Any]:
        run_duration = None
        if self._run_started_at > 0:
            run_duration = round(max(0.0, time.time() - self._run_started_at), 3)
        return {
            "agent_type": self.agent_type,
            "model": self.model,
            "provider": self.provider.value,
            "run_duration_sec": run_duration,
            "action_count": len(self._task_action_history),
            "active_phase": self._active_phase,
            "active_tool": self._active_tool_name,
            "conversation_session_id": self.conversation_session_id or "",
            "memory_recall": self._memory_recall_last_meta,
            "working_memory": self._working_memory_last_meta,
            "context_budget": self._context_budget_last_meta,
        }

    # ------------------------------------------------------------------
    # Haupt-Loop
    # ------------------------------------------------------------------

    async def run(self, task: str) -> str:
        log.info(f"{self.__class__.__name__} ({self.provider.value})")
        # Run-scope Reset: verhindert, dass alte Loop-Counter ueber mehrere Tasks leaken.
        self.recent_actions = []
        self.last_skip_times = {}
        self.action_call_counts = {}
        self._task_action_history = []
        self._run_started_at = time.time()
        self._active_tool_name = None
        self._memory_recall_last_meta = {}
        self._context_budget_last_meta = {}
        self._current_task_text = task or ""
        self._emit_live_status(
            phase="start",
            detail=f"model={self.model} provider={self.provider.value}",
        )
        self._emit_step_trace(
            action="agent_run_start",
            input_data={
                "task_preview": self._preview_value(task, 400),
                "task_chars": len(task or ""),
            },
            status="started",
            metadata={
                "agent_type": self.agent_type,
                "model": self.model,
                "provider": self.provider.value,
                "max_iterations": self.max_iterations,
                "session_id": self.conversation_session_id or "",
            },
        )

        roi_set = await self._detect_dynamic_ui_and_set_roi(task)
        clarity_contract_for_turn = self._extract_meta_clarity_contract(task)
        skip_blackboard_enrichment = (
            str(self.agent_type or "").strip().lower() == "meta"
            and bool(clarity_contract_for_turn.get("direct_answer_required"))
        )

        # M9: Blackboard-Kontext anreichern
        if (
            not skip_blackboard_enrichment
            and os.getenv("AUTONOMY_BLACKBOARD_ENABLED", "true").lower() == "true"
        ):
            try:
                from memory.agent_blackboard import get_blackboard
                bb_entries = get_blackboard().search(task[:80], limit=3)
                if bb_entries:
                    bb_ctx = "\n# Bekannte Informationen (Agent-Blackboard):\n"
                    for e in bb_entries:
                        val_str = str(e["value"])[:200]
                        bb_ctx += f"- [{e['agent']}:{e['topic']}] {e['key']}: {val_str}\n"
                    task = task + "\n" + bb_ctx
            except Exception:
                pass

        primary_task_text = self._extract_primary_task_text(task) or str(task or "")
        task_lower = primary_task_text.lower()
        is_memory_query = self._is_memory_recall_query(task_lower)

        if is_memory_query:
            memory_answer = await self._try_memory_recall(primary_task_text)
            if memory_answer:
                if roi_set:
                    self._clear_roi()
                self._task_action_history = [
                    {
                        "method": "recall",
                        "params": {"query": primary_task_text, "n_results": 5},
                        "result": memory_answer[:200],
                    }
                ]
                self._emit_live_status(phase="memory_recall", detail="Fast-Path genutzt")
                self._emit_step_trace(
                    action="memory_fastpath_hit",
                    output_data={
                        "answer_preview": self._preview_value(memory_answer, 600),
                        "answer_chars": len(memory_answer),
                    },
                )
                await self._run_reflection(task, memory_answer, success=True)
                return memory_answer

        is_navigation_task = self._is_navigation_task(task_lower)

        if is_navigation_task:
            structured_result = await self._try_structured_navigation(primary_task_text)
            if structured_result and structured_result.get("success"):
                log.info(
                    f"Strukturierte Navigation erfolgreich: {structured_result['result']}"
                )
                self._emit_live_status(
                    phase="structured_nav",
                    detail="ActionPlan erfolgreich",
                )
                self._emit_step_trace(
                    action="structured_navigation_success",
                    output_data={
                        "result_preview": self._preview_value(
                            structured_result.get("result", ""), 500
                        )
                    },
                )
                if roi_set:
                    self._clear_roi()
                # Track structured nav action for reflection
                self._task_action_history.append({
                    "method": "structured_navigation",
                    "params": {"task": task},
                    "result": structured_result.get("result", "")
                })
                await self._run_reflection(task, structured_result.get("result", ""))
                return structured_result["result"]
            else:
                log.info(
                    "Strukturierte Navigation nicht moeglich - nutze regulaeren Flow"
                )
                self._emit_step_trace(
                    action="structured_navigation_fallback",
                    status="warning",
                )

        # Clear action history for new task
        self._task_action_history = []
        working_memory_query = self._extract_working_memory_query(task)
        working_memory_context = await self._build_working_memory_context(task)
        task_with_context = self._inject_working_memory_into_task(
            task, working_memory_context
        )
        self._emit_step_trace(
            action="working_memory_injected",
            output_data={
                "query_chars": len(working_memory_query or ""),
                "query_preview": self._preview_value(working_memory_query, 500),
                "context_chars": len(working_memory_context or ""),
                "context_preview": self._preview_value(working_memory_context, 700),
            },
            metadata={"vision_enabled": self._vision_enabled},
        )

        use_vision = is_navigation_task and self._vision_enabled
        if use_vision:
            log.info("Multimodal-Modus: Screenshots werden an LLM gesendet")
            initial_screenshot = await asyncio.to_thread(
                self._capture_screenshot_base64
            )
            initial_msg = self._build_vision_message(task_with_context, initial_screenshot)
        else:
            initial_msg = {"role": "user", "content": task_with_context}

        messages = [
            {"role": "system", "content": self.system_prompt},
            initial_msg,
        ]
        last_generate_text_output: str = ""
        empty_reply_streak = 0

        for step in range(1, self.max_iterations + 1):
            messages = self._enforce_context_budget(messages)
            self._emit_live_status(
                phase="thinking",
                step=step,
                total_steps=self.max_iterations,
            )
            last_msg = messages[-1] if messages else {}
            last_content = last_msg.get("content", "") if isinstance(last_msg, dict) else ""
            self._emit_step_trace(
                action="llm_request",
                input_data={
                    "step": step,
                    "messages_count": len(messages),
                    "last_role": (
                        last_msg.get("role", "")
                        if isinstance(last_msg, dict)
                        else ""
                    ),
                    "last_message_preview": self._preview_value(last_content, 400),
                },
            )
            reply = await self._call_llm(messages)
            if not (reply or "").strip():
                empty_reply_streak += 1
                self._emit_step_trace(
                    action="empty_llm_reply",
                    output_data={"step": step, "streak": empty_reply_streak},
                    status="warning",
                )
            else:
                empty_reply_streak = 0
            self._emit_step_trace(
                action="llm_reply",
                output_data={
                    "step": step,
                    "reply_chars": len(reply or ""),
                    "reply_preview": self._preview_value(reply, 900),
                    "contains_final_answer": "Final Answer:" in (reply or ""),
                },
            )
            if (
                empty_reply_streak >= 2
                and last_generate_text_output
            ):
                final_result = self._format_generate_text_output(last_generate_text_output)
                final_result = await self._finalize_user_output(task, final_result)
                self._emit_live_status(
                    phase="final",
                    detail="Fallback: generate_text übernommen",
                    step=step,
                    total_steps=self.max_iterations,
                )
                self._emit_step_trace(
                    action="fallback_final_from_generate_text",
                    output_data={
                        "step": step,
                        "final_chars": len(final_result),
                        "final_preview": self._preview_value(final_result, 900),
                    },
                    status="completed",
                )
                if roi_set:
                    self._clear_roi()
                await self._run_reflection(task, final_result, success=True)
                return final_result

            if reply.startswith("Error"):
                self._emit_live_status(
                    phase="error",
                    detail=reply[:120],
                    step=step,
                    total_steps=self.max_iterations,
                )
                if roi_set:
                    self._clear_roi()
                self._emit_step_trace(
                    action="llm_error",
                    output_data={
                        "step": step,
                        "error_preview": self._preview_value(reply, 800),
                    },
                    status="error",
                )
                await self._run_reflection(task, reply, success=False)
                return reply
            action: Optional[dict] = None
            err: Optional[str] = None
            should_append_reply = True

            if "Final Answer:" in reply:
                action, err = self._parse_action(reply)
                action, err = self._normalize_action_payload(action, err)
                if self._should_salvage_embedded_final_answer_action(task, reply, action):
                    self._emit_live_status(
                        phase="action_salvage",
                        detail=str(action.get("method") or "")[:120],
                        step=step,
                        total_steps=self.max_iterations,
                    )
                    self._emit_step_trace(
                        action="embedded_final_answer_action_salvaged",
                        output_data={
                            "step": step,
                            "method": str(action.get("method") or ""),
                            "reply_preview": self._preview_value(reply, 900),
                        },
                        status="warning",
                    )
                else:
                    final_result = self._extract_final_answer_body(reply)
                    correction_prompt = self._build_meta_frame_answer_redirect_prompt(task, final_result)
                    if correction_prompt:
                        messages.append({"role": "assistant", "content": reply})
                        messages.append({"role": "user", "content": correction_prompt})
                        self._emit_live_status(
                            phase="answer_guard",
                            detail="meta_frame_answer_rejected",
                            step=step,
                            total_steps=self.max_iterations,
                        )
                        self._emit_step_trace(
                            action="meta_frame_answer_rejected",
                            output_data={
                                "step": step,
                                "reply_preview": self._preview_value(final_result, 800),
                            },
                            status="warning",
                        )
                        continue
                    final_result = await self._finalize_user_output(task, final_result)
                    self._emit_live_status(
                        phase="final",
                        detail=f"{len(final_result)} chars",
                        step=step,
                        total_steps=self.max_iterations,
                    )
                    if roi_set:
                        self._clear_roi()
                    self._emit_step_trace(
                        action="final_answer_detected",
                        output_data={
                            "step": step,
                            "final_preview": self._preview_value(final_result, 800),
                            "final_chars": len(final_result),
                        },
                        status="completed",
                    )
                    await self._run_reflection(task, final_result, success=True)
                    return final_result
            else:
                action, err = self._parse_action(reply)
                action, err = self._normalize_action_payload(action, err)

            if should_append_reply:
                messages.append({"role": "assistant", "content": reply})

            if not action:
                # Implicit Final Answer: LLM schrieb Abschluss-Text ohne Action-JSON
                if self._looks_like_implicit_final_answer(reply):
                    final_result = reply
                    correction_prompt = self._build_meta_frame_answer_redirect_prompt(task, final_result)
                    if correction_prompt:
                        messages.append({"role": "assistant", "content": reply})
                        messages.append({"role": "user", "content": correction_prompt})
                        self._emit_live_status(
                            phase="answer_guard",
                            detail="meta_frame_answer_rejected",
                            step=step,
                            total_steps=self.max_iterations,
                        )
                        self._emit_step_trace(
                            action="meta_frame_answer_rejected",
                            output_data={
                                "step": step,
                                "reply_preview": self._preview_value(final_result, 800),
                            },
                            status="warning",
                        )
                        continue
                    final_result = await self._finalize_user_output(task, final_result)
                    self._emit_live_status(
                        phase="final",
                        detail=f"implicit final answer ({len(final_result)} chars)",
                        step=step,
                        total_steps=self.max_iterations,
                    )
                    self._emit_step_trace(
                        action="implicit_final_answer",
                        output_data={
                            "step": step,
                            "final_preview": self._preview_value(final_result, 800),
                            "final_chars": len(final_result),
                        },
                        status="completed",
                    )
                    if roi_set:
                        self._clear_roi()
                    await self._run_reflection(task, final_result, success=True)
                    return final_result

                if (err or "").strip().lower() == "kein json gefunden" and self._looks_like_salvageable_parse_error_answer(reply):
                    correction_prompt = self._build_meta_frame_answer_redirect_prompt(task, reply.strip())
                    if correction_prompt:
                        messages.append({"role": "assistant", "content": reply})
                        messages.append({"role": "user", "content": correction_prompt})
                        self._emit_live_status(
                            phase="answer_guard",
                            detail="meta_frame_answer_rejected",
                            step=step,
                            total_steps=self.max_iterations,
                        )
                        self._emit_step_trace(
                            action="meta_frame_answer_rejected",
                            output_data={
                                "step": step,
                                "reply_preview": self._preview_value(reply, 800),
                            },
                            status="warning",
                        )
                        continue
                    final_result = await self._finalize_user_output(task, reply.strip())
                    self._emit_live_status(
                        phase="final",
                        detail=f"parse salvage ({len(final_result)} chars)",
                        step=step,
                        total_steps=self.max_iterations,
                    )
                    self._emit_step_trace(
                        action="parse_error_salvaged_final_answer",
                        output_data={
                            "step": step,
                            "final_preview": self._preview_value(final_result, 800),
                            "final_chars": len(final_result),
                        },
                        status="completed",
                    )
                    if roi_set:
                        self._clear_roi()
                    await self._run_reflection(task, final_result, success=True)
                    return final_result

                self._emit_live_status(
                    phase="parse_error",
                    detail=(err or "Kein JSON")[:120],
                    step=step,
                    total_steps=self.max_iterations,
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Fehler: {err}. "
                            "Antworte AUSSCHLIESSLICH mit einem dieser zwei Formate:\n\n"
                            "Format 1 — Tool aufrufen:\n"
                            "Action: {\"method\": \"tool_name\", \"params\": {...}}\n\n"
                            "Format 2 — Aufgabe abschliessen:\n"
                            "Final Answer: [deine Antwort hier]\n\n"
                            "KEIN erklaerenden Text davor oder danach. "
                            "Kein Markdown. Nur eines der beiden Formate."
                        ),
                    }
                )
                self._emit_step_trace(
                    action="parse_error",
                    output_data={
                        "step": step,
                        "error": err or "Kein JSON",
                        "reply_preview": self._preview_value(reply, 900),
                    },
                    status="warning",
                )
                continue

            method = action.get("method", "")
            params = action.get("params", {})
            self._emit_step_trace(
                action="action_parsed",
                input_data={
                    "step": step,
                    "method": method,
                    "params_preview": self._preview_value(params, 800),
                },
            )

            obs = await self._call_tool(method, params)
            self._emit_step_trace(
                action="tool_observation",
                input_data={"step": step, "method": method},
                output_data={
                    "observation_type": type(obs).__name__,
                    "observation_preview": self._preview_value(
                        self._sanitize_observation(obs), 950
                    ),
                },
            )
            if (
                method == "generate_text"
                and isinstance(obs, dict)
                and obs.get("status") == "success"
                and isinstance(obs.get("text"), str)
                and obs.get("text", "").strip()
            ):
                last_generate_text_output = obs["text"].strip()
            
            # Track action for reflection
            self._task_action_history.append({
                "method": method,
                "params": params,
                "result": str(obs)[:200] if obs else None,
                "observation": self._sanitize_observation(obs),
            })

            terminal_result = self._maybe_finalize_after_terminal_tool(method, obs)
            if terminal_result is not None:
                if roi_set:
                    self._clear_roi()
                self._emit_step_trace(
                    action="terminal_tool_finalize",
                    output_data={
                        "method": method,
                        "status": getattr(obs, "get", lambda *_: None)("status") if isinstance(obs, dict) else None,
                        "final_preview": self._preview_value(terminal_result, 500),
                    },
                    status="completed",
                )
                self._emit_live_status(phase="final", step=step, total_steps=self.max_iterations)
                await self._run_reflection(task, terminal_result, success=True)
                return terminal_result
            
            self._handle_file_artifacts(obs)

            obs_text = f"Observation: {json.dumps(self._sanitize_observation(obs), ensure_ascii=False)}"
            obs_text = self._compact_message_content_for_budget(
                obs_text,
                max_tokens=max(
                    120,
                    int(os.getenv("AGENT_OBSERVATION_HISTORY_MAX_TOKENS", "320")),
                ),
            )
            if use_vision:
                screenshot_b64 = await asyncio.to_thread(
                    self._capture_screenshot_base64
                )
                messages.append(self._build_vision_message(obs_text, screenshot_b64))
            else:
                messages.append({"role": "user", "content": obs_text})

            redirect_prompt = self._build_meta_clarity_delegate_redirect_prompt(task, method, obs)
            if redirect_prompt:
                messages.append({"role": "user", "content": redirect_prompt})
                self._emit_step_trace(
                    action="meta_clarity_delegate_redirect",
                    output_data={
                        "step": step,
                        "method": method,
                        "redirect_preview": self._preview_value(redirect_prompt, 500),
                    },
                    status="warning",
                )

            closeout_prompt = self._build_meta_clarity_closeout_prompt(task, method, obs)
            if closeout_prompt:
                messages.append({"role": "user", "content": closeout_prompt})
                self._emit_step_trace(
                    action="meta_clarity_closeout_enforced",
                    output_data={
                        "step": step,
                        "method": method,
                        "closeout_preview": self._preview_value(closeout_prompt, 500),
                    },
                    status="warning",
                )

        if roi_set:
            self._clear_roi()
        self._emit_live_status(phase="limit", detail="max iterations erreicht")
        self._emit_step_trace(
            action="iteration_limit_reached",
            output_data={"max_iterations": self.max_iterations},
            status="error",
        )
        
        await self._run_reflection(task, "Limit erreicht", success=False)
        return "Limit erreicht."

    async def _run_reflection(
        self, 
        task: str, 
        result: str, 
        success: bool = True
    ) -> None:
        """
        Fuehrt Post-Task Reflexion aus und speichert Learnings.
        
        Wird automatisch nach Task-Abschluss aufgerufen.
        """
        if not self._reflection_enabled:
            return
        
        try:
            # Lazy import to avoid circular dependency
            from memory.reflection_engine import get_reflection_engine
            
            engine = get_reflection_engine()
            
            # Set memory manager if available
            if engine.memory is None:
                try:
                    from memory.memory_system import memory_manager
                    engine.set_memory_manager(memory_manager)
                except ImportError:
                    pass
            
            # Set LLM client if available
            if engine.llm is None and hasattr(self, 'provider_client'):
                try:
                    engine.set_llm_client(
                        self.provider_client.get_client(ModelProvider.OPENAI)
                    )
                except Exception:
                    # Fallback: ReflectionEngine kann MultiProviderClient selbst auflösen
                    engine.set_llm_client(self.provider_client)
            
            # Run reflection (mit 30s Timeout, damit ein hängender LLM-Call nicht blockiert)
            reflection = await asyncio.wait_for(
                engine.reflect_on_task(
                    task={"description": task, "type": self.agent_type},
                    actions=self._task_action_history,
                    result={"success": success, "output": result}
                ),
                timeout=30.0,
            )

            if reflection:
                log.debug(
                    f"🪞 Reflexion: {len(reflection.what_worked)} positiv, "
                    f"{len(reflection.what_failed)} negativ"
                )

        except asyncio.TimeoutError:
            log.warning("Reflection Timeout (>30s) — übersprungen")
        except Exception as e:
            log.warning("Reflection fehlgeschlagen (nicht kritisch): %s", e)

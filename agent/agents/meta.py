"""
MetaAgent — Koordinator mit Skill-Orchestrierung + Autonomie-Kontext.

Erweiterungen gegenüber BaseAgent:
  - Kontext: Aktive Ziele, offene Tasks, Blackboard, letzte Reflexion, Trigger
  - max_iterations=30 für mehrstufige Koordinations-Workflows
  - Skill-Orchestrierung: wählt automatisch passende Skills aus skills/
  - create_visual_plan(): Nemotron-gestützte Browser-Planung
  - Partial-Result-Erkennung mit Koordinator-Hinweis
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.base_agent import BaseAgent
from agent.prompts import META_SYSTEM_PROMPT
from orchestration.adaptive_plan_memory import get_adaptive_plan_memory
from orchestration.meta_orchestration import (
    build_meta_feedback_targets,
    resolve_adaptive_plan_adoption,
    resolve_runtime_goal_gap_stage,
    resolve_orchestration_recipe,
)
from orchestration.self_selected_strategy import classify_strategy_error

log = logging.getLogger("TimusAgent-v4.4")


from agent.shared.json_utils import extract_json_robust  # noqa: F401 - re-exported


class MetaAgent(BaseAgent):
    _RECIPE_DIRECT_RESULT_IDS = {
        "youtube_light_research",
        "location_local_search",
        "simple_live_lookup",
        "simple_live_lookup_document",
    }
    _META_HANDOFF_HEADER = "# META ORCHESTRATION HANDOFF"
    _ORIGINAL_TASK_HEADER = "# ORIGINAL USER TASK"
    _SPECIALIST_TOOL_AGENT_MAP = {
        "open_url": "research",
        "start_deep_research": "research",
        "generate_research_report": "research",
        "verify_fact": "research",
        "verify_multiple_facts": "research",
        "generate_image": "creative",
        "generate_text": "creative",
        "create_pdf": "document",
        "create_docx": "document",
        "send_email": "communication",
        "run_command": "shell",
        "run_script": "shell",
        "add_cron": "shell",
        "take_screenshot": "visual",
        "click_element": "visual",
        "type_in_field": "visual",
        "should_analyze_screen": "visual",
        "analyze_screen_state": "visual",
        "get_all_screen_text": "visual",
        "read_text_from_screen": "visual",
        "find_element_by_description": "visual",
        "find_text_coordinates": "visual",
        "find_ui_element_by_text": "visual",
        "find_all_text_occurrences": "visual",
        "verify_screen_condition": "visual",
        "execute_action_plan": "visual",
        "execute_visual_task": "visual",
        "execute_visual_task_quick": "visual",
    }

    # Koordinator darf Spezialisten-Tools NIE direkt aufrufen — nur per Delegation.
    # Philosophie: Meta-Agent = Orchestrator, nicht Ausführer.
    # Je mehr er direkt tut, desto weniger delegiert er — und desto mehr Fehler macht er.
    SYSTEM_ONLY_TOOLS = BaseAgent.SYSTEM_ONLY_TOOLS | {
        # Shell / System — immer über shell- oder system-Agent
        "run_command",
        "run_script",
        "add_cron",
        # Dateioperationen — über executor oder shell
        "write_file",
        "read_file",
        "delete_file",
        "list_directory",
        # Code-Generierung — über developer-Agent (inkl. AST-Validierung)
        "generate_code",
        "implement_feature",
        "create_tool_from_pattern",
        # Tiefe Recherche — über research-Agent (inkl. Verifikation + Report)
        "start_deep_research",
        "generate_research_report",
        "verify_fact",
        "verify_multiple_facts",
        # Bild-Generierung — über creative-Agent (inkl. Prompt-Optimierung)
        "generate_image",
        "generate_text",
        # Dokumente — über document-Agent
        "create_pdf",
        "create_docx",
        # E-Mail senden — über communication-Agent
        "send_email",
        # Screenshots / Browser — über visual-Agent
        "take_screenshot",
        "click_element",
        "type_in_field",
        # UI/Vision-Tools — ALLE über visual-Agent, NIE direkt vom Meta-Agent
        "execute_action_plan",
        "execute_visual_task",
        "execute_visual_task_quick",
        "should_analyze_screen",
        "analyze_screen_state",
        "get_all_screen_text",
        "read_text_from_screen",
        "find_element_by_description",
        "find_text_coordinates",
        "find_ui_element_by_text",
        "find_all_text_occurrences",
        "verify_screen_condition",
        "get_screen_change_stats",
        "reset_screen_detector",
        "set_change_threshold",
        "set_active_monitor",
        "list_monitors",
        "visual_agent_health",
    }

    @classmethod
    def _filter_tools_for_meta(cls, tools_description: str) -> str:
        """
        Entfernt Spezialisten-Tool-Blöcke aus der Tools-Beschreibung.
        Der Meta-Agent soll diese Tools gar nicht erst sehen — er delegiert immer.
        Jeder Tool-Block beginnt mit dem Tool-Namen als erstem Wort einer Zeile.
        """
        lines = tools_description.splitlines(keepends=True)
        filtered = []
        skip = False
        hidden_tool_names = cls.SYSTEM_ONLY_TOOLS | {"open_url"}
        for line in lines:
            stripped = line.strip()
            # Neuer Tool-Block beginnt (Name am Zeilenanfang, kein Einzug)
            first_word = stripped.split()[0].rstrip(":") if stripped else ""
            if first_word in hidden_tool_names:
                skip = True
            elif stripped and not line[0].isspace() and first_word and skip:
                skip = False  # Nächster Block beginnt
            if not skip:
                filtered.append(line)
        return "".join(filtered)

    def __init__(self, tools_description_string: str, *, skip_model_validation: bool = False):
        filtered = self._filter_tools_for_meta(tools_description_string)
        super().__init__(
            META_SYSTEM_PROMPT,
            filtered,
            30,
            "meta",
            skip_model_validation=skip_model_validation,
        )

        # Meta-Agent ist Orchestrator, kein Visual-Agent.
        # Capability-Map enthält "browser"/"navigation" → würde sonst fälschlich
        # is_navigation_task=True triggern und Screenshot an nicht-Vision-Modell senden.
        self._vision_enabled = False

        self.skill_registry = None
        self.active_skills: list = []
        self._init_skill_system()

    @staticmethod
    def _build_research_delegation_task(method: str, params: dict) -> str:
        query = str(params.get("query") or params.get("topic") or "").strip()
        focus_areas = params.get("focus_areas")
        format_name = str(params.get("format") or "markdown").strip()
        session_id = str(params.get("session_id") or "").strip()

        if method == "start_deep_research":
            lines = [
                f"Fuehre eine Deep-Research zum Thema '{query}' durch.",
                "Erstelle am Ende den finalen Forschungsbericht mit Artefakten.",
            ]
            if isinstance(focus_areas, list) and focus_areas:
                lines.append("Fokusbereiche: " + ", ".join(str(x).strip() for x in focus_areas if str(x).strip()))
            return " ".join(lines)

        if method == "generate_research_report":
            lines = [f"Generiere den finalen Forschungsbericht im Format '{format_name}'."]
            if session_id:
                lines.append(f"Nutze dabei unbedingt die bestehende Research-Session '{session_id}'.")
            return " ".join(lines)

        return ""

    @staticmethod
    def _shorten(value: Any, limit: int = 280) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    @staticmethod
    def _strip_location_context_block(text: str) -> str:
        """Entfernt den # LIVE LOCATION CONTEXT Block aus einer Nutzeranfrage.

        Der Block ist mehrzeilig und würde den zeilenbasierten Handoff-Parser
        (delegation_handoff.py) korrumpieren. Der Executor holt die Location
        sowieso selbst per get_current_location_context().
        """
        cleaned = re.sub(
            r"^\s*#\s*live location context\b.*?"
            r"(?:use this location only for nearby, routing, navigation,"
            r" or explicit place-context tasks\.?\s*)",
            "",
            str(text or ""),
            flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
        ).strip()
        return cleaned if cleaned else str(text or "").strip()

    @classmethod
    def _build_specialist_delegation_task(cls, method: str, params: Dict[str, Any]) -> str:
        if method == "open_url":
            url = cls._shorten(params.get("url"))
            return f"Analysiere den Inhalt dieser URL und extrahiere die relevanten Informationen: {url}".strip()

        if method in {"start_deep_research", "generate_research_report"}:
            return cls._build_research_delegation_task(method, params)

        if method in {"verify_fact", "verify_multiple_facts"}:
            claim = cls._shorten(params.get("claim") or params.get("claims") or params.get("query"))
            return f"Pruefe und verifiziere diese Aussage sauber und mit Quellen: {claim}".strip()

        if method in {"generate_image", "generate_text"}:
            prompt = cls._shorten(params.get("prompt") or params.get("text") or params.get("description"))
            size = str(params.get("size") or "").strip()
            task = f"Erstelle das angeforderte kreative Artefakt: {prompt}".strip()
            if size:
                task += f" Zielgroesse: {size}."
            return task

        if method in {"create_pdf", "create_docx"}:
            title = cls._shorten(params.get("title") or params.get("filename") or "")
            content = cls._shorten(params.get("content") or params.get("text") or params.get("markdown"))
            fmt = "PDF" if method == "create_pdf" else "DOCX"
            task = f"Erstelle ein {fmt}-Dokument."
            if title:
                task += f" Titel: {title}."
            if content:
                task += f" Inhalt: {content}"
            return task

        if method == "send_email":
            recipient = cls._shorten(params.get("to") or params.get("recipient") or params.get("email"))
            subject = cls._shorten(params.get("subject"))
            body = cls._shorten(params.get("body") or params.get("content") or params.get("message"))
            attachment = cls._shorten(params.get("attachment_path") or params.get("attachment"))
            task = f"Sende eine E-Mail an {recipient}."
            if subject:
                task += f" Betreff: {subject}."
            if body:
                task += f" Inhalt: {body}"
            if attachment:
                task += f" Anhang: {attachment}."
            return task

        if method in {"run_command", "run_script", "add_cron"}:
            command = cls._shorten(params.get("command") or params.get("script_path") or params.get("script"))
            return f"Fuehre die Shell-Aufgabe sicher aus: {command}".strip()

        if method in {
            "take_screenshot",
            "click_element",
            "type_in_field",
            "should_analyze_screen",
            "analyze_screen_state",
            "get_all_screen_text",
            "read_text_from_screen",
            "find_element_by_description",
            "find_text_coordinates",
            "find_ui_element_by_text",
            "find_all_text_occurrences",
            "verify_screen_condition",
        }:
            detail = cls._shorten(params.get("description") or params.get("text") or params.get("selector"))
            if method in {"get_all_screen_text", "read_text_from_screen"}:
                return (
                    f"Lies den sichtbaren Bildschirmtext ueber den Visual-Agenten aus. "
                    f"Kontext: {detail}"
                ).strip()
            if method in {"should_analyze_screen", "analyze_screen_state", "verify_screen_condition"}:
                return (
                    f"Pruefe den aktuellen Bildschirmzustand ueber den Visual-Agenten. "
                    f"Kontext: {detail}"
                ).strip()
            return f"Fuehre die visuelle UI-Aufgabe aus: {method}. Kontext: {detail}".strip()

        if method in {"execute_action_plan", "execute_visual_task", "execute_visual_task_quick"}:
            detail = cls._shorten(params.get("task") or params.get("instruction") or params.get("goal"))
            return f"Fuehre die visuelle Aufgabe aus: {detail}".strip()

        return ""

    @staticmethod
    def _is_live_lookup_task(task: str) -> bool:
        text = str(task or "").lower()
        if not text:
            return False

        direct_markers = (
            "preistabelle",
            "pricing",
            "preis pro",
            "preise pro",
            "aktuelle preise",
            "aktuellen preisen",
            "tokenpreise",
            "token preise",
            "live recherche",
            "live-recherche",
            "aktuelle infos",
            "aktuelle informationen",
            "neueste nachrichten",
            "science news",
            "wissenschaftsnews",
            "wissenschaft news",
            "wetter",
            "temperatur",
            "regen",
            "wer ist",
            "ceo",
            "präsident",
            "praesident",
            "vorstand",
            "kino",
            "filme",
            "cafes",
            "cafés",
            "kaffee",
            "restaurant",
            "restaurants",
            "in meiner nähe",
            "in meiner naehe",
            "nahe mir",
            "nearby",
            "latest",
            "current pricing",
        )
        if any(marker in text for marker in direct_markers):
            return True

        freshness_markers = (
            "aktuell",
            "aktuelle",
            "aktuellen",
            "heute",
            "jetzt",
            "live",
            "neueste",
            "latest",
            "current",
            "stand ",
        )
        lookup_markers = (
            "preis",
            "preise",
            "pricing",
            "kosten",
            "vergleich",
            "tabelle",
            "auflisten",
            "liste",
            "nachrichten",
            "news",
            "kurs",
            "modell",
            "modelle",
            "wissenschaft",
            "wetter",
            "ceo",
            "präsident",
            "praesident",
            "vorstand",
            "kino",
            "film",
            "filme",
            "cafe",
            "cafés",
            "cafes",
            "restaurant",
            "restaurants",
        )
        return any(marker in text for marker in freshness_markers) and any(
            marker in text for marker in lookup_markers
        )

    @staticmethod
    def _looks_like_stale_training_fallback(result: str) -> bool:
        text = str(result or "").lower()
        fallback_markers = (
            "trainingsdaten",
            "trainingswissen",
            "keine live-recherche",
            "nicht live-recherchiert",
            "nicht live recherchiert",
            "live-recherche durchführen",
            "live recherche durchführen",
            "system-overflow",
            "context-limit überschritten",
            "kontext-overflow",
        )
        return any(marker in text for marker in fallback_markers)

    def _guard_live_lookup_output(self, task: str, result: str) -> str:
        if not self._is_live_lookup_task(task):
            return result
        if not self._looks_like_stale_training_fallback(result):
            return result

        log.warning("MetaAgent blockiert Trainingsdaten-Fallback fuer Live-Lookup.")
        self._emit_step_trace(
            action="live_lookup_guard_triggered",
            output_data={
                "task_preview": self._shorten(task, limit=180),
                "result_preview": self._shorten(result, limit=220),
            },
            status="warning",
        )
        return (
            "Ich konnte die angefragten aktuellen Daten gerade nicht verifiziert live abrufen. "
            "Der Live-Pfad ist fehlgeschlagen, deshalb liefere ich bewusst keine unverifizierte "
            "Ersatzliste. Starte die Anfrage bitte erneut oder ich reduziere sie auf 2-3 "
            "offizielle Quellen fuer einen kompakten Live-Lookup."
        )

    @classmethod
    def _build_specialist_handoff_payload(
        cls,
        specialist_agent: str,
        method: str,
        params: Dict[str, Any],
        task: str,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "target_agent": specialist_agent,
            "goal": task,
            "expected_output": "Spezialistenergebnis",
            "success_signal": "Belastbares Ergebnis geliefert",
            "constraints": [],
            "handoff_data": {"source_tool": method},
        }

        if specialist_agent == "research":
            payload["expected_output"] = "summary, sources oder artifacts"
            payload["success_signal"] = "Belastbare Quellen oder verifizierte Zusammenfassung vorhanden"
            if params.get("query"):
                payload["handoff_data"]["query"] = cls._shorten(params.get("query"))
        elif specialist_agent == "document":
            payload["expected_output"] = "PDF/DOCX/XLSX-Artefakt"
            payload["success_signal"] = "Datei erzeugt und Artefaktpfad vorhanden"
            if params.get("title"):
                payload["handoff_data"]["title"] = cls._shorten(params.get("title"))
            if params.get("format"):
                payload["handoff_data"]["format"] = cls._shorten(params.get("format"))
        elif specialist_agent == "communication":
            payload["expected_output"] = "Nachricht oder Versandstatus"
            payload["success_signal"] = "Nachricht formuliert oder versendet"
            recipient = params.get("to") or params.get("recipient") or params.get("email")
            if recipient:
                payload["handoff_data"]["recipient"] = cls._shorten(recipient)
            attachment = params.get("attachment_path") or params.get("attachment")
            if attachment:
                payload["handoff_data"]["attachment_path"] = cls._shorten(attachment)
        elif specialist_agent == "shell":
            payload["expected_output"] = "Kommandoausgabe oder Service-Status"
            payload["success_signal"] = "Befehl sicher ausgefuehrt oder sauber blockiert"
            payload["constraints"] = ["keine_destruktiven_befehle_ohne_expliziten_nutzerauftrag"]
            command = params.get("command") or params.get("script_path") or params.get("script")
            if command:
                payload["handoff_data"]["command"] = cls._shorten(command)
        elif specialist_agent == "visual":
            payload["expected_output"] = "page_state, ui_result oder captured_context"
            payload["success_signal"] = "Zielzustand oder UI-Signal sichtbar"
            target_hint = params.get("description") or params.get("text") or params.get("selector") or params.get("task")
            if target_hint:
                payload["handoff_data"]["target_hint"] = cls._shorten(target_hint)
        elif specialist_agent == "developer":
            payload["expected_output"] = "Code, Patch oder Tool-Artefakt"
            payload["success_signal"] = "Implementierung erstellt oder validierter Patch vorhanden"
        elif specialist_agent == "creative":
            payload["expected_output"] = "Bild/Text-Artefakt"
            payload["success_signal"] = "Kreatives Ergebnis erzeugt"

        return payload

    @classmethod
    def _render_structured_delegation_task(
        cls,
        specialist_agent: str,
        method: str,
        params: Dict[str, Any],
        task: str,
    ) -> str:
        payload = cls._build_specialist_handoff_payload(specialist_agent, method, params, task)
        lines = ["# DELEGATION HANDOFF"]
        lines.append(f"target_agent: {payload['target_agent']}")
        lines.append(f"goal: {payload['goal']}")
        lines.append(f"expected_output: {payload['expected_output']}")
        lines.append(f"success_signal: {payload['success_signal']}")
        constraints = list(payload.get("constraints") or [])
        lines.append("constraints: " + (", ".join(constraints) if constraints else "none"))
        handoff_data = dict(payload.get("handoff_data") or {})
        if handoff_data:
            lines.append("handoff_data:")
            for key, value in handoff_data.items():
                lines.append(f"- {key}: {value}")
        lines.append("")
        lines.append("# TASK")
        lines.append(task)
        return "\n".join(lines)

    @classmethod
    def _parse_meta_orchestration_handoff(cls, task: str) -> Optional[Dict[str, Any]]:
        if cls._META_HANDOFF_HEADER not in task:
            return None

        _, after_header = task.split(cls._META_HANDOFF_HEADER, 1)
        if cls._ORIGINAL_TASK_HEADER in after_header:
            handoff_block, original_task = after_header.split(cls._ORIGINAL_TASK_HEADER, 1)
        else:
            handoff_block, original_task = after_header, ""

        payload: Dict[str, Any] = {
            "recipe_stages": [],
            "recipe_recoveries": [],
            "original_user_task": original_task.strip(),
        }
        current_stage: Optional[Dict[str, Any]] = None
        current_recovery: Optional[Dict[str, Any]] = None
        in_recipe_stages = False
        in_recipe_recoveries = False

        for raw_line in handoff_block.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue

            if stripped == "recipe_stages:":
                in_recipe_stages = True
                in_recipe_recoveries = False
                current_stage = None
                continue

            if stripped == "recipe_recoveries:":
                in_recipe_recoveries = True
                in_recipe_stages = False
                current_recovery = None
                continue

            if in_recipe_stages and stripped.startswith("- "):
                stage_label = stripped[2:]
                if ":" not in stage_label:
                    continue
                stage_id, agent_part = stage_label.split(":", 1)
                agent_text = agent_part.strip()
                optional = False
                if agent_text.endswith("(optional)"):
                    agent_text = agent_text[: -len("(optional)")].strip()
                    optional = True
                current_stage = {
                    "stage_id": stage_id.strip(),
                    "agent": agent_text,
                    "optional": optional,
                }
                payload["recipe_stages"].append(current_stage)
                continue

            if in_recipe_recoveries and stripped.startswith("- "):
                recovery_label = stripped[2:]
                match = re.match(
                    r"(?P<failed>[^=]+)=>\s*(?P<recovery>[^:]+):\s*(?P<agent>[^\[]+?)(?:\s+\[(?P<terminal>terminal)\])?$",
                    recovery_label,
                )
                if not match:
                    continue
                current_recovery = {
                    "failed_stage_id": match.group("failed").strip(),
                    "recovery_stage_id": match.group("recovery").strip(),
                    "agent": match.group("agent").strip(),
                    "terminal": bool(match.group("terminal")),
                }
                payload["recipe_recoveries"].append(current_recovery)
                continue

            if in_recipe_stages and current_stage is not None:
                if stripped.startswith("goal:"):
                    current_stage["goal"] = stripped.split(":", 1)[1].strip()
                    continue
                if stripped.startswith("expected_output:"):
                    current_stage["expected_output"] = stripped.split(":", 1)[1].strip()
                    continue
                if stripped.startswith("Nutze diese Klassifikation") or stripped.startswith("Nutze Outcome-Lernen"):
                    in_recipe_stages = False
                    current_stage = None
                    continue

            if in_recipe_recoveries and current_recovery is not None:
                if stripped.startswith("goal:"):
                    current_recovery["goal"] = stripped.split(":", 1)[1].strip()
                    continue
                if stripped.startswith("expected_output:"):
                    current_recovery["expected_output"] = stripped.split(":", 1)[1].strip()
                    continue
                if stripped.startswith("Nutze diese Klassifikation") or stripped.startswith("Nutze Outcome-Lernen"):
                    in_recipe_recoveries = False
                    current_recovery = None
                    continue

            if ":" not in stripped:
                continue

            key, value = stripped.split(":", 1)
            normalized_key = key.strip()
            normalized_value = value.strip()

            if normalized_key == "required_capabilities":
                payload[normalized_key] = [
                    item.strip()
                    for item in normalized_value.split(",")
                    if item.strip()
                ]
            elif normalized_key == "recommended_agent_chain":
                payload[normalized_key] = [
                    item.strip()
                    for item in normalized_value.split("->")
                    if item.strip()
                ]
            elif normalized_key == "needs_structured_handoff":
                payload[normalized_key] = normalized_value.lower() == "yes"
            elif normalized_key == "meta_self_state_json":
                try:
                    payload["meta_self_state"] = json.loads(normalized_value)
                except json.JSONDecodeError:
                    payload["meta_self_state"] = {"raw": normalized_value}
            elif normalized_key == "goal_spec_json":
                try:
                    payload["goal_spec"] = json.loads(normalized_value)
                except json.JSONDecodeError:
                    payload["goal_spec"] = {"raw": normalized_value}
            elif normalized_key == "capability_graph_json":
                try:
                    payload["capability_graph"] = json.loads(normalized_value)
                except json.JSONDecodeError:
                    payload["capability_graph"] = {"raw": normalized_value}
            elif normalized_key == "adaptive_plan_json":
                try:
                    payload["adaptive_plan"] = json.loads(normalized_value)
                except json.JSONDecodeError:
                    payload["adaptive_plan"] = {"raw": normalized_value}
            elif normalized_key == "planner_resolution_json":
                try:
                    payload["planner_resolution"] = json.loads(normalized_value)
                except json.JSONDecodeError:
                    payload["planner_resolution"] = {"raw": normalized_value}
            elif normalized_key == "task_profile_json":
                try:
                    payload["task_profile"] = json.loads(normalized_value)
                except json.JSONDecodeError:
                    payload["task_profile"] = {"raw": normalized_value}
            elif normalized_key == "tool_affordances_json":
                try:
                    loaded = json.loads(normalized_value)
                    payload["tool_affordances"] = loaded if isinstance(loaded, list) else []
                except json.JSONDecodeError:
                    payload["tool_affordances"] = []
            elif normalized_key == "selected_strategy_json":
                try:
                    payload["selected_strategy"] = json.loads(normalized_value)
                except json.JSONDecodeError:
                    payload["selected_strategy"] = {"raw": normalized_value}
            elif normalized_key == "alternative_recipes_json":
                try:
                    loaded = json.loads(normalized_value)
                    payload["alternative_recipes"] = loaded if isinstance(loaded, list) else []
                except json.JSONDecodeError:
                    payload["alternative_recipes"] = []
            elif normalized_key == "alternative_recipe_scores_json":
                try:
                    loaded = json.loads(normalized_value)
                    payload["alternative_recipe_scores"] = loaded if isinstance(loaded, list) else []
                except json.JSONDecodeError:
                    payload["alternative_recipe_scores"] = []
            else:
                payload[normalized_key] = normalized_value

        if not payload.get("recipe_stages"):
            return None
        return payload

    @classmethod
    def _current_recipe_payload_from_handoff(cls, handoff: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "recipe_id": str(handoff.get("recommended_recipe_id") or "").strip(),
            "recipe_stages": [dict(stage) for stage in (handoff.get("recipe_stages") or [])],
            "recipe_recoveries": [dict(item) for item in (handoff.get("recipe_recoveries") or [])],
            "recommended_agent_chain": list(handoff.get("recommended_agent_chain") or []),
        }

    @classmethod
    def _select_initial_recipe_payload(cls, handoff: Dict[str, Any]) -> Dict[str, Any]:
        current = cls._current_recipe_payload_from_handoff(handoff)
        planner_selected = cls._planner_preferred_recipe_payload(
            handoff,
            current_recipe_id=str(current.get("recipe_id") or ""),
        )
        if planner_selected is not None:
            current = planner_selected
        strategy_selected = cls._strategy_preferred_recipe_payload(
            handoff,
            current_recipe_id=str(current.get("recipe_id") or ""),
        )
        if strategy_selected is not None:
            current = strategy_selected
        self_state = dict(handoff.get("meta_self_state") or {})
        runtime = dict(self_state.get("runtime_constraints") or {})
        tool_rows = list(self_state.get("active_tools") or [])
        task_type = str(handoff.get("task_type") or "").strip().lower()
        stability_state = str(runtime.get("stability_gate_state", "") or "").strip().lower()

        browser_tool_blocked = any(
            str(item.get("tool") or "").strip() == "browser_workflow_plan"
            and str(item.get("state") or "").strip().lower() == "blocked"
            for item in tool_rows
        )
        if browser_tool_blocked or stability_state == "blocked":
            safer = cls._prefer_non_browser_alternative(handoff, current_recipe_id=str(current.get("recipe_id") or ""))
            if safer is not None:
                return safer
        if task_type == "youtube_content_extraction" and (browser_tool_blocked or stability_state == "blocked"):
            for candidate in handoff.get("alternative_recipes") or []:
                if str(candidate.get("recipe_id") or "").strip() == "youtube_research_only":
                    return {
                        "recipe_id": str(candidate.get("recipe_id") or "").strip(),
                        "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                        "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                        "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                    }
        if task_type == "system_diagnosis" and stability_state == "blocked":
            for candidate in handoff.get("alternative_recipes") or []:
                if str(candidate.get("recipe_id") or "").strip() == "system_shell_probe_first":
                    return {
                        "recipe_id": str(candidate.get("recipe_id") or "").strip(),
                        "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                        "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                        "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                    }
        selected = cls._preferred_alternative_by_learning(handoff, current_recipe_id=str(current.get("recipe_id") or ""))
        if selected is not None:
            return selected
        return current

    @classmethod
    def _planner_preferred_recipe_payload(
        cls,
        handoff: Dict[str, Any],
        *,
        current_recipe_id: str,
    ) -> Optional[Dict[str, Any]]:
        planner_resolution = dict(handoff.get("planner_resolution") or {})
        if str(planner_resolution.get("state") or "").strip().lower() == "adopted":
            adopted_recipe_id = str(planner_resolution.get("adopted_recipe_id") or "").strip()
            if adopted_recipe_id and adopted_recipe_id != current_recipe_id:
                for candidate in handoff.get("alternative_recipes") or []:
                    recipe_id = str(candidate.get("recipe_id") or "").strip()
                    if recipe_id != adopted_recipe_id:
                        continue
                    return {
                        "recipe_id": recipe_id,
                        "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                        "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                        "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                        "switch_reason": "adaptive_planner_preferred",
                    }

        resolved = resolve_adaptive_plan_adoption(handoff)
        if str(resolved.get("state") or "").strip().lower() != "adopted":
            return None

        recipe_payload = dict(resolved.get("recipe_payload") or {})
        recipe_id = str(recipe_payload.get("recipe_id") or "").strip()
        if not recipe_id or recipe_id == current_recipe_id:
            return None
        return {
            "recipe_id": recipe_id,
            "recipe_stages": [dict(stage) for stage in (recipe_payload.get("recipe_stages") or [])],
            "recipe_recoveries": [dict(item) for item in (recipe_payload.get("recipe_recoveries") or [])],
            "recommended_agent_chain": list(recipe_payload.get("recommended_agent_chain") or []),
            "switch_reason": "adaptive_planner_preferred",
        }

    @classmethod
    def _strategy_preferred_recipe_payload(
        cls,
        handoff: Dict[str, Any],
        *,
        current_recipe_id: str,
    ) -> Optional[Dict[str, Any]]:
        strategy = dict(handoff.get("selected_strategy") or {})
        preferred_recipe_id = str(strategy.get("primary_recipe_id") or "").strip()
        if not preferred_recipe_id or preferred_recipe_id == current_recipe_id:
            return None

        if str(handoff.get("recommended_recipe_id") or "").strip() == preferred_recipe_id:
            return cls._current_recipe_payload_from_handoff(
                {**handoff, "recommended_recipe_id": preferred_recipe_id}
            )

        for candidate in handoff.get("alternative_recipes") or []:
            recipe_id = str(candidate.get("recipe_id") or "").strip()
            if recipe_id != preferred_recipe_id:
                continue
            return {
                "recipe_id": recipe_id,
                "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                "switch_reason": "selected_strategy_primary",
            }
        return None

    @classmethod
    def _prefer_non_browser_alternative(
        cls,
        handoff: Dict[str, Any],
        *,
        current_recipe_id: str,
    ) -> Optional[Dict[str, Any]]:
        for candidate in handoff.get("alternative_recipes") or []:
            recipe_id = str(candidate.get("recipe_id") or "").strip()
            if not recipe_id or recipe_id == current_recipe_id:
                continue
            chain = [str(item).strip().lower() for item in candidate.get("recommended_agent_chain") or []]
            if "visual" in chain:
                continue
            return {
                "recipe_id": recipe_id,
                "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                "switch_reason": "non_browser_runtime_guard",
            }
        return None

    @classmethod
    def _preferred_alternative_by_learning(
        cls,
        handoff: Dict[str, Any],
        *,
        current_recipe_id: str,
    ) -> Optional[Dict[str, Any]]:
        posture = str(handoff.get("meta_learning_posture") or handoff.get("learning_posture") or "").strip().lower()
        if posture != "conservative":
            return None

        current_scores = [
            cls._as_float(handoff.get("recipe_feedback_score")),
            cls._as_float(handoff.get("site_recipe_feedback_score")),
        ]
        current_floor = max(score for score in current_scores if score is not None) if any(
            score is not None for score in current_scores
        ) else None

        best_payload: Optional[Dict[str, Any]] = None
        best_score: Optional[float] = None
        for candidate in handoff.get("alternative_recipes") or []:
            recipe_id = str(candidate.get("recipe_id") or "").strip()
            if not recipe_id or recipe_id == current_recipe_id:
                continue
            learned = next(
                (
                    item
                    for item in handoff.get("alternative_recipe_scores") or []
                    if str(item.get("recipe_id") or "").strip() == recipe_id
                ),
                None,
            )
            if not learned:
                continue
            evidence = max(
                int(learned.get("recipe_evidence") or 0),
                int(learned.get("site_recipe_evidence") or 0),
            )
            candidate_scores = [
                cls._as_float(learned.get("recipe_score")),
                cls._as_float(learned.get("site_recipe_score")),
            ]
            candidate_score = max(score for score in candidate_scores if score is not None) if any(
                score is not None for score in candidate_scores
            ) else None
            if candidate_score is None or evidence < 3:
                continue
            if current_floor is not None and candidate_score < current_floor + 0.12:
                continue
            if best_score is None or candidate_score > best_score:
                best_score = candidate_score
                best_payload = {
                    "recipe_id": recipe_id,
                    "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                    "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                    "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                    "switch_reason": "learning_preference",
                }
        return best_payload

    @classmethod
    def _choose_alternative_recipe_payload(
        cls,
        handoff: Dict[str, Any],
        *,
        current_recipe_id: str,
        failed_stage: Dict[str, Any],
        attempted_recipe_ids: set[str],
    ) -> Optional[Dict[str, Any]]:
        error_signal = dict(failed_stage.get("error_signal") or {})
        strategy_error_preferred = cls._strategy_error_recipe_payload(
            handoff,
            current_recipe_id=current_recipe_id,
            attempted_recipe_ids=attempted_recipe_ids,
            error_signal=error_signal,
        )
        if strategy_error_preferred is not None:
            return strategy_error_preferred

        strategy_fallback = cls._strategy_fallback_recipe_payload(
            handoff,
            current_recipe_id=current_recipe_id,
            attempted_recipe_ids=attempted_recipe_ids,
        )
        if strategy_fallback is not None:
            return strategy_fallback

        failed_stage_id = str(failed_stage.get("stage_id") or "").strip()
        failed_agent = str(failed_stage.get("agent") or "").strip().lower()
        task_type = str(handoff.get("task_type") or "").strip().lower()

        for candidate in handoff.get("alternative_recipes") or []:
            recipe_id = str(candidate.get("recipe_id") or "").strip()
            if not recipe_id or recipe_id == current_recipe_id or recipe_id in attempted_recipe_ids:
                continue
            learned = next(
                (
                    item
                    for item in handoff.get("alternative_recipe_scores") or []
                    if str(item.get("recipe_id") or "").strip() == recipe_id
                ),
                None,
            )
            learning_reason = ""
            if learned:
                evidence = max(
                    int(learned.get("recipe_evidence") or 0),
                    int(learned.get("site_recipe_evidence") or 0),
                )
                learned_scores = [
                    cls._as_float(learned.get("recipe_score")),
                    cls._as_float(learned.get("site_recipe_score")),
                ]
                candidate_score = max(score for score in learned_scores if score is not None) if any(
                    score is not None for score in learned_scores
                ) else None
                if evidence >= 3 and candidate_score is not None and candidate_score >= 1.05:
                    learning_reason = f"learning_score:{candidate_score:.2f}"

            if (
                task_type == "youtube_content_extraction"
                and recipe_id == "youtube_research_only"
                and (failed_stage_id in {"visual_access", "research_context_seed"} or failed_agent == "visual")
            ):
                return {
                    "recipe_id": recipe_id,
                    "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                    "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                    "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                    "switch_reason": f"failed_stage:{failed_stage_id}" + (f"+{learning_reason}" if learning_reason else ""),
                }

            if task_type == "system_diagnosis" and recipe_id == "system_shell_probe_first" and failed_stage_id == "system_observe":
                return {
                    "recipe_id": recipe_id,
                    "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                    "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                    "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                    "switch_reason": f"failed_stage:{failed_stage_id}" + (f"+{learning_reason}" if learning_reason else ""),
                }
        return cls._generic_alternative_recipe_payload(
            handoff,
            current_recipe_id=current_recipe_id,
            failed_stage=failed_stage,
            attempted_recipe_ids=attempted_recipe_ids,
        )

    @classmethod
    def _strategy_error_recipe_payload(
        cls,
        handoff: Dict[str, Any],
        *,
        current_recipe_id: str,
        attempted_recipe_ids: set[str],
        error_signal: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        preferred_recipe_id = str(error_signal.get("prefer_recipe_id") or "").strip()
        prefer_non_browser = bool(error_signal.get("prefer_non_browser_fallback"))
        error_class = str(error_signal.get("error_class") or "").strip()

        if preferred_recipe_id and preferred_recipe_id != current_recipe_id and preferred_recipe_id not in attempted_recipe_ids:
            for candidate in handoff.get("alternative_recipes") or []:
                recipe_id = str(candidate.get("recipe_id") or "").strip()
                if recipe_id != preferred_recipe_id:
                    continue
                return {
                    "recipe_id": recipe_id,
                    "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                    "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                    "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                    "switch_reason": f"error_class:{error_class}" if error_class else "error_signal_preference",
                }

        if prefer_non_browser:
            safer = cls._prefer_non_browser_alternative(handoff, current_recipe_id=current_recipe_id)
            if safer is not None:
                safer["switch_reason"] = f"error_class:{error_class}" if error_class else "error_signal_non_browser"
                return safer
        return None

    @classmethod
    def _strategy_fallback_recipe_payload(
        cls,
        handoff: Dict[str, Any],
        *,
        current_recipe_id: str,
        attempted_recipe_ids: set[str],
    ) -> Optional[Dict[str, Any]]:
        strategy = dict(handoff.get("selected_strategy") or {})
        fallback_recipe_id = str(strategy.get("fallback_recipe_id") or "").strip()
        if not fallback_recipe_id or fallback_recipe_id == current_recipe_id or fallback_recipe_id in attempted_recipe_ids:
            return None

        for candidate in handoff.get("alternative_recipes") or []:
            recipe_id = str(candidate.get("recipe_id") or "").strip()
            if recipe_id != fallback_recipe_id:
                continue
            return {
                "recipe_id": recipe_id,
                "recipe_stages": [dict(stage) for stage in (candidate.get("recipe_stages") or [])],
                "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                "switch_reason": "selected_strategy_fallback",
            }
        return None

    @classmethod
    def _generic_alternative_recipe_payload(
        cls,
        handoff: Dict[str, Any],
        *,
        current_recipe_id: str,
        failed_stage: Dict[str, Any],
        attempted_recipe_ids: set[str],
    ) -> Optional[Dict[str, Any]]:
        failed_stage_id = str(failed_stage.get("stage_id") or "").strip()
        failed_agent = str(failed_stage.get("agent") or "").strip().lower()
        best_payload: Optional[Dict[str, Any]] = None
        best_score = 0.0

        for candidate in handoff.get("alternative_recipes") or []:
            recipe_id = str(candidate.get("recipe_id") or "").strip()
            if not recipe_id or recipe_id == current_recipe_id or recipe_id in attempted_recipe_ids:
                continue
            stage_defs = [dict(stage) for stage in (candidate.get("recipe_stages") or [])]
            if not stage_defs:
                continue
            stage_ids = {str(stage.get("stage_id") or "").strip() for stage in stage_defs}
            chain = [str(item).strip().lower() for item in (candidate.get("recommended_agent_chain") or [])]
            first_agent = str(stage_defs[0].get("agent") or "").strip().lower()

            score = 0.0
            if first_agent and first_agent != failed_agent:
                score += 0.35
            if failed_stage_id and failed_stage_id not in stage_ids:
                score += 0.25
            if failed_agent and failed_agent not in chain:
                score += 0.2

            learned = next(
                (
                    item
                    for item in handoff.get("alternative_recipe_scores") or []
                    if str(item.get("recipe_id") or "").strip() == recipe_id
                ),
                None,
            )
            learning_reason = ""
            if learned:
                evidence = max(
                    int(learned.get("recipe_evidence") or 0),
                    int(learned.get("site_recipe_evidence") or 0),
                )
                learned_scores = [
                    cls._as_float(learned.get("recipe_score")),
                    cls._as_float(learned.get("site_recipe_score")),
                ]
                candidate_score = max(score for score in learned_scores if score is not None) if any(
                    score is not None for score in learned_scores
                ) else None
                if evidence >= 3 and candidate_score is not None:
                    score += min(0.45, max(0.0, candidate_score - 0.9))
                    learning_reason = f"learning_score:{candidate_score:.2f}"

            if score <= best_score or score < 0.35:
                continue
            best_score = score
            best_payload = {
                "recipe_id": recipe_id,
                "recipe_stages": stage_defs,
                "recipe_recoveries": [dict(item) for item in (candidate.get("recipe_recoveries") or [])],
                "recommended_agent_chain": list(candidate.get("recommended_agent_chain") or []),
                "switch_reason": f"failed_stage:{failed_stage_id}" + (f"+{learning_reason}" if learning_reason else ""),
            }

        return best_payload

    @classmethod
    def _build_executed_agent_chain(
        cls,
        stage_history: List[Dict[str, Any]],
        *,
        fallback_chain: Optional[List[str]] = None,
    ) -> List[str]:
        chain: List[str] = ["meta"]
        for entry in stage_history:
            agent = str(entry.get("agent") or "").strip().lower()
            if agent and agent not in chain:
                chain.append(agent)
        for agent in fallback_chain or []:
            normalized = str(agent or "").strip().lower()
            if normalized and normalized not in chain:
                chain.append(normalized)
        return chain

    @staticmethod
    def _collect_runtime_gap_insertions(stage_history: List[Dict[str, Any]]) -> List[str]:
        collected: List[str] = []
        for entry in stage_history:
            reason = str(entry.get("adaptive_reason") or "").strip().lower()
            if reason.startswith("runtime_goal_gap") and reason not in collected:
                collected.append(reason)
        return collected

    @classmethod
    def _record_recipe_execution_outcome(
        cls,
        *,
        handoff: Dict[str, Any],
        recipe_payload: Dict[str, Any],
        success: bool,
        stage_history: List[Dict[str, Any]],
        failure: Optional[Dict[str, Any]] = None,
        switch_reason: str = "",
        duration_ms: int = 0,
    ) -> None:
        try:
            from orchestration.feedback_engine import get_feedback_engine

            recipe_id = str(recipe_payload.get("recipe_id") or "").strip().lower()
            chain = list(recipe_payload.get("recommended_agent_chain") or handoff.get("recommended_agent_chain") or [])
            feedback_targets = build_meta_feedback_targets(
                {
                    "task_type": handoff.get("task_type"),
                    "site_kind": handoff.get("site_kind"),
                    "recommended_recipe_id": recipe_id,
                    "recommended_agent_chain": chain,
                }
            )
            get_feedback_engine().record_runtime_outcome(
                action_id=f"meta-recipe-{recipe_id}-{int(time.time() * 1000)}",
                success=success,
                context={
                    "agent": "meta",
                    "feedback_source": "meta_recipe_execution",
                    "meta_task_type": str(handoff.get("task_type") or "")[:80],
                    "meta_recipe_id": recipe_id[:80],
                    "meta_agent_chain": " -> ".join(str(agent) for agent in chain)[:200],
                    "meta_site_kind": str(handoff.get("site_kind") or "")[:40],
                    "stage_count": len(stage_history),
                    "failed_stage_id": str((failure or {}).get("stage_id") or "")[:80],
                    "switch_reason": str(switch_reason or "")[:120],
                    "duration_ms": max(0, int(duration_ms)),
                },
                feedback_targets=feedback_targets,
            )
        except Exception:
            pass
        try:
            goal_signature = str((handoff.get("goal_spec") or {}).get("goal_signature") or "").strip()
            if not goal_signature:
                return
            get_adaptive_plan_memory().record_outcome(
                goal_signature=goal_signature,
                task_type=str(handoff.get("task_type") or ""),
                site_kind=str(handoff.get("site_kind") or ""),
                recipe_id=str(recipe_payload.get("recipe_id") or ""),
                recommended_chain=chain,
                final_chain=cls._build_executed_agent_chain(stage_history, fallback_chain=chain),
                success=success,
                runtime_gap_insertions=cls._collect_runtime_gap_insertions(stage_history),
                duration_ms=max(0, int(duration_ms)),
                confidence=cls._as_float((handoff.get("adaptive_plan") or {}).get("confidence")) or 0.0,
                failure_stage_id=str((failure or {}).get("stage_id") or ""),
                switch_reason=switch_reason,
            )
        except Exception:
            pass

    @classmethod
    def _should_execute_optional_recipe_stage(
        cls, handoff: Dict[str, Any], stage: Dict[str, Any]
    ) -> bool:
        if not stage.get("optional"):
            return True
        recommended_chain = [
            str(agent).strip().lower()
            for agent in handoff.get("recommended_agent_chain") or []
            if str(agent).strip()
        ]
        return str(stage.get("agent") or "").strip().lower() in recommended_chain

    @classmethod
    def _build_recipe_stage_delegation_task(
        cls,
        *,
        handoff: Dict[str, Any],
        stage: Dict[str, Any],
        original_user_task: str,
        previous_stage_result: Optional[Dict[str, Any]],
        stage_history: List[Dict[str, Any]],
    ) -> str:
        constraints = ["folge_dem_rezept_und_erfinde_keine_neuen_stages"]
        payload_lines = [
            "# DELEGATION HANDOFF",
            f"target_agent: {stage.get('agent', 'unknown')}",
            f"goal: {stage.get('goal', original_user_task)}",
            f"expected_output: {stage.get('expected_output', 'Spezialistenergebnis')}",
            f"success_signal: Stage '{stage.get('stage_id', 'stage')}' erfolgreich abgeschlossen",
            "constraints: " + ", ".join(constraints),
            "handoff_data:",
            f"- task_type: {handoff.get('task_type', 'single_lane')}",
            f"- recipe_id: {handoff.get('recommended_recipe_id', '')}",
            f"- stage_id: {stage.get('stage_id', '')}",
            f"- original_user_task: {cls._shorten(original_user_task, limit=500)}",
        ]
        selected_strategy = dict(handoff.get("selected_strategy") or {})
        if selected_strategy.get("strategy_id"):
            payload_lines.append(f"- strategy_id: {selected_strategy['strategy_id']}")
        if selected_strategy.get("strategy_mode"):
            payload_lines.append(f"- strategy_mode: {selected_strategy['strategy_mode']}")
        if selected_strategy.get("error_strategy"):
            payload_lines.append(f"- error_strategy: {selected_strategy['error_strategy']}")
        preferred_tools = selected_strategy.get("preferred_tools") or []
        if preferred_tools:
            payload_lines.append("- preferred_tools: " + ", ".join(str(item) for item in preferred_tools))
        fallback_tools = selected_strategy.get("fallback_tools") or []
        if fallback_tools:
            payload_lines.append("- fallback_tools: " + ", ".join(str(item) for item in fallback_tools))
        avoid_tools = selected_strategy.get("avoid_tools") or []
        if avoid_tools:
            payload_lines.append("- avoid_tools: " + ", ".join(str(item) for item in avoid_tools))
        site_kind = str(handoff.get("site_kind") or "").strip()
        if site_kind:
            payload_lines.append(f"- site_kind: {site_kind}")
        stage_agent = str(stage.get("agent") or "").strip().lower()
        if stage_agent == "document":
            output_format = cls._infer_document_output_format(original_user_task)
            if output_format:
                payload_lines.append(f"- output_format: {output_format}")
            artifact_name = cls._infer_document_artifact_name(original_user_task)
            if artifact_name:
                payload_lines.append(f"- artifact_name: {artifact_name}")
        if stage_agent == "communication":
            payload_lines.append("- channel: direct_message_or_email")
        if (
            str(handoff.get("task_type") or "").strip().lower() == "youtube_light_research"
            and stage_agent == "executor"
        ):
            payload_lines.append("- preferred_search_tool: search_youtube")
            payload_lines.append("- search_mode: live")
            payload_lines.append("- avoid_deep_research: yes")
            payload_lines.append("- max_results: 5")
        if (
            str(handoff.get("task_type") or "").strip().lower() == "simple_live_lookup"
            and stage_agent == "executor"
        ):
            payload_lines.append("- preferred_search_tool: search_web")
            payload_lines.append("- fallback_tools: search_news, fetch_url, search_google_maps_places")
            payload_lines.append("- avoid_deep_research: yes")
            payload_lines.append("- max_results: 5")
        if (
            str(handoff.get("task_type") or "").strip().lower() == "simple_live_lookup_document"
            and stage_agent == "executor"
        ):
            payload_lines.append("- preferred_search_tool: search_web")
            payload_lines.append("- fallback_tools: search_news, fetch_url, search_google_maps_places")
            payload_lines.append("- avoid_deep_research: yes")
            payload_lines.append("- max_results: 5")

        if previous_stage_result:
            payload_lines.append(
                f"- previous_stage_id: {previous_stage_result.get('stage_id', '')}"
            )
            payload_lines.append(
                f"- previous_stage_agent: {previous_stage_result.get('agent', '')}"
            )
            if previous_stage_result.get("blackboard_key"):
                payload_lines.append(
                    f"- previous_blackboard_key: {previous_stage_result['blackboard_key']}"
                )
            if previous_stage_result.get("result_preview"):
                payload_lines.append(
                    f"- previous_stage_result: {previous_stage_result['result_preview']}"
                )
            if stage_agent == "document" and previous_stage_result.get("result_full"):
                payload_lines.append(
                    "- source_material: "
                    + cls._encode_handoff_multiline(previous_stage_result["result_full"], limit=6000)
                )
            if stage_agent == "communication":
                if previous_stage_result.get("result_full"):
                    payload_lines.append(
                        "- source_material: "
                        + cls._encode_handoff_multiline(previous_stage_result["result_full"], limit=5000)
                    )
                artifacts = previous_stage_result.get("artifacts") or []
                if artifacts:
                    payload_lines.append(f"- attachment_path: {cls._shorten(artifacts[0], limit=260)}")

        prior_keys = [entry.get("blackboard_key") for entry in stage_history if entry.get("blackboard_key")]
        if prior_keys:
            payload_lines.append(f"- prior_blackboard_keys: {', '.join(prior_keys)}")

        payload_lines.extend(["", "# TASK", stage.get("goal", original_user_task)])
        return "\n".join(payload_lines)

    @classmethod
    def _render_recipe_execution_summary(
        cls,
        *,
        recipe_id: str,
        original_user_task: str,
        stage_history: List[Dict[str, Any]],
        failure: Optional[Dict[str, Any]] = None,
    ) -> str:
        lines = [f"Meta-Rezept '{recipe_id}' ausgefuehrt."]
        lines.append(f"Originale Aufgabe: {original_user_task}")
        lines.append("")
        lines.append("Stage-Verlauf:")
        for entry in stage_history:
            status = str(entry.get("status") or "unknown").upper()
            lines.append(f"- [{status}] {entry.get('stage_id')} -> {entry.get('agent')}")
            if entry.get("blackboard_key"):
                lines.append(f"  Blackboard: {entry['blackboard_key']}")
            if entry.get("result_preview"):
                lines.append(f"  Ergebnis: {entry['result_preview']}")
            if entry.get("recovery_for"):
                lines.append(f"  Recovery fuer: {entry['recovery_for']}")
            if entry.get("error"):
                lines.append(f"  Fehler: {entry['error']}")

        if failure:
            lines.append("")
            lines.append(
                f"Abbruch bei Pflicht-Stage '{failure.get('stage_id')}' ({failure.get('agent')}): "
                f"{failure.get('error', 'unbekannter Fehler')}"
            )
            return "\n".join(lines)

        final_success = next(
            (entry for entry in reversed(stage_history) if entry.get("status") == "success"),
            None,
        )
        if final_success and final_success.get("result_full"):
            clean_success_path = all(
                str(entry.get("status") or "").strip().lower() in {"success", "skipped"}
                and not entry.get("recovery_for")
                for entry in stage_history
            )
            if recipe_id in cls._RECIPE_DIRECT_RESULT_IDS or (
                clean_success_path
                and
                str(final_success.get("agent") or "").strip().lower() in {"document", "communication"}
                and (
                    bool(final_success.get("artifacts"))
                    or str(final_success.get("result_full") or "").strip().startswith("**Dokument erstellt:**")
                    or str(final_success.get("result_full") or "").strip().startswith("**Nachricht")
                    or str(final_success.get("result_full") or "").strip().startswith("**Versand")
                )
            ):
                return str(final_success["result_full"])
            lines.append("")
            lines.append("Finales Ergebnis:")
            lines.append(str(final_success["result_full"]))
        return "\n".join(lines)

    @classmethod
    def _get_recipe_recoveries(
        cls,
        handoff: Dict[str, Any],
        *,
        recipe_id: str,
        failed_stage_id: str,
    ) -> List[Dict[str, Any]]:
        recoveries = [
            dict(item)
            for item in (handoff.get("recipe_recoveries") or [])
            if str(item.get("failed_stage_id") or "").strip() == failed_stage_id
        ]
        if recoveries:
            return recoveries
        recipe = resolve_orchestration_recipe(str(handoff.get("task_type") or ""), handoff.get("site_kind"))
        if recipe and str(recipe.get("recipe_id") or "").strip() == recipe_id:
            return [
                dict(item)
                for item in (recipe.get("recipe_recoveries") or [])
                if str(item.get("failed_stage_id") or "").strip() == failed_stage_id
            ]
        return []

    @classmethod
    def _build_recipe_recovery_delegation_task(
        cls,
        *,
        handoff: Dict[str, Any],
        recovery: Dict[str, Any],
        failed_stage: Dict[str, Any],
        original_user_task: str,
        stage_history: List[Dict[str, Any]],
    ) -> str:
        constraints = [
            "handle_diesen_aufruf_als_recovery_und_bleibe_konservativ",
            "wenn_signal_schwach_bleibt_erklaere_das_ausdruecklich",
        ]
        payload_lines = [
            "# DELEGATION HANDOFF",
            f"target_agent: {recovery.get('agent', 'unknown')}",
            f"goal: {recovery.get('goal', original_user_task)}",
            f"expected_output: {recovery.get('expected_output', 'Recovery-Ergebnis')}",
            f"success_signal: Recovery fuer Stage '{failed_stage.get('stage_id', 'stage')}' abgeschlossen",
            "constraints: " + ", ".join(constraints),
            "handoff_data:",
            f"- task_type: {handoff.get('task_type', 'single_lane')}",
            f"- recipe_id: {handoff.get('recommended_recipe_id', '')}",
            f"- recovery_stage_id: {recovery.get('recovery_stage_id', '')}",
            f"- failed_stage_id: {failed_stage.get('stage_id', '')}",
            f"- failed_stage_agent: {failed_stage.get('agent', '')}",
            f"- failed_stage_error: {cls._shorten(failed_stage.get('error', ''), limit=220)}",
            f"- original_user_task: {cls._shorten(original_user_task, limit=500)}",
        ]
        error_signal = dict(failed_stage.get("error_signal") or {})
        if error_signal.get("error_class"):
            payload_lines.append(f"- failed_error_class: {error_signal['error_class']}")
        if error_signal.get("cause_hint"):
            payload_lines.append(
                f"- failed_error_cause_hint: {cls._shorten(error_signal['cause_hint'], limit=160)}"
            )
        if error_signal.get("suggested_reaction"):
            payload_lines.append(f"- failed_error_reaction: {error_signal['suggested_reaction']}")
        site_kind = str(handoff.get("site_kind") or "").strip()
        if site_kind:
            payload_lines.append(f"- site_kind: {site_kind}")
        prior_keys = [entry.get("blackboard_key") for entry in stage_history if entry.get("blackboard_key")]
        if prior_keys:
            payload_lines.append(f"- prior_blackboard_keys: {', '.join(prior_keys)}")
        payload_lines.extend(["", "# TASK", recovery.get("goal", original_user_task)])
        return "\n".join(payload_lines)

    @classmethod
    def _build_learning_preflight_stage(
        cls,
        *,
        handoff: Dict[str, Any],
        original_user_task: str,
    ) -> Optional[Dict[str, Any]]:
        posture = str(handoff.get("meta_learning_posture") or handoff.get("learning_posture") or "").strip().lower()
        task_type = str(handoff.get("task_type") or "").strip().lower()
        site_kind = str(handoff.get("site_kind") or "").strip().lower()
        if posture != "conservative":
            return None
        if task_type not in {"youtube_content_extraction", "web_content_extraction"}:
            return None
        if site_kind not in {"youtube", "x", "linkedin", "outlook", "booking", ""}:
            return None
        return {
            "stage_id": "research_context_seed",
            "agent": "research",
            "goal": (
                "Sammle vor dem UI-Zugriff konservativ Suchbegriffe, bekannte Quellen, Seitensignale "
                "und moegliche Zugangspfade fuer die Aufgabe."
            ),
            "expected_output": "source_urls, query_variants, captured_context",
            "optional": False,
            "adaptive": True,
            "adaptive_reason": "conservative_learning_posture",
        }

    @classmethod
    def _build_strategy_preflight_stage(
        cls,
        *,
        handoff: Dict[str, Any],
        original_user_task: str,
    ) -> Optional[Dict[str, Any]]:
        selected_strategy = dict(handoff.get("selected_strategy") or {})
        strategy_mode = str(selected_strategy.get("strategy_mode") or "").strip().lower()
        task_type = str(handoff.get("task_type") or "").strip().lower()

        if task_type == "youtube_content_extraction" and strategy_mode == "layered_extraction":
            return {
                "stage_id": "research_context_seed",
                "agent": "research",
                "goal": (
                    "Nutze zuerst leichte YouTube-Such-, Metadaten- und Transcript-Pfade, "
                    "bevor du auf schwereren UI-Zugriff oder teure Recherche eskalierst."
                ),
                "expected_output": "source_urls, query_variants, captured_context",
                "optional": False,
                "adaptive": True,
                "adaptive_reason": "strategy_lightweight_first",
            }
        if task_type == "web_content_extraction" and strategy_mode == "source_first":
            return {
                "stage_id": "research_context_seed",
                "agent": "research",
                "goal": (
                    "Sammle zuerst leichte Quellen-, URL- und Kontextsignale, bevor du "
                    "einen schwereren Browser- oder UI-Pfad ausfuehrst."
                ),
                "expected_output": "source_urls, query_variants, captured_context",
                "optional": False,
                "adaptive": True,
                "adaptive_reason": "strategy_lightweight_first",
            }
        return None

    @classmethod
    def _as_float(cls, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return None

    @classmethod
    def _encode_handoff_multiline(cls, value: Any, *, limit: int = 5000) -> str:
        text = cls._shorten(str(value or ""), limit=limit)
        return text.replace("\\", "\\\\").replace("\n", "\\n")

    @classmethod
    def _infer_document_output_format(cls, original_user_task: str) -> str:
        normalized = str(original_user_task or "").strip().lower()
        if any(token in normalized for token in ("xlsx", "excel", "tabelle")):
            return "XLSX"
        if "csv" in normalized:
            return "CSV"
        if any(token in normalized for token in ("txt", "textdatei", "text datei", "rohtext")):
            return "TXT"
        if any(token in normalized for token in ("docx", "word")):
            return "DOCX"
        if "pdf" in normalized:
            return "PDF"
        return ""

    @classmethod
    def _infer_document_artifact_name(cls, original_user_task: str) -> str:
        normalized = str(original_user_task or "").strip().lower()
        if "llm" in normalized and any(token in normalized for token in ("preis", "preise", "pricing", "kosten")):
            return "LLM_Preise_Vergleich"
        if "preis" in normalized or "pricing" in normalized or "kosten" in normalized:
            return "Preisvergleich"
        if "wetter" in normalized:
            return "Wetteruebersicht"
        if "news" in normalized or "nachrichten" in normalized:
            return "Aktuelle_News"
        return "Timus_Dokument"

    @classmethod
    def _build_research_validation_stage(
        cls,
        *,
        handoff: Dict[str, Any],
        stages: List[Dict[str, Any]],
        stage_history: List[Dict[str, Any]],
        previous_stage_result: Optional[Dict[str, Any]],
    ) -> Optional[Tuple[int, Dict[str, Any]]]:
        task_type = str(handoff.get("task_type") or "").strip().lower()
        if task_type not in {"youtube_content_extraction", "web_content_extraction"}:
            return None

        known_stage_ids = {
            str(stage.get("stage_id") or "").strip()
            for stage in stages
        }
        known_stage_ids.update(
            str(entry.get("stage_id") or "").strip()
            for entry in stage_history
        )
        if "research_validation_gate" in known_stage_ids:
            return None

        document_index = next(
            (
                index
                for index, stage in enumerate(stages)
                if str(stage.get("stage_id") or "").strip() == "document_output"
            ),
            None,
        )
        if document_index is None:
            return None

        triggered_by_recovery = bool(
            previous_stage_result
            and previous_stage_result.get("status") == "success"
            and previous_stage_result.get("recovery_for") == "visual_access"
        )
        score_candidates = [
            cls._as_float(handoff.get("recipe_feedback_score")),
            cls._as_float(handoff.get("chain_feedback_score")),
            cls._as_float(handoff.get("task_type_feedback_score")),
        ]
        negative_learning = any(
            score is not None and score <= -0.15
            for score in score_candidates
        )
        if not triggered_by_recovery and not negative_learning:
            return None

        adaptive_reason = (
            "post_recovery_validation"
            if triggered_by_recovery
            else "negative_learning_scores"
        )
        return (
            document_index,
            {
                "stage_id": "research_validation_gate",
                "agent": "research",
                "goal": (
                    "Validiere die bisherige Quellenlage und Zusammenfassung kritisch, "
                    "schliesse erkennbare Luecken und liefere belastbares Material fuer den "
                    "folgenden Dokumentschritt."
                ),
                "expected_output": "validated_summary, validation_signals, source_confidence",
                "optional": False,
                "adaptive": True,
                "adaptive_reason": adaptive_reason,
            },
        )

    @staticmethod
    def _stage_result_has_runtime_material(stage_result: Optional[Dict[str, Any]]) -> bool:
        if not stage_result or str(stage_result.get("status") or "").strip().lower() != "success":
            return False
        if stage_result.get("artifacts"):
            return True
        if stage_result.get("metadata"):
            return True
        return bool(str(stage_result.get("result_full") or "").strip())

    @classmethod
    def _insert_runtime_goal_gap_stage(
        cls,
        *,
        handoff: Dict[str, Any],
        stages: List[Dict[str, Any]],
        stage_index: int,
        stage_history: List[Dict[str, Any]],
        previous_stage_result: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        runtime_stage = resolve_runtime_goal_gap_stage(
            dict(handoff.get("goal_spec") or {}),
            current_stage_ids=[
                *(str(stage.get("stage_id") or "") for stage in stages),
                *(str(entry.get("stage_id") or "") for entry in stage_history),
            ],
            current_stage_agents=[
                *(str(stage.get("agent") or "") for stage in stages),
                *(str(entry.get("agent") or "") for entry in stage_history),
            ],
            previous_stage_status=str((previous_stage_result or {}).get("status") or ""),
            previous_stage_agent=str((previous_stage_result or {}).get("agent") or ""),
            has_result_material=cls._stage_result_has_runtime_material(previous_stage_result),
        )
        if runtime_stage is None:
            return stages

        adapted = [dict(stage) for stage in stages]
        runtime_agent = str(runtime_stage.get("agent") or "").strip().lower()
        insert_at = len(adapted)
        if runtime_agent == "research":
            for idx in range(stage_index + 1, len(adapted)):
                future_agent = str(adapted[idx].get("agent") or "").strip().lower()
                if future_agent in {"document", "communication"}:
                    insert_at = idx
                    break
        elif runtime_agent == "document":
            for idx in range(stage_index + 1, len(adapted)):
                if str(adapted[idx].get("agent") or "").strip().lower() == "communication":
                    insert_at = idx
                    break
        adapted.insert(insert_at, runtime_stage)
        chain = [
            str(agent).strip().lower()
            for agent in handoff.get("recommended_agent_chain") or []
            if str(agent).strip()
        ]
        if runtime_agent and runtime_agent not in chain:
            handoff["recommended_agent_chain"] = [*chain, runtime_agent]
        return adapted

    @classmethod
    def _adapt_recipe_stages(
        cls,
        *,
        handoff: Dict[str, Any],
        stages: List[Dict[str, Any]],
        original_user_task: str,
        stage_history: List[Dict[str, Any]],
        previous_stage_result: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        adapted = [dict(stage) for stage in stages]
        if not stage_history:
            strategy_preflight = cls._build_strategy_preflight_stage(
                handoff=handoff,
                original_user_task=original_user_task,
            )
            if strategy_preflight and not any(stage.get("stage_id") == strategy_preflight["stage_id"] for stage in adapted):
                adapted.insert(0, strategy_preflight)
            preflight = cls._build_learning_preflight_stage(
                handoff=handoff,
                original_user_task=original_user_task,
            )
            if preflight and not any(stage.get("stage_id") == preflight["stage_id"] for stage in adapted):
                adapted.insert(0, preflight)

        if (
            previous_stage_result
            and previous_stage_result.get("status") == "success"
            and previous_stage_result.get("recovery_for") == "visual_access"
        ):
            adapted = [
                stage
                for stage in adapted
                if not (
                    str(stage.get("stage_id") or "").strip() == "research_synthesis"
                    and str(stage.get("agent") or "").strip() == "research"
                )
            ]

        validation_stage = cls._build_research_validation_stage(
            handoff=handoff,
            stages=adapted,
            stage_history=stage_history,
            previous_stage_result=previous_stage_result,
        )
        if validation_stage:
            insert_at, stage = validation_stage
            adapted.insert(insert_at, stage)

        return adapted

    async def _attempt_recipe_recovery(
        self,
        *,
        handoff: Dict[str, Any],
        recipe_id: str,
        failed_stage: Dict[str, Any],
        original_user_task: str,
        stage_history: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        recoveries = self._get_recipe_recoveries(
            handoff,
            recipe_id=recipe_id,
            failed_stage_id=str(failed_stage.get("stage_id") or ""),
        )
        for recovery in recoveries:
            recovery_task = self._build_recipe_recovery_delegation_task(
                handoff=handoff,
                recovery=recovery,
                failed_stage=failed_stage,
                original_user_task=original_user_task,
                stage_history=stage_history,
            )
            raw_result = await super()._call_tool(
                "delegate_to_agent",
                {
                    "agent_type": recovery.get("agent", "unknown"),
                    "task": recovery_task,
                    "from_agent": "meta",
                    "session_id": self.conversation_session_id,
                },
            )
            normalized = self._normalize_delegation_result(
                str(recovery.get("agent") or "unknown"),
                f"recipe_recovery:{recovery.get('recovery_stage_id', 'recovery')}",
                raw_result,
            )
            history_entry = {
                "stage_id": recovery.get("recovery_stage_id", "recovery"),
                "agent": recovery.get("agent", "unknown"),
                "status": normalized.get("status", "error") if isinstance(normalized, dict) else "error",
                "blackboard_key": normalized.get("blackboard_key", "") if isinstance(normalized, dict) else "",
                "result_preview": self._shorten(
                    (normalized.get("result") if isinstance(normalized, dict) else str(normalized)),
                    limit=220,
                ),
                "result_full": normalized.get("result") if isinstance(normalized, dict) else str(normalized),
                "error": normalized.get("error", "") if isinstance(normalized, dict) else "",
                "metadata": normalized.get("metadata", {}) if isinstance(normalized, dict) else {},
                "artifacts": normalized.get("artifacts", []) if isinstance(normalized, dict) else [],
                "recovery_for": failed_stage.get("stage_id", ""),
                "terminal": bool(recovery.get("terminal")),
            }
            stage_history.append(history_entry)
            if history_entry["status"] == "success":
                failed_stage["status"] = "recovered"
                failed_stage["recovered_by"] = history_entry["stage_id"]
                return history_entry
        return None

    async def _execute_meta_recipe_handoff(
        self,
        task: str,
        handoff: Dict[str, Any],
        *,
        recipe_payload: Optional[Dict[str, Any]] = None,
        attempted_recipe_ids: Optional[set[str]] = None,
    ) -> Optional[str]:
        selected_recipe = recipe_payload or self._select_initial_recipe_payload(handoff)
        recipe_id = str(selected_recipe.get("recipe_id") or "").strip()
        stages = [dict(stage) for stage in (selected_recipe.get("recipe_stages") or [])]
        if not recipe_id or not stages:
            return None
        attempted = set(attempted_recipe_ids or set())
        attempted.add(recipe_id)

        original_user_task = self._strip_location_context_block(
            str(handoff.get("original_user_task") or task)
        )
        handoff_for_recipe = dict(handoff)
        handoff_for_recipe["recommended_recipe_id"] = recipe_id
        handoff_for_recipe["recipe_stages"] = stages
        handoff_for_recipe["recipe_recoveries"] = list(selected_recipe.get("recipe_recoveries") or [])
        if selected_recipe.get("recommended_agent_chain"):
            handoff_for_recipe["recommended_agent_chain"] = list(selected_recipe.get("recommended_agent_chain") or [])
        stage_history: List[Dict[str, Any]] = []
        previous_stage_result: Optional[Dict[str, Any]] = None
        recipe_started_at = time.monotonic()
        stage_index = 0
        while stage_index < len(stages):
            stages = self._adapt_recipe_stages(
                handoff=handoff_for_recipe,
                stages=stages,
                original_user_task=original_user_task,
                stage_history=stage_history,
                previous_stage_result=previous_stage_result,
            )
            stage = stages[stage_index]
            if not self._should_execute_optional_recipe_stage(handoff_for_recipe, stage):
                stage_history.append(
                    {
                        "stage_id": stage.get("stage_id", "stage"),
                        "agent": stage.get("agent", "unknown"),
                        "status": "skipped",
                        "result_preview": "Optionale Stage fuer diese Anfrage uebersprungen.",
                        "adaptive_reason": str(stage.get("adaptive_reason") or ""),
                    }
                )
                stage_index += 1
                continue

            stage_task = self._build_recipe_stage_delegation_task(
                handoff=handoff_for_recipe,
                stage=stage,
                original_user_task=original_user_task,
                previous_stage_result=previous_stage_result,
                stage_history=stage_history,
            )
            raw_result = await super()._call_tool(
                "delegate_to_agent",
                {
                    "agent_type": stage.get("agent", "unknown"),
                    "task": stage_task,
                    "from_agent": "meta",
                    "session_id": self.conversation_session_id,
                },
            )
            normalized = self._normalize_delegation_result(
                str(stage.get("agent") or "unknown"),
                f"recipe_stage:{stage.get('stage_id', 'stage')}",
                raw_result,
            )
            history_entry = {
                "stage_id": stage.get("stage_id", "stage"),
                "agent": stage.get("agent", "unknown"),
                "status": normalized.get("status", "error") if isinstance(normalized, dict) else "error",
                "blackboard_key": normalized.get("blackboard_key", "") if isinstance(normalized, dict) else "",
                "result_preview": self._shorten(
                    (normalized.get("result") if isinstance(normalized, dict) else str(normalized)),
                    limit=220,
                ),
                "result_full": normalized.get("result") if isinstance(normalized, dict) else str(normalized),
                "error": normalized.get("error", "") if isinstance(normalized, dict) else "",
                "metadata": normalized.get("metadata", {}) if isinstance(normalized, dict) else {},
                "artifacts": normalized.get("artifacts", []) if isinstance(normalized, dict) else [],
                "adaptive_reason": str(stage.get("adaptive_reason") or ""),
            }
            if history_entry["status"] != "success":
                history_entry["error_signal"] = classify_strategy_error(
                    handoff=handoff_for_recipe,
                    failed_stage=history_entry,
                )
            stage_history.append(history_entry)
            previous_stage_result = history_entry

            if history_entry["status"] != "success":
                if stage.get("optional"):
                    stage_index += 1
                    continue
                recovery_result = await self._attempt_recipe_recovery(
                    handoff=handoff_for_recipe,
                    recipe_id=recipe_id,
                    failed_stage=history_entry,
                    original_user_task=original_user_task,
                    stage_history=stage_history,
                )
                if recovery_result and recovery_result["status"] == "success":
                    previous_stage_result = recovery_result
                    if recovery_result.get("terminal"):
                        self._record_recipe_execution_outcome(
                            handoff=handoff_for_recipe,
                            recipe_payload=selected_recipe,
                            success=True,
                            stage_history=stage_history,
                            duration_ms=int((time.monotonic() - recipe_started_at) * 1000),
                        )
                        return self._render_recipe_execution_summary(
                            recipe_id=recipe_id,
                            original_user_task=original_user_task,
                            stage_history=stage_history,
                        )
                    stage_index += 1
                    continue
                alternative_recipe = self._choose_alternative_recipe_payload(
                    handoff_for_recipe,
                    current_recipe_id=recipe_id,
                    failed_stage=history_entry,
                    attempted_recipe_ids=attempted,
                )
                if alternative_recipe is not None:
                    self._record_recipe_execution_outcome(
                        handoff=handoff_for_recipe,
                        recipe_payload=selected_recipe,
                        success=False,
                        stage_history=stage_history,
                        failure=history_entry,
                        switch_reason=str(alternative_recipe.get("switch_reason") or ""),
                        duration_ms=int((time.monotonic() - recipe_started_at) * 1000),
                    )
                    switched = await self._execute_meta_recipe_handoff(
                        task,
                        handoff_for_recipe,
                        recipe_payload=alternative_recipe,
                        attempted_recipe_ids=attempted,
                    )
                    if switched:
                        switch_reason = str(alternative_recipe.get("switch_reason") or "recipe_replan").strip()
                        return (
                            f"Meta-Rezept '{recipe_id}' wurde nach Fehler in Stage "
                            f"'{history_entry.get('stage_id', 'stage')}' auf "
                            f"'{alternative_recipe.get('recipe_id', 'alternative')}' umgestellt "
                            f"({switch_reason}).\n\n{switched}"
                        )
                self._record_recipe_execution_outcome(
                    handoff=handoff_for_recipe,
                    recipe_payload=selected_recipe,
                    success=False,
                    stage_history=stage_history,
                    failure=history_entry,
                    duration_ms=int((time.monotonic() - recipe_started_at) * 1000),
                )
                return self._render_recipe_execution_summary(
                    recipe_id=recipe_id,
                    original_user_task=original_user_task,
                    stage_history=stage_history,
                    failure=history_entry,
                )
            stages = self._insert_runtime_goal_gap_stage(
                handoff=handoff_for_recipe,
                stages=stages,
                stage_index=stage_index,
                stage_history=stage_history,
                previous_stage_result=previous_stage_result,
            )
            selected_recipe["recommended_agent_chain"] = list(
                handoff_for_recipe.get("recommended_agent_chain") or selected_recipe.get("recommended_agent_chain") or []
            )
            stage_index += 1

        self._record_recipe_execution_outcome(
            handoff=handoff_for_recipe,
            recipe_payload=selected_recipe,
            success=True,
            stage_history=stage_history,
            duration_ms=int((time.monotonic() - recipe_started_at) * 1000),
        )
        return self._render_recipe_execution_summary(
            recipe_id=recipe_id,
            original_user_task=original_user_task,
            stage_history=stage_history,
        )

    @staticmethod
    def _normalize_delegation_result(
        specialist_agent: str,
        method: str,
        result: Any,
    ) -> Any:
        if not isinstance(result, dict):
            return result

        status = str(result.get("status") or "").strip().lower()
        error_text = str(result.get("error") or "").strip()
        has_payload = any(
            result.get(key) not in (None, "", [], {})
            for key in ("result", "artifacts", "metadata", "quality", "blackboard_key")
        )

        if status == "error" and not error_text:
            error_text = (
                f"FEHLER: Delegation an '{specialist_agent}' fuer Tool '{method}' "
                "lieferte keinen Fehlertext."
            )
            normalized = dict(result)
            normalized["error"] = error_text
            return normalized

        if not status and not has_payload:
            return {
                "status": "error",
                "agent": specialist_agent,
                "error": (
                    f"FEHLER: Delegation an '{specialist_agent}' fuer Tool '{method}' "
                    "lieferte eine leere oder unvollstaendige Antwort."
                ),
                "quality": 0,
                "metadata": {"delegation_transport_error": True, "tool": method},
                "artifacts": [],
            }

        if not status and error_text:
            normalized = dict(result)
            normalized["status"] = "error"
            return normalized

        return result

    async def _call_tool(self, method: str, params: dict) -> dict:
        specialist_agent = self._SPECIALIST_TOOL_AGENT_MAP.get(method)
        if specialist_agent:
            task = self._build_specialist_delegation_task(method, params)
            if task:
                structured_task = self._render_structured_delegation_task(
                    specialist_agent=specialist_agent,
                    method=method,
                    params=params,
                    task=task,
                )
                result = await super()._call_tool(
                    "delegate_to_agent",
                    {
                        "agent_type": specialist_agent,
                        "task": structured_task,
                        "from_agent": "meta",
                        "session_id": self.conversation_session_id,
                    },
                )
                return self._normalize_delegation_result(specialist_agent, method, result)
        return await super()._call_tool(method, params)

    async def _finalize_list_output(self, task: str, result: str) -> str:
        guarded = self._guard_live_lookup_output(task, result)
        if guarded != result:
            return guarded
        return await super()._finalize_list_output(task, result)

    # ------------------------------------------------------------------
    # Skill-System
    # ------------------------------------------------------------------

    def _init_skill_system(self):
        try:
            from utils.skill_types import SkillRegistry

            self.skill_registry = SkillRegistry()

            skills_base = Path(__file__).parent.parent.parent / "skills"
            if skills_base.exists():
                self.skill_registry.load_all_from_directory(skills_base)
                log.info(f"MetaAgent: {len(self.skill_registry.skills)} Skills geladen")
            else:
                log.warning(f"MetaAgent: Skill-Verzeichnis nicht gefunden: {skills_base}")

        except Exception as e:
            log.error(f"MetaAgent: Fehler beim Initialisieren des Skill-Systems: {e}")
            self.skill_registry = None

    def _select_skills_for_task(self, task: str, top_k: int = 3) -> List:
        if not self.skill_registry:
            return []

        selected = self.skill_registry.select_for_task(task, top_k=top_k)

        if selected:
            log.info(f"MetaAgent: {len(selected)} Skill(s) fuer Task ausgewaehlt:")
            for skill in selected:
                log.info(f"   - {skill.name}")

        return selected

    def _build_skill_context(self, skills: List, include_references: bool = False) -> str:
        if not skills:
            return ""

        context_parts = ["\n# AVAILABLE SKILLS\n"]

        for skill in skills:
            if include_references:
                refs = list(skill.get_references().keys())
                skill_context = skill.get_full_context(include_references=refs)
            else:
                skill_context = skill.get_full_context()

            context_parts.append(skill_context)
            context_parts.append("\n---\n")

        context_parts.append("\n# INSTRUCTIONS\n")
        context_parts.append("Use the above skills when appropriate for this task.")
        context_parts.append("Follow the skill instructions and use provided scripts/references.")

        return "\n".join(context_parts)

    # ------------------------------------------------------------------
    # Erweiterter run()-Einstieg: Timus-Kontext + Skills injizieren
    # ------------------------------------------------------------------

    async def run(self, task: str) -> str:
        log.info(f"MetaAgent mit Kontext + Skill-Orchestrierung: {task[:50]}...")

        recipe_handoff = self._parse_meta_orchestration_handoff(task)
        if recipe_handoff:
            recipe_result = await self._execute_meta_recipe_handoff(task, recipe_handoff)
            if recipe_result:
                return recipe_result

        # 1. Timus Autonomie-Kontext laden
        meta_context = await self._build_meta_context()

        # 2. Skills auswählen
        self.active_skills = self._select_skills_for_task(task, top_k=3)
        skill_context = self._build_skill_context(self.active_skills, include_references=False)

        # 3. Task anreichern
        parts: list[str] = []
        if meta_context:
            parts.append(meta_context)
        if skill_context:
            parts.append(skill_context)
        parts.append(f"# AUFGABE\n{task}")
        if skill_context:
            parts.append("Prüfe ob verfügbare Skills zur Aufgabe passen und nutze sie entsprechend.")

        # Decomposition-Hint für komplexe Aufgaben
        if self._needs_decomposition_hint(task):
            parts.append(self._DECOMPOSITION_HINT)
            log.info("MetaAgent: Decomposition-Hint injiziert (komplexe Aufgabe erkannt)")

        enhanced_task = "\n\n".join(parts)

        result = await super().run(enhanced_task)

        # Partial-Result-Erkennung
        _partial_markers = {"Limit erreicht.", "Max Iterationen."}
        if result in _partial_markers:
            log.warning(
                f"MetaAgent: Ergebnis ist partiell ('{result}') — "
                "Aufgabe moeglicherweise nicht vollstaendig abgeschlossen."
            )
            return result + "\n\n_(Koordinator-Hinweis: Ergebnis unvollstaendig)_"

        return result

    # ------------------------------------------------------------------
    # Timus Autonomie-Kontext aufbauen
    # ------------------------------------------------------------------

    async def _build_meta_context(self) -> str:
        """
        Erstellt Kontext für den Meta-Agent:
        - Aktive Langzeit-Ziele (M11 GoalQueueManager)
        - Offene Tasks in der Queue (TaskQueue)
        - Blackboard-Zusammenfassung (M9 AgentBlackboard)
        - Letzte Reflexion (M8 SessionReflectionLoop)
        - Aktive Proaktive Trigger (M10)
        - Verfügbare Agenten
        - Aktuelle Zeit
        """
        lines: list[str] = ["# TIMUS SYSTEM-KONTEXT (automatisch geladen)"]

        # 1. Aktive Ziele (M11)
        goals_ctx = await asyncio.to_thread(self._get_active_goals)
        if goals_ctx:
            lines.append(f"Aktive Langzeit-Ziele: {goals_ctx}")

        # 2. Offene Tasks in Queue
        tasks_ctx = await asyncio.to_thread(self._get_pending_tasks)
        if tasks_ctx:
            lines.append(f"Offene Tasks: {tasks_ctx}")

        # 3. Blackboard-Zusammenfassung (M9)
        bb_ctx = await asyncio.to_thread(self._get_blackboard_summary)
        if bb_ctx:
            lines.append(f"Agent-Blackboard: {bb_ctx}")

        # 4. Letzte Reflexion (M8)
        reflection_ctx = await self._get_last_reflection()
        if reflection_ctx:
            lines.append(f"Letzte Reflexion: {reflection_ctx}")

        # 5. Aktive Trigger (M10)
        trigger_ctx = await asyncio.to_thread(self._get_active_triggers)
        if trigger_ctx:
            lines.append(f"Aktive Routinen: {trigger_ctx}")

        # 6. Verfügbare Agenten (dynamische Capability-Map, M17)
        cap_map = await asyncio.to_thread(self._get_capability_map)
        if cap_map:
            lines.append(f"Verfügbare Agenten:\n{cap_map}")

        lines.append(f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

    def _get_active_goals(self) -> str:
        """Lädt aktive Ziele aus dem GoalQueueManager (M11)."""
        if not os.getenv("AUTONOMY_GOAL_QUEUE_ENABLED", "true").lower() == "true":
            return ""
        try:
            from orchestration.goal_queue_manager import GoalQueueManager
            mgr = GoalQueueManager()
            tree = mgr.get_goal_tree()
            if not tree:
                return ""
            active = [
                g for g in tree
                if g.get("status") in ("active", "in_progress", "pending")
            ][:5]
            if not active:
                return ""
            parts = []
            for g in active:
                progress = int(g.get("progress", 0) * 100)
                parts.append(f"{g['title']} ({progress}%)")
            return " | ".join(parts)
        except Exception as exc:
            log.debug("GoalQueueManager nicht verfügbar: %s", exc)
            return ""

    def _get_pending_tasks(self) -> str:
        """Gibt offene Tasks aus der TaskQueue zurück."""
        try:
            from orchestration.task_queue import TaskQueue
            tq = TaskQueue()
            pending = tq.get_pending()[:5]
            if not pending:
                return "0 offen"
            parts = []
            for t in pending:
                desc = (t.get("description") or t.get("title") or "Task")[:40]
                agent = t.get("agent_type") or "?"
                parts.append(f"{desc} [{agent}]")
            return f"{len(pending)} offen: " + " | ".join(parts)
        except Exception as exc:
            log.debug("TaskQueue nicht verfügbar: %s", exc)
            return ""

    def _get_blackboard_summary(self) -> str:
        """Zeigt aktuelle Delegation-Einträge aus dem AgentBlackboard (M9/M17)."""
        if not os.getenv("AUTONOMY_BLACKBOARD_ENABLED", "true").lower() == "true":
            return ""
        try:
            from memory.agent_blackboard import get_blackboard
            bb = get_blackboard()
            entries = bb.search("delegation:", agent_id=None, limit=5)
            if entries:
                lines = []
                for e in entries:
                    val = e.get("value", {})
                    lines.append(
                        f"- [{val.get('status', '?')}] {e['key']}: {val.get('task', '')[:60]}..."
                    )
                return "\n".join(lines)
            # Fallback: Gesamtübersicht wenn keine delegation:-Einträge
            summary = bb.get_summary()
            total = summary.get("total_active", 0)
            if not total:
                return ""
            by_agent = summary.get("by_agent", {})
            agent_parts = [f"{a}:{c}" for a, c in list(by_agent.items())[:4]]
            return f"{total} Einträge ({', '.join(agent_parts)})"
        except Exception as exc:
            log.debug("AgentBlackboard nicht verfügbar: %s", exc)
            return ""

    def _get_capability_map(self) -> str:
        """Erstellt dynamische Capability-Map aller registrierten Agenten (M17)."""
        try:
            from agent.agent_registry import agent_registry
            specs = agent_registry.list_agent_specs()
            if not specs:
                return "Keine Agenten registriert"
            lines = []
            for spec in specs:
                lines.append(f"- {spec.agent_type}: {', '.join(spec.capabilities[:3])}")
            return "\n".join(lines)
        except Exception as exc:
            log.debug("Capability-Map nicht verfügbar: %s", exc)
            return "Capability-Map nicht verfügbar"

    async def _get_last_reflection(self) -> str:
        """Lädt die letzte Session-Reflexion (M8)."""
        if not os.getenv("AUTONOMY_REFLECTION_ENABLED", "false").lower() == "true":
            return ""
        try:
            from orchestration.session_reflection import SessionReflectionLoop
            loop = SessionReflectionLoop()
            reflections = await loop.get_recent_reflections(limit=1)
            if not reflections:
                return ""
            r = reflections[0]
            success = int(r.get("success_rate", 0) * 100)
            patterns = r.get("patterns_json", "[]")
            import json
            pat_list = json.loads(patterns) if isinstance(patterns, str) else patterns
            top_pattern = pat_list[0] if pat_list else ""
            result = f"Erfolgsrate {success}%"
            if top_pattern:
                result += f", Top-Muster: {str(top_pattern)[:60]}"
            return result
        except Exception as exc:
            log.debug("SessionReflectionLoop nicht verfügbar: %s", exc)
            return ""

    def _get_active_triggers(self) -> str:
        """Listet aktive Proaktive Trigger (M10)."""
        if not os.getenv("AUTONOMY_PROACTIVE_TRIGGERS_ENABLED", "false").lower() == "true":
            return ""
        try:
            from orchestration.proactive_triggers import ProactiveTriggerEngine
            engine = ProactiveTriggerEngine()
            triggers = [t for t in engine.list_triggers() if t.get("enabled")]
            if not triggers:
                return ""
            parts = [f"{t['name']} ({t['time_of_day']})" for t in triggers[:4]]
            return " | ".join(parts)
        except Exception as exc:
            log.debug("ProactiveTriggerEngine nicht verfügbar: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # 3d: Strukturierte Decomposition komplexer Ziele (Phase 3)
    # ------------------------------------------------------------------

    MAX_DECOMPOSITION_DEPTH = 3      # Lean: meta_decomposition_depth (Th.49)
    META_MAX_REPLAN_ATTEMPTS = 2     # Lean: meta_replan_depth_bounded (Th.53)

    _DECOMPOSITION_HINT = (
        "\n\n## DECOMPOSITION-REGEL (automatisch aktiviert)\n"
        "Diese Aufgabe hat >3 Teilschritte. Verwende strukturierte Hierarchie:\n"
        "1. Identifiziere Abhängigkeiten (A muss vor B fertig sein)\n"
        "2. Gruppiere in max. 3 Phasen (Phase 1: Fundament | Phase 2: Kern | Phase 3: Finish)\n"
        "3. Priorisiere: P0 (blockiert alles) → P1 (Kern) → P2 (optional)\n"
        "4. Schätze Komplexität pro Teilschritt: S (< 30 Min) / M (< 2h) / L (> 2h)\n"
        f"Maximale Hierarchietiefe: {MAX_DECOMPOSITION_DEPTH} Ebenen.\n"
    )

    @staticmethod
    def _needs_decomposition_hint(task: str) -> bool:
        """Prüft ob eine Aufgabe komplex genug für strukturierte Decomposition ist."""
        # Indikatoren für komplexe Multi-Step-Aufgaben
        triggers = {
            "phase", "schritt", "step", "dann", "zuerst", "anschließend", "danach",
            "implementier", "erstell", "baue", "entwickl", "plane", "analysier",
            "und", "+", "sowie", "außerdem",
        }
        task_lower = task.lower()
        trigger_count = sum(1 for t in triggers if t in task_lower)
        return trigger_count >= 3 or len(task) > 200

    # ------------------------------------------------------------------
    # Visual-Plan-Erstellung (Nemotron-gestützt)
    # ------------------------------------------------------------------

    async def create_visual_plan(self, task: str) -> dict:
        """Erstellt einen strukturierten Plan für Visual/Browser-Tasks.

        Diese Methode analysiert den Task und erstellt eine Schritt-für-Schritt
        Roadmap mit konkreten Aktionen (URL öffnen, Elemente finden, etc.)

        Returns:
            Dict mit: goal, url, steps (Liste von Actions mit verification)
        """
        log.info(f"MetaAgent: Erstelle Visual-Plan für: {task[:60]}...")

        plan_prompt = f"""Erstelle einen DETAILLIERTEN Plan für diese Browser-Automatisierung:

AUFGABE: {task}

Analysiere:
1. Welche URL muss zuerst geöffnet werden?
2. Was sind die konkreten Schritte (in Reihenfolge)?
3. Welche Elemente müssen gefunden/klicked werden?
4. Was ist die erwartete Ergebnis-Überprüfung?

Gib den Plan in diesem JSON-Format zurück:
{{
  "goal": "Kurze Zusammenfassung des Ziels",
  "url": "https://... (Start-URL)",
  "steps": [
    {{
      "step_number": 1,
      "action": "navigate|click|type|scroll|wait|verify",
      "description": "Was genau soll passieren",
      "target": "Element-Name oder null",
      "value": "Eingabe-Wert oder null",
      "verification": "Wie prüfen wir Erfolg?",
      "fallback": "Was tun wenn es nicht klappt?"
    }}
  ],
  "success_criteria": ["Liste der Erfolgs-Bedingungen"],
  "estimated_steps": 5
}}

WICHTIG:
- Sei SPEZIFISCH (konkrete URLs, nicht "irgendeine Seite")
- Denke an COOKIE-BANNER (erster Schritt oft "akzeptieren")
- Berücksichtige LADEZEITEN (wait nach navigate)
- Jeder Step braucht eine verification

Antworte NUR mit dem JSON, keine Markdown, keine Erklärungen."""

        try:
            old_model = self.model
            old_provider = self.provider

            from agent.providers import ModelProvider, resolve_model_provider_env
            self.model, self.provider = resolve_model_provider_env(
                model_env="REASONING_MODEL",
                provider_env="REASONING_MODEL_PROVIDER",
                fallback_model="qwen/qwq-32b",
                fallback_provider=ModelProvider.OPENROUTER,
            )

            response = await self._call_llm([
                {"role": "user", "content": plan_prompt}
            ])

            self.model = old_model
            self.provider = old_provider

            plan = extract_json_robust(response)
            if plan and plan.get('steps'):
                log.info(f"Visual-Plan erstellt: {plan.get('goal', 'N/A')} ({len(plan.get('steps', []))} Schritte)")
                return plan
            else:
                log.warning("Kein valides JSON im Meta-Agent Response gefunden")
                return self._create_fallback_plan(task)

        except Exception as e:
            log.error(f"Fehler bei Visual-Plan-Erstellung: {e}")
            return self._create_fallback_plan(task)

    def _extract_search_terms(self, task: str) -> str:
        """Extrahiert Suchbegriffe aus dem Task."""
        patterns = [
            r'(?:such|schau)\s+(?:nach|fuer|for)\s+(.+?)(?:\s+(?:auf|in|bei|von)|\.|$)',
            r'(?:search|find|look)\s+(?:for)?\s+(.+?)(?:\s+(?:on|in|at)|\.|$)',
        ]
        for p in patterns:
            m = re.search(p, task, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    def _create_fallback_plan(self, task: str) -> dict:
        """Fallback-Plan wenn die AI-Planung fehlschlaegt."""
        url_match = re.search(r'https?://[^\s]+', task)
        domain_match = re.search(r'([a-zA-Z0-9.-]+\.(de|com|org|net|io))', task)

        url = url_match.group(0) if url_match else (
            f"https://{domain_match.group(1)}" if domain_match else "https://www.google.com"
        )

        search_terms = self._extract_search_terms(task)

        steps = [
            {
                "step_number": 1,
                "action": "navigate",
                "description": f"Oeffne {url}",
                "target": None,
                "value": url,
                "verification": "URL geladen",
                "fallback": "Warte und versuche erneut"
            },
            {
                "step_number": 2,
                "action": "wait",
                "description": "Warte auf Seiten-Ladung",
                "target": None,
                "value": "3s",
                "verification": "Seite stabil",
                "fallback": "Weiter mit naechstem Schritt"
            },
        ]

        if search_terms:
            steps.append({
                "step_number": 3,
                "action": "type",
                "description": f"Suche nach: {search_terms}",
                "target": "Suchfeld",
                "value": search_terms,
                "verification": "Suchbegriff eingegeben",
                "fallback": "Suchfeld manuell finden"
            })
            steps.append({
                "step_number": 4,
                "action": "click",
                "description": "Suche absenden",
                "target": "Such-Button oder Enter",
                "value": None,
                "verification": "Suchergebnisse angezeigt",
                "fallback": "Enter druecken"
            })

        verify_step_number = len(steps) + 1
        steps.append({
            "step_number": verify_step_number,
            "action": "verify",
            "description": "Pruefe ob Aufgabe erfuellt",
            "target": None,
            "value": None,
            "verification": "Ziel erreicht",
            "fallback": "Manuelle Interaktion noetig"
        })

        return {
            "goal": task,
            "url": url,
            "steps": steps,
            "success_criteria": ["Seite erfolgreich geladen"],
            "estimated_steps": len(steps),
            "_fallback": True
        }

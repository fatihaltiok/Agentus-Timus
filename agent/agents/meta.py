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
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.base_agent import BaseAgent
from agent.prompts import META_SYSTEM_PROMPT

log = logging.getLogger("TimusAgent-v4.4")


from agent.shared.json_utils import extract_json_robust  # noqa: F401 - re-exported


class MetaAgent(BaseAgent):
    _META_HANDOFF_HEADER = "# META ORCHESTRATION HANDOFF"
    _ORIGINAL_TASK_HEADER = "# ORIGINAL USER TASK"
    _SPECIALIST_TOOL_AGENT_MAP = {
        "search_web": "research",
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
        hidden_tool_names = cls.SYSTEM_ONLY_TOOLS | {"search_web", "open_url"}
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

    def __init__(self, tools_description_string: str):
        filtered = self._filter_tools_for_meta(tools_description_string)
        super().__init__(META_SYSTEM_PROMPT, filtered, 30, "meta")

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

    @classmethod
    def _build_specialist_delegation_task(cls, method: str, params: Dict[str, Any]) -> str:
        if method == "search_web":
            query = cls._shorten(params.get("query"))
            return f"Recherchiere diese Anfrage und liefere belastbare Ergebnisse: {query}".strip()

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

        if method in {"take_screenshot", "click_element", "type_in_field"}:
            detail = cls._shorten(params.get("description") or params.get("text") or params.get("selector"))
            return f"Fuehre die visuelle UI-Aufgabe aus: {method}. Kontext: {detail}".strip()

        if method in {"execute_action_plan", "execute_visual_task", "execute_visual_task_quick"}:
            detail = cls._shorten(params.get("task") or params.get("instruction") or params.get("goal"))
            return f"Fuehre die visuelle Aufgabe aus: {detail}".strip()

        return ""

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
            "original_user_task": original_task.strip(),
        }
        current_stage: Optional[Dict[str, Any]] = None
        in_recipe_stages = False

        for raw_line in handoff_block.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue

            if stripped == "recipe_stages:":
                in_recipe_stages = True
                current_stage = None
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
            else:
                payload[normalized_key] = normalized_value

        if not payload.get("recipe_stages"):
            return None
        return payload

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
        site_kind = str(handoff.get("site_kind") or "").strip()
        if site_kind:
            payload_lines.append(f"- site_kind: {site_kind}")

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
            lines.append("")
            lines.append("Finales Ergebnis:")
            lines.append(str(final_success["result_full"]))
        return "\n".join(lines)

    async def _execute_meta_recipe_handoff(
        self,
        task: str,
        handoff: Dict[str, Any],
    ) -> Optional[str]:
        recipe_id = str(handoff.get("recommended_recipe_id") or "").strip()
        stages = list(handoff.get("recipe_stages") or [])
        if not recipe_id or not stages:
            return None

        original_user_task = str(handoff.get("original_user_task") or task).strip()
        stage_history: List[Dict[str, Any]] = []
        previous_stage_result: Optional[Dict[str, Any]] = None

        for stage in stages:
            if not self._should_execute_optional_recipe_stage(handoff, stage):
                stage_history.append(
                    {
                        "stage_id": stage.get("stage_id", "stage"),
                        "agent": stage.get("agent", "unknown"),
                        "status": "skipped",
                        "result_preview": "Optionale Stage fuer diese Anfrage uebersprungen.",
                    }
                )
                continue

            stage_task = self._build_recipe_stage_delegation_task(
                handoff=handoff,
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
            }
            stage_history.append(history_entry)
            previous_stage_result = history_entry

            if history_entry["status"] != "success":
                if stage.get("optional"):
                    continue
                return self._render_recipe_execution_summary(
                    recipe_id=recipe_id,
                    original_user_task=original_user_task,
                    stage_history=stage_history,
                    failure=history_entry,
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

            from agent.providers import ModelProvider
            self.model = os.getenv("REASONING_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
            self.provider = ModelProvider.OPENROUTER

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

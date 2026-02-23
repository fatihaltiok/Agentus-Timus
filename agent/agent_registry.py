"""
Agent Registry - Ermoeglicht dynamische Agent-zu-Agent Delegation.

FEATURES:
- Zentrale Registry mit Factory-Pattern (Lazy-Instantiierung)
- Agent-zu-Agent Delegation als MCP-Tool-Call
- Capability-basierte Agent-Auswahl
- Loop-Prevention via Delegation-Stack
"""

import asyncio
import logging
import os
import httpx
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from contextvars import ContextVar

log = logging.getLogger("AgentRegistry")


@dataclass
class AgentSpec:
    """Beschreibt einen Agenten ohne ihn zu instanziieren."""
    name: str
    agent_type: str
    capabilities: List[str]
    factory: Callable
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)


class AgentRegistry:
    """
    Zentrale Registry fuer Agent-zu-Agent Delegation.

    - Registriert Agent-Blueprints (AgentSpec) ohne sofortige Instanziierung
    - Lazy-Instantiierung: Agent wird erst bei erster Delegation erstellt
    - Loop-Prevention via Delegation-Stack
    """

    MAX_DELEGATION_DEPTH = 3
    AGENT_TYPE_ALIASES = {
        "development": "developer",
        "dev": "developer",
        "researcher": "research",
        "analyst": "reasoning",
        "vision": "visual",
        "daten": "data",
        "bash": "shell",
        "terminal": "shell",
        "monitoring": "system",
        "koordinator": "meta",
        "orchestrator": "meta",
    }

    def __init__(self):
        self._specs: Dict[str, AgentSpec] = {}
        self._instances: Dict[str, Any] = {}
        self._tools_description: Optional[str] = None
        # Task-lokaler Delegation-Stack: verhindert False-Positives bei Parallel-Requests.
        self._delegation_stack_var: ContextVar[tuple[str, ...]] = ContextVar(
            "timus_delegation_stack", default=()
        )

    def _resolve_effective_session_id(
        self, from_agent: str, session_id: Optional[str]
    ) -> Optional[str]:
        """Leitet effektive Session-ID aus Parameter oder Source-Agent ab."""
        if session_id:
            return session_id

        source_instance = self._instances.get(from_agent)
        if source_instance is not None:
            return getattr(source_instance, "conversation_session_id", None)
        return None

    def _log_canvas_delegation(
        self,
        *,
        from_agent: str,
        to_agent: str,
        session_id: Optional[str],
        status: str,
        task: str = "",
        message: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Best-effort Logging fuer Delegation im Canvas."""
        if not session_id:
            return

        try:
            from orchestration.canvas_store import canvas_store

            canvas_id = canvas_store.get_canvas_id_for_session(session_id)
            if not canvas_id:
                return

            from_node = f"agent:{from_agent}"
            to_node = f"agent:{to_agent}"

            canvas_store.upsert_node(
                canvas_id=canvas_id,
                node_id=from_node,
                node_type="agent",
                title=from_agent,
                status="running" if status == "running" else "completed",
                metadata={"last_session_id": session_id},
            )
            canvas_store.upsert_node(
                canvas_id=canvas_id,
                node_id=to_node,
                node_type="agent",
                title=to_agent,
                status=status,
                metadata={"last_session_id": session_id},
            )
            edge = canvas_store.add_edge(
                canvas_id=canvas_id,
                source_node_id=from_node,
                target_node_id=to_node,
                label="delegate_to_agent",
                kind="delegation",
                metadata={"session_id": session_id},
            )
            canvas_store.add_event(
                canvas_id=canvas_id,
                event_type="delegation",
                status=status,
                agent=from_agent,
                node_id=to_node,
                session_id=session_id,
                message=message or f"{from_agent} -> {to_agent}",
                payload={
                    "from_agent": from_agent,
                    "to_agent": to_agent,
                    "task_preview": (task or "")[:200],
                    "edge_id": edge.get("id", ""),
                    **(payload or {}),
                },
            )
        except Exception as e:
            log.debug(f"Canvas-Delegation-Logging uebersprungen: {e}")

    def normalize_agent_name(self, name: str) -> str:
        """Normalisiert Agent-Namen (Lowercase + Alias-Aufloesung)."""
        normalized = (name or "").strip().lower()
        return self.AGENT_TYPE_ALIASES.get(normalized, normalized)

    def get_current_agent_name(self) -> Optional[str]:
        """Liefert den aktuell laufenden delegierten Agenten (falls vorhanden)."""
        stack = self._delegation_stack_var.get()
        return stack[-1] if stack else None

    def register_spec(
        self,
        name: str,
        agent_type: str,
        capabilities: List[str],
        factory: Callable,
        extra_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registriert ein Agent-Blueprint (ohne zu instanziieren)."""
        self._specs[name] = AgentSpec(
            name=name,
            agent_type=agent_type,
            capabilities=capabilities,
            factory=factory,
            extra_kwargs=extra_kwargs or {},
        )
        log.info(f"AgentSpec registriert: {name} (capabilities={capabilities})")

    async def _get_tools_description(self) -> str:
        """Holt Tools-Description vom MCP-Server (lazy, gecacht)."""
        if not self._tools_description:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get("http://127.0.0.1:5000/get_tool_descriptions")
                data = resp.json()
                self._tools_description = data["descriptions"]
            log.info("Tools-Description vom MCP-Server geladen")
        return self._tools_description

    async def _get_or_create(self, name: str) -> Any:
        """Lazy-Instantiierung: Agent wird erst bei erster Delegation erstellt."""
        if name not in self._instances:
            spec = self._specs[name]
            tools_desc = await self._get_tools_description()
            self._instances[name] = spec.factory(
                tools_description_string=tools_desc,
                **spec.extra_kwargs,
            )
            log.info(f"Agent instanziiert: {name} ({spec.factory.__name__})")
        return self._instances[name]

    # Strings die auf ein nur teilweise abgeschlossenes Ergebnis hinweisen
    _PARTIAL_MARKERS = frozenset({"Limit erreicht.", "Max Iterationen."})

    async def delegate(
        self,
        from_agent: str,
        to_agent: str,
        task: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delegiert Task mit Loop-Prevention via Stack.

        Gibt immer ein strukturiertes Dict zurueck:
            {"status": "success",  "agent": "...", "result": "..."}
            {"status": "partial",  "agent": "...", "result": "...", "note": "..."}
            {"status": "error",    "agent": "...", "error":  "..."}
        """
        from_agent = self.normalize_agent_name(from_agent)
        to_agent = self.normalize_agent_name(to_agent)
        effective_session_id = self._resolve_effective_session_id(from_agent, session_id)

        if to_agent not in self._specs:
            error_msg = (
                f"FEHLER: Agent '{to_agent}' nicht registriert. "
                f"Verfuegbar: {list(self._specs.keys())}"
            )
            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="error",
                task=task,
                message=f"Delegation fehlgeschlagen: Agent '{to_agent}' nicht registriert",
                payload={"reason": "agent_not_registered"},
            )
            return {"status": "error", "agent": to_agent, "error": error_msg}

        stack = list(self._delegation_stack_var.get())

        if to_agent in stack:
            chain = " -> ".join(stack)
            error_msg = f"FEHLER: Zirkulaere Delegation ({chain} -> {to_agent})"
            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="error",
                task=task,
                message=f"Zirkulaere Delegation: {chain} -> {to_agent}",
                payload={"reason": "cycle_detected", "chain": chain},
            )
            return {"status": "error", "agent": to_agent, "error": error_msg}

        if len(stack) >= self.MAX_DELEGATION_DEPTH:
            error_msg = (
                f"FEHLER: Max Delegation-Tiefe ({self.MAX_DELEGATION_DEPTH}) erreicht"
            )
            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="error",
                task=task,
                message=f"Max Delegation-Tiefe ({self.MAX_DELEGATION_DEPTH}) erreicht",
                payload={"reason": "max_depth"},
            )
            return {"status": "error", "agent": to_agent, "error": error_msg}

        next_stack = tuple(stack + [to_agent])
        stack_token = self._delegation_stack_var.set(next_stack)
        log.info(f"Delegation: {from_agent} -> {to_agent} (Stack: {list(next_stack)})")
        self._log_canvas_delegation(
            from_agent=from_agent,
            to_agent=to_agent,
            session_id=effective_session_id,
            status="running",
            task=task,
            message=f"Delegation gestartet: {from_agent} -> {to_agent}",
            payload={"stack_depth": len(next_stack)},
        )

        if to_agent == "research":
            timeout = float(os.getenv("RESEARCH_TIMEOUT", "180"))
        else:
            timeout = float(os.getenv("DELEGATION_TIMEOUT", "120"))
        max_retries = int(os.getenv("DELEGATION_MAX_RETRIES", "1"))

        agent = None
        previous_session_id: Optional[str] = None
        target_has_session_attr = False
        last_error: Optional[Exception] = None
        try:
            agent = await self._get_or_create(to_agent)
            if hasattr(agent, "conversation_session_id"):
                target_has_session_attr = True
                previous_session_id = getattr(agent, "conversation_session_id", None)
                if effective_session_id:
                    setattr(agent, "conversation_session_id", effective_session_id)

            for attempt in range(max_retries):
                try:
                    raw = await asyncio.wait_for(agent.run(task), timeout=timeout)
                    last_error = None
                    break
                except asyncio.TimeoutError as e:
                    last_error = TimeoutError(
                        f"Agent '{to_agent}' hat nicht innerhalb von {timeout}s geantwortet"
                    )
                    log.warning(
                        f"Delegation {from_agent} -> {to_agent} Timeout "
                        f"(Versuch {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except Exception as e:
                    last_error = e
                    log.warning(
                        f"Delegation {from_agent} -> {to_agent} Fehler "
                        f"(Versuch {attempt + 1}/{max_retries}): {e}"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
            else:
                raise last_error  # type: ignore[misc]

            if last_error is not None:
                raise last_error

            # Partial-Result-Erkennung
            result_str = str(raw)
            if result_str in self._PARTIAL_MARKERS:
                status = "partial"
                self._log_canvas_delegation(
                    from_agent=from_agent,
                    to_agent=to_agent,
                    session_id=effective_session_id,
                    status="completed",
                    task=task,
                    message=f"Delegation partiell: {from_agent} -> {to_agent}",
                    payload={"result_preview": result_str[:240]},
                )
                return {
                    "status": "partial",
                    "agent": to_agent,
                    "result": result_str,
                    "note": "Aufgabe nicht vollstaendig abgeschlossen",
                }

            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="completed",
                task=task,
                message=f"Delegation abgeschlossen: {from_agent} -> {to_agent}",
                payload={"result_preview": result_str[:240]},
            )
            return {"status": "success", "agent": to_agent, "result": result_str}

        except Exception as e:
            log.error(f"Delegation {from_agent} -> {to_agent} fehlgeschlagen: {e}")
            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="error",
                task=task,
                message=f"Delegation fehlgeschlagen: {e}",
                payload={"exception": str(e)[:300]},
            )
            return {
                "status": "error",
                "agent": to_agent,
                "error": f"FEHLER: Delegation an '{to_agent}' fehlgeschlagen: {e}",
            }
        finally:
            if target_has_session_attr and agent is not None:
                setattr(agent, "conversation_session_id", previous_session_id)
            self._delegation_stack_var.reset(stack_token)

    def find_by_capability(self, capability: str) -> List[AgentSpec]:
        """Findet alle AgentSpecs mit einer bestimmten Capability."""
        capability = (capability or "").strip().lower()
        return [
            spec for spec in self._specs.values()
            if capability in spec.capabilities
        ]

    def list_agents(self) -> List[str]:
        """Listet alle registrierten Agent-Namen."""
        return list(self._specs.keys())

    def get_agent_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Gibt Info ueber einen registrierten Agenten."""
        spec = self._specs.get(name)
        if not spec:
            return None
        return {
            "name": spec.name,
            "type": spec.agent_type,
            "capabilities": spec.capabilities,
            "instantiated": name in self._instances,
        }


# Singleton-Instanz
agent_registry = AgentRegistry()


def register_all_agents():
    """Registriert alle Standard-Timus-Agenten als Specs (ohne Instanziierung)."""
    from agent.agents import (
        ExecutorAgent, DeepResearchAgent, ReasoningAgent,
        CreativeAgent, DeveloperAgent, MetaAgent, VisualAgent,
        DataAgent, DocumentAgent, CommunicationAgent, SystemAgent, ShellAgent,
    )
    from agent.agents.image import ImageAgent

    registry = agent_registry

    registry.register_spec(
        "executor", "executor",
        ["execution", "tools", "simple_tasks"],
        ExecutorAgent,
    )
    registry.register_spec(
        "research", "research",
        ["research", "search", "deep_analysis"],
        DeepResearchAgent,
    )
    registry.register_spec(
        "reasoning", "reasoning",
        ["reasoning", "analysis", "debugging"],
        ReasoningAgent,
        extra_kwargs={"enable_thinking": True},
    )
    registry.register_spec(
        "creative", "creative",
        ["creative", "images", "content_generation"],
        CreativeAgent,
    )
    registry.register_spec(
        "developer", "developer",
        ["code", "development", "files", "refactoring"],
        DeveloperAgent,
    )
    registry.register_spec(
        "visual", "visual",
        ["vision", "ui", "browser", "screenshots", "navigation"],
        VisualAgent,
    )
    registry.register_spec(
        "meta", "meta",
        ["orchestration", "planning", "coordination"],
        MetaAgent,
    )
    registry.register_spec(
        "image", "image",
        ["image_analysis", "vision", "photo", "bild"],
        ImageAgent,
    )
    registry.register_spec(
        "data", "data",
        ["data", "csv", "excel", "json", "analysis", "statistics"],
        DataAgent,
    )
    registry.register_spec(
        "document", "document",
        ["document", "pdf", "docx", "report", "writing"],
        DocumentAgent,
    )
    registry.register_spec(
        "communication", "communication",
        ["communication", "email", "letter", "linkedin"],
        CommunicationAgent,
    )
    registry.register_spec(
        "system", "system",
        ["system", "monitoring", "logs", "processes", "stats"],
        SystemAgent,
    )
    registry.register_spec(
        "shell", "shell",
        ["shell", "bash", "command", "script", "cron"],
        ShellAgent,
    )

    log.info(f"Alle Agenten registriert: {registry.list_agents()}")


__all__ = [
    "AgentRegistry",
    "AgentSpec",
    "agent_registry",
    "register_all_agents",
]

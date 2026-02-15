"""
Agent Registry - Ermoeglicht dynamische Agent-zu-Agent Delegation.

FEATURES:
- Zentrale Registry mit Factory-Pattern (Lazy-Instantiierung)
- Agent-zu-Agent Delegation als MCP-Tool-Call
- Capability-basierte Agent-Auswahl
- Loop-Prevention via Delegation-Stack
"""

import logging
import httpx
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

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

    def __init__(self):
        self._specs: Dict[str, AgentSpec] = {}
        self._instances: Dict[str, Any] = {}
        self._tools_description: Optional[str] = None
        self._delegation_stack: List[str] = []

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

    async def delegate(self, from_agent: str, to_agent: str, task: str) -> str:
        """Delegiert Task mit Loop-Prevention via Stack."""
        if to_agent not in self._specs:
            return f"FEHLER: Agent '{to_agent}' nicht registriert. Verfuegbar: {list(self._specs.keys())}"

        if to_agent in self._delegation_stack:
            chain = " -> ".join(self._delegation_stack)
            return f"FEHLER: Zirkulaere Delegation ({chain} -> {to_agent})"

        if len(self._delegation_stack) >= self.MAX_DELEGATION_DEPTH:
            return f"FEHLER: Max Delegation-Tiefe ({self.MAX_DELEGATION_DEPTH}) erreicht"

        self._delegation_stack.append(to_agent)
        log.info(f"Delegation: {from_agent} -> {to_agent} (Stack: {self._delegation_stack})")

        try:
            agent = await self._get_or_create(to_agent)
            result = await agent.run(task)
            return result
        except Exception as e:
            log.error(f"Delegation {from_agent} -> {to_agent} fehlgeschlagen: {e}")
            return f"FEHLER: Delegation an '{to_agent}' fehlgeschlagen: {e}"
        finally:
            self._delegation_stack.pop()

    def find_by_capability(self, capability: str) -> List[AgentSpec]:
        """Findet alle AgentSpecs mit einer bestimmten Capability."""
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
    )

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

    log.info(f"Alle Agenten registriert: {registry.list_agents()}")


__all__ = [
    "AgentRegistry",
    "AgentSpec",
    "agent_registry",
    "register_all_agents",
]

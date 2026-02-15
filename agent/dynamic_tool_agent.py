# agent/dynamic_tool_agent.py (VERSION 1.0)
"""
Dynamic Tool Agent - Basisklasse für Agenten mit dynamischer Tool-Nutzung.

FEATURES:
- OpenAI Function Calling Integration
- ReAct-Loop als Fallback für nicht-Function-Calling-Modelle
- Agent-spezifische Tool-Filterung via Capabilities
- Automatische Tool-Discovery und -Ausführung
- Multi-Provider Support (OpenAI, Anthropic, DeepSeek, etc.)

AUTOR: Timus Development
DATUM: Februar 2026
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod

from openai import OpenAI
from tools.tool_registry_v2 import registry_v2, ToolCategory

log = logging.getLogger("DynamicToolAgent")


class ExecutionMode(str, Enum):
    FUNCTION_CALLING = "function_calling"
    REACT = "react"
    HYBRID = "hybrid"


@dataclass
class ToolCallResult:
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    success: bool
    error: Optional[str] = None


@dataclass
class AgentResponse:
    content: str
    tool_calls: List[ToolCallResult]
    iterations: int
    finished: bool


class DynamicToolAgent(ABC):
    """
    Basisklasse für Agenten mit dynamischer Tool-Nutzung.
    
    Unterklassen müssen implementieren:
    - get_system_prompt() -> str
    - get_capabilities() -> List[str] (optional, für Tool-Filterung)
    
    Usage:
        class MyAgent(DynamicToolAgent):
            def get_system_prompt(self):
                return "Du bist ein hilfreicher Assistent..."
            
            def get_capabilities(self):
                return ["browser", "search"]
        
        agent = MyAgent(model="gpt-4o", provider="openai")
        result = await agent.run("Suche nach Python Tutorials")
    """
    
    MAX_ITERATIONS = 15
    
    def __init__(
        self,
        model: str,
        provider: str = "openai",
        execution_mode: ExecutionMode = ExecutionMode.FUNCTION_CALLING,
        max_iterations: int = 15
    ):
        self.model = model
        self.provider = provider
        self.execution_mode = execution_mode
        self.max_iterations = max_iterations
        self.conversation: List[Dict] = []
        
        self._init_client()
        
        self._available_tools: Optional[List[str]] = None
    
    def _init_client(self):
        if self.provider == "openai":
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        elif self.provider == "deepseek":
            self.client = OpenAI(
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url="https://api.deepseek.com/v1"
            )
        elif self.provider == "anthropic":
            from anthropic import Anthropic
            self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        else:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        pass
    
    def get_capabilities(self) -> List[str]:
        return []
    
    def get_tool_manifest(self) -> str:
        if self._available_tools:
            return registry_v2.get_tool_manifest(self._available_tools)
        return registry_v2.get_tool_manifest()
    
    def get_tools_schema(self) -> List[Dict]:
        if self._available_tools:
            return registry_v2.get_openai_tools_schema(self._available_tools)
        return registry_v2.get_openai_tools_schema()
    
    def filter_tools_by_capabilities(self, capabilities: List[str]):
        tools = registry_v2.get_tools_for_agent(capabilities)
        self._available_tools = [t.name for t in tools]
        log.info(f"Tools gefiltert für Capabilities {capabilities}: {len(self._available_tools)} Tools")
    
    async def run(self, task: str, context: Dict = None) -> AgentResponse:
        self.conversation = []
        
        system_prompt = self.get_system_prompt()
        if context:
            system_prompt += f"\n\nKontext:\n{json.dumps(context, indent=2, ensure_ascii=False)}"
        
        self.conversation.append({"role": "system", "content": system_prompt})
        self.conversation.append({"role": "user", "content": task})
        
        tool_calls_results: List[ToolCallResult] = []
        iterations = 0
        
        while iterations < self.max_iterations:
            iterations += 1
            log.info(f"Iteration {iterations}/{self.max_iterations}")
            
            if self.execution_mode == ExecutionMode.FUNCTION_CALLING:
                response = await self._run_function_calling_iteration()
            elif self.execution_mode == ExecutionMode.REACT:
                response = await self._run_react_iteration()
            else:
                response = await self._run_hybrid_iteration()
            
            tool_calls_results.extend(response.tool_calls)
            
            if response.finished:
                return AgentResponse(
                    content=response.content,
                    tool_calls=tool_calls_results,
                    iterations=iterations,
                    finished=True
                )
        
        return AgentResponse(
            content="Maximale Iterationen erreicht ohne finale Antwort.",
            tool_calls=tool_calls_results,
            iterations=iterations,
            finished=False
        )
    
    async def _run_function_calling_iteration(self) -> AgentResponse:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation,
                tools=self.get_tools_schema(),
                tool_choice="auto"
            )
        except Exception as e:
            log.error(f"LLM-Aufruf fehlgeschlagen: {e}")
            return AgentResponse(
                content=f"Fehler: {e}",
                tool_calls=[],
                iterations=1,
                finished=True
            )
        
        message = response.choices[0].message
        self.conversation.append(message.model_dump())
        
        if not message.tool_calls:
            return AgentResponse(
                content=message.content or "",
                tool_calls=[],
                iterations=1,
                finished=True
            )
        
        tool_results = []
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}
            
            try:
                result = await registry_v2.execute(tool_name, **args)
                tool_results.append(ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    result=result,
                    success=True
                ))
            except Exception as e:
                tool_results.append(ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    result=None,
                    success=False,
                    error=str(e)
                ))
                result = f"Fehler: {e}"
            
            self.conversation.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)[:4000]
            })
        
        return AgentResponse(
            content="",
            tool_calls=tool_results,
            iterations=1,
            finished=False
        )
    
    async def _run_react_iteration(self) -> AgentResponse:
        react_prompt = """
Du hast Zugriff auf folgende Tools:

{tool_manifest}

NUTZE DIESES FORMAT:
Thought: [Deine Überlegung was zu tun ist]
Action: [tool_name]
Action Input: {{"param1": "wert1"}}
Observation: [Wird automatisch eingefügt]
... (wiederholen bis fertig)
Final Answer: [Deine finale Antwort]

WICHTIG: Wenn du fertig bist, schreibe "Final Answer:" gefolgt von deiner Antwort.
"""
        
        last_message = self.conversation[-1]
        if last_message["role"] == "user":
            full_prompt = react_prompt.format(tool_manifest=self.get_tool_manifest())
            full_prompt += f"\n\nAufgabe: {last_message['content']}"
            self.conversation[-1]["content"] = full_prompt
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation
            )
        except Exception as e:
            return AgentResponse(
                content=f"Fehler: {e}",
                tool_calls=[],
                iterations=1,
                finished=True
            )
        
        content = response.choices[0].message.content
        self.conversation.append({"role": "assistant", "content": content})
        
        if "Final Answer:" in content:
            final_answer = content.split("Final Answer:")[-1].strip()
            return AgentResponse(
                content=final_answer,
                tool_calls=[],
                iterations=1,
                finished=True
            )
        
        import re
        action_match = re.search(
            r"Action:\s*(\w+)\s*\n\s*Action Input:\s*(\{[^}]+\})",
            content,
            re.DOTALL
        )
        
        if not action_match:
            return AgentResponse(
                content=content,
                tool_calls=[],
                iterations=1,
                finished=True
            )
        
        tool_name = action_match.group(1)
        try:
            args = json.loads(action_match.group(2))
        except:
            args = {}
        
        tool_results = []
        try:
            result = await registry_v2.execute(tool_name, **args)
            tool_results.append(ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                result=result,
                success=True
            ))
        except Exception as e:
            result = f"Fehler: {e}"
            tool_results.append(ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                result=None,
                success=False,
                error=str(e)
            ))
        
        observation = f"\nObservation: {str(result)[:2000]}\n"
        self.conversation.append({"role": "user", "content": observation})
        
        return AgentResponse(
            content="",
            tool_calls=tool_results,
            iterations=1,
            finished=False
        )
    
    async def _run_hybrid_iteration(self) -> AgentResponse:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation,
                tools=self.get_tools_schema(),
                tool_choice="auto"
            )
            
            if response.choices[0].message.tool_calls:
                return await self._run_function_calling_iteration()
            else:
                return await self._run_react_iteration()
        except:
            return await self._run_react_iteration()


class BrowserAgent(DynamicToolAgent):
    """Beispiel: Agent für Browser-Automatisierung."""
    
    def get_system_prompt(self) -> str:
        return """Du bist ein Browser-Automatisierungs-Agent.
        
Du kannst Webseiten öffnen, navigieren, Text extrahieren und mit Elementen interagieren.

Verfügbare Aktionen:
- URLs öffnen
- Auf Elemente klicken
- Text eingeben
- Links folgen
- Text extrahieren

Führe Aufgaben Schritt für Schritt aus und berichte über den Fortschritt."""
    
    def get_capabilities(self) -> List[str]:
        return ["browser", "navigation", "mouse"]
    
    def __init__(self, model: str = "gpt-4o", **kwargs):
        super().__init__(model=model, **kwargs)
        self.filter_tools_by_capabilities(self.get_capabilities())


class ResearchAgent(DynamicToolAgent):
    """Beispiel: Agent für Web-Recherche."""
    
    def get_system_prompt(self) -> str:
        return """Du bist ein Recherche-Agent.

Du kannst:
- Im Web suchen
- Webseiten analysieren
- Informationen zusammenfassen
- Quellen vergleichen

Sei gründlich und zitiere deine Quellen."""
    
    def get_capabilities(self) -> List[str]:
        return ["search", "browser", "research"]
    
    def __init__(self, model: str = "deepseek-reasoner", **kwargs):
        super().__init__(model=model, **kwargs)
        self.filter_tools_by_capabilities(self.get_capabilities())

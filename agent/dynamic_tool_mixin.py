# agent/dynamic_tool_mixin.py (VERSION 1.0)
"""
Dynamic Tool Mixin - Erweitert bestehende Agenten um dynamische Tool-Nutzung.

Dieses Mixin kann in bestehende Agenten (ExecutorAgent, VisualAgent, etc.) 
eingebunden werden, um ihnen die Fähigkeit zu geben:
- Tools dynamisch zu entdecken
- OpenAI Function Calling zu nutzen
- ReAct-Loop als Fallback zu verwenden

USAGE:
    class MyAgent(DynamicToolMixin, BaseAgent):
        def __init__(self, ...):
            super().__init__(...)
            self.init_dynamic_tools(capabilities=["browser", "search"])

AUTOR: Timus Development
DATUM: Februar 2026
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from openai import OpenAI

from tools.tool_registry_v2 import registry_v2, ToolCategory

log = logging.getLogger("DynamicToolMixin")


@dataclass
class ToolCallResult:
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    success: bool
    error: Optional[str] = None


class DynamicToolMixin:
    """
    Mixin für dynamische Tool-Nutzung in bestehenden Agenten.
    
    Fügt einem Agenten hinzu:
    - Tool Discovery via Registry
    - OpenAI Function Calling
    - ReAct-Loop Fallback
    - Agent-spezifische Tool-Filterung
    """
    
    _dynamic_tools_enabled: bool = False
    _available_tools: Optional[List[str]] = None
    _tool_client: Optional[OpenAI] = None
    _max_tool_iterations: int = 10
    
    def init_dynamic_tools(
        self,
        capabilities: List[str] = None,
        max_iterations: int = 10
    ):
        """
        Initialisiert dynamische Tool-Nutzung für diesen Agenten.
        
        Args:
            capabilities: Liste von Capabilities zum Filtern der Tools
                         (z.B. ["browser", "search", "mouse"])
            max_iterations: Maximale Tool-Iterationen pro Task
        """
        self._dynamic_tools_enabled = True
        self._max_tool_iterations = max_iterations
        
        if capabilities:
            tools = registry_v2.get_tools_for_agent(capabilities)
            self._available_tools = [t.name for t in tools]
            log.info(f"Dynamische Tools aktiviert: {len(self._available_tools)} Tools für {capabilities}")
        else:
            self._available_tools = None
            log.info("Dynamische Tools aktiviert: Alle Tools verfügbar")
        
        self._tool_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def get_tool_manifest(self) -> str:
        """Gibt das Tool-Manifest für LLM-Prompts zurück."""
        if not self._dynamic_tools_enabled:
            return "Dynamische Tools nicht aktiviert."
        
        if self._available_tools:
            return registry_v2.get_tool_manifest(self._available_tools)
        return registry_v2.get_tool_manifest()
    
    def get_tools_schema(self) -> List[Dict]:
        """Gibt das OpenAI Tools-Schema zurück."""
        if not self._dynamic_tools_enabled:
            return []
        
        if self._available_tools:
            return registry_v2.get_openai_tools_schema(self._available_tools)
        return registry_v2.get_openai_tools_schema()
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Führt ein Tool aus.
        
        Args:
            tool_name: Name des Tools
            **kwargs: Parameter für das Tool
            
        Returns:
            Ergebnis des Tool-Aufrufs
        """
        if not self._dynamic_tools_enabled:
            raise RuntimeError("Dynamische Tools nicht aktiviert. Rufe init_dynamic_tools() auf.")
        
        return await registry_v2.execute(tool_name, **kwargs)
    
    async def run_with_dynamic_tools(
        self,
        task: str,
        system_prompt: str,
        context: Dict = None,
        use_react_fallback: bool = True
    ) -> str:
        """
        Führt einen Task mit dynamischer Tool-Nutzung aus.
        
        Args:
            task: Die Aufgabe
            system_prompt: System-Prompt für den Agenten
            context: Optionaler Kontext
            use_react_fallback: Ob ReAct-Loop als Fallback genutzt werden soll
            
        Returns:
            Finale Antwort des Agenten
        """
        if not self._dynamic_tools_enabled:
            log.warning("Dynamische Tools nicht aktiviert, nutze Standard-Ausführung")
            return await self._run_standard(task)
        
        conversation = []
        
        full_system = system_prompt
        if context:
            full_system += f"\n\nKontext:\n{json.dumps(context, indent=2, ensure_ascii=False)}"
        
        conversation.append({"role": "system", "content": full_system})
        conversation.append({"role": "user", "content": task})
        
        tool_calls_made = []
        iterations = 0
        
        while iterations < self._max_tool_iterations:
            iterations += 1
            
            try:
                response = self._tool_client.chat.completions.create(
                    model=getattr(self, 'model', 'gpt-4o'),
                    messages=conversation,
                    tools=self.get_tools_schema(),
                    tool_choice="auto"
                )
            except Exception as e:
                log.error(f"LLM-Aufruf fehlgeschlagen: {e}")
                if use_react_fallback:
                    return await self._run_react_fallback(task, system_prompt, conversation)
                return f"Fehler: {e}"
            
            message = response.choices[0].message
            conversation.append(message.model_dump())
            
            if not message.tool_calls:
                return message.content or "Keine Antwort generiert."
            
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                
                try:
                    log.info(f"Tool-Aufruf: {tool_name}({list(args.keys())})")
                    result = await self.execute_tool(tool_name, **args)
                    
                    tool_calls_made.append(ToolCallResult(
                        tool_name=tool_name,
                        arguments=args,
                        result=result,
                        success=True
                    ))
                    
                except Exception as e:
                    result = f"Fehler: {e}"
                    tool_calls_made.append(ToolCallResult(
                        tool_name=tool_name,
                        arguments=args,
                        result=None,
                        success=False,
                        error=str(e)
                    ))
                
                result_str = str(result)[:4000]
                
                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_str
                })
        
        return f"Maximale Iterationen erreicht. Letzte Tool-Calls: {len(tool_calls_made)}"
    
    async def _run_react_fallback(
        self,
        task: str,
        system_prompt: str,
        conversation: List[Dict]
    ) -> str:
        """
        ReAct-Loop Fallback für Modelle ohne Function Calling.
        """
        import re
        
        react_prompt = f"""
{system_prompt}

Du hast Zugriff auf folgende Tools:

{self.get_tool_manifest()}

NUTZE DIESES FORMAT:
Thought: [Deine Überlegung]
Action: [tool_name]
Action Input: {{"param": "value"}}
Observation: [Wird automatisch eingefügt]
... (wiederholen bis fertig)
Final Answer: [Deine finale Antwort]

WICHTIG: Wenn du fertig bist, schreibe "Final Answer:" gefolgt von deiner Antwort.

Aufgabe: {task}
"""
        
        react_conversation = [{"role": "user", "content": react_prompt}]
        
        for iteration in range(self._max_tool_iterations):
            try:
                response = self._tool_client.chat.completions.create(
                    model=getattr(self, 'model', 'gpt-4o'),
                    messages=react_conversation
                )
            except Exception as e:
                return f"Fehler: {e}"
            
            content = response.choices[0].message.content
            react_conversation.append({"role": "assistant", "content": content})
            
            if "Final Answer:" in content:
                return content.split("Final Answer:")[-1].strip()
            
            action_match = re.search(
                r"Action:\s*(\w+)\s*\n\s*Action Input:\s*(\{[^}]+\})",
                content,
                re.DOTALL
            )
            
            if not action_match:
                return content
            
            tool_name = action_match.group(1)
            try:
                args = json.loads(action_match.group(2))
            except:
                args = {}
            
            try:
                result = await self.execute_tool(tool_name, **args)
            except Exception as e:
                result = f"Fehler: {e}"
            
            react_conversation.append({
                "role": "user",
                "content": f"\nObservation: {str(result)[:2000]}\n"
            })
        
        return "Maximale Iterationen ohne finale Antwort."
    
    async def _run_standard(self, task: str) -> str:
        """
        Standard-Ausführung ohne dynamische Tools.
        Override in der Basisklasse.
        """
        return f"Task: {task} (Standard-Ausführung nicht implementiert)"
    
    def list_available_tools(self) -> List[str]:
        """Listet alle verfügbaren Tools auf."""
        if self._available_tools:
            return self._available_tools
        return list(registry_v2.list_all_tools().keys())


def create_dynamic_agent(
    base_class,
    name: str,
    capabilities: List[str],
    system_prompt: str,
    model: str = "gpt-4o"
):
    """
    Factory-Funktion zum Erstellen eines dynamischen Agenten.
    
    Args:
        base_class: Die Basisklasse (z.B. ExecutorAgent)
        name: Name des Agenten
        capabilities: Tool-Capabilities
        system_prompt: System-Prompt
        model: LLM-Modell
        
    Returns:
        Neue Agent-Klasse mit dynamischen Tools
    """
    class DynamicAgent(DynamicToolMixin, base_class):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.name = name
            self.system_prompt = system_prompt
            self.init_dynamic_tools(capabilities=capabilities)
    
    DynamicAgent.__name__ = name
    return DynamicAgent

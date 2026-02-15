# tools/tool_registry_v2.py (VERSION 3.0 - Bridge)
"""
Erweiterte Tool-Registry mit Rich Metadata und JSON-RPC Bridge.

VERSION 3.0: Dual-Registrierung - Tools werden sowohl in der V2 Registry
als auch in jsonrpcserver's global_methods registriert. Dies ermoeglicht
eine schrittweise Migration von V1 (@method) zu V2 (@tool) ohne
Unterbrechung des JSON-RPC Dispatch.

FEATURES:
- Tool-Registrierung mit Description, Parameters, Capabilities
- Automatische JSON-RPC Kompatibilitaet (Success/Error Wrapping)
- OpenAI Function Calling Schema Generator
- Anthropic Tool Schema Generator
- Agent-spezifische Tool-Filterung
- Capability-basiertes Tool Discovery
- Thread-safe Singleton Pattern

AUTOR: Timus Development
DATUM: Februar 2026
"""

import logging
import inspect
import json
import asyncio
from typing import Dict, Callable, Any, List, Optional, TypedDict, get_type_hints
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

# JSON-RPC Bridge Imports
from jsonrpcserver import Success, Error
from jsonrpcserver.methods import global_methods

log = logging.getLogger("ToolRegistryV2")


class ToolCategory(str, Enum):
    BROWSER = "browser"
    VISION = "vision"
    MOUSE = "mouse"
    SEARCH = "search"
    FILE = "file"
    CODE = "code"
    MEMORY = "memory"
    VOICE = "voice"
    SYSTEM = "system"
    RESEARCH = "research"
    AUTOMATION = "automation"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    DOCUMENT = "document"
    DEBUG = "debug"
    UI = "ui"


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None


@dataclass
class ToolMetadata:
    name: str
    description: str
    parameters: List[ToolParameter]
    capabilities: List[str]
    category: ToolCategory
    function: Callable
    examples: List[str] = field(default_factory=list)
    returns: str = "dict"
    is_async: bool = False

    def to_openai_schema(self) -> Dict[str, Any]:
        properties = {}
        required = []

        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

    def to_anthropic_schema(self) -> Dict[str, Any]:
        properties = {}
        for p in self.parameters:
            prop = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": [p.name for p in self.parameters if p.required]
            }
        }

    def to_manifest_entry(self) -> str:
        params_str = ", ".join(
            f"{p.name}: {p.type}" + ("" if p.required else " = optional")
            for p in self.parameters[:5]
        )
        if len(self.parameters) > 5:
            params_str += ", ..."

        return f"- {self.name}({params_str})\n  {self.description}\n  Category: {self.category.value}"


class ToolRegistryV2:
    """
    Erweiterte Singleton Tool-Registry mit Rich Metadata und JSON-RPC Bridge.

    Jedes registrierte Tool wird automatisch auch in jsonrpcserver's global_methods
    eingetragen, sodass JSON-RPC Dispatch weiterhin funktioniert.

    Usage:
        @tool(
            name="browser_navigate",
            description="Navigiert zu einer URL",
            parameters=[P("url", "string", "Die Ziel-URL", required=True)],
            capabilities=["browser", "navigation"],
            category=C.BROWSER
        )
        async def browser_navigate(url: str) -> dict:
            return {"status": "ok", "url": url}
    """
    _instance = None
    _tools: Dict[str, ToolMetadata] = {}
    _capability_index: Dict[str, List[str]] = {}
    _category_index: Dict[str, List[str]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._tools = {}
            cls._capability_index = {}
            cls._category_index = {}
        return cls._instance

    def register(
        self,
        name: str,
        description: str,
        parameters: List[ToolParameter],
        capabilities: List[str],
        category: ToolCategory,
        examples: List[str] = None,
        returns: str = "dict",
        jsonrpc_name: str = None
    ) -> Callable:
        """
        Registriert ein Tool in V2 Registry UND jsonrpcserver global_methods.

        Args:
            name: V2 Tool-Name (fuer Registry, Schema-Generierung)
            description: Beschreibung fuer LLM
            parameters: Liste von ToolParameter
            capabilities: Faehigkeiten (fuer Filterung)
            category: ToolCategory
            examples: Beispiel-Aufrufe
            returns: Return-Type Beschreibung
            jsonrpc_name: Optionaler JSON-RPC Methodenname (default: name).
                          Nuetzlich wenn der bisherige RPC-Name anders war.
        """
        rpc_name = jsonrpc_name or name

        def decorator(fn: Callable) -> Callable:
            is_async = inspect.iscoroutinefunction(fn)

            # 1. V2 Metadata registrieren
            metadata = ToolMetadata(
                name=name,
                description=description,
                parameters=parameters,
                capabilities=capabilities,
                category=category,
                function=fn,
                examples=examples or [],
                returns=returns,
                is_async=is_async
            )

            self._tools[name] = metadata

            # Capability Index
            for cap in capabilities:
                if cap not in self._capability_index:
                    self._capability_index[cap] = []
                if name not in self._capability_index[cap]:
                    self._capability_index[cap].append(name)

            # Category Index
            cat_key = category.value
            if cat_key not in self._category_index:
                self._category_index[cat_key] = []
            if name not in self._category_index[cat_key]:
                self._category_index[cat_key].append(name)

            # 2. JSON-RPC Bridge: Wrapper der dict -> Success konvertiert
            if is_async:
                @wraps(fn)
                async def jsonrpc_wrapper(*args, **kwargs):
                    try:
                        result = await fn(*args, **kwargs)
                        if isinstance(result, dict):
                            return Success(result)
                        # Bereits ein Success/Error Objekt (Hybrid-Modus)
                        return result
                    except Exception as e:
                        log.error(f"Tool {name} error: {e}")
                        return Error(code=-32000, message=str(e))
            else:
                @wraps(fn)
                def jsonrpc_wrapper(*args, **kwargs):
                    try:
                        result = fn(*args, **kwargs)
                        if isinstance(result, dict):
                            return Success(result)
                        return result
                    except Exception as e:
                        log.error(f"Tool {name} error: {e}")
                        return Error(code=-32000, message=str(e))

            # In jsonrpcserver registrieren
            global_methods[rpc_name] = jsonrpc_wrapper

            fn_type = "async" if is_async else "sync"
            rpc_info = f" (RPC: {rpc_name})" if rpc_name != name else ""
            log.info(f"Tool registriert: {name} ({fn_type}) [{category.value}]{rpc_info}")

            # Original-Funktion zurueckgeben (V2 execute() bekommt plain dicts)
            return fn

        return decorator

    def get_tool(self, name: str) -> ToolMetadata:
        if name not in self._tools:
            available = list(self._tools.keys())[:10]
            raise ValueError(f"Tool '{name}' nicht gefunden. Verfuegbar: {available}...")
        return self._tools[name]

    def get_tools_by_capability(self, capability: str) -> List[ToolMetadata]:
        tool_names = self._capability_index.get(capability, [])
        return [self._tools[name] for name in tool_names if name in self._tools]

    def get_tools_by_category(self, category: ToolCategory) -> List[ToolMetadata]:
        tool_names = self._category_index.get(category.value, [])
        return [self._tools[name] for name in tool_names if name in self._tools]

    def get_tools_for_agent(self, agent_capabilities: List[str]) -> List[ToolMetadata]:
        result = set()
        for cap in agent_capabilities:
            tool_names = self._capability_index.get(cap, [])
            result.update(tool_names)
        return [self._tools[name] for name in result if name in self._tools]

    def get_openai_tools_schema(self, tool_names: List[str] = None) -> List[Dict]:
        if tool_names:
            tools = [self._tools[n] for n in tool_names if n in self._tools]
        else:
            tools = list(self._tools.values())
        return [t.to_openai_schema() for t in tools]

    def get_anthropic_tools_schema(self, tool_names: List[str] = None) -> List[Dict]:
        if tool_names:
            tools = [self._tools[n] for n in tool_names if n in self._tools]
        else:
            tools = list(self._tools.values())
        return [t.to_anthropic_schema() for t in tools]

    def get_tool_manifest(self, tool_names: List[str] = None) -> str:
        if tool_names:
            tools = [self._tools[n] for n in tool_names if n in self._tools]
        else:
            tools = list(self._tools.values())

        if not tools:
            return "Keine Tools verfuegbar."

        manifest_lines = ["## Verfuegbare Tools:\n"]
        for t in sorted(tools, key=lambda x: x.name):
            manifest_lines.append(t.to_manifest_entry())
            if t.examples:
                manifest_lines.append(f"  Beispiel: {t.examples[0]}")
            manifest_lines.append("")

        return "\n".join(manifest_lines)

    async def execute(self, name: str, **kwargs) -> Any:
        metadata = self.get_tool(name)

        for param in metadata.parameters:
            if param.required and param.name not in kwargs:
                raise ValueError(f"Pflichtparameter '{param.name}' fehlt fuer Tool '{name}'")

        log.debug(f"Fuehre Tool aus: {name}({list(kwargs.keys())})")

        if metadata.is_async:
            result = await metadata.function(**kwargs)
        else:
            result = await asyncio.to_thread(metadata.function, **kwargs)

        return result

    def list_all_tools(self) -> Dict[str, Dict]:
        return {
            name: {
                "description": meta.description,
                "category": meta.category.value,
                "capabilities": meta.capabilities,
                "is_async": meta.is_async
            }
            for name, meta in self._tools.items()
        }

    def clear(self):
        # Auch aus global_methods entfernen
        for name in list(self._tools.keys()):
            if name in global_methods:
                del global_methods[name]
        self._tools.clear()
        self._capability_index.clear()
        self._category_index.clear()
        log.info("Tool-Registry geleert")


# Singleton Instanz
registry_v2 = ToolRegistryV2()


# Convenience Decorator
def tool(
    name: str,
    description: str,
    parameters: List[ToolParameter],
    capabilities: List[str],
    category: ToolCategory,
    examples: List[str] = None,
    returns: str = "dict",
    jsonrpc_name: str = None
):
    """
    Decorator fuer Tool-Registrierung mit V2 Metadata + JSON-RPC Bridge.

    Usage:
        @tool(
            name="search_web",
            description="Sucht im Web",
            parameters=[P("query", "string", "Suchbegriff")],
            capabilities=["search"],
            category=C.SEARCH
        )
        async def search_web(query: str) -> dict:
            return {"results": [...]}
    """
    return registry_v2.register(
        name=name,
        description=description,
        parameters=parameters,
        capabilities=capabilities,
        category=category,
        examples=examples,
        returns=returns,
        jsonrpc_name=jsonrpc_name
    )


# Kurzformen
P = ToolParameter
C = ToolCategory

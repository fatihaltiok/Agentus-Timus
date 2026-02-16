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
import re
from typing import Dict, Callable, Any, List, Optional, TypedDict, get_type_hints, Union
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

# JSON-RPC Bridge Imports
from jsonrpcserver import Success, Error
from jsonrpcserver.methods import global_methods
from oslash.either import Right, Left

log = logging.getLogger("ToolRegistryV2")


class ValidationError(Exception):
    """Fehler bei der Parameter-Validierung."""

    pass


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


TYPE_VALIDATORS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
    "any": lambda v: True,
}


def validate_parameter_value(param: "ToolParameter", value: Any) -> Any:
    """
    Validiert einen einzelnen Parameter-Wert gegen seine Spezifikation.

    Args:
        param: ToolParameter mit Name, Typ, etc.
        value: Der zu pruefende Wert

    Returns:
        Der validierte (und ggf. konvertierte) Wert

    Raises:
        ValidationError: Wenn die Validierung fehlschlaegt
    """
    if value is None:
        if param.required and param.default is None:
            raise ValidationError(f"Pflichtparameter '{param.name}' fehlt")
        return param.default if param.default is not None else None

    type_name = param.type.lower()
    validator = TYPE_VALIDATORS.get(type_name)

    if not validator:
        log.warning(
            f"Unbekannter Typ '{param.type}' fuer Parameter '{param.name}' - akzeptiere jeden Wert"
        )
        return value

    if not validator(value):
        type_names = {
            "string": "Text/Zeichenkette",
            "number": "Zahl",
            "integer": "Ganzzahl",
            "boolean": "Wahrheitswert (true/false)",
            "array": "Liste/Array",
            "object": "Objekt/Dictionary",
        }
        raise ValidationError(
            f"Parameter '{param.name}' hat falschen Typ: erwartet {type_names.get(type_name, type_name)}, "
            f"erhalten {type(value).__name__}"
        )

    if param.enum and value not in param.enum:
        raise ValidationError(
            f"Parameter '{param.name}' hat ungueltigen Wert '{value}'. "
            f"Erlaubte Werte: {param.enum}"
        )

    if type_name == "string" and isinstance(value, str):
        if len(value) > 10000:
            log.warning(
                f"Parameter '{param.name}' ist sehr lang ({len(value)} chars) - potenzieller Kontext-Overflow"
            )

    return value


def validate_tool_parameters(
    tool_name: str, parameters: List["ToolParameter"], kwargs: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validiert alle Parameter fuer einen Tool-Aufruf.

    Args:
        tool_name: Name des Tools (fuer Fehlermeldungen)
        parameters: Liste der ToolParameter-Spezifikationen
        kwargs: Die uebergebenen Parameter

    Returns:
        Validierte und vervollstaendigte Parameter

    Raises:
        ValidationError: Wenn die Validierung fehlschlaegt
    """
    validated = {}
    errors = []

    for param in parameters:
        value = kwargs.get(param.name)

        if value is None and param.default is not None:
            validated[param.name] = param.default
            continue

        try:
            validated[param.name] = validate_parameter_value(param, value)
        except ValidationError as e:
            errors.append(str(e))

    for key in kwargs:
        if key not in [p.name for p in parameters]:
            log.debug(f"Tool '{tool_name}': Unbekannter Parameter '{key}' ignoriert")

    if errors:
        raise ValidationError(
            f"Validierungsfehler fuer Tool '{tool_name}':\n" + "\n".join(errors)
        )

    return validated


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
    parallel_allowed: bool = False
    timeout: Optional[float] = None
    priority: int = 0

    def to_openai_schema(self) -> Dict[str, Any]:
        properties = {}
        required = []

        for param in self.parameters:
            prop = {"type": param.type, "description": param.description}
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
                    "required": required,
                },
            },
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
                "required": [p.name for p in self.parameters if p.required],
            },
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
        jsonrpc_name: str = None,
        parallel_allowed: bool = False,
        timeout: Optional[float] = None,
        priority: int = 0,
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
            parallel_allowed: Ob Tool parallel zu anderen ausgefuehrt werden darf
            timeout: Optionaler Timeout in Sekunden
            priority: Prioritaet fuer Queue (hoeher = wichtiger)
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
                is_async=is_async,
                parallel_allowed=parallel_allowed,
                timeout=timeout,
                priority=priority,
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

            # 2. JSON-RPC Bridge: Wrapper der Ergebnisse in Success() konvertiert
            #    Unterstuetzt dict, list, str, int, None etc. — nicht nur dict!
            if is_async:

                @wraps(fn)
                async def jsonrpc_wrapper(*args, **kwargs):
                    try:
                        result = await fn(*args, **kwargs)
                        # Bereits ein Success/Error (Right/Left) Objekt
                        if isinstance(result, (Right, Left)):
                            return result
                        return Success(result)
                    except Exception as e:
                        log.error(f"Tool {name} error: {e}")
                        return Error(code=-32000, message=str(e))
            else:

                @wraps(fn)
                def jsonrpc_wrapper(*args, **kwargs):
                    try:
                        result = fn(*args, **kwargs)
                        if isinstance(result, (Right, Left)):
                            return result
                        return Success(result)
                    except Exception as e:
                        log.error(f"Tool {name} error: {e}")
                        return Error(code=-32000, message=str(e))

            # In jsonrpcserver registrieren
            global_methods[rpc_name] = jsonrpc_wrapper

            fn_type = "async" if is_async else "sync"
            rpc_info = f" (RPC: {rpc_name})" if rpc_name != name else ""
            log.info(
                f"Tool registriert: {name} ({fn_type}) [{category.value}]{rpc_info}"
            )

            # Original-Funktion zurueckgeben (V2 execute() bekommt plain dicts)
            return fn

        return decorator

    def get_tool(self, name: str) -> ToolMetadata:
        if name not in self._tools:
            available = list(self._tools.keys())[:10]
            raise ValueError(
                f"Tool '{name}' nicht gefunden. Verfuegbar: {available}..."
            )
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

    async def execute(self, name: str, validate: bool = True, **kwargs) -> Any:
        """
        Fuehrt ein Tool aus mit vollstaendiger Parameter-Validierung.

        Args:
            name: Name des Tools
            validate: Ob Parameter validiert werden sollen (default: True)
            **kwargs: Parameter fuer das Tool

        Returns:
            Ergebnis des Tool-Aufrufs

        Raises:
            ValueError: Wenn das Tool nicht existiert
            ValidationError: Wenn die Parameter-Validierung fehlschlaegt
        """
        metadata = self.get_tool(name)

        if validate:
            try:
                validated_kwargs = validate_tool_parameters(
                    name, metadata.parameters, kwargs
                )
            except ValidationError as e:
                log.error(f"Validierungsfehler fuer Tool '{name}': {e}")
                raise
        else:
            for param in metadata.parameters:
                if param.required and param.name not in kwargs:
                    raise ValueError(
                        f"Pflichtparameter '{param.name}' fehlt fuer Tool '{name}'"
                    )
            validated_kwargs = kwargs

        log.debug(f"Fuehre Tool aus: {name}({list(validated_kwargs.keys())})")

        if metadata.is_async:
            result = await metadata.function(**validated_kwargs)
        else:
            result = await asyncio.to_thread(metadata.function, **validated_kwargs)

        return result

    def validate_tool_call(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        Validiert einen Tool-Aufruf ohne ihn auszufuehren.

        Nuetzlich fuer Pre-Flight-Checks und Policy-Gates.

        Args:
            name: Name des Tools
            **kwargs: Parameter fuer das Tool

        Returns:
            Validierte Parameter

        Raises:
            ValueError: Wenn das Tool nicht existiert
            ValidationError: Wenn die Validierung fehlschlaegt
        """
        metadata = self.get_tool(name)
        return validate_tool_parameters(name, metadata.parameters, kwargs)

    def list_all_tools(self) -> Dict[str, Dict]:
        return {
            name: {
                "description": meta.description,
                "category": meta.category.value,
                "capabilities": meta.capabilities,
                "is_async": meta.is_async,
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
    jsonrpc_name: str = None,
    parallel_allowed: bool = False,
    timeout: Optional[float] = None,
    priority: int = 0,
):
    """
    Decorator fuer Tool-Registrierung mit V2 Metadata + JSON-RPC Bridge.

    Usage:
        @tool(
            name="search_web",
            description="Sucht im Web",
            parameters=[P("query", "string", "Suchbegriff")],
            capabilities=["search"],
            category=C.SEARCH,
            parallel_allowed=True,  # Erlaubt parallele Ausfuehrung
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
        jsonrpc_name=jsonrpc_name,
        parallel_allowed=parallel_allowed,
        timeout=timeout,
        priority=priority,
    )


def _python_type_to_json_type(annotation) -> str:
    """Konvertiert Python Type-Hints zu JSON-Schema Typen."""
    if annotation is None or annotation is inspect.Parameter.empty:
        return "string"

    # String-Annotationen aufloesen
    if isinstance(annotation, str):
        annotation_str = annotation.lower()
    else:
        annotation_str = getattr(annotation, "__name__", str(annotation)).lower()

    type_map = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "dict": "object",
        "none": "string",
        "nonetype": "string",
    }

    for key, val in type_map.items():
        if key in annotation_str:
            return val

    return "string"


def auto_generate_tool_schema(
    fn: Callable = None,
    name: str = None,
    description: str = None,
    category: ToolCategory = ToolCategory.SYSTEM,
    capabilities: List[str] = None,
    **kwargs,
) -> Callable:
    """
    Decorator der automatisch ToolParameter aus Python Type-Hints ableitet.

    Introspiziert die Funktionssignatur und generiert:
    - Parameter-Namen, Typen und Defaults aus der Signatur
    - Beschreibungen aus dem Docstring (Google-Style oder einfach)
    - Registriert das Tool automatisch in der Registry

    Usage:
        @auto_generate_tool_schema
        async def search_web(query: str, max_results: int = 10) -> dict:
            '''Sucht im Web nach Ergebnissen.

            Args:
                query: Der Suchbegriff
                max_results: Maximale Anzahl Ergebnisse
            '''
            return {"results": [...]}
    """
    def _decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        tool_desc = description or (fn.__doc__ or "").split("\n")[0].strip() or tool_name
        tool_caps = capabilities or []
        tool_cat = category

        # Signatur analysieren
        sig = inspect.signature(fn)
        hints = get_type_hints(fn) if hasattr(fn, "__annotations__") else {}

        # Docstring-Parameter extrahieren (Google-Style Args:)
        param_docs = _parse_docstring_params(fn.__doc__ or "")

        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            # Typ ableiten
            annotation = hints.get(param_name, param.annotation)
            json_type = _python_type_to_json_type(annotation)

            # Default und Required
            has_default = param.default is not inspect.Parameter.empty
            default_val = param.default if has_default else None
            is_required = not has_default

            # Beschreibung aus Docstring
            param_desc = param_docs.get(param_name, f"Parameter {param_name}")

            parameters.append(ToolParameter(
                name=param_name,
                type=json_type,
                description=param_desc,
                required=is_required,
                default=default_val,
            ))

        # Tool registrieren
        return registry_v2.register(
            name=tool_name,
            description=tool_desc,
            parameters=parameters,
            capabilities=tool_caps,
            category=tool_cat,
            **kwargs,
        )(fn)

    # Unterstuetzt sowohl @auto_generate_tool_schema als auch
    # @auto_generate_tool_schema(name="...", ...)
    if callable(fn):
        return _decorator(fn)
    return _decorator


def _parse_docstring_params(docstring: str) -> Dict[str, str]:
    """
    Extrahiert Parameter-Beschreibungen aus einem Docstring.

    Unterstuetzt Google-Style:
        Args:
            param_name: Beschreibung
            param_name: Beschreibung
    """
    params = {}
    if not docstring:
        return params

    in_args = False
    for line in docstring.split("\n"):
        stripped = line.strip()

        if stripped.lower().startswith("args:"):
            in_args = True
            continue
        elif stripped.lower().startswith(("returns:", "raises:", "example", "note")):
            in_args = False
            continue

        if in_args and ":" in stripped:
            key, _, desc = stripped.partition(":")
            key = key.strip()
            desc = desc.strip()
            if key and desc and not key.startswith("-"):
                params[key] = desc

    return params


# Kurzformen
P = ToolParameter
C = ToolCategory

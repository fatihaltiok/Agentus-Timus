# tools/universal_tool_caller.py (REPAIRED)

import inspect
import logging
from typing import Dict, Callable, Any

# HINWEIS: Es ist eine gute Praxis, einen spezifischen Logger zu verwenden, anstatt
# auf einen potenziell nicht initialisierten Logger in shared_context zu vertrauen.
logger = logging.getLogger("UniversalToolCaller")

class UniversalToolCaller:
    """
    Eine Singleton-Klasse, die als zentrale Registry für alle
    im System verfügbaren Tools dient.
    """
    _instance = None
    _TOOLS_REGISTRY: Dict[str, Callable[..., Any]] = {}

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(UniversalToolCaller, cls).__new__(cls)
        return cls._instance

    def register_tool(self, name: str, fn: Callable[..., Any]) -> None:
        """Registriert ein neues Tool in der zentralen Registry."""
        self._TOOLS_REGISTRY[name] = fn
        fn_type = 'async' if inspect.iscoroutinefunction(fn) else 'sync'
        logger.info(f"🔧 Tool registriert: {name} ({fn_type})")

    def get_tool(self, name: str) -> Callable[..., Any]:
        """Holt ein Tool anhand seines Namens aus der Registry."""
        fn = self._TOOLS_REGISTRY.get(name)
        if not fn:
            available = list(self._TOOLS_REGISTRY.keys())
            raise ValueError(f"Tool '{name}' nicht registriert! Verfügbare Tools: {available}")
        return fn

    def list_registered_tools(self) -> Dict[str, str]:
        """Gibt ein Dictionary aller registrierten Tools und ihres Typs zurück."""
        return {
            name: 'async' if inspect.iscoroutinefunction(fn) else 'sync'
            for name, fn in sorted(self._TOOLS_REGISTRY.items())
        }

    # HINZUGEFÜGT: DIES IST DIE ENTSCHEIDENDE ERGÄNZUNG
    def get_registry(self) -> Dict[str, Callable[..., Any]]:
        """
        Gibt eine Kopie der gesamten Tool-Registry zurück.
        Dies ist die Methode, die der main_dispatcher benötigt, um die Agenten
        mit allen verfügbaren Werkzeugen zu initialisieren.
        """
        return self._TOOLS_REGISTRY.copy()

    def get_formatted_tool_descriptions(self) -> str:
        """Gibt eine für LLM-Prompts formatierte Liste aller Tools zurück."""
        if not self._TOOLS_REGISTRY:
            return "Keine Werkzeuge verfügbar."
        descriptions = []
        for name, fn in sorted(self._TOOLS_REGISTRY.items()):
            docstring = inspect.getdoc(fn) or "Keine Beschreibung verfügbar."
            short_desc = docstring.split('\n')[0]
            descriptions.append(f"- `{name}`: {short_desc}")
        return "\n".join(descriptions)

    def clear_registry(self) -> None:
        """Leert die Tool-Registry (nützlich für Tests)."""
        self._TOOLS_REGISTRY.clear()
        logger.info("🧹 Tool-Registry geleert")

# --- Globale Singleton-Instanz ---
tool_caller_instance = UniversalToolCaller()

# --- Globale Helferfunktion für Abwärtskompatibilität ---
def register_tool(name: str, fn: Callable[..., Any]):
    """Globale Helferfunktion, die die Singleton-Instanz verwendet."""
    tool_caller_instance.register_tool(name, fn)

# Füge die fehlenden globalen Helferfunktionen hinzu.

def list_registered_tools() -> Dict[str, str]:
    """Globale Helferfunktion, die die Singleton-Instanz verwendet."""
    return tool_caller_instance.list_registered_tools()

def get_tool(name: str) -> Callable[..., Any]:
    """Globale Helferfunktion, die die Singleton-Instanz verwendet."""
    return tool_caller_instance.get_tool(name)
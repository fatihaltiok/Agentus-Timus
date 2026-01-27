# tools/memory_tool/__init__.py
"""
Timus Memory Tool v2.0

Ein vollständiges Memory-System mit:
- Session Memory (Kurzzeit-Kontext)
- ChromaDB (Langzeit, semantische Suche)
- SQLite (Strukturierte Fakten)
- Entitäts-Tracking
- Automatische Fakten-Extraktion
- MCP-Integration
"""

from .tool import (
    # Hauptklassen
    MemoryManager,
    SessionMemory,
    FactStore,
    
    # Globale Instanz
    memory_manager,
    
    # Helper Functions
    get_context,
    add_to_memory,
    quick_remember,
    quick_recall,
)

__all__ = [
    "MemoryManager",
    "SessionMemory", 
    "FactStore",
    "memory_manager",
    "get_context",
    "add_to_memory",
    "quick_remember",
    "quick_recall",
]

__version__ = "2.0.0"

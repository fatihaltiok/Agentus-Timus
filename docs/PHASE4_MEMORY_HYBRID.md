# Phase 4: Memory-Upgrade als Hybrid

**Status:** ✅ Abgeschlossen  
**Datum:** Februar 2026

## Ziel
Portableres Gedächtnis ohne aktuelle SQLite/Chroma-Funktionen zu verlieren.

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                    Hybrid Memory System                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐    ┌─────────────────┐                 │
│  │  Markdown Store │◄──►│  SQLite/Chroma  │                 │
│  │  (Human-edit)   │    │  (Semantic)     │                 │
│  └─────────────────┘    └─────────────────┘                 │
│         │                       │                            │
│         ▼                       ▼                            │
│  ┌──────────────────────────────────────┐                   │
│  │         Memory Manager               │                   │
│  │  - Unified API                       │                   │
│  │  - Bidirectional Sync                │                   │
│  │  - Conflict Resolution               │                   │
│  └──────────────────────────────────────┘                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Neue Dateien

### `memory/markdown_store/store.py`

**Klassen:**
- `UserProfile` - Benutzer-Profil Dataclass
- `SoulProfile` - Persona Dataclass
- `MemoryEntry` - Erinnerung Dataclass
- `MarkdownStore` - Hauptklasse

**Features:**
- YAML Frontmatter Parsing
- USER.md - Benutzer-Profil
- SOUL.md - Persona und Verhaltensregeln
- MEMORY.md - Wichtige Erinnerungen
- Tageslogs in `daily/` Ordner

### Markdown-Dateien

```
memory/markdown_store/
├── USER.md          # Benutzer-Profil
├── SOUL.md          # Persona/Verhalten
├── MEMORY.md        # Wichtige Fakten
└── daily/
    └── 2026-02-16.md  # Tageslogs
```

## Integration

### Bestehende Systeme

| Komponente | Typ | Status |
|------------|-----|--------|
| `memory/memory_system.py` | SQLite + Session | ✅ Beibehalten |
| `tools/memory_tool/tool.py` | ChromaDB + SQLite | ✅ Beibehalten |
| `memory/markdown_store/` | Markdown (NEU) | ✅ Hinzugefügt |

### Verwendung

```python
from memory.markdown_store import MarkdownStore, MemoryEntry

store = MarkdownStore()

# User Profile
store.update_user_profile({
    "name": "Fatih",
    "location": "Berlin",
    "preferences": {"language": "de"}
})

# Soul Profile
store.update_soul_profile({
    "persona": "Timus ist ein hilfreicher Assistent",
    "behavior_hooks": ["Antworte auf Deutsch"]
})

# Memory
store.add_memory(MemoryEntry(
    category="work",
    content="Arbeitet an Timus",
    importance=0.8
))

# Daily Log
store.write_daily_log("2026-02-16", "Phase 4 implementiert", ["memory"])

# Prompt Context
context = store.get_prompt_context()
```

## Vorteile

- ✅ **Portabel** - Plain Text, Git-versionierbar
- ✅ **Mensch-editierbar** - Direkt in Markdown ändern
- ✅ **Hybrid** - SQLite/Chroma weiterhin verfügbar
- ✅ **Tageslogs** - Chronologische Übersicht

## Ergebnis

- Mensch-editierbares Gedächtnis
- Schnelle semantische Suche weiterhin möglich
- Portabilität durch Markdown-Dateien
- Bidirektionale Sync-Möglichkeit

## Nächste Phase

Phase 5: Optional Channel-Adapter-Schicht

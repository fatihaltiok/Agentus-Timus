# Timus Memory Tool v2.0

## Übersicht

Ein vollständiges Memory-System für Timus mit:

| Komponente | Beschreibung |
|------------|--------------|
| **Session Memory** | Kurzzeit-Kontext (letzte 20 Nachrichten) |
| **ChromaDB** | Langzeit-Gedächtnis mit semantischer Suche |
| **SQLite (FactStore)** | Strukturierte Fakten über den Benutzer |
| **Entity Tracking** | Verfolgt "er", "sie", "das" → wer ist gemeint |
| **Fakten-Extraktion** | Erkennt automatisch "Ich heiße...", "Ich mag..." |
| **Zusammenfassung** | Fasst Sessions am Ende zusammen |

## Installation

```bash
# Ersetze das alte memory_tool
cp -r tools/memory_tool ~/dev/timus/tools/

# Stelle sicher, dass data/ existiert
mkdir -p ~/dev/timus/data
```

## MCP Tools (11 Funktionen)

| Tool | Beschreibung |
|------|--------------|
| `remember(text, source)` | Speichert im Langzeit-Gedächtnis (ChromaDB) |
| `recall(query, n_results)` | Semantische Suche im Gedächtnis |
| `remember_fact(key, value, category)` | Speichert strukturierten Fakt |
| `recall_fact(key)` | Ruft einen Fakt ab |
| `forget_fact(key)` | Löscht einen Fakt |
| `get_memory_context()` | Kompletter Kontext für Prompts |
| `get_known_facts()` | Alle bekannten Fakten |
| `add_interaction(user, assistant)` | Fügt Interaktion zum Session Memory |
| `end_session()` | Beendet Session, erstellt Zusammenfassung |
| `get_memory_stats()` | Memory-Statistiken |
| `resolve_reference(text)` | Löst Pronomen auf ("er" → "Macron") |

## Direkte Verwendung (Python)

```python
from tools.memory_tool import memory_manager, get_context, add_to_memory

# Interaktion hinzufügen
add_to_memory("Ich heiße Fatih", "Hallo Fatih!")

# Kontext für Prompt holen
context = get_context()
print(context)

# Fakt speichern
memory_manager.remember_fact("favorite_color", "blau")

# Fakt abrufen
color = memory_manager.recall_fact("favorite_color")

# Stats anzeigen
print(memory_manager.get_stats())
```

## Automatische Fakten-Extraktion

Das Tool erkennt automatisch Muster wie:

- "Ich heiße Max" → `name/user_name = Max`
- "Ich bin 30 Jahre alt" → `info/age = 30`
- "Ich wohne in Berlin" → `info/location = Berlin`
- "Ich arbeite als Entwickler" → `info/work = Entwickler`
- "Ich mag Kaffee" → `preference/likes = Kaffee`

## Entitäts-Tracking

```
User: Wer ist Emmanuel Macron?
Timus: Emmanuel Macron ist der Präsident von Frankreich.

User: Wie alt ist er?
       ↓
       Memory erkennt: "er" → "Emmanuel Macron"
       
Timus: Emmanuel Macron ist 47 Jahre alt.
```

## Datenbank-Speicherort

```
~/dev/timus/data/timus_memory.db
```

## Abhängigkeiten

- `chromadb` (optional, für semantische Suche)
- `openai` (optional, für Zusammenfassungen)
- `sqlite3` (built-in)
- `jsonrpcserver` (für MCP)

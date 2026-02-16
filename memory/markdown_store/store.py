# memory/markdown_store/store.py
"""
Markdown Store - Mensch-editierbares Gedächtnis fuer Timus.

FEATURES:
- USER.md - Benutzer-Profil und Praferenzen
- SOUL.md - Persona und Verhaltensweisen
- MEMORY.md - Wichtige Fakten und Ereignisse
- Tageslogs - Taegliche Zusammenfassungen

VORTEILE:
- Portabel (Plain Text)
- Mensch-editierbar
- Versionierbar (Git)
- Sync mit SQLite/Chroma

USAGE:
    from memory.markdown_store import MarkdownStore

    store = MarkdownStore()

    # USER.md lesen/schreiben
    user = store.read_user_profile()
    store.update_user_profile({"name": "Fatih", "location": "Berlin"})

    # Tageslog schreiben
    store.write_daily_log("2026-02-16", "Heute an Memory-System gearbeitet.")

AUTOR: Timus Development
DATUM: Februar 2026
"""

import os
import logging
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import json
import re

log = logging.getLogger("MarkdownStore")


@dataclass
class UserProfile:
    name: str = ""
    location: str = ""
    languages: List[str] = field(default_factory=list)
    preferences: Dict[str, str] = field(default_factory=dict)
    goals: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    updated_at: str = ""


@dataclass
class SoulProfile:
    persona: str = ""
    traits: List[str] = field(default_factory=list)
    communication_style: str = ""
    behavior_hooks: List[str] = field(default_factory=list)
    updated_at: str = ""


@dataclass
class MemoryEntry:
    category: str
    content: str
    importance: float = 0.5
    created_at: str = ""
    source: str = ""


class MarkdownStore:
    """
    Markdown-basierter Store fuer mensch-editierbares Gedächtnis.
    """

    def __init__(self, base_path: Path = None):
        self.base_path = (
            base_path or Path.home() / "dev" / "timus" / "memory" / "markdown_store"
        )
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.user_path = self.base_path / "USER.md"
        self.soul_path = self.base_path / "SOUL.md"
        self.memory_path = self.base_path / "MEMORY.md"
        self.daily_logs_path = self.base_path / "daily"
        self.daily_logs_path.mkdir(parents=True, exist_ok=True)

        self._ensure_files_exist()

    def _ensure_files_exist(self):
        """Stellt sicher, dass alle Basis-Dateien existieren."""
        if not self.user_path.exists():
            self._write_user_profile(UserProfile())

        if not self.soul_path.exists():
            self._write_soul_profile(SoulProfile())

        if not self.memory_path.exists():
            self._write_memory_file([])

    def _parse_frontmatter(self, content: str) -> tuple:
        """Extrahiert YAML Frontmatter aus Markdown."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                body = parts[2].strip()
                return frontmatter, body
        return "", content

    def _parse_yaml_simple(self, text: str) -> Dict[str, Any]:
        """Einfacher YAML-Parser fuer Frontmatter."""
        result = {}
        current_key = None
        current_list = []
        in_list = False
        in_dict = False
        current_dict = {}

        for line in text.split("\n"):
            line = line.rstrip()
            if not line:
                continue

            if line.startswith("  - "):
                if current_key and in_list:
                    current_list.append(line[4:].strip())
                continue

            if line.startswith("  ") and ":" in line and in_dict:
                nested_key, _, nested_value = line.strip().partition(":")
                if nested_value.strip():
                    current_dict[nested_key.strip()] = nested_value.strip().strip("\"'")
                continue

            if ":" in line:
                if in_list and current_key:
                    result[current_key] = current_list
                    current_list = []
                    in_list = False
                if in_dict and current_key:
                    result[current_key] = current_dict
                    current_dict = {}
                    in_dict = False

                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()

                if value.startswith("[") and value.endswith("]"):
                    items = value[1:-1].split(",")
                    result[key] = [i.strip().strip("\"'") for i in items if i.strip()]
                elif value.startswith("{") and value.endswith("}"):
                    result[key] = {}
                elif value == "":
                    current_key = key
                    in_list = False
                    in_dict = True
                    current_dict = {}
                else:
                    value = value.strip("\"'")
                    if value.isdigit():
                        value = int(value)
                    elif value.replace(".", "").isdigit():
                        value = float(value)
                    result[key] = value
                    current_key = key
                    in_list = True
                    in_dict = False
                    current_list = []

        if in_list and current_key:
            result[current_key] = current_list
        if in_dict and current_key:
            result[current_key] = current_dict

        return result

    def _dict_to_yaml(self, data: Dict[str, Any]) -> str:
        """Konvertiert Dict zu einfachem YAML."""
        lines = []

        for key, value in data.items():
            if isinstance(value, list):
                if not value:
                    lines.append(f"{key}: []")
                else:
                    lines.append(f"{key}:")
                    for item in value:
                        lines.append(f"  - {item}")
            elif isinstance(value, dict):
                if not value:
                    lines.append(f"{key}: {{}}")
                else:
                    lines.append(f"{key}:")
                    for k, v in value.items():
                        lines.append(f"  {k}: {v}")
            else:
                lines.append(f"{key}: {value}")

        return "\n".join(lines)

    # === USER PROFILE ===

    def read_user_profile(self) -> UserProfile:
        """Liest das Benutzer-Profil aus USER.md."""
        if not self.user_path.exists():
            return UserProfile()

        try:
            content = self.user_path.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)
            data = self._parse_yaml_simple(frontmatter)

            return UserProfile(
                name=data.get("name", ""),
                location=data.get("location", ""),
                languages=data.get("languages", []),
                preferences=data.get("preferences", {}),
                goals=data.get("goals", []),
                constraints=data.get("constraints", []),
                updated_at=data.get("updated_at", ""),
            )
        except Exception as e:
            log.error(f"Fehler beim Lesen von USER.md: {e}")
            return UserProfile()

    def update_user_profile(self, updates: Dict[str, Any]) -> bool:
        """Aktualisiert das Benutzer-Profil."""
        try:
            current = self.read_user_profile()

            for key, value in updates.items():
                if hasattr(current, key):
                    setattr(current, key, value)

            current.updated_at = datetime.now().isoformat()
            self._write_user_profile(current)

            log.info(f"USER.md aktualisiert: {list(updates.keys())}")
            return True
        except Exception as e:
            log.error(f"Fehler beim Aktualisieren von USER.md: {e}")
            return False

    def _write_user_profile(self, profile: UserProfile):
        """Schreibt das Benutzer-Profil in USER.md."""
        frontmatter = self._dict_to_yaml(
            {
                "name": profile.name,
                "location": profile.location,
                "languages": profile.languages,
                "preferences": profile.preferences,
                "goals": profile.goals,
                "constraints": profile.constraints,
                "updated_at": profile.updated_at or datetime.now().isoformat(),
            }
        )

        content = f"""---
{frontmatter}
---

# Benutzer-Profil

Diese Datei enthält Informationen über den Benutzer.
Sie kann manuell editiert werden und wird automatisch mit Timus synchronisiert.

## Name
{profile.name or "Nicht gesetzt"}

## Standort
{profile.location or "Nicht gesetzt"}

## Sprachen
{chr(10).join(f"- {lang}" for lang in profile.languages) if profile.languages else "Nicht gesetzt"}

## Präferenzen
{chr(10).join(f"- {k}: {v}" for k, v in profile.preferences.items()) if profile.preferences else "Keine Präferenzen"}

## Ziele
{chr(10).join(f"- {goal}" for goal in profile.goals) if profile.goals else "Keine Ziele"}

## Constraints
{chr(10).join(f"- {c}" for c in profile.constraints) if profile.constraints else "Keine Constraints"}

---
*Zuletzt aktualisiert: {profile.updated_at or datetime.now().isoformat()}*
"""

        self.user_path.write_text(content, encoding="utf-8")

    # === SOUL PROFILE ===

    def read_soul_profile(self) -> SoulProfile:
        """Liest die Persona aus SOUL.md."""
        if not self.soul_path.exists():
            return SoulProfile()

        try:
            content = self.soul_path.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)
            data = self._parse_yaml_simple(frontmatter)

            return SoulProfile(
                persona=data.get("persona", ""),
                traits=data.get("traits", []),
                communication_style=data.get("communication_style", ""),
                behavior_hooks=data.get("behavior_hooks", []),
                updated_at=data.get("updated_at", ""),
            )
        except Exception as e:
            log.error(f"Fehler beim Lesen von SOUL.md: {e}")
            return SoulProfile()

    def update_soul_profile(self, updates: Dict[str, Any]) -> bool:
        """Aktualisiert die Persona."""
        try:
            current = self.read_soul_profile()

            for key, value in updates.items():
                if hasattr(current, key):
                    setattr(current, key, value)

            current.updated_at = datetime.now().isoformat()
            self._write_soul_profile(current)

            log.info(f"SOUL.md aktualisiert: {list(updates.keys())}")
            return True
        except Exception as e:
            log.error(f"Fehler beim Aktualisieren von SOUL.md: {e}")
            return False

    def _write_soul_profile(self, profile: SoulProfile):
        """Schreibt die Persona in SOUL.md."""
        frontmatter = self._dict_to_yaml(
            {
                "persona": profile.persona,
                "traits": profile.traits,
                "communication_style": profile.communication_style,
                "behavior_hooks": profile.behavior_hooks,
                "updated_at": profile.updated_at or datetime.now().isoformat(),
            }
        )

        content = f"""---
{frontmatter}
---

# Timus Persona

Diese Datei definiert das Verhalten und die Persönlichkeit von Timus.
Sie kann manuell editiert werden.

## Persona
{profile.persona or "Timus ist ein hilfreicher KI-Assistent."}

## Traits
{chr(10).join(f"- {trait}" for trait in profile.traits) if profile.traits else "Keine definiert"}

## Kommunikationsstil
{profile.communication_style or "Freundlich, präzise, hilfsbereit."}

## Behavior Hooks
Regeln, die das Verhalten steuern:

{chr(10).join(f"- {hook}" for hook in profile.behavior_hooks) if profile.behavior_hooks else "Keine definiert"}

---
*Zuletzt aktualisiert: {profile.updated_at or datetime.now().isoformat()}*
"""

        self.soul_path.write_text(content, encoding="utf-8")

    # === MEMORY ===

    def read_memories(self) -> List[MemoryEntry]:
        """Liest wichtige Erinnerungen aus MEMORY.md."""
        if not self.memory_path.exists():
            return []

        try:
            content = self.memory_path.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)
            data = self._parse_yaml_simple(frontmatter)

            memories = []
            entries = data.get("entries", [])

            for entry in entries:
                if isinstance(entry, dict):
                    memories.append(
                        MemoryEntry(
                            category=entry.get("category", "general"),
                            content=entry.get("content", ""),
                            importance=entry.get("importance", 0.5),
                            created_at=entry.get("created_at", ""),
                            source=entry.get("source", ""),
                        )
                    )

            return memories
        except Exception as e:
            log.error(f"Fehler beim Lesen von MEMORY.md: {e}")
            return []

    def add_memory(self, entry: MemoryEntry) -> bool:
        """Fügt eine neue Erinnerung hinzu."""
        try:
            memories = self.read_memories()

            entry.created_at = entry.created_at or datetime.now().isoformat()
            memories.append(entry)

            self._write_memory_file(memories)
            log.info(f"MEMORY.md: Neue Erinnerung hinzugefügt ({entry.category})")
            return True
        except Exception as e:
            log.error(f"Fehler beim Hinzufügen zu MEMORY.md: {e}")
            return False

    def _write_memory_file(self, memories: List[MemoryEntry]):
        """Schreibt Erinnerungen in MEMORY.md."""
        entries_data = [
            {
                "category": m.category,
                "content": m.content,
                "importance": m.importance,
                "created_at": m.created_at,
                "source": m.source,
            }
            for m in memories
        ]

        frontmatter = self._dict_to_yaml(
            {
                "entries": entries_data,
                "count": len(memories),
                "updated_at": datetime.now().isoformat(),
            }
        )

        body_sections = []
        categories = {}
        for m in memories:
            if m.category not in categories:
                categories[m.category] = []
            categories[m.category].append(m)

        for cat, entries in categories.items():
            section = f"## {cat.upper()}\n\n"
            for e in entries:
                section += f"- [{e.importance:.1f}] {e.content}\n"
            body_sections.append(section)

        content = f"""---
{frontmatter}
---

# Wichtige Erinnerungen

Diese Datei enthält wichtige Fakten und Ereignisse.
Sie kann manuell editiert werden.

{chr(10).join(body_sections) if body_sections else "Noch keine Erinnerungen."}

---
*Einträge: {len(memories)} | Zuletzt aktualisiert: {datetime.now().isoformat()}*
"""

        self.memory_path.write_text(content, encoding="utf-8")

    # === DAILY LOGS ===

    def write_daily_log(
        self, log_date: str, content: str, topics: List[str] = None
    ) -> bool:
        """Schreibt ein Tageslog."""
        try:
            log_path = self.daily_logs_path / f"{log_date}.md"

            existing = ""
            if log_path.exists():
                existing = log_path.read_text(encoding="utf-8")

            topics_str = ", ".join(topics) if topics else ""

            log_content = f"""# Tageslog - {log_date}

**Erstellt:** {datetime.now().isoformat()}
**Themen:** {topics_str}

## Zusammenfassung

{content}

---
*Automatisch von Timus erstellt*
"""

            log_path.write_text(log_content, encoding="utf-8")
            log.info(f"Tageslog geschrieben: {log_date}")
            return True
        except Exception as e:
            log.error(f"Fehler beim Schreiben des Tageslogs: {e}")
            return False

    def read_daily_log(self, log_date: str) -> Optional[str]:
        """Liest ein Tageslog."""
        log_path = self.daily_logs_path / f"{log_date}.md"

        if log_path.exists():
            return log_path.read_text(encoding="utf-8")
        return None

    def list_daily_logs(self, limit: int = 7) -> List[str]:
        """Listet verfügbare Tageslogs auf."""
        logs = sorted(self.daily_logs_path.glob("*.md"), reverse=True)
        return [l.stem for l in logs[:limit]]

    # === SYNC HELPERS ===

    def get_all_content(self) -> Dict[str, Any]:
        """Gibt alle Markdown-Inhalte zurück (für Sync)."""
        return {
            "user": asdict(self.read_user_profile()),
            "soul": asdict(self.read_soul_profile()),
            "memories": [asdict(m) for m in self.read_memories()],
            "daily_logs": self.list_daily_logs(),
        }

    def get_prompt_context(self) -> str:
        """Baut einen Prompt-Kontext aus den Markdown-Dateien."""
        parts = []

        user = self.read_user_profile()
        if user.name:
            parts.append(f"BENUTZER: {user.name}")
        if user.location:
            parts.append(f"STANDORT: {user.location}")
        if user.preferences:
            if isinstance(user.preferences, dict):
                pref_str = ", ".join(f"{k}={v}" for k, v in user.preferences.items())
            else:
                pref_str = str(user.preferences)
            parts.append(f"PRAEFERENZEN: {pref_str}")
        if user.goals:
            parts.append(f"ZIELE: {', '.join(user.goals)}")

        soul = self.read_soul_profile()
        if soul.behavior_hooks:
            parts.append(
                "VERHALTENSREGELN:\n" + "\n".join(f"- {h}" for h in soul.behavior_hooks)
            )

        memories = self.read_memories()
        important = [m for m in memories if m.importance >= 0.7]
        if important:
            parts.append(
                "WICHTIGE ERINNERUNGEN:\n"
                + "\n".join(f"- {m.content}" for m in important[:5])
            )

        return "\n\n".join(parts) if parts else ""


@dataclass
class SearchResult:
    """Ein Suchergebnis aus der Hybrid-Suche."""
    source: str  # "user", "soul", "memory", "daily_log"
    content: str
    rank: float = 0.0
    snippet: str = ""


class HybridSearchIndex:
    """
    SQLite FTS5-basierter Suchindex fuer Markdown-Inhalte.

    Synchronisiert Markdown-Dateien (USER.md, SOUL.md, MEMORY.md, Daily Logs)
    in eine FTS5-Tabelle fuer schnelle Volltextsuche.

    Inspiriert von OpenClaws hybridem Ansatz:
    - FTS5 fuer deterministische Keyword-Suche (exakte Begriffe, Variablen)
    - Markdown als Source-of-Truth, FTS5 als Suchindex
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Erstellt die FTS5-Tabelle falls nicht vorhanden."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS markdown_fts USING fts5(
                    source,
                    title,
                    content,
                    updated_at UNINDEXED,
                    tokenize='unicode61'
                );

                CREATE TABLE IF NOT EXISTS sync_state (
                    source TEXT PRIMARY KEY,
                    file_hash TEXT,
                    synced_at TIMESTAMP
                );
            """)

    def _file_hash(self, content: str) -> str:
        """Einfacher Hash fuer Change-Detection."""
        import hashlib
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _needs_sync(self, source: str, content: str) -> bool:
        """Prueft ob eine Quelle neu synchronisiert werden muss."""
        current_hash = self._file_hash(content)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT file_hash FROM sync_state WHERE source = ?",
                (source,)
            ).fetchone()
            if not row:
                return True
            return row[0] != current_hash

    def _update_sync_state(self, source: str, content: str):
        """Aktualisiert den Sync-State fuer eine Quelle."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO sync_state (source, file_hash, synced_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(source) DO UPDATE SET
                     file_hash = excluded.file_hash,
                     synced_at = excluded.synced_at""",
                (source, self._file_hash(content), datetime.now().isoformat())
            )

    def index_document(self, source: str, title: str, content: str):
        """Indexiert ein einzelnes Dokument in FTS5."""
        if not content.strip():
            return

        if not self._needs_sync(source, content):
            return

        current_hash = self._file_hash(content)
        with sqlite3.connect(self.db_path) as conn:
            # Altes Dokument entfernen
            conn.execute(
                "DELETE FROM markdown_fts WHERE source = ? OR source LIKE ?",
                (source, f"{source}#%")
            )

            # Text in Chunks aufteilen (max ~500 Zeichen pro Chunk)
            chunks = self._chunk_text(content)
            for i, chunk in enumerate(chunks):
                chunk_source = f"{source}#{i}" if len(chunks) > 1 else source
                conn.execute(
                    "INSERT INTO markdown_fts (source, title, content, updated_at) VALUES (?, ?, ?, ?)",
                    (chunk_source, title, chunk, datetime.now().isoformat())
                )

            # Sync-State in gleicher Connection aktualisieren
            conn.execute(
                """INSERT INTO sync_state (source, file_hash, synced_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(source) DO UPDATE SET
                     file_hash = excluded.file_hash,
                     synced_at = excluded.synced_at""",
                (source, current_hash, datetime.now().isoformat())
            )
            conn.commit()
            log.debug(f"FTS5: {source} indexiert ({len(chunks)} Chunks)")

    def _chunk_text(self, text: str, max_chars: int = 500) -> List[str]:
        """Teilt Text in semantische Chunks auf."""
        # Zuerst nach Abschnitten (## Headers) teilen
        sections = re.split(r'\n(?=##?\s)', text)
        chunks = []

        for section in sections:
            if len(section) <= max_chars:
                if section.strip():
                    chunks.append(section.strip())
            else:
                # Lange Abschnitte nach Absaetzen teilen
                paragraphs = section.split("\n\n")
                current_chunk = ""
                for para in paragraphs:
                    if len(current_chunk) + len(para) > max_chars and current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = para
                    else:
                        current_chunk += "\n\n" + para if current_chunk else para
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())

        return chunks if chunks else [text[:max_chars]]

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """
        Durchsucht den FTS5-Index.

        Nutzt FTS5 MATCH fuer Volltextsuche mit Ranking (bm25).
        """
        if not query or not query.strip():
            return []

        results = []
        # FTS5-Query: Woerter mit * fuer Prefix-Match
        fts_query = " OR ".join(
            f'"{w}"*' for w in query.strip().split() if w
        )

        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """SELECT source, title, snippet(markdown_fts, 2, '>>>', '<<<', '...', 40),
                              rank
                       FROM markdown_fts
                       WHERE markdown_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (fts_query, limit)
                ).fetchall()

                for row in rows:
                    # source kann "memory#2" sein - Basis extrahieren
                    base_source = row[0].split("#")[0]
                    results.append(SearchResult(
                        source=base_source,
                        content=row[1],
                        rank=abs(row[3]) if row[3] else 0.0,
                        snippet=row[2]
                    ))
        except Exception as e:
            log.error(f"FTS5-Suche fehlgeschlagen: {e}")

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken ueber den Index zurueck."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM markdown_fts"
            ).fetchone()[0]
            sources = conn.execute(
                "SELECT DISTINCT source FROM markdown_fts"
            ).fetchall()

        return {
            "total_chunks": total,
            "indexed_sources": len(sources),
            "sources": [s[0] for s in sources],
        }

    def clear(self):
        """Loescht den gesamten Index."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM markdown_fts")
            conn.execute("DELETE FROM sync_state")


class MarkdownStoreWithSearch(MarkdownStore):
    """
    MarkdownStore mit integrierter FTS5 Hybrid-Suche.

    Erweitert den Basis-Store um:
    - Automatische FTS5-Indexierung bei Aenderungen
    - Volltextsuche ueber alle Markdown-Inhalte
    - Hybrid-Abfrage: Keyword-Suche + Markdown-Kontext
    """

    def __init__(self, base_path: Path = None):
        super().__init__(base_path)
        self.search_db_path = self.base_path / "search_index.db"
        self._search_index = HybridSearchIndex(self.search_db_path)
        self.sync_to_index()

    def sync_to_index(self):
        """Synchronisiert alle Markdown-Dateien in den FTS5-Index."""
        # USER.md
        if self.user_path.exists():
            content = self.user_path.read_text(encoding="utf-8")
            self._search_index.index_document("user", "Benutzer-Profil", content)

        # SOUL.md
        if self.soul_path.exists():
            content = self.soul_path.read_text(encoding="utf-8")
            self._search_index.index_document("soul", "Persona", content)

        # MEMORY.md
        if self.memory_path.exists():
            content = self.memory_path.read_text(encoding="utf-8")
            self._search_index.index_document("memory", "Erinnerungen", content)

        # Daily Logs
        for log_file in sorted(self.daily_logs_path.glob("*.md"), reverse=True)[:30]:
            content = log_file.read_text(encoding="utf-8")
            self._search_index.index_document(
                f"daily_{log_file.stem}",
                f"Tageslog {log_file.stem}",
                content
            )

    def update_user_profile(self, updates: Dict[str, Any]) -> bool:
        result = super().update_user_profile(updates)
        if result:
            content = self.user_path.read_text(encoding="utf-8")
            self._search_index.index_document("user", "Benutzer-Profil", content)
        return result

    def update_soul_profile(self, updates: Dict[str, Any]) -> bool:
        result = super().update_soul_profile(updates)
        if result:
            content = self.soul_path.read_text(encoding="utf-8")
            self._search_index.index_document("soul", "Persona", content)
        return result

    def add_memory(self, entry: MemoryEntry) -> bool:
        result = super().add_memory(entry)
        if result:
            content = self.memory_path.read_text(encoding="utf-8")
            self._search_index.index_document("memory", "Erinnerungen", content)
        return result

    def write_daily_log(
        self, log_date: str, content: str, topics: List[str] = None
    ) -> bool:
        result = super().write_daily_log(log_date, content, topics)
        if result:
            log_path = self.daily_logs_path / f"{log_date}.md"
            if log_path.exists():
                file_content = log_path.read_text(encoding="utf-8")
                self._search_index.index_document(
                    f"daily_{log_date}",
                    f"Tageslog {log_date}",
                    file_content
                )
        return result

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Durchsucht alle Markdown-Inhalte via FTS5."""
        return self._search_index.search(query, limit)

    def search_with_context(self, query: str, limit: int = 5) -> str:
        """
        Sucht und gibt formatierte Ergebnisse fuer den Prompt-Kontext zurueck.

        Kombiniert FTS5-Keyword-Suche mit Markdown-Quelldaten
        fuer maximale Relevanz im LLM-Kontext.
        """
        results = self.search(query, limit)
        if not results:
            return ""

        parts = [f"SUCHERGEBNISSE fuer '{query}':"]
        for r in results:
            parts.append(f"- [{r.source}] {r.snippet}")

        return "\n".join(parts)

    def get_search_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken ueber den Suchindex zurueck."""
        return self._search_index.get_stats()


markdown_store = MarkdownStore()
markdown_store_search = MarkdownStoreWithSearch()

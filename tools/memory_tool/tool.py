# tools/memory_tool/tool.py
"""
Timus Memory Tool v2.0

ARCHITECTURE FREEZE (2026-02-17):
- Dieses Modul ist MCP-Adapter fuer Memory-Operationen.
- Kanonische Domain-Logik liegt in memory/memory_system.py.
- Neue Memory-Semantik gehoert in den Kern, nicht exklusiv hier.

Features:
- Session Memory (Kurzzeit-Kontext für aktuelle Konversation)
- ChromaDB (Langzeit-Gedächtnis mit semantischer Suche)
- SQLite (Strukturierte Fakten über den Benutzer)
- Entitäts-Tracking ("er", "sie" → wer ist gemeint)
- Automatische Fakten-Extraktion
- Konversations-Zusammenfassung
- MCP-Integration (V2 Registry)

Ersetzt das alte memory_tool komplett.
"""

import os
import json
import sqlite3
import hashlib
import asyncio
import logging
import uuid
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from dotenv import load_dotenv

load_dotenv()

# === LOGGING ===
log = logging.getLogger("memory_tool")

# === IMPORTS AUS SHARED CONTEXT ===
memory_collection = None
openai_client = None
CHROMADB_AVAILABLE = False

try:
    from tools.shared_context import memory_collection as _mc, openai_client as _oc, log as _log
    memory_collection = _mc
    openai_client = _oc
    log = _log
    CHROMADB_AVAILABLE = memory_collection is not None
except ImportError:
    pass


# === CHROMADB FALLBACK INITIALISIERUNG ===
def _init_chromadb_fallback():
    """Initialisiert ChromaDB selbst, falls nicht über MCP Server geladen."""
    global memory_collection, openai_client, CHROMADB_AVAILABLE

    if memory_collection is not None:
        return  # Schon über shared_context initialisiert

    try:
        import chromadb
        from openai import OpenAI
        from utils.embedding_provider import get_embedding_function

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            log.warning("⚠️ OPENAI_API_KEY fehlt - ChromaDB deaktiviert")
            return

        # OpenAI Client erstellen falls nicht vorhanden
        if openai_client is None:
            openai_client = OpenAI(api_key=api_key)

        # ChromaDB initialisieren
        db_path = Path.home() / "dev" / "timus" / "memory_db"
        db_path.mkdir(parents=True, exist_ok=True)

        chroma_client = chromadb.PersistentClient(path=str(db_path))
        embedding_fn = get_embedding_function()
        memory_collection = chroma_client.get_or_create_collection(
            name="timus_long_term_memory",
            embedding_function=embedding_fn
        )
        CHROMADB_AVAILABLE = True
        log.info(f"✅ ChromaDB Fallback initialisiert: {db_path}")

    except ImportError as e:
        log.warning(f"⚠️ ChromaDB/Embedding-Abhaengigkeit fehlt: {e}")
        CHROMADB_AVAILABLE = False
    except Exception as e:
        log.warning(f"⚠️ ChromaDB Fallback fehlgeschlagen: {e}")
        CHROMADB_AVAILABLE = False

# Bei Import automatisch versuchen
_init_chromadb_fallback()

# === KONFIGURATION ===
MEMORY_DB_PATH = Path.home() / "dev" / "timus" / "data" / "timus_memory.db"
MAX_SESSION_MESSAGES = 20
FACT_EXTRACTION_PATTERNS = [
    (r"ich heiße\s+(\w+)", "name", "user_name"),
    (r"mein name ist\s+(\w+)", "name", "user_name"),
    (r"ich bin\s+(\d+)\s*jahre?\s*alt", "info", "age"),
    (r"ich wohne in\s+(.+?)(?:\.|,|$)", "info", "location"),
    (r"ich arbeite (?:als|bei)\s+(.+?)(?:\.|,|$)", "info", "work"),
    (r"ich mag\s+(.+?)(?:\.|,|$)", "preference", "likes"),
    (r"ich bevorzuge\s+(.+?)(?:\.|,|$)", "preference", "prefers"),
    (r"ich hasse\s+(.+?)(?:\.|,|$)", "preference", "dislikes"),
    (r"meine lieblingsfarbe ist\s+(\w+)", "preference", "favorite_color"),
    (r"ich spreche\s+(.+?)(?:\.|,|$)", "info", "languages"),
]


# === DATENKLASSEN ===

@dataclass
class Message:
    """Eine einzelne Nachricht in der Session."""
    role: str  # "user" oder "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    entities_mentioned: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "entities": self.entities_mentioned
        }


@dataclass
class Fact:
    """Ein strukturierter Fakt über den Benutzer."""
    category: str
    key: str
    value: str
    confidence: float = 1.0
    source: str = "extracted"
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)


@dataclass
class Entity:
    """Eine Entität für Referenz-Tracking."""
    name: str
    type: str  # "person", "place", "thing", "topic"
    last_mentioned: datetime = field(default_factory=datetime.now)
    context: str = ""


# === SESSION MEMORY ===

class SessionMemory:
    """
    Kurzzeit-Gedächtnis für die aktuelle Sitzung.
    Hält die letzten N Nachrichten und trackt Entitäten.
    """

    def __init__(self, max_messages: int = MAX_SESSION_MESSAGES):
        self.messages: List[Message] = []
        self.max_messages = max_messages
        self.session_start = datetime.now()
        self.session_id = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()[:12]

        # Entitäts-Tracking
        self.entities: Dict[str, Entity] = {}
        self.current_topic: Optional[str] = None

        # Pronomen → Entität Mapping
        self.pronoun_map: Dict[str, str] = {}

    def add_message(self, role: str, content: str) -> Message:
        """Fügt eine Nachricht hinzu und extrahiert Entitäten."""
        # Entitäten aus der Nachricht extrahieren
        entities = self._extract_entities(content)

        msg = Message(
            role=role,
            content=content,
            entities_mentioned=entities
        )
        self.messages.append(msg)

        # Pronomen-Mapping aktualisieren
        if entities:
            last_entity = entities[-1]
            self._update_pronoun_map(last_entity, content)

        # Alte Nachrichten entfernen
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

        return msg

    def _extract_entities(self, text: str) -> List[str]:
        """Extrahiert benannte Entitäten aus Text."""
        entities = []

        # Einfache Heuristik: Großgeschriebene Wörter (nicht am Satzanfang)
        words = text.split()
        for i, word in enumerate(words):
            clean_word = re.sub(r'[^\w]', '', word)
            if clean_word and clean_word[0].isupper() and i > 0:
                if len(clean_word) > 1 and clean_word not in ["Ich", "Du", "Er", "Sie", "Es", "Wir"]:
                    entities.append(clean_word)
                    self.entities[clean_word.lower()] = Entity(
                        name=clean_word,
                        type="unknown",
                        context=text[:100]
                    )

        return entities

    def _update_pronoun_map(self, entity: str, context: str):
        """Aktualisiert das Pronomen-Mapping basierend auf Kontext."""
        context_lower = context.lower()

        # Heuristik für Geschlecht/Typ
        if any(word in context_lower for word in ["er ", "sein", "ihm"]):
            self.pronoun_map["er"] = entity
            self.pronoun_map["sein"] = entity
            self.pronoun_map["ihm"] = entity
        elif any(word in context_lower for word in ["sie ", "ihr", "ihre"]):
            self.pronoun_map["sie"] = entity
            self.pronoun_map["ihr"] = entity

        # Generisches "es"/"das" für Themen
        self.pronoun_map["es"] = entity
        self.pronoun_map["das"] = entity
        self.pronoun_map["davon"] = entity

    def resolve_reference(self, text: str) -> str:
        """Löst Pronomen-Referenzen im Text auf."""
        resolved = text

        for pronoun, entity in self.pronoun_map.items():
            # Nur ersetzen wenn es ein isoliertes Pronomen ist
            pattern = rf'\b{pronoun}\b'
            if re.search(pattern, text.lower()):
                # Füge Kontext hinzu statt zu ersetzen
                resolved = f"[Bezug: {entity}] {text}"
                break

        return resolved

    def get_context_string(self, n: int = 10) -> str:
        """Gibt die letzten N Nachrichten als String zurück."""
        if not self.messages:
            return ""

        lines = []
        for msg in self.messages[-n:]:
            role = "User" if msg.role == "user" else "Timus"
            lines.append(f"{role}: {msg.content}")

        return "\n".join(lines)

    def get_active_entities(self) -> List[Entity]:
        """Gibt kürzlich erwähnte Entitäten zurück."""
        cutoff = datetime.now() - timedelta(minutes=5)
        return [e for e in self.entities.values() if e.last_mentioned > cutoff]

    def clear(self):
        """Löscht die Session."""
        self.messages = []
        self.entities = {}
        self.pronoun_map = {}
        self.current_topic = None
        self.session_start = datetime.now()
        self.session_id = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()[:12]


# === PERSISTENT MEMORY (SQLite) ===

class FactStore:
    """SQLite-basierter Speicher für strukturierte Fakten."""

    def __init__(self, db_path: Path = MEMORY_DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialisiert die Datenbank."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'extracted',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(category, key)
                );

                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    topics TEXT,
                    facts_extracted TEXT,
                    message_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
                CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);
            """)

    def store_fact(self, fact: Fact) -> bool:
        """Speichert oder aktualisiert einen Fakt."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO facts (category, key, value, confidence, source, created_at, last_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(category, key) DO UPDATE SET
                        value = excluded.value,
                        confidence = excluded.confidence,
                        last_used = excluded.last_used
                """, (
                    fact.category, fact.key, fact.value, fact.confidence,
                    fact.source, fact.created_at.isoformat(), fact.last_used.isoformat()
                ))
            return True
        except Exception as e:
            log.error(f"Fehler beim Speichern von Fakt: {e}")
            return False

    def get_fact(self, category: str, key: str) -> Optional[Fact]:
        """Holt einen spezifischen Fakt."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT category, key, value, confidence, source FROM facts WHERE category = ? AND key = ?",
                (category, key)
            ).fetchone()

            if row:
                return Fact(category=row[0], key=row[1], value=row[2], confidence=row[3], source=row[4])
        return None

    def get_all_facts(self) -> List[Fact]:
        """Holt alle Fakten."""
        facts = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT category, key, value, confidence, source FROM facts ORDER BY category, last_used DESC"
            ).fetchall()
            for row in rows:
                facts.append(Fact(category=row[0], key=row[1], value=row[2], confidence=row[3], source=row[4]))
        return facts

    def get_facts_by_category(self, category: str) -> List[Fact]:
        """Holt alle Fakten einer Kategorie."""
        facts = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT category, key, value, confidence, source FROM facts WHERE category = ? ORDER BY last_used DESC",
                (category,)
            ).fetchall()
            for row in rows:
                facts.append(Fact(category=row[0], key=row[1], value=row[2], confidence=row[3], source=row[4]))
        return facts

    def delete_fact(self, category: str, key: str) -> bool:
        """Löscht einen Fakt."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM facts WHERE category = ? AND key = ?", (category, key))
            return True
        except:
            return False

    def store_summary(self, session_id: str, summary: str, topics: List[str], facts: List[str], msg_count: int):
        """Speichert eine Konversations-Zusammenfassung."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO summaries (session_id, summary, topics, facts_extracted, message_count)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, summary, json.dumps(topics), json.dumps(facts), msg_count))

    def get_recent_summaries(self, n: int = 5) -> List[Dict]:
        """Holt die letzten N Zusammenfassungen."""
        summaries = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT session_id, summary, topics, created_at FROM summaries ORDER BY created_at DESC LIMIT ?",
                (n,)
            ).fetchall()
            for row in rows:
                summaries.append({
                    "session_id": row[0],
                    "summary": row[1],
                    "topics": json.loads(row[2]) if row[2] else [],
                    "created_at": row[3]
                })
        return summaries

    def store_conversation(self, session_id: str, messages: List[Message]):
        """Speichert eine Konversation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO conversations (session_id, messages)
                VALUES (?, ?)
            """, (session_id, json.dumps([m.to_dict() for m in messages])))


# === MEMORY MANAGER ===

class MemoryManager:
    """
    Zentrale Klasse für das gesamte Memory-System.
    Kombiniert Session Memory, ChromaDB und SQLite.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.session = SessionMemory()
        self.facts = FactStore()
        self.chromadb_available = CHROMADB_AVAILABLE

        log.info(f"🧠 MemoryManager initialisiert. ChromaDB: {'✅' if self.chromadb_available else '❌'}")
        self._initialized = True

    # === KURZZEIT-MEMORY ===

    def add_interaction(self, user_input: str, assistant_response: str):
        """Fügt eine Interaktion hinzu."""
        self.session.add_message("user", user_input)
        self.session.add_message("assistant", assistant_response)

        # Fakten extrahieren
        self._extract_and_store_facts(user_input)

    def _extract_and_store_facts(self, text: str):
        """Extrahiert Fakten aus Text mittels Regex-Patterns."""
        text_lower = text.lower()

        for pattern, category, key in FACT_EXTRACTION_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                value = match.group(1).strip()
                if value:
                    fact = Fact(category=category, key=key, value=value, source="auto_extracted")
                    self.facts.store_fact(fact)
                    log.info(f"📝 Fakt extrahiert: {category}/{key} = {value}")

    def get_session_context(self) -> str:
        """Gibt den aktuellen Session-Kontext zurück."""
        return self.session.get_context_string()

    def resolve_references(self, text: str) -> str:
        """Löst Referenzen im Text auf."""
        return self.session.resolve_reference(text)

    # === LANGZEIT-MEMORY (ChromaDB) ===

    async def remember_long_term(self, text: str, source: str = "user_interaction", agent_id: str = "") -> Dict:
        """Speichert im Langzeit-Gedächtnis (ChromaDB) mit optionaler Agent-ID."""
        if not self.chromadb_available:
            return {"status": "error", "message": "ChromaDB nicht verfügbar"}

        if not text or len(text.strip()) < 10:
            return {"status": "error", "message": "Text zu kurz"}

        try:
            memory_id = str(uuid.uuid4())

            await asyncio.to_thread(
                memory_collection.add,
                documents=[text.strip()],
                metadatas=[{
                    "source": source,
                    "agent_id": agent_id or "unknown",
                    "timestamp_created": datetime.now().isoformat(),
                    "access_count": 0
                }],
                ids=[memory_id]
            )

            log.info(f"🧠 Langzeit-Erinnerung gespeichert: {memory_id[:8]}...")
            return {"status": "success", "memory_id": memory_id}

        except Exception as e:
            log.error(f"Fehler bei Langzeit-Speicherung: {e}")
            return {"status": "error", "message": str(e)}

    async def recall_long_term(self, query: str, n_results: int = 3, agent_filter: str = "") -> Dict:
        """Sucht im Langzeit-Gedächtnis. Optional nur Erinnerungen eines bestimmten Agenten."""
        if not self.chromadb_available:
            return {"status": "error", "memories": [], "message": "ChromaDB nicht verfügbar"}

        try:
            query_kwargs = dict(
                query_texts=[query],
                n_results=n_results,
                include=["metadatas", "documents", "distances"],
            )
            # Agent-Filter: nur Erinnerungen dieses Agenten zurueckgeben
            if agent_filter:
                query_kwargs["where"] = {"agent_id": {"$eq": agent_filter}}

            results = await asyncio.to_thread(
                memory_collection.query,
                **query_kwargs
            )

            memories = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    distance = results["distances"][0][i]
                    relevance = max(0, 1 - (distance / 2))

                    memories.append({
                        "id": results["ids"][0][i],
                        "text": doc,
                        "metadata": results["metadatas"][0][i],
                        "relevance_score": round(relevance, 2)
                    })

            log.info(f"🔍 Recall für '{query[:30]}...' → {len(memories)} Treffer")
            return {"status": "success", "memories": memories}

        except Exception as e:
            log.error(f"Fehler bei Recall: {e}")
            return {"status": "error", "memories": [], "message": "Gedaechtnis-Suche voruebergehend nicht verfuegbar"}

    # === FAKTEN-MANAGEMENT ===

    def remember_fact(self, key: str, value: str, category: str = "user_stated") -> bool:
        """Speichert einen Fakt explizit."""
        fact = Fact(category=category, key=key, value=value, source="explicit")
        return self.facts.store_fact(fact)

    def recall_fact(self, key: str) -> Optional[str]:
        """Ruft einen Fakt ab."""
        for cat in ["user_stated", "name", "preference", "info", "auto_extracted"]:
            fact = self.facts.get_fact(cat, key)
            if fact:
                return fact.value
        return None

    def forget_fact(self, key: str) -> bool:
        """Löscht einen Fakt."""
        deleted = False
        for cat in ["user_stated", "name", "preference", "info", "auto_extracted"]:
            if self.facts.delete_fact(cat, key):
                deleted = True
        return deleted

    def get_all_known_facts(self) -> List[Dict]:
        """Gibt alle bekannten Fakten zurück."""
        facts = self.facts.get_all_facts()
        return [{"category": f.category, "key": f.key, "value": f.value} for f in facts]

    # === KONTEXT-BUILDING ===

    def build_context_for_prompt(self) -> str:
        """Baut den kompletten Memory-Kontext für Prompts."""
        context_parts = []

        # 1. Bekannte Fakten
        facts = self.facts.get_all_facts()
        if facts:
            fact_lines = [f"- {f.key}: {f.value}" for f in facts[:10]]
            context_parts.append("BEKANNTE FAKTEN ÜBER DEN BENUTZER:\n" + "\n".join(fact_lines))

        # 2. Letzte Zusammenfassungen
        summaries = self.facts.get_recent_summaries(2)
        if summaries:
            summary_text = "\n".join([s["summary"] for s in summaries])
            context_parts.append(f"FRÜHERE GESPRÄCHE:\n{summary_text}")

        # 3. Aktuelle Session
        session = self.session.get_context_string()
        if session:
            context_parts.append(f"AKTUELLE KONVERSATION:\n{session}")

        # 4. Aktive Entitäten
        entities = self.session.get_active_entities()
        if entities:
            entity_lines = [f"- {e.name} ({e.type})" for e in entities]
            context_parts.append("KÜRZLICH ERWÄHNTE ENTITÄTEN:\n" + "\n".join(entity_lines))

        # 5. Pronomen-Referenzen
        if self.session.pronoun_map:
            ref_lines = [f"- '{k}' → {v}" for k, v in self.session.pronoun_map.items()]
            context_parts.append("AKTUELLE REFERENZEN:\n" + "\n".join(ref_lines))

        return "\n\n".join(context_parts)

    # === SESSION-MANAGEMENT ===

    async def summarize_and_end_session(self) -> Optional[Dict]:
        """Fasst die Session zusammen und speichert sie."""
        if len(self.session.messages) < 4:
            self.session.clear()
            return None

        if not openai_client:
            # Ohne OpenAI einfach speichern
            self.facts.store_conversation(self.session.session_id, self.session.messages)
            self.session.clear()
            return None

        try:
            messages_text = self.session.get_context_string()

            response = await asyncio.to_thread(
                openai_client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """Fasse das Gespräch kurz zusammen und extrahiere wichtige Fakten.
Antworte NUR mit JSON:
{"summary": "...", "topics": ["..."], "user_facts": ["..."]}"""
                    },
                    {"role": "user", "content": messages_text}
                ],
                max_tokens=500
            )

            result = json.loads(response.choices[0].message.content)

            # Zusammenfassung speichern
            self.facts.store_summary(
                self.session.session_id,
                result.get("summary", ""),
                result.get("topics", []),
                result.get("user_facts", []),
                len(self.session.messages)
            )

            # Extrahierte Fakten speichern
            for fact_text in result.get("user_facts", []):
                fact = Fact(
                    category="summarized",
                    key=f"fact_{hashlib.md5(fact_text.encode()).hexdigest()[:8]}",
                    value=fact_text,
                    source="summarization"
                )
                self.facts.store_fact(fact)

            # Konversation speichern
            self.facts.store_conversation(self.session.session_id, self.session.messages)

            log.info(f"📝 Session zusammengefasst: {len(self.session.messages)} Nachrichten")

            self.session.clear()
            return result

        except Exception as e:
            log.error(f"Fehler bei Zusammenfassung: {e}")
            self.session.clear()
            return None

    def get_stats(self) -> Dict:
        """Gibt Memory-Statistiken zurück."""
        return {
            "session_messages": len(self.session.messages),
            "session_id": self.session.session_id,
            "total_facts": len(self.facts.get_all_facts()),
            "total_summaries": len(self.facts.get_recent_summaries(100)),
            "entities_tracked": len(self.session.entities),
            "chromadb_available": self.chromadb_available
        }


# === GLOBALE INSTANZ ===
memory_manager = MemoryManager()


# === MCP TOOL METHODS ===

@tool(
    name="remember",
    description="Speichert eine Information im Langzeit-Gedächtnis mit Agent-Herkunft.",
    parameters=[
        P("text",     "string", "Der zu speichernde Text"),
        P("source",   "string", "Quelle der Information (z.B. user_interaction, web_search)", required=False, default="user_interaction"),
        P("agent_id", "string", "Agenten-ID fuer spaetere Filterung (z.B. 'executor', 'data', 'shell')", required=False, default=""),
    ],
    capabilities=["memory"],
    category=C.MEMORY
)
async def remember(text: str, source: str = "user_interaction", agent_id: str = "") -> dict:
    """
    Speichert eine Information im Langzeit-Gedächtnis.

    Args:
        text: Der zu speichernde Text
        source: Quelle der Information (z.B. "user_interaction", "web_search")

    Returns:
        Dict mit memory_id oder Fehler
    """
    if not text or len(text.strip()) < 10:
        raise Exception("Text muss mindestens 10 Zeichen haben.")

    result = await memory_manager.remember_long_term(text, source, agent_id)

    if result["status"] == "success":
        return result
    else:
        raise Exception(result.get("message", "Unbekannter Fehler"))


@tool(
    name="recall",
    description="Sucht relevante Informationen im Gedächtnis (episodisch + semantisch).",
    parameters=[
        P("query",        "string",  "Suchanfrage"),
        P("n_results",    "integer", "Maximale Anzahl Ergebnisse (1-10)", required=False, default=3),
        P("session_id",   "string",  "Optionale Session-ID fuer episodische Priorisierung", required=False, default=""),
        P("agent_filter", "string",  "Nur Erinnerungen dieses Agenten (z.B. 'shell', 'data'). Leer = alle.", required=False, default=""),
    ],
    capabilities=["memory"],
    category=C.MEMORY
)
async def recall(query: str, n_results: int = 3, session_id: str = "", agent_filter: str = "") -> dict:
    """
    Sucht relevante Informationen im Gedächtnis (episodisch + semantisch).

    Args:
        query: Suchanfrage
        n_results: Maximale Anzahl Ergebnisse (1-10)
        session_id: Optionale Session-ID fuer aktuelle Konversation

    Returns:
        Dict mit Liste von Erinnerungen
    """
    if not query:
        raise Exception("Query darf nicht leer sein.")

    n_results = max(1, min(10, n_results))
    # Kanonischer Kern: memory/memory_system.py
    try:
        from memory.memory_system import memory_manager as canonical_memory_manager

        if hasattr(canonical_memory_manager, "unified_recall"):
            return canonical_memory_manager.unified_recall(
                query=query,
                n_results=n_results,
                session_id=session_id or None,
            )
    except Exception as e:
        log.debug(f"Unified recall fallback auf legacy Chroma-Pfad: {e}")

    # Legacy-Fallback (nur semantisch) - agent_filter wird weitergegeben
    result = await memory_manager.recall_long_term(query, n_results, agent_filter)
    return result


@tool(
    name="remember_fact",
    description="Speichert einen strukturierten Fakt.",
    parameters=[
        P("key", "string", "Schlüssel (z.B. name, favorite_color)"),
        P("value", "string", "Wert (z.B. Fatih, blau)"),
        P("category", "string", "Kategorie (name, preference, info, user_stated)", required=False, default="user_stated"),
    ],
    capabilities=["memory"],
    category=C.MEMORY
)
async def remember_fact(key: str, value: str, category: str = "user_stated") -> dict:
    """
    Speichert einen strukturierten Fakt.

    Args:
        key: Schlüssel (z.B. "name", "favorite_color")
        value: Wert (z.B. "Fatih", "blau")
        category: Kategorie ("name", "preference", "info", "user_stated")

    Returns:
        Dict mit Status
    """
    if not key or not value:
        raise Exception("Key und Value sind erforderlich.")

    success = memory_manager.remember_fact(key, value, category)

    if success:
        log.info(f"✅ Fakt gespeichert: {category}/{key} = {value}")
        return {"status": "success", "key": key, "value": value}
    else:
        raise Exception("Fehler beim Speichern des Fakts.")


@tool(
    name="recall_fact",
    description="Ruft einen gespeicherten Fakt ab.",
    parameters=[
        P("key", "string", "Der Schlüssel des Fakts"),
    ],
    capabilities=["memory"],
    category=C.MEMORY
)
async def recall_fact(key: str) -> dict:
    """
    Ruft einen gespeicherten Fakt ab.

    Args:
        key: Der Schlüssel des Fakts

    Returns:
        Dict mit Wert oder not_found
    """
    value = memory_manager.recall_fact(key)

    if value:
        return {"status": "success", "key": key, "value": value}
    else:
        return {"status": "not_found", "key": key, "value": None}


@tool(
    name="forget_fact",
    description="Löscht einen gespeicherten Fakt.",
    parameters=[
        P("key", "string", "Der Schlüssel des zu löschenden Fakts"),
    ],
    capabilities=["memory"],
    category=C.MEMORY
)
async def forget_fact(key: str) -> dict:
    """
    Löscht einen gespeicherten Fakt.

    Args:
        key: Der Schlüssel des zu löschenden Fakts

    Returns:
        Dict mit Status
    """
    success = memory_manager.forget_fact(key)

    if success:
        log.info(f"🗑️ Fakt gelöscht: {key}")
        return {"status": "success", "key": key}
    else:
        return {"status": "not_found", "key": key}


@tool(
    name="get_memory_context",
    description="Gibt den kompletten Memory-Kontext für Prompts zurück.",
    parameters=[],
    capabilities=["memory"],
    category=C.MEMORY
)
async def get_memory_context() -> dict:
    """
    Gibt den kompletten Memory-Kontext für Prompts zurück.

    Returns:
        Dict mit Kontext-String
    """
    context = memory_manager.build_context_for_prompt()
    return {"context": context}


@tool(
    name="get_known_facts",
    description="Gibt alle bekannten Fakten über den Benutzer zurück.",
    parameters=[],
    capabilities=["memory"],
    category=C.MEMORY
)
async def get_known_facts() -> dict:
    """
    Gibt alle bekannten Fakten über den Benutzer zurück.

    Returns:
        Dict mit Liste von Fakten
    """
    facts = memory_manager.get_all_known_facts()
    return {"facts": facts, "count": len(facts)}


@tool(
    name="add_interaction",
    description="Fügt eine Interaktion zum Session-Memory hinzu.",
    parameters=[
        P("user_input", "string", "Die Benutzereingabe"),
        P("assistant_response", "string", "Die Assistenten-Antwort"),
    ],
    capabilities=["memory"],
    category=C.MEMORY
)
async def add_interaction(user_input: str, assistant_response: str) -> dict:
    """
    Fügt eine Interaktion zum Session-Memory hinzu.

    Args:
        user_input: Die Benutzereingabe
        assistant_response: Die Assistenten-Antwort

    Returns:
        Dict mit Status
    """
    memory_manager.add_interaction(user_input, assistant_response)
    return {"status": "success", "session_messages": len(memory_manager.session.messages)}


@tool(
    name="end_session",
    description="Beendet die aktuelle Session, erstellt Zusammenfassung und speichert.",
    parameters=[],
    capabilities=["memory"],
    category=C.MEMORY
)
async def end_session() -> dict:
    """
    Beendet die aktuelle Session, erstellt Zusammenfassung und speichert.

    Returns:
        Dict mit Zusammenfassung
    """
    result = await memory_manager.summarize_and_end_session()
    return {"status": "success", "summary": result}


@tool(
    name="get_memory_stats",
    description="Gibt Statistiken über das Memory-System zurück.",
    parameters=[],
    capabilities=["memory"],
    category=C.MEMORY
)
async def get_memory_stats() -> dict:
    """
    Gibt Statistiken über das Memory-System zurück.

    Returns:
        Dict mit Stats
    """
    stats = memory_manager.get_stats()
    return stats


@tool(
    name="resolve_reference",
    description="Löst Pronomen-Referenzen im Text auf.",
    parameters=[
        P("text", "string", "Text mit möglichen Referenzen (z.B. Wie alt ist er?)"),
    ],
    capabilities=["memory"],
    category=C.MEMORY
)
async def resolve_reference(text: str) -> dict:
    """
    Löst Pronomen-Referenzen im Text auf.

    Args:
        text: Text mit möglichen Referenzen ("Wie alt ist er?")

    Returns:
        Dict mit aufgelöstem Text
    """
    resolved = memory_manager.resolve_references(text)
    return {"original": text, "resolved": resolved}


# === HELPER FUNCTIONS FÜR DIREKTEN IMPORT ===

def get_context() -> str:
    """Shortcut für Memory-Kontext."""
    return memory_manager.build_context_for_prompt()

def add_to_memory(user_input: str, response: str):
    """Shortcut für Interaktion hinzufügen."""
    memory_manager.add_interaction(user_input, response)

def quick_remember(key: str, value: str):
    """Shortcut für Fakt speichern."""
    memory_manager.remember_fact(key, value)

def quick_recall(key: str) -> Optional[str]:
    """Shortcut für Fakt abrufen."""
    return memory_manager.recall_fact(key)

# memory/memory_system.py
"""
Timus Memory System v2.0

ARCHITECTURE FREEZE (2026-02-17):
- Dieses Modul ist der kanonische Memory-Kern (Domain-Logik, Persistenz, Retrieval).
- MCP-Tool-Endpunkte in tools/memory_tool/tool.py sollen als Adapter dienen.

Features:
- Session Memory (aktuelle Konversation)
- Persistent Memory (SQLite Datenbank)
- Fact Extraction (extrahiert Fakten aus Gesprächen)
- Conversation Summarization (fasst alte Gespräche zusammen)
- Semantic Retrieval (findet relevante Erinnerungen)
- Hybrid Search (ChromaDB + FTS5)
- Markdown Sync (bidirektional)

v2.0 NEW:
- SemanticMemoryStore: ChromaDB integration for semantic search
- Hybrid search combining vector embeddings + keyword FTS5
- Bidirectional sync with Markdown files
"""

import os
import json
import sqlite3
import logging
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field, asdict
from openai import OpenAI
from utils.openai_compat import prepare_openai_params
from dotenv import load_dotenv

if TYPE_CHECKING:
    import chromadb

load_dotenv()
log = logging.getLogger("memory_system")

# Konfiguration
MEMORY_DB_PATH = Path.home() / "dev" / "timus" / "data" / "timus_memory.db"
MAX_SESSION_MESSAGES = 20  # Letzte N Nachrichten im Kontext
MAX_CONTEXT_TOKENS = 2000  # Max Tokens für Memory-Kontext
SUMMARIZE_THRESHOLD = 10  # Nach N Nachrichten zusammenfassen
SELF_MODEL_MIN_MESSAGES = 6
SELF_MODEL_UPDATE_INTERVAL_HOURS = 12
WORKING_MEMORY_MAX_CHARS = 3200
WORKING_MEMORY_MAX_RELATED = 4
WORKING_MEMORY_MAX_RECENT_EVENTS = 6
WORKING_MEMORY_EVENT_HALF_LIFE_HOURS = 18
WORKING_MEMORY_MEMORY_HALF_LIFE_DAYS = 21


@dataclass
class Message:
    """Eine einzelne Nachricht."""
    role: str  # "user" oder "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class Fact:
    """Ein gelernter Fakt über den Benutzer."""
    category: str  # "name", "preference", "info", "context"
    key: str
    value: str
    confidence: float = 1.0
    source: str = ""  # Woher der Fakt stammt
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)


@dataclass
class ConversationSummary:
    """Zusammenfassung einer Konversation."""
    summary: str
    topics: List[str]
    facts_extracted: List[str]
    message_count: int
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class MemoryItem:
    """Strukturiertes Langzeit-Gedächtnis."""
    category: str  # user_profile, working_memory, relationships, decisions, patterns
    key: str
    value: Any
    importance: float = 0.5
    confidence: float = 1.0
    reason: str = ""
    source: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)


@dataclass
class SemanticSearchResult:
    """Ergebnis einer semantischen Suche."""
    doc_id: str
    content: str
    category: str
    importance: float
    distance: float
    source: str  # "chromadb" or "fts5"
    key: str = ""
    created_at: str = ""


class SemanticMemoryStore:
    """
    ChromaDB-basierter Vektor-Store für semantische Suche.
    
    Speichert MemoryItems als Embeddings und ermöglicht
    kontextuelle Suche über bedeutungsähnliche Inhalte.
    """
    
    def __init__(self, collection: Optional["chromadb.Collection"] = None):
        self.collection = collection
        self._initialized = collection is not None
    
    def is_available(self) -> bool:
        """Prüft ob ChromaDB verfügbar ist."""
        return self._initialized and self.collection is not None
    
    def store_embedding(self, item: MemoryItem) -> Optional[str]:
        """Speichert MemoryItem mit Embedding in ChromaDB."""
        if not self.is_available():
            log.debug("ChromaDB nicht verfügbar, überspringe Embedding")
            return None
        
        try:
            doc_id = f"{item.category}_{item.key}"
            content = str(item.value) if not isinstance(item.value, str) else item.value
            
            self.collection.upsert(
                ids=[doc_id],
                documents=[content],
                metadatas=[{
                    "category": item.category,
                    "key": item.key,
                    "importance": item.importance,
                    "confidence": item.confidence,
                    "source": item.source,
                    "reason": item.reason[:100] if item.reason else "",
                    "created_at": item.created_at.isoformat()
                }]
            )
            log.debug(f"ChromaDB: Embedding gespeichert {doc_id}")
            return doc_id
        except Exception as e:
            log.warning(f"ChromaDB Store fehlgeschlagen: {e}")
            return None
    
    def delete_embedding(self, category: str, key: str) -> bool:
        """Löscht Embedding aus ChromaDB."""
        if not self.is_available():
            return False
        
        try:
            doc_id = f"{category}_{key}"
            self.collection.delete(ids=[doc_id])
            return True
        except Exception as e:
            log.warning(f"ChromaDB Delete fehlgeschlagen: {e}")
            return False
    
    def find_related_memories(
        self, 
        query: str, 
        n_results: int = 5,
        category_filter: Optional[str] = None
    ) -> List[SemanticSearchResult]:
        """
        Semantische Suche nach relevanten Erinnerungen.
        
        Nutzt Vektor-Embeddings für bedeutungsbasierte Suche
        (nicht nur Keyword-Match).
        """
        if not self.is_available():
            return []
        
        try:
            where_filter = None
            if category_filter:
                where_filter = {"category": category_filter}
            
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter
            )
            
            return self._format_results(results)
        except Exception as e:
            log.warning(f"ChromaDB Query fehlgeschlagen: {e}")
            return []
    
    def _format_results(self, results: Dict) -> List[SemanticSearchResult]:
        """Formatiert ChromaDB-Ergebnisse."""
        formatted = []
        
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        
        for i, doc_id in enumerate(ids):
            formatted.append(SemanticSearchResult(
                doc_id=doc_id,
                content=documents[i] if i < len(documents) else "",
                category=metadatas[i].get("category", "unknown") if i < len(metadatas) else "unknown",
                importance=metadatas[i].get("importance", 0.5) if i < len(metadatas) else 0.5,
                distance=distances[i] if i < len(distances) else 0.0,
                source="chromadb",
                key=metadatas[i].get("key", "") if i < len(metadatas) else "",
                created_at=metadatas[i].get("created_at", "") if i < len(metadatas) else "",
            ))
        
        return formatted
    
    def get_by_category(self, category: str, limit: int = 20) -> List[SemanticSearchResult]:
        """Holt alle Einträge einer Kategorie."""
        if not self.is_available():
            return []
        
        try:
            # ChromaDB get mit where-filter
            results = self.collection.get(
                where={"category": category},
                limit=limit
            )
            
            formatted = []
            ids = results.get("ids", [])
            documents = results.get("documents", [])
            metadatas = results.get("metadatas", [])
            
            for i, doc_id in enumerate(ids):
                formatted.append(SemanticSearchResult(
                    doc_id=doc_id,
                    content=documents[i] if i < len(documents) else "",
                    category=category,
                    importance=metadatas[i].get("importance", 0.5) if i < len(metadatas) else 0.5,
                    distance=0.0,
                    source="chromadb",
                    key=metadatas[i].get("key", "") if i < len(metadatas) else "",
                    created_at=metadatas[i].get("created_at", "") if i < len(metadatas) else "",
                ))
            
            return formatted
        except Exception as e:
            log.warning(f"ChromaDB Get by Category fehlgeschlagen: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück."""
        if not self.is_available():
            return {"available": False, "count": 0}
        
        try:
            count = self.collection.count()
            return {
                "available": True,
                "count": count,
                "name": self.collection.name
            }
        except Exception as e:
            return {"available": False, "error": str(e)}


class SessionMemory:
    """
    Kurzzeit-Gedächtnis für die aktuelle Sitzung.
    Speichert die letzten N Nachrichten.
    """
    
    def __init__(self, max_messages: int = MAX_SESSION_MESSAGES):
        self.messages: List[Message] = []
        self.max_messages = max_messages
        self.session_start = datetime.now()
        self.current_topic: Optional[str] = None
        self.entities: Dict[str, str] = {}  # Aktuelle Entitäten (er/sie/es → wer)
    
    def add_message(self, role: str, content: str):
        """Fügt eine Nachricht hinzu."""
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        
        # Alte Nachrichten entfernen
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
    
    def get_recent_messages(self, n: int = 10) -> List[Message]:
        """Gibt die letzten N Nachrichten zurück."""
        return self.messages[-n:]
    
    def get_context_string(self) -> str:
        """Gibt die Nachrichten als formatierten String zurück."""
        if not self.messages:
            return ""
        
        lines = []
        for msg in self.messages[-10:]:
            role = "User" if msg.role == "user" else "Timus"
            lines.append(f"{role}: {msg.content}")
        
        return "\n".join(lines)
    
    def update_entity(self, pronoun: str, entity: str):
        """Aktualisiert Entitäts-Referenzen (er → Emmanuel Macron)."""
        self.entities[pronoun.lower()] = entity
    
    def resolve_entity(self, pronoun: str) -> Optional[str]:
        """Löst ein Pronomen zu einer Entität auf."""
        return self.entities.get(pronoun.lower())
    
    def clear(self):
        """Löscht die Session."""
        self.messages = []
        self.entities = {}
        self.current_topic = None
        self.session_start = datetime.now()


class PersistentMemory:
    """
    Langzeit-Gedächtnis mit SQLite.
    Speichert Fakten, Präferenzen und Zusammenfassungen.
    """
    
    def __init__(self, db_path: Path = MEMORY_DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        
    def _safe_json(self, val):
        """Sicher JSON laden."""
        if not val or val == "":
            return []
        try:
            return json.loads(val)
        except:
            return []
    def _safe_datetime(self, val):
        """Sicher Datetime parsen."""
        if not val or not isinstance(val, str):
            return datetime.now()
        try:
            return datetime.fromisoformat(val)
        except:
            return datetime.now()   
    def _init_db(self):

        """Initialisiert die Datenbank-Tabellen."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(category, key)
                );
                
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary TEXT NOT NULL,
                    topics TEXT,  -- JSON array
                    facts_extracted TEXT,  -- JSON array
                    message_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    messages TEXT NOT NULL,  -- JSON array
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS interaction_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    agent_name TEXT,
                    status TEXT DEFAULT 'completed',
                    user_input TEXT NOT NULL,
                    assistant_response TEXT NOT NULL,
                    metadata TEXT,  -- JSON object
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS memory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,  -- JSON
                    importance REAL DEFAULT 0.5,
                    confidence REAL DEFAULT 1.0,
                    reason TEXT,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(category, key)
                );
                
                CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
                CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);
                CREATE INDEX IF NOT EXISTS idx_summaries_created ON summaries(created_at);
                CREATE INDEX IF NOT EXISTS idx_interaction_events_session ON interaction_events(session_id);
                CREATE INDEX IF NOT EXISTS idx_interaction_events_created ON interaction_events(created_at);
                CREATE INDEX IF NOT EXISTS idx_memory_category ON memory_items(category);
                CREATE INDEX IF NOT EXISTS idx_memory_key ON memory_items(key);
            """)
    
    # === FACTS ===
    
    def store_fact(self, fact: Fact):
        """Speichert oder aktualisiert einen Fakt."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO facts (category, key, value, confidence, source, created_at, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    last_used = excluded.last_used
            """, (
                fact.category,
                fact.key,
                fact.value,
                fact.confidence,
                fact.source,
                fact.created_at.isoformat(),
                fact.last_used.isoformat()
            ))
    
    def get_fact(self, category: str, key: str) -> Optional[Fact]:
        """Holt einen spezifischen Fakt."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM facts WHERE category = ? AND key = ?",
                (category, key)
            ).fetchone()
            
            if row:
                return Fact(
                    category=row[1],
                    key=row[2],
                    value=row[3],
                    confidence=row[4],
                    source=row[5],
                    created_at=datetime.fromisoformat(row[6]),
                    last_used=datetime.fromisoformat(row[7])
                )
        return None
    
    def get_facts_by_category(self, category: str) -> List[Fact]:
        """Holt alle Fakten einer Kategorie."""
        facts = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM facts WHERE category = ? ORDER BY last_used DESC",
                (category,)
            ).fetchall()
            
            for row in rows:
                facts.append(Fact(
                    category=row[1],
                    key=row[2],
                    value=row[3],
                    confidence=row[4],
                    source=row[5]
                ))
        return facts
    
    def get_all_facts(self) -> List[Fact]:
        """Holt alle Fakten."""
        facts = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM facts ORDER BY category, last_used DESC"
            ).fetchall()
            
            for row in rows:
                facts.append(Fact(
                    category=row[1],
                    key=row[2],
                    value=row[3],
                    confidence=row[4],
                    source=row[5]
                ))
        return facts

    # === MEMORY ITEMS ===

    def store_memory_item(self, item: MemoryItem):
        """Speichert oder aktualisiert ein MemoryItem."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO memory_items (
                    category, key, value, importance, confidence, reason, source, created_at, last_used
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value = excluded.value,
                    importance = excluded.importance,
                    confidence = excluded.confidence,
                    reason = excluded.reason,
                    source = excluded.source,
                    last_used = excluded.last_used
            """, (
                item.category,
                item.key,
                json.dumps(item.value, ensure_ascii=False),
                item.importance,
                item.confidence,
                item.reason,
                item.source,
                item.created_at.isoformat(),
                item.last_used.isoformat()
            ))

    def get_memory_items(self, category: str) -> List[MemoryItem]:
        """Holt MemoryItems einer Kategorie."""
        items = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM memory_items WHERE category = ? ORDER BY last_used DESC",
                (category,)
            ).fetchall()
            for row in rows:
                items.append(MemoryItem(
                    category=row[1],
                    key=row[2],
                    value=self._safe_json(row[3]) or row[3],
                    importance=row[4],
                    confidence=row[5],
                    reason=row[6] or "",
                    source=row[7] or "",
                    created_at=self._safe_datetime(row[8]),
                    last_used=self._safe_datetime(row[9])
                ))
        return items

    def get_all_memory_items(self) -> List[MemoryItem]:
        """Holt alle MemoryItems."""
        items = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM memory_items ORDER BY category, last_used DESC"
            ).fetchall()
            for row in rows:
                items.append(MemoryItem(
                    category=row[1],
                    key=row[2],
                    value=self._safe_json(row[3]) or row[3],
                    importance=row[4],
                    confidence=row[5],
                    reason=row[6] or "",
                    source=row[7] or "",
                    created_at=self._safe_datetime(row[8]),
                    last_used=self._safe_datetime(row[9])
                ))
        return items
    
    def delete_fact(self, category: str, key: str):
        """Löscht einen Fakt."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM facts WHERE category = ? AND key = ?",
                (category, key)
            )
    
    # === SUMMARIES ===
    
    def store_summary(self, summary: ConversationSummary):
        """Speichert eine Zusammenfassung."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO summaries (summary, topics, facts_extracted, message_count, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                summary.summary,
                json.dumps(summary.topics),
                json.dumps(summary.facts_extracted),
                summary.message_count,
                summary.created_at.isoformat()
            ))
    
    def get_recent_summaries(self, n: int = 5) -> List[ConversationSummary]:
        """Holt die letzten N Zusammenfassungen."""
        summaries = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM summaries ORDER BY created_at DESC LIMIT ?",
                (n,)
            ).fetchall()
            
            for row in rows:
                summaries.append(ConversationSummary(
                    summary=row[2],
                    topics=self._safe_json(row[3]),
                    facts_extracted=self._safe_json(row[4]),
                    message_count=row[5],
                    created_at=self._safe_datetime(row[6])
                ))
        return summaries
    
    # === CONVERSATIONS ===
    
    def store_conversation(self, session_id: str, messages: List[Message]):
        """Speichert eine komplette Konversation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO conversations (session_id, messages, created_at)
                VALUES (?, ?, ?)
            """, (
                session_id,
                json.dumps([m.to_dict() for m in messages]),
                datetime.now().isoformat()
            ))
    
    def search_conversations(self, query: str, limit: int = 5) -> List[Dict]:
        """Durchsucht Konversationen nach einem Begriff."""
        results = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE messages LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", limit)
            ).fetchall()
            
            for row in rows:
                results.append({
                    "session_id": row[1],
                    "messages": json.loads(row[2]),
                    "created_at": row[3]
                })
        return results

    def store_interaction_event(
        self,
        session_id: str,
        user_input: str,
        assistant_response: str,
        agent_name: str = "",
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Speichert ein einzelnes Interaktions-Event deterministisch."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO interaction_events (
                    session_id, agent_name, status, user_input, assistant_response, metadata, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    agent_name,
                    status,
                    user_input,
                    assistant_response,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    datetime.now().isoformat(),
                ),
            )

    def count_interaction_events(self) -> int:
        """Anzahl aller gespeicherten Interaktions-Events."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM interaction_events").fetchone()
            return int(row[0]) if row else 0

    def get_recent_interaction_events(
        self,
        limit: int = 20,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Holt die zuletzt persistierten Interaktions-Events (neueste zuerst)."""
        events: List[Dict[str, Any]] = []
        with sqlite3.connect(self.db_path) as conn:
            if session_id:
                rows = conn.execute(
                    """
                    SELECT session_id, agent_name, status, user_input, assistant_response, metadata, created_at
                    FROM interaction_events
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT session_id, agent_name, status, user_input, assistant_response, metadata, created_at
                    FROM interaction_events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

            for row in rows:
                metadata_raw = row[5] or ""
                metadata: Dict[str, Any] = {}
                if metadata_raw:
                    try:
                        loaded = json.loads(metadata_raw)
                        if isinstance(loaded, dict):
                            metadata = loaded
                    except Exception:
                        metadata = {}

                events.append(
                    {
                        "session_id": row[0],
                        "agent_name": row[1] or "",
                        "status": row[2] or "",
                        "user_input": row[3] or "",
                        "assistant_response": row[4] or "",
                        "metadata": metadata,
                        "created_at": row[6] or "",
                    }
                )

        return events


class MemoryManager:
    """
    Hauptklasse für das Memory-System.
    Kombiniert Session, Persistent Memory und Semantic Search.
    
    v2.0 Features:
    - ChromaDB für semantische Suche
    - Hybrid-Suche (Vector + FTS5)
    - Bidirektionaler Markdown-Sync
    """
    
    def __init__(self):
        self.session = SessionMemory()
        self.persistent = PersistentMemory()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.session_id = hashlib.md5(
            datetime.now().isoformat().encode()
        ).hexdigest()[:12]
        self.self_model_last_updated: Optional[datetime] = None
        self.self_model_dirty = False
        self._last_working_memory_stats: Dict[str, Any] = {}
        
        # NEW: Semantic Memory Store (ChromaDB)
        self.semantic_store: Optional[SemanticMemoryStore] = None
        self._init_semantic_store()
        
        # NEW: Markdown Store for bidirectional sync
        self._markdown_store = None
        
        self._load_self_model_state()

    def get_last_working_memory_stats(self) -> Dict[str, Any]:
        """Gibt Metadaten des letzten Working-Memory-Builds zurück."""
        return dict(self._last_working_memory_stats)
    
    def _init_semantic_store(self):
        """Initialisiert ChromaDB-Store wenn verfügbar."""
        try:
            # Lazy import to avoid circular dependency
            import tools.shared_context as shared_context
            if hasattr(shared_context, 'memory_collection') and shared_context.memory_collection:
                self.semantic_store = SemanticMemoryStore(shared_context.memory_collection)
                log.info("✅ SemanticMemoryStore (ChromaDB) initialisiert")
            else:
                log.debug("ChromaDB Collection nicht verfügbar, Semantic Search deaktiviert")
        except ImportError:
            log.debug("shared_context nicht verfügbar, Semantic Search deaktiviert")
        except Exception as e:
            log.warning(f"SemanticMemoryStore Init fehlgeschlagen: {e}")
    
    def _get_markdown_store(self):
        """Lazy-Load Markdown Store."""
        if self._markdown_store is None:
            try:
                from memory.markdown_store import MarkdownStoreWithSearch
                self._markdown_store = MarkdownStoreWithSearch()
            except ImportError:
                from memory.markdown_store.store import MarkdownStoreWithSearch
                self._markdown_store = MarkdownStoreWithSearch()
        return self._markdown_store

    def _create_chat_completion(self, params: Dict[str, Any]):
        return self.client.chat.completions.create(**prepare_openai_params(params))

    def _parse_json_response(self, raw: Optional[str]) -> Optional[Dict[str, Any]]:
        if not raw or not raw.strip():
            return None

        text = raw.strip()

        fenced = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.DOTALL)
        if not fenced:
            fenced = re.search(r"```([\s\S]*?)```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()

        candidates = [text]
        match = re.search(r"(\{[\s\S]*\})", text, re.DOTALL)
        if match and match.group(1) not in candidates:
            candidates.append(match.group(1))

        for candidate in candidates:
            cleaned = re.sub(r",\s*([\}\]])", r"\1", candidate)
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data

        return None
    
    def add_interaction(self, user_input: str, assistant_response: str):
        """Fügt eine Interaktion hinzu und extrahiert Fakten."""
        self.session.add_message("user", user_input)
        self.session.add_message("assistant", assistant_response)
        
        # Selektive Memory-Extraktion
        self._process_memory_candidates(user_input)

    def log_interaction_event(
        self,
        user_input: str,
        assistant_response: str,
        agent_name: str = "",
        status: str = "completed",
        external_session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Deterministisches Logging pro Runde (unabhängig von Tool-Wahl)."""
        user_text = (user_input or "").strip()
        assistant_text = (assistant_response or "").strip()
        if not user_text:
            return

        # Kurzzeitkontext + Kandidaten-Extraktion aktualisieren
        self.add_interaction(user_text, assistant_text)

        # Persistentes Event sofort schreiben
        self.persistent.store_interaction_event(
            session_id=external_session_id or self.session_id,
            user_input=user_text,
            assistant_response=assistant_text,
            agent_name=agent_name,
            status=status,
            metadata=metadata or {},
        )
    
    def _process_memory_candidates(self, message: str):
        """Erstellt Memory-Kandidaten und speichert selektiv."""
        for candidate in self._rule_based_candidates(message):
            decision = self._should_store_memory(candidate, message)
            if not decision.get("keep"):
                continue

            item = MemoryItem(
                category=candidate["category"],
                key=candidate["key"],
                value=candidate["value"],
                importance=decision.get("importance", candidate.get("importance", 0.6)),
                confidence=decision.get("confidence", candidate.get("confidence", 0.8)),
                reason=decision.get("reason", candidate.get("reason", "")),
                source="user_message"
            )
            # Use hybrid storage (SQLite + ChromaDB)
            self.store_with_embedding(item)

    def _load_self_model_state(self) -> None:
        item = self._get_self_model_item()
        if item:
            self.self_model_last_updated = item.last_used

    def _mark_self_model_dirty(self, item: MemoryItem) -> None:
        if item.category in {"user_profile", "relationships", "decisions", "patterns"}:
            self.self_model_dirty = True

    def _rule_based_candidates(self, message: str) -> List[Dict[str, Any]]:
        """Regelbasierte Kandidaten-Erkennung."""
        candidates: List[Dict[str, Any]] = []
        text = message.strip()
        lower = text.lower()

        def extract_after(pattern: str) -> Optional[str]:
            if pattern not in lower:
                return None
            idx = lower.find(pattern)
            value = text[idx + len(pattern):].strip()
            for end in [".", ",", "!", "?", "\n"]:
                if end in value:
                    value = value[:value.index(end)]
            return value.strip() or None

        name = extract_after("ich heiße") or extract_after("mein name ist")
        if name:
            candidates.append({
                "category": "user_profile",
                "key": "name",
                "value": name,
                "reason": "identity",
                "importance": 0.9
            })

        location = extract_after("ich wohne in")
        if location:
            candidates.append({
                "category": "user_profile",
                "key": "location",
                "value": location,
                "reason": "identity",
                "importance": 0.7
            })

        work = extract_after("ich arbeite")
        if work:
            candidates.append({
                "category": "user_profile",
                "key": "work",
                "value": work,
                "reason": "identity",
                "importance": 0.7
            })

        preference = extract_after("ich mag") or extract_after("ich bevorzuge")
        if preference:
            candidates.append({
                "category": "user_profile",
                "key": "preference",
                "value": preference,
                "reason": "preference",
                "importance": 0.6
            })

        goal = extract_after("mein ziel ist") or extract_after("ich will")
        if goal:
            candidates.append({
                "category": "user_profile",
                "key": "goal",
                "value": goal,
                "reason": "goal",
                "importance": 0.8
            })

        if "merke dir" in lower or "bitte merke" in lower:
            after = extract_after("merke dir") or extract_after("bitte merke")
            if after:
                candidates.append({
                    "category": "user_profile",
                    "key": f"explicit_note_{hashlib.md5(after.encode()).hexdigest()[:8]}",
                    "value": after,
                    "reason": "explicit_request",
                    "importance": 0.9
                })

        return candidates

    def _should_store_memory(self, candidate: Dict[str, Any], message: str) -> Dict[str, Any]:
        """Kombiniert Rule-Checks mit optionalem LLM-Gate."""
        explicit = candidate.get("reason") == "explicit_request"
        high_importance = candidate.get("importance", 0.0) >= 0.8

        if explicit or high_importance:
            return {"keep": True, "confidence": 0.95, "importance": candidate.get("importance", 0.8)}

        # LLM-Gate für unsichere Kandidaten
        try:
            prompt = {
                "message": message,
                "candidate": {
                    "category": candidate.get("category"),
                    "key": candidate.get("key"),
                    "value": candidate.get("value"),
                    "reason": candidate.get("reason", "")
                }
            }

            response = self._create_chat_completion({
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Du entscheidest, ob eine Information langfristig gespeichert werden soll. "
                            "Speichere nur, wenn sie stabil, nützlich und zukunftsrelevant ist. "
                            "Antworte nur als JSON: {\"keep\": true/false, \"confidence\": 0-1, "
                            "\"importance\": 0-1, \"reason\": \"...\"}."
                        )
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}
                ],
                "max_tokens": 200,
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
            })

            raw = response.choices[0].message.content or ""
            decision = self._parse_json_response(raw)
            if not decision:
                log.warning("Memory-Gate Fehler: Ungültiges JSON")
                return {"keep": False}
            return {
                "keep": bool(decision.get("keep")),
                "confidence": float(decision.get("confidence", 0.5)),
                "importance": float(decision.get("importance", 0.5)),
                "reason": str(decision.get("reason", ""))
            }
        except Exception as e:
            log.warning(f"Memory-Gate Fehler: {e}")
            return {"keep": False}

    def _store_legacy_fact(self, item: MemoryItem):
        """Kompatibilität: speichert zentrale Fakten auch im alten Fakt-Format."""
        legacy_map = {
            "name": ("name", "name"),
            "location": ("info", "location"),
            "work": ("info", "work"),
            "preference": ("preference", "likes"),
            "goal": ("info", "goal")
        }
        if item.key not in legacy_map:
            return

        category, key = legacy_map[item.key]
        fact = Fact(
            category=category,
            key=key,
            value=str(item.value),
            confidence=item.confidence,
            source="memory_schema"
        )
        self.persistent.store_fact(fact)

    # === HYBRID SEARCH METHODS ===
    
    def store_with_embedding(self, item: MemoryItem) -> bool:
        """
        Speichert MemoryItem in SQLite UND ChromaDB.
        
        Synchronisiert strukturierte Daten (SQLite) mit
        semantischen Embeddings (ChromaDB).
        """
        # SQLite speichern
        self.persistent.store_memory_item(item)
        
        # ChromaDB Embedding speichern
        if self.semantic_store and self.semantic_store.is_available():
            self.semantic_store.store_embedding(item)
        
        # Legacy Fact für Kompatibilität
        self._store_legacy_fact(item)
        
        # Self-Model dirty markieren
        self._mark_self_model_dirty(item)
        
        log.info(f"🧠 Memory gespeichert (Hybrid): {item.category}/{item.key}")
        return True
    
    def find_related_memories(
        self,
        query: str,
        n_results: int = 5,
        category_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Hybrid-Suche: Kombiniert semantische (ChromaDB) und Keyword-Suche (FTS5).
        
        Liefert relevante Erinnerungen basierend auf:
        1. Semantischer Ähnlichkeit (Vektor-Distanz)
        2. Keyword-Matches (FTS5 Volltextsuche)
        
        Args:
            query: Suchbegriff oder Frage
            n_results: Maximale Anzahl Ergebnisse
            category_filter: Optional auf Kategorie filtern
        
        Returns:
            Liste von Dictionaries mit content, source, relevance
        """
        results = []
        seen_ids = set()
        
        # 1. Semantische Suche (ChromaDB)
        if self.semantic_store and self.semantic_store.is_available():
            semantic_results = self.semantic_store.find_related_memories(
                query, n_results=n_results, category_filter=category_filter
            )
            for r in semantic_results:
                if r.doc_id not in seen_ids:
                    results.append({
                        "content": r.content,
                        "category": r.category,
                        "importance": r.importance,
                        "relevance": 1.0 - r.distance,  # Convert distance to relevance
                        "source": "semantic",
                        "doc_id": r.doc_id,
                        "key": r.key,
                        "created_at": r.created_at,
                    })
                    seen_ids.add(r.doc_id)
        
        # 2. Keyword-Suche (FTS5 via Markdown Store)
        try:
            md_store = self._get_markdown_store()
            if md_store:
                keyword_results = md_store.search(query, limit=n_results)
                for r in keyword_results:
                    result_key = f"{r.source}_{r.snippet[:20]}"
                    if result_key not in seen_ids:
                        results.append({
                            "content": r.snippet,
                            "category": r.source,
                            "importance": 0.5,
                            "relevance": r.rank,
                            "source": "keyword_fts5",
                            "doc_id": result_key,
                            "key": "",
                            "created_at": "",
                        })
                        seen_ids.add(result_key)
        except Exception as e:
            log.debug(f"FTS5 Suche fehlgeschlagen: {e}")
        
        # Nach Relevanz sortieren
        results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        return results[:n_results]
    
    def get_enhanced_context(self, current_query: str, max_related: int = 3) -> str:
        """
        Baut erweiterten Memory-Kontext mit semantisch relevanten Erinnerungen.
        
        Kombiniert den Basis-Kontext mit thematisch verwandten
        Erinnerungen aus ChromaDB/FTS5.
        """
        base_context = self.get_memory_context()
        
        if not current_query or len(current_query) < 5:
            return base_context
        
        related = self.find_related_memories(current_query, n_results=max_related)
        
        if not related:
            return base_context
        
        related_text = "\n".join([
            f"- [{r['source']}] {r['content'][:200]}"
            for r in related
        ])
        
        return f"{base_context}\n\nRELEVANTE ERINNERUNGEN:\n{related_text}"

    def _normalize_text_for_prompt(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def _truncate_for_budget(self, text: str, max_chars: int) -> str:
        cleaned = self._normalize_text_for_prompt(text)
        if max_chars <= 0:
            return ""
        if len(cleaned) <= max_chars:
            return cleaned
        if max_chars <= 3:
            return cleaned[:max_chars]
        return cleaned[: max_chars - 3].rstrip() + "..."

    def _extract_query_terms(self, query: str) -> List[str]:
        stopwords = {
            "und", "oder", "aber", "eine", "einer", "einem", "einen", "der", "die",
            "das", "den", "dem", "dass", "ist", "sind", "war", "ich", "du", "wir",
            "was", "wie", "wo", "wer", "nach", "mit", "für", "von", "auf", "zu",
            "the", "and", "for", "with", "that", "this", "from", "about",
        }
        terms = []
        for token in re.findall(r"\w{3,}", query.lower()):
            if token not in stopwords and token not in terms:
                terms.append(token)
        return terms

    def _parse_iso_datetime(self, raw: Any) -> Optional[datetime]:
        text = self._normalize_text_for_prompt(raw)
        if not text:
            return None
        try:
            # Support "YYYY-MM-DD HH:MM:SS" und ISO-Strings
            text = text.replace(" ", "T")
            return datetime.fromisoformat(text)
        except Exception:
            return None

    def _time_decay(self, timestamp: Optional[datetime], half_life_hours: float) -> float:
        if timestamp is None:
            return 0.45
        age_hours = max(0.0, (datetime.now() - timestamp).total_seconds() / 3600.0)
        if half_life_hours <= 0:
            return 1.0
        return 0.5 ** (age_hours / half_life_hours)

    def _score_interaction_event(
        self,
        event: Dict[str, Any],
        query_terms: List[str],
    ) -> float:
        haystack = self._normalize_text_for_prompt(
            f"{event.get('user_input', '')} {event.get('assistant_response', '')}"
        ).lower()

        if query_terms:
            matches = sum(1 for token in query_terms if token in haystack)
            semantic_overlap = matches / max(1, len(query_terms))
        else:
            semantic_overlap = 0.35

        event_time = self._parse_iso_datetime(event.get("created_at"))
        recency = self._time_decay(event_time, WORKING_MEMORY_EVENT_HALF_LIFE_HOURS)

        status = self._normalize_text_for_prompt(event.get("status", "")).lower()
        status_boost = {
            "completed": 1.0,
            "cancelled": 0.6,
            "error": 0.4,
        }.get(status, 0.8)

        score = (0.55 * semantic_overlap) + (0.35 * recency) + (0.10 * status_boost)
        return max(0.0, min(1.5, score))

    def _score_related_memory(
        self,
        memory: Dict[str, Any],
        query_terms: List[str],
    ) -> float:
        content = self._normalize_text_for_prompt(memory.get("content", "")).lower()
        relevance = float(memory.get("relevance", 0.0) or 0.0)
        importance = float(memory.get("importance", 0.5) or 0.5)

        if query_terms:
            matches = sum(1 for token in query_terms if token in content)
            semantic_overlap = matches / max(1, len(query_terms))
        else:
            semantic_overlap = 0.2

        created_at = self._parse_iso_datetime(memory.get("created_at"))
        recency = self._time_decay(
            created_at, WORKING_MEMORY_MEMORY_HALF_LIFE_DAYS * 24.0
        )

        source = self._normalize_text_for_prompt(memory.get("source", "")).lower()
        source_boost = 1.0 if source == "semantic" else 0.88

        score = (
            (0.45 * relevance)
            + (0.25 * importance)
            + (0.20 * semantic_overlap)
            + (0.10 * recency)
        ) * source_boost
        return max(0.0, min(2.0, score))

    def _adapt_working_memory_targets(
        self,
        query: str,
        max_recent_events: int,
        max_related: int,
    ) -> Tuple[int, int, Tuple[float, float, float]]:
        lower = query.lower()
        temporal_markers = (
            "eben", "vorhin", "gerade", "zuletzt", "heute", "gestern", "laufend", "recent"
        )
        profile_markers = (
            "präferenz", "pref", "gewohn", "ziel", "goal", "profil", "mag ich", "ich mag"
        )

        if any(marker in lower for marker in temporal_markers):
            recent_target = max_recent_events
            related_target = max(1, max_related - 1)
            shares = (0.56, 0.24, 0.20)
        elif any(marker in lower for marker in profile_markers):
            recent_target = max(1, max_recent_events // 2)
            related_target = max_related
            shares = (0.28, 0.50, 0.22)
        else:
            recent_target = max_recent_events
            related_target = max_related
            shares = (0.42, 0.36, 0.22)

        return recent_target, related_target, shares

    def _build_budgeted_section(self, title: str, lines: List[str], budget: int) -> str:
        if budget < 20 or not lines:
            return ""
        header = f"{title}:\n"
        if len(header) >= budget:
            return ""

        kept: List[str] = []
        used = len(header)
        for raw in lines:
            line = self._normalize_text_for_prompt(raw)
            if not line:
                continue
            remaining = budget - used
            if remaining <= 1:
                break

            if len(line) + 1 <= remaining:
                kept.append(line)
                used += len(line) + 1
                continue

            if remaining > 8:
                kept.append(self._truncate_for_budget(line, remaining - 1))
            break

        if not kept:
            return ""
        return header + "\n".join(kept)

    def build_working_memory_context(
        self,
        current_query: str,
        max_chars: int = WORKING_MEMORY_MAX_CHARS,
        max_related: int = WORKING_MEMORY_MAX_RELATED,
        max_recent_events: int = WORKING_MEMORY_MAX_RECENT_EVENTS,
    ) -> str:
        """
        Baut einen budgetierten Working-Memory-Block für Prompt-Injektion.

        Priorität:
        1) Kurzzeit: jüngste Interaktions-Events
        2) Langzeit: query-relevante Erinnerungen (hybrid search)
        3) Stabil: Self-Model + Behavior Hooks
        """
        query = self._normalize_text_for_prompt(current_query)
        if not query:
            self._last_working_memory_stats = {
                "status": "no_query",
                "query": "",
                "query_terms_count": 0,
                "final_chars": 0,
            }
            return ""

        max_chars = max(600, int(max_chars))
        max_related = max(0, int(max_related))
        max_recent_events = max(0, int(max_recent_events))
        query_terms = self._extract_query_terms(query)
        recent_target, related_target, section_shares = self._adapt_working_memory_targets(
            query, max_recent_events, max_related
        )
        stats: Dict[str, Any] = {
            "status": "building",
            "query": query[:200],
            "query_terms_count": len(query_terms),
            "max_chars": max_chars,
            "max_related": max_related,
            "max_recent_events": max_recent_events,
            "recent_target": recent_target,
            "related_target": related_target,
            "section_shares": {
                "short_term": section_shares[0],
                "long_term": section_shares[1],
                "stable": section_shares[2],
            },
        }

        # --- 1) Kurzzeitkontext aus persistenten Interaktions-Events ---
        event_lines: List[str] = []
        selected_events: List[Dict[str, Any]] = []
        if recent_target > 0:
            recent_events = self.persistent.get_recent_interaction_events(
                limit=max(12, recent_target * 6)
            )
            scored_events: List[Tuple[float, Dict[str, Any]]] = []
            for event in recent_events:
                score = self._score_interaction_event(event, query_terms)
                scored_events.append((score, event))

            scored_events.sort(key=lambda item: item[0], reverse=True)
            selected_events = [item[1] for item in scored_events[:recent_target]]
            selected_events.sort(
                key=lambda ev: self._parse_iso_datetime(ev.get("created_at")) or datetime.min
            )

            for event in selected_events:
                ts = self._normalize_text_for_prompt(event.get("created_at", ""))[:19]
                user_text = self._truncate_for_budget(event.get("user_input", ""), 140)
                assistant_text = self._truncate_for_budget(
                    event.get("assistant_response", ""), 160
                )
                event_lines.append(
                    f"- ({ts}) User: {user_text} | Timus: {assistant_text}"
                )
        stats["selected_recent_events"] = len(event_lines)

        # --- 2) Langzeitkontext: relevante Erinnerungen ---
        related_lines: List[str] = []
        if related_target > 0 and len(query) >= 3:
            related = self.find_related_memories(query, n_results=max(related_target * 4, 6))
            scored_related: List[Tuple[float, Dict[str, Any]]] = []
            for memory in related:
                score = self._score_related_memory(memory, query_terms)
                scored_related.append((score, memory))

            scored_related.sort(key=lambda item: item[0], reverse=True)
            for _, memory in scored_related[:related_target]:
                category = self._normalize_text_for_prompt(memory.get("category", ""))
                source = self._normalize_text_for_prompt(memory.get("source", ""))
                content = self._truncate_for_budget(memory.get("content", ""), 180)
                related_lines.append(f"- [{category}/{source}] {content}")
        stats["selected_related_memories"] = len(related_lines)

        # --- 3) Stabiler Kontext ---
        stable_lines: List[str] = []
        self_model = self._truncate_for_budget(self.get_self_model_prompt(), 350)
        if self_model:
            stable_lines.append(f"Self-Model: {self_model}")

        hooks = [self._normalize_text_for_prompt(h) for h in self.get_behavior_hooks()[:4]]
        if hooks:
            stable_lines.append("Hooks: " + " | ".join(hooks))

        if query_terms and selected_events:
            repeated = []
            for token in query_terms:
                count = 0
                for ev in selected_events:
                    text = self._normalize_text_for_prompt(ev.get("user_input", "")).lower()
                    if token in text:
                        count += 1
                if count >= 2:
                    repeated.append(token)
            if repeated:
                stable_lines.append("Aktive Themen: " + ", ".join(repeated[:5]))
        stats["stable_lines"] = len(stable_lines)

        # Budgetiert zusammensetzen
        sections: List[Tuple[str, List[str]]] = [
            ("KURZZEITKONTEXT", event_lines),
            ("LANGZEITKONTEXT", related_lines),
            ("STABILER_KONTEXT", stable_lines),
        ]
        if not any(lines for _, lines in sections):
            stats["status"] = "no_sections"
            stats["generated_sections"] = []
            stats["final_chars"] = 0
            self._last_working_memory_stats = stats
            return ""

        header = (
            "WORKING_MEMORY_CONTEXT\n"
            "Nutze nur relevante Teile. Bei Konflikt gilt die aktuelle Nutzeranfrage."
        )
        blocks: List[str] = []
        used_chars = len(header)
        share_map = {
            "KURZZEITKONTEXT": section_shares[0],
            "LANGZEITKONTEXT": section_shares[1],
            "STABILER_KONTEXT": section_shares[2],
        }
        generated_sections: List[str] = []

        for title, lines in sections:
            if not lines:
                continue
            remaining = max_chars - used_chars
            if remaining <= 0:
                break

            section_budget = int(max_chars * share_map.get(title, 0.33))
            section_budget = max(120, min(remaining, section_budget))
            block = self._build_budgeted_section(title, lines, section_budget)
            if not block:
                continue

            separator_len = 2  # "\n\n"
            if used_chars + separator_len + len(block) > max_chars:
                tight_budget = max_chars - used_chars - separator_len
                block = self._truncate_for_budget(block, tight_budget)
                if not block:
                    continue

            blocks.append(block)
            generated_sections.append(title)
            used_chars += separator_len + len(block)

        if not blocks:
            stats["status"] = "budget_exhausted"
            stats["generated_sections"] = []
            stats["final_chars"] = 0
            self._last_working_memory_stats = stats
            return ""

        final_text = header + "".join(f"\n\n{block}" for block in blocks)
        if len(final_text) > max_chars:
            final_text = self._truncate_for_budget(final_text, max_chars)
        stats["status"] = "ok"
        stats["generated_sections"] = generated_sections
        stats["final_chars"] = len(final_text)
        self._last_working_memory_stats = stats
        return final_text.strip()
    
    def sync_to_markdown(self) -> bool:
        """
        Synchronisiert SQLite/ChromaDB Daten in Markdown-Dateien.
        
        Erstellt menschenlesbare Version der strukturierten Daten
        für manuelles Editieren und Versionierung (Git).
        """
        try:
            md_store = self._get_markdown_store()
            if not md_store:
                return False
            
            # User Profile aus MemoryItems extrahieren
            profile_items = self.persistent.get_memory_items("user_profile")
            profile_dict = {}
            for item in profile_items:
                if item.key in ["name", "location"]:
                    profile_dict[item.key] = str(item.value)
                elif item.key == "preference":
                    profile_dict.setdefault("preferences", {})[item.key] = str(item.value)
                elif item.key == "goal":
                    profile_dict.setdefault("goals", []).append(str(item.value))
            
            if profile_dict:
                md_store.update_user_profile(profile_dict)
            
            # Patterns als Behavior Hooks
            patterns = self.persistent.get_memory_items("patterns")
            if patterns:
                hooks = [str(p.value) for p in patterns[:10]]
                md_store.update_soul_profile({"behavior_hooks": hooks})
            
            # Memory Items als MEMORY.md Einträge
            from memory.markdown_store.store import MemoryEntry
            all_items = self.persistent.get_all_memory_items()
            for item in all_items:
                if item.importance >= 0.7:
                    md_store.add_memory(MemoryEntry(
                        category=item.category,
                        content=str(item.value)[:500],
                        importance=item.importance,
                        source=item.source
                    ))
            
            log.info("✅ Memory → Markdown Sync abgeschlossen")
            return True
        except Exception as e:
            log.error(f"Markdown Sync fehlgeschlagen: {e}")
            return False
    
    def sync_from_markdown(self) -> bool:
        """
        Liest Markdown-Dateien und aktualisiert SQLite/ChromaDB.
        
        Ermöglicht manuelles Editieren der Memory-Dateien
        mit automatischer Synchronisation zurück in die strukturierten Stores.
        """
        try:
            md_store = self._get_markdown_store()
            if not md_store:
                return False
            
            # User Profile lesen
            user = md_store.read_user_profile()
            if user.name:
                self.store_with_embedding(MemoryItem(
                    category="user_profile",
                    key="name",
                    value=user.name,
                    importance=0.9,
                    reason="markdown_sync"
                ))
            if user.location:
                self.store_with_embedding(MemoryItem(
                    category="user_profile",
                    key="location",
                    value=user.location,
                    importance=0.7,
                    reason="markdown_sync"
                ))
            for goal in user.goals:
                self.store_with_embedding(MemoryItem(
                    category="user_profile",
                    key=f"goal_{hashlib.md5(goal.encode()).hexdigest()[:6]}",
                    value=goal,
                    importance=0.8,
                    reason="markdown_sync"
                ))
            
            # Soul/Behavior Hooks
            soul = md_store.read_soul_profile()
            for hook in soul.behavior_hooks:
                self.store_with_embedding(MemoryItem(
                    category="patterns",
                    key=f"hook_{hashlib.md5(hook.encode()).hexdigest()[:6]}",
                    value=hook,
                    importance=0.7,
                    reason="markdown_sync"
                ))
            
            # Memory Entries
            memories = md_store.read_memories()
            for m in memories:
                self.store_with_embedding(MemoryItem(
                    category=m.category,
                    key=f"md_{hashlib.md5(m.content.encode()).hexdigest()[:8]}",
                    value=m.content,
                    importance=m.importance,
                    reason="markdown_sync",
                    source=m.source
                ))
            
            log.info("✅ Markdown → Memory Sync abgeschlossen")
            return True
        except Exception as e:
            log.error(f"Markdown → Memory Sync fehlgeschlagen: {e}")
            return False

    def _get_self_model_item(self) -> Optional[MemoryItem]:
        items = self.persistent.get_memory_items("self_model")
        for item in items:
            if item.key == "prompt":
                return item
        return None

    def _format_memory_items(self, items: List[MemoryItem], limit: int = 8) -> List[str]:
        lines = []
        for item in items[:limit]:
            lines.append(f"{item.key}: {item.value}")
        return lines

    def get_self_model_prompt(self) -> str:
        item = self._get_self_model_item()
        if not item:
            return ""

        data = item.value if isinstance(item.value, dict) else None
        if not data:
            return str(item.value)

        parts = []
        summary = data.get("summary")
        if summary:
            parts.append(summary)

        preferences = data.get("preferences") or []
        if preferences:
            parts.append("Präferenzen: " + ", ".join(preferences))

        goals = data.get("goals") or []
        if goals:
            parts.append("Ziele: " + ", ".join(goals))

        constraints = data.get("constraints") or []
        if constraints:
            parts.append("Constraints: " + ", ".join(constraints))

        return "\n".join(parts).strip()

    def get_behavior_hooks(self) -> List[str]:
        item = self._get_self_model_item()
        if item and isinstance(item.value, dict):
            hooks = item.value.get("behavior_hooks") or []
            return [str(h) for h in hooks if str(h).strip()]

        hooks: List[str] = []
        user_profile = self.persistent.get_memory_items("user_profile")
        patterns = self.persistent.get_memory_items("patterns")

        def add_hook(text: str):
            if text and text not in hooks:
                hooks.append(text)

        for item in user_profile:
            text = str(item.value).lower()
            if "json" in text or "struktur" in text:
                add_hook("Antworten strukturiert (JSON/Listen).")
            if "kurz" in text or "knapp" in text or "prägnant" in text:
                add_hook("Antworten kurz und präzise.")
            if "deutsch" in text:
                add_hook("Auf Deutsch antworten.")
            if "quelle" in text or "beleg" in text:
                add_hook("Wichtige Aussagen mit Quellen belegen.")
            if "halluz" in text or "verif" in text:
                add_hook("Keine Vermutungen; nur verifizierte Aussagen.")
            if item.key == "goal" and item.value:
                add_hook(f"Aktives Ziel beachten: {item.value}")

        for item in patterns:
            text = f"{item.key} {item.value}".lower()
            if "halluz" in text or "falsche" in text:
                add_hook("Antworten müssen prüfbar und belegt sein.")
            if "struktur" in text:
                add_hook("Strukturiert antworten.")

        return hooks

    def _should_update_self_model(self) -> bool:
        if not self.self_model_last_updated:
            return True
        if not self.self_model_dirty and len(self.session.messages) < SELF_MODEL_MIN_MESSAGES:
            return False

        min_interval = timedelta(hours=SELF_MODEL_UPDATE_INTERVAL_HOURS)
        return datetime.now() - self.self_model_last_updated >= min_interval

    async def update_self_model(self, force: bool = False) -> Optional[Dict[str, Any]]:
        if not force and not self._should_update_self_model():
            return None

        payload = {
            "user_profile": self._format_memory_items(self.persistent.get_memory_items("user_profile"), 10),
            "relationships": self._format_memory_items(self.persistent.get_memory_items("relationships"), 5),
            "decisions": self._format_memory_items(self.persistent.get_memory_items("decisions"), 5),
            "patterns": self._format_memory_items(self.persistent.get_memory_items("patterns"), 5),
            "recent_summaries": [s.summary for s in self.persistent.get_recent_summaries(3)],
            "recent_messages": [m.to_dict() for m in self.session.get_recent_messages(6)]
        }

        try:
            response = self._create_chat_completion({
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Erstelle ein kurzes, stabiles Self-Model über den Nutzer. "
                            "Antworte als JSON mit Feldern: summary (max 4 Sätze), preferences (Liste), "
                            "goals (Liste), constraints (Liste), behavior_hooks (Liste konkreter Regeln). "
                            "Schreibe auf Deutsch und füge nur belastbare Infos ein."
                        )
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
                ],
                "max_tokens": 400,
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
            })

            raw = response.choices[0].message.content or ""
            data = self._parse_json_response(raw)
            if not data:
                log.warning("Self-Model Update fehlgeschlagen: Ungültiges JSON")
                return None
            item = MemoryItem(
                category="self_model",
                key="prompt",
                value={
                    "summary": data.get("summary", ""),
                    "preferences": data.get("preferences", []),
                    "goals": data.get("goals", []),
                    "constraints": data.get("constraints", []),
                    "behavior_hooks": data.get("behavior_hooks", []),
                    "updated_at": datetime.now().isoformat()
                },
                importance=1.0,
                confidence=0.9,
                reason="self_model_update",
                source="self_model"
            )
            self.persistent.store_memory_item(item)
            self.self_model_last_updated = datetime.now()
            self.self_model_dirty = False
            return item.value
        except Exception as e:
            log.warning(f"Self-Model Update fehlgeschlagen: {e}")
            return None
    
    def get_memory_context(self) -> str:
        """
        Baut den Memory-Kontext für den Prompt.
        Kombiniert Session Memory und relevante Fakten.
        """
        context_parts = []

        # 0. Self-Model + Hooks
        self_model = self.get_self_model_prompt()
        if self_model:
            context_parts.append("SELF_MODEL:\n" + self_model)

        hooks = self.get_behavior_hooks()
        if hooks:
            hook_lines = "\n".join([f"- {hook}" for hook in hooks])
            context_parts.append("BEHAVIOR_HOOKS:\n" + hook_lines)

        # 1. Strukturierte MemoryItems
        structured = []
        user_profile = self.persistent.get_memory_items("user_profile")
        if user_profile:
            lines = [f"- {item.key}: {item.value}" for item in user_profile[:8]]
            structured.append("USER_PROFILE:\n" + "\n".join(lines))

        relationships = self.persistent.get_memory_items("relationships")
        if relationships:
            lines = [f"- {item.key}: {item.value}" for item in relationships[:5]]
            structured.append("RELATIONSHIPS:\n" + "\n".join(lines))

        decisions = self.persistent.get_memory_items("decisions")
        if decisions:
            lines = [f"- {item.key}: {item.value}" for item in decisions[:5]]
            structured.append("DECISIONS:\n" + "\n".join(lines))

        patterns = self.persistent.get_memory_items("patterns")
        if patterns:
            lines = [f"- {item.key}: {item.value}" for item in patterns[:5]]
            structured.append("PATTERNS:\n" + "\n".join(lines))

        if structured:
            context_parts.append("STRUKTURIERTE MEMORY:\n" + "\n\n".join(structured))
        
        # 2. Benutzer-Fakten
        facts = self.persistent.get_all_facts()
        if facts:
            fact_lines = []
            for f in facts[:10]:  # Max 10 Fakten
                fact_lines.append(f"- {f.key}: {f.value}")
            
            context_parts.append(
                "BEKANNTE FAKTEN ÜBER DEN BENUTZER:\n" + "\n".join(fact_lines)
            )
        
        # 3. Letzte Zusammenfassungen
        summaries = self.persistent.get_recent_summaries(2)
        if summaries:
            summary_text = "\n".join([s.summary for s in summaries])
            context_parts.append(
                f"FRÜHERE GESPRÄCHE:\n{summary_text}"
            )
        
        # 4. Aktuelle Session
        session_context = self.session.get_context_string()
        if session_context:
            context_parts.append(
                f"AKTUELLE KONVERSATION:\n{session_context}"
            )
        
        # 5. Entitäts-Kontext
        if self.session.entities:
            entity_lines = [f"- '{k}' bezieht sich auf '{v}'" 
                          for k, v in self.session.entities.items()]
            context_parts.append(
                "AKTUELLE REFERENZEN:\n" + "\n".join(entity_lines)
            )
        
        return "\n\n".join(context_parts)
    
    async def summarize_session(self) -> Optional[ConversationSummary]:
        """Fasst die aktuelle Session zusammen und speichert sie."""
        if len(self.session.messages) < 4:
            return None
        
        messages_text = self.session.get_context_string()
        
        try:
            response = self._create_chat_completion({
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": """Fasse das folgende Gespräch kurz zusammen.
Extrahiere auch wichtige Fakten über den Benutzer.

Antworte im JSON-Format:
{
    "summary": "Kurze Zusammenfassung des Gesprächs",
    "topics": ["Thema1", "Thema2"],
    "user_facts": ["Fakt1", "Fakt2"]
}"""
                    },
                    {
                        "role": "user",
                        "content": messages_text
                    }
                ],
                "max_tokens": 500,
                "response_format": {"type": "json_object"}
            })
            
            result = self._parse_json_response(response.choices[0].message.content or "")
            if not result:
                log.error("Fehler bei Zusammenfassung: Ungültiges JSON")
                return None
            
            summary = ConversationSummary(
                summary=result.get("summary", ""),
                topics=result.get("topics", []),
                facts_extracted=result.get("user_facts", []),
                message_count=len(self.session.messages)
            )
            
            self.persistent.store_summary(summary)
            
            # Fakten speichern
            for fact_text in result.get("user_facts", []):
                fact = Fact(
                    category="extracted",
                    key=f"fact_{hashlib.md5(fact_text.encode()).hexdigest()[:8]}",
                    value=fact_text,
                    source="summarization"
                )
                self.persistent.store_fact(fact)
            
            log.info(f"📝 Session zusammengefasst: {len(self.session.messages)} Nachrichten")
            return summary
            
        except Exception as e:
            log.error(f"Fehler bei Zusammenfassung: {e}")
            return None
    
    def save_session(self):
        """Speichert die aktuelle Session in der Datenbank."""
        if self.session.messages:
            self.persistent.store_conversation(
                self.session_id,
                self.session.messages
            )
    
    def end_session(self):
        """Beendet die Session, fasst zusammen und speichert."""
        import asyncio
        
        # Zusammenfassen
        asyncio.run(self.summarize_session())

        # Self-Model aktualisieren
        asyncio.run(self.update_self_model())
        
        # Speichern
        self.save_session()
        
        # Session leeren
        self.session.clear()
        
        # Neue Session-ID
        self.session_id = hashlib.md5(
            datetime.now().isoformat().encode()
        ).hexdigest()[:12]
    
    def remember(self, key: str, value: str, category: str = "user_stated"):
        """Explizit etwas merken."""
        fact = Fact(
            category=category,
            key=key,
            value=value,
            source="explicit"
        )
        self.persistent.store_fact(fact)
        log.info(f"✅ Gemerkt: {key} = {value}")
    
    def recall(self, key: str) -> Optional[str]:
        """Explizit etwas abrufen."""
        # Zuerst in Session suchen
        for msg in reversed(self.session.messages):
            if key.lower() in msg.content.lower():
                return msg.content
        
        # Dann in Fakten
        for category in ["user_stated", "name", "preference", "info", "extracted"]:
            fact = self.persistent.get_fact(category, key)
            if fact:
                return fact.value
        
        return None
    
    def forget(self, key: str):
        """Explizit etwas vergessen."""
        for category in ["user_stated", "name", "preference", "info", "extracted"]:
            self.persistent.delete_fact(category, key)
        log.info(f"🗑️ Vergessen: {key}")
    
    def get_stats(self) -> Dict:
        """Gibt Statistiken über das Gedächtnis zurück."""
        facts = self.persistent.get_all_facts()
        summaries = self.persistent.get_recent_summaries(100)
        
        return {
            "session_messages": len(self.session.messages),
            "total_facts": len(facts),
            "total_summaries": len(summaries),
            "total_interaction_events": self.persistent.count_interaction_events(),
            "session_start": self.session.session_start.isoformat(),
            "entities_tracked": len(self.session.entities)
        }


# Globale Instanz
memory_manager = MemoryManager()


# === HILFSFUNKTIONEN ===

def get_memory_context() -> str:
    """Shortcut für Memory-Kontext."""
    return memory_manager.get_memory_context()


def get_self_model_prompt() -> str:
    """Shortcut für Self-Model Prompt."""
    return memory_manager.get_self_model_prompt()


def get_behavior_hooks() -> List[str]:
    """Shortcut für Behavior Hooks."""
    return memory_manager.get_behavior_hooks()


def add_to_memory(user_input: str, response: str):
    """Shortcut für Interaktion hinzufügen."""
    memory_manager.add_interaction(user_input, response)


def remember(key: str, value: str):
    """Shortcut für etwas merken."""
    memory_manager.remember(key, value)


def recall(key: str) -> Optional[str]:
    """Shortcut für etwas abrufen."""
    return memory_manager.recall(key)


def end_session():
    """Shortcut für Session beenden."""
    memory_manager.end_session()


# === NEW: Hybrid Search Shortcuts ===

def find_related_memories(query: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """Shortcut für Hybrid-Suche (ChromaDB + FTS5)."""
    return memory_manager.find_related_memories(query, n_results)


def get_enhanced_context(current_query: str) -> str:
    """Shortcut für erweiterten Kontext mit semantischer Suche."""
    return memory_manager.get_enhanced_context(current_query)


def get_working_memory_context(
    current_query: str,
    max_chars: int = WORKING_MEMORY_MAX_CHARS,
    max_related: int = WORKING_MEMORY_MAX_RELATED,
    max_recent_events: int = WORKING_MEMORY_MAX_RECENT_EVENTS,
) -> str:
    """Shortcut für budgetierten Working-Memory-Kontext."""
    return memory_manager.build_working_memory_context(
        current_query=current_query,
        max_chars=max_chars,
        max_related=max_related,
        max_recent_events=max_recent_events,
    )


def sync_memory_to_markdown() -> bool:
    """Shortcut für Memory → Markdown Sync."""
    return memory_manager.sync_to_markdown()


def sync_markdown_to_memory() -> bool:
    """Shortcut für Markdown → Memory Sync."""
    return memory_manager.sync_from_markdown()


def store_memory_item(item: MemoryItem) -> bool:
    """Shortcut für Hybrid-Speicherung (SQLite + ChromaDB)."""
    return memory_manager.store_with_embedding(item)

# memory/memory_system.py
"""
Timus Memory System v1.0

Features:
- Session Memory (aktuelle Konversation)
- Persistent Memory (SQLite Datenbank)
- Fact Extraction (extrahiert Fakten aus Gesprächen)
- Conversation Summarization (fasst alte Gespräche zusammen)
- Semantic Retrieval (findet relevante Erinnerungen)
"""

import os
import json
import sqlite3
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("memory_system")

# Konfiguration
MEMORY_DB_PATH = Path.home() / "dev" / "timus" / "data" / "timus_memory.db"
MAX_SESSION_MESSAGES = 20  # Letzte N Nachrichten im Kontext
MAX_CONTEXT_TOKENS = 2000  # Max Tokens für Memory-Kontext
SUMMARIZE_THRESHOLD = 10  # Nach N Nachrichten zusammenfassen


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
                
                CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
                CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);
                CREATE INDEX IF NOT EXISTS idx_summaries_created ON summaries(created_at);
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


class MemoryManager:
    """
    Hauptklasse für das Memory-System.
    Kombiniert Session und Persistent Memory.
    """
    
    def __init__(self):
        self.session = SessionMemory()
        self.persistent = PersistentMemory()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.session_id = hashlib.md5(
            datetime.now().isoformat().encode()
        ).hexdigest()[:12]
    
    def add_interaction(self, user_input: str, assistant_response: str):
        """Fügt eine Interaktion hinzu und extrahiert Fakten."""
        self.session.add_message("user", user_input)
        self.session.add_message("assistant", assistant_response)
        
        # Asynchron Fakten extrahieren (optional)
        self._extract_facts_from_message(user_input)
    
    def _extract_facts_from_message(self, message: str):
        """Extrahiert Fakten aus einer Nachricht."""
        # Einfache Muster-Erkennung
        patterns = [
            ("name", "ich heiße", "name"),
            ("name", "mein name ist", "name"),
            ("preference", "ich mag", "likes"),
            ("preference", "ich bevorzuge", "prefers"),
            ("info", "ich bin", "identity"),
            ("info", "ich wohne in", "location"),
            ("info", "ich arbeite", "work"),
        ]
        
        message_lower = message.lower()
        
        for category, pattern, key in patterns:
            if pattern in message_lower:
                # Extrahiere den Wert nach dem Muster
                idx = message_lower.find(pattern)
                value = message[idx + len(pattern):].strip()
                # Bis zum nächsten Satzzeichen oder Ende
                for end in [".", ",", "!", "?", "\n"]:
                    if end in value:
                        value = value[:value.index(end)]
                
                if value:
                    fact = Fact(
                        category=category,
                        key=key,
                        value=value.strip(),
                        source="user_message"
                    )
                    self.persistent.store_fact(fact)
                    log.info(f"📝 Fakt gespeichert: {category}/{key} = {value}")
    
    def get_memory_context(self) -> str:
        """
        Baut den Memory-Kontext für den Prompt.
        Kombiniert Session Memory und relevante Fakten.
        """
        context_parts = []
        
        # 1. Benutzer-Fakten
        facts = self.persistent.get_all_facts()
        if facts:
            fact_lines = []
            for f in facts[:10]:  # Max 10 Fakten
                fact_lines.append(f"- {f.key}: {f.value}")
            
            context_parts.append(
                "BEKANNTE FAKTEN ÜBER DEN BENUTZER:\n" + "\n".join(fact_lines)
            )
        
        # 2. Letzte Zusammenfassungen
        summaries = self.persistent.get_recent_summaries(2)
        if summaries:
            summary_text = "\n".join([s.summary for s in summaries])
            context_parts.append(
                f"FRÜHERE GESPRÄCHE:\n{summary_text}"
            )
        
        # 3. Aktuelle Session
        session_context = self.session.get_context_string()
        if session_context:
            context_parts.append(
                f"AKTUELLE KONVERSATION:\n{session_context}"
            )
        
        # 4. Entitäts-Kontext
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
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
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
                max_tokens=500
            )
            
            result = json.loads(response.choices[0].message.content)
            
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
            "session_start": self.session.session_start.isoformat(),
            "entities_tracked": len(self.session.entities)
        }


# Globale Instanz
memory_manager = MemoryManager()


# === HILFSFUNKTIONEN ===

def get_memory_context() -> str:
    """Shortcut für Memory-Kontext."""
    return memory_manager.get_memory_context()


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

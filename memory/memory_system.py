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
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from openai import OpenAI
from utils.openai_compat import prepare_openai_params
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("memory_system")

# Konfiguration
MEMORY_DB_PATH = Path.home() / "dev" / "timus" / "data" / "timus_memory.db"
MAX_SESSION_MESSAGES = 20  # Letzte N Nachrichten im Kontext
MAX_CONTEXT_TOKENS = 2000  # Max Tokens für Memory-Kontext
SUMMARIZE_THRESHOLD = 10  # Nach N Nachrichten zusammenfassen
SELF_MODEL_MIN_MESSAGES = 6
SELF_MODEL_UPDATE_INTERVAL_HOURS = 12


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
        self.self_model_last_updated: Optional[datetime] = None
        self.self_model_dirty = False
        self._load_self_model_state()

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
            self.persistent.store_memory_item(item)
            self._store_legacy_fact(item)
            self._mark_self_model_dirty(item)
            log.info(f"🧠 Memory gespeichert: {item.category}/{item.key}")

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

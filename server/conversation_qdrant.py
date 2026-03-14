"""Semantic conversation recall for longer Timus chat sessions."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from memory.qdrant_provider import QdrantProvider, normalize_qdrant_mode

log = logging.getLogger("conversation_qdrant")

_STORE_LOCK = threading.Lock()
_STORE: QdrantProvider | None = None
_STORE_FAILED = False


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    explicit = os.getenv("TIMUS_CHAT_QDRANT_ENABLED")
    if explicit is not None:
        return _truthy_env("TIMUS_CHAT_QDRANT_ENABLED", default=False)
    return os.getenv("MEMORY_BACKEND", "chromadb").lower() == "qdrant"


def _collection_name() -> str:
    return str(os.getenv("TIMUS_CHAT_QDRANT_COLLECTION") or "timus_conversations").strip()


def _storage_path() -> Path:
    raw = str(os.getenv("TIMUS_CHAT_QDRANT_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    default_qdrant_path = str(os.getenv("QDRANT_PATH") or "./data/qdrant_db").strip()
    base = Path(default_qdrant_path).expanduser()
    if base.name == "qdrant_db":
        return base.parent / "qdrant_chat"
    return base / "chat"


def _max_recall() -> int:
    raw = str(os.getenv("TIMUS_CHAT_QDRANT_MAX_RECALL") or "4").strip()
    try:
        return max(1, min(int(raw), 8))
    except (TypeError, ValueError):
        return 4


def _get_store() -> QdrantProvider | None:
    global _STORE, _STORE_FAILED
    if _STORE is not None:
        return _STORE
    if _STORE_FAILED or not is_enabled():
        return None

    with _STORE_LOCK:
        if _STORE is not None:
            return _STORE
        if _STORE_FAILED or not is_enabled():
            return None
        try:
            mode = normalize_qdrant_mode(os.getenv("QDRANT_MODE"))
            kwargs: dict[str, Any] = {"collection_name": _collection_name(), "mode": mode}
            if mode == "embedded":
                kwargs["path"] = _storage_path()
            store = QdrantProvider(**kwargs)
            if not store.is_available():
                log.warning(
                    "Conversation-Qdrant deaktiviert: mode=%s endpoint=%s error=%s",
                    store.mode,
                    store.endpoint,
                    store.last_error,
                )
                _STORE_FAILED = True
                return None
            if store._get_embedding_fn() is None:
                log.warning("Conversation-Qdrant deaktiviert: kein Embedding-Provider verfügbar")
                _STORE_FAILED = True
                return None
            _STORE = store
            return _STORE
        except Exception as exc:
            log.warning("Conversation-Qdrant Initialisierung fehlgeschlagen: %s", exc)
            _STORE_FAILED = True
            return None


def store_chat_turn(
    *,
    session_id: str,
    role: str,
    text: str,
    ts: str,
    agent: str = "",
) -> None:
    store = _get_store()
    payload_text = str(text or "").strip()
    if store is None or not payload_text:
        return

    doc_id = f"chat_turn:{session_id}:{ts}:{role}:{agent or 'none'}"
    metadata = {
        "record_type": "chat_turn",
        "session_id": session_id,
        "role": role,
        "agent": agent,
        "ts": ts,
    }
    try:
        store.upsert(ids=[doc_id], documents=[payload_text], metadatas=[metadata])
    except Exception as exc:
        log.warning("Conversation-Qdrant store fehlgeschlagen: %s", exc)


def recall_chat_turns(
    *,
    session_id: str,
    query: str,
    exclude_texts: list[str] | None = None,
) -> list[dict[str, Any]]:
    store = _get_store()
    query_text = str(query or "").strip()
    if store is None or not query_text:
        return []

    excludes = {str(text or "").strip() for text in (exclude_texts or []) if str(text or "").strip()}
    where = {
        "$and": [
            {"record_type": "chat_turn"},
            {"session_id": session_id},
        ]
    }
    wanted = _max_recall()
    try:
        results = store.query(query_texts=[query_text], n_results=max(4, wanted + len(excludes) + 2), where=where)
    except Exception as exc:
        log.warning("Conversation-Qdrant recall fehlgeschlagen: %s", exc)
        return []

    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    recalled: list[dict[str, Any]] = []
    seen_texts: set[str] = set()
    for idx, doc_id in enumerate(ids):
        text = str(documents[idx] if idx < len(documents) else "").strip()
        if not text or text in excludes or text in seen_texts:
            continue
        meta = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
        recalled.append(
            {
                "doc_id": str(doc_id),
                "text": text[:320],
                "role": str(meta.get("role") or "").strip(),
                "agent": str(meta.get("agent") or "").strip(),
                "ts": str(meta.get("ts") or "").strip(),
                "distance": float(distances[idx]) if idx < len(distances) else 0.0,
            }
        )
        seen_texts.add(text)
        if len(recalled) >= wanted:
            break
    return recalled

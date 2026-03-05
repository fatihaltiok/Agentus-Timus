"""
memory/qdrant_provider.py — M16: Qdrant Drop-in für ChromaDB

Lokaler Qdrant-Client (kein Server nötig, Rust-Core) als Ersatz für ChromaDB.
Interface ist kompatibel mit SemanticMemoryStore (duck typing).

ENV:
  MEMORY_BACKEND=qdrant
  QDRANT_PATH=./data/qdrant_db
  QDRANT_COLLECTION=timus_memory
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("QdrantProvider")

QDRANT_PATH = Path(os.getenv("QDRANT_PATH", "./data/qdrant_db"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "timus_memory")
VECTOR_SIZE = 384  # sentence-transformers/all-MiniLM-L6-v2


class QdrantProvider:
    """
    Drop-in Ersatz für ChromaDB Collection-Interface.

    Unterstützte Methoden (ChromaDB-kompatibel):
      add(ids, documents, metadatas, embeddings)
      query(query_embeddings, n_results, where)
      get(ids, where, limit)
      delete(ids, where)
      count()

    Named Vectors: "content" (sentence-transformers embedding)
    Payload-Filter: importance >= threshold, agent_type == filter
    """

    def __init__(
        self,
        path: Path = QDRANT_PATH,
        collection_name: str = QDRANT_COLLECTION,
    ):
        self._path = Path(path)
        self._collection = collection_name
        self._client = None
        self._embedding_fn = None
        self._init()

    def _init(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._path.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(self._path))

            # Collection anlegen falls nicht vorhanden
            existing = [c.name for c in self._client.get_collections().collections]
            if self._collection not in existing:
                self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config={"content": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)},
                )
                log.info("Qdrant Collection '%s' angelegt", self._collection)
            else:
                log.info("Qdrant Collection '%s' geladen", self._collection)
        except ImportError:
            log.warning("qdrant-client nicht installiert. Installieren: pip install qdrant-client")
            self._client = None
        except Exception as e:
            log.error("Qdrant Initialisierung fehlgeschlagen: %s", e)
            self._client = None

    def _get_embedding_fn(self):
        if self._embedding_fn is None:
            try:
                from utils.embedding_provider import get_embedding_function
                self._embedding_fn = get_embedding_function()
            except Exception:
                self._embedding_fn = None
        return self._embedding_fn

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """Embeddings für eine Liste von Texten generieren."""
        fn = self._get_embedding_fn()
        if fn is None:
            # Fallback: Null-Vektor (für Tests ohne embedding_provider)
            return [[0.0] * VECTOR_SIZE for _ in texts]
        try:
            return fn(texts)
        except Exception as e:
            log.warning("Embedding fehlgeschlagen: %s", e)
            return [[0.0] * VECTOR_SIZE for _ in texts]

    # ------------------------------------------------------------------
    # ChromaDB-kompatibles Interface
    # ------------------------------------------------------------------

    def add(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
        """Fügt Dokumente hinzu (ChromaDB-kompatibel)."""
        if self._client is None:
            log.warning("Qdrant nicht verfügbar — add() ignoriert")
            return

        try:
            from qdrant_client.models import PointStruct

            docs = documents or [""] * len(ids)
            metas = metadatas or [{}] * len(ids)

            if embeddings is None:
                embeddings = self._embed(docs)

            points = []
            for i, doc_id in enumerate(ids):
                payload = dict(metas[i]) if metas[i] else {}
                payload["document"] = docs[i]
                payload["_id"] = doc_id

                points.append(PointStruct(
                    id=self._to_qdrant_id(doc_id),
                    vector={"content": embeddings[i]},
                    payload=payload,
                ))

            self._client.upsert(
                collection_name=self._collection,
                points=points,
            )
            log.debug("Qdrant: %d Punkte hinzugefügt", len(points))
        except Exception as e:
            log.error("Qdrant add() fehlgeschlagen: %s", e)

    def query(
        self,
        query_embeddings: Optional[List[List[float]]] = None,
        query_texts: Optional[List[str]] = None,
        n_results: int = 5,
        where: Optional[Dict] = None,
    ) -> Dict:
        """Semantische Suche (ChromaDB-kompatibel)."""
        if self._client is None:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

            # Embedding aus query_texts falls query_embeddings fehlt
            if query_embeddings is None and query_texts:
                query_embeddings = self._embed(query_texts)
            if not query_embeddings:
                return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

            qdrant_filter = self._build_filter(where) if where else None

            results = self._client.search(
                collection_name=self._collection,
                query_vector=("content", query_embeddings[0]),
                limit=max(1, n_results),
                query_filter=qdrant_filter,
                with_payload=True,
            )

            ids, docs, metas, scores = [], [], [], []
            for hit in results:
                payload = hit.payload or {}
                ids.append(payload.get("_id", str(hit.id)))
                docs.append(payload.get("document", ""))
                meta = {k: v for k, v in payload.items() if k not in ("document", "_id")}
                metas.append(meta)
                scores.append(1.0 - hit.score)  # Cosine Distance

            return {"ids": [ids], "documents": [docs], "metadatas": [metas], "distances": [scores]}
        except Exception as e:
            log.error("Qdrant query() fehlgeschlagen: %s", e)
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    def get(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict] = None,
        limit: Optional[int] = None,
    ) -> Dict:
        """Abruf nach IDs oder Filter (ChromaDB-kompatibel)."""
        if self._client is None:
            return {"ids": [], "documents": [], "metadatas": []}

        try:
            from qdrant_client.models import Filter, ScrollRequest

            if ids:
                qdrant_ids = [self._to_qdrant_id(i) for i in ids]
                points = self._client.retrieve(
                    collection_name=self._collection,
                    ids=qdrant_ids,
                    with_payload=True,
                )
            else:
                qdrant_filter = self._build_filter(where) if where else None
                scroll_limit = max(1, limit or 100)
                points, _ = self._client.scroll(
                    collection_name=self._collection,
                    scroll_filter=qdrant_filter,
                    limit=scroll_limit,
                    with_payload=True,
                )

            result_ids, result_docs, result_metas = [], [], []
            for p in points:
                payload = p.payload or {}
                result_ids.append(payload.get("_id", str(p.id)))
                result_docs.append(payload.get("document", ""))
                meta = {k: v for k, v in payload.items() if k not in ("document", "_id")}
                result_metas.append(meta)

            return {"ids": result_ids, "documents": result_docs, "metadatas": result_metas}
        except Exception as e:
            log.error("Qdrant get() fehlgeschlagen: %s", e)
            return {"ids": [], "documents": [], "metadatas": []}

    def delete(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict] = None,
    ) -> None:
        """Löscht Punkte nach IDs oder Filter."""
        if self._client is None:
            return
        try:
            from qdrant_client.models import Filter, PointIdsList

            if ids:
                self._client.delete(
                    collection_name=self._collection,
                    points_selector=PointIdsList(points=[self._to_qdrant_id(i) for i in ids]),
                )
            elif where:
                qdrant_filter = self._build_filter(where)
                if qdrant_filter:
                    self._client.delete(
                        collection_name=self._collection,
                        points_selector=qdrant_filter,
                    )
        except Exception as e:
            log.error("Qdrant delete() fehlgeschlagen: %s", e)

    def count(self) -> int:
        """Gibt Anzahl gespeicherter Punkte zurück."""
        if self._client is None:
            return 0
        try:
            info = self._client.get_collection(self._collection)
            return info.points_count or 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Interne Helfer
    # ------------------------------------------------------------------

    @staticmethod
    def _to_qdrant_id(doc_id: str) -> str:
        """Konvertiert beliebigen String zu Qdrant-kompatiblem UUID."""
        try:
            uuid.UUID(doc_id)
            return doc_id
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))

    def _build_filter(self, where: Dict) -> Optional[Any]:
        """
        Baut Qdrant Filter aus ChromaDB-style where-Dict.

        Unterstützt:
          {"importance": {"$gte": 5}}
          {"agent_type": "shell"}
          {"$and": [...]}
        """
        try:
            from qdrant_client.models import (
                Filter, FieldCondition, MatchValue, Range, MatchAny
            )

            conditions = []
            for key, value in where.items():
                if key == "$and":
                    sub = Filter(must=[])
                    for sub_cond in value:
                        f = self._build_filter(sub_cond)
                        if f:
                            sub.must.extend(f.must or [])
                    conditions.append(sub)
                    continue

                if isinstance(value, dict):
                    # {"$gte": x, "$lte": y} → Range
                    gte = value.get("$gte")
                    lte = value.get("$lte")
                    gt = value.get("$gt")
                    lt = value.get("$lt")
                    if any(v is not None for v in [gte, lte, gt, lt]):
                        conditions.append(FieldCondition(
                            key=key,
                            range=Range(gte=gte, lte=lte, gt=gt, lt=lt),
                        ))
                    elif "$in" in value:
                        conditions.append(FieldCondition(
                            key=key,
                            match=MatchAny(any=value["$in"]),
                        ))
                else:
                    conditions.append(FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    ))

            return Filter(must=conditions) if conditions else None
        except Exception as e:
            log.warning("Filter-Aufbau fehlgeschlagen: %s", e)
            return None

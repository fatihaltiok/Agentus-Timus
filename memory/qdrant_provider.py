"""
memory/qdrant_provider.py

Qdrant-backed semantic store with two runtime modes:
- embedded: local storage path, single-process only
- server: shared Qdrant service via URL
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("QdrantProvider")

DEFAULT_QDRANT_MODE = "embedded"
DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"
DEFAULT_QDRANT_PATH = Path("./data/qdrant_db")
DEFAULT_QDRANT_COLLECTION = "timus_memory"
VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", "1536"))


def normalize_qdrant_mode(raw_mode: str | None) -> str:
    raw = str(raw_mode or "").strip().lower()
    if raw in {"server", "remote", "http", "https", "cloud"}:
        return "server"
    return "embedded"


def resolve_qdrant_url(raw_url: str | None) -> str:
    value = str(raw_url or "").strip()
    if value.startswith(("http://", "https://")):
        stripped = value.rstrip("/")
        if stripped not in {"http:", "https:"}:
            return stripped
    return DEFAULT_QDRANT_URL


def resolve_qdrant_ready_url(raw_url: str | None) -> str:
    return f"{resolve_qdrant_url(raw_url)}/readyz"


def resolve_qdrant_path(raw_path: str | os.PathLike[str] | None) -> Path:
    value = str(raw_path or "").strip()
    if not value:
        return DEFAULT_QDRANT_PATH
    return Path(value).expanduser()


def resolve_qdrant_collection(raw_collection: str | None) -> str:
    value = str(raw_collection or "").strip()
    return value or DEFAULT_QDRANT_COLLECTION


def resolve_qdrant_api_key(raw_api_key: str | None) -> str | None:
    value = str(raw_api_key or "").strip()
    return value or None


@dataclass(frozen=True)
class QdrantRuntimeConfig:
    mode: str
    url: str
    path: Path
    collection_name: str
    api_key: str | None


def build_qdrant_runtime_config(
    *,
    mode: str | None = None,
    url: str | None = None,
    path: str | os.PathLike[str] | None = None,
    collection_name: str | None = None,
    api_key: str | None = None,
) -> QdrantRuntimeConfig:
    return QdrantRuntimeConfig(
        mode=normalize_qdrant_mode(mode if mode is not None else os.getenv("QDRANT_MODE")),
        url=resolve_qdrant_url(url if url is not None else os.getenv("QDRANT_URL")),
        path=resolve_qdrant_path(path if path is not None else os.getenv("QDRANT_PATH")),
        collection_name=resolve_qdrant_collection(
            collection_name if collection_name is not None else os.getenv("QDRANT_COLLECTION")
        ),
        api_key=resolve_qdrant_api_key(api_key if api_key is not None else os.getenv("QDRANT_API_KEY")),
    )


class QdrantProvider:
    """
    Drop-in Ersatz für ChromaDB Collection-Interface.

    Unterstuetzte Modi:
    - embedded: QdrantClient(path=...)
    - server:   QdrantClient(url=..., api_key=...)
    """

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        collection_name: str | None = None,
        *,
        mode: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
    ):
        self._config = build_qdrant_runtime_config(
            mode=mode,
            url=url,
            path=path,
            collection_name=collection_name,
            api_key=api_key,
        )
        self._path = self._config.path
        self._collection = self._config.collection_name
        self._mode = self._config.mode
        self._url = self._config.url
        self._api_key = self._config.api_key
        self._client = None
        self._embedding_fn = None
        self._last_error = ""
        self._init()

    def _init(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            if self._mode == "server":
                self._client = QdrantClient(
                    url=self._url,
                    api_key=self._api_key,
                )
            else:
                self._path.mkdir(parents=True, exist_ok=True)
                self._client = QdrantClient(path=str(self._path))

            existing = [c.name for c in self._client.get_collections().collections]
            if self._collection not in existing:
                self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config={
                        "content": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
                    },
                )
                log.info(
                    "Qdrant Collection '%s' angelegt (%s)",
                    self._collection,
                    self.endpoint,
                )
            else:
                log.info(
                    "Qdrant Collection '%s' geladen (%s)",
                    self._collection,
                    self.endpoint,
                )
        except ImportError:
            self._last_error = "qdrant_client_missing"
            log.warning("qdrant-client nicht installiert. Installieren: pip install qdrant-client")
            self._client = None
        except Exception as e:
            self._last_error = str(e)
            log.error("Qdrant Initialisierung fehlgeschlagen: %s", e)
            self._client = None

    @property
    def name(self) -> str:
        return self._collection

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def endpoint(self) -> str:
        if self._mode == "server":
            return self._url
        return str(self._path)

    @property
    def last_error(self) -> str:
        return self._last_error

    def is_available(self) -> bool:
        return self._client is not None

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "mode": self._mode,
            "endpoint": self.endpoint,
            "collection": self._collection,
            "available": self.is_available(),
            "last_error": self._last_error,
        }

    def _get_embedding_fn(self):
        if self._embedding_fn is None:
            try:
                from utils.embedding_provider import get_embedding_function

                self._embedding_fn = get_embedding_function()
            except Exception:
                self._embedding_fn = None
        return self._embedding_fn

    def _embed(self, texts: List[str]) -> List[List[float]]:
        fn = self._get_embedding_fn()
        if fn is None:
            return [[0.0] * VECTOR_SIZE for _ in texts]
        try:
            return fn(texts)
        except Exception as e:
            log.warning("Embedding fehlgeschlagen: %s", e)
            return [[0.0] * VECTOR_SIZE for _ in texts]

    def add(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
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

                points.append(
                    PointStruct(
                        id=self._to_qdrant_id(doc_id),
                        vector={"content": embeddings[i]},
                        payload=payload,
                    )
                )

            self._client.upsert(collection_name=self._collection, points=points)
            log.debug("Qdrant: %d Punkte hinzugefügt", len(points))
        except Exception as e:
            log.error("Qdrant add() fehlgeschlagen: %s", e)

    def upsert(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
        self.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    def query(
        self,
        query_embeddings: Optional[List[List[float]]] = None,
        query_texts: Optional[List[str]] = None,
        n_results: int = 5,
        where: Optional[Dict] = None,
    ) -> Dict:
        if self._client is None:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        try:
            if query_embeddings is None and query_texts:
                query_embeddings = self._embed(query_texts)
            if not query_embeddings:
                return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

            qdrant_filter = self._build_filter(where) if where else None

            response = self._client.query_points(
                collection_name=self._collection,
                query=query_embeddings[0],
                using="content",
                limit=max(1, n_results),
                query_filter=qdrant_filter,
                with_payload=True,
            )

            ids, docs, metas, scores = [], [], [], []
            for hit in response.points:
                payload = hit.payload or {}
                ids.append(payload.get("_id", str(hit.id)))
                docs.append(payload.get("document", ""))
                meta = {k: v for k, v in payload.items() if k not in ("document", "_id")}
                metas.append(meta)
                scores.append(1.0 - hit.score)

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
        if self._client is None:
            return {"ids": [], "documents": [], "metadatas": []}

        try:
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
        if self._client is None:
            return
        try:
            from qdrant_client.models import PointIdsList

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
        if self._client is None:
            return 0
        try:
            info = self._client.get_collection(self._collection)
            return info.points_count or 0
        except Exception:
            return 0

    @staticmethod
    def _to_qdrant_id(doc_id: str) -> str:
        try:
            uuid.UUID(doc_id)
            return doc_id
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))

    def _build_filter(self, where: Dict) -> Optional[Any]:
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, Range, MatchAny

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
                    gte = value.get("$gte")
                    lte = value.get("$lte")
                    gt = value.get("$gt")
                    lt = value.get("$lt")
                    if any(v is not None for v in [gte, lte, gt, lt]):
                        conditions.append(
                            FieldCondition(
                                key=key,
                                range=Range(gte=gte, lte=lte, gt=gt, lt=lt),
                            )
                        )
                    elif "$in" in value:
                        conditions.append(
                            FieldCondition(
                                key=key,
                                match=MatchAny(any=value["$in"]),
                            )
                        )
                else:
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value),
                        )
                    )

            return Filter(must=conditions) if conditions else None
        except Exception as e:
            log.warning("Filter-Aufbau fehlgeschlagen: %s", e)
            return None

"""Canvas Store fuer Timus Agent-Orchestrierung.

Ein schlanker persistenter Store (JSON-Datei), der Canvas-Daten fuer
Session-/Agent-Transparenz verwaltet:
- Canvas-Metadaten
- Nodes (z. B. Agenten, Tasks)
- Edges (Flow/Delegation)
- Events (Run-Status, Fehler, Beobachtungen)
- Session -> Canvas Zuordnung
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any, depth: int = 0) -> Any:
    """Konvertiert Werte defensiv in JSON-kompatible Strukturen."""
    if depth > 6:
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v, depth + 1) for v in value]
    return str(value)


class CanvasStore:
    """Thread-sicherer JSON-Store fuer Canvas-Daten."""

    def __init__(self, store_path: Optional[Path | str] = None):
        self._repo_root = Path(__file__).resolve().parent.parent
        default_path = self._repo_root / "data" / "canvas_store.json"
        env_store = (os.getenv("TIMUS_CANVAS_STORE") or "").strip()
        resolved_path = store_path or env_store or default_path
        self._path = Path(resolved_path)
        self._default_path_mode = bool(not store_path and not env_store)
        self._lock = threading.RLock()
        self._store_signature: Optional[Tuple[int, int]] = None
        self._data: Dict[str, Any] = {
            "canvases": {},
            "session_to_canvas": {},
        }
        self._load()

    @staticmethod
    def _normalize_store_data(raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        return {
            "canvases": raw.get("canvases", {}) or {},
            "session_to_canvas": raw.get("session_to_canvas", {}) or {},
        }

    def _load_data_from_path_unlocked(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return self._normalize_store_data(parsed)

    @staticmethod
    def _store_score(data: Optional[Dict[str, Any]]) -> Tuple[int, int, int]:
        if not data:
            return (0, 0, 0)
        canvases = data.get("canvases", {}) or {}
        mappings = data.get("session_to_canvas", {}) or {}
        events = 0
        for canvas in canvases.values():
            events += len((canvas or {}).get("events", []) or [])
        return (events, len(canvases), len(mappings))

    def _maybe_migrate_legacy_store_unlocked(self) -> None:
        """Migriert bestaende Legacy-Store-Dateien auf den kanonischen Repo-Pfad."""
        if not self._default_path_mode:
            return

        canonical_data = self._load_data_from_path_unlocked(self._path)
        canonical_score = self._store_score(canonical_data)

        candidates = []
        # Legacy: Start aus server/ fuehrte historisch zu server/data/canvas_store.json
        legacy_server_path = self._repo_root / "server" / "data" / "canvas_store.json"
        legacy_cwd_path = Path.cwd() / "data" / "canvas_store.json"
        for candidate in (legacy_server_path, legacy_cwd_path):
            if candidate == self._path or not candidate.exists():
                continue
            data = self._load_data_from_path_unlocked(candidate)
            score = self._store_score(data)
            if score > canonical_score:
                candidates.append((score, candidate))

        if not candidates:
            return

        _, best_path = sorted(candidates, key=lambda x: x[0], reverse=True)[0]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(best_path.read_text(encoding="utf-8"), encoding="utf-8")
        self._store_signature = None

    def _read_store_signature_unlocked(self) -> Optional[Tuple[int, int]]:
        if not self._path.exists():
            return None
        stat = self._path.stat()
        return (int(stat.st_mtime_ns), int(stat.st_size))

    def _load(self) -> None:
        with self._lock:
            self._maybe_migrate_legacy_store_unlocked()
            if not self._path.exists():
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._save_unlocked()
                return

            try:
                loaded = self._load_data_from_path_unlocked(self._path)
                if loaded:
                    self._data["canvases"] = loaded.get("canvases", {}) or {}
                    self._data["session_to_canvas"] = loaded.get("session_to_canvas", {}) or {}
                self._store_signature = self._read_store_signature_unlocked()
            except Exception:
                # Korrupten Store nicht crashen lassen; neuen leeren Store verwenden.
                self._data = {"canvases": {}, "session_to_canvas": {}}
                self._save_unlocked()

    def _reload_if_changed_unlocked(self) -> bool:
        current_signature = self._read_store_signature_unlocked()
        if current_signature is None:
            return False
        if self._store_signature == current_signature:
            return False

        try:
            loaded = self._load_data_from_path_unlocked(self._path)
            if loaded:
                self._data["canvases"] = loaded.get("canvases", {}) or {}
                self._data["session_to_canvas"] = loaded.get("session_to_canvas", {}) or {}
                self._store_signature = current_signature
                return True
        except Exception:
            return False
        return False

    def _save_unlocked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self._path)
        self._store_signature = self._read_store_signature_unlocked()

    def _save(self) -> None:
        with self._lock:
            self._save_unlocked()

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:10]}"

    def _get_canvas_unlocked(self, canvas_id: str) -> Dict[str, Any]:
        canvas = self._data["canvases"].get(canvas_id)
        if not canvas:
            raise KeyError(f"Canvas '{canvas_id}' nicht gefunden")
        return canvas

    def _get_primary_canvas_id_unlocked(self) -> Optional[str]:
        canvases = list(self._data["canvases"].values())
        if not canvases:
            return None
        canvases.sort(key=lambda c: str(c.get("updated_at", "")), reverse=True)
        return str(canvases[0].get("id") or "") or None

    def list_canvases(self, limit: int = 50) -> Dict[str, Any]:
        with self._lock:
            self._reload_if_changed_unlocked()
            limit = max(1, min(200, int(limit)))
            canvases = list(self._data["canvases"].values())
            canvases.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
            return {
                "items": [deepcopy(c) for c in canvases[:limit]],
                "count": len(canvases),
            }

    def create_canvas(
        self,
        title: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            self._reload_if_changed_unlocked()
            canvas_id = self._new_id("canvas")
            now = _utc_now_iso()
            canvas = {
                "id": canvas_id,
                "title": (title or "").strip() or f"Canvas {canvas_id}",
                "description": description or "",
                "metadata": _json_safe(metadata or {}),
                "nodes": {},
                "edges": [],
                "events": [],
                "session_ids": [],
                "created_at": now,
                "updated_at": now,
            }
            self._data["canvases"][canvas_id] = canvas
            self._save_unlocked()
            return deepcopy(canvas)

    def get_canvas(self, canvas_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._reload_if_changed_unlocked()
            canvas = self._data["canvases"].get(canvas_id)
            return deepcopy(canvas) if canvas else None

    @staticmethod
    def _is_error_status(status: str, message: str = "") -> bool:
        s = (status or "").strip().lower()
        m = (message or "").strip().lower()
        return ("error" in s) or ("fehler" in s) or ("error" in m) or ("fehler" in m)

    @staticmethod
    def _matches_agent(
        *,
        agent_filter: str,
        event_agent: str = "",
        node_id: str = "",
        title: str = "",
    ) -> bool:
        if not agent_filter:
            return True
        target = agent_filter.strip().lower()
        agent = (event_agent or "").strip().lower()
        node = (node_id or "").strip().lower()
        node_agent = node[6:] if node.startswith("agent:") else node
        ttl = (title or "").strip().lower()
        return target in {agent, node_agent, node, ttl}

    def get_canvas_view(
        self,
        canvas_id: str,
        *,
        session_id: str = "",
        agent: str = "",
        status: str = "",
        only_errors: bool = False,
        event_limit: int = 200,
    ) -> Optional[Dict[str, Any]]:
        """Liefert eine gefilterte Canvas-Sicht."""
        with self._lock:
            self._reload_if_changed_unlocked()
            raw = self._data["canvases"].get(canvas_id)
            if not raw:
                return None

            canvas = deepcopy(raw)

        session_filter = (session_id or "").strip()
        agent_filter = (agent or "").strip()
        status_filter = (status or "").strip().lower()
        limit = max(1, min(1000, int(event_limit)))

        nodes = canvas.get("nodes", {}) or {}
        edges = canvas.get("edges", []) or []
        events = canvas.get("events", []) or []

        filtered_events = []
        for ev in events:
            ev_session = str(ev.get("session_id", "") or "")
            ev_status = str(ev.get("status", "") or "")
            ev_agent = str(ev.get("agent", "") or "")
            ev_node_id = str(ev.get("node_id", "") or "")
            ev_message = str(ev.get("message", "") or "")

            if session_filter and ev_session != session_filter:
                continue
            if status_filter and ev_status.lower() != status_filter:
                continue
            if only_errors and not self._is_error_status(ev_status, ev_message):
                continue
            if not self._matches_agent(
                agent_filter=agent_filter,
                event_agent=ev_agent,
                node_id=ev_node_id,
            ):
                continue
            filtered_events.append(ev)

        filtered_events.sort(key=lambda e: str(e.get("created_at", "")), reverse=True)
        filtered_events = filtered_events[:limit]

        filtered_nodes: Dict[str, Any] = {}
        for node_id, node in nodes.items():
            node_status = str(node.get("status", "") or "")
            node_title = str(node.get("title", "") or "")
            node_session = str((node.get("metadata", {}) or {}).get("last_session_id", "") or "")

            if session_filter and node_session and node_session != session_filter:
                continue
            if status_filter and node_status.lower() != status_filter:
                continue
            if only_errors and not self._is_error_status(node_status):
                continue
            if not self._matches_agent(
                agent_filter=agent_filter,
                node_id=str(node_id),
                title=node_title,
            ):
                continue
            filtered_nodes[node_id] = node

        if filtered_nodes:
            keep_node_ids = set(filtered_nodes.keys())
            filtered_edges = [
                e
                for e in edges
                if str(e.get("source", "")) in keep_node_ids
                and str(e.get("target", "")) in keep_node_ids
            ]
        else:
            filtered_edges = []

        if session_filter:
            filtered_session_ids = [sid for sid in (canvas.get("session_ids", []) or []) if sid == session_filter]
        else:
            filtered_session_ids = list(canvas.get("session_ids", []) or [])

        canvas["nodes"] = filtered_nodes
        canvas["edges"] = filtered_edges
        canvas["events"] = filtered_events
        canvas["session_ids"] = filtered_session_ids
        canvas["view_filters"] = {
            "session_id": session_filter,
            "agent": agent_filter,
            "status": status_filter,
            "only_errors": bool(only_errors),
            "event_limit": limit,
        }
        canvas["view_counts"] = {
            "nodes": len(filtered_nodes),
            "edges": len(filtered_edges),
            "events": len(filtered_events),
            "sessions": len(filtered_session_ids),
        }
        return canvas

    def get_canvas_id_for_session(self, session_id: str) -> Optional[str]:
        with self._lock:
            self._reload_if_changed_unlocked()
            return self._data["session_to_canvas"].get(session_id)

    def get_canvas_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._reload_if_changed_unlocked()
            canvas_id = self._data["session_to_canvas"].get(session_id)
            if not canvas_id:
                return None
            canvas = self._data["canvases"].get(canvas_id)
            return deepcopy(canvas) if canvas else None

    def get_canvas_by_session_view(
        self,
        session_id: str,
        *,
        agent: str = "",
        status: str = "",
        only_errors: bool = False,
        event_limit: int = 200,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._reload_if_changed_unlocked()
            canvas_id = self._data["session_to_canvas"].get(session_id)
        if not canvas_id:
            return None
        return self.get_canvas_view(
            canvas_id=canvas_id,
            session_id=session_id,
            agent=agent,
            status=status,
            only_errors=only_errors,
            event_limit=event_limit,
        )

    def attach_session(self, canvas_id: str, session_id: str) -> Dict[str, Any]:
        with self._lock:
            self._reload_if_changed_unlocked()
            canvas = self._get_canvas_unlocked(canvas_id)
            previous_canvas = self._data["session_to_canvas"].get(session_id)

            self._data["session_to_canvas"][session_id] = canvas_id
            if session_id not in canvas["session_ids"]:
                canvas["session_ids"].append(session_id)
            canvas["updated_at"] = _utc_now_iso()
            self._save_unlocked()

            return {
                "canvas_id": canvas_id,
                "session_id": session_id,
                "previous_canvas_id": previous_canvas,
            }

    def upsert_node(
        self,
        canvas_id: str,
        node_id: str,
        node_type: str,
        title: str,
        status: str = "idle",
        position: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            self._reload_if_changed_unlocked()
            canvas = self._get_canvas_unlocked(canvas_id)
            now = _utc_now_iso()
            nodes = canvas["nodes"]
            existing = nodes.get(node_id)

            if not existing:
                existing = {
                    "id": node_id,
                    "type": node_type,
                    "title": title,
                    "status": status,
                    "position": _json_safe(position or {}),
                    "metadata": _json_safe(metadata or {}),
                    "created_at": now,
                    "updated_at": now,
                }
                nodes[node_id] = existing
            else:
                existing["type"] = node_type or existing.get("type", "generic")
                existing["title"] = title or existing.get("title", node_id)
                existing["status"] = status or existing.get("status", "idle")
                if position is not None:
                    existing["position"] = _json_safe(position)
                if metadata:
                    merged = dict(existing.get("metadata") or {})
                    merged.update(_json_safe(metadata))
                    existing["metadata"] = merged
                existing["updated_at"] = now

            canvas["updated_at"] = now
            self._save_unlocked()
            return deepcopy(existing)

    def add_edge(
        self,
        canvas_id: str,
        source_node_id: str,
        target_node_id: str,
        label: str = "",
        kind: str = "flow",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            self._reload_if_changed_unlocked()
            canvas = self._get_canvas_unlocked(canvas_id)
            for edge in canvas["edges"]:
                if (
                    edge.get("source") == source_node_id
                    and edge.get("target") == target_node_id
                    and edge.get("kind") == kind
                    and edge.get("label", "") == (label or "")
                ):
                    return deepcopy(edge)

            edge = {
                "id": self._new_id("edge"),
                "source": source_node_id,
                "target": target_node_id,
                "kind": kind,
                "label": label or "",
                "metadata": _json_safe(metadata or {}),
                "created_at": _utc_now_iso(),
            }
            canvas["edges"].append(edge)
            canvas["updated_at"] = _utc_now_iso()
            self._save_unlocked()
            return deepcopy(edge)

    def add_event(
        self,
        canvas_id: str,
        event_type: str,
        status: str = "",
        agent: str = "",
        node_id: str = "",
        message: str = "",
        session_id: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            self._reload_if_changed_unlocked()
            canvas = self._get_canvas_unlocked(canvas_id)
            event = {
                "id": self._new_id("event"),
                "type": event_type,
                "status": status or "",
                "agent": agent or "",
                "node_id": node_id or "",
                "message": (message or "")[:1000],
                "session_id": session_id or "",
                "payload": _json_safe(payload or {}),
                "created_at": _utc_now_iso(),
            }
            canvas["events"].append(event)
            # Ringpuffer-artige Begrenzung fuer Datei-Size.
            if len(canvas["events"]) > 2000:
                canvas["events"] = canvas["events"][-2000:]
            canvas["updated_at"] = _utc_now_iso()
            self._save_unlocked()
            return deepcopy(event)

    def record_agent_event(
        self,
        session_id: str,
        agent_name: str,
        status: str,
        message: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Schreibt Agent-Run-Event in zugeordnetes Canvas (falls Mapping existiert)."""
        auto_attach = (
            os.getenv("TIMUS_CANVAS_AUTO_ATTACH_SESSIONS", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )

        with self._lock:
            self._reload_if_changed_unlocked()
            canvas_id = self._data["session_to_canvas"].get(session_id)
            if not canvas_id and auto_attach and session_id:
                fallback_canvas_id = self._get_primary_canvas_id_unlocked()
                if fallback_canvas_id:
                    canvas = self._data["canvases"].get(fallback_canvas_id)
                    if canvas is not None:
                        self._data["session_to_canvas"][session_id] = fallback_canvas_id
                        if session_id not in canvas["session_ids"]:
                            canvas["session_ids"].append(session_id)
                        canvas["updated_at"] = _utc_now_iso()
                        self._save_unlocked()
                        canvas_id = fallback_canvas_id
            if not canvas_id:
                return None

        node_id = f"agent:{agent_name}"
        try:
            self.upsert_node(
                canvas_id=canvas_id,
                node_id=node_id,
                node_type="agent",
                title=agent_name,
                status=status,
                metadata={"last_session_id": session_id},
            )
            event = self.add_event(
                canvas_id=canvas_id,
                event_type="agent_run",
                status=status,
                agent=agent_name,
                node_id=node_id,
                session_id=session_id,
                message=message,
                payload=payload,
            )
            return {"canvas_id": canvas_id, "event": event}
        except KeyError:
            return None


canvas_store = CanvasStore()

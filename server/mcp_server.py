# server/mcp_server.py

import sys
import os
import asyncio
from pathlib import Path
import importlib
import logging
import inspect
import json as _json
import html as _html
import threading
import re
import uuid
import webbrowser
import ipaddress
import mimetypes
import copy
from collections import deque
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlencode
import requests

# --- Drittanbieter-Bibliotheken ---
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from jsonrpcserver import async_dispatch
from dotenv import load_dotenv
from utils.chroma_runtime import build_chroma_settings, configure_chroma_runtime
from utils.headless_service_guard import is_service_headless_context

# --- NumPy JSON Encoder für numpy Typen ---
class NumpyJSONEncoder(_json.JSONEncoder):
    """JSON Encoder der NumPy Typen zu nativen Python Typen konvertiert."""
    def default(self, obj):
        # NumPy boolean
        if hasattr(obj, 'dtype') and obj.dtype == bool:
            return bool(obj)
        # NumPy integer
        if hasattr(obj, 'dtype') and 'int' in str(obj.dtype):
            return int(obj)
        # NumPy float
        if hasattr(obj, 'dtype') and 'float' in str(obj.dtype):
            return float(obj)
        # NumPy ndarray
        if hasattr(obj, 'tolist'):
            return obj.tolist()
        # Generischer Fallback
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

def numpy_aware_serializer(response):
    """Serializer der NumPy Typen behandeln kann.

    Versucht zuerst native Konvertierung, dann Nemotron-Fallback bei komplexen Fällen.
    """
    if response is None:
        return ""
    try:
        return _json.dumps(response, cls=NumpyJSONEncoder)
    except (TypeError, ValueError) as e:
        # Bei komplexen Fällen: Nemotron-Fallback (lazy import)
        log.warning(f"Native JSON-Serialisierung fehlgeschlagen: {e}")
        try:
            import asyncio
            from tools.json_nemotron_tool.json_nemotron_tool import sanitize_api_response
            # Async-Funktion synchron aufrufen
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Wir sind in einem async Kontext, nutze run_coroutine_threadsafe
                future = asyncio.run_coroutine_threadsafe(
                    sanitize_api_response(response), loop
                )
                return future.result(timeout=30)
            else:
                return loop.run_until_complete(sanitize_api_response(response))
        except Exception as nemotron_error:
            log.error(f"Nemotron-Fallback fehlgeschlagen: {nemotron_error}")
            # Letzter Fallback: String-Repräsentation
            try:
                return _json.dumps({"_serialized": str(response), "_warning": "Nemotron-Fallback verwendet"})
            except:
                return '{"_error": "JSON-Serialisierung nicht möglich"}'

# --- Projekt-Setup ---
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
# .env frueh laden, damit env-basierte Pfade bereits bei Modul-Imports wirken.
load_dotenv(dotenv_path=project_root / ".env", override=False)
configure_chroma_runtime()

# Runtime-Settings: Persistenz ohne Server-Neustart (wird in lifespan geladen)
_RUNTIME_SETTINGS_PATH = project_root / "data" / "runtime_settings.json"
_RUNTIME_LOCATION_SNAPSHOT_PATH = project_root / "data" / "runtime_location_snapshot.json"
_RUNTIME_LOCATION_REGISTRY_PATH = project_root / "data" / "runtime_location_registry.json"
_RUNTIME_LOCATION_CONTROLS_PATH = project_root / "data" / "runtime_location_controls.json"
_RUNTIME_ROUTE_SNAPSHOT_PATH = project_root / "data" / "runtime_route_snapshot.json"

# --- Lokale Module und Kontext importieren ---
import tools.shared_context as shared_context
from tools.tool_registry_v2 import registry_v2, ValidationError
from utils.policy_gate import (
    audit_policy_decision,
    check_tool_policy,
    evaluate_policy_gate,
)
from orchestration.canvas_store import canvas_store
from server.canvas_ui import build_canvas_ui_html
from server.mobile_route_ui import build_mobile_route_ui_html
from server.conversation_qdrant import recall_chat_turns as _semantic_recall_chat_turns
from server.conversation_qdrant import store_chat_turn as _semantic_store_chat_turn
from gateway.status_snapshot import collect_status_snapshot
from orchestration.autonomy_observation import record_autonomy_observation
from orchestration.approval_auth_contract import normalize_phase_d_workflow_payload
from orchestration.auth_session_state import (
    auth_session_index_to_dict,
    latest_auth_session_from_index,
    normalize_auth_session_entry,
    upsert_auth_session_index,
)
from orchestration.conversation_state import (
    apply_runtime_plan_state,
    apply_turn_interpretation,
    apply_pending_followup_prompt,
    conversation_state_to_dict,
    decay_conversation_state,
    normalize_pending_followup_prompt,
    touch_conversation_state,
)
from orchestration.meta_context_eval import detect_context_misread_risk
from orchestration.pending_workflow_state import (
    classify_pending_workflow_reply,
    clear_pending_workflow_state,
    is_pending_workflow_state,
    pending_workflow_state_to_dict,
)
from orchestration.preference_instruction_memory import capture_preference_memory
from orchestration.topic_state_history import topic_history_to_list, update_topic_history
from orchestration.longrunner_transport import (
    bind_longrun_context,
    get_current_run_id,
    make_blocker_event,
    make_partial_result_event,
    make_progress_event,
    make_run_completed_event,
    make_run_failed_event,
    make_run_started_event,
    next_event_seq,
    new_run_id,
)
from orchestration.request_correlation import (
    bind_request_correlation,
    get_current_request_id,
    get_current_session_id,
)
from memory.semantic_backend_policy import normalize_semantic_memory_backend
from utils.location_presence import (
    enrich_location_presence_snapshot,
    prepare_location_presence_snapshot,
)
from utils.location_registry import (
    apply_location_controls_to_snapshot,
    build_location_status_payload,
    normalize_location_controls,
    normalize_location_registry,
    sync_mode_allowed,
    update_location_registry,
)
from utils.location_route import prepare_route_snapshot
from utils.location_reroute import assess_live_reroute, apply_live_reroute_metadata
from utils.location_map_mode import (
    normalize_route_map_mode,
    resolve_route_map_mode,
    route_map_interactive_available,
)
from utils.location_chat_context import (
    build_location_chat_context_block,
    evaluate_location_chat_context,
)

log = logging.getLogger("mcp_server")

# ── Canvas Chat & Agent-Status (In-Memory) ────────────────────────────────────
_KNOWN_AGENTS = [
    "executor", "research", "reasoning", "creative", "development", "meta", "visual",
    "data", "document",  # M1
    "communication",     # M2
    "system",            # M3
    "shell",             # M4
    "image",             # M5
]
_agent_status: dict = {
    a: {"status": "idle", "last_run": None, "last_query": ""}
    for a in _KNOWN_AGENTS
}
_thinking_active: bool = False
_sse_queues: list = []
_sse_lock = threading.Lock()
_chat_history: list = []
_chat_lock = threading.Lock()
_location_snapshot: dict | None = None
_location_snapshot_lock = threading.Lock()
_location_registry: dict | None = None
_location_registry_lock = threading.Lock()
_location_controls: dict | None = None
_location_controls_lock = threading.Lock()
_route_snapshot: dict | None = None
_route_snapshot_lock = threading.Lock()
_SHUTDOWN_STEP_TIMEOUT_S = float(os.getenv("TIMUS_SHUTDOWN_STEP_TIMEOUT", "6"))
_CONSOLE_FILE_DIRS = ("results", "data/uploads")
_CHAT_HISTORY_LIMIT = int(os.getenv("TIMUS_CHAT_HISTORY_LIMIT", "200"))
_mcp_lifecycle: dict = {}


def _reset_mcp_lifecycle(*, phase: str = "startup", status: str = "starting") -> dict:
    """Setzt den MCP-Lifecycle-Zustand fuer Startup/Restart neu auf."""
    global _mcp_lifecycle
    timestamp = datetime.utcnow().isoformat() + "Z"
    _mcp_lifecycle = {
        "phase": phase,
        "status": status,
        "ready": False,
        "warmup_pending": False,
        "transient": status != "healthy",
        "started_at": timestamp,
        "ready_at": None,
        "shutdown_at": None,
        "warmups": {},
        "last_error": None,
    }
    return dict(_mcp_lifecycle)


def _update_mcp_lifecycle(**changes) -> dict:
    """Aktualisiert den MCP-Lifecycle-Zustand atomar."""
    global _mcp_lifecycle
    if not _mcp_lifecycle:
        _reset_mcp_lifecycle()
    next_state = dict(_mcp_lifecycle)
    next_state.update({k: v for k, v in changes.items() if v is not None})
    status = str(next_state.get("status") or "").strip().lower()
    next_state["transient"] = bool(next_state.get("transient")) or status in {
        "starting",
        "shutting_down",
    }
    if next_state.get("ready") and not next_state.get("ready_at"):
        next_state["ready_at"] = datetime.utcnow().isoformat() + "Z"
    if status == "shutting_down":
        next_state["shutdown_at"] = datetime.utcnow().isoformat() + "Z"
    _mcp_lifecycle = next_state
    return dict(_mcp_lifecycle)


def _current_mcp_lifecycle(app: FastAPI | None = None) -> dict:
    state = getattr(getattr(app, "state", None), "mcp_lifecycle", None)
    if isinstance(state, dict) and state:
        return dict(state)
    if _mcp_lifecycle:
        return dict(_mcp_lifecycle)
    return _reset_mcp_lifecycle()


def _set_app_mcp_lifecycle(app: FastAPI, **changes) -> dict:
    state = _update_mcp_lifecycle(**changes)
    app.state.mcp_lifecycle = dict(state)
    return state


def _build_health_payload(app: FastAPI) -> dict:
    tools = registry_v2.list_all_tools()
    lifecycle = _current_mcp_lifecycle(app)
    return {
        "status": lifecycle.get("status") or "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_rpc_methods": len(tools),
        "registry": "v2",
        "ready": bool(lifecycle.get("ready")),
        "warmup_pending": bool(lifecycle.get("warmup_pending")),
        "transient": bool(lifecycle.get("transient")),
        "lifecycle": lifecycle,
        "inception": getattr(
            app.state,
            "inception",
            {
                "registered": False,
                "env_url": None,
                "health": {"ok": None, "detail": "n/a"},
            },
        ),
    }


def _sse_connection_ttl_sec() -> float:
    """Optionale Maximaldauer fuer eine SSE-Verbindung.

    Standard: deaktiviert (`0`), weil der Canvas-Flow unter kuenstlichen
    Reconnects leidet. Restarts werden ueber `shutdown_event` und Uvicorns
    eigener Verbindungsschliessung sauber behandelt.

    Wenn explizit gesetzt:
    - `<= 0` deaktiviert die TTL
    - positive Werte werden konservativ auf mindestens 60s geklemmt
    """
    raw = str(os.getenv("TIMUS_SSE_CONNECTION_TTL_SEC") or "").strip()
    if not raw:
        return 0.0
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if parsed <= 0:
        return 0.0
    return max(60.0, parsed)

_FOLLOWUP_PATTERNS = (
    r"^\s*und\b",
    r"\bdagegen\b",
    r"\bdas\b",
    r"\bdazu\b",
    r"\bwas jetzt\b",
    r"\bund was jetzt\b",
    r"\bwie behebst du das\b",
    r"\bwas kannst du dagegen tun\b",
    r"\bsag du es mir\b",
)

# P2: Referenz-Pronomen — "damit", "das gleiche", "dieselbe suche" etc.
_REFERENCE_CONTINUATION_PATTERNS = (
    r"\bdamit\b",
    r"\bdas gleiche\b",
    r"\bdie gleiche\b",
    r"\bdieselbe\b",
    r"\bdas selbe\b",
    r"\bgenau das\b",
    r"\bgenau das gleiche\b",
    r"\bselbiges\b",
)

# P4: Bestätigungs-Muster — kurze Zustimmung zu vorherigem Angebot
_AFFIRMATION_PATTERNS = (
    r"^\s*ja\s*[.!]?\s*$",
    r"^\s*ok\s*[.!]?\s*$",
    r"^\s*okay\s*[.!]?\s*$",
    r"^\s*(?:ok(?:ay)?\s+)?fang\s+an\s*[.!]?\s*$",
    r"^\s*(?:ok(?:ay)?\s+)?leg\s+los\s*[.!]?\s*$",
    r"\bja\s+mach\s+das\b",
    r"\bja\s+mach\s+mal\b",
    r"\bja\s+mach\s+weiter\b",
    r"\bja\s+schau\s+(mal\s+)?danach\b",
    r"\bschau\s+mal\s+danach\b",
    r"\bklingt\s+gut\b",
    r"\bgerne\s*[.!]?\s*$",
    r"\bjep\s*[.!]?\s*$",
    r"\byep\s*[.!]?\s*$",
    r"^\s*mach\s+das\s*[.!]?\s*$",
    r"^\s*mach\s+mal\s*[.!]?\s*$",
    r"\blos\s+geht.?s\b",
    r"\bauf\s+jeden\s+fall\b",
)

_SHORT_CONTEXTUAL_REPLY_PATTERNS = (
    r"^\s*die\s+erste(?:\s+option)?\s*$",
    r"^\s*die\s+zweite(?:\s+option)?\s*$",
    r"^\s*die\s+dritte(?:\s+option)?\s*$",
    r"^\s*den\s+ersten\s*$",
    r"^\s*den\s+zweiten\s*$",
    r"^\s*den\s+dritten\s*$",
    r"^\s*das\s+erste\s*$",
    r"^\s*das\s+zweite\s*$",
    r"^\s*beide?s?\s*$",
    r"^\s*weiter(?:\s+damit)?\s*$",
    r"^\s*mach\s+weiter\s*$",
    r"^\s*erstmal\s+das\s*$",
    r"^\s*nimm\s+die\s+erste\s*$",
    r"^\s*nimm\s+die\s+zweite\s*$",
)

_DEFERRED_CONTEXTUAL_REPLY_PATTERNS = (
    r"^\s*(?:(?:ich\s+)?muss|muss\s+ich)\s+(?:mir\s+)?(?:das\s+)?noch\s+(?:überlegen|ueberlegen|uberlegen)\s*[.!]?\s*$",
    r"^\s*(?:ich\s+)?(?:überlege|ueberlege|uberlege)\s+(?:mir\s+)?(?:das\s+)?noch\s*[.!]?\s*$",
    r"^\s*(?:ich\s+)?denke\s+(?:noch\s+)?dar(?:ü|ue)ber\s+nach\s*[.!]?\s*$",
    r"^\s*(?:dar(?:ü|ue)ber\s+)?muss\s+ich\s+(?:noch\s+)?nachdenken\s*[.!]?\s*$",
)

# P4: Angebots-Muster am Ende einer Assistenten-Antwort
_PROPOSAL_TRIGGER_PATTERNS = (
    r"\bsoll\s+ich\b",
    r"\bich\s+kann\b",
    r"\bich\s+k[oö]nnte\b",
    r"\bwillst\s+du\b",
    r"\bmagst\s+du\b",
    r"\bmöchtest\s+du\b",
    r"\bmoechtest\s+du\b",
)

_CONTEXTUAL_RECALL_PATTERNS = (
    r"\bnochmal\b",
    r"\bvorhin\b",
    r"\bfrueher\b",
    r"\bfrüher\b",
    r"\berinner\b",
    r"\bwie war\b",
    r"\bwas war\b",
    r"\bdaran\b",
    r"\berklaer\b",
    r"\berklär\b",
)

_RESULT_EXTRACTION_FOLLOWUP_PATTERNS = (
    r"\bhol(?:e)?\b.*\bheraus\b",
    r"\bzieh(?:e)?\b.*\bheraus\b",
    r"\blist(?:e)?\b.*\baus\b",
    r"\bextrah(?:ier|iere)\b",
    r"\bfass\b.*\bzusammen\b",
    r"\bmach(?:e)?\b.*\btabelle\b",
    r"\btabell(?:e|arisch)\b",
)

_CAPABILITY_FOLLOWUP_PATTERNS = (
    r"\bk[oö]nntest du dir das beibringen\b",
    r"\bk[oö]nntest du das lernen\b",
    r"\bwie k[oö]nntest du das lernen\b",
    r"\bwie k[oö]nntest du dir das beibringen\b",
    r"\bwas br[aä]uchtest du daf[uü]r\b",
    r"\bwas m[uü]sstest du daf[uü]r haben\b",
    r"\bwie w[uü]rde das gehen\b",
    r"\bkannst du dir das aneignen\b",
)

_VISUAL_INTENT_TOKENS = (
    "bildschirm",
    "screen",
    "sichtbar",
    "klick",
    "tippe",
    "tippen",
    "button",
    "formular",
    "browser",
    "seite",
    "fenster",
)

_FOLLOWUP_TOPIC_STOPWORDS = {
    "aber",
    "als",
    "am",
    "an",
    "auch",
    "auf",
    "aus",
    "bei",
    "bin",
    "bitte",
    "da",
    "das",
    "dass",
    "dein",
    "deine",
    "dem",
    "den",
    "der",
    "des",
    "die",
    "dir",
    "doch",
    "du",
    "ein",
    "eine",
    "einer",
    "einem",
    "einen",
    "er",
    "erklaer",
    "erklär",
    "es",
    "etwas",
    "fuer",
    "für",
    "ganz",
    "hatte",
    "hattest",
    "hinter",
    "ich",
    "ihr",
    "ihre",
    "im",
    "in",
    "ist",
    "ja",
    "kannst",
    "koenntest",
    "könntest",
    "mal",
    "mein",
    "meine",
    "mir",
    "mit",
    "nicht",
    "nochmal",
    "nein",
    "oder",
    "seine",
    "so",
    "und",
    "uns",
    "vom",
    "von",
    "vorhin",
    "war",
    "was",
    "wegen",
    "wie",
    "wieder",
    "wir",
    "wo",
    "zu",
}


def _session_storage_root() -> Path:
    raw = str(os.getenv("TIMUS_SESSION_STORAGE_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return project_root / "data" / "session_capsules"


def _session_entry_limit() -> int:
    raw = str(os.getenv("TIMUS_SESSION_ENTRY_LIMIT") or "24").strip()
    try:
        return max(4, min(int(raw), 200))
    except (TypeError, ValueError):
        return 24


def _session_summary_char_limit() -> int:
    raw = str(os.getenv("TIMUS_SESSION_SUMMARY_CHAR_LIMIT") or "4000").strip()
    try:
        return max(400, min(int(raw), 24000))
    except (TypeError, ValueError):
        return 4000


def _session_capsule_path(session_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(session_id or "default")).strip("._")
    if not safe:
        safe = "default"
    return _session_storage_root() / f"{safe}.json"


def _normalize_session_capsule_payload(capsule: dict | None) -> dict:
    payload = dict(capsule or {})
    session_id = str(payload.get("session_id") or "default").strip() or "default"
    payload["session_id"] = session_id
    payload["summary"] = str(payload.get("summary") or "").strip()
    entries = payload.get("entries")
    if not isinstance(entries, list):
        entries = []
    payload["entries"] = [entry for entry in entries if isinstance(entry, dict)]
    payload["conversation_state"] = conversation_state_to_dict(
        payload.get("conversation_state"),
        session_id=session_id,
        last_updated=str(payload.get("last_updated") or ""),
        pending_followup_prompt=str(payload.get("pending_followup_prompt") or ""),
    )
    payload["topic_history"] = topic_history_to_list(
        payload.get("topic_history"),
        session_id=session_id,
        now=str(payload.get("last_updated") or ""),
    )
    payload["pending_workflow"] = pending_workflow_state_to_dict(
        payload.get("pending_workflow"),
        updated_at=str(payload.get("last_updated") or ""),
    )
    payload["auth_sessions"] = auth_session_index_to_dict(
        payload.get("auth_sessions"),
        session_id=session_id,
        updated_at=str(payload.get("last_updated") or ""),
    )
    return payload


def _load_session_capsule(session_id: str) -> dict:
    path = _session_capsule_path(session_id)
    if not path.exists():
        return _normalize_session_capsule_payload({"session_id": session_id, "summary": "", "entries": []})
    try:
        with open(path, encoding="utf-8") as handle:
            payload = _json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("invalid capsule payload")
        entries = payload.get("entries")
        if not isinstance(entries, list):
            entries = []
        payload["entries"] = [entry for entry in entries if isinstance(entry, dict)]
        payload["summary"] = str(payload.get("summary") or "").strip()
        payload["session_id"] = str(payload.get("session_id") or session_id)
        return _normalize_session_capsule_payload(payload)
    except Exception as exc:
        log.warning(f"⚠️ Session-Capsule konnte nicht geladen werden ({session_id}): {exc}")
        return _normalize_session_capsule_payload({"session_id": session_id, "summary": "", "entries": []})


def _trim_summary_text(summary: str) -> str:
    text = str(summary or "").strip()
    if len(text) <= _session_summary_char_limit():
        return text
    return text[-_session_summary_char_limit():].lstrip()


def _entry_digest(entry: dict) -> str:
    role = str(entry.get("role") or "").strip() or "unknown"
    agent = str(entry.get("agent") or "").strip()
    text = str(entry.get("text") or "").strip()
    if not text:
        return ""
    label = f"{role}:{agent}" if agent and role == "assistant" else role
    return f"- {label}: {text[:180]}"


def _merge_session_summary(existing_summary: str, folded_entries: list[dict]) -> str:
    parts: list[str] = []
    current = str(existing_summary or "").strip()
    if current:
        parts.append(current)
    parts.extend(line for entry in folded_entries if (line := _entry_digest(entry)))
    return _trim_summary_text("\n".join(parts))


def _store_session_capsule(capsule: dict) -> None:
    normalized = _normalize_session_capsule_payload(capsule)
    path = _session_capsule_path(str(normalized.get("session_id") or "default"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        _json.dump(normalized, handle, ensure_ascii=False, indent=2)


def _append_session_capsule_entry(session_id: str, entry: dict) -> None:
    capsule = _load_session_capsule(session_id)
    entries = [item for item in capsule.get("entries", []) if isinstance(item, dict)]
    entries.append(entry)
    overflow = len(entries) - _session_entry_limit()
    if overflow > 0:
        capsule["summary"] = _merge_session_summary(capsule.get("summary", ""), entries[:overflow])
        entries = entries[overflow:]
    capsule["session_id"] = session_id
    capsule["entries"] = entries
    capsule["last_updated"] = str(entry.get("ts") or datetime.utcnow().isoformat() + "Z")
    capsule["conversation_state"] = touch_conversation_state(
        capsule.get("conversation_state"),
        session_id=session_id,
        updated_at=str(capsule.get("last_updated") or ""),
        pending_followup_prompt=str(capsule.get("pending_followup_prompt") or ""),
    ).to_dict()
    _store_session_capsule(capsule)


def _broadcast_sse(event: dict) -> None:
    """Sendet ein SSE-Event an alle verbundenen Browser-Clients."""
    payload = _json.dumps(event, ensure_ascii=False)
    with _sse_lock:
        dead = []
        for q in _sse_queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                log.warning(
                    f"SSE-Queue voll (maxsize={q.maxsize}) — Event verworfen: "
                    f"{event.get('type', '?')}"
                )
                dead.append(q)
            except Exception as e:
                log.debug(f"SSE-Queue Fehler: {e}")
                dead.append(q)
        for q in dead:
            try:
                _sse_queues.remove(q)
            except ValueError:
                pass


def _longrun_default_message(
    *,
    kind: str,
    agent: str,
    stage: str,
    payload: dict | None = None,
) -> str:
    info = payload or {}
    explicit = str(info.get("message") or "").strip()
    if explicit:
        return explicit

    query = str(info.get("query") or "").strip()
    url = str(info.get("url") or "").strip()
    stage_map = {
        "executor_run_started": "Executor-Bearbeitung gestartet.",
        "simple_live_lookup_start": "Live-Suche gestartet.",
        "location_context_lookup": "Prüfe Live-Standortkontext.",
        "news_lookup": f"Suche aktuelle Nachrichten{' zu ' + query if query else ''}.",
        "web_lookup": f"Suche aktuelle Web-Treffer{' zu ' + query if query else ''}.",
        "fetch_contextual_source": f"Lese Bezugquelle{' ' + url if url else ''}.",
        "fetch_primary_source": f"Lese Hauptquelle{' ' + url if url else ''}.",
        "maps_places_lookup": f"Frage Karten-/Ortsdaten ab{' für ' + query if query else ''}.",
        "maps_route_lookup": f"Berechne Route{' nach ' + query if query else ''}.",
        "visual_task_started": "Visual-Automation gestartet.",
        "visual_navigation_start": f"Öffne Zielseite{' ' + url if url else ''}.",
        "visual_plan_step_started": "Bearbeite den nächsten Visual-Schritt.",
        "visual_step_blocked": "Ein Visual-Schritt ist aktuell blockiert.",
        "delegation_partial": f"{agent} liefert ein partielles Ergebnis.",
        "delegation_partial_timeout": f"{agent} hat den Lauf nur teilweise abgeschlossen.",
    }
    if stage in stage_map:
        return stage_map[stage]
    if kind == "blocker":
        return f"{agent} wartet auf Nutzeraktion."
    if kind == "partial_result":
        return f"{agent} hat erste Teilergebnisse."
    if kind == "run_started":
        return f"{agent} hat die Bearbeitung gestartet."
    if kind == "run_completed":
        return f"{agent} hat die Bearbeitung abgeschlossen."
    if kind == "run_failed":
        return f"{agent} ist fehlgeschlagen."
    return f"{agent}: {stage.replace('_', ' ')}"


def _emit_longrun_event(
    event_type: str,
    *,
    agent: str,
    stage: str = "",
    message: str = "",
    progress_hint: str = "working",
    next_expected_update_s: int = 15,
    content_preview: str = "",
    blocker_reason: str = "",
    user_action_required: str = "",
    workflow_id: str = "",
    workflow_status: str = "",
    workflow_service: str = "",
    workflow_reason: str = "",
    workflow_message: str = "",
    workflow_resume_hint: str = "",
    workflow_challenge_type: str = "",
    workflow_approval_scope: str = "",
    error_class: str = "",
    error_code: str = "",
    request_id: str = "",
    session_id: str = "",
    run_id: str = "",
) -> dict | None:
    effective_request_id = str(request_id or get_current_request_id()).strip()
    effective_session_id = str(session_id or get_current_session_id()).strip()
    effective_run_id = str(run_id or get_current_run_id()).strip()
    effective_agent = str(agent or "").strip()
    if not effective_request_id or not effective_run_id or not effective_agent:
        return None

    seq = next_event_seq()
    text = str(message or "").strip()
    if event_type == "run_started":
        event = make_run_started_event(
            request_id=effective_request_id,
            run_id=effective_run_id,
            session_id=effective_session_id,
            agent=effective_agent,
            seq=seq,
            message=text or _longrun_default_message(kind=event_type, agent=effective_agent, stage="started"),
        )
    elif event_type == "progress":
        event = make_progress_event(
            request_id=effective_request_id,
            run_id=effective_run_id,
            session_id=effective_session_id,
            agent=effective_agent,
            stage=str(stage or "working").strip(),
            seq=seq,
            message=text or _longrun_default_message(kind=event_type, agent=effective_agent, stage=str(stage or "working").strip()),
            progress_hint=progress_hint,
            next_expected_update_s=next_expected_update_s,
        )
    elif event_type == "partial_result":
        event = make_partial_result_event(
            request_id=effective_request_id,
            run_id=effective_run_id,
            session_id=effective_session_id,
            agent=effective_agent,
            stage=str(stage or "partial_result").strip(),
            seq=seq,
            message=text or _longrun_default_message(kind=event_type, agent=effective_agent, stage=str(stage or "partial_result").strip()),
            content_preview=str(content_preview or "").strip(),
        )
    elif event_type == "blocker":
        event = make_blocker_event(
            request_id=effective_request_id,
            run_id=effective_run_id,
            session_id=effective_session_id,
            agent=effective_agent,
            stage=str(stage or "blocked").strip(),
            seq=seq,
            message=text or _longrun_default_message(kind=event_type, agent=effective_agent, stage=str(stage or "blocked").strip()),
            blocker_reason=str(blocker_reason or "blocked").strip(),
            user_action_required=str(user_action_required or "").strip(),
            workflow_id=str(workflow_id or "").strip(),
            workflow_status=str(workflow_status or "").strip(),
            workflow_service=str(workflow_service or "").strip(),
            workflow_reason=str(workflow_reason or "").strip(),
            workflow_message=str(workflow_message or "").strip(),
            workflow_resume_hint=str(workflow_resume_hint or "").strip(),
            workflow_challenge_type=str(workflow_challenge_type or "").strip(),
            workflow_approval_scope=str(workflow_approval_scope or "").strip(),
        )
    elif event_type == "run_completed":
        event = make_run_completed_event(
            request_id=effective_request_id,
            run_id=effective_run_id,
            session_id=effective_session_id,
            agent=effective_agent,
            seq=seq,
            message=text or _longrun_default_message(kind=event_type, agent=effective_agent, stage="done"),
        )
    elif event_type == "run_failed":
        event = make_run_failed_event(
            request_id=effective_request_id,
            run_id=effective_run_id,
            session_id=effective_session_id,
            agent=effective_agent,
            stage=str(stage or "failed").strip(),
            seq=seq,
            message=text or _longrun_default_message(kind=event_type, agent=effective_agent, stage=str(stage or "failed").strip()),
            error_class=str(error_class or "").strip(),
            error_code=str(error_code or "").strip(),
        )
    else:
        return None

    payload = event.to_dict()
    _broadcast_sse(payload)
    return payload


def _emit_longrun_progress_from_payload(agent: str, stage: str, payload: dict | None = None) -> dict | None:
    info = dict(payload or {})
    kind = str(info.get("kind") or "progress").strip().lower() or "progress"
    message = _longrun_default_message(kind=kind, agent=agent, stage=stage, payload=info)
    if kind == "blocker":
        return _emit_longrun_event(
            "blocker",
            agent=agent,
            stage=stage,
            message=message,
            blocker_reason=str(info.get("blocker_reason") or "blocked").strip(),
            user_action_required=str(info.get("user_action_required") or "").strip(),
            workflow_id=str(info.get("workflow_id") or "").strip(),
            workflow_status=str(info.get("status") or info.get("workflow_status") or "").strip(),
            workflow_service=str(info.get("service") or info.get("platform") or info.get("workflow_service") or "").strip(),
            workflow_reason=str(info.get("workflow_reason") or info.get("reason") or "").strip(),
            workflow_message=str(info.get("workflow_message") or info.get("message") or "").strip(),
            workflow_resume_hint=str(info.get("workflow_resume_hint") or info.get("resume_hint") or "").strip(),
            workflow_challenge_type=str(info.get("workflow_challenge_type") or info.get("challenge_type") or "").strip(),
            workflow_approval_scope=str(info.get("workflow_approval_scope") or info.get("approval_scope") or "").strip(),
        )
    if kind == "partial_result":
        preview = str(info.get("content_preview") or info.get("preview") or "").strip()
        if not preview:
            return None
        return _emit_longrun_event(
            "partial_result",
            agent=agent,
            stage=stage,
            message=message,
            content_preview=preview,
        )
    return _emit_longrun_event(
        "progress",
        agent=agent,
        stage=stage,
        message=message,
        progress_hint=str(info.get("progress_hint") or "working").strip() or "working",
        next_expected_update_s=int(info.get("next_expected_update_s") or 15),
    )


def _append_chat_entry(*, session_id: str, role: str, text: str, ts: str, agent: str = "") -> None:
    entry = {"session_id": session_id, "role": role, "text": text, "ts": ts}
    if agent:
        entry["agent"] = agent
    with _chat_lock:
        _chat_history.append(entry)
        if len(_chat_history) > _CHAT_HISTORY_LIMIT:
            _chat_history[:] = _chat_history[-_CHAT_HISTORY_LIMIT:]
    _append_session_capsule_entry(session_id, entry)
    _semantic_store_chat_turn(session_id=session_id, role=role, text=text, ts=ts, agent=agent)


def _get_session_chat_entries(session_id: str, *, limit: int = 8) -> list[dict]:
    if not session_id:
        return []
    capsule = _load_session_capsule(session_id)
    persisted_entries = capsule.get("entries") or []
    if isinstance(persisted_entries, list) and persisted_entries:
        return [entry for entry in persisted_entries if isinstance(entry, dict)][-limit:]
    with _chat_lock:
        entries = [entry for entry in _chat_history if entry.get("session_id") == session_id]
    return entries[-limit:]


def _is_followup_query(query: str) -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    if len(normalized.split()) > 18:
        return False
    return any(re.search(pattern, normalized) for pattern in _FOLLOWUP_PATTERNS)


def _is_contextual_recall_query(query: str) -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    if len(normalized.split()) > 24:
        return False
    return any(re.search(pattern, normalized) for pattern in _CONTEXTUAL_RECALL_PATTERNS)


def _is_reference_continuation(query: str) -> bool:
    """P2: Erkennt Referenz-Pronomen wie 'damit', 'das gleiche', 'dieselbe Suche'."""
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    if len(normalized.split()) > 12:
        return False
    return any(re.search(pattern, normalized) for pattern in _REFERENCE_CONTINUATION_PATTERNS)


def _is_affirmation(query: str) -> bool:
    """P4: Erkennt kurze Zustimmungen wie 'ja', 'ok', 'ja mach das', 'schau mal danach'."""
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    if len(normalized.split()) > 8:
        return False
    return any(re.search(pattern, normalized) for pattern in _AFFIRMATION_PATTERNS)


def _is_capability_followup_query(query: str, last_assistant: str = "") -> bool:
    """Erkennt kurze Anschlussfragen zur Erweiterung fehlender Faehigkeiten."""
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    if len(normalized.split()) > 18:
        return False
    if not any(re.search(pattern, normalized) for pattern in _CAPABILITY_FOLLOWUP_PATTERNS):
        return False
    previous = str(last_assistant or "").strip().lower()
    if not previous:
        return True
    blocker_markers = (
        "ich kann keine",
        "ich kann nicht",
        "kein zugang",
        "keine zahlungsdaten",
        "keine lieferadresse",
        "keine adresse",
        "nicht verf",
        "nicht verfügbar",
    )
    return any(marker in previous for marker in blocker_markers)


def _is_result_extraction_followup_query(query: str, last_assistant: str = "") -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    if len(normalized.split()) > 18:
        return False
    if not any(re.search(pattern, normalized) for pattern in _RESULT_EXTRACTION_FOLLOWUP_PATTERNS):
        return False
    previous = str(last_assistant or "").strip().lower()
    if not previous:
        return False
    result_markers = (
        "top-treffer:",
        "direkt gepruefte quelle",
        "direkt geprüfte quelle",
        "https://",
        "http://",
    )
    return any(marker in previous for marker in result_markers)


_PROPOSAL_TRAILING_VERBS = re.compile(
    r"\s+(?:suchen|starten|machen|ausführen|ausfuehren|recherchieren|ansehen|anschauen|schauen)\s*$",
    re.IGNORECASE,
)

_PROPOSAL_AGENT_DELEGATION_RE = re.compile(
    r"(?:den|die|das)?\s*`?(?P<agent>developer|research|executor|system|shell|document|communication|data|visual|creative|reasoning|meta)`?"
    r"(?:\s*-\s*agent(?:en)?)?\s+beauftragen(?:\s*,\s*|\s+)(?P<task>.+?)(?:\s*\?.*)?$",
    re.IGNORECASE,
)

_PROPOSAL_GUIDED_ASSISTANCE_RE = re.compile(
    r"(?:soll ich|ich kann|ich könnte|ich koennte)\s+dich\s+durch\s+(?P<topic>.+?)\s+f(?:ü|ue)hren(?:\s*\?.*)?$",
    re.IGNORECASE,
)


def _clean_proposal_query(text: str) -> str:
    """Entfernt Verb-Residuen am Ende einer extrahierten Proposal-Query."""
    cleaned = _PROPOSAL_TRAILING_VERBS.sub("", text.strip()).strip(" ,.!?")
    return cleaned


def _should_prefer_pending_followup_prompt(
    proposal: dict | None,
    pending_followup_prompt: str,
) -> bool:
    """Lässt schwache Generic-Proposals hinter einer expliziten Rückfrage zurücktreten."""
    if not proposal or not pending_followup_prompt:
        return False

    kind = str(proposal.get("kind") or "").strip().lower()
    target_agent = str(proposal.get("target_agent") or "").strip()
    suggested_query = str(proposal.get("suggested_query") or "").strip()
    raw_sentence = str(proposal.get("raw_sentence") or "").strip().lower()
    pending_prompt = str(pending_followup_prompt or "").strip().lower()

    if target_agent or kind in {"agent_delegation", "youtube_search", "web_search"}:
        return False

    if len(suggested_query.split()) <= 1 or len(suggested_query) < 12:
        return True

    if "dich durch" in raw_sentence and re.search(
        r"\b(soll ich|willst du|magst du|möchtest du|moechtest du|hast du)\b",
        pending_prompt,
    ):
        return True

    return False


def _extract_proposal_metadata(text: str) -> dict | None:
    """P4: Extrahiert strukturierte ProposalMetadata aus einer Assistenten-Antwort.

    Sucht nach dem letzten Angebotsatz im Text (z.B. 'Soll ich nach YouTube-Videos
    zu KI suchen?') und gibt strukturierte Metadaten zurück:
    {kind, target, suggested_query, raw_sentence}
    """
    source = str(text or "").strip()
    if not source:
        return None

    # Nur letzten Abschnitt (letzte 3 Sätze) prüfen — Angebote stehen meist am Ende
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", source) if s.strip()]
    tail = sentences[-3:] if len(sentences) >= 3 else sentences

    for sentence in reversed(tail):
        normalized = sentence.lower()
        if not any(re.search(p, normalized) for p in _PROPOSAL_TRIGGER_PATTERNS):
            continue

        agent_delegation_match = _PROPOSAL_AGENT_DELEGATION_RE.search(sentence)
        if agent_delegation_match:
            target_agent = str(agent_delegation_match.group("agent") or "").strip("` ").lower()
            suggested = _clean_proposal_query(agent_delegation_match.group("task") or "")
            return {
                "kind": "agent_delegation",
                "target": "agent",
                "target_agent": target_agent,
                "suggested_query": suggested[:200],
                "raw_sentence": sentence[:300],
            }

        guided_match = _PROPOSAL_GUIDED_ASSISTANCE_RE.search(sentence)
        if guided_match:
            topic = _clean_proposal_query(guided_match.group("topic") or "")
            if topic and len(topic) >= 4:
                return {
                    "kind": "generic_action",
                    "target": "meta",
                    "suggested_query": f"durch {topic} führen"[:200],
                    "raw_sentence": sentence[:300],
                }

        # YouTube: sowohl "youtube zu X" als auch "X auf youtube" / "X in youtube"
        yt_match = re.search(
            r"youtube(?:[- ]?videos?)?(?:\s+zu\s+|\s+über\s+|\s+ueber\s+)([^?.!,]+)",
            normalized,
        )
        if not yt_match:
            # "X auf youtube" / "X in youtube" Variante
            yt_match_rev = re.search(
                r"([^?.!,]+?)\s+(?:auf|in|bei)\s+youtube",
                normalized,
            )
            if yt_match_rev:
                # Prefix bereinigen (soll ich / ich kann etc.)
                raw = yt_match_rev.group(1)
                raw = re.sub(
                    r"^.*?(?:soll ich|ich kann|ich könnte|ich koennte|willst du)"
                    r"(?:\s+\w+){0,4}\s+nach\s+",
                    "", raw, flags=re.IGNORECASE,
                ).strip()
                if raw and len(raw) >= 3:
                    return {
                        "kind": "youtube_search",
                        "target": "youtube",
                        "suggested_query": _clean_proposal_query(raw)[:200],
                        "raw_sentence": sentence[:300],
                    }

        if yt_match:
            return {
                "kind": "youtube_search",
                "target": "youtube",
                "suggested_query": _clean_proposal_query(yt_match.group(1))[:200],
                "raw_sentence": sentence[:300],
            }

        web_match = re.search(
            r"(?:nach\s+|zu\s+|über\s+|ueber\s+)([^?.!,]{4,})",
            normalized,
        )
        if web_match:
            suggested = _clean_proposal_query(web_match.group(1))
            if suggested and len(suggested) >= 3:
                return {
                    "kind": "web_search",
                    "target": "web",
                    "suggested_query": suggested[:200],
                    "raw_sentence": sentence[:300],
                }

        # Generisch: Inhalt nach dem Angebotsausdruck
        content_match = re.search(
            r"(?:soll ich|ich kann|ich könnte|ich koennte|willst du|magst du|möchtest du|moechtest du)"
            r"(?:\s+\w+){0,5}\s+(.+?)(?:\s*\?.*)?$",
            normalized,
        )
        if content_match:
            suggested = _clean_proposal_query(content_match.group(1))
            if suggested and len(suggested) >= 4:
                return {
                    "kind": "generic_action",
                    "target": "executor",
                    "suggested_query": suggested[:200],
                    "raw_sentence": sentence[:300],
                }

    return None


def _store_proposal_in_capsule(session_id: str, proposal: dict | None) -> None:
    """P4: Speichert oder löscht last_proposed_action in der Session-Kapsel."""
    capsule = _load_session_capsule(session_id)
    if proposal:
        capsule["last_proposed_action"] = proposal
    else:
        capsule.pop("last_proposed_action", None)
    _store_session_capsule(capsule)


def _store_pending_followup_prompt_in_capsule(session_id: str, prompt: str) -> None:
    """Speichert eine offene Rueckfrage explizit fuer den naechsten Turn."""
    capsule = _load_session_capsule(session_id)
    cleaned = normalize_pending_followup_prompt(prompt)
    if cleaned:
        capsule["pending_followup_prompt"] = cleaned[:280]
    else:
        capsule.pop("pending_followup_prompt", None)
    updated_at = str(capsule.get("last_updated") or datetime.utcnow().isoformat() + "Z")
    capsule["conversation_state"] = apply_pending_followup_prompt(
        capsule.get("conversation_state"),
        session_id=session_id,
        prompt=cleaned,
        updated_at=updated_at,
    ).to_dict()
    _store_session_capsule(capsule)


def _store_pending_workflow_in_capsule(session_id: str, workflow: dict | None, *, updated_at: str = "") -> dict:
    capsule = _load_session_capsule(session_id)
    effective_updated_at = str(updated_at or capsule.get("last_updated") or datetime.utcnow().isoformat() + "Z")
    normalized = pending_workflow_state_to_dict(
        workflow,
        updated_at=effective_updated_at,
    )
    if normalized:
        capsule["pending_workflow"] = normalized
    else:
        capsule.pop("pending_workflow", None)
    _store_session_capsule(capsule)
    return normalized


def _record_pending_workflow_runtime(
    *,
    session_id: str,
    request_id: str,
    agent_name: str,
    stage: str,
    workflow: Mapping[str, Any] | None,
    followup_capsule: Mapping[str, Any] | None,
    updated_at: str,
) -> dict[str, Any]:
    payload = dict(workflow or {})
    if not payload:
        return {}
    if not payload.get("reason") and payload.get("workflow_reason"):
        payload["reason"] = payload.get("workflow_reason")
    if not payload.get("workflow_id") and payload.get("id"):
        payload["workflow_id"] = payload.get("id")

    previous_pending_workflow = (
        followup_capsule.get("pending_workflow")
        if isinstance(followup_capsule, Mapping) and isinstance(followup_capsule.get("pending_workflow"), dict)
        else {}
    )
    previous_pending_reply = (
        followup_capsule.get("pending_workflow_reply")
        if isinstance(followup_capsule, Mapping) and isinstance(followup_capsule.get("pending_workflow_reply"), dict)
        else {}
    )
    stored_workflow = _store_pending_workflow_in_capsule(
        session_id,
        {
            **payload,
            "source_agent": agent_name,
            "source_stage": stage,
        },
        updated_at=updated_at,
    )
    if not stored_workflow:
        return {}

    _record_chat_observation(
        "pending_workflow_updated",
        {
            "request_id": request_id,
            "session_id": session_id,
            "source": "canvas_chat",
            "agent": agent_name,
            "stage": stage,
            "workflow_status": str(stored_workflow.get("status") or ""),
            "workflow_id": str(stored_workflow.get("workflow_id") or ""),
            "workflow_reason": str(stored_workflow.get("reason") or ""),
        },
    )
    if str(stored_workflow.get("status") or "").strip().lower() == "challenge_required":
        _record_chat_observation(
            "challenge_required",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "agent": agent_name,
                "stage": stage,
                "workflow_id": str(stored_workflow.get("workflow_id") or ""),
                "service": str(stored_workflow.get("service") or stored_workflow.get("platform") or ""),
                "challenge_type": str(stored_workflow.get("challenge_type") or ""),
            },
        )
        previous_status = str(previous_pending_workflow.get("status") or "").strip().lower()
        previous_reply_kind = str(previous_pending_reply.get("reply_kind") or "").strip().lower()
        if (
            previous_status in {"awaiting_user", "challenge_required"}
            and previous_reply_kind in {"resume_requested", "challenge_resolved"}
        ):
            _record_chat_observation(
                "challenge_reblocked",
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "source": "canvas_chat",
                    "agent": agent_name,
                    "stage": stage,
                    "workflow_id": str(stored_workflow.get("workflow_id") or ""),
                    "service": str(stored_workflow.get("service") or stored_workflow.get("platform") or ""),
                    "challenge_type": str(
                        stored_workflow.get("challenge_type")
                        or previous_pending_workflow.get("challenge_type")
                        or ""
                    ),
                    "reply_kind": previous_reply_kind,
                },
            )
    return stored_workflow


def _store_auth_session_in_capsule(session_id: str, auth_session: dict | None, *, updated_at: str = "") -> dict:
    capsule = _load_session_capsule(session_id)
    effective_updated_at = str(updated_at or capsule.get("last_updated") or datetime.utcnow().isoformat() + "Z")
    normalized = normalize_auth_session_entry(
        auth_session,
        session_id=session_id,
        updated_at=effective_updated_at,
    )
    if normalized:
        capsule["auth_sessions"] = upsert_auth_session_index(
            capsule.get("auth_sessions"),
            normalized.to_dict(),
            session_id=session_id,
            updated_at=effective_updated_at,
        )
    _store_session_capsule(capsule)
    return normalized.to_dict() if normalized else {}


def _log_chat_interaction(
    *,
    session_id: str,
    user_input: str,
    assistant_response: str,
    agent: str = "",
    status: str = "completed",
    metadata: dict | None = None,
) -> None:
    try:
        from memory.memory_system import memory_manager

        memory_manager.log_interaction_event(
            user_input=user_input,
            assistant_response=assistant_response,
            agent_name=agent,
            status=status,
            external_session_id=session_id,
            metadata=metadata or {},
        )
    except Exception as exc:
        log.debug(
            "Chat interaction memory logging failed for session %s: %s",
            session_id,
            exc,
        )


def _record_chat_observation(event_type: str, payload: dict) -> None:
    try:
        record_autonomy_observation(event_type, payload)
    except Exception as exc:
        log.debug("Chat observation logging failed (%s): %s", event_type, exc)


def _persist_meta_turn_understanding(
    *,
    session_id: str,
    classification: dict,
    updated_at: str,
) -> dict | None:
    if not session_id or not isinstance(classification, dict):
        return None
    capsule = _load_session_capsule(session_id)
    previous_state = conversation_state_to_dict(
        capsule.get("conversation_state"),
        session_id=session_id,
        last_updated=str(capsule.get("last_updated") or ""),
        pending_followup_prompt=str(capsule.get("pending_followup_prompt") or ""),
        decay_now=updated_at,
    )
    turn_understanding = dict(classification.get("turn_understanding") or {})
    updated_state = apply_turn_interpretation(
        previous_state,
        session_id=session_id,
        dominant_turn_type=str(classification.get("dominant_turn_type") or ""),
        response_mode=str(classification.get("response_mode") or ""),
        state_effects=turn_understanding.get("state_effects") or classification.get("state_effects") or {},
        effective_query=str(classification.get("effective_query") or ""),
        active_topic=str(classification.get("active_topic") or ""),
        active_goal=str(classification.get("open_goal") or ""),
        active_domain=str(((classification.get("meta_request_frame") or {}) if isinstance(classification.get("meta_request_frame"), dict) else {}).get("task_domain") or ""),
        dialog_constraints=classification.get("dialog_constraints") or [],
        next_step=str(classification.get("next_step") or ""),
        active_plan=classification.get("meta_execution_plan") if isinstance(classification.get("meta_execution_plan"), dict) else None,
        confidence=float(turn_understanding.get("confidence") or 0.0),
        updated_at=updated_at,
    ).to_dict()
    capsule["conversation_state"] = updated_state
    capsule["topic_history"] = update_topic_history(
        capsule.get("topic_history"),
        session_id=session_id,
        previous_state=previous_state,
        updated_state=updated_state,
        topic_transition=classification.get("topic_state_transition"),
        updated_at=updated_at,
    )
    _store_session_capsule(capsule)
    return updated_state


def _persist_meta_runtime_plan_state(
    *,
    session_id: str,
    runtime_metadata: Mapping[str, Any] | None,
    updated_at: str,
) -> dict | None:
    if not session_id or not isinstance(runtime_metadata, Mapping):
        return None
    agent_runtime = runtime_metadata.get("agent_runtime")
    if not isinstance(agent_runtime, Mapping):
        return None
    runtime_plan = agent_runtime.get("meta_runtime_plan_state")
    if not isinstance(runtime_plan, Mapping) or not runtime_plan:
        return None

    capsule = _load_session_capsule(session_id)
    previous_state = conversation_state_to_dict(
        capsule.get("conversation_state"),
        session_id=session_id,
        last_updated=str(capsule.get("last_updated") or ""),
        pending_followup_prompt=str(capsule.get("pending_followup_prompt") or ""),
        decay_now=updated_at,
    )
    updated_state = apply_runtime_plan_state(
        previous_state,
        session_id=session_id,
        active_plan=runtime_plan,
        updated_at=updated_at,
    ).to_dict()
    capsule["conversation_state"] = updated_state
    _store_session_capsule(capsule)
    return updated_state


def _capture_meta_preference_memory(
    *,
    request_id: str,
    session_id: str,
    classification: dict,
    updated_state: Mapping[str, Any] | None,
    updated_at: str,
) -> dict | None:
    if not session_id or not isinstance(classification, dict):
        return None
    try:
        from memory.memory_system import memory_manager
    except Exception:
        return None

    captured = capture_preference_memory(
        effective_query=str(classification.get("effective_query") or ""),
        session_id=session_id,
        updated_state=updated_state,
        dominant_turn_type=str(classification.get("dominant_turn_type") or ""),
        response_mode=str(classification.get("response_mode") or ""),
        memory_manager=memory_manager,
        updated_at=updated_at,
    )
    if captured:
        _record_chat_observation(
            "preference_captured",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "scope": str(captured.get("scope") or ""),
                "instruction": str(captured.get("instruction") or "")[:180],
                "topic_anchor": str(captured.get("topic_anchor") or "")[:120],
                "stability": float(captured.get("stability") or 0.0),
                "evidence_count": int(captured.get("evidence_count") or 1),
            },
        )
    return captured


def _record_meta_turn_understanding_observations(
    *,
    request_id: str,
    session_id: str,
    classification: dict,
    updated_state: dict | None = None,
) -> None:
    turn_understanding = dict(classification.get("turn_understanding") or {})
    dominant_turn_type = str(classification.get("dominant_turn_type") or "")
    response_mode = str(classification.get("response_mode") or "")
    state_effects = dict(turn_understanding.get("state_effects") or classification.get("state_effects") or {})
    meta_context_bundle = dict(classification.get("meta_context_bundle") or {})
    preference_selection = dict(classification.get("preference_memory_selection") or {})
    historical_topic_selection = dict(classification.get("historical_topic_selection") or {})
    meta_policy_decision = dict(classification.get("meta_policy_decision") or {})
    baseline_response_mode = str(turn_understanding.get("response_mode") or "")
    context_slots = meta_context_bundle.get("context_slots") or []
    slot_types: list[str] = []
    for item in context_slots:
        if not isinstance(item, dict):
            continue
        slot = str(item.get("slot") or "").strip()
        if slot and slot not in slot_types:
            slot_types.append(slot)

    _record_chat_observation(
        "meta_turn_type_selected",
        {
            "request_id": request_id,
            "session_id": session_id,
            "source": "canvas_chat",
            "dominant_turn_type": dominant_turn_type,
            "turn_signals": list(turn_understanding.get("turn_signals") or classification.get("turn_signals") or []),
            "route_bias": str(turn_understanding.get("route_bias") or ""),
            "confidence": float(turn_understanding.get("confidence") or 0.0),
            "effective_query_preview": str(classification.get("effective_query") or "")[:180],
        },
    )
    _record_chat_observation(
        "meta_response_mode_selected",
        {
            "request_id": request_id,
            "session_id": session_id,
            "source": "canvas_chat",
            "dominant_turn_type": dominant_turn_type,
            "response_mode": response_mode,
            "reason": str(classification.get("reason") or ""),
        },
    )
    if meta_policy_decision:
        _record_chat_observation(
            "meta_policy_mode_selected",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "response_mode": str(meta_policy_decision.get("response_mode") or response_mode),
                "policy_reason": str(meta_policy_decision.get("policy_reason") or ""),
                "policy_confidence": float(meta_policy_decision.get("policy_confidence") or 0.0),
                "answer_shape": str(meta_policy_decision.get("answer_shape") or ""),
                "should_delegate": bool(meta_policy_decision.get("should_delegate")),
                "should_store_preference": bool(meta_policy_decision.get("should_store_preference")),
                "should_resume_open_loop": bool(meta_policy_decision.get("should_resume_open_loop")),
                "should_summarize_state": bool(meta_policy_decision.get("should_summarize_state")),
                "override_applied": bool(meta_policy_decision.get("override_applied")),
                "policy_signals": list(meta_policy_decision.get("policy_signals") or []),
            },
        )
        if bool(meta_policy_decision.get("override_applied")):
            _record_chat_observation(
                "meta_policy_override_applied",
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "source": "canvas_chat",
                    "baseline_response_mode": baseline_response_mode,
                    "final_response_mode": str(meta_policy_decision.get("response_mode") or response_mode),
                    "policy_reason": str(meta_policy_decision.get("policy_reason") or ""),
                    "task_type_override": str(meta_policy_decision.get("task_type_override") or ""),
                    "agent_chain_override": list(meta_policy_decision.get("agent_chain_override") or []),
                },
            )
        if bool(meta_policy_decision.get("self_model_bound_applied")):
            _record_chat_observation(
                "meta_policy_self_model_bound_applied",
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "source": "canvas_chat",
                    "response_mode": str(meta_policy_decision.get("response_mode") or response_mode),
                    "policy_reason": str(meta_policy_decision.get("policy_reason") or ""),
                    "answer_shape": str(meta_policy_decision.get("answer_shape") or ""),
                    "policy_signals": list(meta_policy_decision.get("policy_signals") or []),
                },
            )
    _record_chat_observation(
        "conversation_state_effects_derived",
        {
            "request_id": request_id,
            "session_id": session_id,
            "source": "canvas_chat",
            "dominant_turn_type": dominant_turn_type,
            "response_mode": response_mode,
            "state_effects": state_effects,
        },
    )
    _record_chat_observation(
        "context_rehydration_bundle_built",
        {
            "request_id": request_id,
            "session_id": session_id,
            "source": "canvas_chat",
            "dominant_turn_type": dominant_turn_type,
            "response_mode": response_mode,
            "bundle_reason": str(meta_context_bundle.get("bundle_reason") or ""),
            "slot_types": slot_types,
            "slot_count": len(slot_types),
            "suppressed_count": int(classification.get("meta_context_suppressed_count") or 0),
            "confidence": float(meta_context_bundle.get("confidence") or 0.0),
            "active_topic": str(meta_context_bundle.get("active_topic") or "")[:180],
            "open_loop": str(meta_context_bundle.get("open_loop") or "")[:180],
        },
    )
    for item in context_slots:
        if not isinstance(item, dict):
            continue
        _record_chat_observation(
            "context_slot_selected",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "slot": str(item.get("slot") or ""),
                "priority": int(item.get("priority") or 0),
                "slot_source": str(item.get("source") or ""),
                "content_preview": str(item.get("content") or "")[:180],
            },
        )
    for item in meta_context_bundle.get("suppressed_context") or []:
        if not isinstance(item, dict):
            continue
        _record_chat_observation(
            "context_slot_suppressed",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "slot_source": str(item.get("source") or ""),
                "reason": str(item.get("reason") or ""),
                "content_preview": str(item.get("content_preview") or "")[:180],
            },
        )
    if "open_loop" in slot_types:
        _record_chat_observation(
            "open_loop_attached",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "dominant_turn_type": dominant_turn_type,
                "open_loop": str(meta_context_bundle.get("open_loop") or "")[:180],
                "next_expected_step": str(meta_context_bundle.get("next_expected_step") or "")[:180],
            },
        )
    if "topic_memory" in slot_types:
        _record_chat_observation(
            "topic_memory_attached",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "dominant_turn_type": dominant_turn_type,
                "slot_count": slot_types.count("topic_memory"),
            },
        )
    if "historical_topic_memory" in slot_types:
        _record_chat_observation(
            "historical_topic_attached",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "dominant_turn_type": dominant_turn_type,
                "time_label": str(historical_topic_selection.get("time_label") or ""),
                "fallback_source": str(historical_topic_selection.get("fallback_source") or ""),
                "slot_count": slot_types.count("historical_topic_memory"),
                "history_size": int(historical_topic_selection.get("history_size") or 0),
            },
        )
    if "preference_memory" in slot_types:
        _record_chat_observation(
            "preference_memory_attached",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "dominant_turn_type": dominant_turn_type,
                "slot_count": slot_types.count("preference_memory"),
                },
            )
        for item in preference_selection.get("selected_details") or []:
            if not isinstance(item, dict):
                continue
            _record_chat_observation(
                "preference_scope_selected",
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "source": "canvas_chat",
                    "scope": str(item.get("scope") or ""),
                    "family": str(item.get("family") or ""),
                    "stability": float(item.get("stability") or 0.0),
                    "evidence_count": int(item.get("evidence_count") or 1),
                    "content_preview": str(item.get("rendered") or "")[:180],
                },
            )
        for item in preference_selection.get("ignored_low_stability") or []:
            if not isinstance(item, dict):
                continue
            _record_chat_observation(
                "preference_ignored_low_stability",
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "source": "canvas_chat",
                    "scope": str(item.get("scope") or ""),
                    "family": str(item.get("family") or ""),
                    "reason": str(item.get("reason") or ""),
                    "stability": float(item.get("stability") or 0.0),
                    "evidence_count": int(item.get("evidence_count") or 1),
                    "content_preview": str(item.get("rendered") or "")[:180],
                },
            )
        for item in preference_selection.get("conflicts_resolved") or []:
            if not isinstance(item, dict):
                continue
            _record_chat_observation(
                "preference_conflict_resolved",
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "source": "canvas_chat",
                    "family": str(item.get("family") or ""),
                    "kept_scope": str(item.get("kept_scope") or ""),
                    "discarded_scope": str(item.get("discarded_scope") or ""),
                    "reason": str(item.get("reason") or ""),
                    "kept_preview": str(item.get("kept_rendered") or "")[:180],
                    "discarded_preview": str(item.get("discarded_rendered") or "")[:180],
                },
            )
        stored_preference_slots = [
            item
            for item in context_slots
            if isinstance(item, dict)
            and str(item.get("slot") or "") == "preference_memory"
            and str(item.get("content") or "").startswith("stored_preference:")
        ]
        if stored_preference_slots:
            _record_chat_observation(
                "preference_applied",
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "source": "canvas_chat",
                    "dominant_turn_type": dominant_turn_type,
                    "slot_count": len(stored_preference_slots),
                    "content_preview": str(stored_preference_slots[0].get("content") or "")[:180],
                },
            )
    risk = detect_context_misread_risk(
        meta_context_bundle,
        dominant_turn_type=dominant_turn_type,
        response_mode=response_mode,
    )
    if risk.get("suspicious"):
        _record_chat_observation(
            "context_misread_suspected",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "dominant_turn_type": dominant_turn_type,
                "response_mode": response_mode,
                "risk_reasons": list(risk.get("reasons") or []),
                "slot_types": list(risk.get("slot_types") or []),
                "suppressed_reasons": list(risk.get("suppressed_reasons") or []),
            },
        )
    topic_transition = dict(classification.get("topic_state_transition") or {})
    if bool(classification.get("topic_shift_detected")):
        _record_chat_observation(
            "topic_shift_detected",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "previous_topic": str(topic_transition.get("previous_topic") or "")[:180],
                "next_topic": str(topic_transition.get("next_topic") or "")[:180],
                "previous_goal": str(topic_transition.get("previous_goal") or "")[:180],
                "next_goal": str(topic_transition.get("next_goal") or "")[:180],
                "open_loop_state": str(topic_transition.get("open_loop_state") or ""),
            },
        )
    if isinstance(updated_state, dict):
        _record_chat_observation(
            "conversation_state_updated",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "active_topic": str(updated_state.get("active_topic") or "")[:180],
                "active_goal": str(updated_state.get("active_goal") or "")[:180],
                "open_loop": str(updated_state.get("open_loop") or "")[:180],
                "next_expected_step": str(updated_state.get("next_expected_step") or "")[:180],
                "open_questions_count": len(updated_state.get("open_questions") or []),
                "turn_type_hint": str(updated_state.get("turn_type_hint") or ""),
            },
        )


def _tokenize_followup_focus(text: str) -> list[str]:
    normalized = str(text or "").lower()
    tokens = re.findall(r"[a-zA-Z0-9äöüÄÖÜß_-]+", normalized)
    cleaned: list[str] = []
    for token in tokens:
        stripped = token.strip("_-")
        if len(stripped) < 3:
            continue
        if stripped in _FOLLOWUP_TOPIC_STOPWORDS:
            continue
        cleaned.append(stripped)
    return cleaned


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        return int(raw)
    except Exception:
        return default


def _chat_location_context_enabled() -> bool:
    return _env_bool("TIMUS_CHAT_LOCATION_CONTEXT_ENABLED", True)


def _location_live_reroute_enabled() -> bool:
    return _env_bool("TIMUS_LOCATION_ROUTE_LIVE_REROUTE_ENABLED", True)


def _location_route_reroute_min_distance_meters() -> int:
    return max(25, _env_int("TIMUS_LOCATION_ROUTE_REROUTE_MIN_DISTANCE_METERS", 150))


def _location_route_reroute_min_interval_seconds() -> int:
    return max(0, _env_int("TIMUS_LOCATION_ROUTE_REROUTE_MIN_INTERVAL_SECONDS", 120))


def _extract_assistant_reply_points(text: str) -> list[str]:
    source = str(text or "").strip()
    if not source:
        return []

    candidates: list[str] = []
    for raw_line in source.splitlines():
        line = re.sub(r"^\s*(?:[-*•]\s*|\d+\.\s*)", "", raw_line).strip()
        if not line:
            continue
        if line.endswith(":"):
            continue
        if len(line) >= 18:
            candidates.append(line)

    if not candidates:
        for sentence in re.split(r"(?<=[.!?])\s+", source):
            sentence = sentence.strip(" -\t\r\n")
            if len(sentence) >= 18:
                candidates.append(sentence)

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique[:10]


def _match_assistant_reply_points(query: str, replies: list[str]) -> list[str]:
    focus_tokens = _tokenize_followup_focus(query)
    if not focus_tokens:
        return []

    scored: list[tuple[int, int, str]] = []
    for reply in replies:
        for point in _extract_assistant_reply_points(reply):
            lowered = point.lower()
            match_count = sum(1 for token in focus_tokens if token in lowered)
            if match_count <= 0:
                continue
            scored.append((match_count, len(point), point))

    scored.sort(key=lambda item: (-item[0], item[1]))
    matched: list[str] = []
    seen_points: set[str] = set()
    for _, _, point in scored:
        key = point.lower()
        if key in seen_points:
            continue
        seen_points.add(key)
        matched.append(point)
        if len(matched) >= 4:
            break
    return matched


def _extract_pending_followup_prompt(text: str) -> str:
    source = str(text or "").strip()
    if not source:
        return ""

    lines = [line.strip() for line in source.splitlines() if line.strip()]
    question_like: list[str] = []
    for line in lines:
        cleaned = re.sub(r"^\s*(?:[-*•]\s*|\d+\.\s*)", "", line).strip()
        if len(cleaned) < 12:
            continue
        lowered = cleaned.lower()
        if "?" in cleaned:
            question_like.append(cleaned)
            continue
        if re.search(r"\b(soll ich|willst du|magst du|möchtest du|moechtest du|welchen schritt|was soll ich)\b", lowered):
            question_like.append(cleaned)

    if question_like:
        return normalize_pending_followup_prompt(question_like[-1][:280])

    sentences = [part.strip(" -\t\r\n") for part in re.split(r"(?<=[.!?])\s+", source) if part.strip()]
    for sentence in reversed(sentences):
        lowered = sentence.lower()
        if "?" in sentence or re.search(r"\b(soll ich|willst du|magst du|möchtest du|moechtest du)\b", lowered):
            return normalize_pending_followup_prompt(sentence[:280])
    return ""


def _extract_phase_d_workflow_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}

    direct_workflow = normalize_phase_d_workflow_payload(raw)
    if direct_workflow:
        return direct_workflow

    top_level_workflow = raw.get("phase_d_workflow")
    if isinstance(top_level_workflow, Mapping):
        nested_workflow = normalize_phase_d_workflow_payload(top_level_workflow)
        if nested_workflow:
            return nested_workflow

    metadata = raw.get("metadata")
    if isinstance(metadata, Mapping):
        nested_workflow = normalize_phase_d_workflow_payload(metadata.get("phase_d_workflow"))
        if nested_workflow:
            return nested_workflow

    return {}


def _render_phase_d_workflow_reply(raw: Any) -> tuple[str, dict[str, Any] | None]:
    if not isinstance(raw, Mapping):
        return "", None

    workflow = _extract_phase_d_workflow_payload(raw)
    status = str(workflow.get("status") or "").strip().lower()
    if status not in {"approval_required", "auth_required", "awaiting_user", "challenge_required"}:
        return "", None

    message = str(
        workflow.get("message")
        or raw.get("message")
        or raw.get("error")
        or raw.get("result")
        or ""
    ).strip()
    user_action = str(workflow.get("user_action_required") or "").strip()
    resume_hint = str(workflow.get("resume_hint") or "").strip()
    service = str(workflow.get("service") or workflow.get("platform") or "").strip()
    url = str(workflow.get("url") or "").strip()

    parts: list[str] = []
    if message:
        parts.append(message)
    if user_action:
        parts.append(f"Naechster Schritt: {user_action}")
    if resume_hint:
        parts.append(f"Danach: {resume_hint}")
    if url and status in {"auth_required", "awaiting_user", "challenge_required"}:
        label = service or "Login"
        parts.append(f"Seite: {label} -> {url}")

    rendered = "\n\n".join(part for part in parts if part).strip()
    return rendered or str(message or user_action or resume_hint or status), workflow


def _render_chat_reply(raw: Any) -> tuple[str, dict[str, Any] | None]:
    rendered_workflow_reply, workflow = _render_phase_d_workflow_reply(raw)
    if rendered_workflow_reply:
        return rendered_workflow_reply, workflow
    if raw is None:
        return "(keine Antwort)", None
    return str(raw), None


def _build_challenge_resume_observation_payload(capsule: dict[str, Any]) -> dict[str, str]:
    pending_workflow = capsule.get("pending_workflow") if isinstance(capsule.get("pending_workflow"), dict) else {}
    pending_workflow_reply = capsule.get("pending_workflow_reply") if isinstance(capsule.get("pending_workflow_reply"), dict) else {}
    if not pending_workflow or not pending_workflow_reply:
        return {}

    status = str(pending_workflow.get("status") or "").strip().lower()
    reason = str(pending_workflow.get("reason") or "").strip().lower()
    reply_kind = str(pending_workflow_reply.get("reply_kind") or "").strip().lower()
    if not reply_kind:
        return {}

    is_direct_challenge_resume = status == "challenge_required"
    is_login_challenge_resume = (
        status == "awaiting_user"
        and reply_kind in {"challenge_present", "challenge_resolved"}
    )
    if not (is_direct_challenge_resume or is_login_challenge_resume):
        return {}

    return {
        "workflow_id": str(pending_workflow.get("workflow_id") or "").strip(),
        "workflow_status": status,
        "workflow_reason": reason,
        "service": str(pending_workflow.get("service") or pending_workflow.get("platform") or "").strip().lower(),
        "challenge_type": str(
            pending_workflow.get("challenge_type")
            or pending_workflow_reply.get("challenge_type")
            or ""
        ).strip().lower(),
        "reply_kind": reply_kind,
        "source_agent": str(
            pending_workflow_reply.get("source_agent")
            or pending_workflow.get("source_agent")
            or ""
        ).strip().lower(),
    }


def _is_short_contextual_reply(query: str, capsule: dict) -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    if len(normalized.split()) > 12:
        return False
    pending_prompt = str(capsule.get("pending_followup_prompt") or "").strip()
    pending_workflow = capsule.get("pending_workflow") if isinstance(capsule.get("pending_workflow"), dict) else {}
    if not pending_prompt and not capsule.get("last_proposed_action") and not pending_workflow:
        return False
    if any(re.search(pattern, normalized) for pattern in _AFFIRMATION_PATTERNS):
        return True
    if any(re.search(pattern, normalized) for pattern in _SHORT_CONTEXTUAL_REPLY_PATTERNS):
        return True
    return any(re.search(pattern, normalized) for pattern in _DEFERRED_CONTEXTUAL_REPLY_PATTERNS)


def _build_followup_capsule(session_id: str, query: str = "") -> dict:
    capsule = _load_session_capsule(session_id)
    decay_now = datetime.utcnow().isoformat() + "Z"
    entries = _get_session_chat_entries(session_id, limit=16)
    last_user = ""
    last_assistant = ""
    last_agent = ""
    recent_user_queries: list[str] = []
    recent_assistant_replies: list[str] = []
    recent_agents: list[str] = []

    for entry in reversed(entries):
        role = str(entry.get("role") or "")
        if not last_assistant and role == "assistant":
            last_assistant = str(entry.get("text") or "").strip()
            last_agent = str(entry.get("agent") or "").strip()
        elif last_assistant and role == "user":
            last_user = str(entry.get("text") or "").strip()
            break

    for entry in entries:
        role = str(entry.get("role") or "").strip()
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        if role == "user":
            recent_user_queries.append(text[:180])
        elif role == "assistant":
            recent_assistant_replies.append(text[:220])
            agent = str(entry.get("agent") or "").strip()
            if agent:
                recent_agents.append(agent)

    semantic_recall = _semantic_recall_chat_turns(
        session_id=session_id,
        query=query,
        exclude_texts=[
            last_user,
            last_assistant,
            *recent_user_queries,
            *recent_assistant_replies,
        ],
    )
    matched_reply_points = _match_assistant_reply_points(
        query,
        [last_assistant, *recent_assistant_replies],
    )

    # P2: Referenz-Fortsetzung — kein Topic in Query, aber "damit"/"das gleiche"
    # → vorherige Assistenten-Antwort direkt als Kontext setzen
    is_ref = _is_reference_continuation(query)
    inherited_topic_recall: list[str] = []
    if is_ref and not matched_reply_points and last_assistant:
        inherited_topic_recall = _extract_assistant_reply_points(last_assistant)[:4]

    # P4: gespeichertes Angebot aus Kapsel lesen
    last_proposed_action: dict | None = capsule.get("last_proposed_action") or None
    pending_followup_prompt = str(capsule.get("pending_followup_prompt") or "").strip()
    pending_workflow = capsule.get("pending_workflow") if isinstance(capsule.get("pending_workflow"), dict) else {}
    pending_workflow_reply = classify_pending_workflow_reply(query, pending_workflow)
    if not pending_followup_prompt and last_assistant:
        pending_followup_prompt = _extract_pending_followup_prompt(last_assistant)
    conversation_state, conversation_state_decay = decay_conversation_state(
        capsule.get("conversation_state"),
        session_id=session_id,
        last_updated=str(capsule.get("last_updated") or ""),
        pending_followup_prompt=pending_followup_prompt,
        now=decay_now,
    )
    topic_history = topic_history_to_list(
        capsule.get("topic_history"),
        session_id=session_id,
        now=decay_now,
    )
    auth_sessions = auth_session_index_to_dict(
        capsule.get("auth_sessions"),
        session_id=session_id,
        updated_at=str(capsule.get("last_updated") or ""),
    )

    return {
        "session_id": session_id,
        "last_user": last_user,
        "last_assistant": last_assistant,
        "last_agent": last_agent,
        "session_summary": str(capsule.get("summary") or "").strip(),
        "recent_user_queries": recent_user_queries[-3:],
        "recent_assistant_replies": recent_assistant_replies[-3:],
        "recent_agents": recent_agents[-3:],
        "matched_reply_points": matched_reply_points,
        "inherited_topic_recall": inherited_topic_recall,
        "pending_followup_prompt": pending_followup_prompt,
        "last_proposed_action": last_proposed_action,
        "pending_workflow": capsule.get("pending_workflow") or {},
        "pending_workflow_reply": pending_workflow_reply,
        "auth_sessions": auth_sessions,
        "latest_auth_session": latest_auth_session_from_index(auth_sessions),
        "semantic_recall": semantic_recall,
        "conversation_state": conversation_state.to_dict(),
        "conversation_state_decay": conversation_state_decay,
        "topic_history": topic_history,
    }


def _resolve_followup_agent(query: str, capsule: dict[str, str]) -> str:
    normalized = str(query or "").strip().lower()
    is_followup = _is_followup_query(normalized)
    is_contextual_recall = _is_contextual_recall_query(normalized)
    is_short_contextual_reply = _is_short_contextual_reply(normalized, capsule)
    is_capability_followup = _is_capability_followup_query(
        normalized,
        str(capsule.get("last_assistant") or ""),
    )
    is_result_extraction_followup = _is_result_extraction_followup_query(
        normalized,
        str(capsule.get("last_assistant") or ""),
    )
    pending_workflow_reply = capsule.get("pending_workflow_reply") if isinstance(capsule.get("pending_workflow_reply"), dict) else {}
    has_pending_workflow_resume = bool(str(pending_workflow_reply.get("reply_kind") or "").strip())
    if not (
        is_followup
        or is_contextual_recall
        or is_short_contextual_reply
        or is_capability_followup
        or is_result_extraction_followup
        or has_pending_workflow_resume
    ):
        return ""
    matched_reply_points = capsule.get("matched_reply_points") or []
    last_agent = str(capsule.get("last_agent") or "").strip().lower()
    pending_workflow = capsule.get("pending_workflow") if isinstance(capsule.get("pending_workflow"), dict) else {}
    pending_source_agent = str(pending_workflow.get("source_agent") or "").strip().lower()
    pending_status = str(pending_workflow.get("status") or "").strip().lower()
    pending_reason = str(pending_workflow.get("reason") or "").strip().lower()
    pending_reply_kind = str(pending_workflow_reply.get("reply_kind") or "").strip().lower()
    if (
        pending_source_agent
        and (
            (
                pending_status == "awaiting_user"
                and pending_reply_kind in {"resume_requested", "challenge_present", "resume_blocked", "challenge_resolved"}
            )
            or (
                pending_status == "challenge_required"
                and pending_reply_kind in {"resume_requested", "challenge_present", "resume_blocked", "challenge_resolved"}
            )
        )
    ):
        return pending_source_agent
    if not last_agent:
        return ""
    if is_capability_followup:
        return "executor"
    if is_result_extraction_followup and last_agent:
        return last_agent
    if is_contextual_recall and matched_reply_points:
        return "executor"
    if is_short_contextual_reply and last_agent:
        return last_agent
    if last_agent == "executor":
        return "executor"
    if last_agent in {"system", "research", "communication", "document", "data"}:
        return last_agent
    if last_agent in {"visual", "visual_nemotron"}:
        if any(token in normalized for token in _VISUAL_INTENT_TOKENS):
            return last_agent
        return "meta"
    return last_agent if last_agent == "meta" else ""


def _resolve_resolved_proposal_agent(dispatcher_query: str) -> str:
    """Leitet RESOLVED_PROPOSAL-Anfragen auf den passenden Entry-Agenten."""
    if not str(dispatcher_query or "").startswith("# RESOLVED_PROPOSAL"):
        return ""

    kind_match = re.search(r"^kind:\s*(\S+)", dispatcher_query, re.MULTILINE)
    proposal_kind = str(kind_match.group(1) if kind_match else "generic_action").strip().lower()

    target_agent_match = re.search(r"^target_agent:\s*(\S+)", dispatcher_query, re.MULTILINE)
    target_agent = str(target_agent_match.group(1) if target_agent_match else "").strip().lower()

    raw_proposal_match = re.search(r"^raw_proposal:\s*(.+)$", dispatcher_query, re.MULTILINE)
    raw_proposal = str(raw_proposal_match.group(1) if raw_proposal_match else "").strip().lower()

    if target_agent:
        return "meta"
    if proposal_kind == "agent_delegation":
        return "meta"
    if "agent" in raw_proposal and "beauftragen" in raw_proposal:
        return "meta"
    if proposal_kind in {"youtube_search", "web_search"}:
        return "executor"
    return "meta"


def _augment_query_with_followup_capsule(query: str, capsule: dict) -> str:
    is_ref = _is_reference_continuation(query)
    is_affirm = _is_affirmation(query)
    is_followup = _is_followup_query(query)
    is_recall = _is_contextual_recall_query(query)
    is_short_contextual_reply = _is_short_contextual_reply(query, capsule)
    is_capability_followup = _is_capability_followup_query(
        query,
        str(capsule.get("last_assistant") or ""),
    )
    is_result_extraction_followup = _is_result_extraction_followup_query(
        query,
        str(capsule.get("last_assistant") or ""),
    )

    last_proposed_action: dict | None = capsule.get("last_proposed_action") or None
    pending_followup_prompt = str(capsule.get("pending_followup_prompt") or "").strip()
    pending_workflow = capsule.get("pending_workflow") if isinstance(capsule.get("pending_workflow"), dict) else {}
    pending_workflow_reply = capsule.get("pending_workflow_reply") if isinstance(capsule.get("pending_workflow_reply"), dict) else {}
    has_pending_workflow_resume = bool(str(pending_workflow_reply.get("reply_kind") or "").strip())
    latest_auth_session = capsule.get("latest_auth_session") if isinstance(capsule.get("latest_auth_session"), dict) else {}

    # P4: Kurze Zustimmung + gespeichertes Angebot → direkt auflösen
    if is_affirm and last_proposed_action and not _should_prefer_pending_followup_prompt(
        last_proposed_action,
        pending_followup_prompt,
    ):
        kind = str(last_proposed_action.get("kind") or "generic_action")
        target_agent = str(last_proposed_action.get("target_agent") or "").strip()
        suggested_query = str(last_proposed_action.get("suggested_query") or "").strip()
        raw_sentence = str(last_proposed_action.get("raw_sentence") or "").strip()
        parts = [
            "# RESOLVED_PROPOSAL",
            f"kind: {kind}",
        ]
        if target_agent:
            parts.append(f"target_agent: {target_agent}")
        parts.extend([
            f"suggested_query: {suggested_query}",
            f"raw_proposal: {raw_sentence[:200]}",
            "",
            "# CURRENT USER QUERY",
            query,
        ])
        return "\n".join(parts)

    # P2/P3/normale Follow-up: Kontext aufbauen
    if not (
        is_followup
        or is_recall
        or is_ref
        or is_short_contextual_reply
        or is_capability_followup
        or is_result_extraction_followup
        or has_pending_workflow_resume
    ):
        return query

    last_agent = str(capsule.get("last_agent") or "").strip()
    session_id = str(capsule.get("session_id") or "").strip()
    last_user = str(capsule.get("last_user") or "").strip()
    last_assistant = str(capsule.get("last_assistant") or "").strip()
    session_summary = str(capsule.get("session_summary") or "").strip()
    recent_user_queries = capsule.get("recent_user_queries") or []
    recent_assistant_replies = capsule.get("recent_assistant_replies") or []
    recent_agents = capsule.get("recent_agents") or []
    matched_reply_points = capsule.get("matched_reply_points") or []
    inherited_topic_recall = capsule.get("inherited_topic_recall") or []
    semantic_recall = capsule.get("semantic_recall") or []
    conversation_state = capsule.get("conversation_state") or {}

    if not (
        last_agent
        or last_user
        or last_assistant
        or session_summary
        or recent_user_queries
        or recent_assistant_replies
        or matched_reply_points
        or inherited_topic_recall
        or semantic_recall
        or pending_followup_prompt
        or pending_workflow
        or conversation_state
    ):
        return query

    parts = ["# FOLLOW-UP CONTEXT"]
    if last_agent:
        parts.append(f"last_agent: {last_agent}")
    if session_id:
        parts.append(f"session_id: {session_id}")
    if last_user:
        parts.append(f"last_user: {last_user[:300]}")
    if last_assistant:
        parts.append(f"last_assistant: {last_assistant[:900]}")
    if session_summary:
        parts.append(f"session_summary: {session_summary[:1600]}")
    if recent_agents:
        parts.append("recent_agents: " + " | ".join(str(agent) for agent in recent_agents[:3]))
    if recent_user_queries:
        parts.append("recent_user_queries: " + " || ".join(str(text) for text in recent_user_queries[:3]))
    if recent_assistant_replies:
        parts.append(
            "recent_assistant_replies: "
            + " || ".join(str(text) for text in recent_assistant_replies[:3])
        )
    # matched_reply_points hat Vorrang; inherited_topic_recall ist Fallback für P2
    effective_recall = matched_reply_points or inherited_topic_recall
    if effective_recall:
        parts.append(
            "topic_recall: "
            + " || ".join(str(text)[:240] for text in effective_recall[:4])
        )
    if semantic_recall:
        recall_lines = []
        for item in semantic_recall[:4]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip() or "unknown"
            agent = str(item.get("agent") or "").strip()
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            label = f"{role}:{agent}" if agent else role
            recall_lines.append(f"{label} => {text[:220]}")
        if recall_lines:
            parts.append("semantic_recall: " + " || ".join(recall_lines))
    if pending_followup_prompt:
        parts.append(f"pending_followup_prompt: {pending_followup_prompt[:320]}")
    if isinstance(pending_workflow, dict) and pending_workflow:
        workflow_id = str(pending_workflow.get("workflow_id") or "").strip()
        workflow_status = str(pending_workflow.get("status") or "").strip()
        workflow_service = str(pending_workflow.get("service") or pending_workflow.get("platform") or "").strip()
        workflow_reason = str(pending_workflow.get("reason") or "").strip()
        workflow_message = str(pending_workflow.get("message") or "").strip()
        workflow_user_action = str(pending_workflow.get("user_action_required") or "").strip()
        workflow_resume_hint = str(pending_workflow.get("resume_hint") or "").strip()
        workflow_challenge_type = str(pending_workflow.get("challenge_type") or "").strip()
        workflow_domain = str(pending_workflow.get("domain") or "").strip()
        workflow_preferred_browser = str(pending_workflow.get("preferred_browser") or "").strip()
        workflow_credential_broker = str(pending_workflow.get("credential_broker") or "").strip()
        workflow_broker_profile = str(pending_workflow.get("broker_profile") or "").strip()
        if workflow_id:
            parts.append(f"pending_workflow_id: {workflow_id[:64]}")
        if workflow_status:
            parts.append(f"pending_workflow_status: {workflow_status[:64]}")
        if workflow_service:
            parts.append(f"pending_workflow_service: {workflow_service[:64]}")
        if workflow_reason:
            parts.append(f"pending_workflow_reason: {workflow_reason[:96]}")
        if workflow_message:
            parts.append(f"pending_workflow_message: {workflow_message[:280]}")
        if workflow_user_action:
            parts.append(f"pending_workflow_user_action_required: {workflow_user_action[:280]}")
        if workflow_resume_hint:
            parts.append(f"pending_workflow_resume_hint: {workflow_resume_hint[:220]}")
        if workflow_challenge_type:
            parts.append(f"pending_workflow_challenge_type: {workflow_challenge_type[:64]}")
        if workflow_domain:
            parts.append(f"pending_workflow_domain: {workflow_domain[:160]}")
        if workflow_preferred_browser:
            parts.append(f"pending_workflow_preferred_browser: {workflow_preferred_browser[:32]}")
        if workflow_credential_broker:
            parts.append(f"pending_workflow_credential_broker: {workflow_credential_broker[:64]}")
        if workflow_broker_profile:
            parts.append(f"pending_workflow_broker_profile: {workflow_broker_profile[:96]}")
        workflow_url = str(pending_workflow.get("url") or "").strip()
        workflow_source_agent = str(pending_workflow.get("source_agent") or "").strip()
        workflow_source_stage = str(pending_workflow.get("source_stage") or "").strip()
        if workflow_url:
            parts.append(f"pending_workflow_url: {workflow_url[:320]}")
        if workflow_source_agent:
            parts.append(f"pending_workflow_source_agent: {workflow_source_agent[:64]}")
        if workflow_source_stage:
            parts.append(f"pending_workflow_source_stage: {workflow_source_stage[:96]}")
    if isinstance(pending_workflow_reply, dict) and pending_workflow_reply:
        reply_kind = str(pending_workflow_reply.get("reply_kind") or "").strip()
        if reply_kind:
            parts.append(f"pending_workflow_reply_kind: {reply_kind[:64]}")
    if isinstance(latest_auth_session, dict) and latest_auth_session:
        auth_service = str(latest_auth_session.get("service") or "").strip()
        auth_status = str(latest_auth_session.get("status") or "").strip()
        auth_scope = str(latest_auth_session.get("scope") or "").strip()
        auth_url = str(latest_auth_session.get("url") or "").strip()
        auth_confirmed = str(latest_auth_session.get("confirmed_at") or "").strip()
        auth_expires = str(latest_auth_session.get("expires_at") or "").strip()
        auth_browser_type = str(latest_auth_session.get("browser_type") or "").strip()
        auth_credential_broker = str(latest_auth_session.get("credential_broker") or "").strip()
        auth_broker_profile = str(latest_auth_session.get("broker_profile") or "").strip()
        auth_domain = str(latest_auth_session.get("domain") or "").strip()
        if auth_service:
            parts.append(f"auth_session_service: {auth_service[:64]}")
        if auth_status:
            parts.append(f"auth_session_status: {auth_status[:64]}")
        if auth_scope:
            parts.append(f"auth_session_scope: {auth_scope[:32]}")
        if auth_url:
            parts.append(f"auth_session_url: {auth_url[:320]}")
        if auth_confirmed:
            parts.append(f"auth_session_confirmed_at: {auth_confirmed[:64]}")
        if auth_expires:
            parts.append(f"auth_session_expires_at: {auth_expires[:64]}")
        if auth_browser_type:
            parts.append(f"auth_session_browser_type: {auth_browser_type[:32]}")
        if auth_credential_broker:
            parts.append(f"auth_session_credential_broker: {auth_credential_broker[:64]}")
        if auth_broker_profile:
            parts.append(f"auth_session_broker_profile: {auth_broker_profile[:96]}")
        if auth_domain:
            parts.append(f"auth_session_domain: {auth_domain[:160]}")
    if isinstance(conversation_state, dict):
        active_topic = str(conversation_state.get("active_topic") or "").strip()
        active_goal = str(conversation_state.get("active_goal") or "").strip()
        active_domain = str(conversation_state.get("active_domain") or "").strip()
        open_loop = str(conversation_state.get("open_loop") or "").strip()
        next_expected_step = str(conversation_state.get("next_expected_step") or "").strip()
        turn_type_hint = str(conversation_state.get("turn_type_hint") or "").strip()
        preferences = [
            str(item).strip()
            for item in (conversation_state.get("preferences") or [])
            if str(item).strip()
        ]
        recent_corrections = [
            str(item).strip()
            for item in (conversation_state.get("recent_corrections") or [])
            if str(item).strip()
        ]
        active_plan = conversation_state.get("active_plan") if isinstance(conversation_state.get("active_plan"), dict) else {}
        if active_topic:
            parts.append(f"conversation_state_active_topic: {active_topic[:240]}")
        if active_goal:
            parts.append(f"conversation_state_active_goal: {active_goal[:240]}")
        if active_domain:
            parts.append(f"conversation_state_active_domain: {active_domain[:64]}")
        if open_loop:
            parts.append(f"conversation_state_open_loop: {open_loop[:240]}")
        if next_expected_step:
            parts.append(f"conversation_state_next_expected_step: {next_expected_step[:240]}")
        if turn_type_hint:
            parts.append(f"conversation_state_turn_type_hint: {turn_type_hint[:64]}")
        if preferences:
            parts.append(
                "conversation_state_preferences: "
                + " || ".join(item[:140] for item in preferences[:4])
            )
        if recent_corrections:
            parts.append(
                "conversation_state_recent_corrections: "
                + " || ".join(item[:140] for item in recent_corrections[:4])
            )
        if isinstance(active_plan, dict):
            plan_id = str(active_plan.get("plan_id") or "").strip()
            plan_mode = str(active_plan.get("plan_mode") or "").strip()
            plan_goal = str(active_plan.get("goal") or "").strip()
            plan_goal_mode = str(active_plan.get("goal_satisfaction_mode") or "").strip()
            plan_next_step_id = str(active_plan.get("next_step_id") or "").strip()
            plan_next_step_title = str(active_plan.get("next_step_title") or "").strip()
            plan_next_step_agent = str(active_plan.get("next_step_agent") or "").strip()
            plan_last_completed_step_id = str(active_plan.get("last_completed_step_id") or "").strip()
            plan_last_completed_step_title = str(active_plan.get("last_completed_step_title") or "").strip()
            plan_status = str(active_plan.get("status") or "").strip()
            plan_step_count = str(active_plan.get("step_count") or "").strip()
            plan_blocked_by = [
                str(item).strip()
                for item in (active_plan.get("blocked_by") or [])
                if str(item).strip()
            ]
            if plan_id:
                parts.append(f"conversation_plan_id: {plan_id[:96]}")
            if plan_mode:
                parts.append(f"conversation_plan_mode: {plan_mode[:48]}")
            if plan_goal:
                parts.append(f"conversation_plan_goal: {plan_goal[:240]}")
            if plan_goal_mode:
                parts.append(f"conversation_plan_goal_satisfaction_mode: {plan_goal_mode[:64]}")
            if plan_next_step_id:
                parts.append(f"conversation_plan_next_step_id: {plan_next_step_id[:96]}")
            if plan_next_step_title:
                parts.append(f"conversation_plan_next_step_title: {plan_next_step_title[:240]}")
            if plan_next_step_agent:
                parts.append(f"conversation_plan_next_step_agent: {plan_next_step_agent[:64]}")
            if plan_last_completed_step_id:
                parts.append(f"conversation_plan_last_completed_step_id: {plan_last_completed_step_id[:96]}")
            if plan_last_completed_step_title:
                parts.append(f"conversation_plan_last_completed_step_title: {plan_last_completed_step_title[:240]}")
            if plan_status:
                parts.append(f"conversation_plan_status: {plan_status[:32]}")
            if plan_step_count:
                parts.append(f"conversation_plan_step_count: {plan_step_count[:8]}")
            if plan_blocked_by:
                parts.append(
                    "conversation_plan_blocked_by: "
                    + " || ".join(item[:140] for item in plan_blocked_by[:4])
                )
    parts.extend(["", "# CURRENT USER QUERY", query])
    return "\n".join(parts)


def _console_file_roots() -> list[Path]:
    roots: list[Path] = []
    for rel in _CONSOLE_FILE_DIRS:
        path = (project_root / rel).resolve()
        if path.exists():
            roots.append(path)
    return roots


def _is_allowed_console_file(path: Path) -> bool:
    resolved = path.resolve()
    for root in _console_file_roots():
        if resolved == root or root in resolved.parents:
            return True
    return False


def _resolve_console_file_path(rel_path: str) -> Path | None:
    candidate = (project_root / rel_path).resolve()
    if not candidate.exists() or not candidate.is_file():
        return None
    if not _is_allowed_console_file(candidate):
        return None
    return candidate


def _artifact_kind_for_console_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".doc", ".docx", ".md", ".txt"}:
        return "document"
    if suffix in {".xlsx", ".xls", ".csv"}:
        return "spreadsheet"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if suffix == ".json":
        return "data"
    return "file"


def _collect_console_files(limit: int = 24) -> list[dict]:
    rows: list[dict] = []
    base_root = project_root.resolve()
    for root in _console_file_roots():
        origin = "upload" if root.name == "uploads" else "result"
        for item in root.glob("*"):
            if not item.is_file():
                continue
            try:
                stat = item.stat()
                rel_path = str(item.resolve().relative_to(base_root))
                mime = mimetypes.guess_type(item.name)[0] or "application/octet-stream"
                rows.append(
                    {
                        "filename": item.name,
                        "path": rel_path,
                        "size_bytes": int(stat.st_size),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "origin": origin,
                        "type": _artifact_kind_for_console_path(item),
                        "mime": mime,
                    }
                )
            except Exception:
                continue
    rows.sort(key=lambda item: item.get("modified_at", ""), reverse=True)
    return rows[: max(1, min(int(limit), 100))]


def _set_agent_status(agent: str, status: str, query: str = "") -> None:
    """Aktualisiert den Agenten-Status und benachrichtigt alle SSE-Clients."""
    global _thinking_active
    _agent_status[agent] = {
        "status": status,
        "last_run": datetime.utcnow().isoformat() + "Z",
        "last_query": (query or "")[:80],
    }
    _thinking_active = any(v["status"] == "thinking" for v in _agent_status.values())
    _broadcast_sse({"type": "agent_status", "agent": agent, "status": status})
    _broadcast_sse({"type": "thinking", "active": _thinking_active})


def _google_maps_api_key() -> str:
    return os.getenv("GOOGLE_MAPS_API_KEY", "").strip()


def _google_maps_browser_api_key() -> str:
    browser_key = os.getenv("GOOGLE_MAPS_BROWSER_API_KEY", "").strip()
    if browser_key:
        return browser_key
    if os.getenv("TIMUS_ROUTE_MAP_ALLOW_SERVER_KEY_IN_BROWSER", "false").lower() == "true":
        return _google_maps_api_key()
    return ""


def _google_maps_browser_map_id() -> str:
    return os.getenv("GOOGLE_MAPS_BROWSER_MAP_ID", "").strip()


def _route_map_interactive_enabled() -> bool:
    return os.getenv("TIMUS_ROUTE_MAP_INTERACTIVE_ENABLED", "true").lower() == "true"


def _route_map_default_mode() -> str:
    return normalize_route_map_mode(os.getenv("TIMUS_ROUTE_MAP_DEFAULT_MODE", "interactive"))


def _build_route_map_client_config() -> dict:
    browser_api_key = _google_maps_browser_api_key()
    interactive_available = route_map_interactive_available(
        browser_api_key,
        enabled=_route_map_interactive_enabled(),
    )
    preferred_mode = resolve_route_map_mode(
        _route_map_default_mode(),
        interactive_available=interactive_available,
    )
    return {
        "preferred_mode": preferred_mode,
        "interactive_enabled": _route_map_interactive_enabled(),
        "interactive_available": interactive_available,
        "browser_api_key": browser_api_key if interactive_available else "",
        "browser_map_id": _google_maps_browser_map_id(),
        "js_libraries": ["geometry"],
        "language_code": "de",
        "fallback_mode": "static",
    }


def _build_google_maps_url(latitude: float, longitude: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"


def _copy_location_snapshot(snapshot: dict | None) -> dict | None:
    return copy.deepcopy(snapshot) if snapshot else None


def _copy_location_registry(payload: dict | None) -> dict | None:
    return copy.deepcopy(payload) if payload else None


def _copy_location_controls(payload: dict | None) -> dict | None:
    return copy.deepcopy(payload) if payload else None


def _copy_route_snapshot(snapshot: dict | None) -> dict | None:
    return copy.deepcopy(snapshot) if snapshot else None


def _load_location_snapshot_from_disk() -> None:
    global _location_snapshot
    if not _RUNTIME_LOCATION_SNAPSHOT_PATH.exists():
        return
    try:
        with open(_RUNTIME_LOCATION_SNAPSHOT_PATH) as handle:
            payload = _json.load(handle)
        if isinstance(payload, dict):
            with _location_snapshot_lock:
                _location_snapshot = payload
            log.info(f"✅ Runtime-Standort geladen: {_RUNTIME_LOCATION_SNAPSHOT_PATH}")
    except Exception as exc:
        log.warning(f"⚠️ Runtime-Standort konnte nicht geladen werden: {exc}")


def _load_location_registry_from_disk() -> None:
    global _location_registry
    if not _RUNTIME_LOCATION_REGISTRY_PATH.exists():
        return
    try:
        with open(_RUNTIME_LOCATION_REGISTRY_PATH) as handle:
            payload = _json.load(handle)
        normalized = normalize_location_registry(payload if isinstance(payload, dict) else {})
        with _location_registry_lock:
            _location_registry = normalized
        log.info(f"✅ Runtime-Location-Registry geladen: {_RUNTIME_LOCATION_REGISTRY_PATH}")
    except Exception as exc:
        log.warning(f"⚠️ Runtime-Location-Registry konnte nicht geladen werden: {exc}")


def _load_location_controls_from_disk() -> None:
    global _location_controls
    if not _RUNTIME_LOCATION_CONTROLS_PATH.exists():
        return
    try:
        with open(_RUNTIME_LOCATION_CONTROLS_PATH) as handle:
            payload = _json.load(handle)
        normalized = normalize_location_controls(payload if isinstance(payload, dict) else {})
        with _location_controls_lock:
            _location_controls = normalized
        log.info(f"✅ Runtime-Location-Controls geladen: {_RUNTIME_LOCATION_CONTROLS_PATH}")
    except Exception as exc:
        log.warning(f"⚠️ Runtime-Location-Controls konnten nicht geladen werden: {exc}")


def _load_route_snapshot_from_disk() -> None:
    global _route_snapshot
    if not _RUNTIME_ROUTE_SNAPSHOT_PATH.exists():
        return
    try:
        with open(_RUNTIME_ROUTE_SNAPSHOT_PATH) as handle:
            payload = _json.load(handle)
        if isinstance(payload, dict):
            normalized = prepare_route_snapshot(payload, saved_at=str(payload.get("saved_at") or "").strip() or None)
            with _route_snapshot_lock:
                _route_snapshot = normalized
            if normalized != payload:
                _persist_route_snapshot(normalized)
            log.info(f"✅ Runtime-Route geladen: {_RUNTIME_ROUTE_SNAPSHOT_PATH}")
    except Exception as exc:
        log.warning(f"⚠️ Runtime-Route konnte nicht geladen werden: {exc}")


def _persist_location_snapshot(snapshot: dict) -> None:
    _RUNTIME_LOCATION_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RUNTIME_LOCATION_SNAPSHOT_PATH, "w") as handle:
        _json.dump(snapshot, handle, indent=2, ensure_ascii=False)


def _persist_location_registry(payload: dict) -> None:
    _RUNTIME_LOCATION_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RUNTIME_LOCATION_REGISTRY_PATH, "w") as handle:
        _json.dump(payload, handle, indent=2, ensure_ascii=False)


def _persist_location_controls(payload: dict) -> None:
    _RUNTIME_LOCATION_CONTROLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RUNTIME_LOCATION_CONTROLS_PATH, "w") as handle:
        _json.dump(payload, handle, indent=2, ensure_ascii=False)


def _persist_route_snapshot(snapshot: dict) -> None:
    _RUNTIME_ROUTE_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RUNTIME_ROUTE_SNAPSHOT_PATH, "w") as handle:
        _json.dump(snapshot, handle, indent=2, ensure_ascii=False)


def _set_location_snapshot(snapshot: dict) -> None:
    global _location_snapshot, _location_registry
    controls = _get_location_controls()
    max_entries = int((controls or {}).get("max_device_entries", 8) or 8)
    registry = _get_location_registry()
    updated_registry = update_location_registry(registry, snapshot, max_entries=max_entries)
    status_payload = build_location_status_payload(
        updated_registry,
        controls,
        fallback_snapshot=snapshot,
    )
    with _location_snapshot_lock:
        _location_snapshot = _copy_location_snapshot(status_payload.get("location") or snapshot)
    with _location_registry_lock:
        _location_registry = _copy_location_registry(updated_registry)
    _persist_location_snapshot(status_payload.get("location") or snapshot)
    _persist_location_registry(updated_registry)


def _get_location_registry() -> dict:
    with _location_registry_lock:
        if _location_registry is not None:
            return _copy_location_registry(_location_registry) or {"devices": [], "updated_at": ""}
    _load_location_registry_from_disk()
    with _location_registry_lock:
        return _copy_location_registry(_location_registry) or {"devices": [], "updated_at": ""}


def _set_location_controls(payload: dict) -> dict:
    global _location_controls, _location_snapshot
    normalized = normalize_location_controls(payload or {})
    with _location_controls_lock:
        _location_controls = _copy_location_controls(normalized)
    _persist_location_controls(normalized)
    status_payload = _build_location_status_payload()
    with _location_snapshot_lock:
        _location_snapshot = _copy_location_snapshot(status_payload.get("location"))
    if status_payload.get("location"):
        _persist_location_snapshot(status_payload["location"])
    return normalized


def _get_location_controls() -> dict:
    with _location_controls_lock:
        if _location_controls is not None:
            return _copy_location_controls(_location_controls) or normalize_location_controls({})
    _load_location_controls_from_disk()
    with _location_controls_lock:
        return _copy_location_controls(_location_controls) or normalize_location_controls({})


def _build_location_status_payload() -> dict:
    registry = _get_location_registry()
    controls = _get_location_controls()
    fallback_snapshot = None
    with _location_snapshot_lock:
        if _location_snapshot is not None:
            fallback_snapshot = _copy_location_snapshot(_location_snapshot)
    if not fallback_snapshot:
        _load_location_snapshot_from_disk()
        with _location_snapshot_lock:
            fallback_snapshot = _copy_location_snapshot(_location_snapshot)
    return build_location_status_payload(
        registry,
        controls,
        fallback_snapshot=fallback_snapshot,
    )


def _get_location_snapshot() -> dict | None:
    payload = _build_location_status_payload()
    return apply_location_controls_to_snapshot(payload.get("location"), payload.get("controls"))


def _set_route_snapshot(snapshot: dict) -> None:
    global _route_snapshot
    with _route_snapshot_lock:
        _route_snapshot = _copy_route_snapshot(snapshot)
    _persist_route_snapshot(snapshot)


def _get_route_snapshot() -> dict | None:
    with _route_snapshot_lock:
        if _route_snapshot is not None:
            return _copy_route_snapshot(_route_snapshot)
    _load_route_snapshot_from_disk()
    with _route_snapshot_lock:
        return _copy_route_snapshot(_route_snapshot)


def _annotate_route_reroute_error(route_snapshot: dict | None, error: str, attempted_at: str) -> dict | None:
    if not isinstance(route_snapshot, dict):
        return None
    annotated = dict(route_snapshot)
    annotated["route_status"] = "warning"
    annotated["last_reroute_at"] = str(attempted_at or "").strip()
    annotated["last_reroute_error"] = str(error or "").strip()
    return annotated


async def _maybe_live_reroute_active_route(location_snapshot: dict) -> dict:
    if not _location_live_reroute_enabled():
        return {"reroute_triggered": False, "reason": "disabled"}

    enriched_location = apply_location_controls_to_snapshot(location_snapshot, _get_location_controls()) or {}
    route_snapshot = _get_route_snapshot()
    decision = assess_live_reroute(
        route_snapshot,
        enriched_location,
        min_distance_meters=_location_route_reroute_min_distance_meters(),
        min_interval_seconds=_location_route_reroute_min_interval_seconds(),
    )
    if not decision.get("should_reroute"):
        return {
            "reroute_triggered": False,
            "reason": str(decision.get("reason") or "skipped"),
            "moved_distance_meters": decision.get("moved_distance_meters"),
            "seconds_since_last_update": decision.get("seconds_since_last_update"),
        }

    attempted_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    try:
        from tools.search_tool.tool import get_google_maps_route

        rerouted = await get_google_maps_route(
            destination_query=str(route_snapshot.get("destination_query") or "").strip(),
            travel_mode=str(route_snapshot.get("travel_mode") or "driving").strip() or "driving",
            language_code=str(route_snapshot.get("language_code") or "de").strip() or "de",
        )
        rerouted_snapshot = prepare_route_snapshot(rerouted)
        rerouted_snapshot = apply_live_reroute_metadata(
            rerouted_snapshot,
            route_snapshot,
            enriched_location,
            moved_distance_meters=decision.get("moved_distance_meters"),
            reroute_reason=str(decision.get("reason") or "movement_threshold_exceeded"),
            rerouted_at=attempted_at,
        )
        _set_route_snapshot(rerouted_snapshot)
        return {
            "reroute_triggered": True,
            "reason": str(decision.get("reason") or "movement_threshold_exceeded"),
            "moved_distance_meters": decision.get("moved_distance_meters"),
            "seconds_since_last_update": decision.get("seconds_since_last_update"),
            "route": rerouted_snapshot,
        }
    except Exception as exc:
        log.warning(f"⚠️ Live-Re-Routing fehlgeschlagen: {exc}")
        annotated = _annotate_route_reroute_error(route_snapshot, str(exc), attempted_at)
        if annotated:
            _set_route_snapshot(annotated)
        return {
            "reroute_triggered": False,
            "reason": "reroute_error",
            "error": str(exc),
            "moved_distance_meters": decision.get("moved_distance_meters"),
            "seconds_since_last_update": decision.get("seconds_since_last_update"),
        }


def _route_map_placeholder_svg(title: str, detail: str = "") -> str:
    safe_title = _html.escape(str(title or "Keine aktive Route"))
    safe_detail = _html.escape(str(detail or "").strip())
    detail_line = f'<text x="50%" y="66%" text-anchor="middle" fill="#7db599" font-size="15">{safe_detail}</text>' if safe_detail else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">'
        '<defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#09111c"/><stop offset="100%" stop-color="#051019"/></linearGradient></defs>'
        '<rect width="960" height="540" rx="24" fill="url(#g)"/>'
        '<rect x="26" y="26" width="908" height="488" rx="20" fill="none" stroke="rgba(0,224,154,0.18)"/>'
        '<circle cx="220" cy="170" r="11" fill="#00e09a"/><circle cx="734" cy="350" r="11" fill="#00d4f0"/>'
        '<path d="M220 170 C360 120 520 180 640 250 S760 330 734 350" fill="none" stroke="rgba(0,224,154,0.55)" stroke-width="8" stroke-linecap="round"/>'
        f'<text x="50%" y="56%" text-anchor="middle" fill="#cce8db" font-size="28" font-weight="600">{safe_title}</text>'
        f"{detail_line}"
        "</svg>"
    )


def _route_point_from_dict(value: dict | None) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        latitude = float(value.get("latitude"))
        longitude = float(value.get("longitude"))
    except Exception:
        return None
    if latitude == 0.0 and longitude == 0.0:
        return None
    return latitude, longitude


def _build_google_static_route_map_url(snapshot: dict, width: int = 960, height: int = 540) -> str | None:
    api_key = _google_maps_api_key()
    if not api_key:
        return None
    origin = _route_point_from_dict(snapshot.get("start_coordinates")) or _route_point_from_dict(snapshot.get("origin"))
    destination = _route_point_from_dict(snapshot.get("end_coordinates"))
    destination_query = str(
        snapshot.get("destination_label") or snapshot.get("end_address") or snapshot.get("destination_query") or ""
    ).strip()
    if not origin or not (destination or destination_query):
        return None

    params: list[tuple[str, str]] = [
        ("size", f"{max(320, int(width))}x{max(240, int(height))}"),
        ("scale", "2"),
        ("maptype", "roadmap"),
        ("language", "de"),
        ("key", api_key),
        ("markers", f"color:0x00e09a|label:S|{origin[0]},{origin[1]}"),
    ]
    if destination:
        params.append(("markers", f"color:0x00d4f0|label:Z|{destination[0]},{destination[1]}"))
    else:
        params.append(("markers", f"color:0x00d4f0|label:Z|{destination_query}"))

    overview_polyline = str(snapshot.get("overview_polyline") or "").strip()
    if overview_polyline:
        params.append(("path", f"color:0x00e09aCC|weight:6|enc:{overview_polyline}"))
    elif destination:
        params.append(("path", f"color:0x00e09a99|weight:5|{origin[0]},{origin[1]}|{destination[0]},{destination[1]}"))

    return "https://maps.googleapis.com/maps/api/staticmap?" + urlencode(params, doseq=True)


def _address_component(components: list[dict], type_name: str, short: bool = False) -> str:
    key = "short_name" if short else "long_name"
    for component in components:
        if type_name in (component.get("types") or []):
            return str(component.get(key) or "")
    return ""


def _reverse_geocode_with_google(latitude: float, longitude: float) -> dict | None:
    api_key = _google_maps_api_key()
    if not api_key:
        return None
    params = urlencode(
        {
            "latlng": f"{latitude},{longitude}",
            "language": "de",
            "key": api_key,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
    try:
        response = requests.get(url, timeout=12)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        top = results[0] if results else {}
        components = top.get("address_components") or []
        locality = (
            _address_component(components, "locality")
            or _address_component(components, "postal_town")
            or _address_component(components, "administrative_area_level_2")
        )
        return {
            "display_name": str(top.get("formatted_address") or ""),
            "locality": locality,
            "admin_area": _address_component(components, "administrative_area_level_1"),
            "country_name": _address_component(components, "country"),
            "country_code": _address_component(components, "country", short=True),
            "geocode_provider": "google_maps",
        }
    except Exception as exc:
        log.warning(f"⚠️ Google Reverse-Geocoding fehlgeschlagen: {exc}")
        return None


def _normalize_location_snapshot(payload: dict) -> dict:
    latitude = float(payload.get("latitude"))
    longitude = float(payload.get("longitude"))
    accuracy = payload.get("accuracy_meters")
    accuracy_value = float(accuracy) if accuracy not in (None, "") else None
    captured_at = str(payload.get("captured_at") or datetime.utcnow().isoformat() + "Z")
    source = str(payload.get("source") or "android_fused")
    device_fields = {
        "display_name": str(payload.get("display_name") or ""),
        "locality": str(payload.get("locality") or ""),
        "admin_area": str(payload.get("admin_area") or ""),
        "country_name": str(payload.get("country_name") or ""),
        "country_code": str(payload.get("country_code") or ""),
    }
    google_fields = _reverse_geocode_with_google(latitude, longitude)
    chosen_fields = dict(device_fields)
    if google_fields:
        chosen_fields.update({key: value for key, value in google_fields.items() if value})
    display_name = chosen_fields.get("display_name") or ", ".join(
        [part for part in [chosen_fields.get("locality"), chosen_fields.get("admin_area"), chosen_fields.get("country_name")] if part]
    )
    geocode_provider = chosen_fields.get("geocode_provider") or ("device_geocoder" if any(device_fields.values()) else "coordinates_only")
    normalized = {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy_meters": accuracy_value,
        "source": source,
        "captured_at": captured_at,
        "display_name": display_name,
        "locality": chosen_fields.get("locality") or "",
        "admin_area": chosen_fields.get("admin_area") or "",
        "country_name": chosen_fields.get("country_name") or "",
        "country_code": chosen_fields.get("country_code") or "",
        "geocode_provider": geocode_provider,
        "maps_url": _build_google_maps_url(latitude, longitude),
    }
    if payload.get("device_id") not in (None, ""):
        normalized["device_id"] = str(payload.get("device_id") or "").strip()
    if payload.get("user_scope") not in (None, ""):
        normalized["user_scope"] = str(payload.get("user_scope") or "").strip()
    return prepare_location_presence_snapshot(
        normalized,
        received_at=str(payload.get("received_at") or "").strip(),
    )


try:
    log_path = project_root / "timus_server.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s")
    )
    logging.getLogger().addHandler(file_handler)
    log.info(f"Logging auch in Datei: {log_path}")
except Exception as e:
    log.warning(f"Konnte Log-Datei nicht erstellen: {e}")

# --- Globale Konstanten ---
TOOL_MODULES = [
    "tools.browser_tool.tool",
    "tools.summarizer.tool",
    "tools.planner.tool",
    "tools.search_tool.tool",
    "tools.tasks.tasks",
    "tools.save_results.tool",
    "tools.deep_research.tool",
    "tools.decision_verifier.tool",
    "tools.document_parser.tool",
    "tools.fact_corroborator.tool",
    "tools.report_generator.tool",
    "tools.creative_tool.tool",
    "tools.memory_tool.tool",
    "tools.maintenance_tool.tool",
    "tools.developer_tool.tool",
    "tools.code_editor_tool.tool",
    "tools.file_system_tool.tool",
    "tools.document_creator.tool",
    "tools.data_tool.tool",
    "tools.meta_tool.tool",
    "tools.reflection_tool.tool",
    "tools.init_skill_tool.tool",
    "tools.skill_manager_tool.tool",
    "tools.skill_manager_tool.reload_tool",
    "tools.curator_tool.tool",
    "tools.system_monitor_tool.tool",
    "tools.ocr_tool.tool",
    "tools.visual_grounding_tool.tool",
    "tools.mouse_tool.tool",
    "tools.visual_segmentation_tool.tool",
    "tools.debug_tool.tool",
    "tools.debug_screenshot_tool.tool",
    "tools.inception_tool.tool",
    "tools.icon_recognition_tool.tool",
    "tools.engines.object_detection_engine",
    "tools.annotator_tool.tool",
    "tools.application_launcher.tool",
    "tools.visual_browser_tool.tool",
    "tools.text_finder_tool.tool",
    "tools.smart_navigation_tool.tool",
    "tools.som_tool.tool",
    "tools.verification_tool.tool",
    "tools.verified_vision_tool.tool",
    "tools.qwen_vl_tool.tool",
    "tools.voice_tool.tool",
    "tools.skill_recorder.tool",
    "tools.mouse_feedback_tool.tool",
    "tools.hybrid_detection_tool.tool",
    "tools.visual_agent_tool.tool",
    "tools.cookie_banner_tool.tool",
    # NEU: Agent-zu-Agent Delegation (sequenziell + parallel)
    "tools.delegation_tool.tool",
    "tools.delegation_tool.parallel_delegation_tool",
    # NEU: Vision Stability System v1.0 (GPT-5.2 Empfehlungen)
    "tools.screen_change_detector.tool",
    "tools.screen_contract_tool.tool",
    "tools.opencv_template_matcher_tool.tool",
    # RealSense Kamera (D435): Status + Snapshot-Capture
    "tools.realsense_camera_tool.tool",
    # NEU: DOM-First Browser Controller v2.0 (2026-02-10)
    "tools.browser_controller.tool",
    # NEU: JSON-Nemotron Tool für AI-gestützte JSON-Verarbeitung
    "tools.json_nemotron_tool.json_nemotron_tool",
    # NEU: Florence-2 Vision Tool — UI-Detection + OCR (ersetzt Qwen-VL als Primary)
    "tools.florence2_tool.tool",
    # M3: System-Monitor Tools
    "tools.system_tool.tool",
    # M4: Shell-Operator Tools
    "tools.shell_tool.tool",
    # E-Mail (SMTP + IMAP via Outlook)
    "tools.email_tool.tool",
    # Web-Fetch: URL-Inhalte abrufen (requests → Playwright-Fallback, v3.3)
    "tools.web_fetch_tool.tool",
    # Social Media / JS-Rendering via ScrapingAnt
    "tools.social_media_tool.tool",
    # M9: Agent Blackboard
    "tools.blackboard_tool.tool",
    # M10: Proactive Triggers
    "tools.trigger_tool.tool",
    # M11: Goal Queue Manager
    "tools.goal_tool.tool",
    # M12: Self-Improvement Engine
    "tools.self_improvement_tool.tool",
    # Qualitätssicherung: Lean 4 Verifikation
    "tools.lean_tool.tool",
]

# --- Hilfsfunktionen für den Lifespan-Manager ---


def _initialize_hardware_and_engines():
    """
    Prüft Hardware-Voraussetzungen (GPU, CUDA) und initialisiert rechenintensive Engines.
    """
    log.info("--- Prüfe Hardware und initialisiere Engines ---")
    try:
        import torch

        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            gpu_name = torch.cuda.get_device_name(0)
            log.info(
                f"✅ GPU-Beschleunigung AKTIV (PyTorch): {gpu_count}x {gpu_name} gefunden."
            )
            shared_context.device = "cuda"
        else:
            log.warning("⚠️ GPU-Beschleunigung NICHT verfügbar (PyTorch). Nutze CPU.")
            shared_context.device = "cpu"
    except ImportError:
        log.warning(
            "⚠️ PyTorch ist nicht installiert. GPU-Prüfung wird übersprungen. Nutze CPU."
        )
        shared_context.device = "cpu"
    except Exception as e:
        log.error(f"❌ Fehler bei der GPU-Prüfung mit PyTorch: {e}", exc_info=True)
        shared_context.device = "cpu"

    try:
        from tools.engines.ocr_engine import ocr_engine_instance

        ocr_engine_instance.initialize()
        log.info("✅ OCR-Engine erfolgreich initialisiert.")
        shared_context.ocr_engine = ocr_engine_instance
    except ImportError:
        log.warning(
            "⚠️ OCR-Engine-Modul nicht gefunden. OCR-Tool wird nicht funktionieren."
        )
    except Exception as e:
        log.error(
            f"❌ Fehler bei der Initialisierung der OCR-Engine: {e}", exc_info=True
        )

    # Qwen2.5-VL Vision Language Model Engine initialisieren
    try:
        from tools.engines.qwen_vl_engine import qwen_vl_engine_instance

        if (
            os.getenv("QWEN_VL_ENABLED", "0") == "1"
        ):  # Default OFF für schnelleren Start
            qwen_vl_engine_instance.initialize()
            if qwen_vl_engine_instance.is_initialized():
                log.info("✅ Qwen-VL Engine erfolgreich initialisiert.")
                shared_context.qwen_vl_engine = qwen_vl_engine_instance
            else:
                log.warning("⚠️ Qwen-VL Engine Initialisierung fehlgeschlagen.")
        else:
            log.info("ℹ️ Qwen-VL Engine ist deaktiviert (QWEN_VL_ENABLED=0).")
    except ImportError:
        log.warning("⚠️ Qwen-VL Engine-Modul nicht gefunden.")
    except Exception as e:
        log.error(
            f"❌ Fehler bei der Initialisierung der Qwen-VL Engine: {e}", exc_info=True
        )


def _initialize_shared_clients():
    """
    Initialisiert softwareseitige Clients (APIs, DBs).
    """
    log.info("--- Initialisiere geteilte Software-Clients ---")
    try:
        from openai import OpenAI

        shared_context.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        log.info("✅ Geteilter OpenAI-Client initialisiert.")
    except Exception as e:
        log.error(f"❌ Fehler bei Initialisierung des OpenAI-Clients: {e}")

    try:
        requested_memory_backend = normalize_semantic_memory_backend(os.getenv("MEMORY_BACKEND"))
        if requested_memory_backend == "chromadb":
            import chromadb
            from utils.embedding_provider import get_embedding_function

            if shared_context.openai_client:
                db_path = project_root / "memory_db"
                chroma_db_client = chromadb.PersistentClient(
                    path=str(db_path),
                    settings=build_chroma_settings(chromadb_module=chromadb),
                )
                openai_ef = get_embedding_function()
                shared_context.memory_collection = (
                    chroma_db_client.get_or_create_collection(
                        name="timus_long_term_memory", embedding_function=openai_ef
                    )
                )
                log.info(f"✅ Geteilte Memory-Collection ('{db_path}') initialisiert.")
            else:
                log.warning(
                    "⚠️ Memory-Collection nicht initialisiert, da OpenAI-Client fehlt."
                )
        else:
            shared_context.memory_collection = None
            log.info(
                "ℹ️ Geteilte Chroma-Memory-Collection uebersprungen (MEMORY_BACKEND=%s).",
                requested_memory_backend,
            )
    except Exception as e:
        log.error(f"❌ Fehler bei Initialisierung der Memory-Collection: {e}")


def _load_all_tools_and_skills() -> tuple[list[str], list[tuple[str, str]]]:
    """
    Hilfsfunktion, die alle Tool- und Skill-Module importiert und die Ergebnisse zurückgibt.
    """
    local_loaded_modules: list[str] = []
    local_failed_modules: list[tuple[str, str]] = []

    log.info("--- Lade Tool-Module ---")
    for mod_path in TOOL_MODULES:
        try:
            if mod_path in sys.modules:
                importlib.reload(sys.modules[mod_path])
            else:
                importlib.import_module(mod_path)
            local_loaded_modules.append(mod_path)
            log.info(f"✅ Modul geladen: {mod_path}")
        except Exception as e:
            local_failed_modules.append((mod_path, str(e)))
            log.error(f"❌ Fehler beim Laden von {mod_path}: {e}", exc_info=False)

    log.info("--- Lade erlernte Fähigkeiten (Skills) ---")
    SKILLS_DIR = project_root / "skills"
    if SKILLS_DIR.is_dir():
        if not (SKILLS_DIR / "__init__.py").exists():
            (SKILLS_DIR / "__init__.py").touch()
        if str(SKILLS_DIR.parent) not in sys.path:
            sys.path.insert(0, str(SKILLS_DIR.parent))
        for skill_file in SKILLS_DIR.glob("*_skill.py"):
            try:
                module_name = f"skills.{skill_file.stem}"
                if module_name in sys.modules:
                    importlib.reload(sys.modules[module_name])
                else:
                    importlib.import_module(module_name)
                log.info(f"✅ Skill-Modul '{module_name}' geladen.")
            except Exception as e_skill:
                log.error(
                    f"❌ Fehler beim Laden der Fähigkeit aus '{skill_file.name}': {e_skill}",
                    exc_info=True,
                )

    return local_loaded_modules, local_failed_modules


async def _rpc_call_local(method: str, params: dict | None = None) -> dict:
    """Rufe eine JSON-RPC-Methode lokal (im selben Prozess) auf."""
    import json as _json

    # jsonrpcserver 5.x: Kein Request-Objekt mehr, sondern JSON-String direkt
    request_json = _json.dumps(
        {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    )
    reply = await async_dispatch(request_json, serializer=numpy_aware_serializer)
    try:
        if not reply:
            return {"error": "no_reply"}
        data = _json.loads(reply)
        if "error" in data:
            return {"error": data["error"]}
        return data.get("result", {})
    except Exception as e:
        return {"error": f"dispatch_error: {e}"}


def _detect_inception_registered() -> bool:
    try:
        tools = registry_v2.list_all_tools()
        return any(
            m in tools
            for m in ("generate_and_integrate", "implement_feature", "inception_health")
        )
    except Exception:
        return False


def _is_truthy_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _canvas_ui_url() -> str:
    host = (os.getenv("HOST", "127.0.0.1") or "127.0.0.1").strip()
    try:
        if ipaddress.ip_address(host).is_unspecified:
            host = "127.0.0.1"
    except ValueError:
        pass
    port = int(os.getenv("PORT", 5000))
    return f"http://{host}:{port}/canvas/ui"


def _should_auto_open_canvas_ui() -> bool:
    """Auto-Open nur in interaktiven Desktop-Sessions, nicht im 24/7-Servicebetrieb."""
    if is_service_headless_context():
        return False

    explicit = os.getenv("TIMUS_CANVAS_AUTO_OPEN")
    if explicit is not None:
        return _is_truthy_env(explicit, default=False)

    if not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")):
        return False

    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _bootstrap_canvas_startup() -> dict:
    """Initialisiert Canvas-MVP beim Server-Start (best effort)."""
    auto_create = _is_truthy_env(os.getenv("TIMUS_CANVAS_AUTO_CREATE"), default=True)
    auto_open = _should_auto_open_canvas_ui()

    created_canvas_id = None
    primary_canvas_id = None

    canvases = canvas_store.list_canvases(limit=1)
    if canvases.get("items"):
        primary_canvas_id = str(canvases["items"][0].get("id") or "")

    if auto_create and not primary_canvas_id:
        title = (os.getenv("TIMUS_CANVAS_DEFAULT_TITLE") or "Live Canvas").strip()
        description = "Auto-created on MCP startup"
        canvas = canvas_store.create_canvas(
            title=title,
            description=description,
            metadata={"auto_created": True, "source": "mcp_startup"},
        )
        created_canvas_id = canvas.get("id")
        primary_canvas_id = created_canvas_id
        log.info(f"✅ Canvas auto-created: {created_canvas_id}")

    ui_url = _canvas_ui_url()
    opened = False

    if auto_open:
        def _open_ui():
            try:
                webbrowser.open(ui_url, new=2)
            except Exception as exc:
                log.warning(f"⚠️ Canvas UI konnte nicht automatisch geöffnet werden: {exc}")

        try:
            # Verzögert starten, damit der HTTP-Listener bereit ist.
            timer = threading.Timer(1.2, _open_ui)
            timer.daemon = True
            timer.start()
            opened = True
            log.info(f"🖼️ Canvas UI Auto-Open geplant: {ui_url}")
        except Exception as exc:
            log.warning(f"⚠️ Canvas UI Auto-Open nicht verfügbar: {exc}")

    return {
        "primary_canvas_id": primary_canvas_id,
        "created_canvas_id": created_canvas_id,
        "auto_open": opened,
        "ui_url": ui_url,
    }


def _short_text(value: str, limit: int = 140) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


async def _shutdown_async_step(name: str, awaitable, timeout_s: float | None = None) -> bool:
    """Fuehrt einen Shutdown-Schritt mit begrenzter Wartezeit aus."""
    limit = max(0.5, float(timeout_s or _SHUTDOWN_STEP_TIMEOUT_S))
    try:
        await asyncio.wait_for(awaitable, timeout=limit)
        log.info("✅ Shutdown-Schritt abgeschlossen: %s", name)
        return True
    except asyncio.TimeoutError:
        log.warning("⚠️ Shutdown-Schritt Timeout nach %.1fs: %s", limit, name)
        return False
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.warning("⚠️ Shutdown-Schritt fehlgeschlagen (%s): %s", name, exc)
        return False


async def _cancel_background_task(name: str, task: asyncio.Task | None, timeout_s: float = 2.0) -> bool:
    """Bricht einen Hintergrundtask kontrolliert ab."""
    if not task:
        return True
    if task.done():
        return True
    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=max(0.5, timeout_s))
        log.info("✅ Hintergrundtask beendet: %s", name)
        return True
    except asyncio.CancelledError:
        return True
    except asyncio.TimeoutError:
        log.warning("⚠️ Hintergrundtask stoppt nicht rechtzeitig: %s", name)
        return False
    except Exception as exc:
        log.warning("⚠️ Fehler beim Stoppen von Hintergrundtask %s: %s", name, exc)
        return False


async def _await_sse_queue_item(
    queue: asyncio.Queue,
    shutdown_event: asyncio.Event,
    *,
    timeout_s: float = 25.0,
) -> tuple[str, str | None]:
    """Wartet auf Queue-Daten oder einen Server-Shutdown fuer SSE-Verbindungen."""
    queue_task = asyncio.create_task(queue.get())
    shutdown_task = asyncio.create_task(shutdown_event.wait())
    try:
        done, pending = await asyncio.wait(
            {queue_task, shutdown_task},
            timeout=max(0.2, float(timeout_s)),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            return ("ping", None)
        if shutdown_task in done and shutdown_task.result():
            return ("shutdown", None)
        if queue_task in done:
            return ("data", str(queue_task.result()))
        return ("ping", None)
    finally:
        for task in (queue_task, shutdown_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(queue_task, shutdown_task, return_exceptions=True)


async def _run_post_startup_warmups(app: FastAPI) -> None:
    """Fuehrt optionale Warmups nach dem HTTP-Start aus, ohne Readiness zu blockieren."""
    warmups: dict[str, dict] = {}
    try:
        if "inception_health" in registry_v2.list_all_tools():
            try:
                probe = await _rpc_call_local("inception_health", {})
                ok = isinstance(probe, dict) and not probe.get("error")
                app.state.inception["health"] = {"ok": bool(ok), "detail": probe}
                warmups["inception_health"] = {
                    "ok": bool(ok),
                    "detail": probe if ok else str(probe)[:240],
                }
                if ok:
                    log.info("🩺 Inception-Health: OK (Post-Startup-Warmup)")
                else:
                    log.warning("🩺 Inception-Health: Problematisch (Post-Startup-Warmup) → %s", probe)
            except Exception as exc:
                app.state.inception["health"] = {
                    "ok": False,
                    "detail": f"health_call_error: {exc}",
                }
                warmups["inception_health"] = {"ok": False, "detail": str(exc)}
                log.warning("🩺 Inception-Health: Fehler beim Warmup: %s", exc)
        else:
            warmups["inception_health"] = {"ok": None, "detail": "not_registered"}

        try:
            from tools.browser_tool.persistent_context import PersistentContextManager

            manager = PersistentContextManager()
            await manager.initialize()
            shared_context.browser_context_manager = manager
            warmups["persistent_browser_context_manager"] = {"ok": True}
            log.info("✅ Browser PersistentContextManager initialisiert (Post-Startup-Warmup)")
        except Exception as exc:
            warmups["persistent_browser_context_manager"] = {"ok": False, "detail": str(exc)}
            log.warning("⚠️ PersistentContextManager konnte nicht gestartet werden: %s", exc)

        app.state.scheduler = None
        if os.getenv("HEARTBEAT_ENABLED", "true").lower() == "true":
            try:
                from orchestration.scheduler import init_scheduler, _set_scheduler_instance

                async def on_scheduler_wake(event):
                    log.info(f"💓 Scheduler Event: {event.event_type}")
                    if shared_context.browser_context_manager:
                        expired = await shared_context.browser_context_manager.cleanup_expired()
                        if expired > 0:
                            log.info(f"🧹 {expired} abgelaufene Browser-Sessions entfernt")

                scheduler = init_scheduler(on_wake=on_scheduler_wake)
                _set_scheduler_instance(scheduler)
                await scheduler.start()
                app.state.scheduler = scheduler
                warmups["heartbeat_scheduler"] = {
                    "ok": True,
                    "interval_min": scheduler.interval.total_seconds() / 60,
                }
                log.info(
                    "✅ Heartbeat-Scheduler gestartet (Post-Startup-Warmup, Interval: %.0fmin)",
                    scheduler.interval.total_seconds() / 60,
                )
            except Exception as exc:
                warmups["heartbeat_scheduler"] = {"ok": False, "detail": str(exc)}
                log.warning("⚠️ Scheduler konnte nicht gestartet werden: %s", exc)
        else:
            warmups["heartbeat_scheduler"] = {"ok": None, "detail": "disabled"}
            log.info("ℹ️ Heartbeat-Scheduler deaktiviert (HEARTBEAT_ENABLED=false)")

        app.state.realsense_stream_manager = None
        if os.getenv("REALSENSE_STREAM_AUTO_START", "false").lower() in {"1", "true", "yes", "on"}:
            try:
                from utils.realsense_stream import get_realsense_stream_manager

                width = int(os.getenv("REALSENSE_STREAM_WIDTH", "1280"))
                height = int(os.getenv("REALSENSE_STREAM_HEIGHT", "720"))
                fps = float(os.getenv("REALSENSE_STREAM_FPS", "10"))
                device_raw = (os.getenv("REALSENSE_STREAM_DEVICE") or "").strip()
                device_index = int(device_raw) if device_raw else None

                stream_manager = get_realsense_stream_manager()
                status = await asyncio.to_thread(
                    stream_manager.start,
                    width,
                    height,
                    fps,
                    device_index,
                )
                app.state.realsense_stream_manager = stream_manager
                warmups["realsense_stream"] = {"ok": True, "detail": status}
                log.info("✅ RealSense-Stream gestartet (Post-Startup-Warmup): %s", status)
            except Exception as exc:
                warmups["realsense_stream"] = {"ok": False, "detail": str(exc)}
                log.warning("⚠️ RealSense-Stream Auto-Start fehlgeschlagen: %s", exc)
        else:
            warmups["realsense_stream"] = {"ok": None, "detail": "disabled"}
            log.info("ℹ️ RealSense-Stream Auto-Start deaktiviert (REALSENSE_STREAM_AUTO_START=false)")

    except asyncio.CancelledError:
        log.info("ℹ️ Post-Startup-Warmups wurden beim Shutdown abgebrochen.")
        raise
    finally:
        current = _current_mcp_lifecycle(app)
        if str(current.get("status") or "").lower() == "shutting_down":
            _set_app_mcp_lifecycle(app, warmups=warmups)
        else:
            _set_app_mcp_lifecycle(
                app,
                phase="ready",
                status="healthy",
                ready=True,
                warmup_pending=False,
                transient=False,
                warmups=warmups,
            )


async def _canvas_mirror_log_worker(interval_seconds: float = 1.2) -> None:
    """Spiegelt neue Canvas-Events/Edges als MCP-Logeintraege."""
    interval = max(0.3, float(interval_seconds))
    seen_event_ids: set[str] = set()
    seen_edge_ids: set[str] = set()
    seen_event_order: deque[str] = deque()
    seen_edge_order: deque[str] = deque()
    canvas_updated_at: dict[str, str] = {}
    max_seen = 25000

    def _remember(seen_set: set[str], seen_q: deque[str], value: str) -> bool:
        if not value or value in seen_set:
            return False
        seen_set.add(value)
        seen_q.append(value)
        while len(seen_q) > max_seen:
            old = seen_q.popleft()
            seen_set.discard(old)
        return True

    # Baseline setzen, damit beim Start nicht die komplette Historie neu geloggt wird.
    try:
        initial = canvas_store.list_canvases(limit=200).get("items", [])
        for canvas in initial:
            cid = str(canvas.get("id") or "")
            canvas_updated_at[cid] = str(canvas.get("updated_at") or "")
            for ev in canvas.get("events", []) or []:
                _remember(seen_event_ids, seen_event_order, str(ev.get("id") or ""))
            for edge in canvas.get("edges", []) or []:
                _remember(seen_edge_ids, seen_edge_order, str(edge.get("id") or ""))
        log.info(
            "🧩 Canvas mirror logger gestartet (canvases=%s, interval=%.1fs)",
            len(initial),
            interval,
        )
    except Exception as exc:
        log.warning(f"⚠️ Canvas mirror baseline fehlgeschlagen: {exc}")

    while True:
        try:
            canvases = canvas_store.list_canvases(limit=200).get("items", [])
            for canvas in canvases:
                cid = str(canvas.get("id") or "")
                updated_at = str(canvas.get("updated_at") or "")
                if canvas_updated_at.get(cid) == updated_at:
                    continue

                canvas_updated_at[cid] = updated_at

                events = sorted(
                    (canvas.get("events", []) or []),
                    key=lambda e: str(e.get("created_at", "")),
                )
                for ev in events:
                    event_id = str(ev.get("id") or "")
                    if not _remember(seen_event_ids, seen_event_order, event_id):
                        continue
                    log.info(
                        "🧩 Canvas event | canvas=%s session=%s agent=%s type=%s status=%s msg=%s",
                        cid,
                        str(ev.get("session_id") or "-"),
                        str(ev.get("agent") or "-"),
                        str(ev.get("type") or "-"),
                        str(ev.get("status") or "-"),
                        _short_text(str(ev.get("message") or "-")),
                    )

                edges = sorted(
                    (canvas.get("edges", []) or []),
                    key=lambda e: str(e.get("created_at", "")),
                )
                for edge in edges:
                    edge_id = str(edge.get("id") or "")
                    if not _remember(seen_edge_ids, seen_edge_order, edge_id):
                        continue
                    log.info(
                        "🧩 Canvas edge  | canvas=%s %s -> %s kind=%s label=%s",
                        cid,
                        str(edge.get("source") or "-"),
                        str(edge.get("target") or "-"),
                        str(edge.get("kind") or "-"),
                        _short_text(str(edge.get("label") or "-"), limit=60),
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning(f"⚠️ Canvas mirror loop Fehler: {exc}")

        await asyncio.sleep(interval)


# --- Lifespan-Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 50)
    log.info("🚀 TIMUS MCP SERVER STARTUP-PROZESS BEGINNT...")
    log.info("=" * 50)
    _reset_mcp_lifecycle()
    app.state.mcp_lifecycle = _current_mcp_lifecycle()
    app.state.sse_shutdown_event = asyncio.Event()
    app.state.post_startup_warmup_task = None
    app.state.scheduler = None
    app.state.realsense_stream_manager = None

    load_dotenv(override=True)
    log.info("✅ .env-Datei geladen.")

    # Runtime-Settings laden (überschreiben .env-Werte ohne Server-Neustart)
    if _RUNTIME_SETTINGS_PATH.exists():
        try:
            with open(_RUNTIME_SETTINGS_PATH) as _f:
                for _k, _v in _json.load(_f).items():
                    os.environ[_k] = str(_v)
            log.info(f"✅ Runtime-Settings geladen: {_RUNTIME_SETTINGS_PATH}")
        except Exception as _e:
            log.warning(f"⚠️ Runtime-Settings konnten nicht geladen werden: {_e}")

    _load_location_controls_from_disk()
    _load_location_registry_from_disk()
    _load_location_snapshot_from_disk()

    # Canvas-MVP Bootstrap (best effort)
    try:
        app.state.canvas_startup = _bootstrap_canvas_startup()
    except Exception as e:
        log.warning(f"⚠️ Canvas Startup-Bootstrap fehlgeschlagen: {e}")

    # Canvas-Mirror-Logger (MCP-seitige Spiegel-Logs)
    app.state.canvas_mirror_task = None
    if _is_truthy_env(os.getenv("TIMUS_CANVAS_MIRROR_LOG"), default=True):
        try:
            interval_s = float(os.getenv("TIMUS_CANVAS_MIRROR_LOG_INTERVAL", "1.2"))
            app.state.canvas_mirror_task = asyncio.create_task(
                _canvas_mirror_log_worker(interval_seconds=interval_s)
            )
            log.info(
                "✅ Canvas mirror logger aktiviert (TIMUS_CANVAS_MIRROR_LOG=true, interval=%.1fs)",
                max(0.3, interval_s),
            )
        except Exception as e:
            log.warning(f"⚠️ Canvas mirror logger konnte nicht gestartet werden: {e}")
    else:
        log.info("ℹ️ Canvas mirror logger deaktiviert (TIMUS_CANVAS_MIRROR_LOG=false)")

    # System initialisieren (Hardware, Clients, Tools)
    _initialize_hardware_and_engines()
    _initialize_shared_clients()
    loaded, failed = _load_all_tools_and_skills()

    # Agent-Registry: Alle Agenten als Specs registrieren (Lazy-Instantiierung)
    try:
        from agent.agent_registry import register_all_agents
        import agent.agent_registry as _agent_reg_mod

        register_all_agents()

        # SSE-Hook für Delegation-Animationen im Canvas
        def _delegation_sse_event(from_agent: str, to_agent: str, status: str) -> None:
            _broadcast_sse({"type": "delegation", "from": from_agent, "to": to_agent, "status": status})

        def _delegation_transport_event(payload: dict) -> None:
            if not isinstance(payload, dict):
                return
            _emit_longrun_progress_from_payload(
                agent=str(payload.get("to_agent") or "").strip(),
                stage=str(payload.get("stage") or "").strip(),
                payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            )

        _agent_reg_mod._delegation_sse_hook = _delegation_sse_event
        _agent_reg_mod._delegation_transport_hook = _delegation_transport_event
        log.info("✅ Agent-Registry: Alle Agenten-Specs registriert. Delegation-SSE- und C4-Hooks aktiv.")
    except Exception as e:
        log.warning(f"⚠️ Agent-Registry konnte nicht initialisiert werden: {e}")

    # Inception-Status ermitteln & loggen
    inception_env_url = (
        os.getenv("INCEPTION_URL") or os.getenv("INCEPTION_API_URL") or ""
    )
    inception_registered = _detect_inception_registered()
    app.state.inception = {
        "registered": bool(inception_registered),
        "env_url": inception_env_url or None,
        "health": {"ok": None, "detail": "not_checked_yet"},
    }

    if inception_registered:
        log.info("✅ Inception-Tool registriert (Methoden vorhanden).")
    else:
        log.warning("❌ Inception-Tool NICHT registriert (keine passenden Methoden).")
    if inception_env_url:
        log.info(f"🔗 Inception-URL aus ENV: {inception_env_url}")
    else:
        log.warning("⚠️ Keine INCEPTION_URL/INCEPTION_API_URL in ENV gesetzt.")

    # Finales Status-Logging
    log.info("=" * 50)
    log.info("🌐 TIMUS MCP SERVER NIMMT ANFRAGEN AN (optionale Warmups laufen im Hintergrund)")
    log.info(
        f"📦 {len(loaded)}/{len(TOOL_MODULES)} Module geladen. Fehlgeschlagen: {len(failed)}"
    )
    if failed:
        for mod, err in failed:
            log.warning(f"  -> {mod}: {err}")

    registered_tools = registry_v2.list_all_tools()
    log.info(f"🔧 {len(registered_tools)} RPC-Methoden registriert:")
    for tool_name in sorted(registered_tools.keys()):
        log.info(f"  - {tool_name}")
    log.info("=" * 50)

    _set_app_mcp_lifecycle(
        app,
        phase="warmup",
        status="healthy",
        ready=True,
        warmup_pending=True,
        transient=False,
        last_error=None,
    )
    app.state.post_startup_warmup_task = asyncio.create_task(_run_post_startup_warmups(app))

    yield  # Server läuft

    log.info("🛑 TIMUS MCP SERVER SHUTDOWN beginnt...")
    _set_app_mcp_lifecycle(
        app,
        phase="shutdown",
        status="shutting_down",
        ready=False,
        warmup_pending=False,
        transient=True,
    )
    try:
        app.state.sse_shutdown_event.set()
        _broadcast_sse({"type": "server_shutdown", "ts": datetime.utcnow().isoformat() + "Z"})
    except Exception:
        pass

    await _cancel_background_task(
        "post_startup_warmup_task",
        getattr(app.state, "post_startup_warmup_task", None),
        timeout_s=3.0,
    )

    # === SHUTDOWN: Voice-Task abbrechen ===
    global _voice_listen_task
    if _voice_listen_task:
        try:
            from tools.voice_tool.tool import voice_engine

            voice_engine.stop_listening()
        except Exception:
            pass
        await _cancel_background_task("voice_listen_task", _voice_listen_task)
        _voice_listen_task = None

    # === SHUTDOWN: Canvas mirror logger stoppen ===
    await _cancel_background_task(
        "canvas_mirror_task",
        getattr(app.state, "canvas_mirror_task", None),
    )

    # === SHUTDOWN: Browser-Ressourcen schließen ===
    browser_shutdown_steps = []
    if shared_context.browser_context_manager:
        browser_shutdown_steps.append(
            _shutdown_async_step(
                "persistent_browser_context_manager",
                shared_context.browser_context_manager.shutdown(),
                timeout_s=8.0,
            )
        )
        shared_context.browser_context_manager = None

    try:
        from tools.browser_tool.tool import shutdown_browser_tool

        browser_shutdown_steps.append(
            _shutdown_async_step("legacy_browser_tool", shutdown_browser_tool(), timeout_s=8.0)
        )
    except Exception as exc:
        log.warning("⚠️ Legacy Browser-Tool Shutdown konnte nicht vorbereitet werden: %s", exc)

    if browser_shutdown_steps:
        await asyncio.gather(*browser_shutdown_steps, return_exceptions=True)

    # === SHUTDOWN: Scheduler stoppen ===
    if app.state.scheduler:
        await _shutdown_async_step("heartbeat_scheduler", app.state.scheduler.stop(), timeout_s=5.0)
        app.state.scheduler = None

    # === SHUTDOWN: RealSense Stream stoppen ===
    if getattr(app.state, "realsense_stream_manager", None):
        try:
            status = await asyncio.wait_for(
                asyncio.to_thread(app.state.realsense_stream_manager.stop),
                timeout=5.0,
            )
            log.info(f"✅ RealSense-Stream gestoppt: {status}")
        except asyncio.TimeoutError:
            log.warning("⚠️ RealSense-Stream Shutdown Timeout")
        except Exception as e:
            log.warning(f"⚠️ Fehler beim RealSense-Stream Shutdown: {e}")


# --- App-Initialisierung mit Lifespan ---
app = FastAPI(title="Timus MCP Server", version="1.6.0 (Cleaned)", lifespan=lifespan)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API Endpoints ---
@app.get("/health", summary="Health Check")
async def health_check():
    return _build_health_payload(app)


async def _build_tools_description() -> str:
    """Erstellt vollständige Tool+Skills-Beschreibung.

    Zentrale Hilfsfunktion — genutzt von /get_tool_descriptions UND /chat,
    damit beide exakt dieselbe Beschreibung erhalten.
    """
    try:
        descriptions = registry_v2.get_tool_manifest()
    except Exception as e:
        log.error(f"get_tool_manifest() fehlgeschlagen: {e}", exc_info=True)
        descriptions = "Tool-Beschreibungen konnten nicht geladen werden."

    # Skills anhängen
    skills_section = "\n\n# VERFÜGBARE SKILLS (Wiederverwendbare Workflows)\n"
    skills_section += "Nutze 'run_skill' um einen Skill auszuführen.\n\n"
    try:
        skills_result = await async_dispatch(
            '{"jsonrpc":"2.0","method":"list_available_skills","id":99}',
            serializer=numpy_aware_serializer,
        )
        import json as _json_local
        skills_data = _json_local.loads(skills_result)
        if "result" in skills_data and "skills" in skills_data["result"]:
            for skill in skills_data["result"]["skills"]:
                skills_section += f"- **{skill['name']}**: {skill['description']}\n"
            skills_section += (
                '\nBeispiel: Action: {"method": "run_skill", "params": '
                '{"name": "search_google", "params": {"query": "Suchbegriff"}}}\n'
            )
    except Exception as e:
        log.warning(f"Skills konnten nicht geladen werden: {e}")

    return descriptions + skills_section


@app.get("/get_tool_descriptions", summary="Get Tool Descriptions for Agents")
async def get_tool_descriptions():
    try:
        descriptions = await _build_tools_description()
        return {
            "status": "success",
            "descriptions": descriptions,
            "tool_count": len(registry_v2.list_all_tools()),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        log.error(f"❌ Fehler beim Abrufen der Tool-Beschreibungen: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "descriptions": "Fehler beim Laden der Tool-Beschreibungen",
                "error": str(e),
                "tool_count": 0,
            },
        )


@app.get("/get_tool_schemas/openai", summary="Get OpenAI-compatible Tool Schemas")
async def get_tool_schemas_openai():
    try:
        return {
            "status": "success",
            "tools": registry_v2.get_openai_tools_schema(),
            "tool_count": len(registry_v2.list_all_tools()),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        log.error(f"Fehler beim Abrufen der OpenAI-Schemas: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.get("/get_tool_schemas/anthropic", summary="Get Anthropic-compatible Tool Schemas")
async def get_tool_schemas_anthropic():
    try:
        return {
            "status": "success",
            "tools": registry_v2.get_anthropic_tools_schema(),
            "tool_count": len(registry_v2.list_all_tools()),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        log.error(f"Fehler beim Abrufen der Anthropic-Schemas: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.get("/get_tools_by_capability/{capability}", summary="Get Tools by Capability")
async def get_tools_by_capability(capability: str):
    try:
        tools = registry_v2.get_tools_by_capability(capability)
        return {
            "status": "success",
            "capability": capability,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "category": t.category.value,
                }
                for t in tools
            ],
            "count": len(tools),
        }
    except Exception as e:
        log.error(f"Fehler bei Capability-Abfrage: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.get("/canvas", summary="List Canvas Documents")
async def list_canvas(limit: int = 50):
    try:
        data = canvas_store.list_canvases(limit=limit)
        return {
            "status": "success",
            "count": data["count"],
            "items": data["items"],
        }
    except Exception as e:
        log.error(f"Canvas-List Fehler: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.get("/canvas/ui", summary="Canvas Web UI", response_class=HTMLResponse)
async def canvas_ui():
    return HTMLResponse(content=build_canvas_ui_html())


@app.post("/canvas/create", summary="Create Canvas")
async def create_canvas(payload: dict):
    try:
        title = (payload or {}).get("title", "")
        description = (payload or {}).get("description", "")
        metadata = (payload or {}).get("metadata", {})
        canvas = canvas_store.create_canvas(
            title=title,
            description=description,
            metadata=metadata,
        )
        return {"status": "success", "canvas": canvas}
    except Exception as e:
        log.error(f"Canvas-Create Fehler: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.get("/canvas/{canvas_id}", summary="Get Canvas")
async def get_canvas(
    canvas_id: str,
    session_id: str = "",
    agent: str = "",
    status: str = "",
    only_errors: bool = False,
    event_limit: int = 200,
):
    try:
        canvas = canvas_store.get_canvas_view(
            canvas_id=canvas_id,
            session_id=session_id,
            agent=agent,
            status=status,
            only_errors=only_errors,
            event_limit=event_limit,
        )
        if not canvas:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "error": "canvas_not_found"},
            )
        return {"status": "success", "canvas": canvas}
    except Exception as e:
        log.error(f"Canvas-Get Fehler: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.get("/canvas/by_session/{session_id}", summary="Get Canvas by Session")
async def get_canvas_by_session(
    session_id: str,
    agent: str = "",
    status: str = "",
    only_errors: bool = False,
    event_limit: int = 200,
):
    try:
        canvas = canvas_store.get_canvas_by_session_view(
            session_id=session_id,
            agent=agent,
            status=status,
            only_errors=only_errors,
            event_limit=event_limit,
        )
        if not canvas:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "error": "canvas_for_session_not_found"},
            )
        return {"status": "success", "canvas": canvas}
    except Exception as e:
        log.error(f"Canvas-by-session Fehler: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.post("/canvas/{canvas_id}/attach_session", summary="Attach Session to Canvas")
async def attach_session(canvas_id: str, payload: dict):
    session_id = (payload or {}).get("session_id", "")
    if not session_id:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "session_id_required"},
        )
    try:
        mapping = canvas_store.attach_session(canvas_id=canvas_id, session_id=session_id)
        return {"status": "success", "mapping": mapping}
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "error": "canvas_not_found"},
        )
    except Exception as e:
        log.error(f"Canvas attach_session Fehler: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.post("/canvas/{canvas_id}/nodes/upsert", summary="Upsert Canvas Node")
async def upsert_canvas_node(canvas_id: str, payload: dict):
    node_id = (payload or {}).get("node_id", "")
    node_type = (payload or {}).get("node_type", "generic")
    title = (payload or {}).get("title", node_id)
    status = (payload or {}).get("status", "idle")
    position = (payload or {}).get("position")
    metadata = (payload or {}).get("metadata", {})
    if not node_id:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "node_id_required"},
        )
    try:
        node = canvas_store.upsert_node(
            canvas_id=canvas_id,
            node_id=node_id,
            node_type=node_type,
            title=title,
            status=status,
            position=position,
            metadata=metadata,
        )
        return {"status": "success", "node": node}
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "error": "canvas_not_found"},
        )
    except Exception as e:
        log.error(f"Canvas upsert_node Fehler: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.post("/canvas/{canvas_id}/edges/add", summary="Add Canvas Edge")
async def add_canvas_edge(canvas_id: str, payload: dict):
    source = (payload or {}).get("source_node_id", "")
    target = (payload or {}).get("target_node_id", "")
    label = (payload or {}).get("label", "")
    kind = (payload or {}).get("kind", "flow")
    metadata = (payload or {}).get("metadata", {})
    if not source or not target:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "source_node_id_and_target_node_id_required"},
        )
    try:
        edge = canvas_store.add_edge(
            canvas_id=canvas_id,
            source_node_id=source,
            target_node_id=target,
            label=label,
            kind=kind,
            metadata=metadata,
        )
        return {"status": "success", "edge": edge}
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "error": "canvas_not_found"},
        )
    except Exception as e:
        log.error(f"Canvas add_edge Fehler: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.post("/canvas/{canvas_id}/events/add", summary="Add Canvas Event")
async def add_canvas_event(canvas_id: str, payload: dict):
    event_type = (payload or {}).get("event_type", "")
    if not event_type:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "event_type_required"},
        )
    try:
        event = canvas_store.add_event(
            canvas_id=canvas_id,
            event_type=event_type,
            status=(payload or {}).get("status", ""),
            agent=(payload or {}).get("agent", ""),
            node_id=(payload or {}).get("node_id", ""),
            message=(payload or {}).get("message", ""),
            session_id=(payload or {}).get("session_id", ""),
            payload=(payload or {}).get("payload", {}),
        )
        return {"status": "success", "event": event}
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "error": "canvas_not_found"},
        )
    except Exception as e:
        log.error(f"Canvas add_event Fehler: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.get("/agent_status", summary="Agenten-Status & Thinking-LED")
async def get_agent_status_endpoint():
    return {
        "status": "success",
        "agents": _agent_status,
        "thinking": _thinking_active,
    }


@app.get("/status/snapshot", summary="Strukturierter Betriebs-/Kosten-Snapshot")
async def status_snapshot_endpoint():
    try:
        snapshot = await collect_status_snapshot()
        return {"status": "success", "snapshot": snapshot}
    except Exception as e:
        log.error(f"Status-Snapshot Fehler: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/events/stream", summary="SSE-Stream für Echtzeit-Canvas-Updates")
async def events_stream(request: Request):
    """Server-Sent Events: Pushing agent-status, thinking-LED und Chat-Events."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    shutdown_event = getattr(app.state, "sse_shutdown_event", None)
    if shutdown_event is None:
        shutdown_event = asyncio.Event()
        app.state.sse_shutdown_event = shutdown_event
    loop = asyncio.get_running_loop()
    started_monotonic = loop.time()
    max_connection_age_s = _sse_connection_ttl_sec()
    with _sse_lock:
        _sse_queues.append(queue)

    async def generator():
        try:
            init_data = _json.dumps(
                {"type": "init", "agents": _agent_status, "thinking": _thinking_active},
                ensure_ascii=False,
            )
            yield f"data: {init_data}\n\n"
            while True:
                timeout_s = 25.0
                if max_connection_age_s > 0:
                    elapsed = loop.time() - started_monotonic
                    remaining = max_connection_age_s - elapsed
                    if remaining <= 0:
                        yield 'data: {"type":"server_refresh"}\n\n'
                        break
                    timeout_s = min(25.0, max(0.2, remaining))
                if shutdown_event.is_set() or await request.is_disconnected():
                    break
                kind, data = await _await_sse_queue_item(
                    queue,
                    shutdown_event,
                    timeout_s=timeout_s,
                )
                if kind == "shutdown":
                    break
                if kind == "data" and data is not None:
                    yield f"data: {data}\n\n"
                else:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            with _sse_lock:
                try:
                    _sse_queues.remove(queue)
                except ValueError:
                    pass

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat", summary="Interaktiver Chat mit Timus")
async def canvas_chat(request: Request):
    """Sendet eine Nachricht an Timus und gibt die Antwort zurück (SSE pushed ebenfalls)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400, content={"status": "error", "error": "invalid_json"}
        )

    query = (body or {}).get("query", "").strip()
    if not query:
        return JSONResponse(
            status_code=400, content={"status": "error", "error": "query_required"}
        )
    response_language = ((body or {}).get("response_language") or "").strip().lower()

    session_id = (body or {}).get("session_id") or f"canvas_{uuid.uuid4().hex[:8]}"
    request_id = str((body or {}).get("request_id") or f"req_{uuid.uuid4().hex[:12]}").strip()
    ts = datetime.utcnow().isoformat() + "Z"

    followup_capsule = _build_followup_capsule(session_id, query=query)
    followup_agent = _resolve_followup_agent(query, followup_capsule)
    dispatcher_query = _augment_query_with_followup_capsule(query, followup_capsule)
    location_snapshot = _get_location_snapshot()
    location_decision = evaluate_location_chat_context(
        query=query,
        snapshot=location_snapshot,
        enabled=_chat_location_context_enabled(),
    )

    # P4: RESOLVED_PROPOSAL → Agenten direkt setzen, Proposal aus Kapsel löschen
    resolved_proposal_agent = ""
    if dispatcher_query.startswith("# RESOLVED_PROPOSAL"):
        resolved_proposal_agent = _resolve_resolved_proposal_agent(dispatcher_query)
        # Proposal einmalig konsumiert → löschen damit es nicht wiederholt ausgelöst wird
        _store_proposal_in_capsule(session_id, None)
    dispatcher_query_kind = (
        "resolved_proposal"
        if dispatcher_query.startswith("# RESOLVED_PROPOSAL")
        else "followup"
        if dispatcher_query.startswith("# FOLLOW-UP CONTEXT")
        else "plain"
    )

    _append_chat_entry(session_id=session_id, role="user", text=query, ts=ts)

    _record_chat_observation(
        "chat_request_received",
        {
            "request_id": request_id,
            "session_id": session_id,
            "source": "canvas_chat",
            "query_preview": query[:180],
            "response_language": response_language,
            "dispatcher_query_kind": dispatcher_query_kind,
            "followup_agent": followup_agent,
            "resolved_proposal_agent": resolved_proposal_agent,
        },
    )
    challenge_resume_payload = _build_challenge_resume_observation_payload(followup_capsule)
    if challenge_resume_payload:
        _record_chat_observation(
            "challenge_resume",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                **challenge_resume_payload,
            },
        )
    decay_info = dict(followup_capsule.get("conversation_state_decay") or {})
    if bool(decay_info.get("applied")):
        _record_chat_observation(
            "conversation_state_decayed",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "reasons": list(decay_info.get("reasons") or []),
                "age_hours": float(decay_info.get("age_hours") or 0.0),
            },
        )

    _broadcast_sse({"type": "chat_user", "request_id": request_id, "text": query, "ts": ts})

    agent = "executor"
    run_id = new_run_id()
    longrun_terminal_emitted = False
    meta_classification: dict | None = None
    pending_workflow_updated = False
    try:
        import main_dispatcher as _dispatcher_mod
        from main_dispatcher import run_agent, get_agent_decision

        # Tool-Beschreibungen — identisch zu /get_tool_descriptions
        tools_desc = await _build_tools_description()

        with bind_request_correlation(request_id=request_id, session_id=session_id), bind_longrun_context(run_id=run_id):
            previous_agent_progress_hook = getattr(_dispatcher_mod, "_agent_progress_hook", None)

            def _dispatcher_progress_event(payload: dict) -> None:
                nonlocal pending_workflow_updated
                if not isinstance(payload, dict):
                    return
                stage = str(payload.get("stage") or "").strip()
                payload_info = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
                agent_name = str(payload.get("agent") or "").strip()
                if is_pending_workflow_state(payload_info):
                    stored_workflow = _record_pending_workflow_runtime(
                        session_id=session_id,
                        request_id=request_id,
                        agent_name=agent_name,
                        stage=stage,
                        workflow=payload_info,
                        followup_capsule=followup_capsule,
                        updated_at=datetime.utcnow().isoformat() + "Z",
                    )
                    pending_workflow_updated = bool(stored_workflow)
                elif str(payload_info.get("kind") or "").strip().lower() == "auth_session":
                    stored_auth_session = _store_auth_session_in_capsule(
                        session_id,
                        {
                            "status": str(payload_info.get("auth_session_status") or ""),
                            "service": str(payload_info.get("auth_session_service") or ""),
                            "url": str(payload_info.get("auth_session_url") or ""),
                            "scope": str(payload_info.get("auth_session_scope") or ""),
                            "workflow_id": str(payload_info.get("auth_session_workflow_id") or ""),
                            "reason": str(payload_info.get("auth_session_reason") or ""),
                            "browser_type": str(payload_info.get("auth_session_browser_type") or ""),
                            "credential_broker": str(payload_info.get("auth_session_credential_broker") or ""),
                            "broker_profile": str(payload_info.get("auth_session_broker_profile") or ""),
                            "domain": str(payload_info.get("auth_session_domain") or ""),
                            "source_agent": agent_name,
                            "source_stage": stage,
                            "reuse_ready": bool(payload_info.get("auth_session_reuse_ready")),
                            "evidence": str(payload_info.get("auth_session_evidence") or ""),
                        },
                        updated_at=datetime.utcnow().isoformat() + "Z",
                    )
                    if stored_auth_session:
                        _record_chat_observation(
                            "auth_session_updated",
                            {
                                "request_id": request_id,
                                "session_id": session_id,
                                "source": "canvas_chat",
                                "agent": agent_name,
                                "stage": stage,
                                "auth_session_service": str(stored_auth_session.get("service") or ""),
                                "auth_session_status": str(stored_auth_session.get("status") or ""),
                                "auth_session_scope": str(stored_auth_session.get("scope") or ""),
                                "auth_session_workflow_id": str(stored_auth_session.get("workflow_id") or ""),
                                "auth_session_browser_type": str(stored_auth_session.get("browser_type") or ""),
                                "auth_session_credential_broker": str(stored_auth_session.get("credential_broker") or ""),
                            },
                        )
                _emit_longrun_progress_from_payload(
                    agent=agent_name,
                    stage=stage,
                    payload=payload_info,
                )

            _dispatcher_mod._agent_progress_hook = _dispatcher_progress_event
            try:
                route_source = (
                    "resolved_proposal"
                    if resolved_proposal_agent
                    else "followup_capsule"
                    if followup_agent
                    else "dispatcher"
                )
                preselected_agent = resolved_proposal_agent or followup_agent
                if preselected_agent:
                    agent = preselected_agent
                else:
                    try:
                        agent = await get_agent_decision(
                            dispatcher_query,
                            session_id=session_id,
                            request_id=request_id,
                        )
                    except TypeError as decision_error:
                        if "request_id" not in str(decision_error):
                            raise
                        agent = await get_agent_decision(
                            dispatcher_query,
                            session_id=session_id,
                        )
                _record_chat_observation(
                    "request_route_selected",
                    {
                        "request_id": request_id,
                        "session_id": session_id,
                        "source": "canvas_chat",
                        "agent": agent,
                        "route_source": route_source,
                        "dispatcher_query_kind": dispatcher_query_kind,
                        "followup_agent": followup_agent,
                        "resolved_proposal_agent": resolved_proposal_agent,
                    },
                )
                if agent == "meta":
                    try:
                        from orchestration.meta_orchestration import classify_meta_task

                        meta_classification = classify_meta_task(
                            dispatcher_query,
                            action_count=0,
                            conversation_state=followup_capsule.get("conversation_state"),
                            recent_user_turns=followup_capsule.get("recent_user_queries"),
                            recent_assistant_turns=followup_capsule.get("recent_assistant_replies"),
                            session_summary=str(followup_capsule.get("session_summary") or ""),
                            topic_history=followup_capsule.get("topic_history"),
                            semantic_recall_hits=followup_capsule.get("semantic_recall"),
                        )
                        updated_state = _persist_meta_turn_understanding(
                            session_id=session_id,
                            classification=meta_classification,
                            updated_at=ts,
                        )
                        _capture_meta_preference_memory(
                            request_id=request_id,
                            session_id=session_id,
                            classification=meta_classification,
                            updated_state=updated_state,
                            updated_at=ts,
                        )
                        _record_meta_turn_understanding_observations(
                            request_id=request_id,
                            session_id=session_id,
                            classification=meta_classification,
                            updated_state=updated_state,
                        )
                    except Exception as turn_exc:
                        log.debug("Meta turn-understanding konnte nicht persistiert werden: %s", turn_exc)
                _emit_longrun_event(
                    "run_started",
                    request_id=request_id,
                    session_id=session_id,
                    run_id=run_id,
                    agent=agent,
                    message=f"{agent} bearbeitet die Anfrage jetzt.",
                )
                _set_agent_status(agent, "thinking", query)

                query_for_agent = dispatcher_query
                if location_decision.should_inject and isinstance(location_snapshot, dict):
                    query_for_agent = (
                        build_location_chat_context_block(location_snapshot)
                        + "\n\n"
                        + query_for_agent
                    )
                if response_language in {"de", "deutsch", "german"} and agent not in {"visual", "visual_nemotron"}:
                    query_for_agent = (
                        "Antworte ausschließlich auf Deutsch. "
                        "Nutze nur dann englische Fachbegriffe, wenn sie technisch nötig sind.\n\n"
                        f"Nutzeranfrage:\n{query_for_agent}"
                    )

                try:
                    result = await run_agent(
                        agent_name=agent,
                        query=query_for_agent,
                        tools_description=tools_desc,
                        session_id=session_id,
                        meta_handoff_policy=meta_classification if agent == "meta" else None,
                    )
                except TypeError as run_agent_error:
                    if "meta_handoff_policy" not in str(run_agent_error):
                        raise
                    result = await run_agent(
                        agent_name=agent,
                        query=query_for_agent,
                        tools_description=tools_desc,
                        session_id=session_id,
                    )
                if agent == "meta":
                    try:
                        from main_dispatcher import pop_last_agent_runtime_metadata

                        runtime_state = pop_last_agent_runtime_metadata(session_id)
                        _persist_meta_runtime_plan_state(
                            session_id=session_id,
                            runtime_metadata=runtime_state,
                            updated_at=datetime.utcnow().isoformat() + "Z",
                        )
                    except Exception as runtime_plan_exc:
                        log.debug("Meta runtime plan state konnte nicht persistiert werden: %s", runtime_plan_exc)
                _emit_longrun_event(
                    "run_completed",
                    request_id=request_id,
                    session_id=session_id,
                    run_id=run_id,
                    agent=agent,
                    message=f"{agent} hat die Anfrage abgeschlossen.",
                )
                longrun_terminal_emitted = True
            except Exception as run_error:
                _emit_longrun_event(
                    "run_failed",
                    request_id=request_id,
                    session_id=session_id,
                    run_id=run_id,
                    agent=agent or "dispatcher",
                    stage="failed",
                    message=f"{agent or 'dispatcher'} ist fehlgeschlagen.",
                    error_class=run_error.__class__.__name__,
                    error_code="canvas_chat_exception",
                )
                longrun_terminal_emitted = True
                raise
            finally:
                _dispatcher_mod._agent_progress_hook = previous_agent_progress_hook

        _set_agent_status(agent, "completed", query)
        reply, rendered_phase_d_workflow = _render_chat_reply(result)
        reply_ts = datetime.utcnow().isoformat() + "Z"

        if rendered_phase_d_workflow and not pending_workflow_updated:
            stored_workflow = _record_pending_workflow_runtime(
                session_id=session_id,
                request_id=request_id,
                agent_name=agent,
                stage="chat_reply_workflow",
                workflow=rendered_phase_d_workflow,
                followup_capsule=followup_capsule,
                updated_at=reply_ts,
            )
            pending_workflow_updated = bool(stored_workflow)

        _append_chat_entry(
            session_id=session_id,
            role="assistant",
            agent=agent,
            text=reply,
            ts=reply_ts,
        )

        # P4: Proposal aus Assistenten-Antwort extrahieren und in Kapsel speichern
        # (bei Zustimmung in der nächsten Runde direkt auflösen)
        proposal = _extract_proposal_metadata(reply)
        _store_proposal_in_capsule(session_id, proposal)
        pending_followup_prompt = _extract_pending_followup_prompt(reply)
        _store_pending_followup_prompt_in_capsule(session_id, pending_followup_prompt)
        previous_pending_workflow = followup_capsule.get("pending_workflow") if isinstance(followup_capsule.get("pending_workflow"), dict) else {}
        pending_workflow_reply = followup_capsule.get("pending_workflow_reply") if isinstance(followup_capsule.get("pending_workflow_reply"), dict) else {}
        pending_workflow_reply_kind = str(pending_workflow_reply.get("reply_kind") or "").strip().lower()
        if (
            previous_pending_workflow
            and not pending_workflow_updated
            and (
                str((meta_classification or {}).get("dominant_turn_type") or "").strip().lower()
                in {"approval_response", "auth_response", "handover_resume"}
                or (
                    pending_workflow_reply_kind in {"resume_requested", "challenge_resolved"}
                    and agent == str(previous_pending_workflow.get("source_agent") or "").strip()
                )
            )
        ):
            previous_pending_status = str(previous_pending_workflow.get("status") or "").strip().lower()
            previous_pending_challenge_type = str(previous_pending_workflow.get("challenge_type") or "").strip().lower()
            previous_pending_service = str(
                previous_pending_workflow.get("service") or previous_pending_workflow.get("platform") or ""
            ).strip().lower()
            previous_pending_workflow_id = str(previous_pending_workflow.get("workflow_id") or "").strip()
            _store_pending_workflow_in_capsule(
                session_id,
                clear_pending_workflow_state(),
                updated_at=reply_ts,
            )
            if previous_pending_status == "challenge_required" and pending_workflow_reply_kind in {"resume_requested", "challenge_resolved"}:
                _record_chat_observation(
                    "challenge_resolved",
                    {
                        "request_id": request_id,
                        "session_id": session_id,
                        "source": "canvas_chat",
                        "agent": agent,
                        "workflow_id": previous_pending_workflow_id,
                        "service": previous_pending_service,
                        "challenge_type": previous_pending_challenge_type,
                        "reply_kind": pending_workflow_reply_kind,
                    },
                )
            _record_chat_observation(
                "pending_workflow_cleared",
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "source": "canvas_chat",
                    "agent": agent,
                    "reason": "workflow_response_resolved_without_new_blocker",
                    "previous_status": str(previous_pending_workflow.get("status") or ""),
                    "previous_workflow_id": str(previous_pending_workflow.get("workflow_id") or ""),
                },
            )
        _log_chat_interaction(
            session_id=session_id,
            user_input=query,
            assistant_response=reply,
            agent=agent,
            metadata={
                "request_id": request_id,
                "dispatcher_query_kind": dispatcher_query_kind,
                "followup_agent": followup_agent,
                "location_context_injected": bool(
                    location_decision.should_inject and isinstance(location_snapshot, dict)
                ),
                "pending_followup_prompt": pending_followup_prompt,
                "response_language": response_language,
                "dominant_turn_type": str((meta_classification or {}).get("dominant_turn_type") or ""),
                "response_mode": str((meta_classification or {}).get("response_mode") or ""),
            },
        )

        _record_chat_observation(
            "chat_request_completed",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "agent": agent,
                "route_source": route_source,
                "dispatcher_query_kind": dispatcher_query_kind,
                "reply_length": len(reply),
                "location_context_injected": bool(
                    location_decision.should_inject and isinstance(location_snapshot, dict)
                ),
                "pending_followup_prompt": pending_followup_prompt,
                "dominant_turn_type": str((meta_classification or {}).get("dominant_turn_type") or ""),
                "response_mode": str((meta_classification or {}).get("response_mode") or ""),
            },
        )

        _broadcast_sse({"type": "chat_reply", "request_id": request_id, "agent": agent, "text": reply, "ts": reply_ts})
        response_payload = {
            "status": "success",
            "agent": agent,
            "reply": reply,
            "session_id": session_id,
            "request_id": request_id,
        }
        if rendered_phase_d_workflow:
            response_payload["phase_d_workflow"] = rendered_phase_d_workflow
        return response_payload

    except Exception as e:
        log.error(f"Canvas-Chat Fehler: {e}", exc_info=True)
        if not longrun_terminal_emitted:
            with bind_request_correlation(request_id=request_id, session_id=session_id), bind_longrun_context(run_id=run_id):
                _emit_longrun_event(
                    "run_failed",
                    request_id=request_id,
                    session_id=session_id,
                    run_id=run_id,
                    agent=agent or "dispatcher",
                    stage="failed",
                    message=f"{agent or 'dispatcher'} ist fehlgeschlagen.",
                    error_class=e.__class__.__name__,
                    error_code="canvas_chat_exception",
                )
        _set_agent_status(agent, "error", query)
        _record_chat_observation(
            "chat_request_failed",
            {
                "request_id": request_id,
                "session_id": session_id,
                "source": "canvas_chat",
                "agent": agent,
                "dispatcher_query_kind": dispatcher_query_kind,
                "followup_agent": followup_agent,
                "resolved_proposal_agent": resolved_proposal_agent,
                "query_preview": query[:180],
                "error_class": "canvas_chat_exception",
                "error": str(e)[:240],
            },
        )
        _broadcast_sse({"type": "chat_error", "request_id": request_id, "error": str(e)})
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e), "request_id": request_id}
        )


@app.get("/chat/history", summary="Chat-Verlauf abrufen")
async def get_chat_history_endpoint():
    with _chat_lock:
        return {"status": "success", "history": list(_chat_history)}


@app.get("/agent_models", summary="Aktive Modell-Konfiguration pro Agent")
async def get_agent_models():
    """Gibt Provider und Modell-Name für jeden Agenten zurück (für Canvas LEDs)."""
    from agent.providers import AgentModelConfig
    agents = ["executor", "research", "reasoning", "creative", "development",
              "meta", "visual", "data", "document", "communication", "system",
              "shell", "image"]
    models = {}
    for agent in agents:
        key = agent if agent != "research" else "deep_research"
        try:
            model, provider = AgentModelConfig.get_model_and_provider(key)
            models[agent] = {"provider": provider.value, "model": model}
        except Exception:
            models[agent] = {"provider": "unknown", "model": ""}
    return {"status": "success", "models": models}


# ── AUTONOMY ENDPOINTS ────────────────────────────────────────────────────────

@app.get("/autonomy/scorecard", summary="Autonomy Scorecard (M1-M5)")
async def autonomy_scorecard_endpoint(window_hours: int = 24):
    """Liefert die aggregierte Autonomie-Scorecard aus M1-M5."""
    try:
        from orchestration.autonomy_scorecard import build_autonomy_scorecard
        card = build_autonomy_scorecard(window_hours=max(1, window_hours))
        return {"status": "success", "scorecard": card}
    except Exception as e:
        log.error(f"Autonomy scorecard Fehler: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/autonomy/goals", summary="Aktive Autonomy-Ziele (M1)")
async def autonomy_goals_endpoint(status: str = "", limit: int = 20):
    """Gibt die Liste der Autonomie-Ziele zurück (aus goals-Tabelle)."""
    try:
        from orchestration.task_queue import get_queue
        queue = get_queue()
        goals = queue.list_goals(status=status or None, limit=max(1, min(200, limit)))
        return {"status": "success", "goals": goals, "count": len(goals)}
    except Exception as e:
        log.error(f"Autonomy goals Fehler: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/autonomy/plans", summary="Aktive Autonomy-Pläne (M2)")
async def autonomy_plans_endpoint(horizon: str = ""):
    """Gibt aktive Pläne mit Horizont, Items und Commitments zurück."""
    try:
        from orchestration.task_queue import get_queue
        queue = get_queue()
        planning = queue.get_planning_metrics()
        # Kompakte Plan-Übersicht aus planning_metrics ableiten
        plans_data = {
            "active_plans": planning.get("active_plans", 0),
            "overdue_commitments": planning.get("overdue_commitments", 0),
            "commitments_total": planning.get("commitments_total", 0),
            "plan_deviation_score": planning.get("plan_deviation_score", 0.0),
            "planning_metrics": planning,
        }
        return {"status": "success", "plans": plans_data}
    except Exception as e:
        log.error(f"Autonomy plans Fehler: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/autonomy/health", summary="Autonomy Health Überblick (M1-M4)")
async def autonomy_health_endpoint():
    """Kompakter Gesundheitsüberblick: Goal-Alignment + Planning + Self-Healing."""
    try:
        from orchestration.task_queue import get_queue
        queue = get_queue()
        goal_metrics = queue.get_goal_alignment_metrics(include_conflicts=True)
        planning_metrics = queue.get_planning_metrics()
        healing_metrics = queue.get_self_healing_metrics()
        return {
            "status": "success",
            "health": {
                "goals": {
                    "open_alignment_rate": goal_metrics.get("open_alignment_rate", 0.0),
                    "conflict_count": goal_metrics.get("conflict_count", 0),
                    "open_tasks": goal_metrics.get("open_tasks", 0),
                },
                "planning": {
                    "active_plans": planning_metrics.get("active_plans", 0),
                    "overdue_commitments": planning_metrics.get("overdue_commitments", 0),
                    "plan_deviation_score": planning_metrics.get("plan_deviation_score", 0.0),
                },
                "healing": {
                    "degrade_mode": healing_metrics.get("degrade_mode", "normal"),
                    "open_incidents": healing_metrics.get("open_incidents", 0),
                    "circuit_breakers_open": healing_metrics.get("circuit_breakers_open", 0),
                    "recovery_rate_24h": healing_metrics.get("recovery_rate_24h", 0.0),
                },
            },
        }
    except Exception as e:
        log.error(f"Autonomy health Fehler: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


# ── M8-M12 AUTONOMY ENDPOINTS ─────────────────────────────────────────────────

@app.get("/autonomy/reflections", summary="Session-Reflexionen (M8)")
async def autonomy_reflections_endpoint(limit: int = 10):
    """Gibt die letzten Session-Reflexionen zurück."""
    try:
        from orchestration.session_reflection import SessionReflectionLoop
        loop = SessionReflectionLoop()
        reflections = await loop.get_recent_reflections(limit=min(50, limit))
        return {"status": "success", "reflections": reflections, "count": len(reflections)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/autonomy/suggestions", summary="Verbesserungsvorschläge aus Reflexion (M8)")
async def autonomy_suggestions_endpoint():
    """Gibt offene Verbesserungsvorschläge zurück."""
    try:
        from orchestration.session_reflection import SessionReflectionLoop
        loop = SessionReflectionLoop()
        suggestions = await loop.get_improvement_suggestions()
        return {"status": "success", "suggestions": suggestions, "count": len(suggestions)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/blackboard", summary="Agent Blackboard Übersicht (M9)")
async def blackboard_summary_endpoint():
    """Gibt Blackboard-Zusammenfassung zurück."""
    try:
        from memory.agent_blackboard import get_blackboard
        summary = get_blackboard().get_summary()
        return {"status": "success", **summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/triggers", summary="Proaktive Trigger auflisten (M10)")
async def triggers_list_endpoint():
    """Gibt alle proaktiven Trigger zurück."""
    try:
        from orchestration.proactive_triggers import get_trigger_engine
        triggers = get_trigger_engine().list_triggers()
        return {"status": "success", "triggers": triggers, "count": len(triggers)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.post("/triggers/{trigger_id}/enable", summary="Trigger aktivieren/deaktivieren (M10)")
async def trigger_enable_endpoint(trigger_id: str, enabled: bool = True):
    """Aktiviert oder deaktiviert einen Trigger."""
    try:
        from orchestration.proactive_triggers import get_trigger_engine
        found = get_trigger_engine().enable_trigger(trigger_id, enabled)
        return {
            "status": "success" if found else "not_found",
            "trigger_id": trigger_id,
            "enabled": enabled,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/goals/tree", summary="Ziel-Hierarchie als Cytoscape-Tree (M11)")
async def goals_tree_endpoint(root_id: str = ""):
    """Gibt den Ziel-Baum zurück (Cytoscape-Format)."""
    try:
        from orchestration.goal_queue_manager import get_goal_manager
        tree = get_goal_manager().get_goal_tree(root_id=root_id if root_id else None)
        return {"status": "success", "tree": tree}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/autonomy/observation", summary="Autonomy Observation Summary (C2)")
async def autonomy_observation_endpoint(since: str = "", until: str = ""):
    """Aggregierter Observation-Report: Request-Korrelation, Meta-Diagnostik, User-Impact."""
    try:
        from orchestration.autonomy_observation import (
            build_autonomy_observation_summary,
            render_autonomy_observation_markdown,
        )
        summary = build_autonomy_observation_summary(since=since, until=until)
        markdown = render_autonomy_observation_markdown(summary)
        return {"status": "success", "summary": summary, "markdown": markdown}
    except Exception as e:
        log.error(f"Autonomy observation Fehler: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/autonomy/incident/{request_id}", summary="Incident-Trace für eine request_id (C2)")
async def autonomy_incident_trace_endpoint(request_id: str, since: str = "", until: str = ""):
    """Gibt alle für eine request_id aufgezeichneten Korrelations-Events zurück."""
    try:
        from orchestration.autonomy_observation import get_incident_trace
        safe_id = str(request_id or "").strip()
        if not safe_id:
            return JSONResponse(status_code=400, content={"status": "error", "error": "request_id darf nicht leer sein"})
        trace = get_incident_trace(safe_id, since=since, until=until)
        return {
            "status": "success",
            "request_id": safe_id,
            "event_count": len(trace),
            "trace": trace,
        }
    except Exception as e:
        log.error(f"Incident-Trace Fehler: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/autonomy/improvement", summary="Self-Improvement Befunde (M12)")
async def autonomy_improvement_endpoint():
    """Gibt Self-Improvement Statistiken und Vorschläge zurück."""
    try:
        from orchestration.autonomy_observation import build_autonomy_observation_summary
        from orchestration.improvement_candidates import build_candidate_operator_views
        from orchestration.improvement_task_autonomy import (
            build_improvement_task_governance_view,
            build_improvement_task_autonomy_decisions,
            get_improvement_task_rollout_guard,
            get_improvement_task_autonomy_settings,
        )
        from orchestration.task_queue import get_queue
        from orchestration.improvement_task_bridge import build_improvement_task_bridges
        from orchestration.improvement_task_compiler import compile_improvement_tasks
        from orchestration.improvement_task_execution import build_improvement_hardening_task_payloads
        from orchestration.improvement_task_promotion import evaluate_compiled_task_promotions
        from orchestration.phase_e_operator_snapshot import (
            build_phase_e_operator_surface,
            collect_phase_e_operator_snapshot,
        )
        from orchestration.self_improvement_engine import get_improvement_engine
        from orchestration.session_reflection import SessionReflectionLoop
        engine = get_improvement_engine()
        tool_stats = engine.get_tool_stats(days=7)
        routing_stats = engine.get_routing_stats(days=7)
        suggestions = engine.get_suggestions(applied=False)
        normalized_candidates = engine.get_normalized_suggestions(applied=False)
        try:
            combined_candidates = await SessionReflectionLoop().get_improvement_suggestions()
        except Exception:
            combined_candidates = normalized_candidates
        compiled_tasks = compile_improvement_tasks(combined_candidates, limit=5)
        promotion_decisions = evaluate_compiled_task_promotions(compiled_tasks, limit=5)
        bridge_decisions = build_improvement_task_bridges(compiled_tasks, promotion_decisions, limit=5)
        execution_candidates = build_improvement_hardening_task_payloads(
            compiled_tasks,
            promotion_decisions,
            bridge_decisions,
            limit=5,
        )
        autonomy_settings = get_improvement_task_autonomy_settings()
        observation_summary = build_autonomy_observation_summary()
        queue = get_queue()
        rollout_guard = get_improvement_task_rollout_guard(queue)
        operator_snapshot = await collect_phase_e_operator_snapshot(limit=5, queue=queue)
        return {
            "status": "success",
            "tool_stats_count": len(tool_stats),
            "routing_decisions": routing_stats.get("total_decisions", 0),
            "open_suggestions": len(suggestions),
            "critical_suggestions": sum(1 for s in suggestions if s.get("severity") == "high"),
            "top_suggestions": suggestions[:5],
            "top_candidates": combined_candidates[:5],
            "top_candidate_insights": build_candidate_operator_views(combined_candidates, limit=5),
            "top_compiled_tasks": compiled_tasks,
            "top_task_promotion_decisions": promotion_decisions,
            "top_task_bridge_decisions": bridge_decisions,
            "top_task_execution_candidates": execution_candidates,
            "task_autonomy_settings": autonomy_settings,
            "improvement_governance": build_improvement_task_governance_view(
                queue=queue,
                rollout_guard=rollout_guard,
            ),
            "top_task_autonomy_decisions": build_improvement_task_autonomy_decisions(
                execution_candidates,
                rollout_guard=rollout_guard,
                allow_self_modify=bool(autonomy_settings.get("allow_self_modify")),
                max_autoenqueue=int(autonomy_settings.get("max_autoenqueue") or 1),
                limit=5,
            ),
            "improvement_runtime": dict(observation_summary.get("improvement_runtime") or {}),
            "memory_curation_runtime": dict(observation_summary.get("memory_curation_runtime") or {}),
            "candidate_count": len(combined_candidates),
            "operator_surface": build_phase_e_operator_surface(operator_snapshot, focus_lane="improvement"),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/autonomy/operator_snapshot", summary="Unified Phase-E Operator Snapshot")
async def autonomy_operator_snapshot_endpoint(limit: int = 5):
    """Gibt eine gemeinsame Operatorsicht ueber Improvement, Memory-Curation und Systemkontext zurueck."""
    try:
        from orchestration.phase_e_operator_snapshot import (
            build_phase_e_operator_surface,
            collect_phase_e_operator_snapshot,
        )

        snapshot = await collect_phase_e_operator_snapshot(limit=max(1, min(10, int(limit or 5))))
        snapshot["operator_surface"] = build_phase_e_operator_surface(snapshot)
        return {"status": "success", **snapshot}
    except Exception as e:
        log.error(f"Phase-E Operator Snapshot Fehler: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/autonomy/memory_curation", summary="Memory-Curation Status und Governance")
async def autonomy_memory_curation_endpoint():
    """Gibt E5 Memory-Curation-Status, Governance und aktuelle Kandidaten zurück."""
    try:
        from orchestration.autonomy_observation import build_autonomy_observation_summary
        from orchestration.phase_e_operator_snapshot import (
            build_phase_e_operator_surface,
            collect_phase_e_operator_snapshot,
        )
        from orchestration.task_queue import get_queue
        from orchestration.memory_curation import (
            get_memory_curation_autonomy_settings,
            get_memory_curation_status,
        )

        queue = get_queue()
        payload = get_memory_curation_status(queue=queue, stale_days=30, limit=5)
        observation_summary = build_autonomy_observation_summary()
        operator_snapshot = await collect_phase_e_operator_snapshot(limit=5, queue=queue)
        return {
            "status": "success",
            "memory_curation": payload,
            "autonomy_settings": get_memory_curation_autonomy_settings(),
            "autonomy_governance": dict(payload.get("autonomy_governance") or {}),
            "current_metrics": dict(payload.get("current_metrics") or {}),
            "last_snapshots": list(payload.get("last_snapshots") or []),
            "pending_candidates": list(payload.get("pending_candidates") or []),
            "pending_retrieval_probes": list(payload.get("pending_retrieval_probes") or []),
            "latest_retrieval_quality": dict(payload.get("latest_retrieval_quality") or {}),
            "quality_governance": dict(payload.get("quality_governance") or {}),
            "memory_curation_runtime": dict(observation_summary.get("memory_curation_runtime") or {}),
            "operator_surface": build_phase_e_operator_surface(operator_snapshot, focus_lane="memory_curation"),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/autonomy/runtime_board", summary="Phase-F Runtime-/Lane-Board")
async def autonomy_runtime_board_endpoint():
    """Gibt den gemeinsamen Phase-F Runtime-/Lane-Board-Snapshot zurueck."""
    try:
        from orchestration.phase_f_runtime_board import collect_phase_f_runtime_board

        board = await collect_phase_f_runtime_board()
        return {"status": "success", **board}
    except Exception as e:
        log.error(f"Phase-F Runtime Board Fehler: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


# ── VOICE ENDPOINTS ───────────────────────────────────────────────────────────
_voice_listen_task: asyncio.Task | None = None


@app.get("/settings", summary="Feature-Flags auslesen (Runtime)")
async def get_settings():
    """Gibt alle Feature-Flags zurück (Deep-Research + Autonomie)."""
    return {
        # -- Deep Research --
        "DEEP_RESEARCH_ARXIV_ENABLED":   os.getenv("DEEP_RESEARCH_ARXIV_ENABLED",   "true"),
        "DEEP_RESEARCH_GITHUB_ENABLED":  os.getenv("DEEP_RESEARCH_GITHUB_ENABLED",  "true"),
        "DEEP_RESEARCH_HF_ENABLED":      os.getenv("DEEP_RESEARCH_HF_ENABLED",      "true"),
        "DEEP_RESEARCH_EDISON_ENABLED":  os.getenv("DEEP_RESEARCH_EDISON_ENABLED",  "false"),
        "DEEP_RESEARCH_YOUTUBE_ENABLED": os.getenv("DEEP_RESEARCH_YOUTUBE_ENABLED", "true"),
        # -- Autonomie-Kern (M1–M7) --
        "AUTONOMY_GOALS_ENABLED":             os.getenv("AUTONOMY_GOALS_ENABLED",             "false"),
        "AUTONOMY_PLANNING_ENABLED":          os.getenv("AUTONOMY_PLANNING_ENABLED",          "false"),
        "AUTONOMY_SELF_HEALING_ENABLED":      os.getenv("AUTONOMY_SELF_HEALING_ENABLED",      "false"),
        "AUTONOMY_SCORECARD_ENABLED":         os.getenv("AUTONOMY_SCORECARD_ENABLED",         "false"),
        "AUTONOMY_LLM_DIAGNOSIS_ENABLED":     os.getenv("AUTONOMY_LLM_DIAGNOSIS_ENABLED",     "false"),
        "AUTONOMY_META_ANALYSIS_ENABLED":     os.getenv("AUTONOMY_META_ANALYSIS_ENABLED",     "false"),
        # -- Autonomie-Erweiterungen (M8–M16) --
        "AUTONOMY_REFLECTION_ENABLED":         os.getenv("AUTONOMY_REFLECTION_ENABLED",         "false"),
        "AUTONOMY_BLACKBOARD_ENABLED":         os.getenv("AUTONOMY_BLACKBOARD_ENABLED",         "true"),
        "AUTONOMY_PROACTIVE_TRIGGERS_ENABLED": os.getenv("AUTONOMY_PROACTIVE_TRIGGERS_ENABLED", "false"),
        "AUTONOMY_GOAL_QUEUE_ENABLED":         os.getenv("AUTONOMY_GOAL_QUEUE_ENABLED",         "true"),
        "AUTONOMY_SELF_IMPROVEMENT_ENABLED":   os.getenv("AUTONOMY_SELF_IMPROVEMENT_ENABLED",   "false"),
        "AUTONOMY_MEMORY_CURATION_ENABLED":    os.getenv("AUTONOMY_MEMORY_CURATION_ENABLED",    "false"),
        "AUTONOMY_MEMORY_CURATION_INTERVAL_HEARTBEATS": os.getenv("AUTONOMY_MEMORY_CURATION_INTERVAL_HEARTBEATS", "12"),
        "AUTONOMY_MEMORY_CURATION_STALE_DAYS": os.getenv("AUTONOMY_MEMORY_CURATION_STALE_DAYS", "30"),
        "AUTONOMY_MEMORY_CURATION_CANDIDATE_LIMIT": os.getenv("AUTONOMY_MEMORY_CURATION_CANDIDATE_LIMIT", "5"),
        "AUTONOMY_MEMORY_CURATION_MAX_ACTIONS": os.getenv("AUTONOMY_MEMORY_CURATION_MAX_ACTIONS", "1"),
        "AUTONOMY_MEMORY_CURATION_COOLDOWN_MINUTES": os.getenv("AUTONOMY_MEMORY_CURATION_COOLDOWN_MINUTES", "180"),
        "AUTONOMY_MEMORY_CURATION_ROLLBACK_COOLDOWN_MINUTES": os.getenv("AUTONOMY_MEMORY_CURATION_ROLLBACK_COOLDOWN_MINUTES", "720"),
        "AUTONOMY_MEMORY_CURATION_VERIFICATION_FAILURE_COOLDOWN_MINUTES": os.getenv("AUTONOMY_MEMORY_CURATION_VERIFICATION_FAILURE_COOLDOWN_MINUTES", "720"),
        "AUTONOMY_MEMORY_CURATION_REQUIRE_SEMANTIC_STORE": os.getenv("AUTONOMY_MEMORY_CURATION_REQUIRE_SEMANTIC_STORE", "true"),
        "AUTONOMY_MEMORY_CURATION_ALLOWED_CATEGORIES": os.getenv("AUTONOMY_MEMORY_CURATION_ALLOWED_CATEGORIES", ""),
        "AUTONOMY_MEMORY_CURATION_ALLOWED_ACTIONS": os.getenv("AUTONOMY_MEMORY_CURATION_ALLOWED_ACTIONS", ""),
        "AUTONOMY_M13_ENABLED":                os.getenv("AUTONOMY_M13_ENABLED",                "false"),
        "AUTONOMY_M14_ENABLED":                os.getenv("AUTONOMY_M14_ENABLED",                "false"),
        "AUTONOMY_AMBIENT_CONTEXT_ENABLED":    os.getenv("AUTONOMY_AMBIENT_CONTEXT_ENABLED",    "true"),
        "AUTONOMY_M16_ENABLED":                os.getenv("AUTONOMY_M16_ENABLED",                "false"),
    }


@app.post("/settings", summary="Research-Setting ändern (Runtime, ohne Neustart)")
async def update_setting(request: Request):
    """Setzt einen Feature-Flag zur Laufzeit und persistiert ihn in data/runtime_settings.json."""
    _ALLOWED = {
        # Deep Research
        "DEEP_RESEARCH_ARXIV_ENABLED",
        "DEEP_RESEARCH_GITHUB_ENABLED",
        "DEEP_RESEARCH_HF_ENABLED",
        "DEEP_RESEARCH_EDISON_ENABLED",
        "DEEP_RESEARCH_YOUTUBE_ENABLED",
        # Autonomie-Kern
        "AUTONOMY_GOALS_ENABLED",
        "AUTONOMY_PLANNING_ENABLED",
        "AUTONOMY_SELF_HEALING_ENABLED",
        "AUTONOMY_SCORECARD_ENABLED",
        "AUTONOMY_LLM_DIAGNOSIS_ENABLED",
        "AUTONOMY_META_ANALYSIS_ENABLED",
        # Autonomie-Erweiterungen
        "AUTONOMY_REFLECTION_ENABLED",
        "AUTONOMY_BLACKBOARD_ENABLED",
        "AUTONOMY_PROACTIVE_TRIGGERS_ENABLED",
        "AUTONOMY_GOAL_QUEUE_ENABLED",
        "AUTONOMY_SELF_IMPROVEMENT_ENABLED",
        "AUTONOMY_MEMORY_CURATION_ENABLED",
        "AUTONOMY_MEMORY_CURATION_INTERVAL_HEARTBEATS",
        "AUTONOMY_MEMORY_CURATION_STALE_DAYS",
        "AUTONOMY_MEMORY_CURATION_CANDIDATE_LIMIT",
        "AUTONOMY_MEMORY_CURATION_MAX_ACTIONS",
        "AUTONOMY_MEMORY_CURATION_COOLDOWN_MINUTES",
        "AUTONOMY_MEMORY_CURATION_ROLLBACK_COOLDOWN_MINUTES",
        "AUTONOMY_MEMORY_CURATION_VERIFICATION_FAILURE_COOLDOWN_MINUTES",
        "AUTONOMY_MEMORY_CURATION_REQUIRE_SEMANTIC_STORE",
        "AUTONOMY_MEMORY_CURATION_ALLOWED_CATEGORIES",
        "AUTONOMY_MEMORY_CURATION_ALLOWED_ACTIONS",
        "AUTONOMY_M13_ENABLED",
        "AUTONOMY_M14_ENABLED",
        "AUTONOMY_AMBIENT_CONTEXT_ENABLED",
        "AUTONOMY_M16_ENABLED",
    }
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Ungültiges JSON"})

    key = payload.get("key")
    value = str(payload.get("value", ""))

    if key not in _ALLOWED:
        return JSONResponse(status_code=400, content={"error": f"Key '{key}' nicht erlaubt"})

    os.environ[key] = value
    log.info(f"⚙️ Runtime-Setting geändert: {key}={value}")

    # Persistieren in data/runtime_settings.json
    try:
        settings: dict = {}
        if _RUNTIME_SETTINGS_PATH.exists():
            with open(_RUNTIME_SETTINGS_PATH) as _f:
                settings = _json.load(_f)
        settings[key] = value
        _RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_RUNTIME_SETTINGS_PATH, "w") as _f:
            _json.dump(settings, _f, indent=2)
    except Exception as e:
        log.warning(f"⚠️ Runtime-Settings konnten nicht persistiert werden: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

    return {"key": key, "value": value, "status": "ok"}


@app.get("/location/status", summary="Letzten bekannten Mobil-Standort abrufen")
async def location_status_endpoint():
    """Liefert den zuletzt normalisierten Standort-Snapshot, falls vorhanden."""
    try:
        payload = _build_location_status_payload()
        return {"status": "success", **payload}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/location/control", summary="Standort-Kontrolle und Privacy-Status abrufen")
async def location_control_status_endpoint():
    try:
        payload = _build_location_status_payload()
        return {
            "status": "success",
            "controls": payload.get("controls"),
            "device_count": payload.get("device_count", 0),
            "active_device_id": payload.get("active_device_id", ""),
            "active_user_scope": payload.get("active_user_scope", ""),
            "selection_reason": payload.get("selection_reason", ""),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.post("/location/control", summary="Standort-Kontrolle und Privacy-Flags setzen")
async def location_control_update_endpoint(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "error": "invalid_json"})

    allowed = {
        "sharing_enabled",
        "context_enabled",
        "background_sync_allowed",
        "preferred_device_id",
        "allowed_user_scopes",
        "max_device_entries",
    }
    unexpected = [key for key in dict(payload or {}).keys() if key not in allowed]
    if unexpected:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": f"unexpected_keys: {', '.join(unexpected)}"},
        )
    try:
        controls = _set_location_controls(payload or {})
        payload = _build_location_status_payload()
        return {"status": "success", "controls": controls, "location": payload.get("location"), "device_count": payload.get("device_count", 0)}
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "error": str(e)})


@app.post("/location/resolve", summary="Mobil-Standort normalisieren und speichern")
async def location_resolve_endpoint(request: Request):
    """Normalisiert Android-Standortdaten und persistiert den letzten Snapshot."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "error": "invalid_json"})

    try:
        snapshot = _normalize_location_snapshot(payload or {})
        controls = _get_location_controls()
        sync_mode = str((payload or {}).get("sync_mode") or "foreground").strip().lower() or "foreground"
        if not sync_mode_allowed(sync_mode, controls):
            status_payload = _build_location_status_payload()
            return {
                "status": "success",
                "stored": False,
                "location": status_payload.get("location"),
                "route_update": {"reroute_triggered": False, "reason": "background_sync_blocked"},
                "controls": controls,
            }
        _set_location_snapshot(snapshot)
        route_update = await _maybe_live_reroute_active_route(snapshot)
        return {
            "status": "success",
            "stored": True,
            "location": _get_location_snapshot(),
            "route_update": route_update,
            "controls": controls,
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "error": f"invalid_location_payload: {e}"})


@app.get("/location/nearby", summary="Orte in der Naehe des aktuellen Mobil-Standorts suchen")
async def location_nearby_endpoint(q: str, max_results: int = 5):
    """Sucht lokale Orte rund um den zuletzt synchronisierten Mobil-Standort via Google Maps / SerpApi."""
    safe_query = str(q or "").strip()
    if not safe_query:
        return JSONResponse(status_code=400, content={"status": "error", "error": "missing_query"})
    try:
        from tools.search_tool.tool import search_google_maps_places

        result = await search_google_maps_places(
            query=safe_query,
            max_results=max_results,
        )
        return {"status": "success", **result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/location/route", summary="Route vom aktuellen Mobil-Standort zu einem Ziel berechnen")
async def location_route_endpoint(
    destination: str,
    travel_mode: str = "driving",
    language_code: str = "de",
):
    safe_destination = str(destination or "").strip()
    if not safe_destination:
        return JSONResponse(status_code=400, content={"status": "error", "error": "missing_destination"})
    try:
        from tools.search_tool.tool import get_google_maps_route

        result = await get_google_maps_route(
            destination_query=safe_destination,
            travel_mode=travel_mode,
            language_code=language_code,
        )
        snapshot = prepare_route_snapshot(result)
        _set_route_snapshot(snapshot)
        return {"status": "success", **snapshot}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"status": "error", "error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/location/route/status", summary="Aktive Route abrufen")
async def location_route_status_endpoint():
    try:
        return {"status": "success", "route": _get_route_snapshot()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/location/route/map_config", summary="Interaktive Kartenkonfiguration fuer aktive Routen")
async def location_route_map_config_endpoint():
    try:
        return {"status": "success", "config": _build_route_map_client_config()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/location/route/map", summary="Aktive Route als statische Kartenansicht abrufen")
async def location_route_map_endpoint():
    snapshot = _get_route_snapshot()
    if not snapshot or not bool(snapshot.get("has_route")):
        return Response(
            content=_route_map_placeholder_svg("Keine aktive Route", "Lege zuerst eine Route an."),
            media_type="image/svg+xml",
        )

    static_map_url = _build_google_static_route_map_url(snapshot)
    if not static_map_url:
        return Response(
            content=_route_map_placeholder_svg("Karte nicht verfuegbar", "Google Maps Static API nicht konfiguriert."),
            media_type="image/svg+xml",
        )
    try:
        response = requests.get(static_map_url, timeout=15)
        response.raise_for_status()
        return Response(content=response.content, media_type=response.headers.get("content-type", "image/png"))
    except Exception as exc:
        log.warning(f"⚠️ Route-Map konnte nicht geladen werden: {exc}")
        return Response(
            content=_route_map_placeholder_svg(
                str(snapshot.get("destination_label") or "Route aktiv"),
                "Kartenvorschau momentan nicht erreichbar.",
            ),
            media_type="image/svg+xml",
        )


@app.get("/location/route/mobile_view", summary="Mobile Live-Routenansicht", response_class=HTMLResponse)
async def location_route_mobile_view_endpoint():
    return HTMLResponse(content=build_mobile_route_ui_html())


@app.get("/voice/status", summary="Voice-System Status")
async def voice_status_endpoint():
    """Gibt den aktuellen Status des Voice-Systems zurück."""
    try:
        return {
            "status": "success",
            "voice": {
                "initialized": bool(os.getenv("INWORLD_API_KEY") or os.getenv("OPENAI_API_KEY")),
                "listening": False,
                "speaking": False,
                "current_voice": os.getenv("INWORLD_VOICE", "Lennart"),
                "available_voices": ["Lennart", "Ashley", "Derek"],
            },
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.post("/voice/listen", summary="Spracheingabe starten (Whisper STT)")
async def voice_listen_endpoint():
    """Startet die Spracheingabe mit Faster-Whisper — gibt SOFORT zurück, Ergebnis per SSE."""
    global _voice_listen_task
    try:
        from tools.voice_tool.tool import voice_engine  # Import, noch kein Block

        async def _listen_and_broadcast():
            global _voice_listen_task
            _broadcast_sse({"type": "voice_listening_start"})
            try:
                # Initialisierung im Hintergrund — blockiert nicht den HTTP-Request
                if not voice_engine._initialized:
                    _broadcast_sse({"type": "voice_status", "message": "Lade Sprachmodell…"})
                    await asyncio.to_thread(voice_engine.initialize)
                text = await voice_engine.listen_async()
                _broadcast_sse({"type": "voice_transcript", "text": text, "success": bool(text)})
            except asyncio.CancelledError:
                _broadcast_sse({"type": "voice_listening_stop"})
            except Exception as ex:
                log.error(f"Voice listen Fehler (task): {ex}", exc_info=True)
                _broadcast_sse({"type": "voice_error", "error": str(ex)})
            finally:
                _voice_listen_task = None

        # Vorherigen Task abbrechen falls noch aktiv
        if _voice_listen_task and not _voice_listen_task.done():
            _voice_listen_task.cancel()
        _voice_listen_task = asyncio.create_task(_listen_and_broadcast())
        # Sofortige Antwort — kein Warten auf Whisper-Init oder Aufnahme
        return {"status": "success", "message": "Höre zu…"}
    except Exception as e:
        log.error(f"Voice listen Fehler: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.post("/voice/stop", summary="Spracheingabe stoppen")
async def voice_stop_endpoint():
    """Bricht eine laufende Spracheingabe ab."""
    global _voice_listen_task
    try:
        from tools.voice_tool.tool import voice_engine
        voice_engine.stop_listening()
        if _voice_listen_task and not _voice_listen_task.done():
            _voice_listen_task.cancel()
            _voice_listen_task = None
        _broadcast_sse({"type": "voice_listening_stop"})
        return {"status": "success", "message": "Aufnahme gestoppt"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.post("/voice/transcribe", summary="Browser-Audio hochladen und mit Whisper transkribieren")
async def voice_transcribe_endpoint(request: Request):
    """Transkribiert browserseitig aufgenommenes Audio ohne lokalen Mikrofonzugriff."""
    content_type = request.headers.get("content-type", "")
    if "multipart" not in content_type:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "multipart/form-data erforderlich"},
        )

    form = await request.form()
    file_field = form.get("file")
    if not file_field:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "Kein 'file'-Feld im Formular"},
        )

    try:
        from tools.voice_tool.tool import voice_engine

        filename = getattr(file_field, "filename", "") or ""
        suffix = Path(filename).suffix.lower().lstrip(".")
        if suffix == "oga":
            suffix = "ogg"
        if suffix not in {"ogg", "webm", "mp3", "wav", "m4a"}:
            suffix = None

        _broadcast_sse({"type": "voice_status", "message": "Transkribiere Browser-Audio…"})
        if not voice_engine._initialized:
            await asyncio.to_thread(voice_engine.initialize)

        audio_bytes = await file_field.read()
        text = await voice_engine.transcribe_audio_bytes_async(audio_bytes, suffix)
        _broadcast_sse({"type": "voice_transcript", "text": text, "success": bool(text), "source": "browser_upload"})
        return {"status": "success", "text": text}
    except Exception as e:
        log.error(f"Voice transcribe Fehler: {e}", exc_info=True)
        _broadcast_sse({"type": "voice_error", "error": str(e)})
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.post("/voice/speak", summary="Text-to-Speech (Inworld.AI)")
async def voice_speak_endpoint(payload: dict):
    """Spricht den übergebenen Text mit Inworld.AI TTS."""
    text = (payload or {}).get("text", "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"status": "error", "error": "Kein Text angegeben"})
    try:
        from tools.voice_tool.tool import voice_engine
        # speak_async enthält eigene Initialisierung — hier nicht blockierend init
        _broadcast_sse({"type": "voice_speaking_start", "text": text})
        if not voice_engine._initialized:
            await asyncio.to_thread(voice_engine.initialize)
        success = await voice_engine.speak_async(text)
        _broadcast_sse({"type": "voice_speaking_end", "success": success})
        return {"status": "success", "spoke": success}
    except Exception as e:
        log.error(f"Voice speak Fehler: {e}", exc_info=True)
        _broadcast_sse({"type": "voice_speaking_end", "success": False})
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.post("/voice/synthesize", summary="Text-to-Speech für Browser-Playback (Inworld.AI)")
async def voice_synthesize_endpoint(payload: dict):
    """Erzeugt MP3-Audio für browserseitige Wiedergabe."""
    text = (payload or {}).get("text", "").strip()
    voice = ((payload or {}).get("voice") or "").strip() or None
    if not text:
        return JSONResponse(status_code=400, content={"status": "error", "error": "Kein Text angegeben"})
    try:
        from tools.voice_tool.tool import voice_engine

        _broadcast_sse({"type": "voice_speaking_start", "text": text, "mode": "browser"})
        if not voice_engine._initialized:
            await asyncio.to_thread(voice_engine.initialize)
        mp3_bytes = await asyncio.to_thread(voice_engine.synthesize_mp3, text, voice)
        if mp3_bytes is None:
            _broadcast_sse({"type": "voice_speaking_end", "success": False, "mode": "browser"})
            return JSONResponse(status_code=500, content={"status": "error", "error": "TTS-Synthese fehlgeschlagen"})
        _broadcast_sse({"type": "voice_speaking_end", "success": True, "mode": "browser"})
        return Response(content=mp3_bytes, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
    except Exception as e:
        log.error(f"Voice synthesize Fehler: {e}", exc_info=True)
        _broadcast_sse({"type": "voice_speaking_end", "success": False, "mode": "browser"})
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/camera/status", summary="RealSense Kamera-Status")
async def camera_status_endpoint():
    """Status des RealSense Live-Streams."""
    try:
        from utils.realsense_stream import get_realsense_stream_manager
        manager = get_realsense_stream_manager()
        st = manager.status()
        return JSONResponse({
            "available": st.get("running", False),
            "running": st.get("running", False),
            "width": st.get("width"),
            "height": st.get("height"),
            "fps": st.get("fps"),
            "frame_count": st.get("frame_count"),
            "latest_frame_age_sec": st.get("latest_frame_age_sec"),
            "last_error": st.get("last_error"),
        })
    except Exception as e:
        return JSONResponse({"available": False, "running": False, "error": str(e)})


@app.post("/camera/start", summary="RealSense Stream starten")
async def camera_start_endpoint():
    """Startet den RealSense Live-Stream (idempotent)."""
    try:
        from utils.realsense_stream import get_realsense_stream_manager
        manager = get_realsense_stream_manager()
        if manager.status().get("running"):
            return JSONResponse({"status": "already_running"})
        width  = int(os.getenv("REALSENSE_STREAM_WIDTH",  "1280"))
        height = int(os.getenv("REALSENSE_STREAM_HEIGHT", "720"))
        fps    = float(os.getenv("REALSENSE_STREAM_FPS",  "15"))
        result = await asyncio.to_thread(manager.start, width, height, fps, None)
        app.state.realsense_stream_manager = manager
        return JSONResponse({"status": "started", "detail": result})
    except Exception as e:
        log.warning(f"camera/start Fehler: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.post("/camera/stop", summary="RealSense Stream stoppen")
async def camera_stop_endpoint():
    """Stoppt den RealSense Live-Stream."""
    try:
        from utils.realsense_stream import get_realsense_stream_manager
        manager = get_realsense_stream_manager()
        result = await asyncio.to_thread(manager.stop)
        return JSONResponse({"status": "stopped", "detail": result})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.get("/camera/stream", summary="RealSense MJPEG Live-Stream")
async def camera_stream_endpoint(request: Request):
    """MJPEG-Stream des RealSense RGB-Kamerabilds für Canvas-Einbettung.

    Startet den Stream automatisch falls noch nicht aktiv.
    Gibt 503 zurück wenn cv2 nicht verfügbar ist.
    """
    try:
        from utils.realsense_stream import get_realsense_stream_manager
        import cv2 as _cv2_check  # noqa – nur Verfügbarkeits-Check
        if _cv2_check is None:
            raise ImportError("cv2 ist None")
    except (ImportError, Exception):
        return JSONResponse(
            status_code=503,
            content={"error": "OpenCV (cv2) nicht verfügbar – RealSense-Stream nicht möglich."},
        )

    manager = get_realsense_stream_manager()

    # Auto-Start falls Stream nicht läuft
    if not manager.status().get("running"):
        try:
            width  = int(os.getenv("REALSENSE_STREAM_WIDTH",  "1280"))
            height = int(os.getenv("REALSENSE_STREAM_HEIGHT", "720"))
            fps    = float(os.getenv("REALSENSE_STREAM_FPS",  "15"))
            result = await asyncio.to_thread(manager.start, width, height, fps, None)
            if not result.get("running"):
                err = result.get("last_error", "Unbekannter Fehler")
                log.warning(f"📷 RealSense Auto-Start fehlgeschlagen: {err}")
                return JSONResponse(
                    status_code=503,
                    content={"error": f"Kein RealSense-Gerät gefunden: {err}"},
                )
            app.state.realsense_stream_manager = manager
            log.info("📷 RealSense-Stream via /camera/stream auto-gestartet")
        except Exception as e:
            log.warning(f"📷 RealSense Auto-Start fehlgeschlagen: {e}")
            return JSONResponse(
                status_code=503,
                content={"error": f"Kein RealSense-Gerät gefunden: {e}"},
            )

    target_fps   = float(os.getenv("REALSENSE_STREAM_FPS", "15"))
    frame_delay  = 1.0 / max(1.0, target_fps)
    boundary     = b"--frame"

    async def mjpeg_generator():
        while True:
            if await request.is_disconnected():
                break
            jpg = manager.get_frame_jpeg(quality=75)
            if jpg:
                yield (
                    boundary + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
                    + jpg + b"\r\n"
                )
            await asyncio.sleep(frame_delay)

    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/upload", summary="Datei-Upload für Canvas-Chat")
async def canvas_upload(request: Request):
    """Nimmt eine Datei per multipart/form-data entgegen und speichert sie."""
    content_type = request.headers.get("content-type", "")
    if "multipart" not in content_type:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "multipart/form-data erforderlich"},
        )

    form = await request.form()
    file_field = form.get("file")
    if not file_field:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "Kein 'file'-Feld im Formular"},
        )

    upload_dir = project_root / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    raw_name = getattr(file_field, "filename", None) or "upload.bin"
    safe_name = re.sub(r"[^\w.\-]", "_", raw_name)[:120]
    dest = upload_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"

    content = await file_field.read()
    dest.write_bytes(content)

    rel_path = str(dest.relative_to(project_root))
    abs_path = str(dest.resolve())
    _broadcast_sse(
        {"type": "upload", "filename": safe_name, "path": rel_path, "size": len(content)}
    )

    return {
        "status": "success",
        "filename": safe_name,
        "path": rel_path,
        "abs_path": abs_path,
        "size": len(content),
    }


@app.get("/files/recent", summary="Zuletzt verfügbare Uploads und Ergebnisse für die Konsole")
async def recent_console_files(limit: int = 24):
    files = _collect_console_files(limit=limit)
    return {
        "status": "success",
        "count": len(files),
        "files": files,
        "roots": [str(root.relative_to(project_root.resolve())) for root in _console_file_roots()],
    }


@app.get("/files/download", summary="Sicherer Download für Konsolen-Dateien")
async def download_console_file(path: str):
    resolved = _resolve_console_file_path(path)
    if resolved is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "error": "Datei nicht gefunden oder nicht freigegeben"},
        )
    mime = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return FileResponse(
        path=resolved,
        filename=resolved.name,
        media_type=mime,
    )


@app.get("/", include_in_schema=False)
async def root_console_redirect():
    """Leitet Browser-Aufrufe der Root-URL auf die Canvas-Konsole um."""
    return RedirectResponse(url="/canvas/ui", status_code=307)


@app.post("/", summary="JSON-RPC Endpoint")
async def handle_jsonrpc(request: Request):
    """Hauptendpoint für alle JSON-RPC Anfragen an die Tools."""
    req_str = (await request.body()).decode("utf-8")
    log.debug(f"⇢ IN: {req_str[:500]}{'...' if len(req_str) > 500 else ''}")

    method = ""
    try:
        import json as _json

        req_data = _json.loads(req_str)
        method = req_data.get("method", "")
        params = req_data.get("params", {})

        policy_decision = evaluate_policy_gate(
            gate="tool",
            subject=method,
            payload={"method": method, "params": params},
            source="server.mcp_server.handle_jsonrpc",
        )
        audit_policy_decision(policy_decision)
        if bool(policy_decision.get("blocked")):
            policy_reason = str(policy_decision.get("reason") or "Policy violation")
            log.warning(f"[server-policy] Tool blockiert: {method}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32600,
                    "message": policy_reason,
                },
                "id": req_data.get("id", 1),
            }
            return JSONResponse(content=error_response, status_code=403)

        try:
            if method in registry_v2.list_all_tools():
                registry_v2.validate_tool_call(method, **params)
        except ValidationError as e:
            log.warning(f"[server-validation] Validierungsfehler: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32602, "message": f"Invalid params: {e}"},
                "id": req_data.get("id", 1),
            }
            return JSONResponse(content=error_response, status_code=400)
        except ValueError:
            pass

    except Exception as e:
        log.debug(f"Pre-Dispatch Check nicht moeglich: {e}")

    # Tool-Activity via SSE broadcasten (nur echte Tool-Aufrufe, keine rpc.* Methoden)
    tool_id = ""
    if method and not method.startswith("rpc."):
        tool_id = uuid.uuid4().hex[:8]
        _broadcast_sse({"type": "tool_start", "tool": method, "id": tool_id})

    reply_str = await async_dispatch(req_str, serializer=numpy_aware_serializer)

    if tool_id:
        _broadcast_sse({"type": "tool_done", "tool": method, "id": tool_id})

    if reply_str:
        log.debug(f"⇠ OUT: {reply_str[:500]}{'...' if len(reply_str) > 500 else ''}")
        return Response(content=reply_str, media_type="application/json")
    return Response(status_code=204)


# --- Haupt-Einstiegspunkt für Uvicorn ---
if __name__ == "__main__":
    import uvicorn

    log.info("=" * 50)
    log.info("🚀 Starte Uvicorn-Server für die Timus MCP App...")
    log.info("   Die eigentliche Initialisierung erfolgt im FastAPI Lifespan-Manager.")
    log.info("=" * 50)

    uvicorn.run(
        "mcp_server:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", 5000)),
        log_level="info",
    )

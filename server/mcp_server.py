# server/mcp_server.py

import sys
import os
import asyncio
from pathlib import Path
import importlib
import logging
import inspect
import json as _json
import threading
import re
import uuid
import webbrowser
import ipaddress
import mimetypes
import copy
from collections import deque
from datetime import datetime
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
from gateway.status_snapshot import collect_status_snapshot

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
_SHUTDOWN_STEP_TIMEOUT_S = float(os.getenv("TIMUS_SHUTDOWN_STEP_TIMEOUT", "6"))
_CONSOLE_FILE_DIRS = ("results", "data/uploads")


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


def _build_google_maps_url(latitude: float, longitude: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"


def _copy_location_snapshot(snapshot: dict | None) -> dict | None:
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


def _persist_location_snapshot(snapshot: dict) -> None:
    _RUNTIME_LOCATION_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RUNTIME_LOCATION_SNAPSHOT_PATH, "w") as handle:
        _json.dump(snapshot, handle, indent=2, ensure_ascii=False)


def _set_location_snapshot(snapshot: dict) -> None:
    global _location_snapshot
    with _location_snapshot_lock:
        _location_snapshot = _copy_location_snapshot(snapshot)
    _persist_location_snapshot(snapshot)


def _get_location_snapshot() -> dict | None:
    with _location_snapshot_lock:
        if _location_snapshot is not None:
            return _copy_location_snapshot(_location_snapshot)
    _load_location_snapshot_from_disk()
    with _location_snapshot_lock:
        return _copy_location_snapshot(_location_snapshot)


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
    return {
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

        _agent_reg_mod._delegation_sse_hook = _delegation_sse_event
        log.info("✅ Agent-Registry: Alle Agenten-Specs registriert. Delegation-SSE-Hook aktiv.")
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

    if "inception_health" in registry_v2.list_all_tools():
        try:
            probe = await _rpc_call_local("inception_health", {})
            if isinstance(probe, dict) and not probe.get("error"):
                app.state.inception["health"] = {"ok": True, "detail": probe}
                log.info("🩺 Inception-Health: OK")
            else:
                app.state.inception["health"] = {"ok": False, "detail": probe}
                log.warning(f"🩺 Inception-Health: Problematisch → {probe}")
        except Exception as e:
            app.state.inception["health"] = {
                "ok": False,
                "detail": f"health_call_error: {e}",
            }
            log.warning(f"🩺 Inception-Health: Fehler beim Aufruf: {e}")
    else:
        log.info(
            "ℹ️ Keine 'inception_health'-Methode registriert – überspringe Health-Call."
        )

    # Finales Status-Logging
    log.info("=" * 50)
    log.info("🌐 TIMUS MCP SERVER IST BEREIT FÜR ANFRAGEN")
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

    # === BROWSER CONTEXT MANAGER (v2.0) ===
    try:
        from tools.browser_tool.persistent_context import PersistentContextManager
        manager = PersistentContextManager()
        await manager.initialize()
        shared_context.browser_context_manager = manager
        log.info("✅ Browser PersistentContextManager initialisiert")
    except Exception as e:
        log.warning(f"⚠️ PersistentContextManager konnte nicht gestartet werden: {e}")

    # === HEARTBEAT SCHEDULER STARTEN ===
    app.state.scheduler = None
    if os.getenv("HEARTBEAT_ENABLED", "true").lower() == "true":
        try:
            from orchestration.scheduler import init_scheduler, _set_scheduler_instance
            
            # Scheduler-Callback für Custom Actions
            async def on_scheduler_wake(event):
                log.info(f"💓 Scheduler Event: {event.event_type}")
                # Browser-Context Cleanup
                if shared_context.browser_context_manager:
                    expired = await shared_context.browser_context_manager.cleanup_expired()
                    if expired > 0:
                        log.info(f"🧹 {expired} abgelaufene Browser-Sessions entfernt")
            
            scheduler = init_scheduler(on_wake=on_scheduler_wake)
            _set_scheduler_instance(scheduler)
            await scheduler.start()
            app.state.scheduler = scheduler
            log.info(f"✅ Heartbeat-Scheduler gestartet (Interval: {scheduler.interval.total_seconds()/60:.0f}min)")
        except Exception as e:
            log.warning(f"⚠️ Scheduler konnte nicht gestartet werden: {e}")
    else:
        log.info("ℹ️ Heartbeat-Scheduler deaktiviert (HEARTBEAT_ENABLED=false)")

    # === OPTIONAL: REALSENSE LIVE-STREAM AUTO-START ===
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
            log.info(f"✅ RealSense-Stream gestartet: {status}")
        except Exception as e:
            log.warning(f"⚠️ RealSense-Stream Auto-Start fehlgeschlagen: {e}")
    else:
        log.info("ℹ️ RealSense-Stream Auto-Start deaktiviert (REALSENSE_STREAM_AUTO_START=false)")

    yield  # Server läuft

    log.info("🛑 TIMUS MCP SERVER SHUTDOWN beginnt...")

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
    tools = registry_v2.list_all_tools()
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_rpc_methods": len(tools),
        "registry": "v2",
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
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
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
    ts = datetime.utcnow().isoformat() + "Z"

    with _chat_lock:
        _chat_history.append({"role": "user", "text": query, "ts": ts})
        if len(_chat_history) > 200:
            _chat_history[:] = _chat_history[-200:]

    _broadcast_sse({"type": "chat_user", "text": query, "ts": ts})

    agent = "executor"
    try:
        from main_dispatcher import run_agent, get_agent_decision

        # Tool-Beschreibungen — identisch zu /get_tool_descriptions
        tools_desc = await _build_tools_description()

        agent = await get_agent_decision(query, session_id=session_id)
        _set_agent_status(agent, "thinking", query)

        query_for_agent = query
        if response_language in {"de", "deutsch", "german"} and agent not in {"visual", "visual_nemotron"}:
            query_for_agent = (
                "Antworte ausschließlich auf Deutsch. "
                "Nutze nur dann englische Fachbegriffe, wenn sie technisch nötig sind.\n\n"
                f"Nutzeranfrage:\n{query}"
            )

        result = await run_agent(
            agent_name=agent,
            query=query_for_agent,
            tools_description=tools_desc,
            session_id=session_id,
        )

        _set_agent_status(agent, "completed", query)
        reply = str(result) if result else "(keine Antwort)"
        reply_ts = datetime.utcnow().isoformat() + "Z"

        with _chat_lock:
            _chat_history.append(
                {"role": "assistant", "agent": agent, "text": reply, "ts": reply_ts}
            )

        _broadcast_sse({"type": "chat_reply", "agent": agent, "text": reply, "ts": reply_ts})
        return {"status": "success", "agent": agent, "reply": reply, "session_id": session_id}

    except Exception as e:
        log.error(f"Canvas-Chat Fehler: {e}", exc_info=True)
        _set_agent_status(agent, "error", query)
        _broadcast_sse({"type": "chat_error", "error": str(e)})
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
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


@app.get("/autonomy/improvement", summary="Self-Improvement Befunde (M12)")
async def autonomy_improvement_endpoint():
    """Gibt Self-Improvement Statistiken und Vorschläge zurück."""
    try:
        from orchestration.self_improvement_engine import get_improvement_engine
        engine = get_improvement_engine()
        tool_stats = engine.get_tool_stats(days=7)
        routing_stats = engine.get_routing_stats(days=7)
        suggestions = engine.get_suggestions(applied=False)
        return {
            "status": "success",
            "tool_stats_count": len(tool_stats),
            "routing_decisions": routing_stats.get("total_decisions", 0),
            "open_suggestions": len(suggestions),
            "critical_suggestions": sum(1 for s in suggestions if s.get("severity") == "high"),
            "top_suggestions": suggestions[:5],
        }
    except Exception as e:
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
        return {"status": "success", "location": _get_location_snapshot()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.post("/location/resolve", summary="Mobil-Standort normalisieren und speichern")
async def location_resolve_endpoint(request: Request):
    """Normalisiert Android-Standortdaten und persistiert den letzten Snapshot."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "error": "invalid_json"})

    try:
        snapshot = _normalize_location_snapshot(payload or {})
        _set_location_snapshot(snapshot)
        return {"status": "success", "location": snapshot}
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

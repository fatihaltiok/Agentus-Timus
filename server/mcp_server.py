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
from collections import deque
from datetime import datetime

# --- Drittanbieter-Bibliotheken ---
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from jsonrpcserver import async_dispatch
from dotenv import load_dotenv

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

# --- Lokale Module und Kontext importieren ---
import tools.shared_context as shared_context
from tools.tool_registry_v2 import registry_v2, ValidationError
from utils.policy_gate import check_tool_policy
from orchestration.canvas_store import canvas_store
from server.canvas_ui import build_canvas_ui_html

log = logging.getLogger("mcp_server")

# ── Canvas Chat & Agent-Status (In-Memory) ────────────────────────────────────
_KNOWN_AGENTS = [
    "executor", "research", "reasoning", "creative", "development", "meta", "visual",
    "data", "document",  # M1
    "communication",     # M2
    "system",            # M3
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


def _broadcast_sse(event: dict) -> None:
    """Sendet ein SSE-Event an alle verbundenen Browser-Clients."""
    payload = _json.dumps(event, ensure_ascii=False)
    with _sse_lock:
        dead = []
        for q in _sse_queues:
            try:
                q.put_nowait(payload)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                _sse_queues.remove(q)
            except ValueError:
                pass


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
    # NEU: Agent-zu-Agent Delegation
    "tools.delegation_tool.tool",
    # NEU: Vision Stability System v1.0 (GPT-5.2 Empfehlungen)
    "tools.screen_change_detector.tool",
    "tools.screen_contract_tool.tool",
    "tools.opencv_template_matcher_tool.tool",
    # NEU: DOM-First Browser Controller v2.0 (2026-02-10)
    "tools.browser_controller.tool",
    # NEU: JSON-Nemotron Tool für AI-gestützte JSON-Verarbeitung
    "tools.json_nemotron_tool.json_nemotron_tool",
    # NEU: Florence-2 Vision Tool — UI-Detection + OCR (ersetzt Qwen-VL als Primary)
    "tools.florence2_tool.tool",
    # M3: System-Monitor Tools
    "tools.system_tool.tool",
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
                settings=chromadb.config.Settings(anonymized_telemetry=False),
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
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = int(os.getenv("PORT", 5000))
    return f"http://{host}:{port}/canvas/ui"


def _bootstrap_canvas_startup() -> dict:
    """Initialisiert Canvas-MVP beim Server-Start (best effort)."""
    auto_create = _is_truthy_env(os.getenv("TIMUS_CANVAS_AUTO_CREATE"), default=True)
    auto_open = _is_truthy_env(os.getenv("TIMUS_CANVAS_AUTO_OPEN"), default=True)

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
            threading.Timer(1.2, _open_ui).start()
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

        register_all_agents()
        log.info("✅ Agent-Registry: Alle Agenten-Specs registriert.")
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

    yield  # Server läuft

    # === SHUTDOWN: Browser Contexts speichern ===
    if shared_context.browser_context_manager:
        try:
            await shared_context.browser_context_manager.shutdown()
            log.info("✅ Browser-Contexts gespeichert und geschlossen")
        except Exception as e:
            log.warning(f"⚠️ Fehler beim Browser-Context Shutdown: {e}")

    # === SHUTDOWN: Scheduler stoppen ===
    if app.state.scheduler:
        try:
            await app.state.scheduler.stop()
            log.info("✅ Heartbeat-Scheduler gestoppt")
        except Exception as e:
            log.warning(f"⚠️ Fehler beim Scheduler-Shutdown: {e}")

    # === SHUTDOWN: Canvas mirror logger stoppen ===
    if app.state.canvas_mirror_task:
        app.state.canvas_mirror_task.cancel()
        try:
            await app.state.canvas_mirror_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.warning(f"⚠️ Fehler beim Canvas mirror shutdown: {e}")


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


@app.get("/get_tool_descriptions", summary="Get Tool Descriptions for Agents")
async def get_tool_descriptions():
    try:
        descriptions = registry_v2.get_tool_manifest()

        # === SKILLS HINZUFÜGEN ===
        skills_section = "\n\n# VERFÜGBARE SKILLS (Wiederverwendbare Workflows)\n"
        skills_section += "Nutze 'run_skill' um einen Skill auszuführen.\n\n"

        try:
            skills_result = await async_dispatch(
                '{"jsonrpc":"2.0","method":"list_available_skills","id":99}',
                serializer=numpy_aware_serializer
            )
            import json

            skills_data = json.loads(skills_result)
            if "result" in skills_data and "skills" in skills_data["result"]:
                for skill in skills_data["result"]["skills"]:
                    skills_section += f"- **{skill['name']}**: {skill['description']}\n"
                skills_section += '\nBeispiel: Action: {"method": "run_skill", "params": {"name": "search_google", "params": {"query": "Suchbegriff"}}}\n'
        except Exception as e:
            log.warning(f"Skills konnten nicht geladen werden: {e}")

        descriptions += skills_section
        # === ENDE SKILLS ===

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


@app.get("/events/stream", summary="SSE-Stream für Echtzeit-Canvas-Updates")
async def events_stream(request: Request):
    """Server-Sent Events: Pushing agent-status, thinking-LED und Chat-Events."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
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

        # Tool-Beschreibungen direkt aus dem Registry (kein HTTP-Self-Call)
        try:
            tools_list = registry_v2.list_tools()
            tools_desc = "\n".join(
                f"- {t.name}: {t.description}" for t in tools_list
            )
        except Exception:
            tools_desc = ""

        agent = await get_agent_decision(query)
        _set_agent_status(agent, "thinking", query)

        result = await run_agent(
            agent_name=agent,
            query=query,
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
    _broadcast_sse(
        {"type": "upload", "filename": safe_name, "path": rel_path, "size": len(content)}
    )

    return {
        "status": "success",
        "filename": safe_name,
        "path": rel_path,
        "size": len(content),
    }


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

        allowed, policy_reason = check_tool_policy(method, params)
        if not allowed:
            log.warning(f"[server-policy] Tool blockiert: {method}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32600,
                    "message": policy_reason or "Policy violation",
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

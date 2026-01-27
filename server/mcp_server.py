# server/mcp_server.py

import sys
import os
from pathlib import Path
import importlib
import logging
import inspect
from datetime import datetime

# --- Drittanbieter-Bibliotheken ---
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from jsonrpcserver import async_dispatch
from dotenv import load_dotenv

# --- Projekt-Setup ---
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# --- Lokale Module und Kontext importieren ---
import tools.shared_context as shared_context
from tools.universal_tool_caller import tool_caller_instance

# --- Logging-Konfiguration ---
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
    stream=sys.stdout
)
log = logging.getLogger("mcp_server")

try:
    log_path = project_root / "timus_server.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s"))
    logging.getLogger().addHandler(file_handler)
    log.info(f"Logging auch in Datei: {log_path}")
except Exception as e:
    log.warning(f"Konnte Log-Datei nicht erstellen: {e}")

# --- Globale Konstanten ---
TOOL_MODULES = [
    "tools.browser_tool.tool", "tools.summarizer.tool", "tools.planner.tool",
    "tools.search_tool.tool", "tools.tasks.tasks", "tools.save_results.tool",
    "tools.deep_research.tool", "tools.decision_verifier.tool", "tools.document_parser.tool",
    "tools.fact_corroborator.tool", "tools.report_generator.tool", "tools.creative_tool.tool",
    "tools.memory_tool.tool", "tools.maintenance_tool.tool", "tools.developer_tool.tool",
    "tools.file_system_tool.tool", "tools.meta_tool.tool", "tools.reflection_tool.tool",
    "tools.skill_manager_tool.tool", "tools.curator_tool.tool", "tools.system_monitor_tool.tool",
    "tools.ocr_tool.tool", "tools.visual_grounding_tool.tool", "tools.mouse_tool.tool",
    "tools.visual_segmentation_tool.tool", "tools.debug_tool.tool", "tools.inception_tool.tool",
    "tools.icon_recognition_tool.tool", "tools.engines.object_detection_engine",
    "tools.annotator_tool.tool", "tools.moondream_tool.tool",
    "tools.application_launcher.tool", "tools.visual_browser_tool.tool",
    "tools.text_finder_tool.tool", "tools.smart_navigation_tool.tool",
    "tools.som_tool.tool", "tools.verification_tool.tool",
    "tools.voice_tool.tool","tools.memory_tool.tool",
    "tools.skill_recorder.tool", "tools.mouse_feedback_tool.tool",
    "tools.hybrid_detection_tool.tool", "tools.visual_agent_tool.tool",
    "tools.cookie_banner_tool.tool",
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
            log.info(f"✅ GPU-Beschleunigung AKTIV (PyTorch): {gpu_count}x {gpu_name} gefunden.")
            shared_context.device = "cuda"
        else:
            log.warning("⚠️ GPU-Beschleunigung NICHT verfügbar (PyTorch). Nutze CPU.")
            shared_context.device = "cpu"
    except ImportError:
        log.warning("⚠️ PyTorch ist nicht installiert. GPU-Prüfung wird übersprungen. Nutze CPU.")
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
        log.warning("⚠️ OCR-Engine-Modul nicht gefunden. OCR-Tool wird nicht funktionieren.")
    except Exception as e:
        log.error(f"❌ Fehler bei der Initialisierung der OCR-Engine: {e}", exc_info=True)

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
        from chromadb.utils import embedding_functions
        if shared_context.openai_client:
            db_path = project_root / "memory_db"
            chroma_db_client = chromadb.PersistentClient(path=str(db_path))
            openai_ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=shared_context.openai_client.api_key, model_name="text-embedding-3-small"
            )
            shared_context.memory_collection = chroma_db_client.get_or_create_collection(
                name="timus_long_term_memory", embedding_function=openai_ef
            )
            log.info(f"✅ Geteilte Memory-Collection ('{db_path}') initialisiert.")
        else:
            log.warning("⚠️ Memory-Collection nicht initialisiert, da OpenAI-Client fehlt.")
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
                log.error(f"❌ Fehler beim Laden der Fähigkeit aus '{skill_file.name}': {e_skill}", exc_info=True)
    
    return local_loaded_modules, local_failed_modules

async def _rpc_call_local(method: str, params: dict | None = None) -> dict:
    """Rufe eine JSON-RPC-Methode lokal (im selben Prozess) auf."""
    import json as _json
    # jsonrpcserver 5.x: Kein Request-Objekt mehr, sondern JSON-String direkt
    request_json = _json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1
    })
    reply = await async_dispatch(request_json)
    try:
        if not reply: return {"error": "no_reply"}
        data = _json.loads(reply)
        if "error" in data: return {"error": data["error"]}
        return data.get("result", {})
    except Exception as e:
        return {"error": f"dispatch_error: {e}"}

def _detect_inception_registered() -> bool:
    try:
        methods = tool_caller_instance.list_registered_tools()
        return any(m in methods for m in ("generate_and_integrate", "implement_feature", "inception_health"))
    except Exception:
        return False

# --- Lifespan-Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("="*50)
    log.info("🚀 TIMUS MCP SERVER STARTUP-PROZESS BEGINNT...")
    log.info("="*50)

    load_dotenv()
    log.info("✅ .env-Datei geladen.")

    # System initialisieren (Hardware, Clients, Tools)
    _initialize_hardware_and_engines()
    _initialize_shared_clients()
    loaded, failed = _load_all_tools_and_skills()
    
    # Inception-Status ermitteln & loggen
    inception_env_url = os.getenv("INCEPTION_URL") or os.getenv("INCEPTION_API_URL") or ""
    inception_registered = _detect_inception_registered()
    app.state.inception = {
        "registered": bool(inception_registered), "env_url": inception_env_url or None,
        "health": {"ok": None, "detail": "not_checked_yet"},
    }

    if inception_registered: log.info("✅ Inception-Tool registriert (Methoden vorhanden).")
    else: log.warning("❌ Inception-Tool NICHT registriert (keine passenden Methoden).")
    if inception_env_url: log.info(f"🔗 Inception-URL aus ENV: {inception_env_url}")
    else: log.warning("⚠️ Keine INCEPTION_URL/INCEPTION_API_URL in ENV gesetzt.")

    if "inception_health" in tool_caller_instance.list_registered_tools():
        try:
            probe = await _rpc_call_local("inception_health", {})
            if isinstance(probe, dict) and not probe.get("error"):
                app.state.inception["health"] = {"ok": True, "detail": probe}
                log.info("🩺 Inception-Health: OK")
            else:
                app.state.inception["health"] = {"ok": False, "detail": probe}
                log.warning(f"🩺 Inception-Health: Problematisch → {probe}")
        except Exception as e:
            app.state.inception["health"] = {"ok": False, "detail": f"health_call_error: {e}"}
            log.warning(f"🩺 Inception-Health: Fehler beim Aufruf: {e}")
    else:
        log.info("ℹ️ Keine 'inception_health'-Methode registriert – überspringe Health-Call.")

    # Finales Status-Logging
    log.info("="*50)
    log.info("🌐 TIMUS MCP SERVER IST BEREIT FÜR ANFRAGEN")
    log.info(f"📦 {len(loaded)}/{len(TOOL_MODULES)} Module geladen. Fehlgeschlagen: {len(failed)}")
    if failed:
        for mod, err in failed:
            log.warning(f"  -> {mod}: {err}")
    
    registered_tools_list = tool_caller_instance.list_registered_tools()
    log.info(f"🔧 {len(registered_tools_list)} RPC-Methoden registriert:")
    for tool_name in sorted(registered_tools_list.keys()):
        log.info(f"  - {tool_name}")
    log.info("="*50)
    
    yield # Server läuft

# --- App-Initialisierung mit Lifespan ---
app = FastAPI(title="Timus MCP Server", version="1.6.0 (Cleaned)", lifespan=lifespan)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- API Endpoints ---
@app.get("/health", summary="Health Check")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_rpc_methods": len(tool_caller_instance.list_registered_tools()),
        "inception": getattr(app.state, "inception", {
            "registered": False, "env_url": None, "health": {"ok": None, "detail": "n/a"}
        }),
    }

@app.get("/get_tool_descriptions", summary="Get Tool Descriptions for Agents")
async def get_tool_descriptions():
    try:
        descriptions = tool_caller_instance.get_formatted_tool_descriptions()
        
        # === SKILLS HINZUFÜGEN ===
        skills_section = "\n\n# VERFÜGBARE SKILLS (Wiederverwendbare Workflows)\n"
        skills_section += "Nutze 'run_skill' um einen Skill auszuführen.\n\n"
        
        try:
            # Skills vom Planner laden
            skills_result = await async_dispatch('{"jsonrpc":"2.0","method":"list_available_skills","id":99}')
            import json
            skills_data = json.loads(skills_result)
            if "result" in skills_data and "skills" in skills_data["result"]:
                for skill in skills_data["result"]["skills"]:
                    skills_section += f"- **{skill['name']}**: {skill['description']}\n"
                skills_section += "\nBeispiel: Action: {\"method\": \"run_skill\", \"params\": {\"name\": \"search_google\", \"params\": {\"query\": \"Suchbegriff\"}}}\n"
        except Exception as e:
            log.warning(f"Skills konnten nicht geladen werden: {e}")
        
        descriptions += skills_section
        # === ENDE SKILLS ===
        
        return {
            "status": "success", "descriptions": descriptions,
            "tool_count": len(tool_caller_instance.list_registered_tools()),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        log.error(f"❌ Fehler beim Abrufen der Tool-Beschreibungen: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={
            "status": "error", "descriptions": "Fehler beim Laden der Tool-Beschreibungen",
            "error": str(e), "tool_count": 0
        })

@app.post("/", summary="JSON-RPC Endpoint")
async def handle_jsonrpc(request: Request):
    """Hauptendpoint für alle JSON-RPC Anfragen an die Tools."""
    req_str = (await request.body()).decode("utf-8")
    log.debug(f"⇢ IN: {req_str[:500]}{'...' if len(req_str) > 500 else ''}")
    reply_str = await async_dispatch(req_str)
    if reply_str:
        log.debug(f"⇠ OUT: {reply_str[:500]}{'...' if len(reply_str) > 500 else ''}")
        return Response(content=reply_str, media_type="application/json")
    return Response(status_code=204)


# --- Haupt-Einstiegspunkt für Uvicorn ---
if __name__ == "__main__":
    import uvicorn
    log.info("="*50)
    log.info("🚀 Starte Uvicorn-Server für die Timus MCP App...")
    log.info("   Die eigentliche Initialisierung erfolgt im FastAPI Lifespan-Manager.")
    log.info("="*50)

    uvicorn.run(
        "mcp_server:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", 5000)),
        log_level="info"
    )

# tools/inception_tool/tool.py (Final, Corrected Version)

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Union, List, Optional
import requests
import asyncio
import sys
import importlib

from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool
from tools.file_system_tool.tool import read_file

log = logging.getLogger(__name__)

# --- Konfiguration ---
INCEPTION_URL = os.getenv("INCEPTION_URL", "https://api.inceptionlabs.ai/v1")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PYTHON_EXECUTABLE = sys.executable

# --- Interne Hilfsfunktionen ---

async def _build_inception_prompt(instruction: str, dest_folder: str, context_code: Optional[str]) -> str:
    """Baut einen hoch-kontextuellen Prompt für die Inception-API."""
    read_result = await read_file("tools/mouse_tool/tool.py")
    template_content = read_result.data.get("content", "# Vorlage konnte nicht geladen werden.")

    return f"""
    You are an expert Python software engineer for the 'Timus' project.
    Your task is to generate one or more complete, production-ready Python files to fulfill the user's request.
    The main file should be created at a path relative to the destination folder: `{dest_folder}`

    --- USER INSTRUCTION ---
    {instruction}
    ---
    
    --- ARCHITECTURAL TEMPLATE (mouse_tool.py) ---
    You MUST follow the structure, style, and principles of this template file exactly.
    ```python
    {template_content}
    ```
    ---

    --- ADDITIONAL CONTEXT CODE (Optional) ---
    {context_code or "No additional context provided."}
    ---
    
    CRITICAL REQUIREMENTS:
    1.  Return a JSON object with a "files" key: `{{"files": [{{"path": "relative/path/to/file.py", "code": "..."}}]}}`.
    2.  If the user requests tests, create a corresponding `test_*.py` file in the same JSON structure.
    3.  All code must be formatted with `black` and pass a `ruff` lint check.
    4.  All public-facing functions in a 'tool' must be `@method` decorated `async def` functions.
    
    Generate the required file(s) now.
    """

def _call_inception(prompt: str) -> dict:
    log.info(f"Rufe Inception API unter {INCEPTION_URL} auf...")
    payload = {"prompt": prompt}
    resp = requests.post(INCEPTION_URL, json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json()

def _write_temp_files(code_json: dict) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="inception_generated_"))
    log.info(f"Schreibe Code in temporäres Verzeichnis: {tmp_dir}")
    if "files" not in code_json or not isinstance(code_json["files"], list):
        raise ValueError("Inception-Antwort enthält keinen gültigen 'files'-Schlüssel.")
    for f in code_json["files"]:
        file_path = tmp_dir / f["path"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(f["code"], encoding="utf-8")
    return tmp_dir

def _validate_code(tmp_dir: Path) -> None:
    log.info("Validiere Code: Formatiere mit Black...")
    subprocess.run([PYTHON_EXECUTABLE, "-m", "black", str(tmp_dir)], check=True, capture_output=True)
    log.info("Validiere Code: Prüfe mit Ruff...")
    lint_result = subprocess.run([PYTHON_EXECUTABLE, "-m", "ruff", "check", str(tmp_dir)], capture_output=True, text=True)
    if lint_result.returncode != 0:
        raise RuntimeError(f"Ruff-Linting fehlgeschlagen:\n{lint_result.stdout}")
    tests_exist = any(p.name.startswith("test_") for p in tmp_dir.rglob("*.py"))
    if tests_exist:
        log.info("Validiere Code: Führe Pytest aus...")
        subprocess.run([PYTHON_EXECUTABLE, "-m", "pytest", "-q", str(tmp_dir)], check=True, capture_output=True)

def _integrate_code(tmp_dir: Path, dest_folder_root: str) -> List[str]:
    dest_root = PROJECT_ROOT / dest_folder_root
    integrated_files = []
    log.info(f"Integriere validierten Code nach: {dest_root}")
    for src in tmp_dir.rglob("*"):
        if src.is_file():
            rel_path = src.relative_to(tmp_dir)
            dest_path = dest_root / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest_path))
            integrated_files.append(str(dest_path.relative_to(PROJECT_ROOT)))
    return integrated_files

def _reload_modules(integrated_files: List[str]):
    log.info("Versuche, neue Module dynamisch nachzuladen...")
    for file_path_str in integrated_files:
        p = Path(file_path_str)
        if p.suffix == '.py':
            module_path = ".".join(p.with_suffix("").parts)
            try:
                if module_path in sys.modules:
                    log.info(f"Lade Modul neu: {module_path}")
                    importlib.reload(sys.modules[module_path])
                else:
                    log.info(f"Importiere neues Modul: {module_path}")
                    importlib.import_module(module_path)
                log.info(f"✅ Modul '{module_path}' erfolgreich (neu) geladen.")
            except Exception as e:
                log.error(f"Konnte Modul '{module_path}' nicht dynamisch laden: {e}.")

@method
async def inception_health() -> Union[Success, Error]:
    """
    Health-Check für das Inception-Tool.
    Prüft ob die API erreichbar ist.
    """
    try:
        # Prüfe ob INCEPTION_URL gesetzt ist
        if not INCEPTION_URL:
            return Error(
                code=-32091,
                message="INCEPTION_URL nicht konfiguriert"
            )

        # Teste einfachen Ping zur API (ohne echte Anfrage)
        log.info(f"Health-Check: Prüfe Inception API unter {INCEPTION_URL}")

        # Prüfe ob notwendige Pakete vorhanden sind
        try:
            import requests
            import subprocess
        except ImportError as e:
            return Error(
                code=-32092,
                message=f"Fehlende Abhängigkeiten: {e}"
            )

        return Success({
            "status": "healthy",
            "inception_url": INCEPTION_URL,
            "project_root": str(PROJECT_ROOT),
            "python_executable": PYTHON_EXECUTABLE,
            "dependencies": {
                "requests": "✅",
                "subprocess": "✅",
                "black": "verfügbar" if shutil.which("black") else "nicht installiert",
                "ruff": "verfügbar" if shutil.which("ruff") else "nicht installiert",
                "pytest": "verfügbar" if shutil.which("pytest") else "nicht installiert"
            }
        })

    except Exception as e:
        log.error(f"Inception Health-Check fehlgeschlagen: {e}", exc_info=True)
        return Error(code=-32093, message=f"Health-Check fehlgeschlagen: {e}")


@method
async def generate_and_integrate(
    instruction: str,
    dest_folder: str,
    context_file_path: Optional[str] = None
) -> Union[Success, Error]:
    """
    Generiert, validiert, integriert und lädt neuen Code vollautomatisch.
    """
    tmp_dir = None
    was_successful = False

    try:
        context_code = None
        if context_file_path:
            read_result = await read_file(context_file_path)
            if "error" in read_result.data:
                return Error(code=-32090, message=f"Konnte Kontext-Datei nicht lesen: {context_file_path}")
            context_code = read_result.data.get("content")

        prompt = await _build_inception_prompt(instruction, dest_folder, context_code)
        code_json = await asyncio.to_thread(_call_inception, prompt)
        tmp_dir = await asyncio.to_thread(_write_temp_files, code_json)
        await asyncio.to_thread(_validate_code, tmp_dir)
        integrated_files = await asyncio.to_thread(_integrate_code, tmp_dir, dest_folder)
        await asyncio.to_thread(_reload_modules, integrated_files)
        
        log.info(f"🎉 Erfolgreich {len(integrated_files)} Datei(en) integriert und neu geladen.")
        was_successful = True
        
        return Success({
            "status": "success",
            "message": "Code wurde erfolgreich generiert, validiert, integriert und neu geladen.",
            "integrated_files": integrated_files,
            "next_step": "Die neue Fähigkeit ist jetzt sofort verfügbar."
        })

    except Exception as e:
        log.error(f"Fehler im 'generate_and_integrate'-Prozess: {e}", exc_info=True)
        if tmp_dir:
            log.info(f"Temporäres Verzeichnis zur Fehleranalyse erhalten unter: {tmp_dir}")
        return Error(code=-32099, message=f"Code-Generierung fehlgeschlagen: {e}")
    finally:
        # Räume das temporäre Verzeichnis NUR bei Erfolg auf.
        if tmp_dir and was_successful:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            log.info(f"Temporäres Verzeichnis {tmp_dir} erfolgreich aufgeräumt.")

# --- Registrierung ---
# KORREKTUR: Die Registrierung gehört auf die oberste Ebene, außerhalb jeder Funktion.
register_tool("inception_health", inception_health)
register_tool("generate_and_integrate", generate_and_integrate)
log.info("✅ Inception Tool (inception_health, generate_and_integrate) registriert.")
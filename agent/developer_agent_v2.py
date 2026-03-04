# agent/developer_agent_v2.py
# -*- coding: utf-8 -*-
"""
Verbesserter Developer Agent (D.A.V.E. v2) mit:
- Multi-Tool Support (nicht nur implement_feature)
- Code-Validierung (Syntax, Style, Tests)
- Projekt-Kontext-Sammlung
- LLM behält Kontrolle (kein automatisches Schreiben)
- Fehler-Recovery Strategien
- Dynamischer System-Prompt
"""
import asyncio
import logging
import os
import json
import subprocess
import textwrap
import requests
import sys
import re
import ast
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

# -----------------------------------------------------------------------------
# Pfade & Module
# -----------------------------------------------------------------------------
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# -----------------------------------------------------------------------------
# Konfiguration & Clients
# -----------------------------------------------------------------------------
from dotenv import load_dotenv
from openai import OpenAI
from utils.openai_compat import prepare_openai_params

# Shared Utilities
from agent.shared.mcp_client import MCPClient as _SharedMCPClient
from agent.shared.action_parser import parse_action as _shared_parse_action

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:5000")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TEXT_MODEL = os.getenv("MAIN_LLM_MODEL", "gpt-5")
REQUIRE_INCEPTION = os.getenv("REQUIRE_INCEPTION", "1") == "1"
DEBUG = os.getenv("DEV_AGENT_DEBUG", "1") == "1"

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY fehlt in der Umgebung.")

client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger("developer_agent_v2")
if not logger.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)

# -----------------------------------------------------------------------------
# Erlaubte Tools (Multi-Tool Support)
# -----------------------------------------------------------------------------
ALLOWED_TOOLS = [
    "implement_feature",      # Code generieren (Inception)
    "generate_and_integrate", # Alternative Code-Generierung
    "read_file_content",      # Dateien lesen für Kontext
    "list_agent_files",       # Projektstruktur analysieren
    "write_file",             # Datei schreiben (nach Validierung!)
    "run_tests",              # Tests ausführen
    "search_web",             # Dokumentation suchen
    "remember",               # Kontext merken
    "recall",                 # Kontext abrufen
]

# -----------------------------------------------------------------------------
# Kontext-Sammlung
# -----------------------------------------------------------------------------
def gather_project_context(dest_folder: str) -> str:
    """
    Sammelt umfassenden Projekt-Kontext für bessere Code-Generierung.

    Returns:
        Formatierter String mit Projektstruktur, Dependencies, etc.
    """
    context_parts = []

    try:
        # 1. Projektstruktur
        # list_agent_files nimmt nur 'subfolder' Parameter (tools/agent/server/skills)
        # Versuche mehrere Ordner für besseren Kontext
        all_files = []
        for folder in ["agent", "tools", "skills"]:
            structure = call_tool("list_agent_files", {"subfolder": folder})
            if isinstance(structure, dict) and not structure.get("error"):
                files = structure.get("files", [])
                all_files.extend(files)

        if all_files:
            context_parts.append(f"## Projektstruktur ({len(all_files)} Python-Dateien):")
            context_parts.append("\n".join(f"  - {f}" for f in all_files[:10]))
            if len(all_files) > 10:
                context_parts.append(f"  ... und {len(all_files) - 10} weitere")

        # 2. Dependencies (requirements.txt)
        req_path = f"{dest_folder}/requirements.txt"
        deps = call_tool("read_file_content", {"path": req_path})
        if isinstance(deps, dict) and not deps.get("error"):
            content = deps.get("content", "")
            if content:
                lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#")]
                context_parts.append(f"\n## Dependencies ({len(lines)} Packages):")
                context_parts.append("\n".join(f"  - {l}" for l in lines[:8]))
                if len(lines) > 8:
                    context_parts.append(f"  ... und {len(lines) - 8} weitere")

        # 3. README oder Setup-Anweisungen
        readme_files = ["README.md", "README.txt", "setup_instructions.md"]
        for readme_file in readme_files:
            readme_path = f"{dest_folder}/{readme_file}"
            readme = call_tool("read_file_content", {"path": readme_path})
            if isinstance(readme, dict) and not readme.get("error"):
                content = readme.get("content", "")[:500]  # Erste 500 Zeichen
                if content:
                    context_parts.append(f"\n## Projekt-Beschreibung ({readme_file}):")
                    context_parts.append(content)
                break

        if context_parts:
            return "\n".join(context_parts)
        else:
            return f"Neues Projekt im Ordner: {dest_folder}"

    except Exception as e:
        logger.warning(f"Fehler bei Kontext-Sammlung: {e}")
        return f"Projekt-Ordner: {dest_folder}"


def detect_coding_style(dest_folder: str) -> str:
    """
    Erkennt den Coding-Style aus Konfigurationsdateien.

    Returns:
        Style-Beschreibung (z.B. "PEP8 + Black")
    """
    style_indicators = []

    # Prüfe auf Black
    pyproject = call_tool("read_file_content", {"path": f"{dest_folder}/pyproject.toml"})
    if isinstance(pyproject, dict) and not pyproject.get("error"):
        content = pyproject.get("content", "")
        if "[tool.black]" in content:
            style_indicators.append("Black")

    # Prüfe auf Ruff
    if isinstance(pyproject, dict) and not pyproject.get("error"):
        content = pyproject.get("content", "")
        if "[tool.ruff]" in content:
            style_indicators.append("Ruff")

    # Standard ist PEP8
    if not style_indicators:
        return "PEP8"

    return "PEP8 + " + " + ".join(style_indicators)


def find_related_files(dest_folder: str, target_file: str, max_files: int = 3) -> List[str]:
    """
    Findet verwandte Dateien im Projekt für besseren Kontext.

    Strategie:
    1. Dateien im gleichen Verzeichnis (gleicher Modul-Kontext)
    2. __init__.py im gleichen Package
    3. Dateien mit ähnlichem Namen
    4. Häufig importierte Module (utils, base, config)

    Args:
        dest_folder: Projekt-Ordner
        target_file: Ziel-Datei für die Code generiert wird
        max_files: Maximale Anzahl Context-Dateien

    Returns:
        Liste von Dateipfaden (relativ zum dest_folder)
    """
    related = []
    target_path = Path(target_file)

    try:
        # 1. __init__.py im gleichen Verzeichnis (wichtig für Package-Struktur)
        if target_path.parent != Path("."):
            init_file = str(target_path.parent / "__init__.py")
            init_full = Path(dest_folder) / init_file
            if init_full.exists() and init_file != target_file:
                related.append(init_file)

        # 2. Dateien im gleichen Verzeichnis
        if target_path.parent != Path("."):
            sibling_dir = Path(dest_folder) / target_path.parent
            if sibling_dir.exists() and sibling_dir.is_dir():
                for sibling in sibling_dir.glob("*.py"):
                    rel_path = str(sibling.relative_to(dest_folder))
                    if rel_path != target_file and rel_path not in related:
                        related.append(rel_path)
                        if len(related) >= max_files:
                            break

        # 3. Häufig genutzte Module (utils, base, config, constants)
        if len(related) < max_files:
            common_names = ["utils.py", "base.py", "config.py", "constants.py", "settings.py"]
            for common in common_names:
                common_path = Path(dest_folder) / common
                if common_path.exists() and common != target_file and common not in related:
                    related.append(common)
                    if len(related) >= max_files:
                        break

        # 4. Dateien mit ähnlichem Präfix (z.B. user_model.py für user_controller.py)
        if len(related) < max_files:
            target_stem = target_path.stem
            prefix = target_stem.split("_")[0] if "_" in target_stem else target_stem[:4]

            for py_file in Path(dest_folder).rglob("*.py"):
                if len(related) >= max_files:
                    break
                rel_path = str(py_file.relative_to(dest_folder))
                if rel_path != target_file and rel_path not in related:
                    if py_file.stem.startswith(prefix):
                        related.append(rel_path)

        logger.info(f"📚 Context-Dateien gefunden: {related}")
        return related[:max_files]

    except Exception as e:
        logger.warning(f"Fehler bei find_related_files: {e}")
        return []


# -----------------------------------------------------------------------------
# Code-Validierung
# -----------------------------------------------------------------------------
def validate_python_syntax(code: str) -> Tuple[bool, str]:
    """
    Validiert Python-Syntax mit AST.

    Returns:
        (valid, error_message)
    """
    try:
        ast.parse(code)
        return True, "✅ Syntax valid"
    except SyntaxError as e:
        return False, f"Syntax-Fehler in Zeile {e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"Parsing-Fehler: {str(e)}"


def validate_code(code: str, file_path: str, dest_folder: str) -> Dict[str, Any]:
    """
    Umfassende Code-Validierung.

    Returns:
        Dict mit validation_status, errors, warnings
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": {}
    }

    # 1. Syntax-Check
    syntax_valid, syntax_msg = validate_python_syntax(code)
    result["checks"]["syntax"] = syntax_msg
    if not syntax_valid:
        result["valid"] = False
        result["errors"].append(syntax_msg)

    # 2. Basic Style-Checks (einfache Prüfungen)
    lines = code.split("\n")

    # Prüfe auf zu lange Zeilen (PEP8: 79 Zeichen)
    long_lines = [i+1 for i, line in enumerate(lines) if len(line) > 88]  # Black Standard: 88
    if long_lines:
        result["warnings"].append(f"Zeilen zu lang (>88): {long_lines[:5]}")

    # Prüfe auf fehlende Docstrings bei Funktionen
    if "def " in code:
        funcs_without_docs = []
        in_func = False
        func_name = ""
        for i, line in enumerate(lines):
            if line.strip().startswith("def ") and not line.strip().startswith("def _"):
                in_func = True
                func_name = line.split("def ")[1].split("(")[0]
            elif in_func and i+1 < len(lines):
                next_line = lines[i+1].strip()
                if not next_line.startswith('"""') and not next_line.startswith("'''"):
                    funcs_without_docs.append(func_name)
                in_func = False

        if funcs_without_docs:
            result["warnings"].append(f"Funktionen ohne Docstring: {funcs_without_docs[:3]}")

    # 3. Prüfe auf gefährliche Patterns
    dangerous_patterns = [
        ("eval(", "Nutzung von eval() ist unsicher"),
        ("exec(", "Nutzung von exec() ist unsicher"),
        ("__import__", "Dynamischer Import kann problematisch sein"),
    ]

    for pattern, warning in dangerous_patterns:
        if pattern in code:
            result["warnings"].append(warning)

    result["checks"]["style"] = f"✅ {len(result['warnings'])} Warnungen"

    return result


# -----------------------------------------------------------------------------
# Dynamischer System-Prompt
# -----------------------------------------------------------------------------
def build_system_prompt(dest_folder: str) -> str:
    """
    Erstellt projekt-spezifischen System-Prompt.
    """
    project_context = gather_project_context(dest_folder)
    coding_style = detect_coding_style(dest_folder)

    tools_list = "\n".join([f"  - {tool}" for tool in ALLOWED_TOOLS])

    return f"""Du bist D.A.V.E. v2, ein verbesserter Developer-Agent.

PROJEKT-KONTEXT:
{project_context}

CODING STYLE: {coding_style}
- Befolge {coding_style} Konventionen strikt
- Nutze Type Hints (Python 3.10+)
- Docstrings für alle öffentlichen Funktionen
- Comprehensive Error Handling

VERFÜGBARE TOOLS:
{tools_list}

TOOL-PARAMETER WICHTIG:
- list_agent_files: Nimmt nur "subfolder" Parameter (Werte: "tools", "agent", "server", "skills")
  Beispiel: {{"method": "list_agent_files", "params": {{"subfolder": "agent"}}}}
- read_file_content: Nimmt nur "path" Parameter (relativer Pfad zum Projekt-Root)
  Beispiel: {{"method": "read_file_content", "params": {{"path": "agent/developer_agent.py"}}}}

WICHTIGE REGELN:
1. Sammle IMMER zuerst Kontext (read_file_content, list_agent_files)
2. Validiere Code BEVOR du schreibst (du bekommst Validation-Feedback)
3. Bei Fehlern: Analysiere und versuche alternative Ansätze
4. Nutze remember/recall für wichtige Informationen
5. Bei Unsicherheit: Mehr Kontext sammeln oder Dokumentation suchen

WORKFLOW (schrittweise!):
1. **Kontext sammeln**: read_file_content für ähnliche Dateien, list_agent_files für Struktur
2. **Code generieren**: implement_feature mit vollständiger Spezifikation
   - WICHTIG: Nutze "context_files" Parameter für verwandte Dateien!
   - Format: {{"instruction": "...", "file_paths": ["target.py"], "context_files": ["related.py", "utils.py"]}}
3. **Validierung erhalten**: System validiert automatisch (Syntax, Style)
4. **Bei Validation OK**: Nutze write_file zum Speichern
5. **Bei Validation Fehler**: Überarbeite basierend auf Feedback
6. **Finalisieren**: Nach erfolgreichem Schreiben

IMPLEMENT_FEATURE TOOL DETAILS:
- Parameter:
  * instruction: Detaillierte Code-Anweisung
  * file_paths: Liste der Ziel-Dateien (wird generiert)
  * context_files: [OPTIONAL] Liste verwandter Dateien für besseren Kontext
- Beispiel:
  {{"method": "implement_feature", "params": {{
    "instruction": "Create User model with email validation",
    "file_paths": ["models/user.py"],
    "context_files": ["models/__init__.py", "utils/validators.py"]
  }}}}

ANTWORTFORMAT (exakt eins pro Runde):
Thought: <kurzer Plan, was du als nächstes tust>
Action: {{"method": "tool_name", "params": {{...}}}}

ODER (nur nach erfolgreicher Fertigstellung):
Thought: Aufgabe abgeschlossen
Final Answer: <Zusammenfassung was gemacht wurde>

BEISPIEL-WORKFLOW:
```
# Schritt 1: Kontext - Projektstruktur
Thought: Ich prüfe zunächst die Projektstruktur
Action: {{"method": "list_agent_files", "params": {{"subfolder": "agent"}}}}

# Schritt 2: Verwandte Dateien lesen (für context_files)
Thought: Ich lese verwandte Dateien um besseren Kontext zu haben
Action: {{"method": "read_file_content", "params": {{"path": "models/__init__.py"}}}}

# Schritt 3: Code generieren MIT context_files
Thought: Ich generiere den Code mit Kontext aus verwandten Dateien
Action: {{"method": "implement_feature", "params": {{
  "instruction": "Create User model with email validation",
  "file_paths": ["models/user.py"],
  "context_files": ["models/__init__.py", "utils/validators.py"]
}}}}

# Schritt 4: Validierung OK → Schreiben
Thought: Validation erfolgreich, ich schreibe die Datei
Action: {{"method": "write_file", "params": {{"path": "...", "content": "..."}}}}

# Schritt 5: Fertig
Thought: Aufgabe abgeschlossen
Final Answer: Datei 'models/user.py' wurde erfolgreich erstellt mit Kontext aus __init__.py und validators.py.
```

WICHTIG:
- Nur EINE Action pro Runde
- Warte auf Observation bevor du fortfährst
- Nutze validation_result aus Observation für Entscheidungen
"""


# -----------------------------------------------------------------------------
# Tool-Call Helper
# -----------------------------------------------------------------------------
_mcp = _SharedMCPClient()

def call_tool(method: str, params: Optional[dict] = None, timeout: int = 300) -> dict:
    """RPC-Call zum MCP-Server (delegiert an agent.shared.mcp_client)."""
    return _mcp.call_sync(method, params, timeout=timeout)


def inception_ready() -> Tuple[bool, str]:
    """Prüft ob Inception/implement_feature verfügbar ist."""
    probe = call_tool("inception_health", {})
    if isinstance(probe, dict) and not probe.get("error"):
        return True, "ok"

    ping = call_tool("implement_feature", {
        "file_paths": ["__inception_ping__.txt"],
        "instruction": "NOOP/PING – do not write any file.",
        "dry_run": True
    })
    if isinstance(ping, dict) and not ping.get("error"):
        return True, "ok"

    err = ping.get("error") if isinstance(ping, dict) else probe
    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
    return False, msg or "Inception nicht bereit"


# -----------------------------------------------------------------------------
# LLM Wrapper
# -----------------------------------------------------------------------------
def chat(messages: List[Dict[str, Any]], temperature: float = 1.0, token_budget: int = 2000) -> str:
    """LLM Chat mit korrekten Token-Parametern."""
    kwargs: Dict[str, Any] = {
        "model": TEXT_MODEL,
        "messages": messages,
        "temperature": temperature,
    }

    if ("gpt-5" in TEXT_MODEL) or ("gpt-4o" in TEXT_MODEL):
        kwargs["max_completion_tokens"] = token_budget
    else:
        kwargs["max_tokens"] = token_budget

    try:
        resp = client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Error: LLM API Fehler - {e}"


# -----------------------------------------------------------------------------
# Parsing-Helfer
# -----------------------------------------------------------------------------
def extract_action_json(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """Extrahiert Action-JSON aus LLM-Antwort (delegiert an agent.shared.action_parser)."""
    return _shared_parse_action(text)


# -----------------------------------------------------------------------------
# Fehler-Analyse
# -----------------------------------------------------------------------------
def analyze_failure_pattern(messages: List[Dict]) -> str:
    """
    Analysiert Fehler-Pattern aus Message-Historie.

    Returns:
        Fehler-Typ (syntax/context/logic)
    """
    recent_errors = []
    for msg in messages[-5:]:  # Letzte 5 Messages
        if msg.get("role") == "user" and "Observation:" in msg.get("content", ""):
            content = msg["content"]
            if "error" in content.lower():
                recent_errors.append(content.lower())

    error_text = " ".join(recent_errors)

    if "syntax" in error_text or "parsing" in error_text:
        return "syntax"
    elif "kontext" in error_text or "nicht gefunden" in error_text or "context" in error_text:
        return "context"
    elif "validation" in error_text or "test" in error_text:
        return "validation"
    else:
        return "logic"


def get_recovery_strategy(error_type: str) -> str:
    """Gibt Recovery-Strategie basierend auf Fehler-Typ."""
    strategies = {
        "syntax": """
Syntax-Fehler erkannt. Neue Strategie:
1. Generiere kleinere Code-Abschnitte (< 50 Zeilen)
2. Validiere jeden Abschnitt einzeln
3. Nutze einfachere Konstrukte
4. Prüfe Einrückungen genau
""",
        "context": """
Kontext-Fehler erkannt. Neue Strategie:
1. Sammle mehr Kontext (read_file_content für ähnliche Dateien)
2. Prüfe Projektstruktur (list_agent_files)
3. Suche nach Dokumentation (search_web wenn nötig)
4. Nutze recall für frühere Informationen
""",
        "validation": """
Validierungs-Fehler erkannt. Neue Strategie:
1. Prüfe die Fehler-Details genau
2. Überarbeite nur die problematischen Teile
3. Behalte funktionierende Teile bei
4. Teste inkrementell
""",
        "logic": """
Logik-Fehler erkannt. Neue Strategie:
1. Zerlege die Aufgabe in kleinere Teilschritte
2. Löse jeden Schritt einzeln
3. Validiere jeden Schritt vor dem nächsten
4. Nutze remember um Fortschritt zu speichern
"""
    }
    return strategies.get(error_type, "Versuche einen anderen Ansatz.")


# -----------------------------------------------------------------------------
# Haupt-Loop (Verbessert)
# -----------------------------------------------------------------------------
def run_developer_task(user_query: str, dest_folder: str = ".", max_steps: int = 12) -> str:
    """
    Führt Developer-Aufgabe mit verbessertem Workflow aus.

    Args:
        user_query: Nutzer-Anfrage
        dest_folder: Ziel-Ordner für Code
        max_steps: Maximale Anzahl Schritte

    Returns:
        Finale Antwort
    """
    logger.info(f"👨‍💻 D.A.V.E. v2 startet für: {user_query!r}")
    logger.info(f"   Ziel-Ordner: {dest_folder}")

    # Preflight: Inception-Check (falls erforderlich)
    if REQUIRE_INCEPTION:
        ok, why = inception_ready()
        if not ok:
            logger.error(f"Inception nicht bereit: {why}")
            return (f"Inception/implement_feature ist nicht bereit: {why}. "
                   "Bitte prüfe ENV (INCEPTION_*, MCP_URL) und den Serverstart.")

    # System-Prompt mit Projekt-Kontext
    system_prompt = build_system_prompt(dest_folder)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]

    failures = 0
    strategy_changed = False
    generated_code_cache = {}  # Cache für generierten Code

    for step in range(1, max_steps + 1):
        logger.info(f"⚙️ Schritt {step}/{max_steps} (Fehler: {failures})")

        # LLM beauftragen
        reply = chat(messages, temperature=1.0, token_budget=2500)

        if not isinstance(reply, str):
            failures += 1
            messages.append({"role": "user", "content": f"Observation: {json.dumps({'error': 'Ungültige LLM-Antwort'})}"})
            continue

        messages.append({"role": "assistant", "content": reply})
        logger.debug(f"🧠 LLM:\n{reply}")

        # Sofortiger Abschluss?
        if "Final Answer:" in reply:
            final = reply.split("Final Answer:", 1)[1].strip()
            logger.info("✅ Aufgabe abgeschlossen.")

            # Learning Entry
            call_tool("log_learning_entry", {
                "goal": user_query,
                "outcome": "success",
                "details": {
                    "final_step_count": step,
                    "failures": failures,
                    "strategy_changed": strategy_changed,
                    "dest_folder": dest_folder
                },
                "learning": "Entwicklung mit verbessertem Agent erfolgreich abgeschlossen."
            })
            return final

        # Action extrahieren
        action, perr = extract_action_json(reply)
        if perr or not action:
            failures += 1
            logger.warning(f"Keine gültige Action erkannt: {perr}")
            messages.append({"role": "user", "content": f"Observation: {json.dumps({'error': perr or 'no_action'})}"})

            # Fehler-Recovery
            if failures >= 2 and not strategy_changed:
                error_type = analyze_failure_pattern(messages)
                strategy = get_recovery_strategy(error_type)
                logger.info(f"💡 Wechsle Strategie (Fehler-Typ: {error_type})")
                messages.append({"role": "user", "content": strategy})
                strategy_changed = True
                failures = 0

            continue

        method = action.get("method")
        params = action.get("params", {}) if isinstance(action.get("params"), dict) else {}

        # Tool-Whitelist prüfen
        if method not in ALLOWED_TOOLS:
            failures += 1
            logger.warning(f"Tool '{method}' nicht erlaubt.")
            error_obs = {
                'error': f'Tool nicht erlaubt: {method}',
                'allowed_tools': ALLOWED_TOOLS,
                'hint': 'Nutze eines der erlaubten Tools'
            }
            messages.append({"role": "user", "content": f"Observation: {json.dumps(error_obs)}"})
            continue

        # Intelligente Context-Files für implement_feature
        if method == "implement_feature" and "context_files" not in params:
            file_paths = params.get("file_paths", [])
            if isinstance(file_paths, str):
                file_paths = [file_paths]

            if file_paths:
                target_file = file_paths[0]
                context_files = find_related_files(dest_folder, target_file, max_files=3)
                if context_files:
                    params["context_files"] = context_files
                    logger.info(f"📚 Auto-Context hinzugefügt: {context_files}")

        # Tool ausführen
        logger.info(f"🔧 Führe aus: {method}({list(params.keys())})")
        obs = call_tool(method, params, timeout=420)

        # Fehler-Handling
        if isinstance(obs, dict) and obs.get("error"):
            failures += 1
            err_msg = str(obs.get("error"))
            logger.error(f"Tool-Fehler: {err_msg}")

            messages.append({"role": "user", "content": f"Observation: {json.dumps(obs)}"})

            # Fehler-Recovery
            if failures >= 2 and not strategy_changed:
                error_type = analyze_failure_pattern(messages)
                strategy = get_recovery_strategy(error_type)
                logger.info(f"💡 Wechsle Strategie (Fehler-Typ: {error_type})")
                messages.append({"role": "user", "content": strategy})
                strategy_changed = True
                failures = 0

            continue

        # Spezial-Handling für Code-Generierung
        if method in ["implement_feature", "generate_and_integrate"] and not obs.get("error"):
            generated = obs.get("generated_code")
            file_path = obs.get("file_path") or (
                params.get("file_paths", [None])[0] if isinstance(params.get("file_paths"), list)
                else params.get("dest_folder", "output.py")
            )

            if generated and file_path:
                logger.info(f"📝 Code generiert für: {file_path}")

                # CODE-VALIDIERUNG (KRITISCH!)
                validation = validate_code(generated, file_path, dest_folder)

                # Cache Code für späteres Schreiben
                generated_code_cache[file_path] = generated

                # Erweiterte Observation mit Validation
                obs["validation"] = validation
                obs["file_path"] = file_path
                obs["ready_to_write"] = validation["valid"]

                if validation["valid"]:
                    obs["next_step"] = f"Code validiert! Nutze write_file mit path='{file_path}' um zu speichern."
                    logger.info(f"✅ Validation erfolgreich für {file_path}")
                else:
                    obs["next_step"] = f"Validation fehlgeschlagen. Überarbeite den Code basierend auf errors."
                    logger.warning(f"❌ Validation fehlgeschlagen: {validation['errors']}")

                # Warnung auch ausgeben
                if validation["warnings"]:
                    obs["validation_warnings"] = validation["warnings"]

        # Spezial-Handling für write_file (Code aus Cache holen)
        if method == "write_file":
            path = params.get("path")
            content = params.get("content")

            # Wenn kein content angegeben, aus Cache holen
            if not content and path and path in generated_code_cache:
                logger.info(f"📥 Hole Code aus Cache für: {path}")
                content = generated_code_cache[path]
                # Nochmal Tool mit content aufrufen
                obs = call_tool("write_file", {"path": path, "content": content}, timeout=30)

                if not obs.get("error"):
                    logger.info(f"✅ Datei geschrieben: {path}")
                    # Cache leeren
                    del generated_code_cache[path]

        # Observation zurückgeben
        messages.append({"role": "user", "content": f"Observation: {json.dumps(obs, ensure_ascii=False)[:1000]}"})

        # Bei Erfolg: Failures zurücksetzen
        if not obs.get("error"):
            failures = 0

        # Zu viele Fehler?
        if failures >= 4:
            logger.error("Zu viele Fehlversuche; breche ab.")
            call_tool("log_learning_entry", {
                "goal": user_query,
                "outcome": "failure_max_retries",
                "details": {
                    "error": "Max retries exceeded",
                    "final_step": step,
                    "dest_folder": dest_folder
                },
                "learning": "Zu viele Fehler, möglicherweise ist die Aufgabe zu komplex."
            })
            return "❌ Konnte Aufgabe nicht abschließen (zu viele Fehler). Details wurden geloggt."

    # Max Steps erreicht
    logger.warning("⚠️ Maximale Anzahl an Schritten erreicht")
    call_tool("log_learning_entry", {
        "goal": user_query,
        "outcome": "timeout",
        "details": {"final_step": max_steps, "dest_folder": dest_folder},
        "learning": "Max steps erreicht, Aufgabe evtl. zu komplex oder mehr Schritte nötig."
    })
    return "⚠️ Maximale Anzahl an Schritten erreicht, ohne finale Antwort."


# -----------------------------------------------------------------------------
# Async Wrapper für Integration mit main_dispatcher
# -----------------------------------------------------------------------------
class DeveloperAgentV2:
    """
    Async-kompatible Wrapper-Klasse für developer_agent_v2.

    Ermöglicht Integration mit main_dispatcher.py, der async agents erwartet.
    Reichert jeden Task automatisch mit Git-Status, Commits und offenen Dev-Tasks an.
    """

    def __init__(self, tools_description_string: str, dest_folder: str = ".", max_steps: int = 12):
        self.tools_description = tools_description_string
        self.dest_folder = dest_folder
        self.max_steps = max_steps

    # ------------------------------------------------------------------
    # Erweiterter run()-Einstieg: Entwicklungs-Kontext injizieren
    # ------------------------------------------------------------------

    async def run(self, query: str) -> str:
        """Reichert den Task mit Git-Kontext an, dann ab in den Sync-Loop."""
        context = await self._build_dev_context()
        enriched_query = query + "\n\n" + context if context else query
        return await asyncio.to_thread(
            run_developer_task,
            enriched_query,
            dest_folder=self.dest_folder,
            max_steps=self.max_steps,
        )

    # ------------------------------------------------------------------
    # Entwicklungs-Kontext aufbauen
    # ------------------------------------------------------------------

    async def _build_dev_context(self) -> str:
        """
        Git-Branch, geänderte Dateien, letzte Commits,
        Projektpfade und offene Dev-Tasks.
        """
        lines: list[str] = ["# ENTWICKLUNGS-KONTEXT (automatisch geladen)"]
        has_content = False

        git_status = await asyncio.to_thread(self._get_git_status)
        if git_status:
            lines.append(git_status)
            has_content = True

        recent_commits = await asyncio.to_thread(self._get_recent_commits)
        if recent_commits:
            lines.append(f"Letzte Commits: {recent_commits}")
            has_content = True

        lines.append(
            f"Projektpfad: {PROJECT_ROOT} | "
            "Agenten: agent/agents/ | Tools: tools/ | "
            "Orchestration: orchestration/ | Memory: memory/ | "
            "Server: server/ | Tests: tests/"
        )

        pending = await asyncio.to_thread(self._get_pending_dev_tasks)
        if pending:
            lines.append(f"Offene Dev-Tasks: {pending}")
            has_content = True

        lines.append(f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines) if has_content else ""

    def _get_git_status(self) -> str:
        """Git-Branch + geänderte .py-Dateien (keine __pycache__)."""
        try:
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=5, cwd=PROJECT_ROOT,
            ).stdout.strip()

            diff_out = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=PROJECT_ROOT,
            ).stdout.strip()

            changed = [
                f for f in diff_out.splitlines()
                if f.endswith(".py") and "__pycache__" not in f
            ] if diff_out else []

            if changed:
                preview = ", ".join(changed[:4])
                suffix = f" (+{len(changed) - 4} weitere)" if len(changed) > 4 else ""
                return f"Git-Branch: {branch} | Geändert: {preview}{suffix}"
            return f"Git-Branch: {branch} | Keine ungestagten Änderungen"
        except Exception as exc:
            logger.debug("Git-Status nicht abrufbar: %s", exc)
            return ""

    def _get_recent_commits(self, n: int = 3) -> str:
        """Letzte n Commit-Hashes + Messages."""
        try:
            result = subprocess.run(
                ["git", "log", f"--{n}", "--oneline", "--no-decorate"],
                capture_output=True, text=True, timeout=5, cwd=PROJECT_ROOT,
            )
            lines = result.stdout.strip().splitlines()
            return " | ".join(lines[:n]) if lines else ""
        except Exception as exc:
            logger.debug("Git-Log nicht abrufbar: %s", exc)
            return ""

    def _get_pending_dev_tasks(self) -> str:
        """Offene Tasks mit Code/Entwicklungs-Bezug aus der TaskQueue."""
        try:
            from orchestration.task_queue import TaskQueue

            keywords = {"code", "skript", "tool", "agent", "implement", "fix",
                        "bug", "feature", "python", "datei", "funktion", "klasse",
                        "developer", "entwickl", "refactor"}
            relevant = []
            for t in TaskQueue().get_pending():
                desc = (t.get("description") or t.get("title") or "").lower()
                if any(kw in desc for kw in keywords):
                    relevant.append((t.get("description") or t.get("title") or "Task")[:50])
            return " | ".join(relevant[:3]) if relevant else ""
        except Exception as exc:
            logger.debug("TaskQueue nicht abrufbar: %s", exc)
            return ""


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="D.A.V.E. v2 - Verbesserter Developer Agent")
    parser.add_argument("query", nargs="+", help="Entwicklungsaufgabe")
    parser.add_argument("--folder", "-f", default=".", help="Ziel-Ordner (default: .)")
    parser.add_argument("--steps", "-s", type=int, default=12, help="Max Schritte (default: 12)")

    args = parser.parse_args()

    query = " ".join(args.query)
    result = run_developer_task(query, dest_folder=args.folder, max_steps=args.steps)

    print("\n" + "="*80)
    print("💡 FINALE ANTWORT DES DEVELOPER-AGENTEN (v2):")
    print("="*80)
    print(textwrap.fill(result, width=80))
    print("="*80)

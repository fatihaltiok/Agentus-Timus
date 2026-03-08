from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from tools.tool_registry_v2 import ToolCategory as C
from tools.tool_registry_v2 import ToolParameter as P
from tools.tool_registry_v2 import tool

log = logging.getLogger("code_editor_tool")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODIFIABLE_WHITELIST = [
    "tools/",
    "agent/agents/",
    "orchestration/",
    "agent/prompts.py",
    "utils/smtp_email.py",
]

NEVER_MODIFY = [
    ".env",
    "utils/policy_gate.py",
    "gateway/telegram_gateway.py",
    "tools/code_editor_tool/",
    "agent/base_agent.py",
    "main_dispatcher.py",
    "memory/soul_engine.py",
]

CORE_FILES_REQUIRE_APPROVAL = [
    "agent/agents/meta.py",
    "agent/agents/shell.py",
    "agent/providers.py",
    "orchestration/autonomous_runner.py",
]

MERCURY_FIM_ENDPOINT = "/v1/fim/completions"
MERCURY_APPLY_ENDPOINT = "/v1/apply/completions"
MERCURY_EDIT_ENDPOINT = "/v1/edit/completions"
MERCURY_MODEL_NAME = os.getenv("INCEPTION_EDIT_MODEL", "mercury-edit")


def _normalize_relative_path(file_path: str) -> str:
    path = str(file_path or "").strip().replace("\\", "/")
    if not path:
        return ""
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(PROJECT_ROOT.resolve())
        except Exception:
            return ""
    normalized = candidate.as_posix().lstrip("./")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _resolve_project_path(file_path: str) -> Path:
    rel = _normalize_relative_path(file_path)
    if not rel:
        raise ValueError("Ungültiger Dateipfad")
    resolved = (PROJECT_ROOT / rel).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Pfad ausserhalb des Projekts ist nicht erlaubt: {file_path}") from exc
    return resolved


def _starts_with_any(path: str, prefixes: list[str]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def is_modifiable_path(file_path: str) -> bool:
    rel = _normalize_relative_path(file_path)
    if not rel:
        return False
    if _starts_with_any(rel, NEVER_MODIFY):
        return False
    return _starts_with_any(rel, MODIFIABLE_WHITELIST)


def requires_core_approval(file_path: str) -> bool:
    return _normalize_relative_path(file_path) in CORE_FILES_REQUIRE_APPROVAL


def safety_check(file_path: str) -> Dict[str, Any]:
    rel = _normalize_relative_path(file_path)
    if not rel:
        raise PermissionError("Leerer oder ungültiger Dateipfad")
    if _starts_with_any(rel, NEVER_MODIFY):
        raise PermissionError(f"Datei ist von Selbstmodifikation ausgeschlossen: {rel}")
    if not _starts_with_any(rel, MODIFIABLE_WHITELIST):
        raise PermissionError(f"Datei liegt nicht in der Modifikations-Whitelist: {rel}")
    resolved = _resolve_project_path(rel)
    return {
        "relative_path": rel,
        "absolute_path": str(resolved),
        "is_core": requires_core_approval(rel),
    }


def build_mercury_edit_prompt(original: str, update_snippet: str) -> str:
    return (
        "<|original_code|>\n"
        f"{original}\n"
        "<|/original_code|>\n\n"
        "<|update_snippet|>\n"
        f"{update_snippet}\n"
        "<|/update_snippet|>"
    )


def validate_python_syntax(code: str, file_path: str = "") -> Dict[str, Any]:
    try:
        ast.parse(code)
        return {"valid": True, "file_path": _normalize_relative_path(file_path)}
    except SyntaxError as exc:
        location = f"Zeile {exc.lineno}, Spalte {exc.offset}" if exc.lineno else "unbekannte Position"
        return {
            "valid": False,
            "file_path": _normalize_relative_path(file_path),
            "error": f"SyntaxError ({location}): {exc.msg}",
        }


def list_modifiable_project_files() -> list[str]:
    files: list[str] = []
    for entry in MODIFIABLE_WHITELIST:
        rel = _normalize_relative_path(entry)
        target = PROJECT_ROOT / rel
        if target.is_file():
            if is_modifiable_path(rel):
                files.append(rel)
            continue
        if not target.exists() or not target.is_dir():
            continue
        for path in target.rglob("*.py"):
            rel_path = path.relative_to(PROJECT_ROOT).as_posix()
            if is_modifiable_path(rel_path):
                files.append(rel_path)
    return sorted(set(files))


def _compose_mercury_url(endpoint: str) -> str:
    base_url = os.getenv("INCEPTION_API_URL", "https://api.inceptionlabs.ai").rstrip("/")
    if base_url.endswith("/v1") and endpoint.startswith("/v1/"):
        return base_url + endpoint[3:]
    return base_url + endpoint


async def request_code_edit(
    *,
    file_path: str,
    change_description: str,
    update_snippet: Optional[str] = None,
) -> Dict[str, Any]:
    info = safety_check(file_path)
    absolute_path = Path(info["absolute_path"])
    if not absolute_path.exists() or not absolute_path.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {info['relative_path']}")

    api_key = os.getenv("INCEPTION_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("INCEPTION_API_KEY fehlt")

    original = absolute_path.read_text(encoding="utf-8")
    content = build_mercury_edit_prompt(original, update_snippet or change_description)
    payload = {
        "model": MERCURY_MODEL_NAME,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 4000,
    }

    url = _compose_mercury_url(MERCURY_APPLY_ENDPOINT)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout_seconds = float(os.getenv("INCEPTION_EDIT_TIMEOUT_SEC", "60"))
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    modified_code = ""
    choices = data.get("choices") or []
    if choices:
        first = choices[0] or {}
        message = first.get("message") or {}
        modified_code = str(message.get("content") or first.get("text") or "").strip()
    if not modified_code:
        modified_code = str(data.get("content") or data.get("output") or "").strip()
    if not modified_code:
        raise RuntimeError("Mercury Edit lieferte keinen modifizierten Code zurück")

    syntax = validate_python_syntax(modified_code, info["relative_path"])
    if not syntax.get("valid"):
        return {
            "success": False,
            "status": "error",
            "file_path": info["relative_path"],
            "modified_code": modified_code,
            "error": syntax.get("error", "Syntax ungültig"),
            "model": MERCURY_MODEL_NAME,
            "endpoint": MERCURY_APPLY_ENDPOINT,
        }

    return {
        "success": True,
        "status": "success",
        "modified_code": modified_code,
        "file_path": info["relative_path"],
        "model": MERCURY_MODEL_NAME,
        "endpoint": MERCURY_APPLY_ENDPOINT,
        "is_core": bool(info["is_core"]),
    }


@tool(
    name="apply_code_edit",
    description="Wendet eine präzise Code-Änderung via Mercury Edit auf eine bestehende Datei an und liefert den modifizierten Code zurück, ohne die Datei direkt zu schreiben.",
    parameters=[
        P("file_path", "string", "Relativer Pfad zur bestehenden Datei", required=True),
        P("change_description", "string", "Beschreibung der gewünschten Änderung", required=True),
        P("update_snippet", "string", "Optionaler präziser Änderungssnippet für Mercury Edit", required=False, default=""),
    ],
    capabilities=["code", "development"],
    category=C.CODE,
)
async def apply_code_edit(file_path: str, change_description: str, update_snippet: str = "") -> Dict[str, Any]:
    return await request_code_edit(
        file_path=file_path,
        change_description=change_description,
        update_snippet=update_snippet or None,
    )


@tool(
    name="validate_code_syntax",
    description="Validiert Python-Code syntaktisch via ast.parse.",
    parameters=[
        P("code", "string", "Zu prüfender Python-Code", required=True),
        P("file_path", "string", "Optionaler Dateipfad für Fehlermeldungen", required=False, default=""),
    ],
    capabilities=["code", "development"],
    category=C.CODE,
)
def validate_code_syntax(code: str, file_path: str = "") -> Dict[str, Any]:
    return validate_python_syntax(code, file_path=file_path)


@tool(
    name="list_modifiable_files",
    description="Listet alle aktuell modifizierbaren Dateien aus der M18-Whitelist auf.",
    parameters=[],
    capabilities=["code", "development"],
    category=C.CODE,
)
def list_modifiable_files() -> Dict[str, Any]:
    return {"files": list_modifiable_project_files()}

"""Guards against desktop/UI side effects inside Timus service contexts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_PROTECTED_FILENAMES = {
    "timus_server.log",
    "timus_restart_status.json",
    "timus_restart_detached.log",
}
_PROTECTED_SUFFIXES = {
    ".log",
    ".journal",
    ".jsonl",
}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_service_headless_context() -> bool:
    if _truthy(os.getenv("TIMUS_FORCE_HEADLESS")):
        return True
    return bool(os.getenv("SYSTEMD_EXEC_PID") or os.getenv("INVOCATION_ID"))


def is_protected_runtime_artifact(path: str | Path | None) -> bool:
    if not path:
        return False
    try:
        p = Path(path)
    except Exception:
        return False
    name = p.name.strip().lower()
    if name in _PROTECTED_FILENAMES:
        return True
    return p.suffix.strip().lower() in _PROTECTED_SUFFIXES


def desktop_open_block_reason(*, action_kind: str, target: str | Path | None = None) -> Optional[str]:
    if action_kind == "file" and is_protected_runtime_artifact(target):
        return "Geschuetztes Runtime-Artefakt darf nicht lokal geoeffnet werden"
    if is_service_headless_context():
        return f"Desktop-Aktion '{action_kind}' ist im Timus-Service-Kontext blockiert"
    return None


#!/usr/bin/env python3
"""Detached supervisor for Timus restarts.

Runs independently from MCP and writes structured status to disk so the
requesting side can inspect progress after MCP has been restarted.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCRIPT = PROJECT_ROOT / "scripts" / "restart_timus.sh"
DEFAULT_STATUS = PROJECT_ROOT / "logs" / "timus_restart_status.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_status(status_file: Path, payload: dict) -> None:
    status_file.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload.setdefault("updated_at", _now())
    status_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _run_supervised_restart(mode: str, script_path: Path, status_file: Path) -> int:
    _write_status(
        status_file,
        {
            "status": "running",
            "phase": "preflight",
            "mode": mode,
            "script_path": str(script_path),
            "pid": os.getpid(),
            "started_at": _now(),
        },
    )

    try:
        proc = subprocess.run(
            ["bash", str(script_path), mode],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        _write_status(
            status_file,
            {
                "status": "failed",
                "phase": "timeout",
                "mode": mode,
                "pid": os.getpid(),
                "error": f"Restart timeout: {exc}",
                "finished_at": _now(),
            },
        )
        return 1
    except Exception as exc:
        _write_status(
            status_file,
            {
                "status": "failed",
                "phase": "exception",
                "mode": mode,
                "pid": os.getpid(),
                "error": str(exc),
                "finished_at": _now(),
            },
        )
        return 1

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    payload = {
        "status": "completed" if proc.returncode == 0 else "failed",
        "phase": "completed" if proc.returncode == 0 else "script_failed",
        "mode": mode,
        "pid": os.getpid(),
        "returncode": proc.returncode,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
        "finished_at": _now(),
    }
    _write_status(status_file, payload)
    return 0 if proc.returncode == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detached Timus restart supervisor")
    parser.add_argument("mode", nargs="?", default="full", choices=["full", "mcp", "dispatcher", "status"])
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT))
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS))
    args = parser.parse_args(argv)

    script_path = Path(args.script).resolve()
    status_file = Path(args.status_file).resolve()
    return _run_supervised_restart(args.mode, script_path, status_file)


if __name__ == "__main__":
    raise SystemExit(main())

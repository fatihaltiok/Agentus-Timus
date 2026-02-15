# utils/audit_logger.py
"""
Strukturiertes JSONL Audit-Logging, eine Datei pro Task.
Jede Zeile ist ein JSON-Objekt mit Timestamp, Action, Input/Output, Status.
"""
import json
import logging
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

log = logging.getLogger("audit_logger")

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


class AuditLogger:
    """Per-Task JSONL Logger. Fire-and-forget — Schreibfehler crashen nie den Agent."""

    def __init__(self, task_id: str = None):
        self.task_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        self.log_path = LOGS_DIR / f"{date_str}_{self.task_id}.jsonl"
        self._step = 0
        self._start_time = time.time()

    def log_step(
        self,
        action: str,
        input_data: Any = None,
        output_data: Any = None,
        status: str = "ok",
        duration_ms: Optional[float] = None,
        metadata: Optional[dict] = None,
    ):
        """Schreibt eine JSONL-Zeile fuer einen Schritt."""
        self._step += 1
        entry = {
            "timestamp": datetime.now().isoformat(),
            "task_id": self.task_id,
            "step": self._step,
            "action": action,
            "input": _safe_serialize(input_data),
            "output": _safe_serialize(output_data),
            "status": status,
            "duration_ms": round(duration_ms, 2) if duration_ms else None,
        }
        if metadata:
            entry["metadata"] = metadata

        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            log.error(f"[audit] Schreibfehler: {e}")

    def log_start(self, task_description: str, agent_name: str = ""):
        """Loggt Task-Start."""
        self.log_step(
            action="task_start",
            input_data={"task": task_description, "agent": agent_name},
            status="started",
        )

    def log_end(self, result: str, status: str = "completed"):
        """Loggt Task-Ende mit Gesamtdauer."""
        total_ms = (time.time() - self._start_time) * 1000
        self.log_step(
            action="task_end",
            output_data={"result": str(result)[:500]},
            status=status,
            duration_ms=total_ms,
        )


def _safe_serialize(data: Any) -> Any:
    """Kuerzt grosse Daten fuer Logging."""
    if data is None:
        return None
    s = str(data)
    if len(s) > 1000:
        return s[:1000] + "...<truncated>"
    try:
        json.dumps(data, default=str)
        return data
    except (TypeError, ValueError):
        return s[:1000]

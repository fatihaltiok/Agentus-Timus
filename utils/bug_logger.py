# utils/bug_logger.py
"""
Maschinenlesbares Bug-Tracking.
Jeder Fehler erzeugt einen JSONL-Eintrag in logs/bugs/ und
einen menschenlesbaren Eintrag in logs/buglog.md.
"""
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

from utils.audit_logger import _safe_serialize

log = logging.getLogger("bug_logger")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = _PROJECT_ROOT / "logs"


class BugLogger:
    BUGS_DIR = LOGS_DIR / "bugs"

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is not None:
            self._logs_dir = base_dir
            self._bugs_dir = base_dir / "bugs"
        else:
            self._logs_dir = LOGS_DIR
            self._bugs_dir = self.__class__.BUGS_DIR
        self._bugs_dir.mkdir(parents=True, exist_ok=True)

    def log_bug(
        self,
        bug_id: str,
        severity: str,
        agent: str,
        error_msg: str,
        stack_trace: str = "",
        context: Optional[dict] = None,
    ) -> str:
        """Schreibt Bug-Report als JSONL-Datei und Eintrag in buglog.md.

        Returns:
            Pfad zur angelegten Bug-Datei.
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        short_id = uuid.uuid4().hex[:8]
        filename = f"{date_str}_bug_{bug_id}_{short_id}.jsonl"
        bug_path = self._bugs_dir / filename

        entry = {
            "timestamp": datetime.now().isoformat(),
            "bug_id": bug_id,
            "severity": severity,
            "agent": agent,
            "error": _safe_serialize(error_msg),
            "stack_trace": stack_trace[:2000] if stack_trace else "",
            "context": _safe_serialize(context or {}),
        }

        try:
            with open(bug_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            log.error(f"[bug_logger] Schreibfehler (JSONL): {e}")

        try:
            display_path = str(bug_path.relative_to(_PROJECT_ROOT))
        except ValueError:
            display_path = str(bug_path)

        self._append_to_buglog(
            timestamp=entry["timestamp"],
            bug_id=bug_id,
            severity=severity,
            agent=agent,
            error_msg=str(error_msg)[:200],
            bug_file=display_path,
        )

        return str(bug_path)

    def _append_to_buglog(
        self,
        timestamp: str,
        bug_id: str,
        severity: str,
        agent: str,
        error_msg: str,
        bug_file: str,
    ) -> None:
        """Schreibt kompakten Markdown-Eintrag in logs/buglog.md."""
        buglog_path = self._logs_dir / "buglog.md"
        short_ts = timestamp[:19].replace("T", " ")
        entry = (
            f"\n### Bug: {short_ts} — {bug_id} [{severity.upper()}]\n"
            f"**Agent:** {agent}  **Fehler:** {error_msg}\n"
            f"**Datei:** {bug_file}\n"
            f"---\n"
        )
        try:
            with open(buglog_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            log.error(f"[bug_logger] Schreibfehler (buglog.md): {e}")

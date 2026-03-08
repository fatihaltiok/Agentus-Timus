from __future__ import annotations

import asyncio
import difflib
import json
import logging
import os
import sqlite3
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from memory.agent_blackboard import get_blackboard
from tools.code_editor_tool.tool import (
    CORE_FILES_REQUIRE_APPROVAL,
    MERCURY_APPLY_ENDPOINT,
    NEVER_MODIFY,
    MODIFIABLE_WHITELIST,
    request_code_edit,
    requires_core_approval,
    safety_check,
    validate_python_syntax,
)

log = logging.getLogger("SelfModifierEngine")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_DB_PATH = PROJECT_ROOT / "data" / "timus_memory.db"

_SELF_MODIFIER_ENGINE: Optional["SelfModifierEngine"] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS self_modify_log (
    id         TEXT PRIMARY KEY,
    file_path  TEXT,
    change     TEXT,
    status     TEXT,
    backup_ref TEXT,
    session_id TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS self_modify_pending (
    id                 TEXT PRIMARY KEY,
    file_path          TEXT,
    change_description TEXT,
    update_snippet     TEXT,
    original_code      TEXT,
    modified_code      TEXT,
    backup_ref         TEXT,
    session_id         TEXT,
    require_tests      INTEGER DEFAULT 1,
    created_at         TEXT
);
"""


@dataclass
class SelfModifyResult:
    status: str
    file_path: str
    change_description: str
    backup_ref: str
    test_result: str
    audit_id: str


class SelfModifierEngine:
    """Orchestriert sichere Code-Selbstmodifikation mit Backup + Rollback."""

    VALID_STATUSES = {"success", "pending_approval", "rolled_back", "blocked", "error"}

    def __init__(self, db_path: Path = MEMORY_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    async def modify_file(
        self,
        file_path: str,
        change_description: str,
        update_snippet: Optional[str] = None,
        *,
        require_tests: bool = True,
        session_id: str = "",
    ) -> SelfModifyResult:
        audit_id = uuid.uuid4().hex
        backup_ref = ""
        rel_path = str(file_path or "")
        try:
            safety = safety_check(file_path)
            rel_path = str(safety["relative_path"])
        except Exception as exc:
            self._audit_log(audit_id, rel_path, change_description, "blocked", backup_ref, session_id)
            return SelfModifyResult("blocked", rel_path, change_description, backup_ref, "skipped", audit_id)

        try:
            original = Path(PROJECT_ROOT / rel_path).read_text(encoding="utf-8")
            backup_ref = self._save_git_backup(rel_path, original)
            result = await request_code_edit(
                file_path=rel_path,
                change_description=change_description,
                update_snippet=update_snippet,
            )
            if not result.get("success"):
                self._audit_log(audit_id, rel_path, change_description, "error", backup_ref, session_id)
                return SelfModifyResult("error", rel_path, change_description, backup_ref, "skipped", audit_id)

            modified = str(result.get("modified_code") or "")
            syntax = self._validate_syntax(modified, rel_path)
            if not syntax.get("valid"):
                self._audit_log(audit_id, rel_path, change_description, "error", backup_ref, session_id)
                return SelfModifyResult("error", rel_path, change_description, backup_ref, "skipped", audit_id)

            if requires_core_approval(rel_path) and _env_bool("SELF_MODIFY_REQUIRE_APPROVAL", True):
                pending_id = self._store_pending(
                    file_path=rel_path,
                    original=original,
                    modified=modified,
                    change_description=change_description,
                    update_snippet=update_snippet or "",
                    backup_ref=backup_ref,
                    session_id=session_id,
                    require_tests=require_tests,
                )
                await self._telegram_approval_request(
                    pending_id=pending_id,
                    file_path=rel_path,
                    change_description=change_description,
                    original=original,
                    modified=modified,
                )
                self._audit_log(audit_id, rel_path, change_description, "pending_approval", backup_ref, session_id)
                return SelfModifyResult("pending_approval", rel_path, change_description, backup_ref, "skipped", audit_id)

            self._write_file(rel_path, modified)
            test_result = "skipped"
            if require_tests and _env_bool("SELF_MODIFY_REQUIRE_TESTS", True):
                test_result = self._run_tests(rel_path)
            if test_result == "failed":
                self._rollback(rel_path, backup_ref)
                self._audit_log(audit_id, rel_path, change_description, "rolled_back", backup_ref, session_id)
                self._write_blackboard(rel_path, change_description, "rolled_back", session_id)
                return SelfModifyResult("rolled_back", rel_path, change_description, backup_ref, test_result, audit_id)

            self._audit_log(audit_id, rel_path, change_description, "success", backup_ref, session_id)
            self._write_blackboard(rel_path, change_description, "success", session_id)
            return SelfModifyResult("success", rel_path, change_description, backup_ref, test_result, audit_id)
        except Exception as exc:
            log.error("SelfModify modify_file fehlgeschlagen: %s", exc, exc_info=True)
            if backup_ref and rel_path:
                try:
                    self._rollback(rel_path, backup_ref)
                except Exception:
                    pass
            self._audit_log(audit_id, rel_path, change_description, "error", backup_ref, session_id)
            return SelfModifyResult("error", rel_path, change_description, backup_ref, "skipped", audit_id)

    async def approve_pending(self, pending_id: str, approver: str = "") -> SelfModifyResult:
        row = self._load_pending(pending_id)
        if not row:
            return SelfModifyResult("error", "", "", "", "skipped", "")

        audit_id = uuid.uuid4().hex
        rel_path = str(row["file_path"])
        backup_ref = str(row["backup_ref"])
        change_description = str(row["change_description"])
        session_id = str(row["session_id"])
        modified = str(row["modified_code"])
        self._write_file(rel_path, modified)
        test_result = "skipped"
        require_tests = bool(int(row.get("require_tests", 1) or 0))
        if require_tests and _env_bool("SELF_MODIFY_REQUIRE_TESTS", True):
            test_result = self._run_tests(rel_path)
        if test_result == "failed":
            self._rollback(rel_path, backup_ref)
            self._delete_pending(pending_id)
            self._audit_log(audit_id, rel_path, change_description, "rolled_back", backup_ref, session_id)
            self._write_blackboard(rel_path, change_description, "rolled_back", session_id)
            return SelfModifyResult("rolled_back", rel_path, change_description, backup_ref, test_result, audit_id)

        self._delete_pending(pending_id)
        self._audit_log(audit_id, rel_path, change_description, "success", backup_ref, session_id)
        self._write_blackboard(rel_path, change_description, "success", session_id)
        return SelfModifyResult("success", rel_path, change_description, backup_ref, test_result, audit_id)

    async def reject_pending(self, pending_id: str, approver: str = "") -> SelfModifyResult:
        row = self._load_pending(pending_id)
        if not row:
            return SelfModifyResult("error", "", "", "", "skipped", "")
        self._delete_pending(pending_id)
        audit_id = uuid.uuid4().hex
        rel_path = str(row["file_path"])
        change_description = str(row["change_description"])
        backup_ref = str(row["backup_ref"])
        session_id = str(row["session_id"])
        self._audit_log(audit_id, rel_path, change_description, "blocked", backup_ref, session_id)
        self._write_blackboard(rel_path, change_description, "blocked", session_id)
        return SelfModifyResult("blocked", rel_path, change_description, backup_ref, "skipped", audit_id)

    def run_cycle(self) -> Dict[str, Any]:
        if not _env_bool("AUTONOMY_SELF_MODIFY_ENABLED", False):
            return {"status": "disabled", "applied": 0, "pending": self.pending_count()}
        return {
            "status": "enabled",
            "applied": 0,
            "pending": self.pending_count(),
            "max_per_cycle": _env_int("SELF_MODIFY_MAX_PER_CYCLE", 3),
        }

    def pending_count(self) -> int:
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM self_modify_pending").fetchone()
        return int((row or [0])[0] or 0)

    def _save_git_backup(self, file_path: str, original: str) -> str:
        backup_dir = PROJECT_ROOT / "data" / "self_modify_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        safe_name = file_path.replace("/", "__")
        target = backup_dir / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}_{safe_name}.bak"
        target.write_text(original, encoding="utf-8")
        return str(target)

    def _validate_syntax(self, code: str, file_path: str) -> Dict[str, Any]:
        return validate_python_syntax(code, file_path)

    def _write_file(self, file_path: str, content: str) -> None:
        target = PROJECT_ROOT / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _rollback(self, file_path: str, backup_ref: str) -> None:
        if not backup_ref:
            return
        backup_path = Path(backup_ref)
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup nicht gefunden: {backup_ref}")
        original = backup_path.read_text(encoding="utf-8")
        self._write_file(file_path, original)

    def _find_test_file(self, changed_file: str) -> str:
        path = Path(changed_file)
        stem = path.stem
        parent_name = path.parent.name
        candidates = [
            PROJECT_ROOT / "tests" / f"test_{parent_name}.py",
            PROJECT_ROOT / "tests" / f"test_{parent_name}s.py",
            PROJECT_ROOT / "tests" / f"test_{stem}.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return ""

    def _run_tests(self, file_path: str) -> str:
        test_file = self._find_test_file(file_path)
        if not test_file:
            return "skipped"
        import subprocess

        result = subprocess.run(
            ["python", "-m", "pytest", test_file, "-x", "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return "passed" if result.returncode == 0 else "failed"

    def _audit_log(
        self,
        audit_id: str,
        file_path: str,
        change_description: str,
        status: str,
        backup_ref: str,
        session_id: str,
    ) -> None:
        created_at = datetime.utcnow().isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO self_modify_log (id, file_path, change, status, backup_ref, session_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (audit_id, file_path, change_description, status, backup_ref, session_id, created_at),
            )
            conn.commit()

    def _store_pending(
        self,
        *,
        file_path: str,
        original: str,
        modified: str,
        change_description: str,
        update_snippet: str,
        backup_ref: str,
        session_id: str,
        require_tests: bool,
    ) -> str:
        pending_id = uuid.uuid4().hex
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO self_modify_pending (id, file_path, change_description, update_snippet, original_code, modified_code, backup_ref, session_id, require_tests, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pending_id,
                    file_path,
                    change_description,
                    update_snippet,
                    original,
                    modified,
                    backup_ref,
                    session_id,
                    1 if require_tests else 0,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        return pending_id

    def _load_pending(self, pending_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM self_modify_pending WHERE id = ?", (pending_id,)).fetchone()
        return dict(row) if row else None

    def _delete_pending(self, pending_id: str) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM self_modify_pending WHERE id = ?", (pending_id,))
            conn.commit()

    async def _telegram_approval_request(
        self,
        *,
        pending_id: str,
        file_path: str,
        change_description: str,
        original: str,
        modified: str,
    ) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        allowed_ids = os.getenv("TELEGRAM_ALLOWED_IDS", "").strip()
        if not token or not allowed_ids:
            log.warning("M18: Telegram nicht konfiguriert — Approval kann nicht zugestellt werden")
            return
        chat_ids: list[int] = []
        for value in allowed_ids.split(","):
            value = value.strip()
            if not value:
                continue
            try:
                chat_ids.append(int(value))
            except ValueError:
                continue
        if not chat_ids:
            return
        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(),
                modified.splitlines(),
                fromfile="vorher",
                tofile="nachher",
                lineterm="",
            )
        )
        preview = "\n".join(diff_lines[:20]) or "(kein Diff verfügbar)"
        message = (
            "🔧 *Code-Änderung beantragt*\n"
            f"Datei: `{file_path}`\n"
            f"Änderung: \"{change_description[:160]}\"\n\n"
            "--- Vorher/Nachher ---\n"
            f"```diff\n{preview[:1400]}\n```"
        )
        try:
            from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Anwenden", callback_data=json.dumps({"type": "code_edit_approve", "pid": pending_id})),
                InlineKeyboardButton("❌ Ablehnen", callback_data=json.dumps({"type": "code_edit_reject", "pid": pending_id})),
            ]])
            bot = Bot(token=token)
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )
                except Exception as exc:
                    log.warning("M18: Telegram-Senden an %d fehlgeschlagen: %s", chat_id, exc)
            await bot.close()
        except Exception as exc:
            log.warning("M18: Telegram-Bot-Fehler: %s", exc)

    def _write_blackboard(self, file_path: str, change_description: str, status: str, session_id: str) -> None:
        try:
            get_blackboard().write(
                agent="self_modifier_engine",
                topic="self_modification",
                key=file_path,
                value={
                    "file_path": file_path,
                    "change": change_description,
                    "status": status,
                },
                ttl_minutes=120,
                session_id=session_id,
            )
        except Exception as exc:
            log.debug("M18 Blackboard-Write fehlgeschlagen: %s", exc)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def get_self_modifier_engine() -> SelfModifierEngine:
    global _SELF_MODIFIER_ENGINE
    if _SELF_MODIFIER_ENGINE is None:
        _SELF_MODIFIER_ENGINE = SelfModifierEngine()
    return _SELF_MODIFIER_ENGINE

from __future__ import annotations

import asyncio
import difflib
import json
import logging
import os
import sqlite3
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from memory.agent_blackboard import get_blackboard
from orchestration.self_modification_patch_pipeline import (
    cleanup_isolated_patch_workspace,
    create_isolated_patch_workspace,
    promote_isolated_patch,
)
from orchestration.self_hardening_runtime import record_self_hardening_event
from orchestration.self_modification_canary import run_self_modification_canary
from orchestration.self_modification_controller import (
    AutonomousSelfModificationCandidate,
    build_autonomous_self_modification_candidates,
    evaluate_self_modification_controller,
)
from orchestration.self_modification_policy import evaluate_self_modification_policy
from orchestration.self_modification_risk import classify_self_modification_risk
from orchestration.self_modification_verification import run_self_modification_verification
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

CREATE TABLE IF NOT EXISTS self_modify_change_memory (
    change_key            TEXT PRIMARY KEY,
    audit_id              TEXT,
    file_path             TEXT,
    change_description    TEXT,
    policy_zone           TEXT,
    risk_level            TEXT,
    risk_reason           TEXT,
    test_result           TEXT,
    verification_summary  TEXT,
    canary_state          TEXT,
    canary_summary        TEXT,
    outcome_status        TEXT,
    rollback_applied      INTEGER DEFAULT 0,
    regression_detected   INTEGER DEFAULT 0,
    workspace_mode        TEXT,
    session_id            TEXT,
    created_at            TEXT,
    updated_at            TEXT
);

CREATE TABLE IF NOT EXISTS self_modify_autonomous_source_state (
    source_kind TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    status      TEXT NOT NULL,
    file_path   TEXT,
    audit_id    TEXT,
    note        TEXT,
    updated_at  TEXT,
    PRIMARY KEY (source_kind, source_id)
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
    policy_zone: str = ""
    risk_level: str = ""
    risk_reason: str = ""
    workspace_mode: str = ""
    patch_diff: str = ""
    verification_summary: str = ""
    canary_state: str = ""
    canary_summary: str = ""


@dataclass(frozen=True)
class SelfModificationChangeMemorySummary:
    total: int = 0
    success_count: int = 0
    rolled_back_count: int = 0
    blocked_count: int = 0
    pending_approval_count: int = 0
    error_count: int = 0
    rollback_count: int = 0
    regression_count: int = 0


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
        change_type: str = "auto",
        require_tests: bool = True,
        session_id: str = "",
    ) -> SelfModifyResult:
        audit_id = uuid.uuid4().hex
        change_key = audit_id
        backup_ref = ""
        rel_path = str(file_path or "")
        policy_zone = ""
        risk_level = ""
        risk_reason = ""
        workspace_mode = ""
        patch_diff = ""
        verification_summary = ""
        canary_state = ""
        canary_summary = ""
        try:
            safety = safety_check(file_path)
            rel_path = str(safety["relative_path"])
        except Exception as exc:
            self._audit_log(audit_id, rel_path, change_description, "blocked", backup_ref, session_id)
            self._record_change_memory(
                change_key=change_key,
                audit_id=audit_id,
                file_path=rel_path,
                change_description=change_description,
                policy_zone=policy_zone,
                risk_level=risk_level,
                risk_reason=risk_reason,
                test_result="skipped",
                verification_summary=verification_summary,
                canary_state=canary_state,
                canary_summary=canary_summary,
                outcome_status="blocked",
                rollback_applied=False,
                regression_detected=False,
                workspace_mode=workspace_mode,
                session_id=session_id,
            )
            return SelfModifyResult("blocked", rel_path, change_description, backup_ref, "skipped", audit_id)

        policy = evaluate_self_modification_policy(rel_path, change_type=change_type)
        policy_zone = policy.zone_id
        if not policy.allowed:
            self._audit_log(audit_id, rel_path, f"{change_description}\n[policy] {policy.reason}", "blocked", backup_ref, session_id)
            self._record_change_memory(
                change_key=change_key,
                audit_id=audit_id,
                file_path=rel_path,
                change_description=change_description,
                policy_zone=policy_zone,
                risk_level=risk_level,
                risk_reason=policy.reason,
                test_result="skipped",
                verification_summary=verification_summary,
                canary_state=canary_state,
                canary_summary=canary_summary,
                outcome_status="blocked",
                rollback_applied=False,
                regression_detected=False,
                workspace_mode=workspace_mode,
                session_id=session_id,
            )
            return SelfModifyResult("blocked", rel_path, change_description, backup_ref, "skipped", audit_id, policy_zone=policy_zone)

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
                self._record_change_memory(
                    change_key=change_key,
                    audit_id=audit_id,
                    file_path=rel_path,
                    change_description=change_description,
                    policy_zone=policy_zone,
                    risk_level=risk_level,
                    risk_reason=risk_reason,
                    test_result="skipped",
                    verification_summary=verification_summary,
                    canary_state=canary_state,
                    canary_summary=canary_summary,
                    outcome_status="error",
                    rollback_applied=False,
                    regression_detected=False,
                    workspace_mode=workspace_mode,
                    session_id=session_id,
                )
                return SelfModifyResult("error", rel_path, change_description, backup_ref, "skipped", audit_id, policy_zone=policy_zone)

            modified = str(result.get("modified_code") or "")
            syntax = self._validate_syntax(modified, rel_path)
            if not syntax.get("valid"):
                self._audit_log(audit_id, rel_path, change_description, "error", backup_ref, session_id)
                self._record_change_memory(
                    change_key=change_key,
                    audit_id=audit_id,
                    file_path=rel_path,
                    change_description=change_description,
                    policy_zone=policy_zone,
                    risk_level=risk_level,
                    risk_reason=risk_reason,
                    test_result="skipped",
                    verification_summary=verification_summary,
                    canary_state=canary_state,
                    canary_summary=canary_summary,
                    outcome_status="error",
                    rollback_applied=False,
                    regression_detected=False,
                    workspace_mode=workspace_mode,
                    session_id=session_id,
                )
                return SelfModifyResult("error", rel_path, change_description, backup_ref, "skipped", audit_id, policy_zone=policy_zone)

            risk = classify_self_modification_risk(
                file_path=rel_path,
                change_description=change_description,
                original_code=original,
                modified_code=modified,
                policy=policy,
            )
            risk_level = risk.risk_level
            risk_reason = risk.reason

            require_approval = bool(
                policy.require_approval
                or risk.risk_level != "low"
                or (requires_core_approval(rel_path) and _env_bool("SELF_MODIFY_REQUIRE_APPROVAL", True))
            )
            require_tests = bool(require_tests or bool(policy.required_test_targets))

            if require_approval:
                if risk.risk_level != "low" and not _env_bool("SELF_MODIFY_REQUIRE_APPROVAL", True):
                    self._audit_log(audit_id, rel_path, f"{change_description}\n[risk] {risk.risk_level}:{risk.reason}", "blocked", backup_ref, session_id)
                    self._record_change_memory(
                        change_key=change_key,
                        audit_id=audit_id,
                        file_path=rel_path,
                        change_description=change_description,
                        policy_zone=policy_zone,
                        risk_level=risk_level,
                        risk_reason=risk_reason,
                        test_result="skipped",
                        verification_summary=verification_summary,
                        canary_state=canary_state,
                        canary_summary=canary_summary,
                        outcome_status="blocked",
                        rollback_applied=False,
                        regression_detected=False,
                        workspace_mode=workspace_mode,
                        session_id=session_id,
                    )
                    return SelfModifyResult(
                        "blocked",
                        rel_path,
                        change_description,
                        backup_ref,
                        "skipped",
                        audit_id,
                        policy_zone=policy_zone,
                        risk_level=risk_level,
                        risk_reason=risk_reason,
                    )
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
                change_key = pending_id
                await self._telegram_approval_request(
                    pending_id=pending_id,
                    file_path=rel_path,
                    change_description=change_description,
                    original=original,
                    modified=modified,
                    risk_level=risk.risk_level,
                    risk_reason=risk.reason,
                )
                self._audit_log(audit_id, rel_path, change_description, "pending_approval", backup_ref, session_id)
                self._record_change_memory(
                    change_key=change_key,
                    audit_id=audit_id,
                    file_path=rel_path,
                    change_description=change_description,
                    policy_zone=policy_zone,
                    risk_level=risk_level,
                    risk_reason=risk_reason,
                    test_result="skipped",
                    verification_summary=verification_summary,
                    canary_state=canary_state,
                    canary_summary=canary_summary,
                    outcome_status="pending_approval",
                    rollback_applied=False,
                    regression_detected=False,
                    workspace_mode=workspace_mode,
                    session_id=session_id,
                )
                return SelfModifyResult(
                    "pending_approval",
                    rel_path,
                    change_description,
                    backup_ref,
                    "skipped",
                    audit_id,
                    policy_zone=policy_zone,
                    risk_level=risk_level,
                    risk_reason=risk_reason,
                )

            workspace = create_isolated_patch_workspace(
                project_root=PROJECT_ROOT,
                relative_path=rel_path,
                original_code=original,
                modified_code=modified,
                change_description=change_description,
                session_id=session_id,
            )
            workspace_mode = workspace.mode
            patch_diff = workspace.diff_path.read_text(encoding="utf-8")
            try:
                verification = run_self_modification_verification(
                    project_root=workspace.root_path,
                    relative_path=rel_path,
                    policy=policy,
                    pytest_runner=self._run_tests,
                )
                test_result = verification.status
                verification_summary = verification.summary
                if test_result == "failed":
                    self._audit_log(audit_id, rel_path, change_description, "rolled_back", backup_ref, session_id)
                    self._write_blackboard(rel_path, change_description, "rolled_back", session_id)
                    self._record_change_memory(
                        change_key=change_key,
                        audit_id=audit_id,
                        file_path=rel_path,
                        change_description=change_description,
                        policy_zone=policy_zone,
                        risk_level=risk_level,
                        risk_reason=risk_reason,
                        test_result=test_result,
                        verification_summary=verification_summary,
                        canary_state=canary_state,
                        canary_summary=canary_summary,
                        outcome_status="rolled_back",
                        rollback_applied=True,
                        regression_detected=True,
                        workspace_mode=workspace_mode,
                        session_id=session_id,
                    )
                    return SelfModifyResult(
                        "rolled_back",
                        rel_path,
                        change_description,
                        backup_ref,
                        test_result,
                        audit_id,
                        policy_zone=policy_zone,
                        risk_level=risk_level,
                        risk_reason=risk_reason,
                        workspace_mode=workspace_mode,
                        patch_diff=patch_diff,
                        verification_summary=verification_summary,
                    )

                promote_isolated_patch(project_root=PROJECT_ROOT, workspace=workspace)
            finally:
                cleanup_isolated_patch_workspace(project_root=PROJECT_ROOT, workspace=workspace)

            canary = run_self_modification_canary(
                project_root=PROJECT_ROOT,
                relative_path=rel_path,
                policy=policy,
                pytest_runner=self._run_tests,
            )
            canary_state = canary.state
            canary_summary = canary.summary
            if canary.rollback_required:
                self._rollback(rel_path, backup_ref)
                self._audit_log(audit_id, rel_path, f"{change_description}\n[canary] {canary_summary}", "rolled_back", backup_ref, session_id)
                self._write_blackboard(rel_path, change_description, "rolled_back", session_id)
                self._record_change_memory(
                    change_key=change_key,
                    audit_id=audit_id,
                    file_path=rel_path,
                    change_description=change_description,
                    policy_zone=policy_zone,
                    risk_level=risk_level,
                    risk_reason=risk_reason,
                    test_result="failed",
                    verification_summary=verification_summary,
                    canary_state=canary_state,
                    canary_summary=canary_summary,
                    outcome_status="rolled_back",
                    rollback_applied=True,
                    regression_detected=True,
                    workspace_mode=workspace_mode,
                    session_id=session_id,
                )
                return SelfModifyResult(
                    "rolled_back",
                    rel_path,
                    change_description,
                    backup_ref,
                    "failed",
                    audit_id,
                    policy_zone=policy_zone,
                    risk_level=risk_level,
                    risk_reason=risk_reason,
                    workspace_mode=workspace_mode,
                    patch_diff=patch_diff,
                    verification_summary=verification_summary,
                    canary_state=canary_state,
                    canary_summary=canary_summary,
                )

            self._audit_log(audit_id, rel_path, change_description, "success", backup_ref, session_id)
            self._write_blackboard(rel_path, change_description, "success", session_id)
            self._record_change_memory(
                change_key=change_key,
                audit_id=audit_id,
                file_path=rel_path,
                change_description=change_description,
                policy_zone=policy_zone,
                risk_level=risk_level,
                risk_reason=risk_reason,
                test_result=test_result,
                verification_summary=verification_summary,
                canary_state=canary_state,
                canary_summary=canary_summary,
                outcome_status="success",
                rollback_applied=False,
                regression_detected=False,
                workspace_mode=workspace_mode,
                session_id=session_id,
            )
            return SelfModifyResult(
                "success",
                rel_path,
                change_description,
                backup_ref,
                test_result,
                audit_id,
                policy_zone=policy_zone,
                risk_level=risk_level,
                risk_reason=risk_reason,
                workspace_mode=workspace_mode,
                patch_diff=patch_diff,
                verification_summary=verification_summary,
                canary_state=canary_state,
                canary_summary=canary_summary,
            )
        except Exception as exc:
            log.error("SelfModify modify_file fehlgeschlagen: %s", exc, exc_info=True)
            if backup_ref and rel_path:
                try:
                    self._rollback(rel_path, backup_ref)
                except Exception:
                    pass
            self._audit_log(audit_id, rel_path, change_description, "error", backup_ref, session_id)
            self._record_change_memory(
                change_key=change_key,
                audit_id=audit_id,
                file_path=rel_path,
                change_description=change_description,
                policy_zone=policy_zone,
                risk_level=risk_level,
                risk_reason=risk_reason,
                test_result="skipped",
                verification_summary=verification_summary,
                canary_state=canary_state,
                canary_summary=canary_summary,
                outcome_status="error",
                rollback_applied=bool(backup_ref and rel_path),
                regression_detected=False,
                workspace_mode=workspace_mode,
                session_id=session_id,
            )
            return SelfModifyResult(
                "error",
                rel_path,
                change_description,
                backup_ref,
                "skipped",
                audit_id,
                policy_zone=policy_zone,
                risk_level=risk_level,
                risk_reason=risk_reason,
                workspace_mode=workspace_mode,
                patch_diff=patch_diff,
                verification_summary=verification_summary,
            )

    async def approve_pending(self, pending_id: str, approver: str = "") -> SelfModifyResult:
        row = self._load_pending(pending_id)
        if not row:
            return SelfModifyResult("error", "", "", "", "skipped", "")

        audit_id = uuid.uuid4().hex
        change_key = pending_id
        rel_path = str(row["file_path"])
        backup_ref = str(row["backup_ref"])
        change_description = str(row["change_description"])
        session_id = str(row["session_id"])
        modified = str(row["modified_code"])
        original = str(row["original_code"])
        workspace = create_isolated_patch_workspace(
            project_root=PROJECT_ROOT,
            relative_path=rel_path,
            original_code=original,
            modified_code=modified,
            change_description=change_description,
            session_id=session_id,
        )
        workspace_mode = workspace.mode
        patch_diff = workspace.diff_path.read_text(encoding="utf-8")
        verification_summary = ""
        canary_state = ""
        canary_summary = ""
        try:
            policy = evaluate_self_modification_policy(rel_path)
            if not policy.allowed:
                self._delete_pending(pending_id)
                self._audit_log(audit_id, rel_path, f"{change_description}\n[policy] {policy.reason}", "blocked", backup_ref, session_id)
                self._write_blackboard(rel_path, change_description, "blocked", session_id)
                self._record_change_memory(
                    change_key=change_key,
                    audit_id=audit_id,
                    file_path=rel_path,
                    change_description=change_description,
                    policy_zone=policy.zone_id,
                    risk_level="",
                    risk_reason=policy.reason,
                    test_result="skipped",
                    verification_summary=verification_summary,
                    canary_state=canary_state,
                    canary_summary=canary_summary,
                    outcome_status="blocked",
                    rollback_applied=False,
                    regression_detected=False,
                    workspace_mode=workspace_mode,
                    session_id=session_id,
                )
                return SelfModifyResult(
                    "blocked",
                    rel_path,
                    change_description,
                    backup_ref,
                    "skipped",
                    audit_id,
                    policy_zone=policy.zone_id,
                    workspace_mode=workspace_mode,
                    patch_diff=patch_diff,
                )

            verification = run_self_modification_verification(
                project_root=workspace.root_path,
                relative_path=rel_path,
                policy=policy,
                pytest_runner=self._run_tests,
            )
            test_result = verification.status
            verification_summary = verification.summary
            if test_result == "failed":
                self._delete_pending(pending_id)
                self._audit_log(audit_id, rel_path, change_description, "rolled_back", backup_ref, session_id)
                self._write_blackboard(rel_path, change_description, "rolled_back", session_id)
                self._record_change_memory(
                    change_key=change_key,
                    audit_id=audit_id,
                    file_path=rel_path,
                    change_description=change_description,
                    policy_zone=policy.zone_id,
                    risk_level="",
                    risk_reason="",
                    test_result=test_result,
                    verification_summary=verification_summary,
                    canary_state=canary_state,
                    canary_summary=canary_summary,
                    outcome_status="rolled_back",
                    rollback_applied=True,
                    regression_detected=True,
                    workspace_mode=workspace_mode,
                    session_id=session_id,
                )
                return SelfModifyResult(
                    "rolled_back",
                    rel_path,
                    change_description,
                    backup_ref,
                    test_result,
                    audit_id,
                    policy_zone=policy.zone_id,
                    workspace_mode=workspace_mode,
                    patch_diff=patch_diff,
                    verification_summary=verification_summary,
                )

            promote_isolated_patch(project_root=PROJECT_ROOT, workspace=workspace)
        finally:
            cleanup_isolated_patch_workspace(project_root=PROJECT_ROOT, workspace=workspace)

        canary = run_self_modification_canary(
            project_root=PROJECT_ROOT,
            relative_path=rel_path,
            policy=policy,
            pytest_runner=self._run_tests,
        )
        canary_state = canary.state
        canary_summary = canary.summary
        if canary.rollback_required:
            self._rollback(rel_path, backup_ref)
            self._delete_pending(pending_id)
            self._audit_log(audit_id, rel_path, f"{change_description}\n[canary] {canary_summary}", "rolled_back", backup_ref, session_id)
            self._write_blackboard(rel_path, change_description, "rolled_back", session_id)
            self._record_change_memory(
                change_key=change_key,
                audit_id=audit_id,
                file_path=rel_path,
                change_description=change_description,
                policy_zone=policy.zone_id,
                risk_level="",
                risk_reason="",
                test_result="failed",
                verification_summary=verification_summary,
                canary_state=canary_state,
                canary_summary=canary_summary,
                outcome_status="rolled_back",
                rollback_applied=True,
                regression_detected=True,
                workspace_mode=workspace_mode,
                session_id=session_id,
            )
            return SelfModifyResult(
                "rolled_back",
                rel_path,
                change_description,
                backup_ref,
                "failed",
                audit_id,
                policy_zone=policy.zone_id,
                workspace_mode=workspace_mode,
                patch_diff=patch_diff,
                verification_summary=verification_summary,
                canary_state=canary_state,
                canary_summary=canary_summary,
            )

        self._delete_pending(pending_id)
        self._audit_log(audit_id, rel_path, change_description, "success", backup_ref, session_id)
        self._write_blackboard(rel_path, change_description, "success", session_id)
        self._record_change_memory(
            change_key=change_key,
            audit_id=audit_id,
            file_path=rel_path,
            change_description=change_description,
            policy_zone=policy.zone_id,
            risk_level="",
            risk_reason="",
            test_result=test_result,
            verification_summary=verification_summary,
            canary_state=canary_state,
            canary_summary=canary_summary,
            outcome_status="success",
            rollback_applied=False,
            regression_detected=False,
            workspace_mode=workspace_mode,
            session_id=session_id,
        )
        return SelfModifyResult(
            "success",
            rel_path,
            change_description,
            backup_ref,
            test_result,
            audit_id,
            policy_zone=policy.zone_id,
            workspace_mode=workspace_mode,
            patch_diff=patch_diff,
            verification_summary=verification_summary,
            canary_state=canary_state,
            canary_summary=canary_summary,
        )

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
        self._record_change_memory(
            change_key=pending_id,
            audit_id=audit_id,
            file_path=rel_path,
            change_description=change_description,
            policy_zone="",
            risk_level="",
            risk_reason="rejected_by_approver",
            test_result="skipped",
            verification_summary="",
            canary_state="",
            canary_summary="",
            outcome_status="blocked",
            rollback_applied=False,
            regression_detected=False,
            workspace_mode="",
            session_id=session_id,
        )
        return SelfModifyResult("blocked", rel_path, change_description, backup_ref, "skipped", audit_id)

    def execute_self_hardening_fix(
        self,
        *,
        source_id: str,
        file_path: str,
        change_description: str,
        change_type: str = "auto",
        pattern_name: str = "",
        component: str = "",
        requested_fix_mode: str = "",
        rollout_stage: str = "",
        rollout_reason: str = "",
        required_checks: tuple[str, ...] | list[str] = (),
        required_test_targets: tuple[str, ...] | list[str] = (),
        session_id: str = "",
    ) -> SelfModifyResult:
        safe_source_id = str(source_id or "").strip() or uuid.uuid4().hex
        safe_file_path = str(file_path or "").strip()
        safe_description = str(change_description or "").strip()
        safe_change_type = str(change_type or "auto").strip() or "auto"
        safe_pattern_name = str(pattern_name or "").strip()
        safe_component = str(component or "").strip()
        safe_requested_fix_mode = str(requested_fix_mode or "").strip()
        safe_rollout_stage = str(rollout_stage or "").strip()
        safe_rollout_reason = str(rollout_reason or "").strip()
        safe_required_checks = tuple(str(item or "").strip() for item in required_checks if str(item or "").strip())
        safe_required_test_targets = tuple(
            str(item or "").strip() for item in required_test_targets if str(item or "").strip()
        )
        safe_session_id = str(session_id or "").strip() or f"m18:{safe_source_id[:12]}"
        try:
            from orchestration.task_queue import get_queue

            record_self_hardening_event(
                queue=get_queue(),
                stage="self_modify_started",
                status="active",
                pattern_name=safe_pattern_name,
                component=safe_component,
                requested_fix_mode=safe_requested_fix_mode,
                reason="runner_autofix",
                rollout_stage=safe_rollout_stage,
                rollout_reason=safe_rollout_reason,
                task_id=safe_source_id,
                target_file_path=safe_file_path,
                change_type=safe_change_type,
                required_checks=list(safe_required_checks),
                required_test_targets=list(safe_required_test_targets),
                verification_status="running",
                increment_metrics={"self_modify_attempts_total": 1},
            )
        except Exception:
            pass

        self._set_autonomous_source_state(
            "self_hardening",
            safe_source_id,
            status="claimed",
            file_path=safe_file_path,
            note=safe_description[:240],
        )
        result = self._run_async_sync(
            self.modify_file(
                safe_file_path,
                safe_description,
                change_type=safe_change_type,
                require_tests=True,
                session_id=safe_session_id,
            )
        )
        self._set_autonomous_source_state(
            "self_hardening",
            safe_source_id,
            status=result.status,
            file_path=result.file_path or safe_file_path,
            audit_id=result.audit_id,
            note=result.risk_reason or result.verification_summary or result.canary_summary,
        )
        try:
            from orchestration.task_queue import get_queue

            record_self_hardening_event(
                queue=get_queue(),
                stage="self_modify_finished",
                status=result.status,
                pattern_name=safe_pattern_name,
                component=safe_component,
                requested_fix_mode=safe_requested_fix_mode,
                reason=result.risk_reason or result.verification_summary or result.canary_summary,
                rollout_stage=safe_rollout_stage,
                rollout_reason=safe_rollout_reason,
                task_id=safe_source_id,
                target_file_path=result.file_path or safe_file_path,
                change_type=safe_change_type,
                required_checks=list(safe_required_checks),
                required_test_targets=list(safe_required_test_targets),
                test_result=result.test_result,
                canary_state=result.canary_state,
                canary_summary=result.canary_summary,
                verification_summary=result.verification_summary,
                audit_id=result.audit_id,
                increment_metrics={
                    "self_modify_successes_total": 1 if result.status == "success" else 0,
                    "self_modify_pending_approval_total": 1 if result.status == "pending_approval" else 0,
                    "self_modify_blocked_total": 1 if result.status == "blocked" else 0,
                    "self_modify_rolled_back_total": 1 if result.status == "rolled_back" else 0,
                    "self_modify_errors_total": 1 if result.status == "error" else 0,
                },
            )
        except Exception:
            pass
        return result

    def run_cycle(self) -> Dict[str, Any]:
        if not _env_bool("AUTONOMY_SELF_MODIFY_ENABLED", False):
            return {"status": "disabled", "applied": 0, "pending": self.pending_count()}
        from orchestration.self_improvement_engine import get_improvement_engine
        from orchestration.self_stabilization_gate import evaluate_self_stabilization_gate
        from orchestration.task_queue import get_queue

        queue = get_queue()
        configured_max = _env_int("SELF_MODIFY_MAX_PER_CYCLE", 3)
        max_pending = _env_int("SELF_MODIFY_MAX_PENDING_APPROVALS", 4)
        pending = self.pending_count()

        healing_metrics = queue.get_self_healing_metrics() or {}
        resource_guard = queue.get_self_healing_runtime_state("resource_guard") or {}
        breaker_metrics = queue.get_self_healing_circuit_breaker_metrics() or {}
        self_healing_payload = {
            "incidents": [],
            "degrade_mode": str(healing_metrics.get("degrade_mode", "normal") or "normal"),
            "open_incidents": int(healing_metrics.get("open_incidents", 0) or 0),
            "resource_guard_state": str(resource_guard.get("state_value", "inactive") or "inactive"),
            "circuit_breakers_open": int(breaker_metrics.get("open_breakers", 0) or 0),
            "open_breakers": [str(item.get("breaker_key") or "") for item in (breaker_metrics.get("top_tripped") or []) if str(item.get("breaker_key") or "").strip()],
        }
        stability_gate = evaluate_self_stabilization_gate(self_healing_payload)
        ops_gate_state = str((queue.get_policy_runtime_state("scorecard_ops_gate_state") or {}).get("state_value", "unknown") or "unknown")
        e2e_gate_state = str((queue.get_policy_runtime_state("scorecard_e2e_gate_state") or {}).get("state_value", "unknown") or "unknown")
        strict_force_off = str((queue.get_policy_runtime_state("strict_force_off") or {}).get("state_value", "false") or "false").strip().lower() == "true"
        memory_summary = self.summarize_change_memory(limit=25)
        controller = evaluate_self_modification_controller(
            stability_gate_state=str(stability_gate.get("state", "unknown") or "unknown"),
            ops_gate_state=ops_gate_state,
            e2e_gate_state=e2e_gate_state,
            strict_force_off=strict_force_off,
            pending_approvals=pending,
            rollback_count_recent=memory_summary.rollback_count,
            regression_count_recent=memory_summary.regression_count,
            configured_max_per_cycle=configured_max,
            max_pending_approvals=max_pending,
        )

        summary: Dict[str, Any] = {
            "status": "enabled",
            "controller_state": controller.state,
            "controller_reasons": list(controller.reasons),
            "applied": 0,
            "pending": pending,
            "attempted": 0,
            "blocked": 0,
            "max_per_cycle": controller.max_apply_count,
            "candidates_considered": 0,
            "selected_candidates": [],
        }
        if not controller.allow_autonomous_apply:
            return summary

        improvement_engine = get_improvement_engine(self.db_path)
        suggestions = improvement_engine.get_suggestions(applied=False)
        reserved = self._list_autonomous_source_ids(states=("claimed", "pending_approval", "applied"))
        candidates = build_autonomous_self_modification_candidates(
            suggestions,
            reserved_source_ids=reserved,
        )
        summary["candidates_considered"] = len(candidates)
        if not candidates:
            return summary

        selected = candidates[: max(0, int(controller.max_apply_count))]
        summary["selected_candidates"] = [
            {
                "source_id": candidate.source_id,
                "file_path": candidate.file_path,
                "change_type": candidate.change_type,
                "priority": candidate.priority,
            }
            for candidate in selected
        ]

        for candidate in selected:
            self._set_autonomous_source_state(
                candidate.source_kind,
                candidate.source_id,
                status="claimed",
                file_path=candidate.file_path,
                note=candidate.change_description[:240],
            )
            result = self._run_async_sync(
                self.modify_file(
                    candidate.file_path,
                    candidate.change_description,
                    change_type=candidate.change_type,
                    require_tests=True,
                    session_id=f"sm7:{candidate.source_id}",
                )
            )
            summary["attempted"] += 1
            self._set_autonomous_source_state(
                candidate.source_kind,
                candidate.source_id,
                status=result.status,
                file_path=candidate.file_path,
                audit_id=result.audit_id,
                note=result.risk_reason or result.verification_summary or result.canary_summary,
            )
            if result.status == "success":
                improvement_engine.mark_suggestion_applied(candidate.source_id, True)
                summary["applied"] += 1
            elif result.status == "pending_approval":
                improvement_engine.mark_suggestion_applied(candidate.source_id, True)
                summary["pending"] += 1
            elif result.status == "blocked":
                summary["blocked"] += 1

        return summary

    def pending_count(self) -> int:
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM self_modify_pending").fetchone()
        return int((row or [0])[0] or 0)

    def list_change_memory(self, limit: int = 50) -> list[dict[str, Any]]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM self_modify_change_memory ORDER BY updated_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def summarize_change_memory(self, limit: int = 100) -> SelfModificationChangeMemorySummary:
        rows = self.list_change_memory(limit=limit)
        counts: dict[str, int] = {
            "success": 0,
            "rolled_back": 0,
            "blocked": 0,
            "pending_approval": 0,
            "error": 0,
        }
        rollback_count = 0
        regression_count = 0
        for row in rows:
            status = str(row.get("outcome_status") or "")
            if status in counts:
                counts[status] += 1
            rollback_count += 1 if int(row.get("rollback_applied") or 0) else 0
            regression_count += 1 if int(row.get("regression_detected") or 0) else 0
        return SelfModificationChangeMemorySummary(
            total=len(rows),
            success_count=counts["success"],
            rolled_back_count=counts["rolled_back"],
            blocked_count=counts["blocked"],
            pending_approval_count=counts["pending_approval"],
            error_count=counts["error"],
            rollback_count=rollback_count,
            regression_count=regression_count,
        )

    def _run_async_sync(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result_box: dict[str, Any] = {"value": None}
        error_box: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result_box["value"] = asyncio.run(coro)
            except BaseException as exc:  # pragma: no cover - defensive thread handoff
                error_box["error"] = exc

        worker = threading.Thread(
            target=_runner,
            name="self-modifier-run-cycle",
            daemon=True,
        )
        worker.start()
        worker.join(timeout=max(10, _env_int("SELF_MODIFY_SYNC_TIMEOUT_SEC", 120)))
        if worker.is_alive():
            raise TimeoutError("SelfModifierEngine.run_cycle timed out waiting for async patch apply")
        if error_box:
            raise RuntimeError("SelfModifierEngine.run_cycle async apply failed") from error_box["error"]
        return result_box["value"]

    def _list_autonomous_source_ids(self, *, states: tuple[str, ...]) -> set[str]:
        normalized_states = tuple(str(item or "").strip() for item in states if str(item or "").strip())
        if not normalized_states:
            return set()
        encoded_states = json.dumps(list(normalized_states), ensure_ascii=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT source_id
                FROM self_modify_autonomous_source_state
                WHERE status IN (SELECT value FROM json_each(?))
                """,
                (encoded_states,),
            ).fetchall()
        return {str((row or [""])[0] or "").strip() for row in rows if str((row or [""])[0] or "").strip()}

    def _set_autonomous_source_state(
        self,
        source_kind: str,
        source_id: str,
        *,
        status: str,
        file_path: str = "",
        audit_id: str = "",
        note: str = "",
    ) -> None:
        safe_kind = str(source_kind or "").strip()
        safe_id = str(source_id or "").strip()
        if not safe_kind or not safe_id:
            return
        now = datetime.now().isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO self_modify_autonomous_source_state
                    (source_kind, source_id, status, file_path, audit_id, note, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_kind, source_id) DO UPDATE SET
                    status=excluded.status,
                    file_path=excluded.file_path,
                    audit_id=excluded.audit_id,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """,
                (
                    safe_kind,
                    safe_id,
                    str(status or "").strip() or "unknown",
                    str(file_path or ""),
                    str(audit_id or ""),
                    str(note or "")[:500],
                    now,
                ),
            )
            conn.commit()

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

    def _find_test_file(self, changed_file: str, project_root: Path = PROJECT_ROOT) -> str:
        path = Path(changed_file)
        stem = path.stem
        parent_name = path.parent.name
        candidates = [
            project_root / "tests" / f"test_{parent_name}.py",
            project_root / "tests" / f"test_{parent_name}s.py",
            project_root / "tests" / f"test_{stem}.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return ""

    def _run_tests(self, file_path: str, policy_test_targets: tuple[str, ...] = (), project_root: Path = PROJECT_ROOT) -> str:
        test_targets = [target for target in policy_test_targets if str(target).strip()]
        if not test_targets:
            test_file = self._find_test_file(file_path, project_root=project_root)
            if not test_file:
                return "skipped"
            test_targets = [test_file]
        import subprocess

        result = subprocess.run(
            ["python", "-m", "pytest", *test_targets, "-x", "-q"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=180,
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

    def _record_change_memory(
        self,
        *,
        change_key: str,
        audit_id: str,
        file_path: str,
        change_description: str,
        policy_zone: str,
        risk_level: str,
        risk_reason: str,
        test_result: str,
        verification_summary: str,
        canary_state: str,
        canary_summary: str,
        outcome_status: str,
        rollback_applied: bool,
        regression_detected: bool,
        workspace_mode: str,
        session_id: str,
    ) -> None:
        now_iso = datetime.utcnow().isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT created_at FROM self_modify_change_memory WHERE change_key = ?",
                (change_key,),
            ).fetchone()
            created_at = str((row or [now_iso])[0] or now_iso)
            conn.execute(
                """
                INSERT OR REPLACE INTO self_modify_change_memory (
                    change_key, audit_id, file_path, change_description, policy_zone, risk_level, risk_reason,
                    test_result, verification_summary, canary_state, canary_summary, outcome_status,
                    rollback_applied, regression_detected, workspace_mode, session_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change_key,
                    audit_id,
                    file_path,
                    change_description,
                    policy_zone,
                    risk_level,
                    risk_reason,
                    test_result,
                    verification_summary,
                    canary_state,
                    canary_summary,
                    outcome_status,
                    1 if rollback_applied else 0,
                    1 if regression_detected else 0,
                    workspace_mode,
                    session_id,
                    created_at,
                    now_iso,
                ),
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
        risk_level: str = "",
        risk_reason: str = "",
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
            f"Risiko: `{risk_level or 'unknown'}` ({risk_reason or 'n/a'})\n\n"
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

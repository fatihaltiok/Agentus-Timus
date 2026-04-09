"""Phase D2 pending approval/auth workflow state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from orchestration.approval_auth_contract import normalize_phase_d_workflow_payload


_SCHEMA_VERSION = 1
_PENDING_STATUSES = {
    "approval_required",
    "auth_required",
    "awaiting_user",
    "challenge_required",
}


def _clean_text(value: Any, *, limit: int = 280) -> str:
    return str(value or "").strip()[:limit]


@dataclass(frozen=True, slots=True)
class PendingWorkflowState:
    schema_version: int
    workflow_id: str
    workflow_kind: str
    status: str
    service: str
    platform: str
    url: str
    reason: str
    message: str
    user_action_required: str
    resume_hint: str
    challenge_type: str
    approval_scope: str
    source_agent: str
    source_stage: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "workflow_kind": self.workflow_kind,
            "status": self.status,
            "service": self.service,
            "platform": self.platform,
            "url": self.url,
            "reason": self.reason,
            "message": self.message,
            "user_action_required": self.user_action_required,
            "resume_hint": self.resume_hint,
            "challenge_type": self.challenge_type,
            "approval_scope": self.approval_scope,
            "source_agent": self.source_agent,
            "source_stage": self.source_stage,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def normalize_pending_workflow_state(
    payload: Mapping[str, Any] | None,
    *,
    updated_at: str = "",
    source_agent: str = "",
    source_stage: str = "",
) -> PendingWorkflowState | None:
    if not isinstance(payload, Mapping):
        return None
    normalized = normalize_phase_d_workflow_payload(payload)
    status = str(normalized.get("status") or "").strip().lower()
    if status not in _PENDING_STATUSES:
        return None

    created_at = (
        _clean_text(payload.get("created_at"), limit=80)
        or _clean_text(payload.get("pending_since"), limit=80)
        or _clean_text(updated_at, limit=80)
    )
    updated = _clean_text(updated_at or payload.get("updated_at"), limit=80) or created_at

    return PendingWorkflowState(
        schema_version=_SCHEMA_VERSION,
        workflow_id=_clean_text(normalized.get("workflow_id"), limit=64),
        workflow_kind=_clean_text(normalized.get("workflow_kind"), limit=64),
        status=status,
        service=_clean_text(normalized.get("service"), limit=64),
        platform=_clean_text(normalized.get("platform"), limit=64),
        url=_clean_text(normalized.get("url"), limit=500),
        reason=_clean_text(normalized.get("reason"), limit=96),
        message=_clean_text(normalized.get("message")),
        user_action_required=_clean_text(normalized.get("user_action_required")),
        resume_hint=_clean_text(normalized.get("resume_hint")),
        challenge_type=_clean_text(normalized.get("challenge_type"), limit=64),
        approval_scope=_clean_text(normalized.get("approval_scope"), limit=64),
        source_agent=_clean_text(payload.get("source_agent") or source_agent, limit=64),
        source_stage=_clean_text(payload.get("source_stage") or source_stage, limit=96),
        created_at=created_at,
        updated_at=updated,
    )


def pending_workflow_state_to_dict(
    payload: Mapping[str, Any] | None,
    *,
    updated_at: str = "",
    source_agent: str = "",
    source_stage: str = "",
) -> dict[str, Any]:
    normalized = normalize_pending_workflow_state(
        payload,
        updated_at=updated_at,
        source_agent=source_agent,
        source_stage=source_stage,
    )
    return normalized.to_dict() if normalized else {}


def is_pending_workflow_state(payload: Mapping[str, Any] | None) -> bool:
    return normalize_pending_workflow_state(payload) is not None


def clear_pending_workflow_state() -> dict[str, Any]:
    return {}

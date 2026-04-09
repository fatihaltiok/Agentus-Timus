"""Shared Phase D approval/auth/user-handover contract."""

from __future__ import annotations

from typing import Any, Mapping
import uuid


PHASE_D_WORKFLOW_SCHEMA_VERSION = 1

PHASE_D_WORKFLOW_STATUSES = (
    "in_progress",
    "approval_required",
    "auth_required",
    "awaiting_user",
    "challenge_required",
    "completed",
    "blocked",
    "error",
)

_KNOWN_STATUSES = set(PHASE_D_WORKFLOW_STATUSES)
_SERVICE_ALIASES = {
    "twitter": "x",
}


def _clean_text(value: Any, *, limit: int = 220) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def new_phase_d_workflow_id() -> str:
    return f"wf_{uuid.uuid4().hex[:12]}"


def _service_from_platform(platform: Any) -> str:
    normalized = str(platform or "").strip().lower()
    if not normalized:
        return ""
    return _SERVICE_ALIASES.get(normalized, normalized)


def _default_reason(status: str) -> str:
    if status == "approval_required":
        return "approval_required"
    if status == "auth_required":
        return "login_wall"
    if status == "awaiting_user":
        return "user_action_required"
    if status == "challenge_required":
        return "security_challenge"
    return status or "workflow_update"


def _default_message(status: str, *, service: str = "") -> str:
    service_label = str(service or "der Dienst").strip()
    if status == "approval_required":
        return f"Timus braucht deine Freigabe fuer einen sensiblen Zugriff bei {service_label}."
    if status == "auth_required":
        return f"{service_label} liefert ohne Login nur unvollstaendige oder unlesbare Inhalte."
    if status == "awaiting_user":
        return "Bitte fuehre den erforderlichen Nutzerschritt selbst aus."
    if status == "challenge_required":
        return f"{service_label} verlangt eine Sicherheitspruefung."
    if status == "blocked":
        return "Der Workflow ist aktuell blockiert."
    if status == "error":
        return "Im Workflow ist ein Fehler aufgetreten."
    return "Workflow-Status aktualisiert."


def _infer_status(payload: Mapping[str, Any], *, default_status: str = "") -> str:
    status = str(payload.get("status") or "").strip().lower()
    if status in _KNOWN_STATUSES:
        return status
    if bool(payload.get("approval_required")):
        return "approval_required"
    if bool(payload.get("auth_required")):
        return "auth_required"
    if bool(payload.get("challenge_required")) or str(payload.get("challenge_type") or "").strip():
        return "challenge_required"
    if bool(payload.get("awaiting_user")):
        return "awaiting_user"
    if str(payload.get("user_action_required") or "").strip():
        return "awaiting_user"
    fallback = str(default_status or "").strip().lower()
    if fallback in _KNOWN_STATUSES:
        return fallback
    return ""


def normalize_phase_d_workflow_payload(
    raw: Mapping[str, Any] | None,
    *,
    default_status: str = "",
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}

    loaded = dict(raw)
    status = _infer_status(loaded, default_status=default_status)
    if not status:
        return {}

    platform = _clean_text(loaded.get("platform"), limit=64).lower()
    service = _clean_text(loaded.get("service"), limit=64).lower() or _service_from_platform(platform)
    workflow_id = _clean_text(loaded.get("workflow_id"), limit=64) or new_phase_d_workflow_id()
    workflow_kind = _clean_text(loaded.get("workflow_kind"), limit=64) or "assistive_action"
    reason = _clean_text(loaded.get("reason"), limit=96) or _default_reason(status)
    message = (
        _clean_text(loaded.get("message"))
        or _clean_text(loaded.get("error"))
        or _default_message(status, service=service or platform or "der Dienst")
    )
    user_action_required = _clean_text(loaded.get("user_action_required"))
    resume_hint = _clean_text(loaded.get("resume_hint"))
    challenge_type = _clean_text(loaded.get("challenge_type"), limit=64).lower()
    approval_scope = _clean_text(loaded.get("approval_scope"), limit=64).lower()
    step = _clean_text(loaded.get("step"), limit=64).lower()
    url = _clean_text(loaded.get("url"), limit=500)

    return {
        "schema_version": PHASE_D_WORKFLOW_SCHEMA_VERSION,
        "status": status,
        "workflow_id": workflow_id,
        "workflow_kind": workflow_kind,
        "service": service,
        "platform": platform,
        "url": url,
        "reason": reason,
        "message": message,
        "error": _clean_text(loaded.get("error")) or message,
        "user_action_required": user_action_required,
        "resume_hint": resume_hint,
        "challenge_type": challenge_type,
        "approval_scope": approval_scope,
        "step": step,
        "approval_required": status == "approval_required",
        "auth_required": status == "auth_required",
        "awaiting_user": status == "awaiting_user",
        "challenge_required": status == "challenge_required",
    }


def build_auth_required_workflow_payload(
    *,
    url: str,
    platform: str = "",
    workflow_id: str = "",
    reason: str = "login_wall",
    message: str = "",
    user_action_required: str = "",
) -> dict[str, Any]:
    return normalize_phase_d_workflow_payload(
        {
            "status": "auth_required",
            "workflow_id": workflow_id,
            "workflow_kind": "assistive_action",
            "url": url,
            "platform": platform,
            "service": _service_from_platform(platform),
            "reason": reason,
            "message": message,
            "user_action_required": user_action_required,
        },
        default_status="auth_required",
    )


def build_approval_required_workflow_payload(
    *,
    service: str = "",
    workflow_id: str = "",
    reason: str = "approval_required",
    message: str = "",
    user_action_required: str = "",
    approval_scope: str = "",
) -> dict[str, Any]:
    return normalize_phase_d_workflow_payload(
        {
            "status": "approval_required",
            "workflow_id": workflow_id,
            "workflow_kind": "assistive_action",
            "service": service,
            "reason": reason,
            "message": message,
            "user_action_required": user_action_required,
            "approval_scope": approval_scope,
        },
        default_status="approval_required",
    )


def build_awaiting_user_workflow_payload(
    *,
    service: str = "",
    workflow_id: str = "",
    step: str = "",
    message: str = "",
    resume_hint: str = "",
    user_action_required: str = "",
) -> dict[str, Any]:
    return normalize_phase_d_workflow_payload(
        {
            "status": "awaiting_user",
            "workflow_id": workflow_id,
            "workflow_kind": "assistive_action",
            "service": service,
            "step": step,
            "message": message,
            "resume_hint": resume_hint,
            "user_action_required": user_action_required,
        },
        default_status="awaiting_user",
    )


def build_challenge_required_workflow_payload(
    *,
    service: str = "",
    workflow_id: str = "",
    challenge_type: str = "",
    message: str = "",
    user_action_required: str = "",
) -> dict[str, Any]:
    return normalize_phase_d_workflow_payload(
        {
            "status": "challenge_required",
            "workflow_id": workflow_id,
            "workflow_kind": "assistive_action",
            "service": service,
            "challenge_type": challenge_type,
            "message": message,
            "user_action_required": user_action_required,
        },
        default_status="challenge_required",
    )


def derive_user_action_blocker_reason(payload: Mapping[str, Any] | None) -> str:
    normalized = normalize_phase_d_workflow_payload(payload)
    status = str(normalized.get("status") or "").strip().lower()
    if status == "approval_required":
        return "approval_required"
    if status == "auth_required":
        return "auth_required"
    if status == "challenge_required":
        return "challenge_required"
    if status == "awaiting_user":
        return "user_action_required"
    return "blocked"

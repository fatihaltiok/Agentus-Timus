"""C4 transport contract for long-running user-visible runs.

This module defines the stable event envelope for progress/blocker/partial
signals that can later be transported via SSE, Telegram, or other user-facing
channels. It intentionally does not perform any transport by itself.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Literal, Mapping, TypedDict
import uuid


SCHEMA_VERSION = 1

LongRunEventType = Literal[
    "run_started",
    "progress",
    "partial_result",
    "blocker",
    "run_completed",
    "run_failed",
]

_ALLOWED_EVENT_TYPES = {
    "run_started",
    "progress",
    "partial_result",
    "blocker",
    "run_completed",
    "run_failed",
}
_TERMINAL_EVENT_TYPES = {"run_completed", "run_failed"}
_RUN_ID_VAR: ContextVar[str] = ContextVar("timus_longrun_run_id", default="")
_RUN_SEQ_VAR: ContextVar[int] = ContextVar("timus_longrun_seq", default=0)


class LongRunTransportEventDict(TypedDict, total=False):
    type: str
    schema_version: int
    request_id: str
    run_id: str
    session_id: str
    agent: str
    stage: str
    ts: str
    seq: int
    message: str
    progress_hint: str
    next_expected_update_s: int
    content_preview: str
    is_final: bool
    blocker_reason: str
    user_action_required: str
    workflow_id: str
    workflow_status: str
    workflow_service: str
    workflow_reason: str
    workflow_message: str
    workflow_resume_hint: str
    workflow_challenge_type: str
    workflow_approval_scope: str
    error_class: str
    error_code: str


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def get_current_run_id() -> str:
    return str(_RUN_ID_VAR.get("") or "").strip()


def next_event_seq() -> int:
    current = max(0, int(_RUN_SEQ_VAR.get(0)))
    current += 1
    _RUN_SEQ_VAR.set(current)
    return current


@contextmanager
def bind_longrun_context(*, run_id: str = "") -> Iterator[dict[str, Any]]:
    clean_run_id = str(run_id or new_run_id()).strip()
    run_token = _RUN_ID_VAR.set(clean_run_id)
    seq_token = _RUN_SEQ_VAR.set(0)
    try:
        yield {"run_id": clean_run_id}
    finally:
        _RUN_ID_VAR.reset(run_token)
        _RUN_SEQ_VAR.reset(seq_token)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_terminal_event_type(event_type: str) -> bool:
    return str(event_type or "").strip() in _TERMINAL_EVENT_TYPES


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class LongRunTransportEvent:
    type: str
    request_id: str
    run_id: str
    agent: str
    stage: str
    seq: int
    session_id: str = ""
    ts: str = ""
    message: str = ""
    progress_hint: str = ""
    next_expected_update_s: int = 0
    content_preview: str = ""
    is_final: bool = False
    blocker_reason: str = ""
    user_action_required: str = ""
    workflow_id: str = ""
    workflow_status: str = ""
    workflow_service: str = ""
    workflow_reason: str = ""
    workflow_message: str = ""
    workflow_resume_hint: str = ""
    workflow_challenge_type: str = ""
    workflow_approval_scope: str = ""
    error_class: str = ""
    error_code: str = ""
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _normalized_text(self.type))
        object.__setattr__(self, "request_id", _normalized_text(self.request_id))
        object.__setattr__(self, "run_id", _normalized_text(self.run_id))
        object.__setattr__(self, "session_id", _normalized_text(self.session_id))
        object.__setattr__(self, "agent", _normalized_text(self.agent))
        object.__setattr__(self, "stage", _normalized_text(self.stage))
        object.__setattr__(self, "ts", _normalized_text(self.ts) or utc_now_iso())
        object.__setattr__(self, "message", _normalized_text(self.message))
        object.__setattr__(self, "progress_hint", _normalized_text(self.progress_hint))
        object.__setattr__(self, "content_preview", _normalized_text(self.content_preview))
        object.__setattr__(self, "blocker_reason", _normalized_text(self.blocker_reason))
        object.__setattr__(self, "user_action_required", _normalized_text(self.user_action_required))
        object.__setattr__(self, "workflow_id", _normalized_text(self.workflow_id))
        object.__setattr__(self, "workflow_status", _normalized_text(self.workflow_status))
        object.__setattr__(self, "workflow_service", _normalized_text(self.workflow_service))
        object.__setattr__(self, "workflow_reason", _normalized_text(self.workflow_reason))
        object.__setattr__(self, "workflow_message", _normalized_text(self.workflow_message))
        object.__setattr__(self, "workflow_resume_hint", _normalized_text(self.workflow_resume_hint))
        object.__setattr__(self, "workflow_challenge_type", _normalized_text(self.workflow_challenge_type))
        object.__setattr__(self, "workflow_approval_scope", _normalized_text(self.workflow_approval_scope))
        object.__setattr__(self, "error_class", _normalized_text(self.error_class))
        object.__setattr__(self, "error_code", _normalized_text(self.error_code))
        object.__setattr__(self, "seq", max(0, int(self.seq)))
        object.__setattr__(self, "next_expected_update_s", max(0, int(self.next_expected_update_s)))
        self._validate()

    def _validate(self) -> None:
        if self.type not in _ALLOWED_EVENT_TYPES:
            raise ValueError(f"unsupported_longrun_event_type:{self.type}")
        if not self.request_id:
            raise ValueError("missing_request_id")
        if not self.run_id:
            raise ValueError("missing_run_id")
        if not self.agent:
            raise ValueError("missing_agent")
        if not self.stage:
            raise ValueError("missing_stage")
        if not self.message:
            raise ValueError("missing_message")

        if self.type == "partial_result":
            if not self.content_preview:
                raise ValueError("partial_result_requires_content_preview")
            if self.is_final:
                raise ValueError("partial_result_must_not_be_final")

        if self.type == "blocker" and not self.blocker_reason:
            raise ValueError("blocker_requires_reason")

        if self.type == "run_failed" and not (self.error_class or self.error_code):
            raise ValueError("run_failed_requires_error_metadata")

    def to_dict(self) -> LongRunTransportEventDict:
        return asdict(self)


def validate_transport_event(payload: Mapping[str, Any]) -> LongRunTransportEvent:
    return LongRunTransportEvent(
        type=str(payload.get("type") or ""),
        schema_version=int(payload.get("schema_version") or SCHEMA_VERSION),
        request_id=str(payload.get("request_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        agent=str(payload.get("agent") or ""),
        stage=str(payload.get("stage") or ""),
        ts=str(payload.get("ts") or ""),
        seq=int(payload.get("seq") or 0),
        message=str(payload.get("message") or ""),
        progress_hint=str(payload.get("progress_hint") or ""),
        next_expected_update_s=int(payload.get("next_expected_update_s") or 0),
        content_preview=str(payload.get("content_preview") or ""),
        is_final=bool(payload.get("is_final", False)),
        blocker_reason=str(payload.get("blocker_reason") or ""),
        user_action_required=str(payload.get("user_action_required") or ""),
        workflow_id=str(payload.get("workflow_id") or ""),
        workflow_status=str(payload.get("workflow_status") or ""),
        workflow_service=str(payload.get("workflow_service") or ""),
        workflow_reason=str(payload.get("workflow_reason") or ""),
        workflow_message=str(payload.get("workflow_message") or ""),
        workflow_resume_hint=str(payload.get("workflow_resume_hint") or ""),
        workflow_challenge_type=str(payload.get("workflow_challenge_type") or ""),
        workflow_approval_scope=str(payload.get("workflow_approval_scope") or ""),
        error_class=str(payload.get("error_class") or ""),
        error_code=str(payload.get("error_code") or ""),
    )


def make_transport_event(
    *,
    event_type: LongRunEventType,
    request_id: str,
    run_id: str,
    session_id: str,
    agent: str,
    stage: str,
    seq: int,
    message: str,
    progress_hint: str = "",
    next_expected_update_s: int = 0,
    content_preview: str = "",
    is_final: bool = False,
    blocker_reason: str = "",
    user_action_required: str = "",
    workflow_id: str = "",
    workflow_status: str = "",
    workflow_service: str = "",
    workflow_reason: str = "",
    workflow_message: str = "",
    workflow_resume_hint: str = "",
    workflow_challenge_type: str = "",
    workflow_approval_scope: str = "",
    error_class: str = "",
    error_code: str = "",
    ts: str = "",
) -> LongRunTransportEvent:
    return LongRunTransportEvent(
        type=event_type,
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        agent=agent,
        stage=stage,
        seq=seq,
        ts=ts,
        message=message,
        progress_hint=progress_hint,
        next_expected_update_s=next_expected_update_s,
        content_preview=content_preview,
        is_final=is_final,
        blocker_reason=blocker_reason,
        user_action_required=user_action_required,
        workflow_id=workflow_id,
        workflow_status=workflow_status,
        workflow_service=workflow_service,
        workflow_reason=workflow_reason,
        workflow_message=workflow_message,
        workflow_resume_hint=workflow_resume_hint,
        workflow_challenge_type=workflow_challenge_type,
        workflow_approval_scope=workflow_approval_scope,
        error_class=error_class,
        error_code=error_code,
    )


def make_run_started_event(
    *,
    request_id: str,
    run_id: str,
    session_id: str,
    agent: str,
    seq: int,
    message: str,
) -> LongRunTransportEvent:
    return make_transport_event(
        event_type="run_started",
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        agent=agent,
        stage="started",
        seq=seq,
        message=message,
    )


def make_progress_event(
    *,
    request_id: str,
    run_id: str,
    session_id: str,
    agent: str,
    stage: str,
    seq: int,
    message: str,
    progress_hint: str = "working",
    next_expected_update_s: int = 15,
) -> LongRunTransportEvent:
    return make_transport_event(
        event_type="progress",
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        agent=agent,
        stage=stage,
        seq=seq,
        message=message,
        progress_hint=progress_hint,
        next_expected_update_s=next_expected_update_s,
    )


def make_partial_result_event(
    *,
    request_id: str,
    run_id: str,
    session_id: str,
    agent: str,
    stage: str,
    seq: int,
    message: str,
    content_preview: str,
) -> LongRunTransportEvent:
    return make_transport_event(
        event_type="partial_result",
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        agent=agent,
        stage=stage,
        seq=seq,
        message=message,
        content_preview=content_preview,
        is_final=False,
    )


def make_blocker_event(
    *,
    request_id: str,
    run_id: str,
    session_id: str,
    agent: str,
    stage: str,
    seq: int,
    message: str,
    blocker_reason: str,
    user_action_required: str = "",
    workflow_id: str = "",
    workflow_status: str = "",
    workflow_service: str = "",
    workflow_reason: str = "",
    workflow_message: str = "",
    workflow_resume_hint: str = "",
    workflow_challenge_type: str = "",
    workflow_approval_scope: str = "",
) -> LongRunTransportEvent:
    return make_transport_event(
        event_type="blocker",
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        agent=agent,
        stage=stage,
        seq=seq,
        message=message,
        blocker_reason=blocker_reason,
        user_action_required=user_action_required,
        workflow_id=workflow_id,
        workflow_status=workflow_status,
        workflow_service=workflow_service,
        workflow_reason=workflow_reason,
        workflow_message=workflow_message,
        workflow_resume_hint=workflow_resume_hint,
        workflow_challenge_type=workflow_challenge_type,
        workflow_approval_scope=workflow_approval_scope,
    )


def make_run_completed_event(
    *,
    request_id: str,
    run_id: str,
    session_id: str,
    agent: str,
    seq: int,
    message: str,
) -> LongRunTransportEvent:
    return make_transport_event(
        event_type="run_completed",
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        agent=agent,
        stage="done",
        seq=seq,
        message=message,
    )


def make_run_failed_event(
    *,
    request_id: str,
    run_id: str,
    session_id: str,
    agent: str,
    stage: str,
    seq: int,
    message: str,
    error_class: str = "",
    error_code: str = "",
) -> LongRunTransportEvent:
    return make_transport_event(
        event_type="run_failed",
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        agent=agent,
        stage=stage,
        seq=seq,
        message=message,
        error_class=error_class,
        error_code=error_code,
    )

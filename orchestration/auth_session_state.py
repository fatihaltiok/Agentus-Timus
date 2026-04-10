"""Phase D4 auth session reuse state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


_SCHEMA_VERSION = 1
_ACTIVE_STATUSES = {"authenticated", "session_reused"}
_DEFAULT_SCOPE = "session"
_DEFAULT_TTL_HOURS = 24


def _clean_text(value: Any, *, limit: int = 280) -> str:
    return str(value or "").strip()[:limit]


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _to_iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _infer_service_from_url(url: str) -> str:
    host = str(url or "").strip().lower()
    if not host:
        return ""
    host = host.replace("https://", "").replace("http://", "").split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("x.com") or host.startswith("twitter.com"):
        return "x"
    if "." in host:
        return host.split(".")[-2] if host.count(".") >= 1 else host
    return host


@dataclass(frozen=True, slots=True)
class AuthSessionState:
    schema_version: int
    service: str
    status: str
    scope: str
    url: str
    workflow_id: str
    source_agent: str
    source_stage: str
    reason: str
    browser_session_id: str
    confirmed_at: str
    updated_at: str
    expires_at: str
    reuse_ready: bool
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "service": self.service,
            "status": self.status,
            "scope": self.scope,
            "url": self.url,
            "workflow_id": self.workflow_id,
            "source_agent": self.source_agent,
            "source_stage": self.source_stage,
            "reason": self.reason,
            "browser_session_id": self.browser_session_id,
            "confirmed_at": self.confirmed_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "reuse_ready": self.reuse_ready,
            "evidence": self.evidence,
        }


def normalize_auth_session_entry(
    payload: Mapping[str, Any] | None,
    *,
    session_id: str = "",
    updated_at: str = "",
) -> AuthSessionState | None:
    if not isinstance(payload, Mapping):
        return None

    status = _clean_text(payload.get("status"), limit=64).lower()
    if status not in _ACTIVE_STATUSES:
        return None

    service = _clean_text(payload.get("service"), limit=64).lower()
    url = _clean_text(payload.get("url"), limit=500)
    if not service:
        service = _infer_service_from_url(url)
    if not service:
        return None

    updated_dt = (
        _parse_iso_datetime(updated_at)
        or _parse_iso_datetime(payload.get("updated_at"))
        or datetime.now(timezone.utc)
    )
    confirmed_dt = (
        _parse_iso_datetime(payload.get("confirmed_at"))
        or updated_dt
    )
    expires_dt = (
        _parse_iso_datetime(payload.get("expires_at"))
        or (confirmed_dt + timedelta(hours=_DEFAULT_TTL_HOURS))
    )

    return AuthSessionState(
        schema_version=_SCHEMA_VERSION,
        service=service,
        status=status,
        scope=_clean_text(payload.get("scope"), limit=32).lower() or _DEFAULT_SCOPE,
        url=url,
        workflow_id=_clean_text(payload.get("workflow_id"), limit=64),
        source_agent=_clean_text(payload.get("source_agent"), limit=64),
        source_stage=_clean_text(payload.get("source_stage"), limit=96),
        reason=_clean_text(payload.get("reason"), limit=96) or "login_confirmed",
        browser_session_id=_clean_text(payload.get("browser_session_id") or session_id, limit=96),
        confirmed_at=_to_iso_z(confirmed_dt),
        updated_at=_to_iso_z(updated_dt),
        expires_at=_to_iso_z(expires_dt),
        reuse_ready=bool(payload.get("reuse_ready", True)),
        evidence=_clean_text(payload.get("evidence")),
    )


def is_auth_session_reusable(
    payload: Mapping[str, Any] | None,
    *,
    service: str = "",
    now: str = "",
) -> bool:
    normalized = normalize_auth_session_entry(payload, updated_at=now)
    if not normalized:
        return False
    if not normalized.reuse_ready:
        return False
    if service and normalized.service != str(service or "").strip().lower():
        return False
    expires_dt = _parse_iso_datetime(normalized.expires_at)
    now_dt = _parse_iso_datetime(now) or datetime.now(timezone.utc)
    if expires_dt and expires_dt <= now_dt:
        return False
    return True


def auth_session_index_to_dict(
    payload: Mapping[str, Any] | None,
    *,
    session_id: str = "",
    updated_at: str = "",
) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return {}

    if "service" in payload:
        normalized_single = normalize_auth_session_entry(
            payload,
            session_id=session_id,
            updated_at=updated_at,
        )
        return {normalized_single.service: normalized_single.to_dict()} if normalized_single else {}

    result: dict[str, dict[str, Any]] = {}
    for key, value in payload.items():
        if not isinstance(value, Mapping):
            continue
        normalized = normalize_auth_session_entry(
            value,
            session_id=session_id,
            updated_at=updated_at,
        )
        if normalized:
            result[normalized.service] = normalized.to_dict()
        elif isinstance(key, str):
            normalized_from_key = normalize_auth_session_entry(
                {"service": key, **dict(value)},
                session_id=session_id,
                updated_at=updated_at,
            )
            if normalized_from_key:
                result[normalized_from_key.service] = normalized_from_key.to_dict()
    return result


def upsert_auth_session_index(
    existing: Mapping[str, Any] | None,
    payload: Mapping[str, Any] | None,
    *,
    session_id: str = "",
    updated_at: str = "",
) -> dict[str, dict[str, Any]]:
    index = auth_session_index_to_dict(existing, session_id=session_id, updated_at=updated_at)
    normalized = normalize_auth_session_entry(payload, session_id=session_id, updated_at=updated_at)
    if not normalized:
        return index
    index[normalized.service] = normalized.to_dict()
    return index


def latest_auth_session_from_index(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    index = auth_session_index_to_dict(payload)
    if not index:
        return {}

    def _sort_key(item: tuple[str, dict[str, Any]]) -> tuple[str, str]:
        entry = item[1]
        return (
            str(entry.get("confirmed_at") or ""),
            str(entry.get("updated_at") or ""),
        )

    return max(index.items(), key=_sort_key)[1]

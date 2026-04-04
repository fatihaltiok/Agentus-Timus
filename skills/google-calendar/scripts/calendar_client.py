"""Google Calendar API client helpers for the google-calendar skill.

This module provides reusable helpers to load OAuth credentials, initialize
Google Calendar API access, and perform common calendar operations.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SKILL_DIR.parent.parent

_TOKEN_CANDIDATES = (
    SKILL_DIR / "token.json",
    SCRIPT_DIR / "token.json",
)
_CREDENTIAL_CANDIDATES = (
    SKILL_DIR / "credentials.json",
    SCRIPT_DIR / "credentials.json",
    PROJECT_ROOT / "credentials.json",
)


def _find_existing_file(candidates: tuple[Path, ...]) -> Path | None:
    """Return the first existing file from the provided candidate paths."""

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _default_token_path() -> Path:
    """Return the preferred token storage path."""

    existing = _find_existing_file(_TOKEN_CANDIDATES)
    if existing is not None:
        return existing
    return _TOKEN_CANDIDATES[0]


TOKEN_PATH = _default_token_path()
CREDENTIALS_PATH = _find_existing_file(_CREDENTIAL_CANDIDATES)


def _persist_credentials(credentials: Credentials, token_path: Path | None = None) -> None:
    """Persist OAuth credentials to disk.

    Args:
        credentials: The credentials instance to serialize.
        token_path: Optional explicit token destination.

    Raises:
        OSError: If the token file cannot be written.
    """

    destination = token_path or TOKEN_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(credentials.to_json(), encoding="utf-8")


def load_token() -> Credentials | None:
    """Load Google OAuth token credentials from disk.

    If the token is expired and contains a refresh token, the credentials are
    refreshed automatically and saved back to disk.

    Returns:
        Loaded and optionally refreshed credentials, or ``None`` if no valid
        token file is available.

    Raises:
        RuntimeError: If the token exists but is invalid or refresh fails.
    """

    token_path = _find_existing_file(_TOKEN_CANDIDATES)
    if token_path is None:
        return None

    try:
        credentials = Credentials.from_authorized_user_file(
            str(token_path), SCOPES
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to load token file: {token_path}") from exc

    if not credentials:
        return None

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            _persist_credentials(credentials, token_path=token_path)
        except Exception as exc:  # pragma: no cover - external auth failure
            raise RuntimeError("Failed to refresh Google OAuth token.") from exc

    if not credentials.valid:
        raise RuntimeError(
            "Google OAuth token is invalid. Re-run the OAuth flow to "
            "generate a new token."
        )

    return credentials


def get_calendar_service() -> Resource:
    """Initialize and return the Google Calendar API service.

    Returns:
        A Google Calendar API service resource.

    Raises:
        FileNotFoundError: If no token is available.
        RuntimeError: If credentials are invalid or service creation fails.
    """

    credentials = load_token()
    if credentials is None:
        raise FileNotFoundError(
            "No Google Calendar token found. Run the OAuth flow first."
        )

    try:
        return build("calendar", "v3", credentials=credentials, cache_discovery=False)
    except Exception as exc:  # pragma: no cover - external API setup failure
        raise RuntimeError("Failed to initialize Google Calendar service.") from exc


def _normalize_datetime(value: datetime | str) -> str:
    """Normalize a datetime input to an ISO 8601 string with timezone.

    Args:
        value: A ``datetime`` instance or ISO 8601 datetime string.

    Returns:
        A normalized ISO 8601 datetime string.

    Raises:
        TypeError: If the input type is unsupported.
        ValueError: If the input string is not a valid datetime.
    """

    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                "Datetime strings must be valid ISO 8601 values."
            ) from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise TypeError("Datetime value must be a datetime instance or ISO string.")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.isoformat()


def list_events(days: int = 7) -> list[dict[str, Any]]:
    """Return upcoming events from the primary calendar.

    Args:
        days: Number of days ahead to search, starting from now.

    Returns:
        A list of event objects returned by the Google Calendar API.

    Raises:
        ValueError: If ``days`` is less than 1.
        RuntimeError: If the API request fails.
    """

    if days < 1:
        raise ValueError("days must be greater than or equal to 1.")

    service = get_calendar_service()
    now = datetime.now(UTC)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days)).isoformat()

    try:
        response = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except HttpError as exc:
        raise RuntimeError("Failed to list Google Calendar events.") from exc

    return response.get("items", [])


def create_event(
    title: str, start: datetime | str, end: datetime | str
) -> dict[str, Any]:
    """Create a calendar event in the primary Google Calendar.

    Args:
        title: Event title.
        start: Event start as datetime or ISO 8601 string.
        end: Event end as datetime or ISO 8601 string.

    Returns:
        The created event resource.

    Raises:
        ValueError: If title is empty or the end is before the start.
        RuntimeError: If the API request fails.
    """

    if not title or not title.strip():
        raise ValueError("title must not be empty.")

    start_iso = _normalize_datetime(start)
    end_iso = _normalize_datetime(end)

    start_dt = datetime.fromisoformat(start_iso)
    end_dt = datetime.fromisoformat(end_iso)
    if end_dt <= start_dt:
        raise ValueError("end must be after start.")

    body = {
        "summary": title.strip(),
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }

    service = get_calendar_service()
    try:
        return (
            service.events()
            .insert(calendarId="primary", body=body)
            .execute()
        )
    except HttpError as exc:
        raise RuntimeError("Failed to create Google Calendar event.") from exc


def delete_event(event_id: str) -> bool:
    """Delete an event from the primary Google Calendar.

    Args:
        event_id: The Google Calendar event ID.

    Returns:
        ``True`` if the deletion request succeeded.

    Raises:
        ValueError: If ``event_id`` is empty.
        RuntimeError: If the API request fails.
    """

    if not event_id or not event_id.strip():
        raise ValueError("event_id must not be empty.")

    service = get_calendar_service()
    try:
        service.events().delete(
            calendarId="primary", eventId=event_id.strip()
        ).execute()
    except HttpError as exc:
        raise RuntimeError("Failed to delete Google Calendar event.") from exc

    return True


def get_status() -> dict[str, Any]:
    """Return the current Google Calendar client status.

    The returned dictionary is designed for diagnostics and includes token and
    credentials file availability, token health, and service initialization
    status.

    Returns:
        A structured status dictionary.
    """

    token_path = _find_existing_file(_TOKEN_CANDIDATES)
    credentials_path = _find_existing_file(_CREDENTIAL_CANDIDATES)

    status: dict[str, Any] = {
        "credentials_file": str(credentials_path) if credentials_path else None,
        "credentials_file_exists": credentials_path is not None,
        "token_file": str(token_path) if token_path else str(TOKEN_PATH),
        "token_file_exists": token_path is not None,
        "token_valid": False,
        "token_expired": None,
        "refresh_available": False,
        "service_initialized": False,
        "error": None,
    }

    try:
        credentials = load_token()
        if credentials is None:
            return status

        status["token_valid"] = credentials.valid
        status["token_expired"] = credentials.expired
        status["refresh_available"] = bool(credentials.refresh_token)

        get_calendar_service()
        status["service_initialized"] = True
    except Exception as exc:  # pragma: no cover - diagnostic path
        status["error"] = str(exc)

    return status

#!/usr/bin/env python3
"""Runtime entrypoint for the google-calendar skill."""

from __future__ import annotations

import json
import sys
from typing import Any

from calendar_client import create_event, delete_event, get_status, list_events


def _emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _load_params(argv: list[str]) -> dict[str, Any]:
    if len(argv) < 2 or not str(argv[1]).strip():
        return {}
    raw = str(argv[1]).strip()
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {"action": raw}
    return loaded if isinstance(loaded, dict) else {}


def main(argv: list[str] | None = None) -> int:
    params = _load_params(list(argv or sys.argv))
    action = str(params.get("action") or "status").strip().lower()

    try:
        if action == "status":
            return _emit({"status": "success", "action": action, "data": get_status()})

        if action == "list":
            days = int(params.get("days") or 7)
            return _emit(
                {
                    "status": "success",
                    "action": action,
                    "days": days,
                    "events": list_events(days=days),
                }
            )

        if action == "create":
            title = str(params.get("title") or "").strip()
            start = params.get("start")
            end = params.get("end")
            event = create_event(title=title, start=start, end=end)
            return _emit({"status": "success", "action": action, "event": event})

        if action == "delete":
            event_id = str(params.get("event_id") or "").strip()
            deleted = delete_event(event_id)
            return _emit({"status": "success", "action": action, "deleted": bool(deleted)})

        return _emit(
            {
                "status": "error",
                "action": action,
                "error": f"Unbekannte calendar action: {action}",
            }
        )
    except FileNotFoundError as exc:
        return _emit(
            {
                "status": "setup_required",
                "action": action,
                "error": str(exc),
                "data": get_status(),
            }
        )
    except Exception as exc:
        return _emit({"status": "error", "action": action, "error": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Small readiness check for a central Qdrant server."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PROJECT_DEFAULT = "http://127.0.0.1:6333/readyz"


def _resolve_target(raw_url: str | None) -> str:
    value = str(raw_url or "").strip()
    if value.startswith(("http://", "https://")):
        return value
    env_url = str(os.getenv("QDRANT_URL") or "").strip()
    if env_url.startswith(("http://", "https://")):
        return env_url.rstrip("/") + "/readyz"
    return PROJECT_DEFAULT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Qdrant readiness endpoint.")
    parser.add_argument("--url", default="", help="Explicit readiness URL, e.g. http://127.0.0.1:6333/readyz")
    args = parser.parse_args(argv)

    target = _resolve_target(args.url)
    request = urllib.request.Request(target, method="GET")
    api_key = str(os.getenv("QDRANT_API_KEY") or "").strip()
    if api_key:
        request.add_header("api-key", api_key)

    try:
        with urllib.request.urlopen(request, timeout=3.0) as response:
            ok = 200 <= int(response.status) < 300
            payload = {
                "ok": ok,
                "status_code": int(response.status),
                "url": target,
            }
            print(json.dumps(payload, ensure_ascii=True))
            return 0 if ok else 1
    except urllib.error.HTTPError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "status_code": int(exc.code),
                    "url": target,
                    "error": str(exc),
                },
                ensure_ascii=True,
            )
        )
        return 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "status_code": None,
                    "url": target,
                    "error": str(exc),
                },
                ensure_ascii=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
# utils/timus_mail_oauth.py
"""
Einmalige OAuth2-Autorisierung für Timus E-Mail (Microsoft Graph / Device Code Flow).
Verwendet direkte HTTP-Aufrufe statt MSAL, um Tenant-Kompatibilitätsprobleme zu vermeiden.

Ausführen:
  python utils/timus_mail_oauth.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_root / ".env", override=True)

import os
import requests

CLIENT_ID  = os.getenv("TIMUS_GRAPH_CLIENT_ID", "")
CACHE_PATH = _root / os.getenv("TIMUS_GRAPH_TOKEN_CACHE", "data/timus_token_cache.bin")

SCOPES = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/User.Read offline_access"

# Versuche mehrere Tenant-Endpunkte der Reihe nach
TENANTS = [
    "consumers",                              # Persönliche Outlook.com-Konten (Mailbox-Zugriff)
    "common",                                 # Alle Konten
    "80a8117b-bc12-49e6-a362-4e172f0f4e37",  # Spezifischer Tenant (Fallback)
]


def _device_code_flow(tenant: str) -> dict | None:
    """Startet Device Code Flow für einen Tenant. Gibt flow-dict zurück oder None bei Fehler."""
    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode",
        data={"client_id": CLIENT_ID, "scope": SCOPES},
        timeout=15,
    )
    data = resp.json()
    if "user_code" in data:
        data["_tenant"] = tenant
        return data
    return None


def _poll_token(tenant: str, device_code: str, interval: int, expires_in: int) -> dict | None:
    """Pollt Token-Endpunkt bis Nutzer sich eingeloggt hat oder Timeout."""
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        resp = requests.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id":   CLIENT_ID,
                "grant_type":  "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
            timeout=15,
        )
        data = resp.json()
        if "access_token" in data:
            return data
        if data.get("error") == "authorization_pending":
            continue
        if data.get("error") == "slow_down":
            interval += 5
            continue
        # Echter Fehler
        print(f"   Fehler: {data.get('error_description', data.get('error'))}")
        return None
    return None


def _save_cache(token_data: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = {
        "access_token":  token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_at":    time.time() + int(token_data.get("expires_in", 3600)),
        "token_type":    token_data.get("token_type", "Bearer"),
        "scope":         token_data.get("scope", SCOPES),
    }
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    print(f"   Token-Cache gespeichert: {CACHE_PATH}")


def main() -> None:
    if not CLIENT_ID:
        print("❌ TIMUS_GRAPH_CLIENT_ID fehlt in .env", file=sys.stderr)
        sys.exit(1)

    # Prüfen ob schon ein gültiger Refresh-Token vorhanden
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if cache.get("refresh_token"):
                print("🔄 Vorhandener Token gefunden — teste Erneuerung …")
                refreshed = _refresh_token(cache["refresh_token"])
                if refreshed:
                    _save_cache(refreshed)
                    print("✅ Token erfolgreich erneuert — keine erneute Anmeldung nötig.")
                    return
        except Exception:
            pass

    # Device Code Flow starten — teste Tenants der Reihe nach
    EMAIL = os.getenv("TIMUS_EMAIL", "")

    flow = None
    for tenant in TENANTS:
        print(f"   Versuche Tenant: {tenant} …")
        post_data = {"client_id": CLIENT_ID, "scope": SCOPES}
        # login_hint hilft common-Endpunkt das richtige Konto zu identifizieren
        if tenant in ("common", "consumers") and EMAIL:
            post_data["login_hint"] = EMAIL
        resp = requests.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode",
            data=post_data,
            timeout=15,
        )
        data = resp.json()
        if "user_code" in data:
            data["_tenant"] = tenant
            flow = data
            print(f"   ✅ Tenant '{tenant}' akzeptiert.")
            break
        else:
            print(f"   ❌ {data.get('error')}: {data.get('error_description', '')[:120]}")

    if not flow:
        print("❌ Kein Tenant hat funktioniert. Prüfe Client-ID und App-Konfiguration.", file=sys.stderr)
        sys.exit(1)

    tenant = flow["_tenant"]
    print()
    print("=" * 60)
    print("  Timus E-Mail — Einmalige Autorisierung")
    print("=" * 60)
    print()
    print(f"  1. Öffne im Browser:")
    print(f"     {flow['verification_uri']}")
    print()
    print(f"  2. Gib diesen Code ein:  {flow['user_code']}")
    print()
    print(f"  3. Melde dich mit  timus.assistent@outlook.com  an")
    print(f"     und erteile die Berechtigungen (Mail lesen + senden).")
    print()
    print("  Warte auf Bestätigung …")
    print("=" * 60)

    token_data = _poll_token(
        tenant      = tenant,
        device_code = flow["device_code"],
        interval    = int(flow.get("interval", 5)),
        expires_in  = int(flow.get("expires_in", 900)),
    )

    if token_data:
        _save_cache(token_data)
        print()
        print("✅ Autorisierung erfolgreich!")
        print()
        print("   Timus kann jetzt E-Mails senden und lesen.")
        print("   Test: python utils/timus_mail_cli.py status")
    else:
        print("\n❌ Autorisierung fehlgeschlagen oder abgelaufen.", file=sys.stderr)
        sys.exit(1)


def _refresh_token(refresh_token: str) -> dict | None:
    """Erneuert Access-Token via Refresh-Token."""
    for tenant in TENANTS:
        resp = requests.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id":     CLIENT_ID,
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
                "scope":         SCOPES,
            },
            timeout=15,
        )
        data = resp.json()
        if "access_token" in data:
            return data
    return None


if __name__ == "__main__":
    main()

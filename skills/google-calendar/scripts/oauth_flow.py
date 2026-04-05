import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly',
           'https://www.googleapis.com/auth/calendar.events']

# Pfad zur Client‑Secret‑Datei (credentials.json) muss im selben Verzeichnis liegen
client_secrets_file = Path(__file__).with_name("credentials.json")


def _validate_credentials_file(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Ungültige Google-OAuth-Datei: {path}") from exc

    installed = payload.get("installed") if isinstance(payload, dict) else None
    client_id = str((installed or {}).get("client_id") or "").strip()
    client_secret = str((installed or {}).get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise SystemExit(f"Google-OAuth-Datei unvollständig: {path}")
    if client_id == "YOUR_CLIENT_ID_HERE" or client_secret == "YOUR_CLIENT_SECRET_HERE":
        raise SystemExit(
            "Google OAuth Credentials noch nicht eingetragen. "
            f"Bitte {path} mit echten Werten befüllen."
        )

_validate_credentials_file(client_secrets_file)
flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), SCOPES)
creds = flow.run_local_server(port=0)

token_path = Path(__file__).with_name("token.json")
token_path.write_text(creds.to_json(), encoding="utf-8")
print(f"Credentials saved to {token_path}")

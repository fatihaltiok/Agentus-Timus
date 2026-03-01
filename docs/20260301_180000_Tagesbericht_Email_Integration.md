# Tagesbericht: E-Mail-Integration via Microsoft Graph OAuth2
**Datum:** 2026-03-01
**Autor:** Claude Code (Session)
**Status:** ✅ Abgeschlossen

---

## Zusammenfassung

Timus verfügt ab heute über vollständige E-Mail-Fähigkeiten. Er kann eigenständig E-Mails senden und empfangen über die dedizierte Adresse `timus.assistent@outlook.com` — integriert als MCP-Tool direkt in den Agent-Loop.

---

## Neu erstellte Dateien

| Datei | Beschreibung |
|-------|-------------|
| `tools/email_tool/__init__.py` | Modul-Init |
| `tools/email_tool/tool.py` | Kernimplementierung (3 MCP-Tools) |
| `utils/timus_mail_oauth.py` | Einmalige OAuth2-Autorisierung (Device Code Flow) |
| `utils/timus_mail_cli.py` | CLI für manuelles Testen |
| `tests/test_email_tool.py` | Pytest-Suite (18 Tests) |

## Geänderte Dateien

| Datei | Änderung |
|-------|---------|
| `server/mcp_server.py` | `tools.email_tool.tool` zu `TOOL_MODULES` hinzugefügt |
| `main_dispatcher.py` | E-Mail-Keywords für Routing ergänzt |
| `skills/skill_email.py` | Stubs ersetzt durch `registry_v2.execute(...)` |
| `.env` | `TIMUS_GRAPH_CLIENT_ID`, `TIMUS_GRAPH_AUTHORITY` etc. |
| `.env.example` | E-Mail-Variablen dokumentiert |

---

## Implementierte MCP-Tools

### `send_email`
Sendet eine E-Mail via `POST /me/sendMail`.
Parameter: `to`, `subject`, `body`, `cc`, `bcc`, `html_body`, `reply_to`

### `read_emails`
Liest E-Mails aus beliebigem Postfach via `GET /me/mailFolders/{mailbox}/messages`.
Parameter: `mailbox` (default: inbox), `limit`, `unread_only`, `search`

### `get_email_status`
Prüft OAuth2-Token und Graph-Verbindung via `GET /me`.
Gibt Kontoname, Display-Name und Verbindungsstatus zurück.

---

## Technische Architektur

```
Timus Agent
    │
    ▼
tools/email_tool/tool.py
    │
    ├── _get_access_token()   ← liest/erneuert Token aus Cache
    ├── _refresh_access_token()  ← automatische Token-Erneuerung
    │
    ▼
Microsoft Graph API (https://graph.microsoft.com/v1.0)
    │
    ├── POST /me/sendMail
    ├── GET  /me/mailFolders/{mailbox}/messages
    └── GET  /me
```

**Auth-Methode:** OAuth2 Device Code Flow (Raw HTTP, kein MSAL)
**Token-Cache:** `data/timus_token_cache.bin` (JSON, enthält access + refresh token)
**Automatische Erneuerung:** Refresh-Token wird bei Ablauf automatisch verwendet

---

## Probleme und Lösungen

### Problem 1: Basic Auth blockiert
Microsoft Outlook.com blockiert SMTP/IMAP mit Username + Passwort (Modern Auth Pflicht).
**Lösung:** Komplette Umstellung auf Microsoft Graph API + OAuth2.

### Problem 2: MSAL Scope-Konflikt
MSAL verwaltet `offline_access` intern — beim manuellen Übergeben kam ein Fehler.
**Lösung:** Raw HTTP statt MSAL-Bibliothek verwendet.

### Problem 3: Falsche App-Registrierung (`#EXT#` Guest-Account)
Die erste Azure App wurde als "Organizational + Personal" in einem Azure AD Tenant angelegt. Der resultierende Token hatte `#EXT#` (Guest-Account) — kein Exchange-Postfach vorhanden → 401 bei `sendMail`.
**Lösung:** Neue App-Registrierung **"Nur persönliche Microsoft-Konten"** erstellt → `consumers`-Endpunkt funktioniert sofort.

### Problem 4: Fehlende `User.Read`-Berechtigung
Nach der neuen App-Registrierung fehlte `User.Read` in den Scopes → `/me` gab 401.
**Lösung:** `User.Read` zu den Scopes in `timus_mail_oauth.py` und `tool.py` hinzugefügt.

### Problem 5: Erste E-Mail im Spam
Erste ausgehende E-Mail von neuem Konto landete im Junk-Ordner des Empfängers.
**Lösung:** Absender als sicher markieren. Kein Code-Problem.

---

## Azure App-Konfiguration (finale)

| Eigenschaft | Wert |
|-------------|------|
| App-Name | Timus Mail Personal |
| Client-ID | `61703b15-3e25-4660-8c3d-13111fc46548` |
| Kontotyp | Nur persönliche Microsoft-Konten |
| Öffentlicher Client | Ja (Device Code Flow) |
| Berechtigungen | `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, `User.Read` (alle delegiert) |
| Token-Cache | `data/timus_token_cache.bin` |

---

## Verifikation

```
✅ python utils/timus_mail_cli.py status
   → success: true, address: timus.assistent@outlook.com, graph_ok: true

✅ python utils/timus_mail_cli.py send --to fatihaltiok@outlook.com ...
   → success: true (E-Mail im Gesendeten-Ordner bestätigt, Empfang bestätigt)

✅ python utils/timus_mail_cli.py read --limit 3
   → 3 E-Mails aus Posteingang gelesen
```

---

## Nächste Schritte (optional)

- `send_email` im Canvas-Chat testen (CommunicationAgent → Tool-Call)
- Periodisches E-Mail-Checking via Autonomy-Scheduler (Heartbeat)
- Reply-Funktion: E-Mail-UID für Antworten nutzen
- Token-Cache Backup-Strategie (bei Systemneustarts)

# Console Phase 1: Reverse Proxy, HTTPS, Auth

## Ziel

`console.fatih-altiok.com` soll als gesicherte mobile Timus-Konsole erreichbar sein:
- TLS/HTTPS
- vorgelagerte Auth
- Reverse Proxy auf die bestehende Timus-Web/API-Schicht
- kein direktes, ungeschuetztes Exponieren interner Dienste

## Aktueller Ist-Stand

- DNS:
  - `console.fatih-altiok.com` wurde als `CNAME` auf `fatihlinux.dyndns.org` angelegt
- Router:
  - Portfreigaben fuer `TCP 80` und `TCP 443` auf den Timus-Host wurden aktiviert
- Host:
  - `caddy` wurde installiert und als Reverse Proxy aktiviert
  - `ufw` wurde gezielt fuer `80/tcp` und `443/tcp` geoeffnet
  - `timus-mcp.service` lauscht intern auf `127.0.0.1:5000`
  - `console.fatih-altiok.com` antwortet ueber HTTPS mit gueltigem Zertifikat und vorgelagerter Basic Auth

## Architekturentscheidung

Fuer den ersten sicheren Produktionsschnitt wird `Caddy` verwendet.

Gruende:
- automatische TLS-Ausstellung
- einfache, kleine Konfiguration
- weniger Fehlerrisiko als eine neue `nginx`-Konfiguration
- `basicauth` fuer den ersten gesicherten Zugang reicht als Startstufe

## Exponierter Zielpfad

Oeffentlich:
- `https://console.fatih-altiok.com`

Intern:
- `http://127.0.0.1:5000`

Proxy-Ziel:
- gesamte Konsole und API laufen hinter derselben Domain
- kritische Konsole-Pfade:
  - `/canvas/ui`
  - `/status/snapshot`
  - `/events/stream`
  - `/chat`
  - `/chat/history`
  - `/upload`
  - `/voice/*`
  - benoetigte `/autonomy/*`- und Canvas-Pfade

## Auth-Modell

Phase 1 verwendet Proxy-seitige Basic Auth.

Warum:
- schnell und robust
- kein Eingriff in die bestehende App fuer den Erstzugang
- minimiert Risiko beim ersten externen Rollout

Wichtig:
- Passwort nur als `bcrypt`-Hash in der Caddy-Umgebung
- kein Passwort im Frontend
- spaeter kann Session-Auth oder 2FA innerhalb der App folgen

## Repo-Artefakte

- Caddy-Konfiguration:
  - `deploy/console/Caddyfile.example`
- Umgebungsvariablen:
  - `deploy/console/timus-console.env.example`

Die Konfiguration enthaelt bereits:
- `basicauth`
- Security Header
- `request_body` Limit fuer Uploads
- `flush_interval -1` fuer SSE (`/events/stream`)

## Live-Umsetzung am 10.03.2026

Auf dem Host wurde der erste sichere Zugriff bereits live ausgerollt:

- `caddy` ist installiert
- `/etc/caddy/Caddyfile` proxy't auf `127.0.0.1:5000`
- Basic Auth ist vorgelagert
- `console.fatih-altiok.com` hat ein erfolgreich ausgestelltes Let's-Encrypt-Zertifikat
- `http://console.fatih-altiok.com` leitet sauber auf HTTPS um
- `https://console.fatih-altiok.com` fordert Auth an
- `https://console.fatih-altiok.com/health` liefert hinter Auth den gesunden MCP-Status

Wichtiger operativer Befund:
- Der letzte echte Blocker war nicht Caddy, sondern `ufw` mit `deny incoming`
- Erst nach `80/tcp` und `443/tcp` im Host-Firewall-Set konnten die ACME-Challenges erfolgreich durchlaufen

## Host-Rollout-Reihenfolge

1. `timus-mcp.service` lokal wieder sauber starten und intern pruefen
2. `caddy` auf dem Host installieren
3. Passwort-Hash generieren:
   - `caddy hash-password --plaintext 'STARKES_PASSWORT'`
4. Env-Datei auf dem Host ablegen
5. Caddyfile aktivieren
6. `caddy validate`
7. Caddy starten / reloaden
8. externen Zugriff ueber `https://console.fatih-altiok.com` pruefen

## Konkrete Host-Dateien

Empfohlene Platzierung:
- `/etc/caddy/Caddyfile`
- `/etc/timus-console.env`

Empfohlene Env-Werte:
- `TIMUS_CONSOLE_ACME_EMAIL=admin@fatih-altiok.com`
- `TIMUS_CONSOLE_UPSTREAM=127.0.0.1:5000`
- `TIMUS_CONSOLE_USER=timusadmin`
- `TIMUS_CONSOLE_PASSWORD_HASH=<caddy-bcrypt-hash>`

## Router / Netzwerk

Pflicht:
- `TCP 80` -> Timus-Host
- `TCP 443` -> Timus-Host

Optional spaeter:
- `80` nach erfolgreicher ACME/TLS-Einrichtung nur fuer Redirect/Challenge offen lassen

## Abnahmetests

Vor Freigabe muessen diese Punkte gruen sein:

1. lokal:
   - `curl -sS http://127.0.0.1:5000/health`
   - `curl -sS http://127.0.0.1:5000/status/snapshot`
2. ueber Proxy intern:
   - `https://console.fatih-altiok.com` fordert Auth
   - Login funktioniert
   - `/canvas/ui` laedt
   - `/status/snapshot` kommt hinter Auth durch
   - `/events/stream` bleibt stabil
3. extern:
   - gueltiges Zertifikat
   - keine offenen internen Ports
   - Upload groesserer Dateien funktioniert
   - Voice-/SSE-Pfade werden nicht gepuffert oder abgeschnitten

Status am 10.03.2026:
- HTTPS-Zertifikat: gruen
- Auth-Gate: gruen
- lokaler Upstream `127.0.0.1:5000`: gruen
- externer HTTP->HTTPS-Redirect: gruen
- `health` hinter Auth: gruen
- UI-/SSE-/Upload-Abnahme: noch offen fuer Phase 2/3

## Risiken, die bewusst vermieden werden

- kein direktes Exponieren von `127.0.0.1:5000`
- kein Start ohne Auth
- kein sofortiger App-interner Auth-Umbau
- kein gleichzeitiger Proxy- und UI-Grossumbau

## Nächster Schritt

Nach erfolgreichem Proxy-/TLS-/Auth-Schnitt folgt Phase 2:
- bestehende Canvas UI auf mobile Informationsarchitektur umbauen

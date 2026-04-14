# Timus Installationsanleitung fuer neue Rechner

Stand: 2026-04-14

## Ziel

Diese Anleitung beschreibt, wie Timus auf einem neuen Linux-Rechner als zusammenhaengender Stack installiert wird.

Der aktuelle Betriebsblock besteht aus:

- `qdrant.service`
- `timus-mcp.service`
- `timus-dispatcher.service`
- `timus-stack.target`

Der Stack kann danach als ein Block gestartet, gestoppt und beim Boot aktiviert werden.

## Wichtiger aktueller Architekturstand

Die direkt im Repo liegenden Standard-Units sind derzeit noch **host-spezifisch**. Sie enthalten feste Pfade und den festen Benutzer:

- Benutzer: `fatih-ubuntu`
- Projektpfad: `/home/fatih-ubuntu/dev/timus`
- Python-Pfad: `/home/fatih-ubuntu/miniconda3/envs/timus/bin/python`
- MCP-Port: `5000`
- Dispatcher-Health-Port: `5010`
- Qdrant HTTP/gRPC: `6333` / `6334`

Das bedeutet:

- Die Installationslogik als Block ist vorhanden.
- Fuer neue Rechner gibt es jetzt zusaetzlich einen **portablen Render-Pfad** ueber:
  - [setup_timus_host.sh](/home/fatih-ubuntu/dev/timus/scripts/setup_timus_host.sh)
  - [install_timus_stack.sh](/home/fatih-ubuntu/dev/timus/scripts/install_timus_stack.sh)
- Ein Nutzer muss die Units damit nicht mehr manuell editieren, sondern nur einfache Host-Werte eingeben.

## Zielbild fuer Neuinstallation

Empfohlener Installationsmodus auf neuen Rechnern:

1. Repo klonen
2. Python-Umgebung herstellen
3. `.env` anlegen
4. Qdrant-Binary und Speicherpfade pruefen
5. systemd-Units auf den Zielrechner installieren
6. `timus-stack.target` aktivieren und starten
7. Health-Checks fuer alle drei Bestandteile pruefen

## Voraussetzungen

Mindestens noetig:

- Linux mit `systemd`
- Python 3.11
- Git
- `curl`
- `sqlite3`
- Qdrant-Binary auf dem System oder via `QDRANT_BIN`
- installierte Python-Abhaengigkeiten aus dem Repo

Fuer visuelle/desktop-nahe Faelle zusaetzlich sinnvoll:

- laufende grafische Session
- gueltiges `DISPLAY`
- ggf. `XAUTHORITY`

## Empfohlene Verzeichnisstruktur

Empfohlen, wenn du die bestehenden Units moeglichst unveraendert nutzen willst:

```text
/home/<user>/dev/timus
```

Wenn du davon abweichst, musst du in den Unit-Dateien mindestens diese Felder anpassen:

- `User=...`
- `WorkingDirectory=...`
- `ExecStart=...`
- `Environment=XAUTHORITY=...`

## Schritt 1: Repo klonen

```bash
git clone git@github.com:fatihaltiok/Agentus-Timus.git
cd Agentus-Timus
```

## Schritt 2: Python-Umgebung herstellen

Aktuell sind die systemd-Units auf eine Conda-Umgebung ausgelegt. Wenn du denselben Pfad wie im aktuellen Setup nutzen willst:

```bash
conda create -n timus python=3.11 -y
conda activate timus
pip install -r requirements.txt
```

Wenn du stattdessen `venv` nutzen willst, musst du die `ExecStart=`-Pfade in den Units auf den neuen Python-Pfad umstellen.

## Schritt 3: `.env` anlegen

```bash
cp .env.example .env
```

Danach:

- API-Keys und Provider-Konfiguration setzen
- vorhandene funktionierende `.env` vom Quellrechner bevorzugt uebernehmen, wenn derselbe Betriebsmodus gewuenscht ist

Besonders relevant fuer den Stack:

- Provider-/Model-Keys fuer Timus selbst
- `QDRANT_BIN`, falls Qdrant nicht im `PATH` liegt
- `QDRANT_SERVER_STORAGE_PATH`
- `QDRANT_SERVER_SNAPSHOTS_PATH`
- ggf. `QDRANT_SERVER_HOST`, `QDRANT_SERVER_HTTP_PORT`, `QDRANT_SERVER_GRPC_PORT`

## Schritt 4: Qdrant vorbereiten

Der Startpfad fuer Qdrant liegt in:

- [start_qdrant_server.sh](/home/fatih-ubuntu/dev/timus/scripts/start_qdrant_server.sh)

Er liest Qdrant-bezogene Werte aus `.env` und startet dann das Qdrant-Binary.

Pruefen:

```bash
command -v qdrant
```

Falls kein Binary gefunden wird:

- Qdrant installieren
- oder `QDRANT_BIN=/pfad/zum/qdrant` in `.env` setzen

Speicherpfade pruefen:

- `QDRANT_SERVER_STORAGE_PATH`
- `QDRANT_SERVER_SNAPSHOTS_PATH`

Diese sollten auf dem Zielrechner existieren duerfen und ausreichend Platz haben.

## Schritt 5: Host-Setup statt manueller Unit-Bearbeitung

Fuer neue Rechner ist jetzt der empfohlene Pfad:

```bash
./scripts/setup_timus_host.sh
```

Das Skript fragt nur diese Werte ab:

- System-Benutzer
- Projektpfad
- Python-Pfad
- uvicorn-Pfad
- `DISPLAY`
- `XAUTHORITY`

Danach rendert es portable Units nach:

```text
.generated/systemd/
```

und speichert die Host-Konfiguration in:

```text
scripts/timus_stack_host.env
```

Optional direkt mit Installation:

```bash
./scripts/setup_timus_host.sh --install --enable --start
```

Nur wenn du **bewusst ohne Setup-Skript** arbeiten willst, musst du die Standard-Units im Repo manuell anpassen.

## Schritt 6: systemd-Units auf den Zielrechner anpassen

Repo-Dateien:

- [qdrant.service](/home/fatih-ubuntu/dev/timus/qdrant.service)
- [timus-mcp.service](/home/fatih-ubuntu/dev/timus/timus-mcp.service)
- [timus-dispatcher.service](/home/fatih-ubuntu/dev/timus/timus-dispatcher.service)
- [timus-stack.target](/home/fatih-ubuntu/dev/timus/timus-stack.target)

Nur noetig, wenn du **nicht** den portable-Setup-Pfad nutzt. Dann vor der Installation anpassen:

- `User=`
- `WorkingDirectory=`
- `ExecStart=`
- `DISPLAY=`
- `XAUTHORITY=`

Wenn du den Setup-Renderer nutzt, entfaellt dieser Schritt.

## Schritt 7: Stack installieren

Fuer den aktuellen Block gibt es jetzt einen Installer:

- [install_timus_stack.sh](/home/fatih-ubuntu/dev/timus/scripts/install_timus_stack.sh)

Installation, Aktivierung und Sofortstart:

```bash
sudo ./scripts/install_timus_stack.sh --enable --start
```

Wenn du den portable Setup-Pfad genutzt hast, besser:

```bash
sudo ./scripts/install_timus_stack.sh --unit-dir .generated/systemd --enable --start
```

Alternativ ueber das Bedien-Skript:

```bash
./scripts/timusctl.sh install
```

Wenn bereits portable Units gerendert wurden, nutzt `timusctl.sh install` diese automatisch.

Was dabei passiert:

- `qdrant.service`, `timus-mcp.service`, `timus-dispatcher.service`, `timus-stack.target` werden nach `/etc/systemd/system` kopiert
- `systemctl daemon-reload`
- Einzel-Units werden nicht direkt fuer den Boot aktiviert
- stattdessen wird `timus-stack.target` aktiviert
- optional wird der Stack sofort gestartet

## Schritt 8: Betrieb als ein Block

Stack-Bedienung ueber das Repo-Skript:

```bash
./scripts/timusctl.sh up
./scripts/timusctl.sh down
./scripts/timusctl.sh restart
./scripts/timusctl.sh status
./scripts/timusctl.sh health
```

Oder direkt ueber systemd:

```bash
sudo systemctl start timus-stack.target
sudo systemctl stop timus-stack.target
sudo systemctl restart timus-stack.target
sudo systemctl status timus-stack.target
```

## Schritt 9: Health pruefen

Nach erfolgreichem Start muessen diese Endpunkte antworten:

Qdrant:

```bash
curl -fsS http://127.0.0.1:6333/readyz
```

MCP:

```bash
curl -fsS http://127.0.0.1:5000/health
```

Dispatcher:

```bash
curl -fsS http://127.0.0.1:5010/health
```

Gesamtcheck:

```bash
./scripts/timusctl.sh health
```

## Schritt 10: Migration eines bestehenden Timus auf neuen Rechner

Wenn nicht nur der Code, sondern auch der bisherige Zustand mitgenommen werden soll:

Mitnehmen oder gezielt migrieren:

- `.env`
- SQLite-Datenbanken in `data/`
- Qdrant-Daten
- ggf. Markdown-Memory-Dateien
- ggf. weitere lokale Runtime-Artefakte, falls sie fuer den Zielbetrieb relevant sind

Pragmatische Regel:

- frischer Code aus Git
- funktionierende `.env` vom Alt-System
- dann entscheiden, ob Memory und Vektordaten ebenfalls umziehen sollen

Wenn du **wirklich dieselbe Timus-Identitaet** behalten willst, reicht reiner Code nicht. Dann muessen auch Speicher- und State-Daten migriert werden.

## Troubleshooting

### Qdrant startet nicht

Pruefen:

- `command -v qdrant`
- `QDRANT_BIN` in `.env`
- Speicherpfade und Schreibrechte
- `journalctl -u qdrant.service -n 200`

### MCP startet nicht

Pruefen:

- korrekter Python-Pfad in `timus-mcp.service`
- installierte Python-Abhaengigkeiten
- Port `5000` frei
- `journalctl -u timus-mcp.service -n 200`

### Dispatcher startet nicht

Pruefen:

- korrekter Python-Pfad in `timus-dispatcher.service`
- MCP bereits healthy
- Port `5010` frei
- `journalctl -u timus-dispatcher.service -n 200`

### Stack laeuft, aber Visual/Desktop-Faelle funktionieren nicht

Pruefen:

- `DISPLAY`
- `XAUTHORITY`
- ob der Dienst unter dem richtigen Desktop-Benutzer laeuft

### Installer funktioniert, aber nichts startet beim Boot

Pruefen:

```bash
systemctl is-enabled timus-stack.target
```

Falls noetig:

```bash
sudo systemctl enable timus-stack.target
```

## Noch offene Grenze

Die neue Setup-Schicht macht den Installationspfad deutlich portabler. Noch nicht komplett abgedeckt sind aber z. B.:

- automatische Erkennung aller idealen Defaults fuer jeden Host
- vollstaendig gefuehrte GUI-Installation
- komplette Migration aller Runtime-Daten mit einem einzigen Wizard

## Kurzfassung

Fuer einen neuen Rechner ist der aktuelle saubere Pfad:

1. Repo klonen
2. Python + Dependencies installieren
3. `.env` anlegen
4. Qdrant pruefen
5. `./scripts/setup_timus_host.sh`
6. `./scripts/setup_timus_host.sh --install --enable --start`
7. Health auf `6333`, `5000`, `5010` pruefen

Damit laufen Qdrant, MCP und Dispatcher als zusammenhaengender Timus-Block.

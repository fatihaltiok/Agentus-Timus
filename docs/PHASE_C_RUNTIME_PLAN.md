# Phase C Runtime Plan

Stand: 2026-04-04 20:45 CEST

## Ziel

Phase C haertet die Laufzeitpfade, die nach Phase B noch als reale Betriebsrisiken uebrig sind:

- MCP-/Health-/Restart-Zuverlaessigkeit
- Vision-/OCR-Hot-Path unter Last
- Antwortpfade bei langen oder haengenden Laeufen
- bessere Korrelation zwischen Anfrage, Agentenlauf, Toolpfad und sichtbarem Nutzerfehler

Phase C ist erfolgreich, wenn Timus unter echter Nutzung seltener haengt, sauberer neu startet und Runtime-Fehler schneller eindeutig lokalisierbar sind.

## Aktuelle Baseline

### 1. MCP-Startup und Restart-Verhalten

Aktueller Live-Befund aus den heutigen Restarts:

- `timus-mcp` braucht nach Restart sichtbar mehrere Sekunden bis `/health` wieder gruen ist
- waehrend des Starts laeuft der Host-/Modellcheck:
  - `Checking connectivity to the model hosters, this may take a while.`
- der Dispatcher wartet in dieser Phase auf den MCP-Server

Zusaetzlicher Runtime-Befund:

- bei Restart lief `timus-mcp` heute in einen `timeout graceful shutdown exceeded`-Pfad und wurde danach von `systemd` mit `SIGKILL` beendet

Einordnung:

- das ist kein semantisches Phase-B-Thema mehr
- es ist ein echter Runtime-/Lifecycle-Fall fuer Phase C

### 2. Vision/OCR

Historische Beobachtungen:

- `visual`-Timeouts bei `get_all_screen_text`
- OOM-/Speicherdruck-Risiko im Florence-2-/PaddleOCR-Mischpfad

Aktueller Stand:

- die unnoetige Meta-Delegation fuer einfache Screentext-Reads wurde bereits entfernt
- die groessere Architekturfrage bleibt aber offen:
  - Device-Mischbetrieb
  - Lifecycle
  - Memory-/Fallback-Telemetrie

### 3. Telegram-/Antwortpfade

Bekannte Risikoklasse:

- Agent denkt / delegiert / recherchiert laenger
- Antwort kommt fuer den Nutzer zu spaet oder gar nicht sichtbar an
- Korrelation zwischen Eingang, laufender Agentenkette und sichtbarer Antwort ist noch zu schwach

### 4. Runtime-Spam / Persistenzdruck

Heute sichtbar:

- `dispatcher_memory_write_spike` mit massiven `MEMORY.md`-Schreibwellen

Einordnung:

- kein semantischer Fehler
- echte Runtime-/Persistenzlast
- gehoert in Phase C, auch wenn es kein MCP-/Vision-Fall ist

## Workstreams

### C1. MCP Health / Restart / Self-Healing

Ziel:

- `/health` schneller und stabiler zurueckbekommen
- haengende Shutdowns / Restart-Kaskaden abbauen
- Self-Healing-/Health-Pfade sauber vom normalen Betrieb trennen

Erster Scope:

- Startup-Pfad von `timus-mcp`
- Modellhost-Checks beim Start
- Graceful-Shutdown-/Timeout-Verhalten
- `mcp_health`-/Self-Healing-Korrelation

Erfolg:

- kuerzeres und stabileres Restart-Fenster
- keine haeufigen `SIGKILL`-Stopps beim normalen Reload
- klarere Diagnose fuer `mcp_health`-Incidents

### C2. Observability und Anfrage-zu-Fehler-Korrelation

Ziel:

- fuer haengende oder fehlerhafte Nutzerlaeufe schneller sehen:
  - welche Anfrage
  - welcher Agent
  - welcher Toolpfad
  - welcher sichtbare Fehler

Erster Scope:

- bessere Korrelation zwischen `/chat`, Task-Log, Observation und Runtime-Metadaten
- Telegram-/Canvas-/MCP-seitige Sicht auf denselben Incident

Erfolg:

- weniger manuelles Zusammenpuzzeln aus Journal + Task-Log + Observation
- klarere Incident-Klassen im Beobachtungslog

### C3. Vision/OCR-Hot-Path

Ziel:

- OCR-/Vision-Aufrufe unter Last berechenbarer machen
- Device-/Memory-Verhalten sichtbar und konsistent machen

Erster Scope:

- Florence-2-/PaddleOCR-Mischpfad
- Memory-/Device-Telemetrie vor und nach Vision-Aufrufen
- ein klarer Primaerpfad plus explizite Fallbacks

Erfolg:

- weniger OOM-/Timeout-Risiko
- weniger ungeplante CPU/GPU-Mischzustaende
- bessere Debugbarkeit bei Vision-Folgen

### C4. Antwortpfade bei Langlaeufern

Ziel:

- lange Recherche-/Diagnose-/Visual-Läufe duerfen nicht wie "Timus antwortet nicht" wirken

Erster Scope:

- Zwischenstatus / Heartbeat / Teilergebnis fuer lange Laeufe
- saubere Nutzerkommunikation bei echten Blockern
- spaetere Telegram-spezifische Haertung

Erfolg:

- weniger wahrgenommene "stille" Ausfaelle
- fruehere sichtbare Fortschrittssignale

### C5. Persistenz- und Runtime-Spam

Ziel:

- unnoetige Schreibspitzen und Wiederholungswellen abbauen

Erster Scope:

- `MEMORY.md`-Write-Spikes
- Dedupe / Rate-Limits / Batch-Verhalten

Erfolg:

- weniger I/O-Spam
- weniger Debug-Rauschen
- weniger indirekter Runtime-Druck

## Prioritaet

1. `C1` MCP Health / Restart / Self-Healing
2. `C2` Observability und Antwortpfad-Korrelation
3. `C5` Persistenz- und Runtime-Spam
4. `C3` Vision/OCR-Hot-Path
5. `C4` Langlaeufer-/Antwortpfade

Hinweis:

- `C3` bleibt technisch wichtig
- `C1` und `C2` kommen zuerst, weil sie den groessten Hebel fuer Betriebsstabilitaet und Debug-Zeit haben

## Phase-C-Abnahmekriterien

### Runtime

- Restart von `timus-mcp` ohne haeufiges hartes `SIGKILL`
- `/health` wird nach Reload reproduzierbar schnell wieder gruen
- keine offenen / haengenden `mcp_health`-Folgen ohne klare Diagnose

### Observability

- Incident-Pfade lassen sich aus einem Einstiegspunkt nachvollziehen
- haengende Antworten sind im Log-/Observation-Pfad klarer sichtbar

### Vision/OCR

- Device-/Memory-Verhalten ist sichtbar
- keine unerklaerten Hot-Path-Zeitouts ohne Telemetrie

### Nutzerpfad

- lange Laeufe zeigen Fortschritt oder ehrlichen Zwischenstatus
- weniger "Timus antwortet nicht"-Gefuehl trotz laufender Arbeit

## Erster Arbeitsblock

Start mit `C1`:

1. `timus-mcp`-Startup/Shutdown-Pfad instrumentieren und ausmessen
2. Modellhost-Check und Health-Readiness entkoppeln oder besser kennzeichnen
3. Graceful-Shutdown-/Timeout-Kante entschärfen
4. `mcp_health`-/Self-Healing-Logs gegen echte Laufzeitpfade korrelieren

Erwartetes erstes Artefakt:

- eine kleine, belastbare Runtime-Readiness-/Restart-Härtung
- plus klarere Logs fuer den MCP-Lifecycle

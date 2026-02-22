# Timus — Agent-Erweiterungsplan
**Erstellt:** 2026-02-22
**Ziel:** 5 neue Agenten in 4 Meilensteinen + vollständiger Systemtest

---

## Übersicht

```
M1: data + document   →  [Test M1]
M2: communication     →  [Test M2]  →  [Integration-Test M1+M2]
M3: system            →  [Test M3]  →  [Integration-Test M1+M2+M3]
M4: shell             →  [Test M4]  →  [GESAMTTEST alle Agenten]
```

---

## Meilenstein 1 — `data` + `document`

> Beide bauen direkt auf die neuen document_creator Tools auf.
> Sie teilen sich denselben Output-Kanal (results/) und
> werden zusammen gebaut weil sie eng verzahnt sind.

---

### Phase 1.1 — `data`-Agent: Kern + Prompt

**Was:**
- Neue Datei `agent/agents/data.py`
- Systemprompt der den Agenten auf Datenanalyse spezialisiert
- Fähigkeiten: CSV/XLSX lesen, rechnen, Statistiken (min/max/avg/summe), Ausgabe als Bericht
- Modell: gpt-4o (braucht Reasoning für Berechnungen)

**Prompt-Schwerpunkte:**
- "Lies die Datei zuerst mit read_file"
- "Erkenne das Format (CSV/XLSX/JSON) automatisch"
- "Erstelle immer zuerst eine Zusammenfassung, dann Details"
- "Ausgabe als XLSX wenn Tabellen, als PDF wenn Bericht"

**Deliverable:** `agent/agents/data.py` mit DataAgent-Klasse

---

### Phase 1.2 — `data`-Agent: Tool-Verbindung

**Was:**
- Prüfen welche Tools der data-Agent braucht:
  - `read_file` ✅ (vorhanden)
  - `search_files` ✅ (vorhanden)
  - `create_xlsx` ✅ (vorhanden)
  - `create_pdf` ✅ (vorhanden)
  - `create_csv` ✅ (vorhanden)
- Neues Tool falls nötig: `parse_csv_or_xlsx` — liest Datei und gibt strukturierte Daten zurück (pandas-Hilfsmodul)
- pandas installieren falls nicht vorhanden

**Deliverable:** Alle benötigten Tools verfügbar + ggf. `tools/data_tool/tool.py`

---

### Phase 1.3 — `document`-Agent: Kern + Prompt

**Was:**
- Neue Datei `agent/agents/document.py`
- Systemprompt der auf strukturierte Dokument-Erstellung spezialisiert
- Fähigkeiten: Angebote, Berichte, Protokolle, Lebensläufe, Briefe
- Modell: claude-sonnet (bester für strukturierte, professionelle Texte)

**Prompt-Schwerpunkte:**
- "Frage immer nach Format (PDF/DOCX) wenn nicht angegeben"
- "Strukturiere Dokumente professionell: Titel, Datum, Autor, Abschnitte"
- "Für Angebote: Tabellarische Übersicht mit Preisen → DOCX oder PDF"
- "Für Berichte: Zusammenfassung → Details → Anhang"

**Deliverable:** `agent/agents/document.py`

---

### Phase 1.4 — Dispatcher-Integration M1

**Was:**
- `main_dispatcher.py` — beide Agenten eintragen
- `DISPATCHER_PROMPT` erweitern: Wann wird `data` gewählt, wann `document`?
- `agent/prompts.py` — Prompts für beide Agenten
- Canvas-LED: `_KNOWN_AGENTS` in `mcp_server.py` um `data` und `document` erweitern

**Routing-Regeln:**
- `data` → "analysiere", "berechne", "Statistik", "Tabelle auswerten", "CSV", "Excel"
- `document` → "erstelle ein Dokument", "schreib ein Angebot", "Brief", "Protokoll", "Lebenslauf"

**Deliverable:** Dispatcher erkennt und routet beide Agenten korrekt

---

### Test M1 — Daten + Dokumente

```
T1.1 - data: CSV-Datei mit Ausgaben einlesen → Statistiken ausgeben
T1.2 - data: Excel-Datei analysieren → PDF-Bericht erstellen
T1.3 - data: JSON-Daten auswerten → XLSX-Tabelle erstellen
T1.4 - document: "Erstell ein Angebot für KI-Automatisierung" → DOCX
T1.5 - document: "Schreib einen Projektbericht" → PDF
T1.6 - Telegram: Datei senden → Timus analysiert sie mit data-Agent
T1.7 - Canvas: LEDs für data + document erscheinen korrekt
T1.8 - Routing-Test: 10 Beispielanfragen → korrekter Agent gewählt?
```

**Bestanden wenn:** Alle 8 Tests erfolgreich, keine Exceptions im Log

---
---

## Meilenstein 2 — `communication`

> Eigenständiger Agent. Keine neuen Tools nötig.
> Schreibt E-Mails, Briefe, LinkedIn-Nachrichten, Angebote in
> verschiedenen Tönen (professionell, freundlich, kurz, förmlich).

---

### Phase 2.1 — Agent-Kern + Prompt

**Was:**
- Neue Datei `agent/agents/communication.py`
- Spezialprompt: Kommunikations-Experte, kennt Ton/Stil-Varianten
- Modell: claude-sonnet (nuancierte Sprache, Stil-Kontrolle)

**Ton-Varianten die der Agent kennt:**
- professionell / förmlich (Geschäftsbriefe, Angebote)
- freundlich / locker (Freelance-Anfragen, Netzwerk)
- kurz / präzise (Follow-up, Reminder)
- motivierend (LinkedIn-Posts, Selbstpräsentation)

**Prompt-Schwerpunkte:**
- "Erkenne den Ton automatisch aus dem Kontext"
- "Frage nach Empfänger und Zweck wenn unklar"
- "Gib immer Betreff + vollständigen Text aus"
- "Für LinkedIn-Posts: mit Hashtags, max 300 Wörter"

**Deliverable:** `agent/agents/communication.py`

---

### Phase 2.2 — Output-Optionen

**Was:**
- Kommunikations-Ergebnisse können als TXT gespeichert werden (`create_txt`)
- Optional: direkt als DOCX (für formelle Briefe mit Briefkopf)
- Telegram: fertige Nachricht direkt als Text zurück (kein Datei-Overhead)

**Deliverable:** Flexibler Output-Kanal implementiert

---

### Phase 2.3 — Dispatcher-Integration M2

**Was:**
- Dispatcher-Routing für `communication`
- `DISPATCHER_PROMPT` erweitern

**Routing-Regeln:**
- `communication` → "schreib eine E-Mail", "formuliere", "LinkedIn-Post", "Anschreiben", "Bewerbung", "Nachricht an", "Antwort auf"

**Deliverable:** Routing funktioniert, Agent erscheint in Canvas-LED

---

### Test M2 — Kommunikation

```
T2.1 - "Schreib eine E-Mail an einen potenziellen Kunden für KI-Automatisierung"
T2.2 - "Formuliere ein LinkedIn-Post über mein Timus-Projekt"
T2.3 - "Schreib ein kurzes Follow-up nach einem Gespräch"
T2.4 - "Erstelle ein professionelles Anschreiben für Malt.de"
T2.5 - Ton-Erkennung: selber Inhalt → professionell vs. freundlich
T2.6 - Canvas-LED: communication erscheint korrekt
```

**Bestanden wenn:** Alle 6 Tests erfolgreich, Texte qualitativ nutzbar

---

### Integration-Test M1 + M2

```
IT-A: "Analysiere meine Ausgaben (CSV) und schick mir eine E-Mail-Zusammenfassung"
      → data-Agent liest + berechnet → communication-Agent formuliert E-Mail
IT-B: "Erstell einen Kundenbericht als PDF und schreib ein Begleit-E-Mail"
      → document erstellt PDF → communication schreibt E-Mail
IT-C: Routing-Konsistenz: 20 Beispielanfragen, kein falscher Agent
```

---
---

## Meilenstein 3 — `system`

> Liest Logs, überwacht Prozesse, diagnostiziert Timus-eigene Fehler.
> Erfordert neue Shell-Read-Only Tools (kein Schreiben, kein Ausführen).

---

### Phase 3.1 — System-Tools (Read-Only)

**Was:** Neues Tool-Modul `tools/system_tool/` mit:

| Tool | Funktion |
|---|---|
| `read_log` | Letzte N Zeilen aus Logdatei lesen (timus_server.log etc.) |
| `get_processes` | Laufende Prozesse auflisten (psutil) |
| `get_system_stats` | CPU, RAM, Disk, Netzwerk |
| `search_log` | Fehler/Keywords in Logs suchen |
| `get_service_status` | systemd-Service-Status lesen |

**Sicherheit:** Nur lesen, kein Ausführen — klare Grenze zu M4 (shell)

**Deliverable:** `tools/system_tool/tool.py` mit allen 5 Tools

---

### Phase 3.2 — Agent-Kern + Prompt

**Was:**
- Neue Datei `agent/agents/system.py`
- Prompt: System-Administrator-Modus, diagnostisch, präzise
- Modell: gpt-4o (gut für Log-Analyse + strukturierte Ausgabe)

**Prompt-Schwerpunkte:**
- "Lese zuerst den relevanten Log-Abschnitt"
- "Erkenne Muster: ERROR, WARNING, Exception, Traceback"
- "Gib eine klare Diagnose: Was ist passiert? Warum? Wie beheben?"
- "Fasse kritische Ereignisse der letzten 24h zusammen"

**Deliverable:** `agent/agents/system.py`

---

### Phase 3.3 — Dispatcher-Integration M3

**Routing-Regeln:**
- `system` → "was ist im Log", "Fehler gestern Nacht", "Service-Status", "CPU-Auslastung", "was läuft gerade", "Timus-Fehler", "warum ist Timus abgestürzt"

**Deliverable:** Routing + Canvas-LED

---

### Test M3 — System-Monitor

```
T3.1 - "Was ist heute Nacht im Timus-Log passiert?"
T3.2 - "Zeig mir alle Errors der letzten 24 Stunden"
T3.3 - "Wie ist die aktuelle CPU/RAM-Auslastung?"
T3.4 - "Ist der timus.service aktiv?"
T3.5 - "Welche Python-Prozesse laufen gerade?"
T3.6 - Log mit absichtlichem ERROR-Eintrag → korrekte Diagnose?
T3.7 - Canvas-LED: system erscheint korrekt
```

**Bestanden wenn:** Alle 7 Tests erfolgreich, keine falschen Diagnosen

---

### Integration-Test M1 + M2 + M3

```
IT-D: "Analysiere den System-Status und erstell mir einen PDF-Bericht"
      → system liest Logs → data/document erstellt Bericht
IT-E: "Was ist im Log falsch gelaufen und schreib mir eine Zusammenfassung per E-Mail"
      → system diagnostiziert → communication formuliert
IT-F: 30 Routing-Tests quer durch alle 5 Agenten (data, document, communication,
      system + die 7 bestehenden) — Verwechslungen < 5%?
```

---
---

## Meilenstein 4 — `shell`

> Der mächtigste und risikoreichste Agent.
> Führt Bash-Befehle aus, startet Skripte, legt Cron-Jobs an.
> Erfordert mehrstufige Policy-Kontrolle.

---

### Phase 4.1 — Shell-Tool mit Policy-Layer

**Was:** Neues Tool `tools/shell_tool/tool.py`

**Tools:**
| Tool | Funktion | Einschränkung |
|---|---|---|
| `run_command` | Bash-Befehl ausführen | Whitelist + Timeout |
| `run_script` | Python/Bash-Skript aus results/ starten | Nur eigene Skripte |
| `list_cron` | Cron-Jobs anzeigen | read-only |
| `add_cron` | Cron-Job hinzufügen | Nur mit expliziter Bestätigung |

**Sicherheits-Policy (mehrstufig):**
1. **Blacklist:** `rm -rf`, `dd if=`, `mkfs`, `shutdown`, `reboot`, `:(){:|:&}` → sofort blockiert
2. **Whitelist-Modus:** Nur Befehle aus einer vordefinierten Liste erlaubt (konfigurierbar in `.env`)
3. **Timeout:** Jeder Befehl max. 30 Sekunden, dann Kill
4. **Audit-Log:** Jeder Befehl wird geloggt (Befehl + Ausgabe + Zeitstempel)
5. **Dry-Run-Option:** Befehl wird angezeigt aber nicht ausgeführt (zur Bestätigung)

**Deliverable:** `tools/shell_tool/tool.py` mit vollständigem Policy-Layer

---

### Phase 4.2 — Agent-Kern + Prompt

**Was:**
- Neue Datei `agent/agents/shell.py`
- Prompt: Vorsichtiger System-Operator, erklärt immer was er tun will
- Modell: claude-sonnet (beste Einschätzung von Risiken)

**Prompt-Schwerpunkte:**
- "Erkläre IMMER zuerst was der Befehl tut, bevor du ihn ausführst"
- "Bei destruktiven Operationen: Dry-Run zuerst"
- "Bevorzuge sichere Alternativen wenn vorhanden (z.B. read_file statt cat)"
- "Nach Ausführung: zeige Ausgabe und interpretiere sie"
- "Niemals mehrere gefährliche Befehle in Kette"

**Deliverable:** `agent/agents/shell.py`

---

### Phase 4.3 — Dispatcher-Integration M4

**Routing-Regeln (eng gefasst):**
- `shell` → explizite Kommandos: "führe aus", "starte das Skript", "lege einen Cron-Job an", "führe im Terminal aus"
- Nicht: "öffne App" (→ visual), "lese Datei" (→ executor + read_file)

**Deliverable:** Routing + Canvas-LED + Policy-Log aktiv

---

### Test M4 — Shell (abgestufte Sicherheitstests)

```
T4.1 - Sicherer Befehl: "zeig mir alle Python-Dateien in ~/dev/timus"
        → ls oder find, korrekte Ausgabe
T4.2 - Mittelriskant: "starte mein Backup-Skript"
        → Dry-Run zuerst, dann Ausführung
T4.3 - Cron-Job anlegen: "erinnere mich täglich um 08:00"
        → crontab-Eintrag korrekt
T4.4 - Blacklist-Test: "lösche alle tmp-Dateien mit rm -rf /tmp/*"
        → BLOCKIERT, Erklärung warum
T4.5 - Blacklist-Test: "rm -rf /"
        → sofort BLOCKIERT, kein Dry-Run
T4.6 - Timeout-Test: Endlos-Schleife → nach 30s abgebrochen
T4.7 - Audit-Log: Alle Befehle aus T4.1–T4.3 im Log nachweisbar
T4.8 - Canvas-LED: shell erscheint korrekt
```

**Bestanden wenn:** T4.4 + T4.5 definitiv blockiert, T4.1–T4.3 funktional

---
---

## Gesamttest — Alle 12 Agenten

> Sicherstellung dass neue Agenten die bestehenden nicht stören
> und das gesamte System stabil bleibt.

---

### GT-1 — Routing-Konsistenz (alle Agenten)

50 Beispielanfragen quer durch alle 12 Agenten:

```
executor, research, reasoning, creative, development, meta, visual,
data, document, communication, system, shell
```

Erwartung: Verwechslungsrate < 5% (max. 2–3 falsche Routings)

---

### GT-2 — Tool-Konflikte

```
GT-2.1 - Zwei Agenten gleichzeitig aktiv (meta orchestriert data + document)
GT-2.2 - Tool-Doppelbenutzung: read_file gleichzeitig von data + system
GT-2.3 - results/-Verzeichnis: Mehrere Agenten schreiben gleichzeitig
GT-2.4 - SSE/Canvas: Alle 12 LEDs korrekt, kein Durcheinander
```

---

### GT-3 — Telegram-End-to-End

```
GT-3.1 - Datei senden → data analysiert → Bericht als PDF zurück
GT-3.2 - "Schreib ein Angebot" → document erstellt → DOCX zurück
GT-3.3 - "Was ist im Log?" → system liest → Text-Antwort
GT-3.4 - Bild erstellen → creative → Foto zurück (Regression-Test)
GT-3.5 - Voice-Nachricht → Whisper → routing → Antwort als Voice
```

---

### GT-4 — Stabilitätstest (30 Minuten)

```
- Service durchgehend aktiv
- 20 aufeinanderfolgende Anfragen an verschiedene Agenten
- Kein Memory-Leak (RAM-Anstieg < 100 MB)
- Kein Agent bleibt dauerhaft auf "thinking" hängen
- SSE-Verbindung stabil (kein Reconnect nötig)
```

---

### GT-5 — Regression (bestehende Features)

```
- Canvas v2: Chat, LEDs, Tool-Anzeige, Upload — alles wie vor M1
- Autonome Task-Queue: Scheduler läuft weiter
- Telegram: alle bestehenden Commands (/tasks, /status, /remind)
- File-System-Tools: list_directory, search_files etc.
- document_creator: PDF, DOCX, XLSX noch funktional
```

---

## Zeitplan (grobe Orientierung)

| Meilenstein | Inhalt | Komplexität |
|---|---|---|
| M1 | data + document | mittel — Tools vorhanden |
| M2 | communication | niedrig — nur Prompt-Arbeit |
| M3 | system | mittel — neue Tools |
| M4 | shell | hoch — Policy-Layer kritisch |
| Gesamttest | alle 12 Agenten | — |

---

## Wichtige Dateien die bei jedem Meilenstein angefasst werden

```
agent/agents/<neuer_agent>.py       ← Agenten-Klasse
agent/prompts.py                    ← Systemprompte
main_dispatcher.py                  ← Routing-Logik
server/mcp_server.py                ← _KNOWN_AGENTS + Tool-Module
tools/<neues_tool>/tool.py          ← neue Tools (M1, M3, M4)
requirements.txt                    ← neue Abhängigkeiten
```

---

*Plan erstellt: 2026-02-22 — Timus Agent-Erweiterung v1*

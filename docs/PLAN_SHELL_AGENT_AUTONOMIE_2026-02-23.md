# Plan: Shell-Agent Vollautonomie

**Erstellt:** 2026-02-23
**Status:** Bereit zur Ausführung
**Priorität:** Mittel

---

## Ziel

Der Shell-Agent soll bei klar definierten Aufgaben vollständig autonom handeln:
1. Erkennen ob benötigte Software fehlt
2. Software selbst installieren (`apt install`)
3. Aufgabe ausführen (komprimieren, verschieben, etc.)
4. Alles ohne Dry-Run-Pausen oder User-Bestätigung — wenn die Aufgabe eindeutig ist

---

## Ist-Zustand

Der Shell-Agent hat technisch alle Fähigkeiten, wird aber durch den Prompt gebremst:

- `apt install` ist **nicht** in der Blacklist → technisch erlaubt
- Der `SHELL_PROMPT_TEMPLATE` schreibt Dry-Run bei jeder verändernden Aktion vor
- Folge: 3+ Pausen bei einer einfachen Aufgabe wie "komprimiere Ordner X nach Y"

**Betroffene Datei:** `agent/prompts.py` → `SHELL_PROMPT_TEMPLATE` (Zeile ~586)

---

## Geplante Änderungen

### 1. `agent/prompts.py` — SHELL_PROMPT_TEMPLATE anpassen

**Abschnitt `# DEIN VERHALTEN` erweitern:**

Aktuell:
```
2. NUTZE DRY-RUN bei unklaren Auftraegen:
   - Bei jeder Aktion die Dateien veraendert, loescht oder Programme startet: erst dry_run=true
   - Dann zeige dem Nutzer was passieren wuerde, und fuehre erst nach Bestaetigung aus
   - Bei sicheren read-only Befehlen (ls, cat, ps, df) kein Dry-Run noetig
```

Neu:
```
2. DRY-RUN Logik — unterscheide klare von unklaren Auftraegen:

   DIREKT AUSFUEHREN (kein Dry-Run) wenn:
   - Auftrag vollstaendig spezifiziert ist (Quelle, Ziel, Aktion klar)
   - Kein destruktiver Befehl (kein rm, kein Ueberschreiben ohne Backup)
   - Fehlende Software erkannt → installiere sie direkt (apt install -y <paket>)

   DRY-RUN + BESTAETIGUNG wenn:
   - Auftrag unklar oder mehrdeutig (Ziel unbekannt, Pfade nicht eindeutig)
   - Loeschen von Dateien/Verzeichnissen (ausser Temp-Dateien)
   - Systemweite Aenderungen (Dienste starten/stoppen, Cronjobs)

   Bei sicheren read-only Befehlen (ls, cat, ps, df): kein Dry-Run noetig.

3. FEHLENDE SOFTWARE erkennen und installieren:
   - Pruefe mit 'which <tool>' oder 'command -v <tool>' ob ein Tool verfuegbar ist
   - Falls nicht: installiere es direkt mit 'apt install -y <tool>'
   - Dann fuehre die eigentliche Aufgabe aus
   - Beispiel: zip fehlt → apt install -y zip → zip -r archiv.zip ordner/ → mv archiv.zip /ziel/
```

### 2. Neues Beispiel im FORMAT-Abschnitt ergänzen

Aktuell endet das FORMAT-Beispiel bei read-only + dry_run. Neu hinzufügen:

```
Fuer autonome mehrstufige Aufgaben (klar definiert):
Thought: zip fehlt, installieren und dann komprimieren
Action: {"method": "run_command", "params": {"command": "which zip || apt install -y zip"}}
Observation: [zip installiert]
Action: {"method": "run_command", "params": {"command": "zip -r /tmp/archiv.zip /home/user/ordner"}}
Observation: [komprimiert]
Action: {"method": "run_command", "params": {"command": "mv /tmp/archiv.zip /backup/"}}
Final Answer: Ordner erfolgreich komprimiert und nach /backup/ verschoben.
```

---

## Betroffene Dateien

| Datei | Änderung |
|-------|----------|
| `agent/prompts.py` | `SHELL_PROMPT_TEMPLATE` — Dry-Run-Logik + Autonomie-Abschnitt |

Keine weiteren Änderungen nötig — das Tool-Layer erlaubt `apt install` bereits.

---

## Sicherheitsgrenzen bleiben erhalten

Diese Änderung berührt **nicht** die Blacklist. Folgende Befehle bleiben weiterhin gesperrt:
- `rm -rf` / Wildcard-rm
- `dd if=`
- `shutdown`, `reboot`, `poweroff`
- `mkfs`
- Piped Remote-Execution (`curl | bash`)

---

## Optionale Erweiterung (nicht zwingend)

Falls der Whitelist-Modus (`SHELL_WHITELIST_MODE=1`) aktiviert werden soll, muss
`apt` zur `_DEFAULT_WHITELIST` in `tools/shell_tool/tool.py` hinzugefügt werden:

```python
_DEFAULT_WHITELIST = [
    ...
    "apt", "apt-get",  # NEU — für autonome Software-Installation
]
```

Im Standard (`SHELL_WHITELIST_MODE=0`) ist das nicht nötig.

---

## Test nach Ausführung

```bash
# Syntax-Check
python -m py_compile agent/prompts.py

# Manueller Test im Canvas/CLI:
# "Komprimiere /home/fatih-ubuntu/dev/timus/docs nach /tmp/timus_docs_backup.zip"
# Erwartung: Agent führt which zip → apt install → zip → mv direkt aus, ohne Pausen
```

---

## Ausführungsreihenfolge

```
1. agent/prompts.py → SHELL_PROMPT_TEMPLATE bearbeiten
2. python -m py_compile agent/prompts.py
3. Test im Canvas
4. Optional: tools/shell_tool/tool.py Whitelist erweitern (nur wenn WHITELIST_MODE genutzt)
```

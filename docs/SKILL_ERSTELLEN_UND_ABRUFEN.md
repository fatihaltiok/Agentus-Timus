# Skill Erstellen Und Abrufen

## Ziel
Diese Anleitung zeigt, wie du Skills in Timus gezielt erzeugst, testest und aufrufst.

## Voraussetzungen
1. MCP/Timus nach Tool-Änderungen neu starten.
2. Tool-Aufträge möglichst als eine zusammenhängende Eingabe senden.

## 1. Skill-Skeleton Erzeugen
Verwende `init_skill_tool` mit einem eindeutigen Namen.

Beispiel:
```text
Nutze nur Tool-Action init_skill_tool mit {"name":"stockholm-cafe-skill-test","description":"Create a curated list of cozy and vintage cafes in Stockholm.","resources":["scripts","references"],"examples":true,"path":"skills"} und danach Final Answer mit success, skill_name, skill_path.
```

## 2. Skill-Logik Implementieren
1. Lege die eigentliche Logik in `scripts/main.py` ab.
2. Schärfe Trigger und Nutzung in `SKILL.md`.
3. Hinterlege optionale Daten in `references/REFERENCE.md`.

Hinweis:
- `run_skill` bevorzugt bei SKILL.md-Skills ein Entry-Script wie `main.py`, `run.py`, `entrypoint.py`.

## 3. Skill Ausführen
```text
Nutze nur Tool-Action run_skill mit {"name":"stockholm-cafe-skill-test","params":{"query":"cozy vintage cafes stockholm","limit":8}} und danach Final Answer nur mit run_skill_result.
```

## 4. Skills Abfragen
1. Übersicht: `list_available_skills`
2. Details: `get_skill_details` mit `{"name":"<skill-name>"}`
3. Ausführen: `run_skill` mit `{"name":"<skill-name>","params":{...}}`

## 5. Typische Fehler Und Fixes
1. Fehler: `Skill '<name>' existiert bereits`
   - Skill wurde schon erstellt. Nicht erneut `init_skill_tool` mit demselben Namen aufrufen.
   - Stattdessen direkt `run_skill` nutzen oder neuen Namen verwenden.
2. Fehler: `Skill '<name>' nicht gefunden`
   - Mit `list_available_skills` prüfen, ob der Skill geladen ist.
   - Nach Änderungen ggf. MCP/Timus neu starten.
3. Prompt wird in mehrere Runs zerlegt
   - Einen kurzen, klaren Auftrag pro Run senden.
   - Kein fragmentiertes Nachschieben von `1)`, `2)`, `3)` in separaten Turns.

## 6. Empfohlener Ablauf
1. Skill einmal mit `init_skill_tool` anlegen.
2. `scripts/main.py` implementieren.
3. Mit `run_skill` testen.
4. Mit `get_skill_details` und `list_available_skills` verifizieren.

# Milestone 6 Runbook (E2E + Rollout Readiness)

Stand: 2026-02-17

## Ziel
- End-to-End nachweisen, dass jeder `run_agent(...)` Aufruf deterministisch persistiert wird.
- Nachweisen, dass Working-Memory-Relevanz/Stats stabil abrufbar sind.
- Nachweisen, dass dynamischer Recall offene Anliegen innerhalb einer Session priorisiert.
- Einfache Go/No-Go Checks für lokalen Rollout bereitstellen.

## Automatische Checks

1. Quality-Gates (Milestone 5):
```bash
pytest -q tests/test_milestone5_quality_gates.py
```

2. E2E Readiness (Milestone 6):
```bash
pytest -q tests/test_milestone6_e2e_readiness.py
```

3. Schnellcheck ohne pytest:
```bash
python verify_milestone6.py
```

## Pass-Kriterien
- Alle oben genannten Commands enden ohne Fehler.
- `run_agent(...)` schreibt Events in `interaction_events` für:
  - Standardpfad (`status=completed`, `execution_path=standard`)
  - Fehlerpfad (`status=error`, `metadata.error=agent_not_found`)
- Event-Metadaten enthalten `memory_snapshot` (Standard- und Fehlerpfad).
- Working-Memory Stats sind verfügbar (`status` Feld vorhanden).
- Working-Memory Stats enthalten dynamische Felder:
  - `focus_terms_count`
  - `prefer_unresolved`
- Bei `status=ok` gilt: `final_chars <= max_chars`.
- Dynamischer Recall (`unified_recall`) liefert bei Querys wie "was ist aktuell offen"
  session-nahe, ungelöste Anliegen als Top-Treffer.

## Operative Empfehlung vor Produktivbetrieb
- `WORKING_MEMORY_INJECTION_ENABLED=true` belassen.
- Start-Budget konservativ halten:
  - `WORKING_MEMORY_CHAR_BUDGET=3200`
  - `WORKING_MEMORY_MAX_RELATED=4`
  - `WORKING_MEMORY_MAX_RECENT_EVENTS=6`
- Logs auf diese Marker überwachen:
  - `Deterministisches Logging gespeichert`
  - `Working-Memory-Kontext injiziert`

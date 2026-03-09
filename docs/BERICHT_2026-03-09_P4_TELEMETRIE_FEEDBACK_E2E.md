# Bericht 2026-03-09: P4.1 bis P4.3

## Ziel

Nach den gruenen `P0` bis `P3`-Gates wurden drei weitere Produktionsachsen gehaertet:

1. `P4.1` Telemetrie-/Startlog-Bereinigung
2. `P4.2` Autonomie- und Feedback-Lernen wirksamer machen
3. `P4.3` E2E-Live-Haertung der Kernflows

## P4.1 Telemetrie-/Startlog-Bereinigung

### Problem

Beim Start der Services tauchten wiederholt ChromaDB-/PostHog-Warnungen auf, unter anderem:

- `Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given`
- `Failed to send telemetry event ClientCreateCollectionEvent: capture() takes 1 positional argument but 3 were given`

Diese Meldungen waren kein direkter Service-Crash, aber unnoetiges Produktionsrauschen.

### Umsetzung

- Neue gemeinsame Runtime-Hilfe in [chroma_runtime.py](/home/fatih-ubuntu/dev/timus/utils/chroma_runtime.py)
  - setzt `ANONYMIZED_TELEMETRY=FALSE`
  - deaktiviert die Chroma-Telemetrie-Logger frueh im Prozess
  - liefert eine gemeinsame `Settings(...)`-Erzeugung fuer Chroma-Clients
- MCP-Server auf gemeinsame Chroma-Runtime umgestellt in [mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- Memory-System auf gemeinsame Chroma-Runtime umgestellt in [memory_system.py](/home/fatih-ubuntu/dev/timus/memory/memory_system.py)

### Live-Verifikation

Nach einem echten Restart von `timus-dispatcher.service` und `timus-mcp.service` am **9. Maerz 2026 um 22:14 CET**:

- beide Services starteten sauber
- [health](/home/fatih-ubuntu/dev/timus/server/mcp_server.py) antwortete wieder `healthy`
- im Journal seit `2026-03-09 22:14:20` gab es **keinen** Treffer mehr auf:
  - `Failed to send telemetry`
  - `capture() takes`
  - `chromadb`
  - `posthog`

Der fruehere Qdrant-Startkonflikt blieb ebenfalls verschwunden.

## P4.2 Feedback-Lernen wirksamer machen

### Problem

Das bisherige Feedback-System speicherte Signale und verschob Ziel-Scores, aber es war zu leicht, schon mit sehr wenig Evidenz operative Biases zu erzeugen.

### Umsetzung

- Evidenz-Gewichtung in [feedback_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/feedback_engine.py)
  - `feedback_evidence_confidence(...)`
  - `get_target_stats(...)`
  - `get_effective_target_score(...)`
- Dispatcher-Bias gehaertet in [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - Bias nur noch fuer komplexe Aufgaben
  - Bias nur noch mit ausreichender Evidenz
  - Logging jetzt mit Evidenzzaehlern
- Curiosity-Scoring auf effektive statt rohe Target-Scores umgestellt in [curiosity_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/curiosity_engine.py)
- Reflection-Pattern-Akkumulation auf effektive Scores umgestellt in [session_reflection.py](/home/fatih-ubuntu/dev/timus/orchestration/session_reflection.py)
- Visual-Recovery-Praeferenz auf effektive Scores umgestellt in [visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)

### Wirkung

Feedback wirkt jetzt konservativer und glaubwuerdiger:

- wenig Evidenz -> nur schwache Wirkung
- genug Evidenz -> voller Score-Effekt
- operative Teilpfade (`dispatcher`, `curiosity`, `visual`, `reflection`) reagieren nicht mehr ueber

## P4.3 Weitere E2E-Live-Haertung

### Problem

Die E2E-Matrix erkannte bisher harte Ausfaelle gut, aber degradierte Kernflows konnten im Gesamtstatus noch als `pass` durchrutschen.

### Umsetzung

- Drift-/Degradationssignale in [e2e_regression_matrix.py](/home/fatih-ubuntu/dev/timus/orchestration/e2e_regression_matrix.py)
  - Warnschwelle fuer `mcp_health.latency_ms`
  - lokale Drift-Signale aus `agent_status` und `autonomy_health`
  - `ops.state=warn|critical` wirkt auf `restart_recovery`
- Statuslogik korrigiert:
  - `ok + degraded` -> `warn`
  - `overall` wird jetzt `warn`, sobald Warnflows existieren

### Wirkung

Die Kernflow-Matrix unterscheidet jetzt klar zwischen:

- `pass`: alles gesund
- `warn`: Kernfluss lebt, aber driftet oder ist degradiert
- `fail`: echter Ausfall

Das verbessert die Aussagekraft fuer Release-/Canary-Gates und Runtime-Holds.

## Verifikation

### Test- und Formallaeufe

- `python -m py_compile` auf allen geaenderten P4-Dateien: gruen
- `pytest -q tests/test_m16_feedback.py tests/test_e2e_regression_matrix.py tests/test_m16_feedback_contracts.py tests/test_e2e_regression_matrix_contracts.py`
  - `33 passed`
- `pytest -q tests/test_m16_integration.py tests/test_visual_improvements.py`
  - `34 passed`
- gezielte Dispatcher-Feedback-Tests liefen bis zu `.....` gruen; der Prozess fiel danach erneut in den bekannten `main_dispatcher`-Teardown-Haenger
- `python -m crosshair check tests/test_m16_feedback_contracts.py --analysis_kind=deal`
  - gruen
- `python -m crosshair check tests/test_e2e_regression_matrix_contracts.py --analysis_kind=deal`
  - gruen
- `lean lean/CiSpecs.lean`
  - gruen
- `python scripts/run_production_gates.py`
  - `READY | total=4 passed=4 failed=0 skipped=0 blocking_failed=0`

## Live-Betriebsprobe

Nach dem echten Restart am **9. Maerz 2026 um 22:14 CET**:

- `timus-dispatcher.service`: `active (running)`
- `timus-mcp.service`: `active (running)`
- `/health`: `healthy`
- keine neuen Journal-Treffer auf:
  - Chroma-/PostHog-Telemetriefehler
  - Qdrant-Lock-Konflikt
  - `coroutine ... was never awaited`

## Restpunkte

Diese Punkte sind nach diesem Schnitt noch offen, aber nicht Blocker fuer den erreichten P4-Stand:

- gezielte `pytest`-Laeufe mit `main_dispatcher` haengen weiterhin im bekannten Teardown-/Import-Seiteneffekt
- ein gezielter `bandit`-Scan auf [memory_system.py](/home/fatih-ubuntu/dev/timus/memory/memory_system.py) zeigt dort weiterhin alte `md5`-Bestandsstellen; das lag ausserhalb dieses P4-Schnitts und blockiert den aktuellen Gate-Runner nicht

## Fazit

Mit `P4.1` bis `P4.3` ist der Produktionsstand wieder klarer und glaubwuerdiger:

- Startlogs sind deutlich ruhiger
- Feedback-Lernen ist vorsichtiger und evidenzbasiert
- E2E-Gates sehen jetzt auch degradierte statt nur tote Kernflows
- der Produktions-Gate-Runner bleibt insgesamt gruen

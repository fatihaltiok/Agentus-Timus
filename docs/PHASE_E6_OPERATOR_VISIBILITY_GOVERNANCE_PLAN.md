# Phase E6 Plan - Operator Visibility und Governance

Stand: 2026-04-16

## Ziel

E6 schliesst Phase E nicht mit noch mehr Autonomie, sondern mit einer haerteren Operatorsicht und klareren Governance ab.

Der Kern ist:

- Improvement und Memory-Curation sollen nicht nur laufen, sondern fuer den Operator als zusammenhaengende Lanes sichtbar sein
- Risk-/Approval-Grenzen sollen fuer hoehere Eingriffe explizit und steuerbar werden
- Timus soll erklaeren koennen:
  - was er verbessern will
  - was er zuletzt getan hat
  - was blockiert ist
  - was zurueckgerollt wurde
  - was auf Approval wartet

E6 ist damit keine neue Engine-Phase, sondern ein Abschlussblock fuer:

- zentrale Laufzeitsicht
- Governance-Transparenz
- Approval-Pfade fuer hohe Risikoklassen
- klare Operator-Entscheidbarkeit

## Warum E6 jetzt sinnvoll ist

Die technischen Grundlagen sind jetzt da:

- E1-E4 liefern Improvement-Kandidaten, Ausfuehrung, Verifikation und Rollout-Governance
- E5 liefert kontrollierte Memory-Curation inklusive Retrieval-Gates, Rollback und zentraler Runtime-Sicht
- MCP, Dispatcher und Observation haben bereits mehrere Operatorsurfaces

Was noch fehlt, ist die Schicht darueber:

- eine einheitliche Operator-Sicht ueber diese Lanes
- eine klare Pending-/Approval-Sicht fuer hoehere Risiken
- eine kurze, belastbare Antwort auf die Frage:
  - "Was macht Timus gerade autonom und warum?"

## Ausgangslage im Repo

Bereits vorhanden:

- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - zentrale Laufzeitaggregation
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - Operatorschnittstellen:
    - `/autonomy/observation`
    - `/autonomy/improvement`
    - `/autonomy/memory_curation`
    - `/health`
- [tools/self_improvement_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/self_improvement_tool/tool.py)
  - zentrale Improvement-/Ops-Tool-Surface
- [orchestration/self_hardening_rollout.py](/home/fatih-ubuntu/dev/timus/orchestration/self_hardening_rollout.py)
  - Rollout- und Freeze-Logik
- [orchestration/approval_auth_contract.py](/home/fatih-ubuntu/dev/timus/orchestration/approval_auth_contract.py)
  - vorhandene Approval-/Auth-Muster
- [gateway/dispatcher_health_server.py](/home/fatih-ubuntu/dev/timus/gateway/dispatcher_health_server.py)
  - Dispatcher-Lifecycle und Readiness

Die aktuelle Luecke:

- die Sicht ist verteilt
- Risk-/Approval-Zustaende sind nicht als einheitliche Lane sichtbar
- es gibt noch keinen klaren Operator-Block fuer:
  - letzte autonome Aktion
  - letzte Blockade
  - letzter Rollback
  - Pending Approval
  - naechste freigaberelevante Entscheidung

## Leitprinzipien

1. One operator model across surfaces
- dieselben Zustaende duerfen in Tool, MCP, Observation und spaeter UI nicht unterschiedlich heissen

2. Explain before approve
- wenn Timus Approval braucht, muss der Operator vorher sehen:
  - warum
  - fuer welche Lane
  - mit welchem Risiko
  - mit welchem erwarteten Effekt

3. Governance is state, not prose
- `allow`, `blocked`, `rollback_active`, `approval_required`, `frozen` muessen als harte Zustandswerte sichtbar sein

4. Last action matters
- der Operator muss nicht nur Kandidaten sehen, sondern die juengste tatsaechliche autonome Wirkung

5. No hidden high-risk autonomy
- hoehere Risikoklassen duerfen nicht nur intern geblockt werden
- sie muessen sichtbar als Pending-/Blocked-/Approval-Fall auftauchen

## Phase-E6-Struktur

### E6.1 Unified Operator Snapshot

Ziel:

- eine gemeinsame, knappe Operatorsicht ueber Improvement, Memory-Curation, Rollout und Systemzustand

Stand:

- erster Runtime-Slice umgesetzt

Schwerpunkte:

- konsolidierter Snapshot fuer:
  - Improvement-Lane
  - Memory-Curation-Lane
  - Rollout-/Freeze-/Rollback-Zustaende
  - Service-/Health-Kontext
- gemeinsame Felder wie:
  - `state`
  - `blocked`
  - `reasons`
  - `last_action`
  - `last_completed_at`
  - `last_rollback`
  - `next_candidates`
- MCP- und Tool-Surface fuer denselben Snapshot

Technische Anker:

- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- [tools/self_improvement_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/self_improvement_tool/tool.py)

Erfolgskriterium:

- ein Operator kann mit einem Call sehen, welche Phase-E-Lanes aktiv, geblockt oder erfolgreich gelaufen sind

Umgesetzt:

- neuer Snapshot-Builder in [orchestration/phase_e_operator_snapshot.py](/home/fatih-ubuntu/dev/timus/orchestration/phase_e_operator_snapshot.py)
  - konsolidiert jetzt:
    - System-/Service-Kontext
    - Improvement-Lane
    - Memory-Curation-Lane
    - letzte Lane-Aktivitaet
    - naechste Kandidaten
- neue Tool-Surface in [tools/self_improvement_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/self_improvement_tool/tool.py)
  - `get_phase_e_operator_snapshot(...)`
- neuer MCP-Endpoint in [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - `GET /autonomy/operator_snapshot`
- Contract-Abdeckung in:
  - [tests/test_phase_e_operator_snapshot.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot.py)
  - [tests/test_phase_e_operator_snapshot_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot_hypothesis.py)
  - [tests/test_phase_e_operator_snapshot_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot_crosshair.py)
  - [tests/test_self_improvement_tool_ops.py](/home/fatih-ubuntu/dev/timus/tests/test_self_improvement_tool_ops.py)
  - [tests/test_c2_entrypoints.py](/home/fatih-ubuntu/dev/timus/tests/test_c2_entrypoints.py)

Verifikation:

- `pytest -q tests/test_phase_e_operator_snapshot.py tests/test_phase_e_operator_snapshot_hypothesis.py tests/test_self_improvement_tool_ops.py tests/test_c2_entrypoints.py` -> `25 passed`
- `python -m crosshair check tests/test_phase_e_operator_snapshot_crosshair.py` -> Exit `0`

### E6.2 Governance-Risk Surface

Ziel:

- Risk-, Freeze- und Rollback-Entscheidungen als explizite Governance-Sicht sichtbar machen

Stand:

- erster Runtime-Slice umgesetzt

Schwerpunkte:

- gemeinsame Darstellung fuer:
  - `strict_force_off`
  - `rollout_frozen`
  - `rollback_active`
  - `verification_backpressure`
  - `retrieval_backpressure`
  - Degraded-Mode
- letzte Governance-Aktion:
  - `allow`
  - `hold`
  - `freeze`
  - `rollback`
- kurze Begruendungsfelder statt verstreuter Einzelreasons

Technische Anker:

- [orchestration/improvement_task_autonomy.py](/home/fatih-ubuntu/dev/timus/orchestration/improvement_task_autonomy.py)
- [orchestration/memory_curation.py](/home/fatih-ubuntu/dev/timus/orchestration/memory_curation.py)
- [orchestration/self_hardening_rollout.py](/home/fatih-ubuntu/dev/timus/orchestration/self_hardening_rollout.py)

Erfolgskriterium:

- die aktuelle Governance-Lage von Phase E ist ohne Log-Lesen ablesbar

Umgesetzt:

- [orchestration/phase_e_operator_snapshot.py](/home/fatih-ubuntu/dev/timus/orchestration/phase_e_operator_snapshot.py)
  - neuer zentraler `governance`-Block im Operator-Snapshot
  - vereinheitlicht jetzt:
    - `strict_force_off`
    - `rollout_frozen`
    - `rollback_active`
    - `verification_backpressure`
    - `retrieval_backpressure`
    - `degraded_mode`
  - zeigt pro Lane:
    - `state`
    - `action`
    - `risk_class`
    - `active_states`
    - `shadowed_states`
    - `signals`
  - zeigt zentral:
    - `action`
    - `highest_risk_class`
    - `active_states`
    - `blocked_lanes`
- vorhandene MCP-/Tool-Surface aus E6.1 liefert diesen Governance-Block jetzt automatisch mit
- Contract-Abdeckung erweitert in:
  - [tests/test_phase_e_operator_snapshot.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot.py)
  - [tests/test_phase_e_operator_snapshot_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot_hypothesis.py)
  - [tests/test_phase_e_operator_snapshot_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot_crosshair.py)
  - [tests/test_self_improvement_tool_ops.py](/home/fatih-ubuntu/dev/timus/tests/test_self_improvement_tool_ops.py)
  - [tests/test_c2_entrypoints.py](/home/fatih-ubuntu/dev/timus/tests/test_c2_entrypoints.py)

Verifikation:

- `pytest -q tests/test_phase_e_operator_snapshot.py tests/test_phase_e_operator_snapshot_hypothesis.py tests/test_self_improvement_tool_ops.py tests/test_c2_entrypoints.py` -> `26 passed`
- `python -m crosshair check tests/test_phase_e_operator_snapshot_crosshair.py` -> Exit `0`

### E6.3 Approval Paths for Higher Risk Classes

Ziel:

- hoehere Risikoklassen nicht nur blocken, sondern als entscheidbare Approval-Faelle fuehren

Stand:

- erster Runtime-Slice umgesetzt

Schwerpunkte:

- Risk-Klassen fuer Approval explizit schneiden:
  - hoehere Self-Modify-Risiken
  - Rollout-Promotions
  - Rollback-Freigaben mit Nebenwirkung
  - spaeter aggressivere Memory-Curation-Aktionen
- Pending-Approval-Sicht mit:
  - lane
  - risk_class
  - requested_action
  - rationale
  - evidence
  - rollback_path
- Approval-/Reject-/Expire-Zustaende maschinenlesbar

Technische Anker:

- [orchestration/approval_auth_contract.py](/home/fatih-ubuntu/dev/timus/orchestration/approval_auth_contract.py)
- [orchestration/autonomy_change_control.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_change_control.py)
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)

Erfolgskriterium:

- hoehere Risikoklassen tauchen als explizite Pending-Entscheidungen statt als diffuse interne Sperren auf

Umgesetzt:

- [orchestration/phase_e_operator_snapshot.py](/home/fatih-ubuntu/dev/timus/orchestration/phase_e_operator_snapshot.py)
  - neuer zentraler `approval`-Block im Operator-Snapshot
  - zeigt jetzt:
    - `pending_count`
    - `highest_risk_class`
    - `requested_actions`
    - `lanes`
    - `oldest_pending_minutes`
    - konkrete `items`
  - pro Approval-Fall sichtbar:
    - `lane`
    - `risk_class`
    - `requested_action`
    - `approval_reason`
    - `rationale`
    - `evidence`
    - `rollback_path`
  - nutzt dafuer die bestehenden Pending-Approval-Requests aus [orchestration/autonomy_change_control.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_change_control.py)
- vorhandene MCP-/Tool-Surface aus E6.1/E6.2 liefert den Approval-Block jetzt automatisch mit
- Contract-Abdeckung erweitert in:
  - [tests/test_phase_e_operator_snapshot.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot.py)
  - [tests/test_phase_e_operator_snapshot_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot_hypothesis.py)
  - [tests/test_phase_e_operator_snapshot_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot_crosshair.py)
  - [tests/test_self_improvement_tool_ops.py](/home/fatih-ubuntu/dev/timus/tests/test_self_improvement_tool_ops.py)
  - [tests/test_c2_entrypoints.py](/home/fatih-ubuntu/dev/timus/tests/test_c2_entrypoints.py)

Verifikation:

- `pytest -q tests/test_phase_e_operator_snapshot.py tests/test_phase_e_operator_snapshot_hypothesis.py tests/test_self_improvement_tool_ops.py tests/test_c2_entrypoints.py` -> `28 passed`
- `python -m crosshair check tests/test_phase_e_operator_snapshot_crosshair.py` -> Exit `0`

### E6.4 Recent Action and Incident Explainability

Ziel:

- juengste autonome Wirkung und juengste Problemfaelle kurz und belastbar erklaerbar machen

Stand:

- erster Runtime-Slice umgesetzt

Schwerpunkte:

- operator-orientierter Feed fuer:
  - letzte Improvement-Aktion
  - letzte Memory-Curation-Aktion
  - letzter Rollback
  - letzte Blockade
  - juengster fehlgeschlagener Lauf
- kurze Payloads:
  - `when`
  - `lane`
  - `action`
  - `result`
  - `why`
  - `what_changed`
- klare Verknuepfung zu Observation-/Incident-Trace

Technische Anker:

- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)

Erfolgskriterium:

- der Operator kann die letzte autonome Wirkung in wenigen Zeilen rekonstruieren

Umgesetzt:

- [orchestration/phase_e_operator_snapshot.py](/home/fatih-ubuntu/dev/timus/orchestration/phase_e_operator_snapshot.py)
  - neuer zentraler `explainability`-Block im Operator-Snapshot
  - zeigt jetzt:
    - `latest_by_lane`
    - `latest_block`
    - `latest_failure`
    - `latest_rollback`
    - `recent_feed`
  - jede Explainability-Entry enthaelt:
    - `when`
    - `lane`
    - `action`
    - `result`
    - `why`
    - `what_changed`
    - `refs`
  - `refs` traegt:
    - `request_id`
    - `incident_key`
    - `task_id`
    - `snapshot_id`
    - `ref_id`
- Summary erweitert um:
  - `explainability_latest_at`
  - `explainability_count`
- vorhandene MCP-/Tool-Surface liefert den Explainability-Block jetzt automatisch mit
- Contract-Abdeckung erweitert in:
  - [tests/test_phase_e_operator_snapshot.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot.py)
  - [tests/test_phase_e_operator_snapshot_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot_hypothesis.py)
  - [tests/test_phase_e_operator_snapshot_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_e_operator_snapshot_crosshair.py)
  - [tests/test_self_improvement_tool_ops.py](/home/fatih-ubuntu/dev/timus/tests/test_self_improvement_tool_ops.py)
  - [tests/test_c2_entrypoints.py](/home/fatih-ubuntu/dev/timus/tests/test_c2_entrypoints.py)

Verifikation:

- `pytest -q tests/test_phase_e_operator_snapshot.py tests/test_phase_e_operator_snapshot_hypothesis.py tests/test_self_improvement_tool_ops.py tests/test_c2_entrypoints.py` -> `30 passed`
- `python -m crosshair check tests/test_phase_e_operator_snapshot_crosshair.py` -> Exit `0`

### E6.5 Surface Closeout for Canvas / MCP / Tooling

Ziel:

- die E6-Sicht nicht nur im Backend, sondern konsistent auf den realen Operatorsurfaces verfuegbar machen

Schwerpunkte:

- MCP-Endpoints liefern denselben Governance-/Snapshot-Vertrag
- Self-Improvement-Tool liefert dieselbe Sicht
- Canvas-/spaetere UI-Surfaces koennen direkt darauf aufsetzen
- keine zweite konkurrierende Begriffswelt in UI und API

Technische Anker:

- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- [tools/self_improvement_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/self_improvement_tool/tool.py)
- spaeter Canvas-Surface

Erfolgskriterium:

- E6 ist abgeschlossen, wenn MCP und Tooling dieselbe Operator-Sicht ohne Sonderlogik bereitstellen

## Reihenfolge innerhalb von E6

1. E6.1 Unified Operator Snapshot
2. E6.2 Governance-Risk Surface
3. E6.3 Approval Paths for Higher Risk Classes
4. E6.4 Recent Action and Incident Explainability
5. E6.5 Surface Closeout for Canvas / MCP / Tooling

Begruendung:

- zuerst braucht es eine gemeinsame Sicht
- dann die explizite Governance-Lage
- danach koennen Approval-Faelle sauber modelliert werden
- zuletzt wird die Sicht fuer Tooling und spaetere UI-Surfaces konsolidiert

## Nicht Ziel von E6

- keine neue Improvement-Engine
- kein weiterer Memory-Curation-Algorithmus
- keine allgemeine Mehrschritt-Planung
- kein volles UI-Redesign
- kein aggressiver Ausbau freier Selbstmodifikation

## Abschlusskriterium fuer Phase E

Phase E ist insgesamt abgeschlossen, wenn nach E6 gilt:

- Improvement und Memory-Curation sind als Lanes zentral sichtbar
- Governance-Zustaende sind einheitlich benannt und operatorsichtbar
- hoehere Risikoklassen koennen als Pending-Approval-Faelle erscheinen
- letzte autonome Wirkung und letzte Blockade sind schnell erklaerbar
- Tooling, Observation und MCP liefern dieselbe Phase-E-Operatorsicht

Danach ist der naechste grosse Block:

- [Phase F Plan](/home/fatih-ubuntu/dev/timus/docs/PHASE_F_PLAN.md)

# Phase E Plan - Self-Improvement und kontrollierte Selbstpflege

Stand: 2026-04-11

## Ziel

Phase E baut auf D0 und Phase D auf und macht aus Timus kein "frei drehendes" System, sondern ein kontrolliert selbstverbesserndes System.

Der Kern ist:

- Timus erkennt wiederkehrende Schwaechen aus Live-Betrieb, Beobachtung und Verlaufsdaten
- Timus uebersetzt diese Schwaechen in konkrete, pruefbare Verbesserungsmaßnahmen
- nur ein konservativer Teil davon darf halb- oder vollautonom ausgefuehrt werden
- jede Ausfuehrung bleibt beobachtbar, verifizierbar und notfalls ruecknehmbar

Phase E ist damit keine "mehr Freiheit"-Phase, sondern eine Phase fuer:

- bessere Diagnostik
- bessere Priorisierung
- sichere Hardening-Schleifen
- spaetere kontrollierte Gedaechtnispflege

## Warum Phase E jetzt sinnvoll ist

Die noetigen Voraussetzungen sind inzwischen vorhanden:

- D0 liefert semantischen Gespraechszustand, Topic-Historie, Praeferenzen, Self-Model und Context-Propagation
- Phase D liefert Approval, Auth, user-mediated Login, Session-Reuse und Challenge-Handover
- Observability und Runtime-Korrelation sind ausgebaut

Damit kann Phase E auf belastbaren Signalen aufsetzen, statt auf unscharfen Chat- oder Log-Fetzen.

## Bereits vorhandene Bausteine im Repo

Phase E startet nicht bei null. Wichtige bestehende Bausteine sind:

- [orchestration/self_improvement_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_improvement_engine.py)
  - M12 Self-Improvement Engine
- [orchestration/session_reflection.py](/home/fatih-ubuntu/dev/timus/orchestration/session_reflection.py)
  - wiederkehrende Pattern-Erkennung und Improvement-Suggestions
- [orchestration/meta_analyzer.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_analyzer.py)
  - kritische Self-Improvement-Befunde als Meta-Input
- [orchestration/autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)
  - Heartbeat-/Autonomy-Loop als Integrationspunkt
- [orchestration/self_modifier_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_modifier_engine.py)
  - kontrollierte Codeaenderungen, Verifikation, Canary, Change-Memory
- [orchestration/self_hardening_rollout.py](/home/fatih-ubuntu/dev/timus/orchestration/self_hardening_rollout.py)
  - konservative Rollout-Stufen
- [orchestration/autonomy_change_control.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_change_control.py)
  - Approval-/Change-Control-Muster
- [tools/maintenance_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/maintenance_tool/tool.py)
  - `run_memory_maintenance` als Ausgangspunkt fuer spaetere Memory-Curation

Phase E soll diese vorhandenen Bausteine ordnen, begrenzen und semantisch besser verbinden.

## Leitprinzipien

1. Observation vor Action
- keine Verbesserung ohne konkrete Laufzeit- oder Verlaufssignale

2. Diagnosis vor Fix
- nicht direkt "selbst patchen", sondern erst Problemklasse sauber bestimmen

3. Safe subset first
- zuerst nur kleine, klar begrenzte Verbesserungen
- keine grossen Refactors als Phase-E-Start

4. Verify before and after
- jede Massnahme braucht Vorher-/Nachher-Nachweis

5. Rollback ist Pflicht
- wenn Verifikation oder Canary kippt, muss Ruecknahme moeglich sein

6. No secret expansion
- Phase E darf keine Abkuerzung fuer Credentials, 2FA oder andere harte Grenzen werden

7. No self-scoring shortcuts
- Timus darf seinen Autonomy-Score nicht "optimieren", indem er nur Metriken glatter macht
- Ziel ist reale Qualitaetsverbesserung, nicht Score-Kosmetik

## Phase-E-Struktur

### E1. Improvement Signal Pipeline

Ziel:

- Beobachtungsereignisse, Reflection-Signale und wiederkehrende Fehlmuster in ein gemeinsames Verbesserungsformat bringen

Schwerpunkte:

- gemeinsame Taxonomie fuer Schwachstellen:
  - routing
  - context
  - policy
  - runtime
  - tool
  - specialist
  - memory
  - UX / handoff
- Dedupe, Severity und Confidence
- Trennung zwischen:
  - einmaligem Ausreisser
  - wiederkehrendem Pattern
  - kritischem strukturellem Fehler

Technische Anker:

- [orchestration/self_improvement_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_improvement_engine.py)
- [orchestration/session_reflection.py](/home/fatih-ubuntu/dev/timus/orchestration/session_reflection.py)
- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
- [orchestration/meta_analyzer.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_analyzer.py)

Erfolgskriterium:

- Timus kann aus mehreren gleichartigen Live-Faellen einen deduplizierten, priorisierten Improvement-Kandidaten erzeugen

### E1.1 Improvement Signal Normalization

Stand:

- erster Runtime-Slice gestartet

Umgesetzt:

- gemeinsames Normalisierungsformat in [orchestration/improvement_candidates.py](/home/fatih-ubuntu/dev/timus/orchestration/improvement_candidates.py)
- M12-Suggestions aus [orchestration/self_improvement_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_improvement_engine.py) werden jetzt mit:
  - `candidate_id`
  - `source`
  - `category`
  - `problem`
  - `proposed_action`
  - `severity`
  - `confidence`
  - `evidence_level`
  - `evidence_basis`
  - `occurrence_count`
  - `status`
  angereichert
- M8-Reflection-Suggestions aus [orchestration/session_reflection.py](/home/fatih-ubuntu/dev/timus/orchestration/session_reflection.py) werden in dieselbe Candidate-Form ueberfuehrt
- [orchestration/meta_analyzer.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_analyzer.py) bevorzugt jetzt normalisierte Felder statt nur Legacy-`finding`/`type`
- [tools/self_improvement_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/self_improvement_tool/tool.py) und der MCP-Endpoint in [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py) exponieren die normalisierten Kandidaten jetzt direkt

Noch nicht Teil von E1.1:

- systemweite Dedupe ueber mehrere Quellen hinweg
- gemeinsame Severity-/Confidence-Kalibrierung ueber alle Improvement-Quellen
- automatische Promotion von Kandidaten in konkrete E2-Tasks

### E1.2 Taxonomie, Dedupe und Priorisierung

Stand:

- erster Runtime-Slice gestartet

Umgesetzt:

- gemeinsame Taxonomie in [orchestration/improvement_candidates.py](/home/fatih-ubuntu/dev/timus/orchestration/improvement_candidates.py) fuer:
  - `routing`
  - `context`
  - `policy`
  - `runtime`
  - `tool`
  - `specialist`
  - `memory`
  - `ux_handoff`
- Reflection-Kandidaten behalten `raw_category=reflection_pattern`, werden aber wenn moeglich auf die Phase-E-Taxonomie gemappt
- konservatives Cross-Source-Dedupe ueber:
  - `self_improvement_engine`
  - `session_reflection`
- priorisierte Consolidation mit:
  - `priority_score`
  - `priority_reasons`
  - `signal_class`
  - `merged_sources`
  - `source_count`
  - `merged_candidate_ids`
- [orchestration/session_reflection.py](/home/fatih-ubuntu/dev/timus/orchestration/session_reflection.py) liefert jetzt deduplizierte, priorisierte Kandidaten statt nur lose gemergter Suggestion-Listen
- [tools/self_improvement_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/self_improvement_tool/tool.py) und [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py) exponieren jetzt bevorzugt diese kombinierten Kandidaten

Noch offen fuer spaetere E1-Slices:

- echte Observation-/Incident-Signale als dritte Candidate-Quelle
- staerkere Similarity-Heuristik fuer paraphrasierte Duplicate
- systemweite Severity-/Confidence-Kalibrierung statt nur konservativer Merge-Regeln

### E1.3 Incident Signals als dritte Candidate-Quelle

Stand:

- erster Runtime-Slice gestartet

Umgesetzt:

- offene und fehlgeschlagene Self-Healing-Incidents werden jetzt als eigene Improvement-Kandidaten normalisiert
- neue Incident-Candidate-Form in [orchestration/improvement_candidates.py](/home/fatih-ubuntu/dev/timus/orchestration/improvement_candidates.py):
  - `source = self_healing_incident`
  - `evidence_level = incident`
  - `evidence_basis = self_healing_runtime`
- [orchestration/session_reflection.py](/home/fatih-ubuntu/dev/timus/orchestration/session_reflection.py) zieht jetzt zusaetzlich offene/fehlgeschlagene Incidents aus dem Self-Healing-Store in denselben deduplizierten Kandidatenstrom
- dadurch koennen Incident-Signale jetzt zusammen mit:
  - Reflection-Patterns
  - M12-Runtime-Suggestions
  priorisiert werden statt in einem separaten Diagnosepfad zu verbleiben

Noch offen fuer spaetere E1-Slices:

- echte Observation-Events aus `autonomy_observation` direkt als weitere Candidate-Quelle
- staerkere Incident-Dedupe ueber aehnliche, aber nicht identische Incident-Titel
- bessere Ableitung von `occurrence_count` aus Incident-Historie statt nur aus vorhandenem Detailzustand

### E1.4 Observation-Events als vierte Candidate-Quelle

Stand:

- erster Runtime-Slice gestartet

Umgesetzt:

- ausgewaehlte negative Runtime-/Routing-/Context-Events aus [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py) werden jetzt als Improvement-Kandidaten normalisiert
- neue Observation-Candidate-Form in [orchestration/improvement_candidates.py](/home/fatih-ubuntu/dev/timus/orchestration/improvement_candidates.py) fuer einen konservativen stabilen Event-Satz:
  - `dispatcher_meta_fallback`
  - `chat_request_failed`
  - `context_misread_suspected`
  - `specialist_signal_emitted` mit `context_mismatch` oder `needs_meta_reframe`
  - `communication_task_failed`
  - `send_email_failed`
  - `challenge_reblocked`
  - fehlerhafte `meta_direct_tool_call`
- [orchestration/session_reflection.py](/home/fatih-ubuntu/dev/timus/orchestration/session_reflection.py) zieht diese Observation-Events jetzt aus dem bestehenden Observation-Store in denselben kombinierten Kandidatenstrom
- unter Pytest wird das produktive Observation-Log dabei konservativ nicht implizit mitgelesen; Tests muessen die Observation-Quelle explizit einspeisen

Noch offen fuer spaetere E1-Slices:

- breitere Event-Abdeckung ueber den konservativen Kernsatz hinaus
- bessere Fenster-/Decay-Regeln fuer Observation-Kandidaten
- staerkere Similarity-Heuristik fuer paraphrasierte Observation-/Incident-Kollisionen

### E1.5 Candidate-Decay und Freshness-Regeln

Stand:

- erster Runtime-Slice gestartet

Umgesetzt:

- source-sensitive Freshness-Profile direkt in [orchestration/improvement_candidates.py](/home/fatih-ubuntu/dev/timus/orchestration/improvement_candidates.py)
  - `autonomy_observation` altert am schnellsten
  - `self_healing_incident` altert mittelfristig
  - `session_reflection` und `self_improvement_engine` bleiben laenger relevant
- konsolidierte Kandidaten tragen jetzt:
  - `freshness_score`
  - `freshness_state`
  - `freshness_age_days`
- `priority_score` wird jetzt nicht nur aus Severity/Confidence/Source-Count berechnet, sondern mit einem echten Freshness-Decay gewichtet
- alte Observation-/Incident-Signale bleiben sichtbar, dominieren aber nicht mehr automatisch gegen frische strukturelle Befunde

Noch offen fuer spaetere E1-Slices:

- feinere Freshness-Profile pro Kategorie statt nur pro Quelle
- decay-aware Dedupe-Entscheidungen bei sehr alten Duplicate

### E1.6 Operator Visibility fuer Candidate-Priorisierung

Stand:

- erster Runtime-Slice gestartet

Umgesetzt:

- [orchestration/improvement_candidates.py](/home/fatih-ubuntu/dev/timus/orchestration/improvement_candidates.py) erzeugt jetzt aus priorisierten Improvement-Kandidaten eine operator-lesbare Sicht:
  - `candidate_id`
  - `label`
  - `priority_score`
  - `freshness_score`
  - `freshness_state`
  - `signal_class`
  - `merged_sources`
  - `priority_reasons`
  - kompakte `summary`
- [tools/self_improvement_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/self_improvement_tool/tool.py) gibt diese Sicht als `top_candidate_insights` zusaetzlich zur rohen Candidate-Liste aus
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py) exponiert dieselbe operator-orientierte Sicht im `/autonomy/improvement`-Pfad
- damit wird jetzt nicht nur intern priorisiert, sondern auch sichtbar, warum ein Kandidat oben steht oder bereits zu altern beginnt

Noch offen fuer spaetere E1-Slices:

- Ranking-Erklaerungen ueber mehr als die Top-5-Kandidaten hinaus
- decay-aware Visualisierung direkt in Observation-/Dashboard-Reports
- spaetere Verknuepfung mit E2, damit aus sichtbaren Top-Kandidaten direkt konkrete Compiler-Tasks entstehen

### E2. Weakness-to-Task Compiler

Ziel:

- aus einem Improvement-Kandidaten wird eine konkrete, bearbeitbare Massnahme

Ausgabeformen:

- `developer_task`
- `shell_task`
- `config_change_candidate`
- `test_gap`
- `verification_needed`
- `do_not_autofix`

Schwerpunkte:

- klare Zustandsform:
  - problem
  - evidence
  - likely_root_cause
  - safe_fix_class
  - target_files
  - verification_plan
  - rollback_risk
- keine "ich sollte besser werden"-Texte mehr
- stattdessen konkrete, pruefbare Arbeitspakete

Technische Anker:

- [orchestration/self_improvement_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_improvement_engine.py)
- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
- [orchestration/specialist_context.py](/home/fatih-ubuntu/dev/timus/orchestration/specialist_context.py)

Erfolgskriterium:

- aus einem wiederkehrenden Fehler entsteht ein strukturierter Task mit Verifikationsplan statt nur ein Befund

### E3. Safe Self-Hardening Execution

Ziel:

- ein kleiner, sicherer Teil der Improvement-Tasks darf kontrolliert ausgefuehrt werden

Zuerst erlaubte Klassen:

- Guard-/Threshold-Haertung
- Prompt-/Routing-Haertung
- kleine Parser-/Normalizer-Fixes
- Beobachtungs- und Contract-Erweiterungen
- fokussierte Regressionstests

Zunaechst nicht erlaubt:

- grosse Refactors
- Architekturumbauten
- Secrets/Auth-Policy-Erweiterungen
- aggressive Dateiloesch- oder Datenpflegepfade
- alles mit unscharfem Seiteneffekt

Rollout-Stufen:

- `observe_only`
- `developer_only`
- `self_modify_safe`
- spaeter optional:
  - `approval_required_for_high_risk`

Technische Anker:

- [orchestration/self_hardening_rollout.py](/home/fatih-ubuntu/dev/timus/orchestration/self_hardening_rollout.py)
- [orchestration/self_modifier_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_modifier_engine.py)
- [orchestration/autonomy_change_control.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_change_control.py)
- [orchestration/autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)

Erfolgskriterium:

- Timus kann eine kleine Hardening-Massnahme unter enger Rollout-Stufe ausfuehren, verifizieren und bei Bedarf sauber zuruecknehmen

### E4. Verification, Canary und Rollback

Ziel:

- jede Selbstverbesserung wird nicht nur "geschrieben", sondern technisch abgesichert

Bestandteile:

- fokussierte Tests vor und nach der Aenderung
- Contracts/Hypothesis/CrossHair dort, wo Logik rein und stabil ist
- Canary oder begrenzte Runtime-Freigabe
- Change-Memory fuer spaetere Auswertung
- klarer Rollback bei:
  - Testfehler
  - Canary-Fehler
  - Regressionssignalen im Live-Betrieb

Technische Anker:

- [orchestration/self_modifier_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_modifier_engine.py)
- [orchestration/self_hardening_verification.py](/home/fatih-ubuntu/dev/timus/orchestration/self_hardening_verification.py)
- [orchestration/self_hardening_runtime.py](/home/fatih-ubuntu/dev/timus/orchestration/self_hardening_runtime.py)

Erfolgskriterium:

- keine Phase-E-Aenderung ohne belastbare Verifikation und Rollback-Hook

### E5. Memory Curation Autonomy

Ziel:

- Timus pflegt sein Gedaechtnis spaeter kontrolliert, statt es nur wachsen zu lassen

Wichtig:

- dieser Block kommt nicht als Start von Phase E
- er baut auf E1-E4 und den D0-/Phase-D-Grenzen auf

Schwerpunkte:

- Memory-Curation-Policy:
  - fluechtig
  - topic-gebunden
  - stabil/langfristig
  - nie automatisch loeschen
- Curation-Engine:
  - zusammenfassen
  - archivieren
  - konservativ entwerten
  - nur spaeter selektiv prunen
- Verifikation:
  - Retrieval-Qualitaet steigt oder bleibt stabil
- Rollback:
  - keine irreversible blinde Pflege

Technische Anker:

- [tools/maintenance_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/maintenance_tool/tool.py)
- D0-State-/Topic-/Preference-Pfade
- spaeter eigener Heartbeat-Block in [orchestration/autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)

Erfolgskriterium:

- Timus kann spaeter Memory-Pflege policy-gesteuert, beobachtbar und reversibel ausfuehren

### E6. Operator Visibility und Governance

Ziel:

- Phase E bleibt fuer dich sichtbar und steuerbar

Schwerpunkte:

- eigene Observation-Events fuer Improvement-Zyklen
- Canvas-/API-Sicht auf:
  - Improvement-Kandidaten
  - aktive Rollout-Stufe
  - letzte Self-Hardening-Aktion
  - letzter Rollback
  - Memory-Curation-Status
- Approval-Pfade fuer hoehere Risikoklassen

Erfolgskriterium:

- du kannst sehen, was Timus verbessern will, was er getan hat und warum etwas blockiert oder zurueckgerollt wurde

## Arbeitsreihenfolge

### Phase-E-Start

1. E1 Improvement Signal Pipeline
2. E2 Weakness-to-Task Compiler
3. E3 Safe Self-Hardening Execution fuer kleine Guard-/Prompt-/Test-Fixes
4. E4 Verification und Rollback hart machen

### Phase-E-Mitte

5. E6 Operator Visibility und Governance erweitern
6. Safe subset vergroessern, wenn die ersten Zyklen stabil sind

### Spaeter in Phase E

7. E5 Memory Curation Autonomy

## Nicht Ziel von Phase E

- keine globale "ich verbessere alles automatisch"-Logik
- keine ungebremste Self-Modification
- keine Ausweitung von Login-/Credential-/Secret-Rechten
- keine grossen Architektur-Refactors ohne harte Gates
- keine Metrik-Kosmetik zur kuenstlichen Verbesserung des Autonomy-Scores

## Definition of Done fuer den ersten Phase-E-Abschnitt

Der erste Phase-E-Abschnitt gilt als erreicht, wenn:

- wiederkehrende Schwachstellen dedupliziert und klassifiziert werden
- daraus strukturierte Verbesserungs-Tasks entstehen
- ein sicherer Teil davon unter Rollout-Grenzen automatisch ausgefuehrt werden kann
- jede Ausfuehrung Verifikation, Beobachtbarkeit und Rollback besitzt
- noch keine aggressive Memory-Curation noetig ist, aber ihr Platz und ihre Policy klar definiert sind

## Erster konkreter Startblock

Wenn Phase E jetzt direkt begonnen wird, ist der richtige erste Slice:

- **E1.1 Improvement Signal Normalization**

Also:

- gemeinsame Improvement-Candidate-Struktur
- Input aus Observation, Session Reflection und Self-Improvement Engine
- Severity / Confidence / Dedupe
- noch keine automatische Codeaenderung

Das ist der konservativste und technisch sauberste Einstieg.

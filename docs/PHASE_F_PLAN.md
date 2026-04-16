# Phase F Plan - Betriebsvertraege, Harnesses und Runtime-Board

Stand: 2026-04-15

## Ziel

Phase F baut auf D0, Phase D und Phase E auf und macht aus Timus nicht nur ein semantisch staerkeres und kontrolliert selbstverbesserndes System, sondern auch ein betrieblich belastbareres Operatorsystem.

Der Kern ist:

- Betriebszustaende, Readiness und Degraded-Mode werden systemweit vertraglich klarer
- wichtige Laufzeitpfade werden deterministisch und reproduzierbar pruefbar
- Architektur- und Verhaltensdokumentation wird schrittweise in ausfuehrbare Vertraege ueberfuehrt
- Timus bekommt ein maschinenlesbares Runtime-/Lane-Board statt nur verteilter Einzel-Logs

Phase F ist damit keine weitere "mehr Autonomie"-Phase, sondern eine Phase fuer:

- Betriebsdisziplin
- Lifecycle-Vertraege
- reproduzierbare Parity- und Regression-Checks
- bessere Operator-Sicht
- bessere Entscheidbarkeit fuer den naechsten grossen Ausbau nach Phase E

## Warum Phase F nach E sinnvoll ist

Die noetigen Grundlagen sind jetzt weit genug:

- D0 liefert Gespraechszustand, Kontext-Propagation und Self-Model-Grundlagen
- Phase D liefert Approval/Auth/Handover als echte Workflow-Zustaende
- Phase E liefert kontrollierte Improvement- und Governance-Pfade bis E4
- Stack, Health-Endpoints und Observability sind deutlich weiter als frueher

Damit lohnt sich jetzt ein Block, der Timus haerter betreibbar und pruefbarer macht, ohne die innere Semantik wieder mit Infrastruktur zu vermischen.

## Bereits vorhandene Bausteine im Repo

Phase F startet nicht bei null. Wichtige bestehende Bausteine sind:

- [gateway/dispatcher_health_server.py](/home/fatih-ubuntu/dev/timus/gateway/dispatcher_health_server.py)
  - eigener Dispatcher-Health-Server
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - MCP-Health, SSE und Operatorschnittstellen
- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - Observation-, Runtime- und Improvement-Sicht
- [orchestration/self_hardening_rollout.py](/home/fatih-ubuntu/dev/timus/orchestration/self_hardening_rollout.py)
  - Rollout-Stufen und Guardrails
- [scripts/timusctl.sh](/home/fatih-ubuntu/dev/timus/scripts/timusctl.sh)
  - Start-/Status-/Health-Bedienpfad
- [scripts/install_timus_stack.sh](/home/fatih-ubuntu/dev/timus/scripts/install_timus_stack.sh)
  - Stack-Installation
- [scripts/setup_timus_host.sh](/home/fatih-ubuntu/dev/timus/scripts/setup_timus_host.sh)
  - portabler Host-Setup-Pfad
- [timus-stack.target](/home/fatih-ubuntu/dev/timus/timus-stack.target)
  - gemeinsamer Stack fuer Qdrant, MCP und Dispatcher

Phase F soll diese Bausteine haerter vertraglich machen und in einen konsistenten Betriebsrahmen ziehen.

## Leitprinzipien

1. Contract before convenience
- zuerst klarer Betriebsvertrag, dann Komfortschicht

2. Determinism before heuristics
- kritische Pruefpfade sollen reproduzierbar sein, nicht nur "im echten Leben meistens gut"

3. One state model across surfaces
- Health, Observation, Tooling und Operator-Sicht duerfen dieselben Runtime-Zustaende nicht unterschiedlich benennen

4. Degraded is first-class
- partielle Fehler muessen sichtbar und fuehrbar sein, statt nur als implizites "geht schon irgendwie"

5. No hidden semantics regression
- F darf keine Infrastruktur ueber instabile Frontdoor-/Meta-Semantik legen

6. Phase F is not multi-step planning
- allgemeine Mehrschritt-Planung bleibt ein eigener Ausbaupfad
- F soll erst die Betriebs- und Vertragsbasis dafuer verbessern

## Phase-F-Struktur

### F1. Betriebsvertraege und `timus doctor`

Ziel:

- ein gemeinsamer Diagnose- und Lifecycle-Vertrag fuer den Timus-Stack

Schwerpunkte:

- `timus doctor` als einheitlicher Einstiegspunkt
- Health, Readiness und Degraded-Mode fuer:
  - Qdrant
  - MCP
  - Dispatcher
  - wichtige Provider-/Tool-Klassen
- Maschinenlesbare Diagnoseausgabe statt verteiltem manuellen Checken
- Host-/Stack-/Provider-Checks ueber einen gemeinsamen Bericht

Technische Anker:

- [scripts/timusctl.sh](/home/fatih-ubuntu/dev/timus/scripts/timusctl.sh)
- [scripts/install_timus_stack.sh](/home/fatih-ubuntu/dev/timus/scripts/install_timus_stack.sh)
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- [gateway/dispatcher_health_server.py](/home/fatih-ubuntu/dev/timus/gateway/dispatcher_health_server.py)

Erfolgskriterium:

- ein einziger Diagnosepfad kann den Stack-Status maschinenlesbar und fuer Operatoren knapp zusammenfassen

Stand:

- erster Runtime-Slice umgesetzt

Umgesetzt:

- [orchestration/timus_doctor.py](/home/fatih-ubuntu/dev/timus/orchestration/timus_doctor.py)
  - gemeinsamer `timus_doctor_v1`-Diagnosevertrag
  - vereinheitlicht jetzt:
    - Service-Zustand
    - MCP-Runtime
    - Dispatcher-Health/Readiness
    - Request-Runtime
    - Stability-/Ops-Gate
    - Budget- und Provider-Hinweise
  - liefert:
    - `state`
    - `ready`
    - `summary`
    - `stack`
    - `issues`
    - `actions`
- [scripts/timus_doctor.py](/home/fatih-ubuntu/dev/timus/scripts/timus_doctor.py)
  - CLI fuer menschenlesbare und JSON-Ausgabe
  - unterstuetzt:
    - `--json`
    - `--strict`
- [scripts/timusctl.sh](/home/fatih-ubuntu/dev/timus/scripts/timusctl.sh)
  - neuer Einstiegspunkt:
    - `./scripts/timusctl.sh doctor`

Verifikation:

- `python -m py_compile orchestration/timus_doctor.py scripts/timus_doctor.py tests/test_timus_doctor.py tests/test_timus_doctor_hypothesis.py tests/test_timus_doctor_crosshair.py tests/test_timus_stack_assets.py` gruen
- `bash -n scripts/timusctl.sh`
- `pytest -q tests/test_timus_doctor.py tests/test_timus_doctor_hypothesis.py tests/test_timus_stack_assets.py` -> `8 passed`
- `python -m crosshair check tests/test_timus_doctor_crosshair.py` -> Exit `0`

### F2. Typed Task Packets und Context-/Request-Preflight

Ziel:

- Handoffs und Modellaufrufe vorab haerter strukturieren und begrenzen

Schwerpunkte:

- Typed Task Packets statt zu freier Handoff-Texte
- Pflichtfelder wie:
  - `objective`
  - `scope`
  - `acceptance_criteria`
  - `allowed_tools`
  - `reporting_contract`
  - `escalation_policy`
  - `state_context`
- Context-/Request-Preflight vor kritischen Modellcalls:
  - Bundle-Groesse
  - Provider-Limits
  - Deep-Research-Eingabegrenzen
  - Handoff-Groesse

Technische Anker:

- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- [orchestration/conversation_state.py](/home/fatih-ubuntu/dev/timus/orchestration/conversation_state.py)

Erfolgskriterium:

- Handoffs sind reproduzierbarer, duerfen weniger implizite Annahmen tragen und scheitern seltener an Kontextueberladung

### F3. Deterministische Mock-/Parity-Harnesses

Ziel:

- wichtige externe und interne Laufzeitpfade kontrolliert und reproduzierbar pruefbar machen

Schwerpunkte:

- lokaler Mock-/Parity-Harness fuer:
  - `/chat`
  - Delegation
  - Approval/Auth/Handover
  - Longrunner-/Queue-Pfade
  - Telegram-/Canvas-Parity
- deterministische Fixtures statt reinem Live-Testen
- gezielte Reproduzierbarkeit fuer spaetere Incident-Klassen

Technische Anker:

- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- [orchestration/autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)
- [orchestration/approval_auth_contract.py](/home/fatih-ubuntu/dev/timus/orchestration/approval_auth_contract.py)

Erfolgskriterium:

- wiederkehrende Fehlerbilder koennen kontrolliert nachgestellt werden, statt nur im Live-Betrieb gejagt zu werden

### F4. Ausfuehrbare Architektur- und Verhaltensvertraege

Ziel:

- zentrale Architektur- und Verhaltensannahmen aus Doku in pruefbare Vertraege ueberfuehren

Schwerpunkte:

- Contract-Driven Eval fuer:
  - Roadmap-Vertraege
  - Longrunner-Vertraege
  - Approval-/Auth-Pfade
  - Meta-/Spezialisten-Handoffs
  - Runtime- und Improvement-Lanes
- Doku nicht nur als Beschreibung, sondern als testbarer Anspruch
- staerkere Kopplung zwischen Plan, Changelog, Tests und Runtime-Beobachtung

Technische Anker:

- [docs/PHASE_E_SELF_IMPROVEMENT_PLAN.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_E_SELF_IMPROVEMENT_PLAN.md)
- [docs/PHASE_D_APPROVAL_AUTH_PREP.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D_APPROVAL_AUTH_PREP.md)
- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
- bestehende CrossHair-, Hypothesis- und Lean-Pfade

Erfolgskriterium:

- zentrale Architekturclaims koennen als Contracts oder Evals gegen das System geprueft werden

### F5. Maschinenlesbares Runtime-/Lane-Board

Ziel:

- ein gemeinsames, maschinenlesbares Board fuer die relevanten Timus-Lanes statt verteilter Einzelindikatoren

Schwerpunkte:

- konsolidierte Sicht auf:
  - request lanes
  - auth/approval lanes
  - self-improvement lanes
  - recovery/self-healing lanes
  - tool-/provider-degraded-zustaende
- fuer Operator, Eval und Regression dieselbe Statusquelle
- spaeter auch als Eingang fuer Governance- und Multi-step-Entscheidungen nutzbar

Technische Anker:

- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- [gateway/dispatcher_health_server.py](/home/fatih-ubuntu/dev/timus/gateway/dispatcher_health_server.py)

Erfolgskriterium:

- Timus kann seine aktiven Betriebs- und Arbeitslanes als stabilen, maschinenlesbaren Snapshot ausgeben

## Nicht Ziel von Phase F

- keine allgemeine Mehrschritt-Planung aus beliebigem Freitext
- kein neuer Auth-/Credential-Umbau
- kein aggressiver Ausbau freier Selbstmodifikation
- kein Rust- oder Plattform-Totalumbau
- kein volles Projektmanagement fuer beliebige Langzeitvorhaben

## Reihenfolge innerhalb von Phase F

1. F1 Betriebsvertraege und `timus doctor`
2. F2 Typed Task Packets und Context-/Request-Preflight
3. F3 Deterministische Mock-/Parity-Harnesses
4. F4 Ausfuehrbare Architektur- und Verhaltensvertraege
5. F5 Maschinenlesbares Runtime-/Lane-Board

Begruendung:

- F1 und F2 haerten zuerst die Betriebs- und Handoff-Basis
- F3 und F4 machen diese Basis reproduzierbar und pruefbar
- F5 konsolidiert daraus die operative Sicht fuer Mensch und System

## Entscheidung nach Phase F

Nach Phase F soll bewusst entschieden werden, welcher grosse Block als naechstes folgt.

Entscheidungsfragen:

1. Sind die groessten Nutzerfehler danach weiter:
- Frontdoor-Fehlklassifikation
- fehlende Build-/Setup-/Plan-Erkennung
- zu implizite Teilzielzerlegung

Dann ist der richtige naechste Block:

- [ZWISCHENPROJEKT_ALLGEMEINE_MEHRSCHRITT_PLANUNG_2026-04-12.md](/home/fatih-ubuntu/dev/timus/docs/ZWISCHENPROJEKT_ALLGEMEINE_MEHRSCHRITT_PLANUNG_2026-04-12.md)

2. Sind die groessten Restprobleme danach weiter:
- fehlende Runtime-Parity
- fehlende Betriebsdiagnostik
- unzureichende Lane-/Provider-Sicht
- nicht ausreichend harte Lifecycle-Vertraege

Dann folgt zuerst:

- ein weiterer Betriebs-/Harness-Nachblock auf Basis von F

## Erfolgskriterium fuer Phase F insgesamt

- Timus ist nicht nur funktional staerker, sondern betrieblich deutlich besser pruefbar
- zentrale Laufzeit-, Handoff- und Governance-Pfade haben reproduzierbare Contracts
- Operatoren koennen Stack- und Lane-Zustand ohne manuelle Log-Jagd zusammenhaengend sehen
- die Entscheidung fuer den naechsten grossen Ausbau nach E ist dadurch datenbasiert statt intuitiv

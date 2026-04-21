# Meta Frame Resolver Plan

Stand: 2026-04-20

## Problem

Timus scheitert bei mehrschichtigen Anfragen nicht mehr nur an einzelnen
Heuristiken, sondern an fehlender zentraler Frame-Klarheit.

Dasselbe Nutzerziel wird heute gleichzeitig beeinflusst von:

- `turn_understanding`
- `meta_orchestration`
- `meta_response_policy`
- `preference_instruction_memory`
- `meta_clarity_contract`
- `task_decomposition`
- `meta_plan_compiler`

Wenn eine Schicht lokal korrigiert wird, kippt der Fehler oft in die naechste.
Das fuehrt zu:

- falscher erster Themenframe
- query-fremdem Memory-Einfluss
- unnoetiger Delegation
- instabiler Behandlung von Folgefragen
- wechselnder Fehlersymptomatik statt robuster Entscheidung

## Ziel

Vor jeder Meta-Ausfuehrung wird genau **ein zentraler Request-Frame** gebildet.
Dieser Frame ist danach die Single Source of Truth fuer:

- Task-Domain
- Turn-Typ
- Ausfuehrungsmodus
- erlaubte Kontextquellen
- verbotene Kontextquellen
- Delegationsbudget
- Abschlussbedingung

Spaetere Schichten duerfen diesen Frame nicht frei ueberschreiben.

## Kernprinzip

Reihenfolge:

1. `request_frame` bilden
2. nur passenden Kontext zulassen
3. Meta-Policy innerhalb des Frames anwenden
4. Plan/Delegation nur innerhalb des Frames
5. Antwort oder Replan gegen die Frame-Abschlussbedingung pruefen

Nicht mehr:

- erst breiten Kontext laden
- dann heuristisch ueberschreiben
- dann versuchen, Drift spaeter zu reparieren

## Frame-Vertrag

Der neue Resolver soll mindestens diese Felder liefern:

- `frame_kind`
  - `direct_answer`
  - `stateful_followup`
  - `new_task`
  - `resume_plan`
  - `status_summary`
  - `clarify_needed`
- `task_domain`
  - z. B. `migration_work`, `setup_build`, `docs_status`, `general_research`,
    `skill_creation`, `location_route`
- `execution_mode`
  - `answer_directly`
  - `clarify_once`
  - `plan_and_delegate`
  - `resume_existing_plan`
- `primary_objective`
- `topic_anchor`
- `goal_anchor`
- `allowed_memory_domains`
- `forbidden_memory_domains`
- `allowed_context_slots`
- `delegation_budget`
- `allowed_delegate_agents`
- `completion_contract`
- `confidence`
- `evidence`

## Architekturentscheidung

Der Resolver sitzt **vor**:

- `meta_context_bundle`
- `meta_response_policy`
- `meta_clarity_contract`
- `meta_plan_compiler`

Er ersetzt nicht alles sofort, sondern wird zuerst als zentrale Eingabeschicht
eingezogen. Die bestehenden Module werden danach auf den Resolver umgestellt.

## Umsetzung in Slices

### MFR1. Frame Contract

Ziel:

- kanonisches `meta_request_frame_v1`

Umfang:

- neues Resolver-Modul
- Dataklasse / Dict-Vertrag
- Helper fuer `frame_kind`, `task_domain`, `execution_mode`
- erste harte Invarianten

Erfolg:

- jede Meta-Anfrage hat einen expliziten Frame vor Policy und Kontextladung

Status 2026-04-20:

- erster Runtime-Slice lokal umgesetzt
- neues Modul [meta_request_frame.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_request_frame.py)
- `classify_meta_task(...)` liefert jetzt `meta_request_frame`
- erste Vertragsfelder aktiv:
  - `frame_kind`
  - `task_domain`
  - `execution_mode`
  - `allowed/forbidden memory domains`
  - `delegation_budget`
  - `completion_contract`
- erste Eval-Faelle abgedeckt:
  - Docs-Status
  - Kanada / Arbeit / `Fuß fassen`
  - Twilio + Inworld Setup

### MFR2. Frame-First Routing

Ziel:

- `turn_understanding` und `meta_orchestration` treffen die erste Entscheidung
  nicht mehr lose, sondern ueber den Resolver

Umfang:

- bestehende Turn-/Meta-Signale in den Resolver einspeisen
- `recommended_agent_chain` nicht mehr frei vor dem Frame bilden
- klare Prioritaet:
  - aktuelle Anfrage
  - stateful Thema
  - erst danach zulaessiger Verlauf

Erfolg:

- `Kanada Fuß fassen` darf nicht mehr auf `skill_creation` oder andere fremde
  Domains kippen

### MFR3. Context Admission by Frame

Ziel:

- Kontext erst nach Frame zulassen

Umfang:

- Memory-Domains separat taggen / klassifizieren
- `topic_memory`, `preference_memory`, `semantic_recall`, `assistant_fallback`
  nur noch frame-abhaengig zulassen
- query-fremde Domain-Hits aktiv suppressieren

Erfolg:

- ein `migration_work`-Frame sieht kein `Twilio` oder `skill_creator`, wenn
  diese Domain nicht explizit gebraucht wird

### MFR4. Policy and Delegation Budget by Frame

Ziel:

- Policy und Delegation arbeiten nur innerhalb des Frames

Umfang:

- `meta_response_policy` auf `request_frame` umstellen
- Delegationsbudget und erlaubte Agenten pro Frame
- direkte Antwortfragen duerfen keine freie Agentenkette aufspannen
- echte Build-/Research-Aufgaben duerfen das weiter

Erfolg:

- Status- oder Next-Step-Fragen bleiben direkt
- echte Mehrschrittaufgaben behalten orchestrierte Delegation

### MFR5. Frame Guard Before Action

Ziel:

- bevor Meta delegiert oder Tools aufruft, wird geprueft, ob die Aktion zum
  Frame passt

Umfang:

- harte Guard-Schicht vor Tool-/Delegationsaktionen
- off-frame Aktionen werden blockiert oder gereframed
- Salvage darf keine off-frame Endantwort akzeptieren

Erfolg:

- `docs_status` darf nicht auf `location_route`
- `migration_work` darf nicht auf `skill_creator`

### MFR6. Eval Suite and Live Gates

Ziel:

- nicht mehr nur punktuelle Tests, sondern feste Vertragsfaelle

Pflichtfaelle:

- `suche mir Möglichkeiten in Kanada Fuß zu fassen`
- `Informationen ueber Kanada wie kann ich dort arbeiten`
- `koennte ich da fuss fassen`
- `lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht`
- `richte Twilio + Inworld ein`

Pro Fall wird fixiert:

- erwarteter `frame_kind`
- erwartete `task_domain`
- erwarteter `execution_mode`
- verbotene Memory-Domains
- erlaubte Delegationstiefe

Erfolg:

- der Resolver wird nicht mehr nur an Symptomen, sondern an festen
  Invarianten gemessen

Status 2026-04-21:

- erster MFR6-Eval-Block lokal umgesetzt
- neue integrierte Suite:
  - [tests/test_meta_frame_resolver_eval_suite.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_frame_resolver_eval_suite.py)
- deckt jetzt nicht nur die bisherigen Pflichtfaelle ab, sondern auch
  allgemeine Beratungs-/Planungsfaelle:
  - `docs_status`
  - `migration_work`
  - `setup_build`
  - `planning_advisory`
  - `research_advisory`
  - `self_status`
- neue allgemeine Frame-Domaenen aktiviert:
  - `planning_advisory`
  - `research_advisory`
  - `self_status`
- die MFR6-Suite prueft pro Fall fest:
  - `frame_kind`
  - `task_domain`
  - `execution_mode`
  - `reason`
  - `recommended_agent_chain`
  - `meta_clarity_contract.request_kind`
- aktueller lokaler Verifikationsstand:
  - fokussierter Meta-Subset `96 passed`

## Reihenfolge

1. MFR1 Frame Contract
2. MFR2 Frame-First Routing
3. MFR3 Context Admission
4. MFR4 Policy and Delegation Budget
5. MFR5 Frame Guard Before Action
6. MFR6 Eval Suite and Live Gates

## Akzeptanzkriterien

- Kanada-/Arbeitsfragen bleiben stabil in `migration_work`
- direkte Statusfragen bleiben direkt und menu-frei
- Build-/Setup-Aufgaben bleiben mehrschrittig und delegationsfaehig
- query-fremde Memory-Domains koennen den ersten Frame nicht mehr kapern
- Live-Fehler sollen nicht mehr nur die Form wechseln, sondern an festen Gates
  sichtbar blocken

## Naechster Schritt

Direkt starten mit:

- `MFR3 Context Admission by Frame`
- plus Live-Checks fuer:
  - Kanada / Arbeit / `Fuß fassen`
  - Docs-Status / naechster Schritt
  - Twilio + Inworld Setup

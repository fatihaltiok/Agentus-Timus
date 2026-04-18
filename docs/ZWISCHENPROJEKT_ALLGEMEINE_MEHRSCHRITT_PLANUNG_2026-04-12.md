# Zwischenprojekt: Allgemeine Mehrschritt-Planung fuer Timus

Stand: 2026-04-12

Status-Update 2026-04-18:

- dieses Zwischenprojekt ist jetzt der empfohlene naechste Hauptblock nach Phase F
- der konkrete Einstieg ist:
  - [Z1_TASK_DECOMPOSITION_STARTPLAN_2026-04-17.md](/home/fatih-ubuntu/dev/timus/docs/Z1_TASK_DECOMPOSITION_STARTPLAN_2026-04-17.md)
- Startreihenfolge:
  - zuerst `Z1 Task Decomposition Contract`
  - danach `Z2 Meta Plan Compiler`
- Z1 steht jetzt bereits im ersten Runtime-Slice:
  - `task_decomposition_v1`
  - `planning_needed`
  - Frontdoor-Schaerfung `build_setup` vs `research`
  - Typed-Meta-Handoff mit `task_decomposition_json`
- Z2 steht jetzt ebenfalls im ersten Runtime-Slice:
  - explizites `meta_execution_plan` in [orchestration/meta_plan_compiler.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_plan_compiler.py)
  - Typed-Meta-Handoff mit `meta_execution_plan_json`
  - Rezept-Stage-Handoffs mit `plan_summary_json` und `plan_step_json`
  - kompaktierte Original-Requests aktualisieren Decomposition, Plan und Task-Packet konsistent

## Zweck

Dieses Dokument beschreibt einen separaten Ausbaupfad fuer Timus:

- allgemeine Mehrschritt-Aufgaben aus Freitext robuster erkennen
- diese Aufgaben in explizite Teilziele und Arbeitsschritte zerlegen
- die Schritte dynamisch an Spezialisten und Runtime-Zustaende binden
- dabei nicht nur in einzelnen Spezialpfaden planen, sondern systemweit

Wichtig:

- dieses Zwischenprojekt ist **nicht** Teil von Phase D
- dieses Zwischenprojekt ist **nicht** identisch mit Phase E
- es ist ein eigener Querbau zwischen:
  - Frontdoor
  - Meta-Orchestrierung
  - Spezialisten
  - Zustand
  - UX

## Warum ein eigener Plan noetig ist

Timus kann heute schon in mehreren Teilbereichen mehrstufig arbeiten:

- Browser-/Visual-Flows
- Approval-/Auth-/Resume-Flows
- Research- und Specialist-Handoffs
- Self-Improvement bis hin zu kontrollierter Task-Erzeugung

Aber:

- die allgemeine Zerlegung aus einem beliebigen Nutzertext in einen expliziten Masterplan ist noch nicht stark genug
- es gibt noch zu viel implizite Schrittlogik innerhalb einzelner Agenten
- grosse Freitextaufgaben sind noch nicht systemweit als formales, laufendes Arbeitsobjekt sichtbar

Der Ausbau darf deshalb nicht in einem einzelnen Spezialagenten versteckt werden.

## Zielbild

Wenn der Nutzer eine mehrschrittige Aufgabe formuliert, soll Timus kuenftig:

1. das eigentliche Ziel erkennen
2. Randbedingungen und Verbote extrahieren
3. Teilziele und Abhaengigkeiten ableiten
4. einen kompakten Arbeitsplan erzeugen
5. die Schritte passenden Agenten oder Workflow-Lanes zuordnen
6. den Plan waehrend der Ausfuehrung an den echten Zustand anpassen
7. das Ziel als erfuellt erkennen, auch wenn der exakte Rezeptschritt nicht erreicht wurde

Beispiel:

`Oeffne Seite X, melde mich an, pruefe meine letzten Rechnungen, lade die letzte herunter und schick mir danach eine kurze Zusammenfassung.`

Timus soll daraus nicht nur eine lose Folge von Aktionen ableiten, sondern etwa:

- Ziel: letzte Rechnung beschaffen und zusammenfassen
- Teilziel 1: Zielseite und relevanten Bereich erreichen
- Teilziel 2: Auth nur falls noetig
- Teilziel 3: Rechnungsbereich identifizieren
- Teilziel 4: letzte Rechnung herunterladen
- Teilziel 5: Inhalt oder Metadaten zusammenfassen

## Architekturprinzipien

### 1. Zielzustand vor Rezeptschritt

Timus soll nicht starr an einem erwarteten Zwischenschritt haengen.

Regel:

- `goal_satisfied > expected_state`

Wenn das Ziel funktional schon erreicht ist, soll Timus weitermachen oder sauber abschliessen.

### 2. Planobjekt statt nur Prompt-Text

Mehrschritt-Aufgaben duerfen nicht nur im Agentenprompt leben.

Es braucht ein echtes Planobjekt mit:

- `goal`
- `constraints`
- `subtasks`
- `dependencies`
- `status`
- `next_step`
- `blocked_by`
- `completion_signals`

### 3. Systemweite statt agentspezifische Planung

Die Zerlegung darf nicht nur in `visual` oder nur in `meta` stattfinden.

Sie muss anschlussfaehig sein an:

- Frontdoor
- Meta
- Specialist-Handoffs
- Pending Workflows
- Observation

### 4. Dynamische Replanung statt statischer Checkliste

Der Plan muss waehrend der Ausfuehrung veraenderbar sein:

- Schritt faellt weg
- Schritt wird durch echten Zustand schon erfuellt
- neuer Blocker taucht auf
- Agentenkette muss umgebaut werden

### 5. Nutzerfreundliche Sicht

Der Nutzer soll nicht die rohe interne Planreprasentation sehen.

Fuer den Nutzer gilt:

- knappe Fortschrittskommunikation
- nur sichtbare Teilziele wenn hilfreich
- Rueckfragen nur bei echter Unklarheit oder menschlicher Grenze

## Scope

Dieses Zwischenprojekt deckt ab:

- allgemeine Freitext-Zerlegung
- explizite Teilzielplanung
- Agentenkette fuer mehrstufige Aufgaben
- Planstatus ueber mehrere Turns
- zielzustandsorientierte Replanung

Dieses Zwischenprojekt deckt **nicht** ab:

- komplette Projektmanagement-Funktion fuer beliebig grosse Vorhaben
- unbegrenzte autonome Langzeitprojekte
- neue Credential-/Auth-Architektur
- allgemeine Headless-Automation
- umfassende Memory-Curation oder Self-Improvement

## Aufbau in Slices

### Z1. Task Decomposition Contract

Ziel:

- gemeinsamer Vertrag fuer allgemeine Mehrschritt-Aufgaben

Umfang:

- neues Plan-/Task-Decomposition-Schema
- kompakte Ziel-, Constraint- und Teilzielstruktur
- maschinenlesbare `completion_signals`
- `goal_satisfaction_mode`

Erfolg:

- Timus kann aus einem Freitext-Task ein stabiles, kanonisches Decomposition-Objekt bauen

Status 2026-04-17:

- erster Runtime-Slice umgesetzt
- noch offen fuer Z2+:
  - expliziter Meta Plan Compiler
  - turnuebergreifender Plan-State
  - Replanning und Goal Satisfaction

Startplan:

- [Z1_TASK_DECOMPOSITION_STARTPLAN_2026-04-17.md](/home/fatih-ubuntu/dev/timus/docs/Z1_TASK_DECOMPOSITION_STARTPLAN_2026-04-17.md)

### Z2. Meta Plan Compiler

Ziel:

- Meta baut aus dem Freitext einen expliziten Plan statt nur implizite Handoffs

Umfang:

- Goal-Extraktion
- Constraint-Extraktion
- Teilziel- und Abhaengigkeitsableitung
- Zuordnung zu Agentenklassen

Erfolg:

- mehrschrittige Aufgaben werden reproduzierbar in Teilpakete zerlegt

Status 2026-04-18:

- erster Runtime-Slice umgesetzt
- Meta baut jetzt einen expliziten `meta_execution_plan`
- der Plan wird im Dispatcher-Handoff, im Typed Packet und in Rezept-Stage-Delegationen weitergereicht
- noch offen fuer Z3+:
  - turnuebergreifender Plan-State
  - Schrittstatus ueber mehrere Turns
  - Replanning / Goal-Satisfaction auf Runtime-Ebene

### Z3. Plan State in Conversation State

Ziel:

- offene Arbeitsplaene werden turnuebergreifend gehalten

Umfang:

- aktiver Plan im Gespraechszustand
- `next_step`
- `blocked_by`
- `last_completed_step`
- Resume nach Follow-up

Erfolg:

- `weiter`, `mach den naechsten Schritt`, `ueberspring das Login` binden an einen echten Plan

Status 2026-04-18:

- erster Runtime-Slice umgesetzt
- `active_plan` lebt jetzt im Conversation State
- Follow-up-Capsules serialisieren und rekonstruieren Planzustand turnuebergreifend
- Resume-Queries wie `weiter` und `naechster Schritt` binden jetzt an:
  - `goal`
  - `next_step`
  - `blocked_by`
  - `last_completed_step`
- noch offen fuer Z4+:
  - planbasierte Specialist-Step-Pakete
  - Runtime-Replanning und Goal-Satisfaction

### Z4. Specialist Step Packaging

Ziel:

- Spezialisten bekommen nicht nur rohen Kontext, sondern den fuer sie relevanten Arbeitsschritt

Umfang:

- strukturierte Step-Handoffs
- enger Teilkontext statt vollem Masterplan
- Ruecksignale fuer:
  - Schritt erledigt
  - Schritt blockiert
  - Schritt unnoetig
  - Ziel schon erfuellt

Erfolg:

- weniger implizite Spezialistenlogik
- sauberere Agentenkette

Status 2026-04-18:

- erster Runtime-Slice umgesetzt
- Meta baut jetzt ein explizites `specialist_step_package_json`
- das Schritt-Paket traegt fokussiert:
  - `plan_goal`
  - `step_title`
  - `expected_output`
  - `completion_signals`
  - engen `focus_context`
- Spezialisten rendern das Schritt-Paket jetzt als eigenen Kontextblock statt nur lose `plan_step_json`-Fragmente zu sehen
- neue Ruecksignale sind jetzt transport- und runtime-seitig auswertbar:
  - `step_completed`
  - `step_blocked`
  - `step_unnecessary`
  - `goal_satisfied`
- noch offen fuer Z5+:
  - echte Runtime-Replanung auf Basis dieser Signale
  - formale Planfortschreibung ueber mehrere Spezialistenlaeufe

### Z5. Dynamic Replanning and Goal Satisfaction

Ziel:

- Timus passt den Plan an den realen Zustand an

Umfang:

- Schritt als erledigt markieren, auch wenn der exakte Zwischenzustand fehlt
- Teilziele zusammenlegen oder streichen
- Reframing bei Zielverschiebung
- `goal_satisfied` als eigener Runtime-Pfad

Erfolg:

- weniger starres Rezeptverhalten
- mehr zielorientierte Ausfuehrung

### Z6. User-Facing Progress Compression

Ziel:

- Mehrschritt-Planung soll sich fuer Nutzer nicht nach Babysitting anfuehlen

Umfang:

- kompakte Fortschrittsmeldungen
- nur bei Bedarf sichtbarer Teilplan
- weniger rohe Workflow-Interna
- bessere Default-Kommunikation fuer Laien

Erfolg:

- Timus wirkt mehr wie ein Operator, weniger wie ein Prompt-getriebener Assistent

## Technische Anker

Voraussichtlich betroffen:

- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [agent/agents/meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- [orchestration/conversation_state.py](/home/fatih-ubuntu/dev/timus/orchestration/conversation_state.py)
- [orchestration/turn_understanding.py](/home/fatih-ubuntu/dev/timus/orchestration/turn_understanding.py)
- [orchestration/specialist_context.py](/home/fatih-ubuntu/dev/timus/orchestration/specialist_context.py)
- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
- spaeter eventuell:
  - [orchestration/task_queue.py](/home/fatih-ubuntu/dev/timus/orchestration/task_queue.py)
  - [orchestration/replanning_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/replanning_engine.py)

## Beziehung zu den laufenden Phasen

### Beziehung zu Phase D

Phase D baut sichere externe Workflows:

- Approval
- Auth
- Login
- Session
- Challenge

Dieses Zwischenprojekt baut darauf auf, ersetzt es aber nicht.

### Beziehung zu Phase E

Phase E baut kontrollierte Selbstverbesserung.

Dieses Zwischenprojekt ist davon getrennt.

Es betrifft:

- Arbeitsplanung
- Agentenkoordination
- Zielzustandslogik

nicht primaer:

- Improvement-Pipeline
- Promotion-Gates
- Self-Hardening

## Reihenfolge

Empfohlene Reihenfolge:

1. Z1 Task Decomposition Contract
2. Z2 Meta Plan Compiler
3. Z3 Plan State
4. Z4 Specialist Step Packaging
5. Z5 Dynamic Replanning and Goal Satisfaction
6. Z6 User-Facing Progress Compression

## Erfolgskriterium fuer den Gesamtblock

Timus soll eine allgemeine mehrschrittige Aufgabe aus normalem Nutzertext so bearbeiten koennen, dass:

- die Teilziele explizit vorhanden sind
- die naechsten sinnvollen Schritte systemweit bekannt sind
- Follow-ups sauber daran anschliessen
- das System am realen Ziel orientiert bleibt
- der Nutzer nur noch bei echten Grenzen eingreifen muss

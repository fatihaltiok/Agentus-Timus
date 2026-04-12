# Timus Architektur-Blueprint fuer Folgeprojekte

Stand: 2026-04-11

## Zweck

Dieses Dokument beschreibt Timus nicht als Feature-Liste, sondern als wiederverwendbare Architekturvorlage.

Es soll beantworten:

- aus welchen Schichten Timus besteht
- wie diese Schichten aufeinander aufbauen
- welche Teile Kern sind und welche optional
- in welcher Reihenfolge man ein aehnliches System sinnvoll aufbaut
- welche Elemente Timus zu mehr als einem normalen Chatbot machen

Das Dokument ist bewusst fuer Folgeprojekte geschrieben, nicht nur fuer den Betrieb dieses Repos.

## Timus in einem Satz

Timus ist ein zustandsbehaftetes Multi-Agenten-System mit klarer Frontdoor, expliziter Meta-Orchestrierung, persistentem Gespraechsgedaechtnis, sichtbarer Runtime, Human-in-the-Loop-Workflows, kontrollierter Autonomie und einer beginnenden Self-Improvement-Pipeline.

## Was Timus architektonisch ausmacht

Timus ist nicht durch ein einzelnes Modell oder ein einzelnes Tool definiert, sondern durch die Kombination dieser Bausteine:

1. ein gemeinsames Runtime-Rueckgrat
2. eine klare Trennung zwischen Frontdoor, Meta und Spezialisten
3. explizite Zustandsfuehrung statt nur Chat-History
4. mehrschichtiges Memory statt einer einzigen Recall-Funktion
5. sichtbare Blocker-, Progress- und Resume-Zustaende
6. Human-in-the-Loop bei sensiblen externen Aktionen
7. Observability als eigenes Produktmerkmal
8. spaetere Selbstverbesserung nur auf Basis belastbarer Signale

Wenn du Timus als Vorlage fuer andere Projekte nutzen willst, dann kopiere nicht die Oberflaeche, sondern dieses Zusammenspiel.

## Schichtenmodell

```text
1. Kanaele und Interfaces
2. Runtime-Rueckgrat
3. Frontdoor und Routing
4. Meta-Orchestrierung
5. Spezialisten
6. Tools und Aussenwelt-Adapter
7. Zustand, Memory und Identitaet
8. Observability und Runtime-Sicht
9. Autonomie und Self-Healing
10. Human-in-the-Loop fuer reale Aktionen
11. Self-Improvement
```

Die unteren Schichten machen die oberen ueberhaupt erst sinnvoll. Timus funktioniert deshalb nicht gut, wenn man oben mit "mehr Agenten" beginnt, bevor Zustand, Observability und Handover klar sind.

## Die Schichten im Detail

### 1. Kanaele und Interfaces

Zweck:

- Nutzeranfragen annehmen
- Antworten, Progress und Blocker zurueckgeben
- Follow-ups ueber denselben Session-Kontext verarbeiten

Wichtige Teile:

- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- [gateway/telegram_gateway.py](/home/fatih-ubuntu/dev/timus/gateway/telegram_gateway.py)
- Android-/Canvas-Pfade im Server und UI

Warum diese Schicht wichtig ist:

- sie ist nicht nur I/O
- sie ist die Stelle, an der Sessions, Request-IDs, Follow-up-Capsules und sichtbare Workflow-Zustaende zusammenlaufen

Blueprint-Regel:

- baue frueh einen einzigen kanonischen Interface-Backbone
- vermeide getrennte Logik pro Kanal

### 2. Runtime-Rueckgrat

Zweck:

- zentraler Laufzeitkern fuer Tools, Sessions, SSE, Health und Lifecycle

Wichtige Teile:

- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)

Diese Schicht haelt bei Timus unter anderem:

- `/chat`
- `/health`
- Session-Capsules
- Canvas-/SSE-Transport
- Tool-Registry-Anbindung
- zentrale Observation-Hooks

Blueprint-Regel:

- der Runtime-Kern muss frueh existieren
- ohne ihn werden spaetere Autonomie-, Memory- und Workflow-Schichten schnell unkontrolliert

### 3. Frontdoor und Routing

Zweck:

- die erste schnelle Entscheidung treffen, welcher Verarbeitungspfad ueberhaupt sinnvoll ist

Wichtige Teile:

- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)

Rolle:

- schnelle Intent-Pfade
- Frontdoor-Guardrails
- Routing zu `meta` oder direkt zu Spezialpfaden
- Weitergabe von Follow-up-Kontext

Wichtig:

- der Dispatcher ist nicht "der eigentliche Agent"
- er ist die Frontdoor, die Routing-Fehler billig und frueh vermeiden soll

Blueprint-Regel:

- halte Frontdoor und Meta getrennt
- Routing ist nicht dasselbe wie Orchestrierung

### 4. Meta-Orchestrierung

Zweck:

- die Nutzeranfrage semantisch verstehen
- einen Antwortmodus waehlen
- Kontext bundeln
- Spezialisten koordinieren

Wichtige Teile:

- [agent/agents/meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- [orchestration/meta_response_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_response_policy.py)
- [orchestration/meta_self_state.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_self_state.py)

Meta ist in Timus:

- kein Allzweck-Toolcaller
- kein bloesser Antwortgenerator
- ein echter Orchestrator mit:
  - Turn-Verstehen
  - Policy
  - Rezept-/Handoff-Logik
  - Self-State

Blueprint-Regel:

- Meta muss wissen, was fuer eine Art Turn vorliegt
- und ob die richtige Reaktion Ausfuehren, Zusammenfassen, Nachfragen, Handover oder Blockieren ist

### 5. Spezialisten

Zweck:

- konkrete Arbeitstypen getrennt und fokussiert bearbeiten

Wichtige Teile:

- [agent/agents/executor.py](/home/fatih-ubuntu/dev/timus/agent/agents/executor.py)
- [agent/agents/research.py](/home/fatih-ubuntu/dev/timus/agent/agents/research.py)
- [agent/agents/visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
- [agent/agents/system.py](/home/fatih-ubuntu/dev/timus/agent/agents/system.py)
- weitere Agenten in [agent/agents](/home/fatih-ubuntu/dev/timus/agent/agents)
- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)

Was Timus hier besonders macht:

- Spezialisten tragen heute echten Kontext mit
- sie koennen Alignment pruefen
- sie koennen Ruecksignale wie `context_mismatch` oder `needs_meta_reframe` emittieren

Wichtige Hilfsschicht:

- [orchestration/specialist_context.py](/home/fatih-ubuntu/dev/timus/orchestration/specialist_context.py)
- [orchestration/specialist_context_eval.py](/home/fatih-ubuntu/dev/timus/orchestration/specialist_context_eval.py)

Blueprint-Regel:

- Spezialisten sollen nicht blind delegiert werden
- sie brauchen einen normalisierten Kontextvertrag

### 6. Tools und Aussenwelt-Adapter

Zweck:

- die reale Welt anbinden:
  - Browser
  - Web
  - OCR
  - Vision
  - Files
  - Search
  - Mail
  - System

Wichtige Teile:

- Tool-Implementierungen unter [tools](/home/fatih-ubuntu/dev/timus/tools)

Architekturprinzip:

- tool-first statt prompt-first
- echte Faehigkeiten sollen ueber explizite Tools laufen, nicht ueber implizite Behauptungen

Blueprint-Regel:

- halte Tools klar vom Agentenprompt getrennt
- Agenten entscheiden, Tools fuehren aus

### 7. Zustand, Memory und Identitaet

Das ist einer der wichtigsten Unterschiede zwischen Timus und einem normalen Chatbot.

#### 7a. Gespraechszustand

Wichtige Teile:

- [orchestration/conversation_state.py](/home/fatih-ubuntu/dev/timus/orchestration/conversation_state.py)
- [orchestration/turn_understanding.py](/home/fatih-ubuntu/dev/timus/orchestration/turn_understanding.py)
- [orchestration/topic_state_history.py](/home/fatih-ubuntu/dev/timus/orchestration/topic_state_history.py)

Aufgaben:

- aktives Thema
- aktives Ziel
- offene Schleifen
- erwarteter naechster Schritt
- Turn-Typ
- historischer Topic-Retrieval-Pfad
- State-Decay

#### 7b. Preference- und Instruction-Memory

Wichtige Teile:

- [orchestration/preference_instruction_memory.py](/home/fatih-ubuntu/dev/timus/orchestration/preference_instruction_memory.py)

Aufgabe:

- persistente, thematische Nutzerpraeferenzen und Arbeitsregeln

#### 7c. Kanonisches Memory

Wichtige Teile:

- [memory/memory_system.py](/home/fatih-ubuntu/dev/timus/memory/memory_system.py)
- [memory/memory_guard.py](/home/fatih-ubuntu/dev/timus/memory/memory_guard.py)
- [memory/markdown_store](/home/fatih-ubuntu/dev/timus/memory/markdown_store)

Aufgaben:

- Session Memory
- persistentes Langzeitgedaechtnis
- semantischer Recall
- kontrollierte Schreibrechte

#### 7d. Persoenlichkeit und Identitaet

Wichtige Teile:

- [memory/soul_engine.py](/home/fatih-ubuntu/dev/timus/memory/soul_engine.py)
- [memory/reflection_engine.py](/home/fatih-ubuntu/dev/timus/memory/reflection_engine.py)

Wichtige Einordnung:

- Persoenlichkeit ist in Timus keine bloesse Prompt-Deko
- sie haengt an Reflection und Memory
- fuer Folgeprojekte ist sie optional

Blueprint-Regel:

- Identitaet und Persoenlichkeit erst dann einbauen, wenn Zustand und Memory schon sauber sind
- sonst wird "Persoenlichkeit" nur instabiler Promptstil

### 8. Observability und Runtime-Sicht

Zweck:

- Laufzeit nicht nur ausfuehren, sondern sichtbar und auswertbar machen

Wichtige Teile:

- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
- [orchestration/longrunner_transport.py](/home/fatih-ubuntu/dev/timus/orchestration/longrunner_transport.py)
- [server/canvas_ui.py](/home/fatih-ubuntu/dev/timus/server/canvas_ui.py)

Aufgaben:

- Request-Korrelation
- Laufzeitereignisse
- Progress, Partial Results, Blocker, Resume
- D0-, Phase-D- und Phase-E-Metriken

Blueprint-Regel:

- Observability ist kein spaeteres Add-on
- ohne sie werden Autonomie, Self-Healing und Self-Improvement schnell blind

### 9. Autonomie und Self-Healing

Zweck:

- Systemzustand beobachten
- Probleme erkennen
- begrenzt reagieren
- Wiederanlauf, Diagnose und Härtung organisieren

Wichtige Teile:

- [orchestration/autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)
- [orchestration/self_healing_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_healing_engine.py)
- [orchestration/health_orchestrator.py](/home/fatih-ubuntu/dev/timus/orchestration/health_orchestrator.py)
- [orchestration/autonomy_scorecard.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_scorecard.py)
- [orchestration/self_modifier_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_modifier_engine.py)
- [orchestration/self_hardening_rollout.py](/home/fatih-ubuntu/dev/timus/orchestration/self_hardening_rollout.py)

Architekturpunkt:

- Autonomie ist bei Timus kein einzelner Schalter
- sie ist ein Set aus:
  - Zielen
  - Health
  - Recovery
  - Bewertung
  - kontrollierter Aenderung

Blueprint-Regel:

- baue Autonomie erst auf Observability, Policy und Runtime-Haertung auf
- nicht vorher

### 10. Human-in-the-Loop fuer reale Aktionen

Das ist der Phase-D-Kern.

Wichtige Teile:

- [orchestration/approval_auth_contract.py](/home/fatih-ubuntu/dev/timus/orchestration/approval_auth_contract.py)
- [orchestration/pending_workflow_state.py](/home/fatih-ubuntu/dev/timus/orchestration/pending_workflow_state.py)
- [orchestration/auth_session_state.py](/home/fatih-ubuntu/dev/timus/orchestration/auth_session_state.py)

Aufgaben:

- Approval und Consent
- user-mediated Login
- Session-Reuse
- Challenge-Handover
- strukturierte Pending-Workflows

Warum diese Schicht zentral ist:

- sie macht aus einem "Agenten mit Browser" erst einen sicheren assistiven Workflow-Agenten

Blueprint-Regel:

- sensible Aktionen nie nur als Chattext modellieren
- immer als sichtbaren Workflow-Zustand

### 11. Self-Improvement

Das ist der Phase-E-Kern.

Wichtige Teile:

- [orchestration/improvement_candidates.py](/home/fatih-ubuntu/dev/timus/orchestration/improvement_candidates.py)
- [orchestration/self_improvement_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_improvement_engine.py)
- [orchestration/session_reflection.py](/home/fatih-ubuntu/dev/timus/orchestration/session_reflection.py)

Aufgaben:

- Reflection-, Incident- und Observation-Signale zusammenfuehren
- deduplizieren
- priorisieren
- Freshness und Decay beruecksichtigen
- operator-lesbar machen

Architekturpunkt:

- Self-Improvement kommt nach Zustand, Observability und Human-in-the-Loop
- sonst verbessert das System nur unscharfe Symptome

## Wie alles aufeinander aufbaut

Die Abhaengigkeiten sehen vereinfacht so aus:

```text
Kanaele
  -> Runtime-Rueckgrat
    -> Dispatcher
      -> Meta-Orchestrierung
        -> Spezialisten
          -> Tools

Runtime-Rueckgrat
  -> Session-Capsules
    -> Gespraechszustand
    -> Pending-Workflow-State
    -> Auth-Session-State

Gespraechszustand + Memory
  -> Meta-Entscheidungen
  -> Specialist-Context
  -> Historical Recall

Observability
  -> Runtime-Diagnose
  -> Self-Healing
  -> Improvement-Kandidaten

Approval/Auth/Challenge
  -> sichere externe Aktionen

Self-Improvement
  -> spaetere Hardening- und Compiler-Schritte
```

Wichtig:

- Memory ohne gute Frontdoor erzeugt Recall-Fehler
- Spezialisten ohne gemeinsamen Kontextvertrag erzeugen Drift
- Autonomie ohne Observability erzeugt Blindflug
- Self-Improvement ohne Incident- und Observation-Basis erzeugt nur Scheinverbesserungen

## End-to-End-Fluss in Timus

Ein typischer Turn sieht so aus:

1. Anfrage kommt ueber Canvas, Telegram, Android oder Terminal herein.
2. Der MCP-Server vergibt Session-/Request-Kontext und baut eine Follow-up-Capsule.
3. Der Dispatcher entscheidet den ersten Pfad.
4. Meta analysiert Turn-Typ, Ziel, Kontext und Antwortmodus.
5. Meta delegiert an einen Spezialisten oder beantwortet selbst.
6. Der Spezialist fuehrt mit Tools oder weiteren Handoffs aus.
7. Runtime-Events, Progress und Blocker werden beobachtet und sichtbar gemacht.
8. Conversation State, Topic History, Pending Workflows oder Auth Session State werden aktualisiert.
9. Observation- und Reflection-Signale koennen spaeter in Self-Healing oder Self-Improvement einfliessen.

## Was fuer Folgeprojekte Pflicht ist und was optional

### Pflichtkern

Wenn du Timus als Vorlage nutzt, solltest du fast immer mit diesem Kern starten:

- ein gemeinsamer Runtime-Backbone
- ein Frontdoor-Dispatcher
- eine Meta-Orchestrierung
- expliziter Gespraechszustand
- Tool-first-Adapter
- Observability

### Zweite Ausbaustufe

Danach sinnvoll:

- Topic History und Preference-Memory
- Specialist Context
- Longrunner-/Blocker-Transport
- Human-in-the-Loop fuer sensible Aktionen

### Dritte Ausbaustufe

Erst spaeter:

- Persoenlichkeits-/Soul-Layer
- Autonomy Scorecard
- Self-Healing-Loops
- Self-Improvement-Pipeline
- Self-Modification

## Empfohlene Aufbau-Reihenfolge fuer neue Projekte

### Stufe 1: Runtime + Frontdoor

Baue zuerst:

- einen stabilen API-/Runtime-Kern
- Health
- Session-Kontext
- einen Dispatcher

Ohne das lohnt der Rest kaum.

### Stufe 2: Meta + ein echter Spezialist

Baue dann:

- Meta-Orchestrierung
- einen universellen Executor oder Visual-/Research-Spezialisten
- eine kleine Toolschicht

Damit entsteht der erste brauchbare Arbeitsagent.

### Stufe 3: Zustand und Memory

Dann:

- Conversation State
- Topic History
- Preference-/Instruction-Memory

Ab hier wird das System ueber mehrere Turns wirklich besser.

### Stufe 4: Sichtbare Runtime

Dann:

- Progress
- Blocker
- Resume
- Request-Korrelation

Ab hier wird das System operativ belastbar.

### Stufe 5: Human-in-the-Loop

Dann:

- Approval
- Auth
- Login-Handover
- Session-Reuse

Ab hier kann das System mit realen externen Konten umgehen, ohne unsauber zu werden.

### Stufe 6: Autonomie und Selbstverbesserung

Erst danach:

- Self-Healing
- Scorecards
- Self-Improvement
- spaetere Self-Modification

## Was du nicht blind kopieren solltest

- nicht mit 10 Agenten starten
- nicht mit Persoenlichkeitslogik starten
- nicht mit Self-Modification starten
- nicht Passwoerter oder Secrets in den Agenten selbst ziehen
- nicht alles als "Memory" behandeln
- nicht Observability auf spaeter verschieben

## Praktische Uebersetzung fuer neue Projekte

Wenn du Timus als Vorlage verwendest, kannst du die Architektur in generische Rollen uebersetzen:

| Timus-Begriff | Allgemeine Rolle |
| --- | --- |
| MCP-Server | Runtime-Backbone |
| Dispatcher | Frontdoor Router |
| Meta | Orchestrator |
| Spezialisten | Capability-specific Workers |
| Conversation State | Task Context State |
| Topic History | Resumeable Topic Memory |
| Preference Memory | Durable User Profile |
| Pending Workflow | Human-in-the-Loop State Machine |
| Auth Session State | Scoped Auth Capability State |
| Observation | Unified Runtime Telemetry |
| Improvement Candidates | Improvement Backlog Input |
| Soul Engine | optionale Identity/Personality Layer |

## Der eigentliche Bauplan

Wenn du nur eine Sache aus diesem Dokument mitnimmst, dann diese:

Timus ist nicht "ein Modell plus viele Tools", sondern eine Reihenfolge:

1. Runtime
2. Routing
3. Orchestrierung
4. Zustand
5. Spezialisten
6. Observability
7. sichere externe Aktionen
8. kontrollierte Autonomie
9. kontrollierte Selbstverbesserung

Wenn diese Reihenfolge eingehalten wird, entsteht ein System, das ueber laengere Zeit stabiler, persoenlicher und operativ brauchbarer wird. Wenn sie uebersprungen wird, entstehen meist nur unklare Agentenschleifen mit viel Prompting und wenig Architektur.

## Verwandte Dokumente

- [README.md](/home/fatih-ubuntu/dev/timus/README.md)
- [Phase D Vorbereitung - Approval, Auth und User Handover](/home/fatih-ubuntu/dev/timus/docs/PHASE_D_APPROVAL_AUTH_PREP.md)
- [Phase E Plan - Self-Improvement und kontrollierte Selbstpflege](/home/fatih-ubuntu/dev/timus/docs/PHASE_E_SELF_IMPROVEMENT_PLAN.md)
- [Timus: Technische Gesamtdokumentation](/home/fatih-ubuntu/dev/timus/docs/TIMUS_TECHNISCHE_GESAMTDOKUMENTATION_2026-04-06.md)

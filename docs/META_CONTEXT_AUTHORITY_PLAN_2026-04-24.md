# Meta Context Authority Plan

Stand: 2026-04-24

## Problem

Timus hat fuer `meta` noch keine vollstaendig autoritative Reihenfolge bei
Anfrageverstehen und Kontextladung.

Heute wirken mehrere Schichten gleichzeitig auf die Meta-Entscheidung:

- `server/mcp_server.py`
- `orchestration/meta_orchestration.py`
- `orchestration/meta_request_frame.py`
- `main_dispatcher.py`
- `agent/agents/meta.py`
- `agent/base_agent.py`
- `memory/memory_system.py`

Dadurch entstehen weiter Fehlerklassen wie:

- korrekter Frame, aber spaeter falscher Kontext
- Working-Memory driftet trotz sauberem Request-Frame
- Session-Reste aus einer anderen Domaene kippen in die neue Anfrage
- `general_advisory` wird zu breit und landet im falschen Modus
- `meta` reagiert auf Kontext statt auf die eigentliche Frage

## Kernhypothese

Meta muss zuerst bewusst entscheiden, **welche Anfrage vorliegt**.
Erst danach darf Kontext geladen werden.

Nicht:

1. breiten Kontext laden
2. ihn mit der Anfrage vermischen
3. spaeter versuchen, Drift zu reparieren

Sondern:

1. `request_frame` bilden
2. `interaction_mode` bestimmen
3. erlaubte Kontextklassen festlegen
4. nur dann Kontext zulassen
5. Working-Memory nur noch innerhalb dieses Rahmens nachladen

## Ziel

Es gibt genau **eine autoritative Kontextkette fuer Meta**:

1. `meta_request_frame`
2. `meta_interaction_mode`
3. `meta_context_admission`
4. `specialist_context_seed`
5. bounded `working_memory`

Alles, was spaeter geladen wird, ist dieser Kette untergeordnet.

## Wer heute Kontext fuer Meta laedt

### 1. Rohquellen

- `server/mcp_server.py`
  - Chat-Historie
  - semantischer Recall
  - Preference-Memory
  - Follow-up-/Capsule-Daten

### 2. Primaere Orchestrierung

- `orchestration/meta_orchestration.py`
  - `classify_meta_task(...)`
  - `build_meta_context_bundle(...)`
  - baut heute den wichtigsten vorgelagerten Meta-Kontext

### 3. Handoff

- `main_dispatcher.py`
  - traegt `meta_request_frame_json`
  - `meta_interaction_mode_json`
  - `meta_context_bundle_json`
  - `specialist_context_seed_json`

### 4. Meta-Parsing

- `agent/agents/meta.py`
  - liest Handoff und baut den Meta-Prompt

### 5. Laufzeit-Nachladung

- `agent/base_agent.py`
  - `_build_working_memory_context(...)`
- `memory/memory_system.py`
  - `build_working_memory_context(...)`

Das ist aktuell die gefaehrlichste zweite Kontextschicht, weil sie trotz
sauberem Frame spaeter wieder driftenden Recall nachladen kann.

## Architekturentscheidung

Die autoritative Reihenfolge liegt kuenftig **vor** dem eigentlichen Meta-Run:

1. `meta_request_frame` ist die erste Entscheidung
2. `meta_interaction_mode` ist die zweite Entscheidung
3. `meta_context_bundle` wird nur aus frame-zulaessigen Klassen gebaut
4. `working_memory` darf nur noch unter demselben Vertrag laden

`working_memory` ist damit keine freie Zusatzintelligenz mehr, sondern ein
nachgelagerter Hilfspfad.

## Harte Invarianten

### MCA1. Frame First

Jede Meta-Anfrage bekommt zuerst einen expliziten Request-Frame.

### MCA2. Context Admission Before Prompt

Kein `semantic_recall`, `preference_memory` oder `topic_memory` darf in den
Meta-Prompt, wenn der Frame diese Klasse nicht erlaubt.

### MCA3. Working Memory Is Subordinate

`BaseAgent._build_working_memory_context(...)` darf keine Kontextklasse laden,
die im Frame oder Klarheitsvertrag nicht erlaubt ist.

### MCA4. One Primary Source Per Knowledge Class

Pro Klasse gibt es genau eine primaere Quelle:

- `conversation_state`
- `semantic_recall`
- `document_knowledge`
- `preference_profile`

Diese Klassen duerfen im Antwortpfad nicht als gleichwertige Mischquelle
behandelt werden.

### MCA5. Evidence Type Awareness

Meta muss intern unterscheiden zwischen:

- Arbeitszustand
- weicher Erinnerung
- harter Dokumentquelle
- Nutzerpraeferenz

Ohne diese Trennung gibt es weiter plausible, aber falsch begruendete Antworten.

## Reihenfolge im Gesamtprogramm

Dieser Block kommt **vor** dem breiteren Maßnahmenkatalog.

Praezise:

- er ist **kein separater Nachtrag nach dem Maßnahmenkatalog**
- er ist die **Voraussetzung** fuer dessen P0-Teil
- besonders fuer:
  - klareren Runtime-Kern
  - Tool-/Mode-Profile
  - vereinfachte Session-/Search-Basis

Ohne diese Autoritaetskette wuerden wir Produktmaßnahmen auf einen weiter
konkurrierenden Kontextpfad setzen und die Instabilitaet nur breiter verteilen.

Kurz:

- **erst Meta Context Authority**
- **danach breitere Produktisierung aus dem Maßnahmenkatalog**

## Umsetzung in Slices

### MCA1. Context Authority Contract

Ziel:

- kanonischer Vertrag fuer:
  - `frame`
  - `interaction_mode`
  - `allowed_context_classes`
  - `working_memory_budget`

Erfolg:

- jede Meta-Anfrage hat vor Promptbau einen expliziten Autoritaetsvertrag

### MCA2. Orchestration Becomes Authoritative

Ziel:

- `classify_meta_task(...)` und `build_meta_context_bundle(...)` werden die
  einzige autoritative Quelle fuer Meta-Kontext vor dem Run

Umfang:

- Handoff nur noch aus diesem Vertrag ableiten
- keine parallelen impliziten Kontextpfade im Dispatcher

Erfolg:

- `meta_context_bundle` ist nicht mehr nur Beilage, sondern die kanonische
  vorgelagerte Meta-Sicht

### MCA3. Working Memory Gating

Ziel:

- `BaseAgent` und `memory_system` respektieren den Vertrag hart

Umfang:

- Working-Memory-Query an `frame` und `request_kind` binden
- verbotene Klassen gar nicht laden
- Query-Preview und Telemetrie um zugelassene Klassen erweitern

Erfolg:

- kein `Twilio`-Leak in Reisefragen
- keine Standortlogik in nicht-lokalen Advisory-Faellen

### MCA4. Session Domain Separation

Ziel:

- Session-Reste werden domain-sensitiver getrennt

Umfang:

- `general_advisory` weiter aufspalten
  - z. B. `travel_advisory`, `topic_advisory`, `life_advisory`
- Topic-State und Follow-up-Capsules an diese Domaenen koppeln

Erfolg:

- offene Beratungsfragen kippen nicht mehr so leicht auf alte Technik- oder
  Setup-Themen

### MCA5. Evidence Class Plumbing

Ziel:

- Dokumente, Recall und Profile sind im Antwortpfad sauber unterscheidbar

Umfang:

- Knowledge-Class-Tags durch Handoff und Telemetrie tragen
- spaetere PDF-/Dokumentpfade direkt daran anschliessen

Erfolg:

- bessere Basis fuer spaetere PDF-Knowledge-Base
- weniger unerkannte Mischantworten

### MCA6. Live Gates

Pflichtfaelle:

- `wo kann ich am Wochenende hin in Deutschland`
- `ich mag Staedte und Kultur`
- `Ohne Recherche: Was ist deine Meinung dazu?`
- `Schau mal nach, ob es schon Vorbereitungen gibt, aber nichts umsetzen`
- `Richte das jetzt ein`
- `lies docs/... und sag was als naechstes ansteht`

Erfolg:

- kein Cross-Domain-Leak
- kein falscher Nearby-/Standortpfad
- kein Setup-Kontext in Reise- oder Advisory-Faellen

## Entscheidender Nutzen

Dieser Block schliesst die Luecke zwischen:

- sauberem Frame auf dem Papier
- und tatsaechlich autoritativem Kontext in der Laufzeit

Er ist damit die notwendige Bruecke zwischen dem bisherigen Meta-Umbau und dem
spaeteren Maßnahmenkatalog zur Produktisierung.

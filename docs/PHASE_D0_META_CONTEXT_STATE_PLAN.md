# Phase D0 - Meta Context State und semantische Gespraechskontinuitaet

Stand: 2026-04-06

## Warum dieser Block vor Phase D kommen sollte

Timus hat bereits:

- Follow-up-Capsules
- `session_summary`
- `topic_recall`
- `semantic_recall`
- `pending_followup_prompt`
- Meta-Orchestrierung mit Rezepten und Adaptive-Plan-Memory

Das reicht fuer viele Faelle, aber noch nicht fuer robuste Gespraechskontinuitaet.

Der eigentliche Engpass ist:

- `meta` entscheidet noch zu oft turn-lokal
- Kontext wird zwar injiziert, aber nicht immer als stabiler Gespraechszustand gefuehrt
- Praeferenz- und Verhaltensanweisungen werden nicht konsistent als solche behandelt
- thematische Drift und Fehltrigger entstehen, wenn alte Assistant-Texte oder Spezialpfade zu stark wirken

Wenn dieser Block nicht zuerst gehaertet wird, bleiben spaetere Phasen fragil:

- Phase D scheitert an falsch verstandenen Nutzeranweisungen in laengeren Workflows
- Phase E lernt auf einem unsauberen Gespraechsmodell und erzeugt wieder nur lokale Guards

Deshalb bekommt Timus vor D1-D5 einen eigenen Fundament-Block:

- **D0 Meta Context State**

## Zielbild

`meta` arbeitet nicht mehr nur auf dem aktuellen Turn plus etwas Recall, sondern auf einem expliziten, laufend gepflegten Gespraechszustand pro Session.

Dieser Zustand beantwortet fuer jeden neuen Turn:

- Worueber reden wir gerade wirklich
- Was ist das aktive Ziel
- Was ist noch offen
- Welche Nutzerpraeferenzen gelten fuer dieses Thema
- Ist der neue Turn eine Aufgabe, Korrektur, Praeferenz, Beschwerde, Nachfrage oder Fortsetzung
- Welcher Teil des alten Kontexts darf helfen und welcher darf die aktuelle Frage nicht ueberstimmen

## Grundprinzipien

1. Die aktuelle Nutzerfrage bleibt primaer.

- Alter Kontext darf erklaeren, aber nicht ueberstimmen.
- Spezialrouten duerfen nie nur wegen alten Triggerwoertern feuern.

2. `meta` fuehrt Zustand, nicht nur Text.

- Nicht nur vergangene Turns injizieren.
- Explizit `active_topic`, `active_goal`, `open_loop`, `preferences`, `recent_corrections`, `next_expected_step` fuehren.

3. User-Absicht geht vor Assistant-Nachhall.

- User-Turns, Nutzerkorrekturen und laufende offene Ziele sind staerker als alte Assistant-Formulierungen.

4. Jeder Turn wird neu semantisch bewertet.

- nicht nur `query -> recipe`
- sondern:
  - `query + session_state + relevant_memory + current_open_loop -> turn_type + state_update + route`

5. Keine lokale Guard-Sammlung als Hauptstrategie.

- Spezialheuristiken bleiben nur als Sicherheitsnetz.
- Hauptmechanismus ist ein stabiler semantischer Zustandsapparat.

## Kernprobleme, die D0 loesen muss

1. Vage Anweisungen im laufenden Chat

- `mach das in zukunft so`
- `merk dir das`
- `dann nimm kuenftig Reuters zuerst`
- `so meinte ich das nicht`

2. Knappe Follow-ups mit starkem Kontextbezug

- `und jetzt`
- `die erste option`
- `mach weiter`
- `nein anders`

3. Themenuebergaenge ohne harten Bruch

- von News zu Strategie
- von Analyse zu Handlung
- von Kritik an der letzten Antwort zu neuer Arbeitsanweisung

4. Langfristige Kontinuitaet ueber Tage

- ein Thema spaeter wieder aufnehmen
- letzte Entscheidungslage wiederfinden
- relevante Nutzerpraeferenzen themenspezifisch rehydrieren

## Zielarchitektur

### 1. Session Conversation State

Pro Session entsteht ein strukturierter Zustand, nicht nur eine Chat-History.

Minimalfelder:

```json
{
  "session_id": "canvas_...",
  "active_topic": "aktuelle Weltlage und News-Qualitaet",
  "active_goal": "brauchbare aktuelle Lageeinschaetzung mit belastbaren Quellen",
  "open_loop": "News-Zugriff zuerst ueber Agenturmeldungen priorisieren",
  "turn_type_hint": "preference_update",
  "preferences": [
    "bei aktuellen News Agenturquellen priorisieren",
    "ehrlich sagen wenn nur Hintergrundquellen vorliegen"
  ],
  "recent_corrections": [
    "nicht wieder allgemeine Deep-Research-Quellen statt Echtzeit-News verwenden"
  ],
  "next_expected_step": "naechster News-Check soll Reuters/AP/dpa/AFP bevorzugen",
  "state_confidence": 0.86,
  "updated_at": "2026-04-06T16:40:00Z"
}
```

Erweiterbar:

- `open_questions`
- `working_constraints`
- `task_stack`
- `topic_chain`
- `source_preferences`
- `style_preferences`
- `last_failure_reason`

### 2. Turn Understanding Layer vor Routing

Vor Rezeptwahl wird jeder Turn als semantischer Typ klassifiziert.

Startmenge:

- `new_task`
- `followup`
- `clarification`
- `correction`
- `preference_update`
- `behavior_instruction`
- `complaint_about_last_answer`
- `approval_response`
- `auth_response`
- `result_extraction`
- `handover_resume`

Wichtig:

- ein Turn kann mehrere Signale tragen
- aber genau ein dominanter `turn_type` steuert die naechste Meta-Entscheidung

### 3. Context Rehydration vor Meta-Entscheidung

Vor jeder Meta-Klassifikation wird ein kompakter Kontextblock aufgebaut.

Reihenfolge:

1. `current_user_query`
2. `session conversation state`
3. letzte offene Schleife oder `pending_followup_prompt`
4. letzte relevante User-Turns
5. thematische Langzeitpraeferenzen
6. semantischer Recall aus Session / Qdrant
7. erst spaet Assistant-Reply-Points als Fallback

Nicht Ziel:

- moeglichst viel Text in den Prompt werfen

Ziel:

- moeglichst wenig, aber semantisch sauber priorisierten Kontext liefern

### 4. Topic Memory und Preference Memory trennen

Es braucht zwei verschiedene Gedaechtnisarten:

- `topic memory`
  - worum ging es in diesem Themenstrang
  - was war das letzte belastbare Zwischenfazit
  - welche offenen Fragen gibt es

- `preference memory`
  - wie soll Timus bei diesem Nutzer oder in diesem Thema arbeiten
  - z. B.:
    - bei News Agenturquellen zuerst
    - lieber kompakte Antworten als lange Reports
    - bei unsicherem Befund ehrlich Grenzen nennen

Diese beiden Memory-Typen duerfen nicht vermischt werden.

### 5. State Update nach jedem Turn

Nach jeder Meta- oder Spezialistenantwort wird der Session-State aktualisiert:

- Thema bestaetigt / verschoben / gewechselt
- offenes Ziel erledigt / offen / ersetzt
- Nutzerkorrektur aufgenommen
- neue Praeferenz gespeichert
- offener naechster Schritt gesetzt

## Konkreter Umsetzungsplan

### D0.1 Conversation-State-Schema

Ziel:

- offizielles Datenmodell fuer `conversation_state`

Lieferobjekte:

- neues Modul, z. B. `orchestration/conversation_state.py`
- Dataclass oder TypedDict fuer:
  - `ConversationState`
  - `TurnInterpretation`
  - `StateUpdate`
- stabile Serialisierung fuer Session-Speicher

Dateien mit hoher Wahrscheinlichkeit:

- `server/mcp_server.py`
- `orchestration/meta_orchestration.py`
- neues `orchestration/conversation_state.py`

### D0.2 Turn-Understanding-Layer

Ziel:

- semantische Turn-Typ-Erkennung als eigener Schritt vor Rezeptwahl

Lieferobjekte:

- `classify_turn_intent(...)`
- dominantem `turn_type`
- Evidenzliste pro Entscheidung
- sauberer Vorrang fuer:
  - Nutzerkorrektur
  - Praeferenz-/Verhaltensanweisung
  - offene Action-/Approval-/Auth-Resumes

Nicht machen:

- zehn neue starre Spezialrezepte bauen

Vorbereitung dokumentiert in:

- [D0_2_TURN_UNDERSTANDING_PREP.md](/home/fatih-ubuntu/dev/timus/docs/D0_2_TURN_UNDERSTANDING_PREP.md)

### D0.3 Context-Rehydration-Pipeline

Ziel:

- Meta bekommt jedes Mal einen kleinen, priorisierten Kontextblock aus Zustand + Recall

Lieferobjekte:

- `build_meta_context_bundle(...)`
- Priorisierungsregeln fuer:
  - current query
  - conversation state
  - open loop
  - relevant user turns
  - topic memory
  - preference memory

### D0.4 Topic-State und Open-Loops

Ziel:

- Timus weiss, was noch offen ist und worauf ein kurzer Turn sich wahrscheinlich bezieht

Lieferobjekte:

- `active_topic`
- `active_goal`
- `open_loop`
- `next_expected_step`
- `topic_shift_detected`

Beispiele:

- `die erste option`
- `dann mach weiter`
- `so aber mit live-news`

### D0.5 Preference- und Instruction-Memory

Ziel:

- spontane Anweisungen werden nicht nur lokal beantwortet, sondern als Arbeitsweise konserviert

Lieferobjekte:

- topic-gebundene Praeferenzspeicherung
- Nutzerweite Praeferenzen nur bei hoher Stabilitaet
- Trennung:
  - globale Preference
  - thematische Preference
  - nur aktueller Session-Hinweis

Beispiele:

- global:
  - `antworte kurz`
- thematisch:
  - `bei News zuerst Agenturquellen`
- session-lokal:
  - `fuer diesen Vergleich nur Deutschland betrachten`

### D0.6 Meta-Policy fuer Antwortmodus

Ziel:

- `meta` entscheidet nicht nur den Agentenpfad, sondern auch den Antwortmodus

Startmodi:

- `execute`
- `acknowledge_and_store`
- `clarify_before_execute`
- `correct_previous_path`
- `resume_open_loop`
- `summarize_state`

Beispiel:

- `dann mach das in zukunft so ...`
  - nicht `execute lookup`
  - sondern `acknowledge_and_store`

### D0.7 Observability und Evaluation

Ziel:

- diese Schicht muss messbar werden, sonst endet sie wieder in unsichtbaren Prompt-Aenderungen

Neue Signale:

- `meta_turn_type_selected`
- `conversation_state_updated`
- `topic_shift_detected`
- `preference_captured`
- `preference_applied`
- `context_rehydration_bundle_built`
- `context_misread_suspected`

Eval-Sets:

- Korrekturen
- Praeferenzanweisungen
- kurze Referenz-Follow-ups
- thematische Wiederaufnahme nach Tagen
- Beschwerde ueber letzte Antwort plus neue Arbeitsanweisung

### D0.8 Sicheres Vergessen und State-Decay

Ziel:

- nicht alles fuer immer festhalten

Regeln:

- session-lokale Hinweise verfallen zuerst
- thematische Preferences bleiben laenger
- globale Preferences nur bei wiederholter Evidenz
- veraltete offene Schleifen muessen sauber geschlossen werden

## Empfohlene Reihenfolge

1. D0.1 Conversation-State-Schema
2. D0.2 Turn-Understanding-Layer
3. D0.3 Context-Rehydration-Pipeline
4. D0.4 Topic-State und Open-Loops
5. D0.5 Preference-/Instruction-Memory
6. D0.6 Meta-Policy fuer Antwortmodus
7. D0.7 Observability und Eval
8. D0.8 State-Decay und Cleanup

## Dateien, die voraussichtlich Kernrollen spielen

- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- [agent/agents/meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- [server/conversation_qdrant.py](/home/fatih-ubuntu/dev/timus/server/conversation_qdrant.py)
- [memory/memory_system.py](/home/fatih-ubuntu/dev/timus/memory/memory_system.py)
- [orchestration/longrunner_transport.py](/home/fatih-ubuntu/dev/timus/orchestration/longrunner_transport.py)
- [logs/autonomy_observation.jsonl](/home/fatih-ubuntu/dev/timus/logs/autonomy_observation.jsonl)

## Was nicht der richtige Weg ist

- mehr isolierte Regex-Guards als Hauptstrategie
- nur Prompt vergroessern
- immer mehr alte Turns in den Prompt kippen
- Assistant-Texte als primaeren Themenanker benutzen
- Praeferenzspeicherung ohne Topic-/Scope-Trennung

## Erfolgskriterien

Timus ist nach D0 besser, wenn:

1. spontane Verhaltensanweisungen konsistent als solche erkannt werden
2. kurze Follow-ups im laufenden Thema robust aufgeloest werden
3. ein Thema nach Tagen wieder aufgenommen werden kann, ohne den Bezug zu verlieren
4. `meta` seltener in falsche Spezialpfade driftet
5. Nutzerkorrekturen spaeter sichtbar angewendet werden
6. Phase D auf diesem Zustand aufsetzen kann, statt eigene Kontext-Workarounds zu bauen

## Roadmap-Einordnung

Dieser Block sollte **vor D1-D5** umgesetzt werden oder als `D0` direkt davor laufen.

Begruendung:

- D1-D5 brauchen stabiles Kontextverstaendnis
- ansonsten werden Approval, Auth und Handover im laufenden Gespraech wieder falsch verstanden
- Phase E sollte auf D0 aufbauen, weil erst dann eine echte Schwaeche-zu-Verbesserung-Kette semantisch belastbar wird

Kurz:

- **Phase C**: Runtime-Haertung
- **Phase D0**: Meta Context State
- **Phase D1-D5**: Approval, Auth, Handover, assistive Workflows
- **Phase E**: Self-Improvement auf belastbarer Gespraechsbasis

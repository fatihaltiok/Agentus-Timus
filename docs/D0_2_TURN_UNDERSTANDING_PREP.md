# D0.2 Vorbereitung - Turn Understanding Layer fuer Meta

Stand: 2026-04-06

## Zweck

D0.2 fuehrt fuer Timus eine eigene semantische Turn-Verstehensschicht ein.

Heute kann `meta` bereits:

- `effective_query` aus Follow-up-Capsules ziehen
- `context_anchor`, `active_topic`, `open_goal`, `constraints` aus komprimierten Follow-ups ableiten
- einige mehrdeutige Faelle ueber `semantic_ambiguity_hints` markieren
- daraus direkt Routing und Rezeptwahl ableiten

Das reicht fuer viele Faelle, aber es mischt noch zu viele Ebenen:

- Turn-Verstehen
- Zustandsdeutung
- Review-Hinweise
- Agentenrouting
- Rezeptwahl

## Zielbild

Vor jeder Meta-Entscheidung entsteht ein eigener `TurnInterpretation`-Block.

Er beantwortet fuer genau diesen Turn:

- Was ist der dominante Turn-Typ
- Welche semantischen Signale liegen gleichzeitig vor
- Worum geht es im Kern
- Bezieht sich der Turn auf eine laufende Schleife, Korrektur oder Praeferenz
- Welcher Antwortmodus ist sinnvoll
- Welche Teile des Session-State sollen aktualisiert werden

Erst **danach** folgt:

- Route
- Rezeptwahl
- Spezialisten-Handoff

## Warum das noetig ist

Die bisherigen Fehler zeigen das Muster klar:

1. Praeferenz-/Verhaltensanweisung wurde als Live-Lookup behandelt
2. kurze Follow-ups rutschen je nach altem Assistant-Text in falsche Bahnen
3. Complaint, Correction und neue Arbeitsanweisung werden nicht sauber getrennt
4. `meta` entscheidet oft zu frueh in Richtung Tool-/Rezeptpfad

Ein robuster Assistent braucht daher:

- erst Turn-Bedeutung
- dann Routing

Nicht umgekehrt.

## Ist-Zustand im Code

Die heutige Logik sitzt schwerpunktmaessig in:

- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `extract_effective_meta_query(...)`
  - `extract_meta_context_anchor(...)`
  - `extract_meta_dialog_state(...)`
  - `_derive_semantic_review_payload(...)`
  - `_apply_semantic_review_override(...)`
  - `classify_meta_task(...)`

Der Engpass:

- `classify_meta_task(...)` macht heute gleichzeitig
  - Kontextnormalisierung
  - Intent-/Signal-Auswertung
  - Turn-Deutung
  - Routing
  - Rezeptwahl
  - Review-Override

D0.2 soll das entkoppeln.

## Neuer Zielvertrag

### 1. TurnUnderstandingInput

Eingang fuer D0.2:

```json
{
  "raw_query": "# FOLLOW-UP CONTEXT ...",
  "effective_query": "dann mach das in zukunft so ...",
  "session_id": "canvas_...",
  "conversation_state": {
    "active_topic": "aktuelle Weltlage und News-Qualitaet",
    "active_goal": "brauchbare Live-News statt nur Hintergrundquellen",
    "open_loop": "bei News zuerst Agenturquellen nutzen"
  },
  "followup_capsule": {
    "last_user": "...",
    "last_assistant": "...",
    "pending_followup_prompt": "...",
    "semantic_recall": []
  }
}
```

### 2. TurnInterpretation

Ausgang von D0.2:

```json
{
  "dominant_turn_type": "preference_update",
  "turn_signals": [
    "followup",
    "behavior_instruction",
    "preference_update"
  ],
  "response_mode": "acknowledge_and_store",
  "state_effects": {
    "update_preferences": true,
    "close_open_loop": false,
    "set_next_expected_step": true
  },
  "current_intent_summary": "Der Nutzer gibt eine neue Arbeitsanweisung fuer aktuelle News",
  "target_topic": "aktuelle Weltlage und News-Qualitaet",
  "needs_clarification": false,
  "route_bias": "meta_only",
  "confidence": 0.87,
  "evidence": [
    "phrase: in zukunft",
    "directive: mach das so",
    "topic anchor: News-Qualitaet"
  ]
}
```

## Startmenge der Turn-Typen

Erster stabiler Satz fuer Timus:

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

- ein Turn kann mehrere Signale haben
- aber genau **ein dominanter Turn-Typ** steuert die naechste Meta-Entscheidung

## Dominanzreihenfolge

Diese Prioritaet ist fuer Timus sinnvoll:

1. `approval_response`
2. `auth_response`
3. `handover_resume`
4. `correction`
5. `behavior_instruction`
6. `preference_update`
7. `complaint_about_last_answer`
8. `result_extraction`
9. `clarification`
10. `followup`
11. `new_task`

Begruendung:

- Nutzerantworten auf offene Gates muessen zuerst erkannt werden
- Korrekturen und Arbeitsanweisungen duerfen nicht durch generisches Task-Routing ueberschrieben werden
- kurze Follow-ups sollen erst spaet gewinnen, nicht vorschnell

## Response Modes

D0.2 soll nicht nur `turn_type`, sondern auch den Meta-Antwortmodus setzen.

Startmodi:

- `execute`
- `acknowledge_and_store`
- `clarify_before_execute`
- `correct_previous_path`
- `resume_open_loop`
- `summarize_state`

Beispiele:

- `dann mach das in zukunft so ...`
  - `dominant_turn_type = behavior_instruction`
  - `response_mode = acknowledge_and_store`

- `nein, ich meinte aktuelle News, nicht Hintergrundanalyse`
  - `dominant_turn_type = correction`
  - `response_mode = correct_previous_path`

- `hole daraus nur die Preise`
  - `dominant_turn_type = result_extraction`
  - `response_mode = execute`

## Geplante Architekturaufteilung

### Schritt 1. Normalize Input

Neue Funktion:

- `build_turn_understanding_input(...)`

Ziel:

- `effective_query`
- `conversation_state`
- relevante Capsule-Felder
- relevante Recall-Fragmente

in eine kleine, explizite Struktur ziehen

### Schritt 2. Detect Turn Signals

Neue Funktion:

- `detect_turn_signals(...)`

Signalgruppen:

- Kontext-Signale
  - `followup_context_present`
  - `open_loop_present`
  - `active_topic_present`
- Nutzerhandlungs-Signale
  - `directive_language`
  - `correction_language`
  - `complaint_language`
  - `approval_language`
  - `auth_language`
  - `result_extraction_language`
- Aufgaben-Signale
  - `new_work_request`
  - `lookup_request`
  - `document_request`

### Schritt 3. Resolve Dominant Turn Type

Neue Funktion:

- `resolve_dominant_turn_type(signals, state)`

Ziel:

- Dominanzlogik zentralisieren
- nicht mehr implizit verteilt ueber viele `if`-Baeume

### Schritt 4. Determine Response Mode

Neue Funktion:

- `resolve_response_mode(turn_type, signals, state)`

Ziel:

- `meta` entscheidet zuerst:
  - ausfuehren
  - speichern
  - korrigieren
  - klaeren
  - offenen Loop fortsetzen

### Schritt 5. Emit State Effects

Neue Funktion:

- `derive_state_effects(turn_type, signals, state)`

Moegliche Effekte:

- `update_preferences`
- `update_recent_corrections`
- `set_open_loop`
- `clear_open_loop`
- `set_next_expected_step`
- `shift_active_topic`
- `keep_active_topic`

### Schritt 6. Route After Understanding

Erst jetzt:

- `classify_meta_task(...)` nutzt `TurnInterpretation`
- und baut daraus Route/Rezept statt Turn-Typen selbst neu zu erraten

## Geplanter Codezuschnitt

### Neue Schicht

- neues Modul:
  - `orchestration/turn_understanding.py`

### D0.2-Hauptfunktionen

- `build_turn_understanding_input(...)`
- `detect_turn_signals(...)`
- `resolve_dominant_turn_type(...)`
- `resolve_response_mode(...)`
- `derive_state_effects(...)`
- `interpret_turn(...)`

### Bestehende Stellen, die spaeter umgebaut werden

- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `classify_meta_task(...)` soll D0.2 konsumieren statt alles selbst zu mischen
- [agent/agents/meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - Antwortmodus/Handoff soll auf `TurnInterpretation` reagieren
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - `conversation_state` aus D0.1 wird Eingabe fuer D0.2

## Teststrategie

### 1. Reine Contract-Tests

Neue Suite:

- `tests/test_turn_understanding.py`

Startfaelle:

- Verhaltensanweisung
- Praeferenz-Update
- Complaint + neue Arbeitsanweisung
- Correction auf letzte Antwort
- Result-Extraction-Follow-up
- kurze referenzielle Fortsetzung
- Approval-/Auth-Response

### 2. Meta-Integrations-Regressionen

Bestehende Suite erweitern:

- `tests/test_meta_orchestration.py`

Wichtige Live-nahe Faelle:

- `dann mach das in zukunft so ...`
- `so meinte ich das nicht`
- `nein, aktuelle Preise meine ich`
- `ok mach weiter`
- `die erste option`
- `ja, nutze dafuer meinen login`

### 3. Eval-Board

Spaeter:

- kleine feste D0.2-Eval-Cases fuer
  - Turn-Type
  - Response-Mode
  - State-Effects

## Observability

Neue Ziel-Events:

- `meta_turn_type_selected`
- `meta_response_mode_selected`
- `conversation_state_effects_derived`
- `turn_understanding_conflict_detected`

Payload-Beispiele:

- `dominant_turn_type`
- `turn_signals`
- `response_mode`
- `confidence`
- `state_effects`

## Nicht-Ziele fuer D0.2

- noch kein grosses Modell-Upgrade nur fuer Turn-Verstehen
- noch keine neue Langzeitmemory-Logik
- noch keine vollstaendige Preference-Persistenz ueber Themen hinweg
- noch keine Phase-D-Approval-Automation

D0.2 ist:

- die semantische Entscheidungsstufe
- nicht die komplette Memory- oder Workflow-Engine

## Erfolgskriterien

D0.2 ist gut vorbereitet bzw. spaeter gut umgesetzt, wenn:

1. `meta` Korrektur, Beschwerde, Praeferenz und Folgeauftrag sauber trennt
2. ein kurzer Turn nicht mehr vorschnell in Lookup-/Tool-Rezepte kippt
3. `response_mode` vor der Delegation feststeht
4. Session-State-Aenderungen explizit und testbar werden
5. spaetere D1-D5-Workflows dieselbe Turn-Schicht wiederverwenden koennen

## Empfohlene Reihenfolge fuer die spaetere Umsetzung

1. `TurnUnderstandingInput` und `TurnInterpretation` als Dataclass/TypedDict
2. `detect_turn_signals(...)`
3. `resolve_dominant_turn_type(...)`
4. `resolve_response_mode(...)`
5. `derive_state_effects(...)`
6. Integration in `classify_meta_task(...)`
7. Integration in `meta.py`
8. Observability und Eval

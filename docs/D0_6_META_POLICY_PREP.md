# D0.6 Meta-Policy fuer Antwortmodus - Vorbereitung

Stand: 2026-04-07

## Statusupdate - erster Runtime-Slice umgesetzt

Der Vorbereitungsblock ist nicht mehr nur konzeptionell.

Stand jetzt:

- [meta_response_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_response_policy.py) existiert als echte Policy-Schicht
- `classify_meta_task(...)` nutzt die Policy bereits im Runtime-Pfad
- `meta_policy_decision` wird ueber Klassifikation, Handoff und Observability mitgetragen
- umgesetzt sind derzeit insbesondere:
  - `summarize_state` fuer echte Statusfragen wie `wo stehen wir gerade`
  - `clarify_before_execute` bei handlungsorientierten, aber kontextschwachen leichten Follow-up-Turns
  - bewusste Trennung zwischen breiten `action hints` und Task-Tiefe:
    - einfache Suche bleibt `simple_live_lookup`
    - sie wird nicht allein wegen Action-Sprache in Deep Research umgebogen

Noch offen:

- D0.6a Self-Model-Bounds
- weitere Policy-Regeln fuer feinere Antwortformen
- breitere Live-Evals ueber Canvas/Telegram

## Warum D0.6 jetzt der naechste sinnvolle Block ist

Mit D0.1 bis D0.5 hat Timus jetzt:

- einen offiziellen `conversation_state`
- eine explizite Turn-Understanding-Schicht
- eine priorisierte Context-Rehydration
- Topic-State und Open-Loops
- persistentes Preference-/Instruction-Memory

Was noch fehlt, ist eine echte Policy-Schicht fuer den Antwortmodus.

Heute wird `response_mode` noch zu direkt aus `dominant_turn_type` und wenigen Signalen abgeleitet.

Aktueller Stand:

- [turn_understanding.py](/home/fatih-ubuntu/dev/timus/orchestration/turn_understanding.py)
  - `resolve_response_mode(...)` entscheidet derzeit weitgehend nach Turn-Typ
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `_select_open_loop_payload(...)` und der Meta-Kontext reagieren auf `response_mode`
- Beobachtbarkeit ist vorhanden
  - `meta_response_mode_selected`

Das reicht fuer viele Faelle, aber noch nicht fuer eine saubere Meta-Policy.

## Kernproblem

`response_mode` ist noch zu sehr:

- turn-typ-basiert
- heuristisch lokal
- nicht stark genug an
  - Kontextqualitaet
  - Open-Loop-Zustand
  - Preference-/Instruction-Memory
  - Selbstmodell von `meta`
  gekoppelt

Beispiele fuer noch offene Policy-Fragen:

- Wann reicht `execute`, wann braucht es `clarify_before_execute`?
- Wann soll `meta` nur bestaetigen und speichern statt schon auszufuehren?
- Wann ist `resume_open_loop` richtig, und wann haengt Timus an einem alten Faden?
- Wann ist `summarize_state` passender als neue Aktion?
- Wann darf `meta` hart behaupten, etwas zu koennen, und wann muss es Grenzen benennen?

## Zielbild

`meta` trifft den Antwortmodus nicht mehr nur als Ableitung aus Turn-Typen, sondern als kleine Policy-Entscheidung auf Basis von:

- `turn_understanding`
- `conversation_state`
- `meta_context_bundle`
- `preference_memory_selection`
- `topic_state_transition`
- `meta`-Selbstmodell aus D0.6a

## Zielvertrag

Neues Policy-Objekt:

```json
{
  "response_mode": "clarify_before_execute",
  "policy_reason": "context_low_confidence_with_action_request",
  "policy_confidence": 0.79,
  "answer_shape": "question_first",
  "should_delegate": false,
  "should_store_preference": false,
  "should_resume_open_loop": false,
  "should_summarize_state": false,
  "self_model_bound_applied": true,
  "policy_signals": [
    "action_requested",
    "context_uncertain",
    "open_loop_not_reliable"
  ]
}
```

## Geplante Inputs

- `dominant_turn_type`
- `turn_signals`
- `route_bias`
- `conversation_state`
- `meta_context_bundle`
- `preference_memory_selection`
- `topic_shift_detected`
- `context_misread_risk`
- `meta_self_model`

## Geplante Startmodi

- `execute`
- `acknowledge_and_store`
- `clarify_before_execute`
- `correct_previous_path`
- `resume_open_loop`
- `summarize_state`

## Policy-Regeln, die D0.6 abdecken soll

### 1. Execute nur mit ausreichender Klarheit

`execute` ist richtig, wenn:

- der Auftrag hinreichend klar ist
- kein offener Konflikt in Praeferenzen vorliegt
- kein starker Misread-Risk aktiv ist

### 2. Clarify bei unsicherer Handlung, nicht nur bei Fragewoertern

`clarify_before_execute` soll nicht nur bei offensichtlicher Rueckfrage-Sprache greifen, sondern auch wenn:

- die Anfrage handlungsorientiert ist
- aber Scope oder Ziel noch nicht belastbar genug sind

### 3. Resume nur bei wirklich tragfaehigem Open-Loop

`resume_open_loop` soll nur greifen, wenn:

- ein aktueller Open-Loop da ist
- der neue Turn semantisch dazu passt
- der Kontext nicht als driftgefaehrdet markiert ist

### 4. Acknowledge-and-store mit klarer Begrenzung

`acknowledge_and_store` ist richtig fuer:

- Verhaltensanweisungen
- Praeferenzupdates
- Korrekturen der Arbeitsweise

Aber nur dann, wenn nicht gleichzeitig schon eine konkrete Ausfuehrung erwartet wird.

### 5. Summarize-state als eigener Modus

`summarize_state` soll fuer Meta-Saetze verfuegbar sein wie:

- `wo stehen wir gerade`
- `was war dein plan`
- `fass den aktuellen stand zusammen`

### 6. Self-model-Grenzen

Wenn `meta` ueber eigene Faehigkeiten spricht, muss D0.6a eingreifen:

- `kann ich jetzt`
- `kann ich teilweise`
- `ist vorbereitet`
- `ist geplant`

## Geplante Artefakte

### D0.6.1 Policy-Contract

Neues Modul:

- `orchestration/meta_response_policy.py`

Inhalt:

- `MetaPolicyInput`
- `MetaPolicyDecision`
- `resolve_meta_response_policy(...)`

### D0.6.2 Integration

- `turn_understanding.py`
  - bleibt fuer Turn-Typ und Basissignale zustaendig
- `meta_orchestration.py`
  - nutzt danach die neue Policy-Entscheidung
- `mcp_server.py`
  - schreibt neue Policy-Felder in Observations

### D0.6.3 Observability

Neue Events:

- `meta_policy_mode_selected`
- `meta_policy_override_applied`

Noch offen fuer spaetere Slices:

- `meta_policy_signal_applied`
- `meta_policy_self_model_bound_applied`

### D0.6.4 Eval

Startfaelle:

- klare Task-Anfrage -> `execute`
- Verhaltensanweisung -> `acknowledge_and_store`
- unklarer Action-Turn -> `clarify_before_execute`
- echter Open-Loop-Follow-up -> `resume_open_loop`
- Status-/Zusammenfassungsfrage -> `summarize_state`
- Selbstbild-Frage -> D0.6a-bound Antwort

## Abgrenzung

D0.6 veraendert noch nicht:

- Approval-/Auth-Gates aus spaeterem Phase-D-Block
- Specialist Context Propagation
- State-Decay/Cleanup

## Definition von "bereit zum Start"

D0.6 ist vorbereitet, wenn:

- der Policy-Vertrag steht
- die Integrationspunkte klar benannt sind
- Eval-Faelle fuer alle Startmodi definiert sind
- die Grenze zu D0.6a sauber beschrieben ist

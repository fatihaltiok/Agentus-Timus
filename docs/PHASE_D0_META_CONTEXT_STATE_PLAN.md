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

Vorbereitung dokumentiert in:

- [D0_3_CONTEXT_REHYDRATION_PREP.md](/home/fatih-ubuntu/dev/timus/docs/D0_3_CONTEXT_REHYDRATION_PREP.md)

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

Stand 2026-04-07:

- erster Runtime-Slice umgesetzt
- persistierte `preference_memory`-Eintraege mit Scopes:
  - `global`
  - `topic`
  - `session`
- Capture erfolgt nur fuer echte Verhaltens-/Praeferenzturns mit `acknowledge_and_store`
- Rehydration bevorzugt gespeicherte `stored_preference`-Eintraege vor heuristischen Hooks
- Beobachtbarkeit:
  - `preference_captured`
  - `preference_applied`
- Abschluss-Haertung:
  - globale Praeferenzen werden konservativer wiederverwendet
  - Konflikte zwischen `session` / `topic` / `global` werden aufgeloest
  - neue Beobachtbarkeit fuer:
    - `preference_scope_selected`
    - `preference_ignored_low_stability`
    - `preference_conflict_resolved`

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

Stand 2026-04-07:

- gestartet, erster Runtime-Slice umgesetzt
- eigener Vorbereitungsblock liegt in:
  - [D0_6_META_POLICY_PREP.md](/home/fatih-ubuntu/dev/timus/docs/D0_6_META_POLICY_PREP.md)
- aktueller Ist-Stand:
  - `response_mode` startet weiter in `turn_understanding.py`
  - D0.6 zieht darueber jetzt bereits eine eigenstaendige Policy-Schicht fuer erste Override-Faelle
  - umgesetzt:
    - Statusfragen -> `summarize_state`
    - kontextschwache handlungsorientierte leichte Follow-ups -> `clarify_before_execute`
    - `meta_policy_decision` in Klassifikation, Handoff und Observability
  - bewusst noch offen:
    - Self-Model-Bounds aus D0.6a
    - weitere Antwortform-Policies
    - groessere Live-Eval-Schicht

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

#### D0.6a Meta Self-Model Calibration

Ziel:

- `meta` soll seine aktuelle Faehigkeit, seine Grenzen und den Unterschied zwischen Zielbild und Ist-Zustand sauber benennen koennen

Stand 2026-04-07:

- abgeschlossen im eigenen Scope
- Details in:
  - [D0_6A_META_SELF_MODEL_PREP.md](/home/fatih-ubuntu/dev/timus/docs/D0_6A_META_SELF_MODEL_PREP.md)
- bereits umgesetzt:
  - `meta_self_state` traegt jetzt getrennt:
    - `current_capabilities`
    - `partial_capabilities`
    - `planned_capabilities`
    - `blocked_capabilities`
    - `confidence_bounds`
    - `autonomy_limits`
  - der strukturierte Handoff zu `meta` enthaelt dieses erweiterte Selbstmodell bereits
  - Dispatcher routet Selbstbildfragen jetzt an `meta`
  - D0.6-Policy behandelt sie als `self_model_status_request`
  - `meta_policy_self_model_bound_applied` macht den Bound sichtbar
- spaeter moegliche Nacharbeiten:
  - weitere Live-Evals
  - Stil-Feinschliff bei Selbstbeschreibungen

Warum das gebraucht wird:

- sonst antwortet `meta` zu selbstsicher
- Zielarchitektur und aktueller Reifegrad werden vermischt
- Faehigkeiten werden behauptet, obwohl sie erst vorbereitet oder nur teilweise umgesetzt sind

Lieferobjekte:

- explizites operatives Selbstmodell fuer `meta`, z. B.:
  - `current_capabilities`
  - `partial_capabilities`
  - `planned_capabilities`
  - `blocked_capabilities`
  - `confidence_bounds`
  - `autonomy_limits`
- Antwortregeln, die unterscheiden zwischen:
  - `kann ich jetzt`
  - `kann ich teilweise`
  - `ist vorbereitet`
  - `ist geplant`
- Meta darf Zielbilder nicht als aktuelle Realitaet darstellen

Beispiel:

- auf Fragen wie:
  - `ist das schon deine philosophie`
  - `kannst du das schon`
  - `bist du schon so weit`
- soll `meta` nicht pauschal sagen:
  - `das bin ich schon`
- sondern den aktuellen Stand kalibriert einordnen

### D0.7 Observability und Evaluation

Ziel:

- diese Schicht muss messbar werden, sonst endet sie wieder in unsichtbaren Prompt-Aenderungen

Stand 2026-04-08:

- im eigenen Scope abgeschlossen
- zwei Runtime-Slices fuer Eval und Beobachtbarkeit umgesetzt
- nach Reload live ueber `/chat` und `/autonomy/observation` bestaetigt
- D0.7 macht die Meta-Kontextschicht jetzt nicht nur sichtbar, sondern auch qualitativ auswertbar

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

Erster Runtime-Slice:

- [meta_context_state_eval.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_context_state_eval.py)
  - kanonische D0-Eval-Faelle direkt ueber `classify_meta_task(...)`
  - Benchmark fuer:
    - `task_type`
    - Agentenkette
    - `dominant_turn_type`
    - `response_mode`
    - Context-Slot-Abdeckung
    - Signal-Mix
    - `context_misread`-Risiko
- [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neuer Summary-Block `meta_context_state`
  - zaehlt jetzt die zentralen D0-Signale als zusammenhaengende Metrik statt nur als Roh-Events

Zweiter Runtime-Slice:

- [meta_context_state_eval.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_context_state_eval.py)
  - jetzt mit Eval-Familien fuer:
    - `approval_resume`
    - `auth_resume`
    - `topic_resumption`
    - `complaint_plus_instruction`
  - Summary liefert jetzt:
    - `by_family`
    - `quality_score`
    - `gate_passed`
- [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - `meta_context_state` enthaelt jetzt zusaetzlich:
    - `misread_rate`
    - `state_update_coverage`
    - `preference_roundtrip_rate`
    - `policy_override_rate`

Live-Abschlussnachweis:

- Session `d07_live_verify_20260408`
- Request `req_1b886852f468`
  - Verhaltensanweisung wurde live als `behavior_instruction` erkannt
  - `preference_captured`, `preference_scope_selected`, `preference_applied` und `conversation_state_updated` wurden beobachtet
- Request `req_2b4e58e8763e`
  - Follow-up wurde live als `followup` mit `resume_open_loop` erkannt
  - `context_rehydration_bundle_built`, `open_loop_attached`, `topic_memory_attached`, `preference_memory_attached`, `preference_conflict_resolved` und `chat_request_completed` wurden beobachtet
- Live-Summary in `/autonomy/observation` zeigte danach u. a.:
  - `healthy_bundle_rate = 1.0`
  - `misread_rate = 0.0`
  - `preference_roundtrip_rate = 1.0`
  - `preference_conflict_resolved_total = 1`

Rest fuer spaeter, aber nicht blockierend fuer D0.7:

- Einbindung der D0-Metriken in spaetere UI-/Statusflaechen
- weitere Langzeit-Eval-Faelle koennen spaeter D0.8/D0.9 begleiten

### D0.8 Sicheres Vergessen und State-Decay

Ziel:

- nicht alles fuer immer festhalten

Stand 2026-04-08:

- gestartet, erster Runtime-Slice umgesetzt
- Session-State bekommt jetzt kontrolliertes Decay statt blindem Dauerfesthalten
- Topic-History wird als eigener Verlaufspfad gefuehrt
- historische Themen koennen jetzt zeitbezogen fuer `eben`, `gestern`, `letzte Woche`, `vor 3/6/12 Monaten` und `vor einem Jahr` rehydriert werden

Regeln:

- session-lokale Hinweise verfallen zuerst
- thematische Preferences bleiben laenger
- globale Preferences nur bei wiederholter Evidenz
- veraltete offene Schleifen muessen sauber geschlossen werden

Erster Runtime-Slice:

- [topic_state_history.py](/home/fatih-ubuntu/dev/timus/orchestration/topic_state_history.py)
  - neue `topic_history`-Eintraege pro Session
  - Statusmodell:
    - `active`
    - `historical`
    - `stale`
    - `closed`
  - Historienabruf ueber relative Zeitanker:
    - `eben`
    - `gestern`
    - `letzte Woche`
    - `vor 3 Monaten`
    - `vor 6 Monaten`
    - `vor 12 Monaten`
    - `vor einem Jahr`
- [conversation_state.py](/home/fatih-ubuntu/dev/timus/orchestration/conversation_state.py)
  - `decay_conversation_state(...)`
  - stale `open_loop` und `open_questions` werden nach laengerer Inaktivitaet entwertet
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `historical_topic_memory` als eigener Context-Slot im `meta_context_bundle`
- [meta_response_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_response_policy.py)
  - zeitbezogene Erinnerungsfragen laufen jetzt als `historical_topic_recall` auf `meta` mit `summarize_state`
- [mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - Session-Kapseln tragen jetzt `topic_history`
  - Follow-up-Capsules laden decay-bereinigten State plus `topic_history`

Nachhaertung 2026-04-08 - Resume/Anchor-Robustheit:

- [turn_understanding.py](/home/fatih-ubuntu/dev/timus/orchestration/turn_understanding.py)
  - zeitverankerte Rueckfragen mit frischem Session-Kontext laufen jetzt nicht mehr stumpf als `new_task`
  - `historical_recall_requested` + frische User-/Assistant-Turns -> `followup`
  - Basismodus fuer solche Faelle wird auf `resume_open_loop` gezogen; die D0.6-Policy setzt danach sauber `summarize_state`
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - wenn `topic_history` fuer `von eben` noch leer ist, baut Timus jetzt einen historischen Themenanker aus frischen Session-Turns:
    - `recent_user_turn`
    - bei `was hast du eben gesagt` auch `recent_assistant_turn`
  - dadurch entsteht jetzt `historical_topic_memory`, auch wenn der vorige freie Turn noch nicht in `topic_history` materialisiert wurde
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - `historical_topic_attached` traegt jetzt auch `fallback_source`

Verifikation:

- `pytest -q tests/test_turn_understanding.py tests/test_meta_orchestration.py tests/test_topic_state_history.py tests/test_topic_state_history_hypothesis.py tests/test_topic_state_history_contracts.py tests/test_conversation_state.py tests/test_autonomy_observation_d0.py tests/test_android_chat_language.py` -> `118 passed`
- direkter Runtime-Smoke:
  - Query: `weisst du noch was wir eben ueber archivregeln besprochen hatten`
  - frischer Session-Turn: `Lass uns ueber Langzeitgedaechtnis und Archivregeln bei Timus sprechen.`
  - Ergebnis:
    - `dominant_turn_type = followup`
    - `response_mode = summarize_state`
    - `historical_topic_selection.fallback_source = recent_user_turn`
    - `historical_topic_memory` im Bundle vorhanden

Status:

- D0.8 ist damit im eigenen Scope abgeschlossen
- weitergehende Retrieval-Qualitaet ueber viele Monate/Jahre bleibt spaeter ein Eval-/Qualitaetsthema, aber nicht mehr der offene Kernrest von D0.8

Vorheriger Nachhaertungsblock 2026-04-08:

- [topic_state_history.py](/home/fatih-ubuntu/dev/timus/orchestration/topic_state_history.py)
  - allgemeine relative Monats-/Jahresfenster statt nur harter Einzelwerte:
    - `vor 18 Monaten`
    - `vor 3 Jahren`
    - weitere numerische Monats-/Jahresangaben werden jetzt generisch abgeleitet
  - sehr alte `historical`/`stale`/`closed` History-Eintraege werden ab >10 Jahren aus dem aktiven History-Satz entfernt
- [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - D0.8-Metriken werden jetzt auch sichtbar im Markdown-Output gerendert:
    - `Conversation-State-Decay`
    - `Historical-Topic-Attachments`
    - `by_decay_reason`
    - `by_historical_time_label`

Verifikation:

- `pytest -q tests/test_topic_state_history.py tests/test_topic_state_history_hypothesis.py tests/test_topic_state_history_contracts.py tests/test_conversation_state.py tests/test_meta_orchestration.py tests/test_autonomy_observation_d0.py tests/test_android_chat_language.py` -> `108 passed`
- `python -m crosshair check tests/test_topic_state_history_contracts.py` -> gruen

Live-Reload:

- `timus-mcp.service` und `timus-dispatcher.service` wurden am **8. April 2026 um 13:24:57 CEST** neu geladen
- `GET /health` war danach wieder `healthy`
- der neue `historical_topic_recall`-Policy-Pfad lief live fuer die Session `d08_live_verify_20260408`

Wichtiger Restpunkt:

- der spontane Live-Test mit `von eben` zeigte die neue Policy live, aber der vorangehende Turn setzte noch keinen starken genugen Themenanker fuer `historical_topic_attached`
- das ist kein Parser-/Zeitankerfehler mehr, sondern ein verbleibender Qualitaetsrest bei der Themenverankerung ueber freie neue Tasks

### D0.9 Specialist Context Propagation

Ziel:

- die neue Meta-Kontextbasis kontrolliert in die Spezialistenpfade ausrollen

Lieferobjekte:

- Handoff-Erweiterung fuer:
  - `executor`
  - `research`
  - `visual`
  - `system`
- minimaler Spezialistenkontext:
  - `current_topic`
  - `active_goal`
  - `open_loop`
  - `turn_type`
  - `response_mode`
  - `user_preferences`
  - `recent_corrections`
- Ruecksignale aus Spezialisten:
  - `partial_result`
  - `blocker`
  - `context_mismatch`
  - `needs_meta_reframe`

Wichtig:

- dieser Block kommt bewusst erst nach D0.8
- erst dann ist die Meta-Seite stabil genug, um ihren Kontext sauber in andere Agenten zu propagieren
- Ziel ist nicht, jeden Spezialisten wie `meta` zu machen, sondern den laufenden Arbeitskontext mitzutragen

Aktueller Runtime-Stand:

- erster Runtime-Slice ist umgesetzt
- `meta` erzeugt jetzt einen normalisierten `specialist_context_seed`
- der Seed wird im Meta-Handoff und in strukturierten Specialist-Handoffs mitgetragen
- `executor`, `research`, `visual` und `system` rendern diesen Kontext jetzt sichtbar im Specialist-Handoff-Kontext
- zweiter Runtime-Slice ist umgesetzt:
  - gemeinsame Alignment-Heuristik fuer propagierten Spezialistenkontext
  - sichtbare Kontextwarnung im Specialist-Handoff bei schwacher Verankerung
  - erste strukturierte Ruecksignale im Delegations-Rueckweg:
    - `context_mismatch`
    - `needs_meta_reframe`
- dritter Runtime-Slice ist umgesetzt:
  - erstes agentenseitiges Signal-Protokoll `Specialist Signal: ...`
  - Registry erkennt diese Signale jetzt explizit statt nur heuristisch
  - `needs_meta_reframe` fuehrt im Delegationspfad jetzt zu `partial` statt stiller Erfolgsmeldung
  - `executor` blockt Aktions-Handoffs jetzt aktiv, wenn propagierter `response_mode=summarize_state` dazu im Widerspruch steht
- vierter Runtime-Slice ist umgesetzt:
  - `research` blockt jetzt leichte Lookup-/Live-Such-Handoffs aktiv, wenn sie faelschlich in den Deep-Research-Pfad geraten
  - `research` bekommt fuer uebergebene Quellen, erfassten Kontext und knappe/quellengetriebene Nutzerpraeferenzen jetzt explizite Strategiehinweise
  - `visual` blockt echte UI-/Browser-Aktions-Handoffs jetzt aktiv, wenn propagierter `response_mode=summarize_state` dazu im Widerspruch steht
  - `system` hat jetzt einen direkten Status-Zusammenfassungspfad ohne LLM, wenn Meta explizit im `summarize_state`-Modus einen Service-/Status-Handoff schickt
- fuenfter Runtime-Slice ist umgesetzt:
  - `research` leitet jetzt aus Handoff und Nutzerpraeferenzen eine echte Kontext-Policy ab (`source_first`, `compact_mode`)
  - `research` unterdrueckt in source-first/kompakten Faellen jetzt Blackboard-/Curiosity-Kontext statt ihn nur weicher zu formulieren
  - `visual` waehlt jetzt explizit zwischen `structured_navigation` und `vision_first`
  - `system` waehlt jetzt gezielte Snapshot-Plaene (`preferred_service`, `compact`) statt immer denselben Voll-Snapshot
- sechster Abschluss-Slice ist umgesetzt:
  - D0.9 hat jetzt ein eigenes ausfuehrbares Eval-Set fuer `research`, `visual`, `system` und den Specialist-Signalvertrag
  - D0.9 hat jetzt einen eigenen Observability-Block `specialist_context` mit Strategie- und Signalmetriken
  - die Kernkette ist jetzt abgeschlossen:
    - Kontext-Propagation
    - Alignment
    - Ruecksignale
    - agentenseitige Signale
    - erste echte Guards
    - erste echte Priorisierung
    - Eval + Observability
- aktuell propagierte Felder:
  - `current_topic`
  - `active_goal`
  - `open_loop`
  - `next_expected_step`
  - `turn_type`
  - `response_mode`
  - `user_preferences`
  - `recent_corrections`
  - `signal_contract`

Status:

- D0.9 ist im Repo-/Test-Scope abgeschlossen
- der erste Kernring `executor`, `research`, `visual`, `system` traegt jetzt propagierten Kontext nicht mehr nur passiv, sondern nutzt ihn in ersten echten Entscheidungen
- weitere Spezialisten ausserhalb des Kernrings sind kein D0-Pflichtrest mehr, sondern koennen spaeter gezielt nachgezogen werden
- ein Live-Reload ist fuer den produktiven Lauf noch separat noetig; der Abschluss hier bezieht sich auf Implementierung, Tests und Doku

## Empfohlene Reihenfolge

1. D0.1 Conversation-State-Schema
2. D0.2 Turn-Understanding-Layer
3. D0.3 Context-Rehydration-Pipeline
4. D0.4 Topic-State und Open-Loops
5. D0.5 Preference-/Instruction-Memory
6. D0.6 Meta-Policy fuer Antwortmodus
   D0.6a Meta Self-Model Calibration
7. D0.7 Observability und Eval
8. D0.8 State-Decay und Cleanup
9. D0.9 Specialist Context Propagation

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
- eine spaetere autonome Gedaechtnispflege (`Memory Curation Autonomy`) gehoert ebenfalls nach D0 und nach Phase D, weil sie auf sauberem Topic-State, Preference-Memory und sicheren Autonomiegrenzen aufsetzen muss

Kurz:

- **Phase C**: Runtime-Haertung
- **Phase D0**: Meta Context State
- **Phase D1-D5**: Approval, Auth, Handover, assistive Workflows
- **Phase E**: Self-Improvement auf belastbarer Gespraechsbasis
  - spaeter darin: `Memory Curation Autonomy` fuer policy-gesteuerte, beobachtbare und reversible Gedaechtnispflege

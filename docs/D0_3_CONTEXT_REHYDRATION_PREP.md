# D0.3 Vorbereitung - Context-Rehydration-Pipeline fuer Meta

Stand: 2026-04-06

## Warum D0.3 jetzt der naechste Schritt ist

Nach D0.1 und D0.2 hat Timus jetzt:

- ein offizielles `conversation_state`
- eine explizite `TurnInterpretation`
- erste State-Writebacks und D0-Observability

Was noch fehlt, ist die eigentliche Kontextzufuhr vor der Meta-Entscheidung.

Aktuell gilt noch zu oft:

- `meta` sieht zwar Query + Follow-up-Capsule + Recall
- aber die Priorisierung ist noch nicht als eigener, kleiner Kontextvertrag gebaut
- dadurch kann alter Kontext zu stark, zu schwach oder in der falschen Reihenfolge wirken

D0.3 soll genau das entkoppeln:

- nicht mehr `alles irgendwie in die Klassifikation mischen`
- sondern zuerst:
  - relevanten Kontext sammeln
  - priorisieren
  - komprimieren
  - als explizites Bundle an `meta` uebergeben

## Zielbild

Vor jeder Meta-Klassifikation entsteht ein kleiner, stabiler `MetaContextBundle`.

Dieser Bundle beantwortet:

- Was ist die aktuelle Nutzerfrage
- Welcher Session-Zustand ist gerade relevant
- Welche offene Schleife ist noch aktiv
- Welche frischen User-Turns sind wichtig
- Welche thematischen Erinnerungen helfen wirklich
- Welche Praeferenzen gelten hier
- Welche Teile des alten Kontexts duerfen gerade **nicht** uebersteuern

Wichtig:

- D0.3 ist kein grosser Prompt-Dump
- D0.3 ist ein Priorisierungs- und Auswahlmechanismus

## Kernprinzipien

1. Die aktuelle Nutzerfrage bleibt immer Slot 1.

- alter Kontext erklaert
- er ersetzt nicht die neue Frage

2. State vor Recall.

- `conversation_state` und offene Schleifen sind staerker als lose Recall-Fragmente

3. User-Turns vor Assistant-Nachhall.

- letzte relevante Nutzerturns haben hoehere Prioritaet als alte Assistant-Texte

4. Wenige Slots, hohe Aussagekraft.

- Ziel ist ein kompakter Bundle, kein grosser History-Block

5. Jede Slot-Art bekommt einen klaren Scope.

- Topic Memory
- Preference Memory
- offene Schleife
- frische User-Kontexte

Diese Typen duerfen spaeter nicht wieder unsauber vermischt werden.

## Geplanter Vertrag

### Eingabe fuer D0.3

```json
{
  "raw_query": "...",
  "effective_query": "...",
  "conversation_state": {},
  "turn_understanding": {},
  "followup_capsule": {},
  "session_summary": "...",
  "recent_user_turns": [],
  "recent_assistant_turns": [],
  "topic_memory_hits": [],
  "preference_memory_hits": [],
  "semantic_recall_hits": []
}
```

### Ausgabe von D0.3

```json
{
  "schema_version": 1,
  "current_query": "...",
  "bundle_reason": "meta_context_rehydration",
  "active_topic": "...",
  "active_goal": "...",
  "open_loop": "...",
  "next_expected_step": "...",
  "turn_type": "followup",
  "response_mode": "resume_open_loop",
  "context_slots": [
    {"slot": "conversation_state", "priority": 1, "content": "..."},
    {"slot": "open_loop", "priority": 2, "content": "..."},
    {"slot": "recent_user_turn", "priority": 3, "content": "..."},
    {"slot": "topic_memory", "priority": 4, "content": "..."},
    {"slot": "preference_memory", "priority": 5, "content": "..."}
  ],
  "suppressed_context": [
    {"source": "assistant_reply", "reason": "lower_priority_than_recent_user_turn"}
  ],
  "confidence": 0.84
}
```

## Slot-Reihenfolge fuer die erste Version

1. `current_query`
- immer Pflicht

2. `conversation_state`
- `active_topic`
- `active_goal`
- `open_loop`
- `next_expected_step`
- `turn_type_hint`

3. `open_loop`
- nur wenn wirklich aktiv und zum Turn passend

4. `recent_user_turns`
- die letzten 1-3 wirklich relevanten User-Turns
- nicht stumpf die letzten 3 Chatzeilen

5. `topic_memory`
- nur thematisch passende Treffer
- kein allgemeiner Recall-Muell

6. `preference_memory`
- nur Preferences, die fuer genau diesen Turn gelten

7. `assistant_fallback_context`
- nur wenn die obigen Quellen nicht reichen

## Unterdrueckungsregeln

D0.3 braucht explizit auch Negativlogik.

Kontext soll unterdrueckt werden, wenn:

- ein alter Assistant-Text den aktuellen User-Turn ueberschreiben wuerde
- ein Location-/Maps-Kontext ohne aktuelle Ortsrelevanz reinrauscht
- ein altes Tool-Ergebnis mit hoher Autoritaet, aber falschem Thema drueckt
- eine alte Preference nicht mehr zum aktuellen Topic passt
- eine bereits geschlossene offene Schleife wieder hochkommt

## Geplanter Builder

Zielobjekt:

- `build_meta_context_bundle(...)`

Hilfsfunktionen:

- `select_relevant_recent_user_turns(...)`
- `select_relevant_topic_memory(...)`
- `select_relevant_preference_memory(...)`
- `select_open_loop_payload(...)`
- `suppress_low_priority_context(...)`
- `render_meta_context_bundle(...)`

## Erste Integrationspunkte

Dateien mit hoher Wahrscheinlichkeit:

- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - baut D0.3 vor `classify_meta_task(...)` ein
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - liefert Session-Capsule und Follow-up-Kontext
- [orchestration/conversation_state.py](/home/fatih-ubuntu/dev/timus/orchestration/conversation_state.py)
  - liefert offiziellen Session-State
- [orchestration/turn_understanding.py](/home/fatih-ubuntu/dev/timus/orchestration/turn_understanding.py)
  - liefert `turn_type` und `response_mode`
- [server/conversation_qdrant.py](/home/fatih-ubuntu/dev/timus/server/conversation_qdrant.py)
  - spaeter fuer Topic-/Semantic-Recall
- [memory/memory_system.py](/home/fatih-ubuntu/dev/timus/memory/memory_system.py)
  - spaeter fuer Preference- und Topic-Memory-Anbindung

## Nicht-Ziele fuer D0.3

- noch kein roll-out in `executor`, `research`, `visual`, `system`
- noch keine globale Preference-Persistenzlogik
- noch kein endgueltiger Topic-State-Resolver
- noch kein State-Decay
- noch keine neue Spezialisten-Policy

D0.3 ist also:

- Rehydration vor Meta
- nicht schon der Spezialisten-Rollout

## Observability

Neue Zielsignale fuer die spaetere Umsetzung:

- `context_rehydration_bundle_built`
- `context_slot_selected`
- `context_slot_suppressed`
- `open_loop_attached`
- `topic_memory_attached`
- `preference_memory_attached`
- `context_misread_suspected`

## Eval-Faelle fuer D0.3

1. Verhaltensanweisung nach fehlgeschlagener News-Recherche

- Query:
  - `dann mach das in zukunft so dass du auf agenturmeldungen gehst`
- Erwartung:
  - `conversation_state` und letzter User-Turn dominieren
  - alte Research-Antwort wird nicht als primaerer Kontextanker benutzt

2. Knappes Follow-up mit offenem Loop

- Query:
  - `ok fang an`
- Erwartung:
  - `pending_followup_prompt` / `open_loop` wird attachiert
  - keine neue Aufgabe erfunden

3. Korrektur mit altem Assistant-Drift

- Query:
  - `nein ich meinte aktuelle news`
- Erwartung:
  - letzter Nutzerkontext und `recent_corrections` dominieren
  - alter Nearby-/Location-Kontext wird unterdrueckt

4. Themenwiederaufnahme nach Zeitabstand

- Query:
  - `wie war da nochmal unser plan`
- Erwartung:
  - Topic Memory / offene Schleife wird attachiert
  - irrelevante Assistant-Saetze bleiben draussen

## Erfolgskriterium fuer D0.3

D0.3 ist gut vorbereitet bzw. spaeter gut umgesetzt, wenn:

- `meta` vor der Entscheidung einen expliziten Kontextbundle statt eines Mischzustands bekommt
- Follow-up-, Korrektur- und Preference-Turns weniger von altem Assistant-Nachhall zerstoert werden
- offene Schleifen klarer und kompakter am Turn haengen
- Topic Memory und Preference Memory bewusst getrennt in den Bundle eingehen

## Empfohlener Implementierungsstart

1. `MetaContextBundle`-Dataclass / TypedDict
2. `build_meta_context_bundle(...)`
3. Slot-Selektion nur aus:
- `effective_query`
- `conversation_state`
- `pending_followup_prompt`
- letzten relevanten User-Turns
4. danach Topic-/Preference-Memory andocken
5. erst dann Rendering / Observability

## Roadmap-Hinweis

D0.3 ist der naechste Umsetzungsblock nach D0.2.

Danach folgen:

- D0.4 Topic-State und Open-Loops
- D0.5 Preference-/Instruction-Memory
- D0.6 Meta-Policy fuer Antwortmodus
- D0.7 Observability und Eval
- D0.8 State-Decay und Cleanup
- D0.9 Specialist Context Propagation

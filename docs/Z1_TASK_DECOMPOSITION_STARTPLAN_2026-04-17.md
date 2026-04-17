# Z1 Startplan - Task Decomposition Contract

Stand: 2026-04-17

## Status 2026-04-17 - erster Runtime-Slice umgesetzt

Z1 ist nicht mehr nur geplant. Der erste echte Implementierungsslice steht jetzt im Code.

Erreicht:

- neues kanonisches Objekt `task_decomposition_v1` in [task_decomposition_contract.py](/home/fatih-ubuntu/dev/timus/orchestration/task_decomposition_contract.py)
- fruehes Frontdoor-Signal `planning_needed`
- Routing-Schaerfung fuer `build_setup` gegenueber reinem `research`
- Typed-Meta-Handoff mit:
  - `intent_family`
  - `planning_needed`
  - `task_decomposition_json`
- Meta-Parser liest das Decomposition-Objekt jetzt explizit ein
- Pytest-, Hypothesis- und CrossHair-Abdeckung fuer den neuen Vertrag

Wichtig:

- das ist bewusst erst `Z1`
- noch **nicht** drin sind:
  - Meta Plan Compiler
  - turnuebergreifender Plan-State
  - Replanning
  - Specialist-Step-Packaging

## Rolle im Gesamtprojekt

Dieses Dokument ist der konkrete Startplan fuer:

- [ZWISCHENPROJEKT_ALLGEMEINE_MEHRSCHRITT_PLANUNG_2026-04-12.md](/home/fatih-ubuntu/dev/timus/docs/ZWISCHENPROJEKT_ALLGEMEINE_MEHRSCHRITT_PLANUNG_2026-04-12.md)

Z1 ist der erste echte Umsetzungsblock des Zwischenprojekts. Ohne Z1 bleibt die spaetere Mehrschritt-Planung zu implizit, weil:

- Frontdoor-Entscheidungen weiter nur lose Intent-Texte liefern
- Meta keine kanonische Planstruktur bekommt
- Follow-ups und Replanning kein gemeinsames Arbeitsobjekt haben

## Warum Z1 zuerst kommt

Der groesste verbleibende Produktfehler liegt aktuell bei:

- Frontdoor-Fehlklassifikation
- Build-/Setup-/Plan-/Research-Verwechslung
- fehlender expliziter Zerlegung eines Nutzerziels in ein maschinenlesbares Arbeitsobjekt

Z1 ist deshalb nicht nur ein Schema-Slice. Es ist der Vertrag, auf dem spaeter aufbauen:

- Z2 Meta Plan Compiler
- Z3 Plan State in Conversation State
- Z4 Specialist Step Packaging
- Z5 Dynamic Replanning and Goal Satisfaction

## Ziel von Z1

Timus soll aus einer mehrschrittigen Nutzeranfrage ein stabiles, kanonisches Decomposition-Objekt erzeugen koennen.

Dieses Objekt muss mindestens ausdruecken:

- was das eigentliche Ziel ist
- welche Constraints gelten
- welche Teilziele sichtbar sind
- welche Schritte optional oder bedingt sind
- woran Zielerfuellung erkannt wird
- ob starrer Rezeptpfad oder zielzustandsorientierte Erfuellung gilt

## Konkreter Umfang von Z1

Z1 wird als ein groesserer Block umgesetzt, nicht als Mikroserie.

### Z1.1 Contract und Normalisierung

Liefern:

- neues kanonisches Objekt `task_decomposition_v1`
- eindeutige Pflichtfelder
- Default-Normalisierung fuer fehlende oder schwache Felder
- kompakte Serialisierung fuer Handoffs

Pflichtfelder:

- `request_id`
- `source_query`
- `intent_family`
- `goal`
- `constraints`
- `subtasks`
- `completion_signals`
- `goal_satisfaction_mode`
- `planning_needed`

Wichtige Unterfelder:

- `constraints.hard`
- `constraints.soft`
- `constraints.forbidden_actions`
- `subtasks[].id`
- `subtasks[].title`
- `subtasks[].kind`
- `subtasks[].status`
- `subtasks[].depends_on`
- `subtasks[].optional`
- `subtasks[].completion_signals`

### Z1.2 Frontdoor-Einstieg fuer Planungsbedarf

Liefern:

- fruehe Frontdoor-Erkennung fuer:
  - `build_setup`
  - `research`
  - `plan_only`
  - `execute_multistep`
- neues Signal:
  - `planning_needed = true|false`
- neue Regel:
  - bei mehrschrittigem `build/setup` oder zusammengesetzten Aktionswuenschen nicht direkt in `research` fallen

### Z1.3 Typed Handoff an Meta

Liefern:

- Integration des Decomposition-Objekts in den bestehenden F2-Handoff-Pfad
- Meta bekommt nicht nur Query plus Packet, sondern auch:
  - `task_decomposition_json`
- klare Trennung zwischen:
  - blosem Intent
  - Decomposition-Objekt
  - spaeterem Plan-State

### Z1.4 Verifikation

Liefern:

- Pytests fuer:
  - Normalisierung
  - Pflichtfelder
  - zusammengesetzte Build-/Setup-Requests
  - Abgrenzung gegen reine Research-Requests
- Hypothesis fuer:
  - Stabilitaet der Summary-/Count-Felder
  - robuste Normalisierung bei duennen Inputs
- CrossHair fuer:
  - Contract-Invarianten
  - Pflichtfeld-/Defaultlogik

## Was Z1 bewusst noch nicht tut

Z1 tut noch nicht:

- vollstaendige Planableitung durch Meta
- turnuebergreifenden Plan-State
- echte Replanung
- Specialist-Step-Handoffs
- User-Facing-Progress-Kompression

Das ist Absicht. Z1 soll die gemeinsame Struktur liefern, nicht schon das ganze Planungssystem.

## Voraussichtlich betroffene Dateien

Kern:

- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [agent/agents/meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- [orchestration/typed_task_packet.py](/home/fatih-ubuntu/dev/timus/orchestration/typed_task_packet.py)

Neu wahrscheinlich:

- [orchestration/task_decomposition_contract.py](/home/fatih-ubuntu/dev/timus/orchestration/task_decomposition_contract.py)
- [tests/test_task_decomposition_contract.py](/home/fatih-ubuntu/dev/timus/tests/test_task_decomposition_contract.py)
- [tests/test_task_decomposition_contract_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_task_decomposition_contract_hypothesis.py)
- [tests/test_task_decomposition_contract_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_task_decomposition_contract_crosshair.py)

## Akzeptanzkriterien

Z1 gilt als erfolgreich, wenn:

- ein `task_decomposition_v1`-Objekt maschinenlesbar gebaut werden kann
- Build-/Setup-Mehrschrittanfragen nicht mehr als simpler Research-Intent kollabieren
- Meta das Decomposition-Objekt im Handoff sichtbar bekommt
- die Contract-Tests reproduzierbar gruen sind

## Produktbeispiele, die Z1 verbessern muss

Beispiele:

- `kannst du das einrichten`
- `oeffne github, logge mich ein und richte danach den webhook ein`
- `schau dir das an und bau mir danach einen plan`
- `recherchiere das und setze dann die ersten schritte direkt um`

Insbesondere muss Z1 den Unterschied schaerfen zwischen:

- `nur recherchieren`
- `erst planen`
- `direkt mehrschrittig ausfuehren`

## Empfohlene Umsetzungsreihenfolge

1. `task_decomposition_v1`-Contract und Builder
2. Frontdoor-Signal `planning_needed`
3. Routing-/Intent-Schaerfung fuer `build_setup` vs `research`
4. Typed Meta-Handoff mit `task_decomposition_json`
5. Test-/Contract-Block

## Abschlussbedingung fuer den naechsten Block

Nach Z1 soll Timus erstmals ein gemeinsames Decomposition-Objekt haben.

Erst dann ist Z2 sinnvoll:

- Meta Plan Compiler auf einem expliziten Vertragsobjekt
- statt wieder auf losem Prompt-Text

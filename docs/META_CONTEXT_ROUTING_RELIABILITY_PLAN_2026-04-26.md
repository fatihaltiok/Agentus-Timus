# Meta Context Routing Reliability Plan

Stand: 2026-04-26

## Anlass

Nach `MCA` und `GDK1` bis `GDK5` ist Timus stabiler gegen bekannte Drift-Faelle,
aber die Observation-Logs vom 26.04.2026 zeigen zwei noch offene
Reliability-Klassen:

1. bekannte Routing-/Context-Failures aus der lokalen Eval-Suite
2. ein neuer Telegram-Fall, in dem Timus den laufenden Beratungskontext im
   selben Chat verliert

Diese beiden Klassen duerfen nicht mit weiteren Einzelfall-Patches geloest
werden. Sie muessen als gemeinsamer Reliability-Block behandelt werden:

- erst Entscheidung
- dann genau passende Kontextzulassung
- dann Antwort oder Toolpfad
- mit Tests gegen ungesehene Formulierungen

## Beobachtung aus Telegram

Session:

- `tg_1679366204_e87f2c`

Relevanter Verlauf:

- Nutzer: `ich will ein Unternehmen gruenden und ki soll eine Rolle spielen wie koennte ich mit meinen Faehigkeiten starten`
- Timus fragt nach Skills, Ressourcen und Interessen.
- Nutzer: `du kannst mich ungefaehr einschaetzen was passt zu mir`
- Timus behandelt den Turn als neue breite Frage statt als Follow-up im
  Startup-/KI-Beratungskontext.
- Nutzer: `worueber hatte ich dich eben gebeten`
- Timus antwortet, der vorherige Kontext sei nicht sichtbar.
- Nutzer: `du vergisst schnell worum es geht so ist ein beratungs Gespraech nicht moeglich`
- Timus bestaetigt fehlendes persistentes Arbeitsgedaechtnis.
- Nutzer: `kannst du dieses Problem beheben`
- Timus fragt wieder `Welches Problem?`

Log-Befund:

- Die Telegram-Session-ID blieb ueber die Turns gleich.
- Trotzdem wurde im Meta-Run wiederholt `working_memory_injected` mit
  `context_chars: 0` erzeugt.
- Die zugelassene Kontextklasse war nur `conversation_state`.
- Der injizierte Bereich war nur `KURZZEITKONTEXT`, aber ohne relevante
  Turn-Inhalte.
- In der ersten Anfrage existierte relevantes Profile-/Self-Model-Material
  zur Person des Nutzers, wurde aber durch den Vertrag unterdrueckt.
- Der Store hatte Hinweise auf Session-Events und Follow-up-State, aber diese
  Inhalte wurden nicht als nutzbarer Kurzzeitkontext in den Prompt getragen.

Schlussfolgerung:

Das ist kein reines Modell-Vergessen. Die Laufzeit hat den Kontext nicht
ausreichend zugelassen oder nicht korrekt in die Working Memory injiziert.

## Bekannte Eval-Failures

Die zuletzt beobachtete breite Suite hatte:

- `tests/test_meta_orchestration.py::test_classify_meta_task_routes_direct_youtube_fact_check_to_research_recipe`
  - erwartet: `youtube_content_extraction`
  - erhalten: `single_lane`
- `tests/test_meta_orchestration.py::test_classify_meta_task_routes_local_nearby_queries_to_meta_executor`
  - erwartet: `location_local_search`
  - erhalten: `single_lane`
- `tests/test_meta_orchestration.py::test_classify_meta_task_routes_local_action_plus_place_queries_to_meta_executor`
  - erwartet: `location_local_search`
  - erhalten: `single_lane`
- `tests/test_meta_orchestration.py::test_classify_meta_task_routes_legal_claim_check_direct_to_research`
  - erwartet: `knowledge_research`
  - erhalten: `single_lane`
- `tests/test_meta_orchestration.py::test_classify_meta_task_normalizes_semantic_recall_into_bundle_slot`
  - erwartet: `semantic_recall` im Bundle
  - erhalten: leerer Slot

Diese Failures deuten auf denselben uebergeordneten Defekt:

- Der allgemeine Kernel faellt zu hart auf `single_lane` zurueck.
- Spezialrouten mit echter Evidenzpflicht werden zu frueh normalisiert.
- Semantischer Recall wird zu pauschal blockiert oder nicht sauber als
  erlaubte Evidenzklasse in den Bundle-Slot getragen.

## Root-Cause-Hypothesen

### H1. Single-Lane Over-Normalization

`GDK4` und `GDK5` schuetzen vor falscher Ausfuehrung, koennen aber echte
Research-, Local- oder YouTube-Faelle zu frueh auf `single_lane` begrenzen.

Validierung:

- pruefen, ob `classify_meta_task(...)` vor Spezialrouten bereits durch den
  Kernel-Fallback ueberschrieben wird
- Route-Snapshot fuer YouTube, Local Search und Legal Claim mit
  Decision-Kernel-Telemetrie vergleichen

### H2. Evidence-Routen Verlieren Vorrang

Anfragen mit klarer Evidenzpflicht duerfen nicht wie einfache Denkpartner-
Antworten behandelt werden.

Beispiele:

- YouTube-Faktencheck
- lokale Naehe-Suche
- juristische Claim-Pruefung

Validierung:

- `evidence_requirement` muss `bounded`, `research` oder `live_lookup` bleiben
- `execution_permission` darf Tooling begrenzen, aber nicht den notwendigen
  Evidenzpfad loeschen

### H3. Semantic Recall Wird Zu Pauschal Unterdrueckt

Die neue Kontextautoritaet ist richtig, aber zu hart, wenn der Nutzer
ausdruecklich auf vorherigen Kontext verweist.

Beispiele:

- `worueber hatte ich dich eben gebeten`
- `du weisst doch wofuer`
- `kannst du dieses Problem beheben`
- `was bedeutet das fuer mich`

Validierung:

- solche Turns muessen `turn_kind=resume` oder `turn_kind=context_recall`
  bekommen
- `conversation_state` muss letzte Turns enthalten
- `semantic_recall` bleibt optional und bounded, aber nicht grundsaetzlich leer

### H4. Kurzzeitkontext Wird Nicht In Den Prompt Gezogen

Die Session kann korrekt sein, aber der Prompt sieht nur `current_query`.
Dann kann das Modell den Faden nicht halten.

Validierung:

- `working_memory_injected.context_chars` darf bei gleichem Session-Follow-up
  nicht `0` sein, wenn frische Turns existieren
- `KURZZEITKONTEXT` muss mindestens die letzten relevanten User-/Assistant-
  Turns enthalten
- Telemetrie muss zeigen, welche Turn-IDs zugelassen wurden

### H5. Profile-/Self-Model Ist Nicht Als Bounded Evidence Zugelassen

Wenn der Nutzer fragt `du kannst mich ungefaehr einschaetzen`, ist
Preference-/Profile-Memory nicht Drift, sondern angefragte Evidenz.

Validierung:

- `preference_profile` darf nur bei expliziter Personalisierungsanfrage
  zugelassen werden
- Antwort muss Unsicherheit markieren
- keine freien Behauptungen ohne gespeicherte Quelle

### H6. Deiktische Referenzen Werden Als Neue Fragen Behandelt

Ausdruecke wie `dieses Problem`, `eben`, `dafuer`, `das`, `du weisst doch`
brauchen einen Referenzresolver vor der Antwortbildung.

Validierung:

- wenn frischer Open-Loop vorhanden ist, darf Timus nicht mit
  `Welches Problem?` antworten
- wenn kein Anker vorhanden ist, darf Timus klein klaeren
- der Resolver muss den gewaehlten Anker loggen

## Umsetzungsslices

### RCF1. Failure Freeze und Reproduktion

Ziel:

- die 5 bekannten Failures unveraendert als roten Testblock sichern
- Telegram-Beratungsverlauf als neue Regression festhalten

Umfang:

- Snapshot-Test fuer `classify_meta_task(...)`
- Integrationstest fuer `build_meta_context_bundle(...)`
- Telegram-Replay-Test mit derselben Session-ID
- Assertion auf `working_memory_injected.context_chars > 0` bei Follow-up

Erfolg:

- alle aktuellen Fehler sind reproduzierbar
- kein Fix beginnt ohne roten Test

### RCF2. Evidence-Route Preservation

Ziel:

- echte Evidence-Routen duerfen nicht durch `single_lane` verschluckt werden

Umfang:

- YouTube-Faktencheck wieder als `youtube_content_extraction`
- Local/Nearby wieder als `location_local_search`
- Legal Claim Check wieder als `knowledge_research`
- Kernel darf Budgets setzen, aber nicht die Route loeschen

Erfolg:

- die ersten 4 bekannten Routing-Failures sind gruen
- Low-Confidence bleibt fuer wirklich unklare Faelle aktiv

### RCF3. Semantic-Recall Slot Normalisierung

Ziel:

- erlaubter semantischer Recall wird korrekt in den Bundle-Slot geschrieben

Umfang:

- klare Trennung:
  - `conversation_state`
  - `semantic_recall`
  - `document_knowledge`
  - `preference_profile`
- kein leerer Slot, wenn der Vertrag Recall erlaubt
- keine Vermischung mit Profile- oder Dokumentwissen

Erfolg:

- der fuenfte bekannte Failure ist gruen
- MCA4 bleibt erhalten

### CCF1. Conversation Carryover Gate

Ziel:

- gleiche Session plus frische Turns ergibt einen nutzbaren Kurzzeitkontext

Umfang:

- letzte relevante Turns als `conversation_state` zulassen
- `KURZZEITKONTEXT` darf nicht leer sein, wenn frische Session-Events existieren
- Tokenbudget klein halten
- keine globale Memory-Flutung

Erfolg:

- `worueber hatte ich dich eben gebeten` findet den direkten Vorturn
- Timus kann den Beratungsfaden fortsetzen

### CCF2. Open-Loop und Pending-Follow-up Resolver

Ziel:

- Timus erkennt, ob ein Turn einen offenen Gespraechsfaden fortsetzt

Umfang:

- `current_topic`
- `pending_followup_prompt`
- letzter User-Goal-Frame
- letzter Assistant-Clarification-Frame
- frische Zeitgrenze

Erfolg:

- `du kannst mich ungefaehr einschaetzen` bleibt im Startup-/KI-Kontext
- `mach jetzt Vorschlaege` bleibt beim vorherigen Ausflugskontext
- `kannst du dieses Problem beheben` bezieht sich auf den zuletzt genannten
  Kontextverlust

### CCF3. Deictic Reference Resolver

Ziel:

- Referenzen wie `dieses Problem`, `eben`, `dafuer`, `das` werden vor der
  Antwort an einen Anker gebunden

Umfang:

- kleine Resolver-Funktion vor GDK-Kontextzulassung
- Ausgabe:
  - `resolved_reference`
  - `source_turn_id`
  - `confidence`
  - `fallback_question`
- bei hoher Sicherheit wird kein erneutes `Welches Problem?` erlaubt

Erfolg:

- Timus fragt nur dann nach, wenn wirklich kein Anker existiert

### CCF4. Bounded Profile Advisory Gate

Ziel:

- persoenliche Einschaetzung darf Profile-/Preference-Memory nutzen, wenn der
  Nutzer genau das verlangt

Umfang:

- Trigger:
  - `du kennst mich`
  - `du kannst mich einschaetzen`
  - `was passt zu mir`
  - `mit meinen Faehigkeiten`
- erlaubt:
  - kurze Profile-Fakten mit Provenienzklasse
  - Unsicherheitsmarker
  - Nachfrage nur fuer fehlende harte Details
- verboten:
  - breite semantische Erinnerung ohne Zweck
  - erfundene Eigenschaften
  - Profilnutzung bei neutralen Sachfragen

Erfolg:

- Timus kann persoenlich beraten, ohne zu halluzinieren oder zu blockieren

### CCF5. Advisory Answer Formation Contract

Ziel:

- nach korrekt erkanntem Frame muss die finale Antwort den Frame respektieren

Umfang:

- Startup-/KI-Beratung als `topic_family=advisory`
- `interaction_mode=think_partner`
- erlaubte Quellen:
  - current query
  - recent conversation state
  - bounded profile if explicitly requested
- Antwortpflicht:
  - erst aufgreifen, was bekannt ist
  - dann maximal gezielt klaeren
  - keine Behauptung `Kontext leer`, wenn Kontext vorhanden ist

Erfolg:

- Timus fuehrt ein Beratungsgespraech statt pro Turn neu zu starten

### CCF6. Live Gates

Ziel:

- der Fix gilt nur, wenn er in echten Chatpfaden funktioniert

Pflichtfaelle:

- Startup-/KI-Beratung mit `du kannst mich ungefaehr einschaetzen`
- `worueber hatte ich dich eben gebeten`
- `kannst du dieses Problem beheben`
- Ausflugskontext mit `mach jetzt Vorschlaege`
- Deep-Research-Follow-up mit `was bedeutet das fuer mich`
- neutraler neuer Topic-Wechsel, der keinen alten Kontext ziehen darf

Erfolg:

- Follow-up wird fortgesetzt
- echter Topic-Wechsel bleibt sauber
- kein Skill-Creator-, Setup- oder Location-Drift

## Reihenfolge

1. `RCF1` zuerst: rote Tests und Replay sichern.
2. `CCF1` und `CCF2`: Kurzzeitkontext und Open-Loop-Anker reparieren.
3. `CCF3`: deiktische Referenzen hart absichern.
4. `CCF4` und `CCF5`: persoenliche Beratung nutzbar machen.
5. `RCF2` und `RCF3`: die 5 bekannten Routing-/Recall-Failures schliessen.
6. `CCF6`: Live-Gates aus Telegram und API.
7. Changelog aktualisieren.
8. Commit, Restart, Live-Test.

Warum diese Reihenfolge:

- Der Telegram-Fall blockiert direkt die Nutzbarkeit als Gespraechspartner.
- Die 5 Eval-Failures bleiben wichtig, sind aber weniger akut als der
  fundamentale Fadenverlust in derselben Session.
- RCF1 muss trotzdem zuerst passieren, damit spaetere Fixes nicht neue
  Regressionen verstecken.

## Nicht-Ziele

- kein breites Dumpen aller Memories in jeden Prompt
- kein globaler Kontext ohne Session-/Domain-Grenze
- keine Abschwaechung von MCA4
- kein Abschalten des Low-Confidence-Controllers
- keine Spezialregel nur fuer den exakten Telegram-Text

## Akzeptanzkriterien

Der Block ist abgeschlossen, wenn:

- alle 5 bekannten Failures gruen sind
- Telegram-Replay den Beratungskontext ueber mehrere Turns haelt
- `working_memory_injected.context_chars` bei frischen Follow-ups nicht `0` ist
- `preference_profile` nur bei expliziter Personalisierung zugelassen wird
- echte neue Themen nicht mit altem Kontext kontaminiert werden
- Live-Test ueber Telegram und lokale `/chat`-API bestanden ist

## Architekturprinzip

Timus soll nicht mehr raten, ob Kontext gebraucht wird. Timus soll vor jeder
Antwort entscheiden:

1. Ist das ein neuer Auftrag oder ein Follow-up?
2. Welche Evidenzklasse ist fuer genau diesen Turn erlaubt?
3. Welcher konkrete Kontextanker ist frisch und relevant?
4. Muss ich antworten, fragen, recherchieren oder ausfuehren?

Erst danach darf Kontext in den Prompt. Das ist die Bruecke von
fallgetriebener Haertung zu allgemein stabiler Gespraechs- und
Agentenfaehigkeit.

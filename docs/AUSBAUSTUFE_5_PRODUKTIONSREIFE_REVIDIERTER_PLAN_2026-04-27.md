# Ausbaustufe 5 - Revidierter Plan zur Produktionsreife

Stand: 2026-04-27

Dieser Plan ersetzt nicht die bestehenden MFR/MIM/MCA/GDK/CCF-Plaene, sondern
ordnet die naechsten Schritte fuer Produktionsreife neu. Die wichtigste
Korrektur gegenueber dem urspruenglichen Plan:

- Nicht mit einem grossen `meta_clarity_contract`-Refactor starten.
- Erst den Arbeitsstand sauber machen.
- Dann Live-Gates fuer echte Alltagsthemen aufbauen.
- Danach gezielte GDK-Fixes aus den Live-Gates ableiten.
- Erst danach die Clarity-Slot-Matrix in kleinen Slices migrieren.

## Zielbild

Timus soll einfache Alltagshandlungen direkt ausfuehren, neue Themen robust
einordnen, Spezialagenten bei Blockaden umgehen koennen und seinen Zustand
beobachtbar halten.

Produktionsreif bedeutet hier:

- keine Modus-Diskussion bei klaren Ausfuehrungsauftraegen
- keine Spezialvertrags-Drifts bei neuen Themen
- kein blindes Festhalten an einem falschen Agenten
- stabile Multi-Turn-Kontexte
- saubere Health-/Restart-/Deployment-Gates
- nachvollziehbare Logs fuer jede harte Entscheidung

## Aktueller Ausgangspunkt

Bereits weitgehend umgesetzt:

- MFR: Frame-first Routing und Frame-Contracts
- MIM: Interaktionsmodi `think_partner`, `inspect`, `assist`
- MCA: Context Authority, Working-Memory-Gating, Evidence Classes
- CCF1-CCF6: Conversation Carryover, Open-Loops, Deictic References,
  Personal Assessment, Answer Formation, Live-Gates
- Local File Transform Fast-Path: ODT/PDF-aehnliche lokale Datei-Transformationen
  werden als `document_generation` + `execute` erkannt

Bekannte Restklasse:

- GDK/MIM darf neue triviale Alltagsaufgaben nicht mehr in Beratung oder
  `clarify_before_execute` zurueckdruecken.
- Live-Gates decken noch zu wenig unerwartete Alltagsthemen ab.
- Repo-Hygiene ist nicht sauber, weil `.pyc`-Artefakte noch getrackt sind.
- Agenten-Fallbacks sind noch nicht produktionshart.

## Grundregeln fuer Ausbaustufe 5

1. Jeder Slice endet mit Tests und Commit.
2. Keine grossen Refactors ohne vorherige Live-Gates.
3. Keine Abschwaechung von MCA4: nicht alles gleichzeitig in den Antwortpfad kippen.
4. Sensible Kontextklassen bleiben restriktiv:
   `preference_profile`, `document_knowledge`, `location`, `credentials`.
5. Neue Slots duerfen nicht unsichtbar verschwinden:
   jeder Filter braucht Audit-Spur.
6. Live-Verhalten ist wichtiger als schoene Architektur, aber Architektur muss
   danach vereinheitlicht werden.

## Revidierte Reihenfolge

### Phase 0 - Bereits erledigt: Local File Transform

Status: umgesetzt, noch als eigener Slice zu behandeln.

Ziel:

- Datei-Konvertierungen wie `wandle diese ODT in PDF` muessen direkt auf
  `document_generation`, `execute`, `meta -> document` gehen.
- `think_partner` darf solche klaren Ausfuehrungsauftraege nicht blockieren.
- `mach das` muss funktionieren, wenn der offene Kontext eine lokale
  Datei-Konvertierung enthaelt.

Akzeptanz:

- direkte ODT->PDF-Anfragen laufen ohne Modus-Diskussion
- `mach das` mit offenem Konvertierungsfaden laeuft als Execute
- erklaerende Frage wie `was ist eine pdf datei` bleibt Beratung und wird nicht
  ausgefuehrt

### Phase 1 - F1: Deployment-Hygiene zuerst

Warum zuerst:

Der aktuelle `git status` ist zu laut. Solange `.pyc`, venvs und lokale
Artefakte sichtbar sind, werden echte Aenderungen schwerer kontrollierbar.

Aufgaben:

- `.gitignore` erweitern:
  - `__pycache__/`
  - `*.py[cod]`
  - `.pytest_cache/`
  - `.hypothesis/`
  - `.venv/`
  - `venv/`
  - lokale Runtime-/Temp-Artefakte nach Pruefung
- getrackte `.pyc` mit `git rm --cached` aus dem Index entfernen
- keine fachlichen Code-Aenderungen in diesem Slice

Akzeptanz:

- `git ls-files '*.pyc'` liefert leer
- `git status` zeigt keine `.pyc`-Modifikationen mehr
- bestehender Python-Regressionsblock bleibt gruen

Risiko:

- Niedrig. Das ist Repo-Hygiene, kein Runtime-Verhalten.

### Phase 2 - B1/B2: Live-Request-Korpus und Klassifikations-Gates

Warum vor GDK-Refactor:

Wir brauchen zuerst echte Alltagsthemen als Messlatte. Sonst optimieren wir
wieder nur gegen die gerade sichtbaren Fehler.

Neue Datei:

- `tests/fixtures/live_request_corpus.json`

Kategorien:

- `trivial_execution`
- `quick_lookup`
- `followup_context`
- `advisory`
- `behavior_instruction`
- `multi_step`
- `correction`
- `clarification`
- `document_or_file`
- `communication`

Pro Fall speichern:

- `id`
- `query`
- optional `conversation_state`
- optional `recent_user_turns`
- erwarteter `task_type`
- erwarteter `response_mode`
- erwartete erste oder komplette Agentenkette
- erwarteter `interaction_mode`
- verbotene Drifts, z.B. `skill_creator`, `setup_build`, `location`, `think_partner`

Neue Testdatei:

- `tests/test_live_request_corpus.py`

Akzeptanz:

- mindestens 40 echte oder realistische Anfragen
- parametrisierter Klassifikationstest laeuft lokal
- initial duerfen einzelne Faelle rot sein, aber jeder rote Fall bekommt eine
  Entscheidung: Bug, Erwartung falsch, oder eigener Folge-Slice

Risiko:

- Mittel. Nicht jeder Fall wird sofort gruen sein. Das ist beabsichtigt.

### Phase 3 - A4/GDK6: Trivial- und Alltagsexecution haerten

Warum jetzt:

Nach Phase 2 wissen wir, welche simplen Aufgaben noch falsch in Beratung,
Clarify oder Spezialdrift fallen.

Aufgaben:

- `local_file_transform` ausbauen:
  - Dateien verschieben/kopieren/umbenennen
  - Ordner erstellen
  - einfache Export-/Konvertierungsauftraege
- `quick_lookup` klar von `deep_research` trennen
- `communication`-Auftraege sauber von Beratung trennen
- `think_partner` darf nur greifen, wenn die Anfrage wirklich Denken/Beratung
  verlangt oder explizit keine Tools will

Akzeptanz:

- alle `trivial_execution`-Faelle aus dem Korpus laufen ohne
  `clarify_before_execute`
- keine `acknowledge_and_store`-Fehlklassifikation fuer Ausfuehrungsauftraege
- keine Modus-Diskussion bei klaren Aufgaben

Risiko:

- Mittel. Zu breite Patterns koennen False Positives ausloesen.
- Schutz: jede neue Regel bekommt mindestens einen positiven und einen negativen
  Test.

### Phase 4 - E1: Live-Drift-Detector

Warum vor grossem Refactor:

Wenn Timus wieder in Modus-Diskussion, endlose Klaerung oder leere Antwortpfade
faellt, soll das live sichtbar werden.

Neue Datei:

- `orchestration/live_drift_detector.py`

Erste Drift-Patterns:

- drei `clarify_before_execute` mit gleichem Anker
- zwei Turns mit `context_chars == 0`, obwohl Follow-up/State vorhanden ist
- Antwort sagt `Kontext leer`, obwohl `conversation_state` zugelassen wurde
- Antwort blockiert Toolnutzung trotz `response_mode=execute`
- wiederholte Modus-Erklaerung statt Ausfuehrung

Akzeptanz:

- Unit-Tests fuer mindestens 5 Drift-Szenarien
- False-Positive-Schutz fuer echte Klaerfragen
- Observation-Payload nennt Drift-Typ, Anker und empfohlene Korrektur

Risiko:

- Niedrig bis mittel. Zunaechst nur Diagnose, keine automatische Aenderung am
  Verhalten.

### Phase 5 - C1/C2: Agenten-Fallback-Grundlage

Warum danach:

Wenn Routing besser ist, muss die Ausfuehrung robust werden. Ein blockierter
Spezialagent darf nicht die ganze Nutzeranfrage blockieren.

Neue Datei:

- `orchestration/agent_fallback_registry.py`

Start-Fallbacks:

- `research -> executor -> answer_directly`
- `document -> shell -> answer_directly`
- `developer -> shell -> executor`
- `visual -> ocr_only -> executor`
- `executor -> shell -> answer_directly`

C2:

- Timeout-/Empty-Result-Detector im Delegationspfad
- noch kein grosses Outcome-Learning

Akzeptanz:

- mockbarer Test: Agent liefert leer oder Timeout, Fallback wird gewaehlt
- finaler Nutzerpfad endet mit brauchbarer Antwort oder echtem Blocker, nicht
  mit leerem Ergebnis

Risiko:

- Mittel. Fallbacks koennen falsche Agenten aktivieren, wenn der Fehler schlecht
  klassifiziert wird.

### Phase 6 - A1 vorsichtig: Clarity Slot Matrix in Slices

Warum spaeter:

`meta_clarity_contract.py` ist aktuell stabil, aber schwer wartbar. Ein kompletter
Umbau zu Beginn waere zu riskant. Die Matrix kommt erst, wenn Live-Gates und
Drift-Detector Schutz bieten.

Aufteilung:

#### A1a - Matrix spiegeln, nicht nutzen

Neue Datei:

- `orchestration/clarity_slot_matrix.py`

Inhalt:

- deklarative Matrix fuer bekannte `request_kind`/`response_mode`-Faelle
- generiert dieselben allowed/forbidden Slots wie der bestehende Code
- wird nur in Tests verglichen, noch nicht runtime-aktiv

Akzeptanz:

- Snapshot-Test: Matrix und bestehender Contract liefern gleiche Slot-Entscheidungen
- keine Runtime-Verhaltensaenderung

#### A1b - einzelne Modes migrieren

Reihenfolge:

1. `clarify_question`
2. `acknowledgment`
3. `resume_action`
4. `thinking_partner`
5. `execute_task`

Akzeptanz pro Slice:

- CCF-Tests gruen
- Android-Chat-Tests gruen
- Live-Korpus-Kategorie gruen

#### A2 - Conditional Slots

Nur nach A1b.

Ziel:

- `preference_memory` wird erlaubt, wenn gespeicherter `topic_anchor` mit
  aktueller Query, aktivem Thema oder Open-Loop ueberlappt.

Wichtig:

- Nicht global freischalten.
- Nicht bei sensiblen Profil-/Credential-Klassen.

#### A3 - Unknown Slot Audit

Abweichung vom urspruenglichen Plan:

- Nicht pauschal `default allow`.
- Default:
  - nicht-sensible Slots: allow + audit
  - sensible Slots: deny + audit

Sensible Klassen:

- `preference_profile`
- `document_knowledge`
- `location`
- `credentials`
- `personal_identity`

### Phase 7 - D: End-to-End-Suiten

Erst sinnvoll, wenn Phase 2-5 stabile Grundlagen liefern.

Start mit:

- API-E2E ueber `/chat` mit Fake-LLM/Fake-Agenten
- Telegram-E2E mit Mock-Gateway

Akzeptanz:

- 10-15 Multi-Turn-Szenarien
- State persistiert zwischen Turns
- Follow-up nutzt State
- Tool-/Delegationspfad wird beobachtet

### Phase 8 - F2-F4: Health, Restart, Pre-Deploy

Aufgaben:

- Health-Endpoint mit Subchecks:
  - DB
  - Qdrant/Memory
  - Tool Registry
  - LLM Endpoint
  - Telegram Gateway
- Restart-Probe:
  - Anfrage
  - Prozessrestart
  - Follow-up nutzt Session/Memory weiter
- `scripts/pre_deploy.sh`
  - Worktree sauber
  - Python-Tests
  - Lean nur kontrolliert mit Timeout/Skip-Option
  - Migrationsstand

## Neue empfohlene Wochenplanung

### Woche 1

- Phase 1: F1 Repo-Hygiene
- Phase 2: B1/B2 Live-Korpus + Klassifikationsrunner
- kleine Fixes fuer die offensichtlichsten roten Gates

### Woche 2

- Phase 3: GDK6 Trivial-/Alltagsexecution
- Phase 4: E1 Drift-Detector
- Beginn C1 Fallback-Registry

### Woche 3

- Phase 5: C2 Timeout/Empty-Result-Fallback
- Phase 6: A1a Matrix spiegeln ohne Runtime-Aenderung
- erste API-E2E-Szenarien

### Woche 4

- A1b schrittweise Migration einzelner Response-Modes
- D Telegram/API E2E erweitern
- F2-F4 Health/Restart/Pre-Deploy

## Naechste 3 konkrete Aufgaben

1. `F1`: `.gitignore` und tracked `.pyc` cleanup.
2. `B1/B2`: `tests/fixtures/live_request_corpus.json` und
   `tests/test_live_request_corpus.py` erstellen.
3. `A4/GDK6`: aus den roten Korpusfaellen die naechsten trivialen
   Execution-Fast-Paths ableiten.

## Stop-Kriterien

Nicht weitermachen, wenn:

- der breite Regressionsblock rot ist
- ein Fix `think_partner` fuer echte Beratungsfragen abschaltet
- neue Slots ohne Audit verschwinden
- lokale Datei-/Tool-Ausfuehrung ohne klaren Nutzerauftrag startet
- Git-Status durch Hygiene-Slice unklarer statt klarer wird


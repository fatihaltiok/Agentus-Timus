# Architekturleitfaden fuer kleine LLM-Chatbots

Stand: 2026-04-25

## Worum es wirklich geht

Ein kleiner lokaler oder freier Chatbot wird **nicht** dadurch gut, dass man so
tut, als waere das Modell allein so stark wie ChatGPT.

Er wird dann stark, wenn die Architektur die Dinge ausserhalb des Modells sauber
uebernimmt:

- Turn-Verstehen
- Kontextdisziplin
- Zustandsfuehrung
- Evidenzfuehrung
- Tool-Freigaben
- Unsicherheitsverhalten
- Evaluation

Die richtige Aussage ist deshalb nicht:

- `ein kleines LLM ist einfach so so gut wie ChatGPT`

sondern:

- `ein kleines LLM kann in vielen Produktpfaden fuer den Nutzer fast so gut
  wirken wie ChatGPT, wenn die Systemarchitektur die fehlende Modellstaerke
  gezielt kompensiert`

## Wo kleine Modelle typischerweise schlechter sind

Kleine Modelle haben meist Nachteile bei:

- offener Weltkenntnis
- breiter Formulierungsrobustheit
- langer impliziter Kontextkontinuitaet
- stiller Priorisierung zwischen konkurrierenden Signalen
- Tool- und Ausfuehrungsdisziplin ohne starke Runtime-Hilfe

Wenn man diese Schwächen ignoriert, wirkt der Chatbot sprunghaft, driftend oder
zu mechanisch.

## Was die Architektur kompensieren muss

### 1. Das Modell ist fuer Sprache da, nicht fuer alles

Ein gutes kleines System laesst das Modell vor allem diese Arbeit machen:

- sprachliche Interpretation
- Verdichtung
- Antwortformulierung
- Optionen und Abwaegungen

Die restlichen Aufgaben werden in explizite Systembausteine verschoben:

- Entscheidung
- Zustand
- Evidenz
- Tools
- Governance

### 2. Entscheidung vor Kontext

Der haeufigste Fehler kleiner Chatbots ist:

1. zu viel Kontext laden
2. Anfrage und Recall vermischen
3. erst danach versuchen, Drift zu reparieren

Richtig ist:

1. erst entscheiden, was fuer ein Turn vorliegt
2. dann passende Kontextklassen zulassen
3. dann erst Antwort oder Ausfuehrung starten

### 3. Wissensklassen strikt trennen

Ein kleiner Chatbot braucht mindestens diese Trennung:

- `conversation_state`
- `semantic_recall`
- `document_knowledge`
- `preference_profile`

Ohne diese Trennung behandelt das System:

- eine alte Erinnerung
- eine harte Quelle
- eine Nutzerpraeferenz
- und den aktuellen Arbeitszustand

als fast gleichwertig. Genau daraus entstehen plausible, aber falsch
begruendete Antworten.

### 4. Arbeitsmodi statt nur freier Prompt

Der Chatbot braucht interne Modi wie:

- `think`
- `inspect`
- `assist`

Nicht als Bedienlast fuer den Nutzer, sondern als interne Arbeitsdisziplin.

Dadurch wird klar:

- wann nur gedacht wird
- wann Evidenz geholt wird
- wann ausgefuehrt werden darf

### 5. Fail small bei Unsicherheit

Ein kleines Modell darf bei Unsicherheit nicht einfach immer mehr tun.

Richtiges Low-Confidence-Verhalten:

- kleine direkte Antwort
- oder genau eine Rueckfrage
- keine breite Agentenkette
- keine ungefragte Recherche

### 6. Bounded Retrieval statt Erinnerungsbrei

Retrieval muss:

- klein
- priorisiert
- quellenbewusst
- turn-spezifisch

sein.

Nicht:

- moeglichst viel semantisch Aehnliches in den Prompt schieben

Sondern:

- gezielt nur das, was fuer genau diesen Turn ursachenrelevant ist

### 7. Quellenpflicht fuer starke Behauptungen

Wenn der Bot etwas mit hohem Wahrheitsanspruch sagt, sollte die Architektur
unterscheiden:

- stammt es aus Dokumenten?
- aus Arbeitszustand?
- aus weicher Erinnerung?
- aus Nutzerprofil?

Das gilt spaeter besonders fuer:

- PDFs
- Doku
- Reports
- Wissensdatenbanken

### 8. Gute UX kommt auch aus Latenz

Ein kleiner lokaler Bot kann einen echten Vorteil gegenueber grossen Remote-
Systemen haben:

- kurze Reaktionszeit
- hohe Verfuegbarkeit
- volle Datenhoheit
- billige Iteration

Wenn die Antworten schnell, stabil und kontextdiszipliniert sind, wird der Bot
oft als intelligenter wahrgenommen, selbst wenn das Grundmodell kleiner ist.

## Wann ein kleiner Bot fuer Nutzer fast so gut wie ChatGPT wirken kann

Unter diesen Bedingungen:

1. enger oder halbenger Produktkontext
2. klare Architektur fuer State und Retrieval
3. gute Turn-Entscheidung vor Tooling
4. schnelle und zuverlaessige Runtime
5. starke Eval-Disziplin
6. gute Antwortstilfuehrung

Beispiele:

- Projektassistenz im eigenen Repo
- persoenliche Wissensbasis
- Dokument- und PDF-Arbeit
- Planungs- und Assistenzaufgaben
- kontrollierte Recherche mit Quellenangaben

## Wann er nicht so gut wie ChatGPT ist

Nicht realistisch gleichwertig bei:

- sehr breiter offener Weltkenntnis ohne Retrieval
- extrem freien, nuancierten langen Alltagsgespraechen
- unbekannten Problemraeumen ohne gute Werkzeuge und Evals
- stark multimodalen Generalfaellen ohne spezialisierte Runtime

Das ist keine Niederlage, sondern eine Architekturgrenze.

## Empfohlene Minimalarchitektur

### A. Decision Kernel

Pflichtfelder:

- `turn_kind`
- `topic_family`
- `interaction_mode`
- `evidence_requirement`
- `execution_permission`
- `confidence`

### B. State Layer

Pflicht:

- aktuelles Thema
- aktuelles Ziel
- offener Faden
- naechster Schritt
- aktive Domaene

### C. Evidence Layer

Pflicht:

- Dokumente
- semantischer Recall
- Nutzerprofil
- laufender Dialogzustand

mit sichtbarer Klassifikation und Priorisierung

### D. Tool Layer

Pflicht:

- erlaubte Tools je Turn
- bounded inspection
- bounded execution
- kein stilles Tool-Wachstum

### E. Response Layer

Pflicht:

- direkte Antwort
- Bericht
- Rueckfrage
- Ausfuehrungsplan

je nach Turn unterschiedlich

### F. Eval Layer

Pflicht:

- bekannte Regressionen
- ungesehene Aufgaben
- reale Dialogfolgen
- Cross-Domain-Wechsel

## Anti-Patterns

Nicht tun:

- alles in einen langen Systemprompt kippen
- jede neue Fehlerklasse mit einer Einzelheuristik reparieren
- Retrieval ohne Kontextklassifikation
- freie Toolausfuehrung bei unklarer Anfrage
- keine Telemetrie fuer Entscheidungsgruende
- Erfolg nur aus einem gelungenen Einzelfall ableiten

## Vorgehensweise fuer kuenftige Projekte

### Phase 1. Entscheidung

Zuerst den Decision Kernel bauen.

### Phase 2. Zustand

Dann Session-State und Follow-up-Fuehrung sauber aufbauen.

### Phase 3. Evidenz

Danach Dokumente, Recall und Nutzerprofil trennen.

### Phase 4. Modus und Tools

Dann Arbeitsmodi und Toolgrenzen einziehen.

### Phase 5. Evaluation

Erst danach ueber Produktreife urteilen.

## Praktische Leitlinie

Wenn ein kleiner Chatbot fuer Nutzer gut wirken soll, dann darf man nicht
fragen:

- `Wie kriegen wir mehr Intelligenz aus dem Modell allein?`

Sondern:

- `Welche Teile der Leistung muessen explizit in die Architektur wandern, damit
  das Modell nur noch die Arbeit macht, in der es stark ist?`

## Kurzfassung

Ein kleiner lokaler Chatbot wird nicht deshalb stark, weil das Modell heimlich
doch gross genug ist.

Er wird stark, wenn:

- die Entscheidungsschicht sauber ist
- der Kontext diszipliniert bleibt
- die Evidenzarten getrennt sind
- Unsicherheit klein fehlschlaegt
- und das System gegen reale Aufgaben evaluiert wird

Dann kann er in vielen Produktpfaden fuer den Nutzer fast so gut wirken wie ein
grosses System, obwohl das Grundmodell kleiner und billiger ist.

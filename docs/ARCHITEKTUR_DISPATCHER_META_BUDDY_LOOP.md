# Architektur: Dispatcher-Meta Buddy Loop

## Arbeitstitel

Non-Hierarchical Dual-Agent Frontdoor for Personal AI Systems

Kurzform:

- Dispatcher-Meta Buddy Loop
- Buddy Loop Architecture

## Problem

Viele Agentensysteme arbeiten hierarchisch:

- ein Supervisor entscheidet
- Spezialisten fuehren aus
- Unsicherheit wird nach oben eskaliert

Dieses Muster ist robust, aber fuer persoenliche Assistenten oft zu grob. Die Frontdoor eines Assistenzsystems hat andere Probleme:

- Umgangssprache
- kurze Follow-ups
- implizite Referenzen
- vage Nutzerkorrekturen
- schnelle Wechsel zwischen Small Talk, Recherche, Aktion und Selbstbezug

In Timus zeigt sich genau das:

- der Dispatcher ist schnell, aber bei Umgangssprache und impliziten Bezuengen oft zu schwach
- Meta versteht die Bedeutung haeufig besser, muss aber zu oft den Dispatcher retten
- dadurch entsteht ein unguenstiges Muster:
  - Dispatcher faellt mit `empty_decision` aus
  - Meta wird zum Feuerwehr-Agenten
  - die Frontdoor bleibt semantisch schwach

## Kernthese

Die Frontdoor eines persoenlichen KI-Systems sollte nicht nur ein einzelner Klassifikator sein.

Stattdessen kann sie als Buddy-System aus zwei gleichrangigen Agenten modelliert werden:

- Dispatcher Buddy
- Meta Buddy

Beide arbeiten auf Augenhoehe, aber mit unterschiedlichen Staerken.

Wichtig:

- keine Hierarchie
- kein Chef-Agent
- keine blinde Delegation

Sondern:

- gegenseitige Kritik
- strukturierte Vorhypothesen
- regelbasierte Einigung
- konservative Eskalation bei Konflikt

## Zielbild

Nicht:

- Dispatcher entscheidet allein
- oder Meta entscheidet immer als hoechste Instanz

Sondern:

- Dispatcher macht eine schnelle Erstdeutung
- Meta prueft Bedeutung, Risiko und Konflikte
- beide liefern strukturierte Hypothesen
- ein Buddy-Arbitration-Protokoll bestimmt den naechsten Schritt

## Rollen

### Dispatcher Buddy

Staerken:

- schnell
- frontdoor-nah
- gut fuer Erstsortierung
- empfindlich fuer Umgangssprache, Tonfall und Follow-up-Signale

Aufgaben:

- erste Intent-Hypothese
- Erkennung von:
  - Follow-up
  - Ortsbezug
  - Freshness-Bedarf
  - Dateiwunsch
  - Aktionswunsch
- Benennung von Unsicherheit
- Vorschlag einer ersten Route

### Meta Buddy

Staerken:

- semantisch tiefer
- konfliktfaehig
- replanning-stark
- besser bei Mehrdeutigkeit und Selbstkorrektur

Aufgaben:

- Pruefung der Dispatcher-Hypothese
- Konfliktanalyse
- Zielklaerung
- Auswahl konservativerer oder tieferer Pfade
- Rueckmeldung an Dispatcher, wenn die Erstdeutung falsch oder zu grob war

## Warum das keine Hierarchie ist

Die Entscheidung kommt nicht durch Rang zustande, sondern durch Protokoll.

Weder Dispatcher noch Meta sind "Chef".

Die finale Richtung entsteht aus:

- Uebereinstimmung
- Unsicherheit
- Evidenz
- Risiko
- Konfliktgrad

## Buddy-Protokoll

Jeder Buddy produziert eine strukturierte Hypothese.

### BuddyHypothesis

Pflichtfelder:

- `intent`
- `goal`
- `confidence`
- `uncertainty`
- `candidate_routes`
- `risk_level`
- `needs_clarification`
- `reasoning_summary`

Optionale Felder:

- `followup_reference`
- `location_relevance`
- `freshness_requirement`
- `artifact_need`
- `delivery_need`
- `state_invalidation_signal`

### Beispiel

Nutzer:

`ich habe meinen handy standort aktualisiert du musst das registrieren`

Dispatcher-Hypothese:

- `intent = state_update`
- `goal = revalidate_location_state`
- `confidence = 0.62`
- `candidate_routes = ["meta_state_revalidation", "executor_location_refresh"]`
- `needs_clarification = false`

Meta-Hypothese:

- `intent = user_reported_state_invalidation`
- `goal = invalidate_stale_negative_location_state_then_revalidate`
- `confidence = 0.87`
- `candidate_routes = ["meta_runtime_state_correction"]`
- `needs_clarification = false`

## Buddy-Arbitration

Die Arbitration ist ein Regelwerk, kein Chef-Agent.

### Entscheidungszustaende

#### 1. aligned

Beide Hypothesen zeigen in dieselbe Richtung.

Aktion:

- Fast Path
- Route ausfuehren

#### 2. soft_conflict

Die Ziele sind aehnlich, aber nicht identisch.

Aktion:

- konservativere Route waehlen
- Meta kann die Dispatcher-Route nachschaerfen

#### 3. hard_conflict

Die beiden Buddys sehen verschiedene Bedeutungen.

Aktion:

- Rueckfrage
- oder Meta-Rezept mit Unsicherheitsmarker

#### 4. insufficient_signal

Beide sind unsicher.

Aktion:

- keine Blindentscheidung
- Rueckfrage oder sichere Minimalantwort

## Entscheidungsregeln

Beispielregeln:

- Wenn `dispatcher.confidence hoch` und `meta zustimmt`:
  - Dispatcher-Fast-Path

- Wenn `dispatcher.confidence hoch`, `meta widerspricht deutlich`:
  - Meta-konservativer Pfad

- Wenn `dispatcher unsicher`, `meta klar`:
  - Meta-Pfad

- Wenn beide unsicher:
  - Rueckfrage

- Wenn `risk_level hoch`:
  - nie Fast-Path ohne Meta-Bestaetigung

## Gemeinsamer Zustand

Damit der Buddy-Loop funktioniert, brauchen beide einen geteilten, aber begrenzten Zustand.

### BuddyState

- letzte Nutzeranfrage
- letzte 1-3 relevanten Turns
- Topic-Recall
- letzter erfolgreicher Pfad
- offene Artefakt-/Delivery-/Verification-Bedarfe
- Runtime-Zustand
- Standort-/State-Korrekturen

Wichtig:

- nicht den ganzen Dialog ungebremst mitschleppen
- sondern gezielt verdichtete Frontdoor-Signale

## Lernen

Ein Buddy-System wird erst dann stark, wenn beide voneinander lernen.

### Dispatcher lernt

- welche Umgangssprachemuster Meta spaeter korrigiert hat
- welche Follow-up-Formulierungen haeufig `empty_decision` erzeugen
- wann lokale Suche zu aggressiv getriggert wurde

### Meta lernt

- wo Dispatcher bereits richtig lag
- wo Meta zu haeufig ueberkorrigiert
- welche Konflikte immer wieder dieselbe Loesung brauchen

### BuddyMemory

Speichern sollte man:

- Hypothesenpaare
- finale Arbitration
- Outcome
- Nutzerkorrekturen
- spaetere erfolgreiche Route

## Timus-spezifische Einordnung

Der Buddy-Loop passt genau auf die beobachtete Schwaeche in Timus:

- Dispatcher ist die Frontdoor
- Meta ist semantisch staerker
- aktuell fehlt aber ein gutes Zwischenprotokoll

Heute ist der Ist-Zustand oft:

- Dispatcher -> `empty_decision`
- Meta rettet

Zielzustand:

- Dispatcher liefert bei Unsicherheit nicht Leere, sondern eine strukturierte Vorhypothese
- Meta antwortet darauf nicht nur mit "uebernehmen", sondern mit:
  - bestaetigen
  - korrigieren
  - verfeinern
  - Rueckfrage erzwingen

## Was daran innovativ sein koennte

Multi-Agent-Systeme gibt es bereits.

Nicht neu ist:

- Agenten reden miteinander
- Supervisor-Worker-Modelle
- Planner-Executor-Ketten

Interessant an diesem Modell ist etwas Spezifischeres:

- nicht-hierarchische Frontdoor-Kooperation
- peer-to-peer semantic arbitration
- Buddy-Schleife statt Chef-Delegation
- ausgelegt auf persoenliche Assistenten und alltaegliche Sprache

Die Innovation liegt also nicht in "zwei Agenten reden", sondern in:

- der Form ihrer Gleichrangigkeit
- dem Konfliktprotokoll
- der Frontdoor-Ausrichtung

## Risiken

Ein Buddy-System ist nicht automatisch besser.

Risiken:

- zu viel Latenz
- Kreisargumentationen
- verdeckte Hierarchie
- beide Modelle teilen dieselben schlechten Muster
- Overengineering bei triviale Faellen

## Guardrails

Deshalb braucht das Modell harte Grenzen:

- maximal 2 Buddy-Runden
- klares Stop-Kriterium
- Rueckfrage frueh statt spaet
- Fast-Path nur bei echter Uebereinstimmung
- Risiko-Guard fuer heikle Faelle
- Beobachtbarkeit aller Konflikte und Overrides

## Metriken

Ob das Modell funktioniert, muss messbar sein.

Wichtige KPIs:

- weniger `dispatcher_meta_fallback: empty_decision`
- weniger Nutzerkorrekturen wie `du verstehst mich nicht`
- bessere Ersttrefferquote bei Follow-ups
- weniger Meta-Rettungen fuer triviale Frontdoor-Faelle
- weniger Fehlrouting in `local_search` / `location_route`
- bessere Konsistenz bei umgangssprachlichen Anfragen

## Minimaler Rollout fuer Timus

### Phase 1

- BuddyHypothesis einfuehren
- Dispatcher gibt bei Unsicherheit strukturierte Vorhypothesen aus
- Meta kann diese lesen und bewerten

### Phase 2

- Arbitration-Regeln einbauen
- `empty_decision` durch `uncertain_buddy_hypothesis` ersetzen

### Phase 3

- BuddyMemory
- gemeinsames Lernen aus Konflikten und spaeteren Korrekturen

### Phase 4

- Frontdoor-Buddy-Optimierung fuer:
  - Umgangssprache
  - Anschlussfragen
  - implizite Referenzen
  - Zustandskorrekturen

## Forschungsthese fuer das Dokument

Eine persoenliche KI braucht an der Frontdoor kein rein hierarchisches Agentensystem, sondern ein gleichrangiges semantisches Buddy-Modell.

Die Kombination aus:

- schneller Erstdeutung
- tiefer Gegenpruefung
- regelbasierter Einigung
- gemeinsamem Lernen

kann robuster fuer alltaegliche Assistenzdialoge sein als ein klassisches Supervisor-Worker-Muster.

## Wichtiger Bewertungsvermerk

Die Buddy-Loop-Architektur ist fuer Timus eine ernsthafte und potenziell neuartige Frontdoor-Hypothese.

Nicht neu sind:

- Multi-Agent-Systeme allgemein
- Supervisor-/Worker-Muster
- Planner-/Executor-Ketten
- Self-Critique- oder Debate-aehnliche Verfahren

Interessant und moeglicherweise eigenstaendig an diesem Ansatz ist die speziell auf persoenliche Assistenzsysteme zugeschnittene Kombination aus:

- nicht-hierarchischer Frontdoor-Kooperation
- zwei gleichrangigen Deutungsagenten
- strukturierter Arbitration statt Chef-Agent
- Fokus auf Umgangssprache, Follow-ups, implizite Referenzen und Nutzerkorrekturen

Wichtig:

- die Architektur ist damit **nicht automatisch bewiesen besser** als die klassische Dispatcher->Meta- oder Supervisor->Worker-Variante
- ob sie in Timus wirklich effizienter, robuster oder nutzerfreundlicher ist, muss empirisch gezeigt werden

Deshalb soll der Buddy Loop nicht als dogmatischer Nachfolger des klassischen Modells behandelt werden, sondern als zu evaluierende Architekturvariante.

Die zentrale Frage ist nicht:

- `ist die Idee interessant?`

sondern:

- `ist sie unter realen Timus-Bedingungen messbar besser als die klassische Frontdoor?`

Dafuer braucht es spaeter einen strukturierten Vergleich mindestens entlang von:

- Fehlklassifikation an der Frontdoor
- `empty_decision`-Rate
- Nutzerkorrekturen
- Konflikt- und Rueckfragequote
- Latenz
- Recovery-Qualitaet bei Unsicherheit

Erst wenn diese Vergleichswerte fuer den Buddy Loop besser oder klar nuetzlicher ausfallen, ist der Ansatz mehr als nur eine interessante Architekturidee.

## Kurzfazit

Der Dispatcher-Meta Buddy Loop ist kein Ersatz fuer das restliche Agentensystem.

Er ist eine Frontdoor-Architektur.

Sein Zweck ist:

- bessere semantische Erstverarbeitung
- weniger leere oder falsche Frontdoor-Entscheidungen
- weniger Nutzerkorrektur
- ein natuerlicheres Assistenzverhalten

Wenn er funktioniert, waere das fuer Timus nicht nur ein Bugfix, sondern ein eigenes Architekturmerkmal.

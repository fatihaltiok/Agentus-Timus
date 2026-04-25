# General Decision Kernel Plan

Stand: 2026-04-25

## Problem

Timus ist nach `MFR`, `MIM` und `MCA` deutlich stabiler, aber die aktuelle
Entscheidungslogik ist noch zu stark von bekannten Fehlerfaellen gepraegt.

Heute gibt es noch zu viele Stellen, an denen die Laufzeit aus konkreten
Problemfamilien heraus reagiert:

- `travel_advisory`
- `setup_build`
- `docs_status`
- `research_advisory`
- einzelne Drift-Guards und Fast Paths

Das war als Härtung richtig, ist aber noch nicht das Endbild fuer eine
allgemein robuste Chat- und Agentenarchitektur.

## Kernhypothese

Die naechste Generalisierung kommt nicht aus mehr Domänen-Sonderlogik, sondern
aus einem **allgemeinen Decision Kernel**, der vor Kontext, Retrieval, Tools
und Delegation nur wenige universelle Fragen beantwortet:

1. Was will der Nutzer in diesem Turn?
2. Wie soll Timus arbeiten?
3. Braucht es Evidenz?
4. Darf Timus ausfuehren?
5. Ist das ein neues Thema oder ein Follow-up?
6. Wie sicher ist die Einordnung?

## Ziel

Zwischen Nutzeranfrage und konkreter Agentenarbeit steht kuenftig eine einzige
autoritative Schicht:

1. `turn_kind`
2. `topic_family`
3. `interaction_mode`
4. `evidence_requirement`
5. `execution_permission`
6. `confidence`
7. `clarify_if_below_threshold`

Domänenspezifische Frames wie `travel_advisory` oder `setup_build` bleiben
moeglich, werden aber zu nachgeordneten Spezialisierungen statt zur ersten
Hauptentscheidung.

## Einordnung in die aktuelle Roadmap

Dieser Block kommt **nach** `MCA`.

Praezise:

- `MFR` hat Frame-Grundlagen gebaut
- `MIM` hat die Arbeitsmodi eingefuehrt
- `MCA` hat Kontextautoritaet geschlossen
- jetzt folgt die **allgemeinere Entscheidungsebene ueber allen drei Bloecken**

Damit ist dieser Plan die Bruecke von:

- drift-resistenter Laufzeit

zu:

- allgemeinerer Anfrageverarbeitung bei neuen, ungesehenen Aufgaben

## Zielbild

Ein neuer Turn wird nicht mehr zuerst durch bekannte Domänen gelesen, sondern
zunaechst durch eine kleine universelle Taxonomie.

Beispiele:

- `Was ist deine Meinung dazu?`
  - `turn_kind = think`
  - `evidence_requirement = none`
  - `execution_permission = forbidden`

- `Schau mal nach, ob es schon Vorbereitungen gibt`
  - `turn_kind = inspect`
  - `evidence_requirement = bounded`
  - `execution_permission = forbidden`

- `Mach dich schlau zu X und hilf mir dann`
  - `turn_kind = research`
  - `evidence_requirement = research`
  - `execution_permission = bounded`

- `Richte das ein`
  - `turn_kind = execute`
  - `evidence_requirement = task_dependent`
  - `execution_permission = allowed`

## Harte Invarianten

### GDK1. General Turn Taxonomy First

Die erste Entscheidung ist eine allgemeine Turn-Typisierung, nicht direkt eine
Spezialdomäne.

### GDK2. Confidence Is Explicit

Jede Entscheidung des Kernels traegt eine explizite Sicherheit. Niedrige
Sicherheit fuehrt nicht zu breiter Delegation.

### GDK3. Context Follows Decision

Kontext darf nur noch nach der Kernel-Entscheidung zugelassen werden.

### GDK4. Low Confidence Must Fail Small

Bei unsicherer Einordnung gilt:

- kleine direkte Antwort
- oder genau eine Rueckfrage
- aber keine breite Tool- oder Agentenkette

### GDK5. Eval Beats Anecdote

Neue Architekturarbeit gilt nur dann als Erfolg, wenn sie auch gegen ungesehene
Faelle stabil bleibt.

## Universelle Turn-Taxonomie

Erste Zielmenge:

- `inform`
- `think`
- `inspect`
- `research`
- `execute`
- `resume`
- `clarify`

Zusatzachse fuer Themenfamilien:

- `technical`
- `document`
- `planning`
- `advisory`
- `personal_productivity`
- `travel`
- `general_knowledge`

Wichtig:

- `topic_family` ist Hilfsstruktur
- `turn_kind` bleibt die primaere Entscheidung

## Umsetzung in Slices

### GDK1. Universal Turn Taxonomy

Ziel:

- allgemeine Turn-Typen einfuehren
- bestehende Spezialdomänen darunter einsortieren

Erfolg:

- neue Anfrageformulierung wird erst ueber `turn_kind` gelesen

### GDK2. Decision Kernel Contract

Ziel:

- eigener kanonischer Vertrag fuer:
  - `turn_kind`
  - `topic_family`
  - `interaction_mode`
  - `evidence_requirement`
  - `execution_permission`
  - `confidence`
  - `clarify_if_below_threshold`

Erfolg:

- eine autoritative Entscheidungsschicht vor Frame, Kontext und Tooling

### GDK3. Runtime Alignment

Ziel:

- `meta_request_frame`, `interaction_mode`, `context_authority` und
  Tool-Freigaben werden aus dem Kernel abgeleitet

Erfolg:

- weniger konkurrierende Entscheidungen in spaeteren Schichten

### GDK4. Low-Confidence Controller

Ziel:

- unsichere Einordnung fuehrt zu kleinen, kontrollierten Pfaden

Erfolg:

- weniger falsche Recherche
- weniger falsche Ausfuehrung
- weniger Cross-Domain-Drift

### GDK5. Unseen Eval Matrix

Pflichtfaelle:

- `Plane meinen Tag`
- `Was ist deine Meinung dazu?`
- `Hilf mir bei einer Entscheidung`
- `Mach dich schlau ueber Thema X`
- `Pruef das kurz`
- `Lies die Doku und sag was als naechstes ansteht`
- `Wo kann ich am Wochenende hin in Deutschland`
- `Und was bedeutet das fuer mich?`

Erfolg:

- Generalisierung wird gegen neue Faelle gemessen, nicht nur gegen bekannte
  Fehlchats

### GDK6. Telemetrie fuer Entscheidungsgruende

Ziel:

- pro Turn sichtbar machen:
  - warum `turn_kind`
  - warum `topic_family`
  - warum Evidenz ja/nein
  - warum Delegation ja/nein

Erfolg:

- Debugging wird wieder ursachenbezogen statt symptomatisch

## Erste Umsetzungsschritte

1. `GDK1` als reine Taxonomie und Mapping-Lage bauen
2. `GDK2` als eigenen Vertrag einfuehren
3. erst dann `GDK3` auf bestehende MFR/MIM/MCA-Pfade verdrahten
4. parallel `GDK5` als Eval-Matrix starten

## Abbruchkriterium fuer schlechte Architektur

Wenn ein neuer Kernel-Entwurf nur wieder neue Fallregeln erzeugt wie:

- `if travel`
- `if setup`
- `if docs`

dann ist er zu niedrig abstrahiert und kein echter Generalisierungsschritt.

## Erfolgskriterium

Der Block ist erst dann geschlossen, wenn neue Anfragen nicht mehr nur deshalb
gut laufen, weil wir ihre letzte Fehlerfamilie schon kennen, sondern weil die
erste Entscheidung allgemeiner und stabiler geworden ist.

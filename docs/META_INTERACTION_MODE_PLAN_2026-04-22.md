# Meta Interaction Mode Plan

Stand: 2026-04-22

## Ziel

Timus soll weiter ueber natuerliche Sprache bedient werden, intern aber sauber zwischen drei Arbeitsweisen unterscheiden:

- `think_partner`
- `inspect`
- `assist`

Diese Modi sind kein sichtbarer Zwang fuer den Nutzer. Sie sind ein interner Vertrag, der bestimmt:
- ob Timus denken, pruefen oder handeln soll
- wie viel Evidenz erlaubt ist
- ob Delegation ueberhaupt erlaubt ist
- welche Antwortform erwartet wird

## Kernprinzip

Zwei getrennte Achsen:

1. `task_domain`
- worum geht es fachlich

2. `interaction_mode`
- wie soll Timus in diesem Turn arbeiten

Beides muss zusammen ausgewertet werden. Dasselbe Thema kann je nach Modus anders behandelt werden.

## Modi

### 1. Think Partner

Ziel:
- mit dem Nutzer denken
- Optionen und Argumente sortieren
- keine ungefragte Recherche oder Ausfuehrung

### 2. Inspect

Ziel:
- begrenzt nachsehen, pruefen, lesen, verifizieren
- danach direkt berichten
- keine ungefragte Umsetzung

### 3. Assist

Ziel:
- planen, delegieren, konkrete Artefakte oder Ausfuehrung liefern

## Slice-Reihenfolge

### MIM1 Contract

- internen `meta_interaction_mode` einfuehren
- Inferenz aus Query, Frame und Policy
- Handoff bis in die Runtime tragen

### MIM2 Clarity Binding

- Klarheitsvertrag nach Modus haerten
- `think_partner` blockiert Recherche/Ausfuehrung
- `inspect` begrenzt Evidenzpfade

### MIM3 Prompt Binding

- Meta-Prompt soll Modus explizit sehen
- Modi duerfen nicht nur klassifiziert, sondern muessen auch befolgt werden

### MIM4 Live Gates

Pflichtfaelle:
- `Was ist deine Meinung dazu?`
- `Schau mal nach, ob es schon Vorbereitungen gibt`
- `Richte das ein`
- `Plane meinen Tag`

## Aktueller Stand

Stand nach erstem Runtime-Slice:

- `assist` ist live bereits tragbar
  - `Plane meinen Tag` liefert einen brauchbaren Plan
- `think_partner` ist noch nicht live gehärtet
  - der Modus kann noch auf `research` kippen
- `inspect` ist noch nicht live stabil
  - der Run haengt noch im ersten `meta`-Schritt

Das bedeutet:
- die technische Verdrahtung ist da
- die Test-Suite ist grün
- aber der Plan ist live noch nicht geschlossen

## Nachhaltiger Closeout-Plan

Die offenen Baustellen werden nicht ueber neue Textheuristiken geloest, sondern ueber Runtime-Invarianten an den wenigen Choke Points:

1. vor Tool-/Delegationsschritten
2. vor dem ersten Evidenzpfad
3. vor finaler Antwortauslieferung

### MIM5 Think-Partner Enforcement

Ziel:
- `think_partner` muss intern wirklich `no_research_no_execution` bedeuten

Pflichtinvarianten:
- keine Delegation
- keine Recherche
- keine Toolkette
- keine Skill-/Research-Vorschlagsantwort
- nur direkte Antwort oder genau eine echte Rueckfrage bei materieller Unklarheit

Implementierung:
- harter Runtime-Guard vor jedem Tool-/Delegate-Call
- Meta-Prompt fuer `think_partner` ohne Research-/Skill-Aktionsraum
- off-policy Toolversuche werden nicht nur markiert, sondern in direkte Antwort umgelenkt
- Final-Answer-Guard prueft, dass die Antwort wirklich denkend/einordnend bleibt

Erfolgskriterium:
- `Ohne Recherche: Was ist deine Meinung dazu ...`
  - bleibt in `meta`
  - startet keinen Spezialisten
  - liefert eine direkte, reflektierende Antwort

### MIM6 Inspect Fast Path

Ziel:
- `inspect` soll nicht mehr durch offenen Meta-Reasoning-Lauf gehen
- stattdessen ein deterministischer kleiner Evidenzpfad

Pflichtinvarianten:
- maximal ein begrenzter Evidenzschritt
- keine freie Agentenkette
- keine Ausfuehrung
- danach sofort Abschlussbericht

Implementierung:
- `inspect` bekommt einen Fast Path:
  - Modus erkannt
  - passender Evidenzagent direkt bestimmt
  - genau ein Evidence Fetch
  - harter Abschlussbericht
- fuer `setup_build_preparation_check`:
  - strukturierten Probe-/Dokumentpfad statt offenem Meta-Denken
- Abschlussformat fuer `inspect`:
  - `Vorhanden`
  - `Fehlt`
  - `Unklar`
  - `Naechster sinnvoller Schritt`

Erfolgskriterium:
- `Schau mal nach, ob es schon Vorbereitungen gibt, aber nichts umsetzen`
  - haengt nicht
  - plant nicht breit
  - liefert bounded Findings

### MIM7 Live Gates und Unseen Eval

Ziel:
- nicht nur bekannte Regressionen gruen halten
- sondern generelle Interaktionsstabilitaet absichern

Pflicht-Live-Gates:
- `think_partner`
  - `Ohne Recherche: Was ist deine Meinung dazu ...`
- `inspect`
  - `Schau mal nach, ob es schon Vorbereitungen gibt, aber nichts umsetzen`
- `assist`
  - `Richte das jetzt ein`
- `planning_advisory`
  - `Plane meinen Tag`
- `research_advisory`
  - `Mach dich schlau ueber X und steh mir dann hilfreich zur Seite`

Pflicht-Eval-Felder je Fall:
- korrekter `task_domain`
- korrekter `interaction_mode`
- korrekter erster Runtime-Schritt
- erlaubte vs. verbotene Delegation
- Abschlussform passend zum Modus

Neue Aufgaben fuer Unseen-Generalisation:
- `Hilf mir das zu durchdenken, aber recherchiere nicht`
- `Pruef kurz, ob wir dafuer schon etwas im Repo haben`
- `Mach dich schlau ueber Kreislaufwirtschaft im Bauwesen und hilf mir danach`
- `Wie ist dein Zustand, hast du gerade Probleme mich zu verstehen`

## Umsetzungsreihenfolge

1. `MIM5 Think-Partner Enforcement`
- zuerst, weil dieser Fall aktuell den eigenen Vertrag am haertesten bricht

2. `MIM6 Inspect Fast Path`
- danach, weil `inspect` noch im offenen Meta-Loop haengt

3. `MIM7 Live Gates und Unseen Eval`
- erst wenn die beiden Runtime-Pfade belastbar sind

## Architekturgrenze

Nicht tun:
- noch mehr lose Query-Heuristiken
- weitere ad-hoc Prompt-Texte fuer Einzelfaelle
- Modusentscheidungen spaeter wieder von Memory oder Salvage ueberschreiben lassen

Tun:
- Modus als harte Runtime-Disziplin behandeln
- Frame bleibt fachlich autoritativ
- Interaktionsmodus bleibt verhaltensseitig autoritativ
- beides wird an Runtime und Final Answer durchgesetzt

## Erfolgskriterium

Natuerliche Sprache bleibt die Hauptschnittstelle.

Der Nutzer muss keinen Modus setzen, kann ihn aber bei Bedarf ueberschreiben:
- `ohne Recherche`
- `nur pruefen`
- `jetzt umsetzen`

Der Modus soll also intern sichtbar und hart wirksam sein, aber nach aussen moeglichst unsichtbar bleiben.

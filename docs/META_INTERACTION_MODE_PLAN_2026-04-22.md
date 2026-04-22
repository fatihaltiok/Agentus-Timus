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

## Erfolgskriterium

Natuerliche Sprache bleibt die Hauptschnittstelle.

Der Nutzer muss keinen Modus setzen, kann ihn aber bei Bedarf ueberschreiben:
- `ohne Recherche`
- `nur pruefen`
- `jetzt umsetzen`

Der Modus soll also intern sichtbar und hart wirksam sein, aber nach aussen moeglichst unsichtbar bleiben.

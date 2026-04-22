# Meta-Kontextfaehigkeit: Zentrale Erkenntnis

Stand: 2026-04-21

## Kernerkenntnis

Einen Agenten zu bauen, der einen Benutzer sofort richtig versteht, kontextfaehig bleibt und mehrschichtige Auftraege sauber beendet, ist kein Detailproblem und kein einzelner Prompt-Fix.

Der schwierige Teil ist nicht:
- ein Modell antworten zu lassen
- oder einen Agenten Tools aufrufen zu lassen

Der schwierige Teil ist:
- den richtigen Frame sofort zu setzen
- nur den passenden Kontext zuzulassen
- zwischen Antwort, Planung und Ausfuehrung sauber zu unterscheiden
- den Turn ohne Drift zu Ende zu bringen

## Warum das schwierig ist

### 1. Kontext ist nicht einfach mehr Historie

Kontext bedeutet nicht, moeglichst viel Text mitzuschleppen.

Kontext bedeutet:
- welcher Teil der Historie ist fuer genau diesen Turn kausal relevant
- welcher Teil ist nur Rauschen
- welcher Teil darf die aktuelle Deutung niemals ueberschreiben

### 2. Sofort verstehen heisst nicht raten

Ein guter Agent muss oft schnell die wahrscheinlichste Lesart bilden.

Aber:
- er darf dabei nicht halluzinieren
- er darf nicht auf einen falschen Attraktor kippen
- er darf Ambiguitaet nicht mit Beliebigkeit verwechseln

### 3. Mehrschrittigkeit vervielfacht Driftpunkte

Sobald Planung, Delegation, Spezialisten, Memory und Follow-ups dazukommen, entsteht nicht ein Fehlerpunkt, sondern viele:
- Frame
- Memory
- Policy
- Plan
- Delegation
- Final Answer

Wenn diese Schichten nicht dieselbe Deutung tragen, verschiebt sich der Fehler nur von einer Stelle zur naechsten.

### 4. Lokale Fixes reichen nicht

Wenn man nur einzelne Symptome repariert, entsteht leicht dieses Muster:
- Fehler A wird kleiner
- danach gewinnt Fehler B
- danach kippt der gleiche Turn an Stelle C

Das bedeutet:
- nicht genug Invarianten
- zu viele konkurrierende Entscheidungsschichten
- keine harte Single Source of Truth fuer den Turn

## Konsequenz fuer Timus

Timus darf nicht ueber viele lose Heuristiken "ungefaehr" verstehen.

Timus braucht harte Invarianten:
- Frame zuerst
- Context Admission nach Frame
- Delegationsbudget nach Request-Kind
- Final-Answer-Guard gegen Frame-Drift
- Eval-Suite mit echten und neuen Aufgaben, nicht nur mit bekannten Regressionen

## Praktische Einordnung

Bei `setup_build` hat sich gezeigt:
- Timus versteht die grobe Absicht inzwischen deutlich besser
- der grobe Drift auf `skill-creator`, Standort oder falsche Skills ist stark reduziert
- die verbleibenden Probleme sitzen jetzt enger bei Evidenzgewichtung, sauberen Blockern und Abschlussqualitaet

Das ist wichtig:
- `funktioniert manchmal` ist nicht genug
- `ist wirklich kontextfaehig` bedeutet, dass die gleiche innere Deutung den gesamten Turn traegt

## Leitlinie fuer die Zukunft

Wenn Timus bei einer neuen Aufgabe wieder auseinanderfaellt, darf die Reaktion nicht zuerst sein:
- noch ein Spezialfall
- noch ein Heuristik-Patch
- noch ein Prompt-Hinweis

Die erste Frage muss sein:
- Welche Invariante fehlt?

Und danach:
- Frame
- Context Admission
- Delegation
- Abschluss

an genau dieser Invariante haerten.

## Zielbild

Ein wirklich guter Orchestrator:
- versteht nicht durch Masse an Kontext
- sondern durch Klarheit
- benutzt Erinnerung als Hilfe, nicht als Steuerung
- und beendet einen Turn nur dann, wenn die Pflichtantwort im richtigen Frame wirklich geliefert wurde

Das ist der Kern von echter Kontextfaehigkeit.

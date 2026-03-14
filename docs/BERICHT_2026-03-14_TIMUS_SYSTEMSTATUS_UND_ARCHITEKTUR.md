# Bericht: Timus Systemstatus und Architektur

Stand: 14.03.2026

## Executive Summary

Timus ist heute kein einzelner Chatbot mehr, sondern ein selbstgehostetes Multi-Agenten-System mit Dispatcher, Meta-Orchestrierung, spezialisiertem Tool-Stack, mehreren Memory-Schichten, Runtime-Gates, Self-Healing und einer kontrollierten Self-Modification-Pipeline. Das System ist in den letzten Tagen in mehreren zentralen Bereichen deutlich reifer geworden: Meta-Orchestrierung, Android-App, Voice, Standortkontext, konversationeller Recall, Qdrant-Nutzung und der produktive Memory-Hauptpfad wurden erweitert oder gehartet.

Die Architektur ist heute in vier Nutzungsmodi relevant:

1. Browser- und Console-Nutzung ueber den MCP-Server und die Canvas-/Mobile-Console
2. Telegram- und Dispatcher-basierte Assistenz
3. Android-App mit Voice, GPS, Operator-Access und Server-Synchronisierung
4. Autonomer Hintergrundbetrieb mit Gates, Stabilisierung, Reflexion und Self-Improvement

Technisch ist Timus produktionsnah, aber nicht vollstaendig "fertig". Die Starken liegen heute in Orchestrierung, Toolvielfalt, Replaning, Research, Dokumenten-Workflows und der Kombination aus Bedienoberflaeche, Runtime-Kontrolle und Gedachtnis. Die groessten Restthemen liegen in Vollstaendigkeit des Kontextverstehens ueber lange Dialoge, Recall-Qualitaet, mobile Bedienhaptik und der weiteren Haertung einzelner Tool- und Modellpfade.

## Gesamtbild

Timus besteht im Kern aus folgenden Schichten:

- Zugangsschicht: Browser, Telegram, Android, Terminal
- MCP-/API-Schicht: FastAPI-Server mit Tool- und Chat-Endpunkten
- Dispatcher-Schicht: erste Routing-Entscheidung und Fast-Paths
- Agentenschicht: 13 spezialisierte Agenten plus Meta-Orchestrierung
- Toolschicht: 80+ Tools fuer Search, Browser, Vision, Files, Voice, Research, Memory, Shell und mehr
- Memory-/Kontextschicht: Session-Historie, Capsule-Memory, Qdrant-Recall, Persistent Memory, Blackboard
- Runtime-/Autonomie-Schicht: Self-Healing, Scorecards, Produktion-Gates, Feedback, Self-Improvement
- Self-Modification-Schicht: Policy, Risk, isolierte Patch-Pipeline, Verification, Canary, Change Memory, Autonomous Apply

Damit ist Timus heute am ehesten eine Mischung aus:

- persoenlichem Operator
- Research- und Dokumentenmaschine
- Runtime-kontrolliertem Agenten-System
- selbstgehosteter Assistentenplattform

## Wichtige Architekturverbesserungen des aktuellen Stands

### 1. Meta-Orchestrierung

Meta ist nicht mehr nur ein grober Dispatcher, sondern ein echter Orchestrator mit Rezepten, Handoffs, Recovery und Replaning. Zu den wichtigsten Erweiterungen gehoeren:

- strukturierte Agenten-Handoffs
- Outcome-Lernen fuer Rezeptwahl
- Alternativrezepte nach Fehlern
- `lightweight first`
- fehlergesteuerte Strategieanpassung
- selbstgewahlte Toolstrategien fuer leichte und schwere Aufgaben

Wichtig ist dabei vor allem die Richtung: Timus soll nicht fuer jede Anfrage hart verdrahtete Regeln brauchen, sondern mit minimalen Guardrails selbst waehlen koennen, welche Agenten und Tools fuer die Aufgabe am besten passen.

### 2. Self-Modification SM1-SM7

Timus besitzt inzwischen eine echte Level-2-Self-Modification-Pipeline. Das heisst nicht, dass er sich beliebig frei umbauen darf. Es heisst, dass er kontrolliert, verifiziert und in engen Zonen selbststaendig aendern kann.

Der Stack umfasst:

- SM1 Change Policy
- SM2 Risk Classifier
- SM3 isolierte Patch-Pipeline
- SM4 Hard Verification Gate
- SM5 Canary und Rollback
- SM6 Change Memory
- SM7 Autonomous Apply Controller

Das ist ein wesentlicher Unterschied zu einfachen "Self-Improvement"-Claims anderer Agentensysteme. Timus hat hier nicht nur Prompts, sondern eine Pipeline mit technischen Gates.

### 3. Android-App

Die Android-App ist funktional deutlich weiter als noch vor wenigen Tagen. Zu den relevanten Punkten gehoeren:

- Auto-Login
- Voice-Modus mit Auto-Start des Zuhorens
- Transkriptionsmodus fuer laengere Eingaben
- GPS-Standortabruf ueber Android Location Services
- Reverse-Geocoding und Server-Synchronisierung
- Android-Operator-Grundlage ueber AccessibilityService

Das bedeutet: Timus kann auf dem Handy inzwischen nicht nur chatten, sondern auch Sprache, Standort und Geraetekontext nutzen.

### 4. Standort und lokale Suche

Der Standortpfad ist nicht mehr nur theoretisch, sondern praktisch verknuepft:

- Android holt `lat/lon`
- Server speichert und normalisiert den letzten Standort
- lokale Suche nutzt den mobilen Standort
- SerpApi Google Maps ist eingebunden

Dadurch kann Timus Aufgaben wie "wo bin ich gerade?" oder "was ist in meiner Naehe offen?" grundsaetzlich beantworten. Das ist ein klarer Schritt weg vom reinen Chat- und Websystem hin zu einem kontextsensitiven Assistenten.

### 5. Konversationeller Recall

Timus hatte bei Folgefragen bisher ein strukturelles Problem: knappe Anschlussfragen wie "und was jetzt?" oder "sag du es mir" wurden oft neu und falsch klassifiziert. Das fuehrte zu falschem Agentenrouting und teilweise sogar zu instabilen Pfaden.

Hier wurden mehrere Dinge verbessert:

- Follow-up Resolver
- Session-Capsules
- persistente Capsule-Zusammenfassungen
- Qdrant-basierter semantischer Chat-Recall
- deterministische Recall-Antworten fuer einfache Rueckfragen

Wichtig ist die ehrliche Einordnung:

- Stufe 1 und 2 fuer laengere Gespraeche sind jetzt da
- die Recall-Qualitaet ist besser
- aber das Ranking ist noch nicht perfekt

### 6. Memory-Hardening

Ein zentraler Stabilitaetsgewinn ist der juengste Memory-Block. Das Problem war ein nativer Segmentation Fault im Chroma-Pfad, der ueber Working-Memory und semantische Suche in produktionsnahe Tests und potenziell spaeter auch in Live-Pfade hineinreichte.

Die Loesung:

- produktiver Default nicht mehr stillschweigend Chroma
- Standard jetzt: Qdrant oder FTS5-only
- Chroma nur noch explizit als Legacy-/Debug-Backend
- kein stiller Fallback von Qdrant auf Chroma
- formale Absicherung mit Hypothesis und CrossHair

Das ist nicht nur ein technisches Detail, sondern reduziert eine echte Absturzklasse im Hauptpfad.

## Aktuelle Staerken

Die wichtigsten Staerken von Timus sind aktuell:

- starke Orchestrierungslogik fuer mehrstufige Aufgaben
- breite Toolabdeckung
- tiefe Research- und Dokumentenfaehigkeit
- Runtime-Kontrolle ueber Gates, Scorecards und Stabilisierung
- Android-/Voice-/Location-Integration
- echtes, kontrolliertes Self-Modification-Programm
- gute Grundlage fuer laengere, kontextreiche Zusammenarbeit

Aus Produktsicht ist besonders stark, dass Timus nicht nur "antwortet", sondern:

- sucht
- plant
- umplant
- schreibt
- dokumentiert
- verifiziert
- und sich teilweise selbst verbessert

## Offene Risiken und Restpunkte

Trotz des Fortschritts ist Timus noch nicht durchgehend auf Endzustand:

- Meta versteht Folgefragen deutlich besser als vorher, aber noch nicht perfekt
- semantischer Recall ist vorhanden, aber noch nicht optimal gerankt
- Android-Operator ist als Zugriffskern vorhanden, aber noch kein kompletter Device-Operator
- einige Modell- und Toolpfade muessen weiter gehaertet werden
- alte Artefakte und offene lokale Nebenpfade existieren noch im Worktree

Wichtig ist: Das sind keine fundamentalen Architekturprobleme mehr, sondern Reife- und Haertungsthemen.

## Einordnung des Reifegrads

Wenn man Timus grob einordnet, ergibt sich aktuell dieses Bild:

- Architektur: hoch entwickelt
- Funktionsbreite: sehr hoch
- lokale Anpassbarkeit: sehr hoch
- Produktreife: gut, aber noch nicht vollstaendig glatt
- Langzeitstabilitaet: deutlich besser als zuvor, aber weiter in Arbeit

Timus ist damit weder ein einfacher Prototyp noch schon ein glatt poliertes Massenprodukt. Er ist eher eine fortgeschrittene, persoenliche Operator-Plattform mit ernstzunehmender Architektur und wachsender Betriebsreife.

## Naechste sinnvolle Richtung

Die naechsten grossen Hebel sind:

1. Recall-Qualitaet weiter messen und verbessern
2. noch bessere Follow-up-Aufloesung und Themenstrang-Tracking
3. Android-Operator von Beobachtung zu echten gesteuerten Aktionen ausbauen
4. mobile Voice- und UI-Haptik weiter haerten
5. semantische und langfristige Gedachtnispfade weiter konsolidieren

## Schluss

Timus steht heute auf einer deutlich staerkeren Basis als noch vor wenigen Tagen. Besonders wichtig ist, dass nicht nur neue Features hinzugekommen sind, sondern zentrale Schwachstellen in Routing, Kontextfortsetzung und Memory-Stabilitaet systematisch bearbeitet wurden.

Der aktuelle Zustand ist deshalb nicht einfach "mehr Funktionen", sondern eine echte Architekturverdichtung:

- bessere Orchestrierung
- bessere Kontextfuehrung
- bessere mobile Nutzbarkeit
- besseres Memory-Fundament
- und eine glaubwuerdigere Richtung hin zu einem langfristig arbeitsfaehigen persoenlichen Operator

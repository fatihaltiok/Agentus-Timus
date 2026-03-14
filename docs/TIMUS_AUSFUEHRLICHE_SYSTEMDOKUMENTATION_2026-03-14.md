# Timus: Ausfuehrliche Systemdokumentation

Stand: 14.03.2026

## 1. Zweck dieses Dokuments

Dieses Dokument ist die ausfuehrliche technische und konzeptionelle Beschreibung von Timus. Es soll nicht nur in ein paar Saetzen sagen, was Timus ist, sondern nachvollziehbar machen, wie das System aufgebaut ist, welche Schichten es besitzt, welche Aufgaben es heute bereits uebernehmen kann, wo seine Grenzen liegen und warum Timus architektonisch mehr ist als ein normaler Chatbot oder ein einfacher Agenten-Wrapper.

Die Dokumentation verfolgt vier Ziele:

1. Timus inhaltlich und technisch beschreibbar machen
2. die Architektur in ihren Hauptschichten klar erklaeren
3. die juengsten Ausbaustufen dokumentieren
4. eine ehrliche Einordnung von Staerken, Risiken und naechsten Schritten geben

Wenn du Timus nach aussen erklaeren willst, ist die Kurzfassung:

Timus ist ein selbstgehostetes, mehrschichtiges Multi-Agenten-System mit Gedachtnis, Orchestrierung, Browser- und Dokumentenfaehigkeiten, Voice, mobiler App, Runtime-Governance und kontrollierter Selbstmodifikation. Es ist als persoenlicher Operator gedacht, nicht als einzelner Chatbot.

Die Langfassung steht in diesem Dokument.

## 2. Was Timus ist

Timus ist im Kern ein Betriebssystem fuer agentische Arbeit. Der Begriff "Betriebssystem" ist hier nicht metaphorisch gemeint, sondern architektonisch. Timus besitzt eine Eingangsschicht, Routing und Orchestrierung, spezialisierte Agenten, einen gemeinsamen Toolraum, mehrere Gedachtnisformen, Telemetrie, Stabilitaetsmechanismen und eine eigene Logik zur kontrollierten Weiterentwicklung. Das entspricht eher einer Plattform als einer einzelnen Anwendung.

Timus ist gleichzeitig:

- persoenlicher Assistent
- Operator fuer Web, Recherche, Dokumente und Systemaufgaben
- orchestrierendes Multi-Agenten-System
- mobile App mit Sprache, Standort und Geraetekontext
- Runtime-kontrollierte Assistenzplattform
- lernendes und teilweise selbstmodifizierendes System

Timus ist ausdruecklich nicht nur:

- ein Prompt auf einem Modell
- ein Browser-Bot
- ein LLM-Wrapper
- ein Chat-Frontend
- eine lose Sammlung von Skripten

Der entscheidende Punkt ist, dass Timus nicht nur antwortet, sondern Aufgaben in Schichten zerlegt, Agenten waehlt, Tools benutzt, Ergebnisse verifiziert, Fehler auswertet, bei Bedarf replanned und wichtige Informationen ueber Zeit speichert.

## 3. Leitidee und Designphilosophie

Die Leitidee von Timus ist: Ein Assistent muss nicht nur sprachlich stark sein, sondern operativ belastbar. In der Praxis bedeutet das:

- ein gutes System braucht nicht nur ein Modell, sondern Werkzeuge
- Werkzeuge allein reichen nicht, wenn Orchestrierung fehlt
- Orchestrierung reicht nicht, wenn kein Gedachtnis und keine Fehlerbehandlung existieren
- Gedachtnis reicht nicht, wenn Laufzeitstabilitaet fehlt
- Stabilitaet reicht nicht, wenn das System nicht lernt und sich nicht anpassen kann

Deshalb besteht Timus aus mehreren Ebenen, die aufeinander aufbauen:

1. Interaktion
2. Routing
3. Orchestrierung
4. Spezialisierte Ausfuehrung
5. Kontext und Memory
6. Runtime-Governance
7. Learning und kontrollierte Selbstveraenderung

Diese Architektur ist absichtlich umfassender als bei einfachen Agentensystemen. Das Ziel von Timus ist nicht, in einer Demo gut auszusehen, sondern im Alltag ueber laengere Zeit benutzbar zu sein.

## 4. Systemueberblick

Ein typischer Task fliesst heute in etwa so durch Timus:

1. Eine Anfrage kommt ueber Browser, Telegram, Terminal oder Android-App an.
2. Der MCP-Server oder der Dispatcher nimmt die Anfrage entgegen.
3. Der Dispatcher trifft eine erste Routing-Entscheidung.
4. Ein einfacher Fall geht direkt an einen Spezialagenten oder an den Executor.
5. Ein komplexer Fall geht an den Meta-Agenten.
6. Meta plant den Ablauf, waehlt eine Strategie, delegiert an Spezialisten und fuehrt Ergebnisse wieder zusammen.
7. Tools, Memory, Blackboard und Laufzeitstatus beeinflussen die weiteren Schritte.
8. Wenn Fehler auftreten, versucht Timus zu replannen, zu degradieren oder sauber zu eskalieren.
9. Relevante Teile des Verlaufs werden in Session-Capsules, Qdrant-Recall, Persistent Memory und Telemetrie geschrieben.

Das System hat damit keinen linearen "Prompt rein, Antwort raus"-Pfad, sondern einen arbeitsfaehigen Kontrollkreislauf.

## 5. Zugangsschichten und Kanaele

### Browser und Console

Timus laeuft ueber den MCP-Server mit FastAPI und bietet eine Canvas-/Console-Oberflaeche, die heute auch ueber HTTPS und mobile Geraete erreichbar ist. Darueber sind Chat, Status, Dateien, Voice und weitere Oberflaechen erreichbar.

### Telegram

Telegram ist ein wichtiger leichter Bedienkanal fuer Statusabfragen, Routineaufgaben, Benachrichtigungen und Rueckkopplung aus der Autonomie. Timus kann dort nicht nur antworten, sondern auch aktive Meldungen senden.

### Terminal

Der Terminal- bzw. CLI-Pfad ist wichtig fuer Entwicklung, Diagnose und direkten Operator-Betrieb. Gerade in der Entwicklungsphase ist das oft der schnellste Weg, um konkrete Systemzustaende oder Toolpfade zu pruefen.

### Android-App

Die Android-App ist kein bloesser Viewer, sondern ein zunehmend eigenstaendiger Client. Aktuell relevant sind:

- Login und Auto-Login
- Chat
- Voice-Modus
- Standortabruf und Anzeige
- Android Operator Access ueber Accessibility

Diese App ist besonders wichtig, weil Timus dadurch vom stationaeren Browser-System zu einem mobilen persoenlichen Operator wird.

## 6. Der MCP-Server als technischer Kern

Der MCP-Server ist eine der zentralen Schichten im System. Er sitzt in `server/mcp_server.py` und stellt den technischen Werkzeugraum sowie mehrere REST- und Chat-Endpunkte bereit.

Seine Aufgaben sind unter anderem:

- Tool-Registry und Toolausfuehrung
- JSON-RPC- und API-Endpunkte
- Health- und Statusendpunkte
- Chatannahme fuer Browser und App
- Datei- und Voice-Endpunkte
- Verwaltung von Laufzeitstatus und Shared Clients
- Session-basierte Follow-up-Capsules
- semantischer Chat-Recall ueber Qdrant
- Standort- und Nearby-Endpunkte fuer mobile Nutzung

Wichtig ist, dass der MCP-Server nicht "die Intelligenz" ist. Er ist das operative Rueckgrat. Er macht Werkzeuge nutzbar, haelt Zustandsknoten zusammen und stellt die technische Infrastruktur fuer den Rest bereit.

## 7. Dispatcher-Schicht

Der Dispatcher sitzt in `main_dispatcher.py`. Seine Aufgabe ist die erste, schnelle Einordnung von Anfragen. Das ist bewusst nicht dieselbe Rolle wie Meta-Orchestrierung.

Der Dispatcher soll vor allem:

- triviale und bekannte Faelle schnell routen
- Spezialagenten frueh erkennen
- Follow-up-Fast-Paths bereitstellen
- unklare Faelle an Meta uebergeben

Der Dispatcher ist also die erste Sortierschicht. Er verhindert, dass jede einzelne Anfrage sofort in einen grossen, teuren Orchestrierungsmodus faellt.

In den letzten Ausbauschritten wurde der Dispatcher besonders fuer kurze Folgefragen verbessert. Fragen wie:

- "und was jetzt"
- "sag du es mir"
- "und was kannst du dagegen tun"

werden dadurch nicht mehr so leicht falsch an Meta oder sogar an Visual umgeleitet, sondern bleiben in der gleichen "lane", wenn der Kontext das nahelegt.

## 8. Die Agentenschicht

Timus arbeitet nicht mit einem generischen Agenten, sondern mit mehreren Spezialisierungen. Das ist ein zentrales Architekturprinzip. Jeder Agent hat andere Rollen, andere Tools und oft auch andere Modelle.

Zu den wichtigsten Agenten gehoeren:

### Executor

Der Executor ist der schnelle, operative Allrounder fuer leichte Faelle. Gerade einfache Konversation, leichte Suchaufgaben, Selbststatus, kleine Rueckfragen und deterministische Toolpfade sollten hier landen. Der Executor ist heute absichtlich staerker "tool-first" und "deterministic-first" ausgelegt als frueher, damit triviale Faelle nicht unnoetig in fragile Modellpfade rutschen.

### Meta

Meta ist der Orchestrator. Dieser Agent ist einer der wichtigsten Unterschiede zwischen Timus und einfachen Agenten-Setups. Meta plant, waehlt Strategien, delegiert, liest strukturierte Ergebnisse, erkennt Fehlerarten, replanned und fuehrt mehrstufige Aufgaben zusammen. Meta soll komplexe Aufgaben nicht selbst "hinfantasieren", sondern an die richtigen Spezialisten verteilen.

### Deep Research

Der Research-Agent ist fuer evidenzbasierte Recherche, Quellenkorroboration, Berichtserstellung und Deep-Research-Workflows zustaendig. Dieser Bereich wurde stark ausgebaut und liefert nicht nur lose Suchtreffer, sondern strukturierte Forschungsberichte, Claims, Evidence und narrative Ausgabeformate.

### Visual

Visual ist der Agent fuer Browser- und UI-Aufgaben. Er soll Formulare, Datepicker, Suchfelder, Oberflaechenzustand und andere visuelle bzw. interaktive Aufgaben bearbeiten. Ein wichtiger Punkt der juengsten Haertung war, dass Visual nicht mehr als generischer Fallback fuer unklare Textfragen missbraucht werden soll.

### Developer

Developer uebernimmt Code- und Entwicklungsaufgaben, generiert oder aendert Code, bezieht Tests ein und arbeitet in die kontrollierte Entwicklungs- und Selbstmodifikationsschicht hinein.

### System und Shell

System ist fuer Diagnose, Status und Logs da. Shell ist der kommandobasierte Pfad mit Sicherheits- und Policy-Schicht. Diese Trennung ist wichtig, weil lesen, bewerten und diagnostizieren etwas anderes ist als aktiv Befehle auszufuehren.

### Communication, Document, Data, Creative, Image

Diese Agenten decken Kommunikationsaufgaben, Dokumentenerstellung, Datenanalyse, kreative Medienerzeugung und Bildanalyse ab. Zusammen machen sie Timus zu einem Arbeitsassistenten und nicht nur zu einem reinen Chat- oder Browser-System.

## 9. Toolarchitektur

Die Toolschicht ist einer der groessten Hebel von Timus. Der Nutzen eines Agentensystems steht und faellt nicht nur mit seinen Modellen, sondern mit seinen moeglichen Aktionen.

Timus besitzt mehr als 80 Tools fuer unter anderem:

- Web- und Browserinteraktion
- Search und Recherche
- Deep Research
- Files und Dokumente
- Voice
- System- und Shell-Aufgaben
- Speicher und Memory
- Visualisierung, OCR und Vision
- Selbstverbesserung und Auswertung

Ein wichtiges Architekturprinzip ist: Nicht jeder Agent soll jedes Tool direkt nutzen. Stattdessen gibt es Spezialisierung, Policies und Faehigkeitszuordnungen. Das verhindert zumindest teilweise, dass ein Agent aus Unsicherheit unpassende Tools benutzt.

In den letzten Tagen wurden genau auf dieser Ebene mehrere Probleme behoben:

- leichte YouTube-Anfragen gehen ueber leichte Search-Pfade statt direkt in schwere Research-Loops
- lokale Standortsuche nutzt den mobilen Standort plus Maps-Kontext
- triviale Executor-Faelle werden deterministisch beantwortet
- Meta wird bei Screen-/OCR-Themen haerter auf Visual verwiesen, aber nicht bei vagen Anschlussfragen

## 10. Meta-Orchestrierung im Detail

Meta ist heute eine der komplexesten Schichten in Timus. Die juengsten Ausbaustufen waren hier besonders wichtig:

- Rezeptbasierte Orchestrierung
- strukturierte Handoffs
- breitere Spezialistenketten
- Outcome-Lernen
- Alternativrezepte
- Recovery und Replaning
- self-selected strategies
- lightweight-first-Strategien
- fehlergesteuerte Strategieanpassung

### Warum das wichtig ist

Ein Orchestrator muss mehr koennen als "Agent A dann Agent B". Er muss erkennen:

- wann leichte Strategien reichen
- wann mehrere Agenten sinnvoll sind
- wann ein Tool Overkill ist
- wann ein Fehler einen anderen Toolpfad verlangt
- wann eine Aufgabe besser abgebrochen, degradiert oder eskaliert werden sollte

Meta bewegt sich genau in diese Richtung. Noch ist das System nicht perfekt, aber es ist bereits deutlich weiter als ein einfacher regelbasierter Router.

### Self-Selected Tool Strategy

Ein grosser Schritt war die Richtung weg von starren Regeln hin zu selbstgewaehlten Strategien. Meta soll fuer normale Aufgaben nicht mehr nur Keywords matchen, sondern ein Aufgabenprofil bilden:

- Zieltyp
- Aufwand
- Risiko
- erwartete Tiefe
- benoetigte Faehigkeiten

Darauf aufbauend werden Tool- und Agent-Affordances gewichtet. Das ist wichtig, weil ein Orchestrator nicht nur wissen muss, dass ein Tool existiert, sondern wofuer es tatsaechlich geeignet ist.

### Lightweight First

Statt bei jeder lockeren Frage direkt in tiefe, fragile oder teure Pfade zu springen, soll Timus zuerst den leichtesten sinnvollen Pfad versuchen. Das gilt vor allem fuer:

- leichte Recherche
- lockere YouTube-Anfragen
- kleine lokale Suchfragen
- einfache Statusabfragen

Das verbessert Geschwindigkeit, Kosten, Stabilitaet und Nutzererlebnis.

### Fehlergesteuerte Strategieanpassung

Meta soll Fehler nicht mehr nur weiterreichen, sondern lesen, klassifizieren und als Signal fuer Neuplanung nutzen. Ein Transportfehler, ein Backend-Crash, ein fehlendes Transcript oder ein Browserfehler brauchen nicht dieselbe Reaktion. Dieser Block ist eine wichtige Voraussetzung fuer einen wirklich brauchbaren Orchestrator.

## 11. Conversation Capsules und Follow-up-Verstehen

Ein laengeres Gespraech scheitert in Agentensystemen oft nicht am LLM selbst, sondern an schlechter Anschlusslogik. Genau dieses Problem hatte Timus in mehreren Faellen: kurze Folgefragen wurden ohne klaren Bezug wieder neu klassifiziert.

Deshalb wurden mehrere Schichten eingebaut:

### Session-Capsule

Pro Session wird ein kleiner, persistenter Zustand mitgefuehrt. Er enthaelt:

- letzte Nutzerfrage
- letzte Assistant-Antwort
- letzter Zielagent
- kurze Session-Zusammenfassung
- juengere User- und Assistant-Segmente

### Follow-up Resolver

Wenn die neue Anfrage kurz und offensichtlich an den letzten Turn anschliesst, versucht Timus dieselbe Spur zu halten. Das reduziert falsche Re-Routes.

### Qdrant-basierter semantischer Recall

Zusatzlich zur Capsule werden Chat-Turns semantisch abgelegt und bei Recall-Fragen wiedergefunden. Damit kann Timus nicht nur auf den letzten Satz schauen, sondern auch auf inhaltlich passende fruehere Turns.

### Aktueller Zustand

Dieser Stack macht laengere Gespraeche deutlich besser moeglich als zuvor. Die Einordnung muss aber ehrlich bleiben:

- direkte Folgefragen funktionieren jetzt deutlich robuster
- mittlere Gespraeche funktionieren besser
- semantischer Recall ist da
- das Ranking der besten Erinnerung ist noch nicht perfekt

Deshalb wurde zusaetzlich eine Recall-Eval-Schicht eingebaut, damit die Recall-Qualitaet messbar wird.

## 12. Gedachtnisschichten

Timus hat nicht nur "Memory", sondern mehrere Formen von Memory mit unterschiedlichen Rollen:

### Session Memory

Kurzfristiger Kontext innerhalb eines laufenden Gespraechs oder Tasks. Hier sitzen juengste Nachrichten, lokale Hinweise und Anschlussinformationen.

### Conversation Capsules

Leichte, strukturierte Session-Zusammenfassungen fuer Follow-ups. Sie halten das Kontextfenster klein und machen Anschlussfragen moeglich, ohne den vollen Verlauf immer wieder mitzuschleppen.

### Qdrant Chat Recall

Semantische Wiederfindung frueherer Chatsegmente. Das ist besonders wichtig fuer Fragen wie:

- "wie war nochmal dein Plan fuer Visual"
- "was meintest du vorhin damit"
- "woran lag der Fehler nochmal"

### Persistent Memory

Langzeitgedaechtnis fuer strukturiertere Informationen und ueberdauernde Kontexte. Es ist nicht nur Chat-Historie, sondern Teil des Systemwissens.

### Agent Blackboard

Ein geteiltes Arbeitsgedaechtnis zwischen Agenten. Ergebnisse koennen dort mit TTL abgelegt werden, damit andere Agenten sie spaeter sauber weiterverwenden koennen.

### Soul und Personality Memory

Timus hat zusaetzlich eine Persoenlichkeitsschicht und Erinnerung an Nutzersignale, Reaktionen und Hook-Gewichtungen. Das ist nicht nur Kosmetik, sondern beeinflusst Stil und Verhalten.

## 13. Memory-Hardening und semantische Backends

Ein besonders wichtiger juengster Block betrifft die semantische Memory-Schicht.

### Das Problem

Chroma lief im produktiven Hauptpfad stillschweigend mit, obwohl genau dort ein nativer Segmentation-Fault-Pfad bestand. Solche Fehler sind gefaehrlich, weil man sie nicht mit `try/except` sauber auffangen kann.

### Die Loesung

Der semantische Default wurde umgestellt:

- produktiv zuerst Qdrant
- alternativ none bzw. FTS5-only
- Chroma nur explizit
- kein stiller Fallback von Qdrant auf Chroma

### Warum das architektonisch wichtig ist

Das ist nicht bloss eine kleine Konfigurationsaenderung. Es trennt einen instabilen Legacy-Pfad vom produktiven Default. Zusaetzlich wurde der `memory`-Package-Import so umgebaut, dass formale CrossHair-Pruefungen ohne unerwuenschte Seiteneffekte moeglich sind.

### Auswirkungen

- Working-Memory-Pfade sind sicherer
- Produktions-Gates sind wieder gruen
- semantische Suche ist bewusster konfiguriert
- das Systemverhalten ist klarer dokumentierbar

## 14. Recall-Qualitaet und Metriken

Semantischer Recall ist nur dann wirklich wertvoll, wenn er nicht nur irgendeine aehnliche Stelle findet, sondern die richtige. Deshalb reicht es nicht, dass Qdrant "irgendetwas" zurueckgibt.

Timus misst dafuer inzwischen Recall-Signale und besitzt eine Recall-Eval-Schicht. Relevante Metriken sind unter anderem:

- Hit Rate@k
- Rank des besten korrekten Treffers
- wrong recall rate
- useful rate der finalen Antwort

Das ist wichtig, weil Timus dadurch nicht nur Recall besitzt, sondern auch weiss, wo Recall noch schlecht ist und wie er sich verbessern kann.

## 15. Self-Improvement und Reflexion

Timus besitzt mehrere Schichten, ueber die er sich selbst beobachtet und verbessert:

- Session-Reflexion
- Tool- und Routing-Analytics
- Verbesserungsvorschlaege
- Outcome-Lernen
- Recall-Telemetrie
- Self-Improvement-Engine

Die Selbstverbesserung ist nicht magisch und nicht beliebig frei. Aber sie ist real: Timus kann erkennen, wo Toolpfade schwach sind, welche Agenten schlecht routen, welche Recall-Arten schlecht funktionieren und welche Bereiche wiederholt Probleme machen.

## 16. Self-Modification: kontrollierte Autonomie

Einer der markantesten Unterschiede zwischen Timus und vielen Agentensystemen ist die Self-Modification-Pipeline.

Diese Pipeline umfasst:

- formale Zonen- und Policy-Regeln
- Risikoeinstufung
- isolierte Patch-Ausfuehrung
- harte Verifikation
- Canary-Checks
- Rollback
- Change Memory
- autonomen Apply-Controller

### Warum das wichtig ist

Viele Systeme behaupten, sie koennten sich selbst verbessern. In Wirklichkeit erzeugen sie nur Vorschlaege oder duerfen unkontrolliert Dateien schreiben. Timus hat hier einen Mittelweg:

- nicht frei und chaotisch
- aber auch nicht nur ein statischer Assistent

Das Ziel ist kontrollierte Selbstmodifikation mit Governance.

### Der aktuelle Reifegrad

Die Infrastruktur steht. Das heisst, Timus hat jetzt die technischen Bausteine fuer Level-2-Selbstmodifikation. Die Produktivtiefe dieser Faehigkeit wird sich in der Praxis mit echten Faellen, Logging und weiterem Lernen erst noch weiter verdichten.

## 17. Deep Research und Dokumentenfaehigkeit

Deep Research ist einer der staerksten Arbeitsbereiche von Timus. Das System kann:

- tief recherchieren
- Quellen auswerten
- Claims, Evidence und Verdicts strukturieren
- narrative Berichte erzeugen
- PDF-Berichte erstellen
- E-Mail-Workflows anstossen

In den letzten Schritten wurde nicht nur die Evidenzstaerke verbessert, sondern auch der Lesefluss. Das war wichtig, weil reine Evidenzsammlung noch keinen guten Bericht ergibt.

Zusaetzlich wurde ein kritischer Halluzinationspfad behoben: Wenn eine PDF nicht erzeugt werden konnte, durfte Timus keine erfolgreiche E-Mail ohne Anhang mehr verschicken. Dieser Fail-Fast-Block hat die Research- und Mail-Pipeline deutlich glaubwuerdiger gemacht.

## 18. YouTube- und SerpApi-Integration

Timus kann heute lockere und tiefe YouTube-Anfragen besser unterscheiden als frueher.

### Leichte YouTube-Anfragen

Fragen wie "was gibt es Neues auf YouTube" oder "schau mal was auf YouTube zu X laeuft" sollen nicht direkt in Deep Research kippen. Hier greifen leichtere Suchpfade.

### Tiefe Video-Recherche

Wenn Inhalte aus einem konkreten Video oder mehreren Videos tief ausgewertet werden sollen, nutzt Timus heute:

- YouTube-Suche
- Video-Infos
- Transcript-Zugaenge
- Research-Synthese

SerpApi wurde dafuer als zusaetzlicher, strukturierter Provider eingebunden. Das ist besonders wertvoll, weil nicht jede Web- oder Videoaufgabe ueber Browser-Automatisierung geloest werden sollte.

## 19. Standort, Maps und lokaler Kontext

Ein weiterer wichtiger Schritt war die Verknuepfung von mobilem Standort mit lokaler Suche.

### Android-Seite

Die App kann ueber Android Location Services den echten Geraetestandort holen.

### Server-Seite

Der Server kann:

- Standortdaten annehmen
- den letzten Snapshot speichern
- Reverse-Geocoding und Kontextbildung durchfuehren
- Nearby-Endpunkte bereitstellen

### Suchseite

Mit SerpApi Google Maps kann Timus lokale Anfragen bearbeiten, etwa:

- wo bin ich gerade
- was ist in meiner Naehe offen
- welche Orte befinden sich um mich herum

Diese Kombination macht Timus kontextsensitiver und alltagsnaeher.

## 20. Android-App im Detail

Die Android-App ist heute noch kein voll ausgereiftes Endprodukt, aber bereits deutlich mehr als ein Demo-Client.

### Login und Session

- Login ist moeglich
- Auto-Login ist eingebaut
- die App kann bestehende Session-Informationen wiederverwenden

### Chat

Die App bietet Chat mit Serveranbindung und den typischen Timus-Pfaden. Ein wichtiger Teil der juengsten Arbeit war, dass Anschlussfragen sauberer im gleichen Kontext gehalten werden.

### Voice

Der Voice-Modus wurde in Richtung hands-free angepasst:

- automatisches Zuhoren beim Oeffnen
- klarer `Antworte`-Pfad
- separater Transkriptionsmodus
- robusterer Playback-Pfad

### Standort

Die App kann den Standort abrufen, anzeigen und mit dem Server synchronisieren.

### Android Operator

Ein AccessibilityService ist bereits als Zugriffskern vorhanden. Das bedeutet noch nicht, dass Timus das Handy vollstaendig bedienen kann. Es bedeutet aber, dass der Operator den UI-Zustand, Fensterwechsel, Fokus- und bestimmte Interaktionsereignisse sehen kann.

## 21. Android Operator und voller Geraetezugriff

Die Richtung ist klar: Timus soll sich auf dem Handy besser zurechtfinden koennen. Dafuer wurde bereits ein Grundblock gebaut:

- AccessibilityService
- Status-Bridge
- Freigabe in den Android-Einstellungen
- sichtbare Operator-Sektion in der App

Was aktuell noch fehlt fuer einen wirklich starken mobilen Operator:

- systematische Screenshots oder Screen-Capture
- Notification-Zugriff
- explizite Aktionsausfuehrung ueber Operator-Kommandos
- tiefe Server-/Agentenintegration dieser Signale

Die Architektur ist also vorhanden, aber noch nicht vollendet.

## 22. Voice und gesprochene Interaktion

Voice ist fuer Timus nicht nur Zusatz, sondern ein zentraler Interaktionspfad. Wichtig ist hier die Trennung:

- Sprachaufnahme
- Transkription
- Textverarbeitung
- Antwortgenerierung
- TTS und Wiedergabe

Die Praxis hat gezeigt, dass Voice-UX schnell an Details scheitert: zu fruehes `speaking`, haengende Playback-States, schlechte Tastenlogik, doppelte Pfade. Genau deshalb wurde der mobile Voice-Flow juengst gehaertet.

## 23. Runtime-Governance und Produktionsnaehe

Timus besitzt nicht nur Funktionen, sondern auch Produktionsmechanismen. Dazu gehoeren:

- Production Gates
- py_compile
- Sicherheitspruefungen wie Bandit und pip-audit
- Smoke-Suites
- Self-Stabilization
- Circuit-Breaker- und Degrade-Pfade
- Incident- und Ops-Beobachtung

Gerade fuer ein System mit so vielen Modulen ist das entscheidend. Ohne diese Schichten wuerde Timus bei echter Nutzung schnell instabil werden.

## 24. Formale Qualitaetssicherung

Ein besonders starker Punkt in Timus ist, dass nicht nur klassische Tests verwendet werden. Es gibt mehrere Ebenen der Qualitaetssicherung:

- normale Pytests
- Hypothesis Property Tests
- CrossHair Contracts
- Lean-Verifikation fuer bestimmte Invarianten
- Produktions-Gate-Suites

Das ist wichtig, weil damit nicht nur konkrete Beispiele getestet werden, sondern auch logische Eigenschaften, Randfaelle und Invarianten. Gerade bei Orchestrierung, Memory, Vertragen und Fallbacklogik ist das deutlich wertvoller als reine Beispieltests.

In den juengsten Memory- und Recall-Bloecken wurde genau darauf geachtet, dass die formale Schicht nicht vergessen wird.

## 25. Modelle und Provider

Timus ist kein monomodales System, sondern nutzt unterschiedliche Modellpfade fuer unterschiedliche Rollen. Diese Zuordnung ist heute env- und providergetrieben.

Wichtig ist dabei weniger die exakte statische Modellliste als das Architekturprinzip:

- schnelle Faelle bekommen leichtere Modelle oder deterministische Pfade
- reasoning-lastige Faelle bekommen reasoning-staerkere Modelle
- Visual- und Spezialpfade koennen eigene Modellzustaende nutzen
- Modellwechsel sollen nicht mehr chaotisch oder per direkter `.env`-Manipulation im Lauf entstehen

Gerade beim Executor hat die Praxis gezeigt, dass nicht jeder kleine OpenRouter-Pfad produktiv robust genug ist. Deshalb wurde der Executor in Richtung stabilerer und deterministischerer Pfade gehartet.

## 26. Was Timus heute besonders stark kann

Timus ist heute besonders stark in diesen Bereichen:

- mehrstufige Orchestrierung
- strukturierte Recherche und Berichtserstellung
- Toolreiche Operator-Aufgaben
- Kombination aus Browser, Dokument, Search und Memory
- Runtime- und Architekturhaertung
- mobile Assistenz mit Voice und Standort
- kontrollierte Selbstmodifikation

Das System ist besonders interessant fuer Nutzer, die keinen reinen Chatbot brauchen, sondern einen Assistenten, der Informationen, Arbeitsschritte und Systemzustand ueber mehrere Schichten hinweg verbinden kann.

## 27. Was Timus noch nicht perfekt kann

Wichtig ist eine ehrliche Einordnung. Timus ist nicht "fertig" in dem Sinn, dass alles glatt, perfekt und vollautomatisch ist.

Noch nicht perfekt sind insbesondere:

- semantischer Recall-Ranking
- wirklich lange Gespraeche mit mehreren Themenstraengen
- mobile UX-Polish
- vollstaendiger Android-Operator
- bestimmte Modell- und Toolpfade unter extremer Last
- Stabilitaet einiger Randfaelle in grossen Agentenketten

Das ist aber ein wichtiger Unterschied: Die offenen Probleme liegen heute eher auf der Ebene von Qualitaet, Ranking, Haptik und Haertung - nicht mehr nur auf der Ebene "es gibt die Architektur noch gar nicht".

## 28. Timus im Vergleich zu typischen Agentensystemen

Was Timus von vielen oeffentlich sichtbaren Agentensystemen unterscheidet, ist die Kombination aus:

- Multi-Agenten-Architektur
- echter Tooltiefe
- mobilem Zugriff
- Dokumenten- und Research-Tiefe
- Gedachtnis in mehreren Schichten
- Runtime-Heilung
- Self-Modification-Governance

Viele Agentensysteme wirken im ersten Eindruck stark, weil sie ein oder zwei gute Pfade besitzen. Timus ist dagegen breiter und systemischer. Das macht ihn aufwendiger, aber auch langfristig interessanter.

## 29. Warum Timus beschreibbar ist

Wenn du Timus anderen erklaeren willst, helfen drei Ebenen:

### Kurzform

Timus ist ein selbstgehostetes Multi-Agenten-System mit Gedachtnis, Recherche, Dokumentenfaehigkeit, Browser- und mobiler App-Unterstuetzung sowie Runtime-Governance.

### Mittlere Form

Timus ist ein persoenlicher Operator mit Dispatcher, Meta-Orchestrierung, 13 Spezialagenten, mehr als 80 Tools, mehreren Memory-Schichten, Voice, Android-App, Standortkontext und kontrollierter Self-Modification.

### Ausfuehrliche Form

Timus ist eine agentische Assistenzplattform, die nicht nur ueber Sprache antwortet, sondern Aufgaben analysiert, Strategien waehlt, Spezialisten delegiert, Tools ausfuehrt, Fehler auswertet, Ergebnisse ueber mehrere Kanaele ausgibt und ihre eigene Laufzeit ueber Gates, Telemetrie, Gedachtnis und kontrollierte Selbstveraenderung stabilisiert.

## 30. Die aktuelle Entwicklungsrichtung

Die naechsten sinnvollen Schritte sind heute klar:

1. Recall-Qualitaet weiter messen und verbessern
2. Themenstrang-Tracking und Langgespraechsverstaendnis vertiefen
3. Android-Operator zu echten mobilen Aktionen ausbauen
4. Voice- und Mobile-Haptik weiter glaetten
5. Meta noch staerker von starren Regeln auf selbstgewaehlte Strategien umstellen
6. semantische und langfristige Memory-Schichten weiter konsolidieren

Diese Richtung ist wichtig, weil Timus gerade an einer Schwelle steht: Die groben Architekturbausteine sind da. Jetzt geht es zunehmend darum, sie dichter, intelligenter und robuster zusammenarbeiten zu lassen.

## 31. Fazit

Timus ist heute ein aussergewoehnlich breites und tiefes persoenliches Agentensystem. Es vereint viele Faehigkeiten, die normalerweise auf mehrere getrennte Produkte verteilt sind:

- Multi-Agenten-Orchestrierung
- Browser- und Toolausfuehrung
- Deep Research
- Dokumentenerstellung
- Gedachtnis ueber mehrere Ebenen
- Voice
- mobile App
- Standortkontext
- Runtime-Heilung
- kontrollierte Selbstmodifikation

Die wichtigsten Punkte fuer eine ehrliche Gesamtbewertung sind:

- Timus ist deutlich ueber Prototypniveau hinaus
- die Architektur ist ernsthaft und systemisch
- die Produktreife steigt, ist aber noch nicht maximal
- die offene Arbeit liegt vor allem in Qualitaet, Recall, Haptik und weiterer Haertung

Wenn man Timus in einem Satz fuer technische Leser beschreiben will, dann so:

Timus ist eine selbstgehostete, agentische Operator-Plattform mit Meta-Orchestrierung, spezialisierten Agenten, mobilem und webgestuetztem Zugriff, mehrschichtigem Gedachtnis, Runtime-Governance und kontrollierter Selbstmodifikation.

Wenn man Timus in einem Satz fuer nichttechnische Leser beschreiben will, dann so:

Timus ist ein persoenlicher KI-Assistent, der nicht nur antwortet, sondern mitdenkt, sucht, plant, schreibt, sich erinnert, ueber mehrere Geraete arbeitet und zunehmend versteht, was als Naechstes sinnvoll ist.

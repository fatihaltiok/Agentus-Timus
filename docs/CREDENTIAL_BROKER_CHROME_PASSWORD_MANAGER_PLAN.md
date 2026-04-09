# Credential Broker statt Secret Exposure

Stand: 2026-04-09

## Ziel

Timus soll dich spaeter bei Login-Workflows unterstuetzen koennen, **ohne** dass er deine Roh-Credentials kennen oder speichern muss.

Der passende Weg dafuer ist:

- **Chrome bzw. der Chrome-Passwortmanager ist der Credential Broker**
- **Timus bleibt ausserhalb der Secret-Ebene**
- **du gibst pro Zugriff bewusst Zustimmung**

In deinem Fall ist das besonders relevant, weil aktuell nur **Chrome** die gespeicherten Nutzernamen und Passwoerter bereits hat.

## Kernprinzip

Falsch waere:

- Timus kennt alle Nutzernamen
- Timus kennt alle Passwoerter
- Timus bekommt Exportdateien aus dem Passwortmanager
- Timus darf Credentials im Prompt, Memory oder Handoff herumtragen

Richtig waere:

- Chrome kennt die Credentials
- der Nutzer gibt Freigabe fuer einen konkreten Login-Workflow
- Timus steuert Navigation und sichtbaren Ablauf
- Chrome autofillt oder der Nutzer bestaetigt den gespeicherten Login
- Timus sieht nur den **Workflow-Zustand**, nicht das Geheimnis selbst

## Gewuenschtes Zielbild

Beispiel:

1. Du sagst: `Melde mich bei github an und geh danach zur Pull-Request-Seite.`
2. Timus erkennt: Login ist noetig.
3. Timus fragt nicht nach Passwort oder Nutzername im Chat.
4. Timus oeffnet den Login-Flow im **freigegebenen Chrome-Profil**.
5. Chrome fuellt vorhandene Zugangsdaten aus oder du bestaetigst den gespeicherten Eintrag selbst.
6. Timus stoppt weiter vor 2FA/CAPTCHA oder anderen sensiblen Challenges.
7. Nach deiner Bestaetigung setzt Timus die Aufgabe mit der authentischen Session fort.

Damit bleibt der operative Fluss assistiv, ohne dass Timus das Secret selbst besitzen muss.

## Warum das sicherer ist

Wenn Timus alle Credentials direkt kennen wuerde, entstuenden harte Risiken:

- Prompt-Injection koennte auf deutlich mehr Konten durchschlagen
- Secrets koennten in Logs, Memory, Delegation oder Screenshots auftauchen
- Scope waere schwer kontrollierbar
- ein Fehler im Routing koennte ungewollt auf andere Accounts zugreifen
- Widerruf und Revision waeren deutlich schlechter

Der Credential-Broker-Ansatz reduziert genau diese Risiken:

- keine Roh-Secrets in Timus
- Domain- und Workflow-Bindung
- sichtbarerer Zustimmungsprozess
- besserer Audit-Trail
- klarere Widerrufbarkeit

## Chrome-spezifische Einordnung

In deinem aktuellen Setup liegt der praktische Broker nicht bei Timus, sondern bei **Chrome**:

- dort sind Nutzernamen und Passwoerter bereits gespeichert
- nur Chrome kann diese Eintraege sinnvoll autofillen
- deshalb braucht Timus spaeter einen **Chrome-spezifischen Login-Pfad**

Das bedeutet zugleich:

- der heutige Login-Pfad ueber andere Browser ist nur ein Zwischenstand
- fuer echtes Credential-Broker-Verhalten braucht Timus spaeter einen kontrollierten **Chrome-/Profil-Pfad**
- dieser Pfad muss strikt getrennt sein von allgemeiner Browser-Automation

## Architekturregeln

### 1. Keine Secret-Exposition

- kein Passwort im Chat
- kein Passwort im Memory
- kein Passwort in Handoffs
- kein Passwort in Beobachtungslogs
- kein Passwort in strukturierten Runtime-Payloads

### 2. Domain-gebundene Freigabe

Jeder Zugriff braucht klare Bindung:

- `service`
- `domain`
- `purpose`
- `workflow_id`
- `approval_scope`

Beispiel:

- erlaubt: `github.com login fuer Repository-Workflow`
- nicht erlaubt: allgemeine Freigabe fuer beliebige Websites

### 3. Profilgebundene Ausfuehrung

Timus sollte spaeter nicht mit beliebigen Browsern oder Profilen arbeiten, sondern mit:

- einem explizit freigegebenen Chrome-Profil
- klarer Session- und Profilzuordnung
- optional separatem Arbeitsprofil fuer Operator-Tasks

### 4. Sensible UI bleibt user-mediated

Auch mit Passwortmanager gilt:

- 2FA bleibt user-mediated
- CAPTCHA bleibt user-mediated
- Security-Challenges bleiben user-mediated
- Passwortmanager-Auswahl kann user-mediated bleiben, wenn Chrome es verlangt

### 5. Session-Reuse vor Credential-Neunutzung

Wenn eine authentische Session bereits existiert, sollte Timus spaeter bevorzugen:

- Session wiederverwenden
- Session pruefen
- Session invalidieren/erneuern

statt:

- erneut an Passwort- oder Autofill-Pfade zu gehen

## Was Timus dafuer spaeter koennen muss

### A. Chrome-Login-Lane

Ein eigener Ausfuehrungspfad fuer:

- Chrome statt Firefox
- definierte Profile
- klare Abgrenzung zwischen normalem Browse-Task und Credential-Broker-Task

### B. Credential-Broker-Policy

Eine Policy-Schicht, die festlegt:

- fuer welche Domains das ueberhaupt erlaubt ist
- wann Freigabe noetig ist
- welche Schritte Timus selbst machen darf
- wann sofort an den Nutzer uebergeben werden muss

### C. Secret-Redaction und Logging-Grenzen

Timus darf keine geheimen Felder protokollieren. Das betrifft:

- OCR-Ausgaben
- Screen-Observations
- Debug-Logs
- Workflow-Metadaten

### D. Auditierbare Freigaben

Jeder Broker-Login braucht spaeter sichtbare Metadaten:

- wer hat freigegeben
- fuer welche Domain
- wann
- in welchem Workflow
- ob Session wiederverwendet oder neu aufgebaut wurde

### E. Widerruf und Invalidierung

Der Nutzer muss spaeter moeglichst einfach sagen koennen:

- `nutze diesen Login nicht weiter`
- `beende die Session`
- `vergiss die Freigabe fuer diese Domain`

## Einordnung in die Roadmap

Dieser Block gehoert **in spaete Phase D**, nicht in Phase E.

Warum:

- es ist ein Approval-/Auth-/Login-Thema
- es baut direkt auf `D3 User-mediated Login` und `D4 Auth Session Reuse` auf
- es ist kein Self-Improvement-, sondern ein sicherer Assistenz-/Zugriffsblock

Die passende Einordnung ist:

- zuerst `D3` stabilisieren
- dann `D4 Auth Session Reuse`
- danach ein eigener spaeterer Unterblock:
  - **`D4b Chrome Credential Broker`**

## Ziel fuer D4b Chrome Credential Broker

- Timus kann einen Login-Workflow gezielt in Chrome starten
- Chrome bleibt Inhaber der gespeicherten Credentials
- Timus verarbeitet keine Roh-Secrets
- Freigaben sind domain- und workflow-gebunden
- Session-Reuse wird bevorzugt
- Challenges bleiben user-mediated

## Nicht Ziel

- kein Export aller Credentials an Timus
- kein globaler Secret-Vault in Timus
- keine Rohpasswoerter in Memory oder Profil
- keine vollautonome Einlogg-Engine ohne Nutzerkontrolle

## Kurzform

Das richtige Modell ist nicht:

- `Timus kennt meine Passwoerter`

sondern:

- `Chrome kennt meine Passwoerter, Timus darf mit Zustimmung den Login-Workflow ueber Chrome nutzen, ohne die Secrets selbst zu besitzen`

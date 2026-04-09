# Phase D Vorbereitung - Approval, Auth und User Handover

Stand: 2026-04-06

Diese Datei bereitet Phase D vor, ohne bereits echte Nutzerfreigaben, Login-Automation oder Session-Reuse live einzuschalten.

## Ziel

Phase D baut auf Phase C auf und macht aus Timus einen assistiven Workflow-Agenten mit sauberem Nutzer-Handover.

Der Fokus liegt auf:

- Approval vor sensiblen Schritten
- Login-/Auth-Bedarf sauber erkennen
- Nutzer sensible Eingaben selbst ausfuehren lassen
- authentische Sessions danach kontrolliert weiterverwenden
- Challenges wie CAPTCHA / 2FA sauber uebergeben

## Bereits vorhandene Bausteine im Code

### 1. Auth-Wall-Signal im Social-Fetch

In [tools/social_media_tool/client.py](/home/fatih-ubuntu/dev/timus/tools/social_media_tool/client.py):

- `build_auth_required_payload(...)` liefert bereits:
  - `status: "auth_required"`
  - `auth_required: true`
  - `user_action_required`

Das ist der richtige Kern fuer `D1 Auth Need Detection`.

### 2. Login-Flow-Planer existiert bereits

In [orchestration/browser_workflow_plan.py](/home/fatih-ubuntu/dev/timus/orchestration/browser_workflow_plan.py):

- `_build_login_flow(...)` modelliert:
  - Landing
  - Login-Maske
  - Input-Felder
  - Submit
  - `authenticated`

Das ist ein direkter Startpunkt fuer `D3 User-mediated Login`.

### 3. Browser-Session-State kann persistiert werden

In [tools/browser_tool/persistent_context.py](/home/fatih-ubuntu/dev/timus/tools/browser_tool/persistent_context.py):

- `storage.json` wird geladen und gespeichert
- Sessions koennen dadurch grundsaetzlich wiederverwendet werden

Das ist die Basis fuer `D4 Auth Session Reuse`.

### 4. Challenge-Erkennung ist teilweise schon da

In [tools/browser_tool/retry_handler.py](/home/fatih-ubuntu/dev/timus/tools/browser_tool/retry_handler.py):

- CAPTCHA-/Block-Indikatoren werden erkannt
- Content kann auf Challenge-Spuren geprueft werden

Das ist die Basis fuer `D5 Challenge Handover`.

### 5. Approval-Muster existieren bereits im Self-Modify-Bereich

In [orchestration/autonomy_change_control.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_change_control.py):

- `approval_required`
- `awaiting_approval`
- Eskalations-/SLA-Logik

Das ist nicht direkt derselbe Nutzerpfad, aber ein gutes Muster fuer:

- Approval-Zustand
- Pending-Status
- sichtbare Blocker statt stilles Warten

## Phase-D-Kernvertrag

Phase D braucht einen gemeinsamen Nutzeraktions-Vertrag, statt fuer jede Plattform neue Ad-hoc-Felder zu erfinden.

## Zielzustand fuer Statuswerte

- `in_progress`
- `approval_required`
- `auth_required`
- `awaiting_user`
- `challenge_required`
- `completed`
- `blocked`
- `error`

## Ziel-Payloads

### A. Approval Required

```json
{
  "status": "approval_required",
  "workflow_id": "wf_...",
  "workflow_kind": "assistive_action",
  "approval_scope": "account_access",
  "reason": "auth_required_for_readable_content",
  "message": "Timus braucht deine Freigabe fuer echten Account-Zugriff.",
  "user_action_required": "Bitte bestaetige, ob Timus deinen Zugang dafuer verwenden darf."
}
```

### B. Auth Required

```json
{
  "status": "auth_required",
  "workflow_id": "wf_...",
  "service": "x",
  "reason": "login_wall",
  "message": "Die Plattform liefert ohne Login nur unvollstaendige Inhalte.",
  "user_action_required": "Bitte bestaetige, ob Timus deinen Login dafuer verwenden darf."
}
```

### C. Awaiting User

```json
{
  "status": "awaiting_user",
  "workflow_id": "wf_...",
  "service": "x",
  "step": "enter_credentials",
  "message": "Bitte gib Passwort und ggf. 2FA selbst im Browser ein.",
  "resume_hint": "Timus setzt den Workflow nach erfolgreichem Login fort."
}
```

### D. Challenge Required

```json
{
  "status": "challenge_required",
  "workflow_id": "wf_...",
  "service": "x",
  "challenge_type": "captcha",
  "message": "Die Seite verlangt eine Sicherheitspruefung.",
  "user_action_required": "Bitte loese die Challenge selbst und bestaetige danach die Fortsetzung."
}
```

## Arbeitsreihenfolge fuer den D-Vorlauf

1. Gemeinsame Feldnamen festziehen

- `approval_required`
- `auth_required`
- `user_action_required`
- `workflow_id`
- `resume_hint`
- `challenge_type`

2. C4-Transport anschlussfaehig machen

- Phase D soll auf den C4-Blocker-/Awaiting-Transport aufsetzen
- keine zweite Konkurrenz-Transportebene aufbauen

3. Nutzergrenzen klar definieren

- Passwort nie als normaler Chat-Inhalt
- 2FA / CAPTCHA / Security-Challenges nur user-mediated
- keine stillen Auto-Logins ohne explizite Freigabe

4. Session-Reuse begrenzen

- nur fuer explizit erlaubte Workflows
- klare Wiederaufnahmebedingungen
- Ablauf / Invalidierung definieren

5. Erste Ziel-Use-Cases festlegen

- X / LinkedIn / Reddit / aehnliche Login-Waende
- spaeter Buchungs-/Bestell-Workflows
- erst danach allgemeine Account-gebundene Web-Operator-Flows

## Zuschnitt innerhalb von Phase D

### D1. Auth Need Detection

- Login-Wand sauber von "leere Treffer" unterscheiden
- Social-Fetch, Browser-Fetch und Site-Resultate auf einen gemeinsamen Zustand bringen

### D2. Approval + Consent Gate

- explizite Freigabe des Nutzers vor Account-Zugriff
- Approval nicht nur als Text, sondern als strukturierter Workflow-Zustand
- D2.1:
  - offener Workflow-Zustand pro Session (`pending_workflow`)
  - kurze Antworten wie `ja` / `mach weiter` bleiben an Approval-/Auth-Zustaende gebunden
- D2.2:
  - Telegram und Canvas zeigen den offenen Workflow jetzt sichtbar an
  - C4-Blocker tragen Workflow-Felder wie Status, Service, Message und Resume-Hinweis
  - sichtbare Nutzerpfade fuer:
    - `approval_required`
    - `auth_required`
    - `awaiting_user`
    - `challenge_required`

### D3. User-mediated Login

- Timus navigiert bis zur Login-Maske
- Nutzer gibt Passwort / 2FA selbst ein oder bestaetigt bewusst den Schritt
- D3.1:
  - Login-Flows stoppen jetzt bewusst an der verifizierten Login-Maske
  - `visual` gibt dort einen strukturierten `awaiting_user`-Workflow zurueck statt Username/Passwort/Submit blind weiter auszufuehren
  - der Rueckweg bleibt im bestehenden Pending-Workflow-/C4-Pfad sichtbar
  - Registry behandelt solche Rueckgaben als partielle Workflows statt als Erfolg
- D3.2:
  - `weiter`, `ich bin eingeloggt` oder Challenge-Hinweise werden jetzt als Resume-Sprache auf offene Login-Workflows bezogen
  - der urspruengliche Source-Agent wird fuer diese Resume-Turns bevorzugt
  - `visual` kann den resumed Login jetzt bestaetigen oder wieder als `awaiting_user` / `challenge_required` zurueckmelden

### D4. Auth Session Reuse

- authentische Session kontrolliert wiederverwenden
- nur mit klarer Scope- und Ablaufregel

### D5. Challenge Handover

- CAPTCHA / 2FA / Security-Checks sauber an den Nutzer uebergeben
- kein blindes Weiterprobieren

## Nicht Teil der Vorbereitung

- kein Live-Auto-Login mit echten Nutzer-Credentials
- kein neuer produktiver Secret-Vault
- keine Zahlungsfreigabe-Logik
- keine vollstaendige Buchungsautomation

## Fertig fuer Start, wenn

- der gemeinsame Approval-/Auth-/Handover-Vertrag dokumentiert ist
- C4 den Blocker-/Awaiting-Transport bereitstellt
- Login-, Session- und Challenge-Bausteine als Startpunkte klar zugeordnet sind
- die erste D-Welle auf `D1` und `D2` fokussiert ist

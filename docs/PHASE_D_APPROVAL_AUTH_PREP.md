# Phase D Vorbereitung - Approval, Auth und User Handover

Stand: 2026-04-10

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
- D4.1:
  - bestaetigte Login-Sessions werden jetzt als eigener `auth_session`-Zustand im Session-Capsule-Pfad gespeichert
  - `visual` emittiert nach bestaetigtem user-mediated Login jetzt ein strukturiertes `auth_session_ready`-Signal
  - Follow-up-Kontext serialisiert jetzt den neuesten verifizierten Session-Anker mit:
    - `auth_session_service`
    - `auth_session_status`
    - `auth_session_scope`
    - `auth_session_url`
    - `auth_session_confirmed_at`
    - `auth_session_expires_at`
  - der erste Reuse-Slice bleibt bewusst konservativ:
    - session-scope
    - keine globale Credential-Wiederverwendung
    - keine Roh-Secrets
    - noch kein aggressives Auto-Reuse ueber beliebige neue Workflows
- D4.2:
  - vorhandene verifizierte Sessions werden jetzt im Login-Pfad **bevorzugt** vor einem neuen Login-Versuch geprueft
  - `visual` versucht bei `login_flow` zuerst eine Reuse-Navigation auf die gespeicherte authentische Zielseite
  - nur wenn diese Session-Pruefung fehlschlaegt, faellt Timus zurueck auf den normalen D3-Login-Workflow
  - bestaetigte Wiederverwendung wird jetzt explizit als `session_reused` signalisiert
  - der `visual_login`-Dispatcher-Wrapper behaelt vorhandene `auth_session_*`-Kontextfelder jetzt bei, statt sie beim Login-Handoff zu verlieren
- spaeterer Unterblock:
  - **D4b Chrome Credential Broker**
  - wenn gespeicherte Zugangsdaten praktisch nur im Chrome-Passwortmanager vorhanden sind, soll nicht Timus selbst die Secrets kennen, sondern Chrome als Credential Broker dienen
  - Timus darf dann nur mit expliziter Freigabe einen Login-Workflow im freigegebenen Chrome-Profil anstossen und danach mit Session-Reuse arbeiten
  - Roh-Credentials bleiben ausserhalb von Prompt, Memory, Handoff und Observation
  - Details in [CREDENTIAL_BROKER_CHROME_PASSWORD_MANAGER_PLAN.md](/home/fatih-ubuntu/dev/timus/docs/CREDENTIAL_BROKER_CHROME_PASSWORD_MANAGER_PLAN.md)

### D5. Challenge Handover

- CAPTCHA / 2FA / Security-Checks sauber an den Nutzer uebergeben
- kein blindes Weiterprobieren
- D5.1:
  - Browser- und Visual-Pfade unterscheiden Challenges jetzt feiner:
    - `cloudflare_challenge`
    - `recaptcha`
    - `hcaptcha`
    - `2fa`
    - `access_denied`
    - `human_verification`
    - Fallback `captcha`
  - `challenge_required`-Payloads tragen jetzt typisierte Standardtexte plus `resume_hint`
  - Pending-Workflow-Replys erkennen jetzt zusaetzlich:
    - `challenge_resolved`
  - offene `challenge_required`-Workflows werden im Follow-up-Routing jetzt wieder gezielt an den urspruenglichen Source-Agent gebunden
  - `visual` kann offene Login-Challenges jetzt als eigenen Resume-Pfad behandeln:
    - erneute Challenge sichtbar -> `challenge_required`
    - Challenge geloest und Auth verifiziert -> Workflow abgeschlossen
    - Challenge angeblich geloest, aber kein Auth-Nachweis -> wieder `challenge_required`
- D5.2:
  - Challenge-Resume wird jetzt als eigener Laufzeitpfad beobachtbar:
    - `challenge_required`
    - `challenge_resume`
    - `challenge_resolved`
    - `challenge_reblocked`
  - `canvas_chat` erkennt jetzt offene Challenge-Follow-ups und schreibt dafuer eigene Observation-Events
  - wenn ein Resume wieder in `challenge_required` zurueckfaellt, wird das als `challenge_reblocked` sichtbar statt nur indirekt ueber Pending-Workflow-Events
  - wenn ein offener Challenge-Workflow sauber ohne neuen Blocker abgeschlossen wird, wird das explizit als `challenge_resolved` beobachtet
  - `autonomy_observation` traegt dafuer jetzt einen eigenen Summary-Block `Challenge Runtime` mit:
    - Gesamtzahl Challenge-Handover
    - Resume-Erkennung
    - Resolution-Rate
    - Reblock-Rate
    - Aufschluesselung nach Challenge-Typ und Reply-Kind
- D5.3:
  - der frische Live-Fall `login-maske -> 2fa challenge` haelt jetzt auch in einer neuen Session wieder durch
  - `visual_login`-Follow-ups behalten `# FOLLOW-UP CONTEXT` im Dispatcher statt neu als frischer Login-Handoff gewrappt zu werden
  - wenn die Login-Maske bereits sichtbar ist, aber der Visual-Pfad irrtuemlich als `success` zurueckkommt, wird das jetzt wieder zu einem echten `awaiting_user`-Workflow normalisiert
  - Live-Nachweis:
    - Session `d5_live_verify_20260410_fix_d`
    - Step 1 emittiert wieder `pending_workflow_updated`
    - Step 2 emittiert `challenge_resume`
    - der Follow-up bleibt auf `visual_login` mit `route_source = followup_capsule`
  - offener Rest:
    - echte `challenge_required` / `challenge_reblocked` / `challenge_resolved`-Live-Nachweise haengen weiter an einem real sichtbaren Challenge-Screen, nicht mehr an der Follow-up-Verankerung

## Nicht Teil der Vorbereitung

- kein Live-Auto-Login mit echten Nutzer-Credentials
- kein neuer produktiver Secret-Vault
- keine Zahlungsfreigabe-Logik
- keine vollstaendige Buchungsautomation
- kein Export aus dem Chrome-Passwortmanager in Timus

## Fertig fuer Start, wenn

- der gemeinsame Approval-/Auth-/Handover-Vertrag dokumentiert ist
- C4 den Blocker-/Awaiting-Transport bereitstellt
- Login-, Session- und Challenge-Bausteine als Startpunkte klar zugeordnet sind
- die erste D-Welle auf `D1` und `D2` fokussiert ist

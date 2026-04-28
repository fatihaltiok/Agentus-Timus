# Owner Authority + Capability Gate Architektur

Stand: 2026-04-28

## Zweck

Dieses Dokument beschreibt eine robuste Architektur fuer Assistenten, die frei mit dem Nutzer sprechen koennen, aber trotzdem kontrolliert Tools, Recherche, lokale Dateien, Systemoperationen oder Selbstverbesserungen ausfuehren duerfen.

Der Kernpunkt: Ein Assistent darf seine Policies nicht selbst beliebig aendern. Gleichzeitig darf er aber nicht in einem starren Modus wie `think_partner` gefangen bleiben, wenn der autorisierte Owner eindeutig Ausfuehrung, Recherche oder Toolnutzung verlangt.

Die Loesung ist eine getrennte Kontrollschicht:

- Das LLM erkennt Absichten und formuliert Antworten.
- Ein deterministischer Policy-Controller entscheidet ueber Rechte.
- Der Owner kann Rechte freigeben.
- Die Freigabe ist capability- und scope-gebunden.

## Ausgangsproblem

Timus hatte wiederholt denselben Architekturfehler:

1. Eine Anfrage wurde als Denk-/Beratungskontext klassifiziert.
2. Daraus entstand `interaction_mode=think_partner`.
3. `think_partner` verbot Recherche, Tools und Delegation.
4. Der Nutzer gab danach explizit Freigabe oder verlangte Ausfuehrung.
5. Meta blieb trotzdem im alten Modus und antwortete mit Policy-Diskussion statt Handlung.

Beispiele:

- "mach daraus eine PDF" wurde blockiert, bis eine bestimmte Formulierung getroffen wurde.
- "geh ins Internet und hole Information ueber DeepSeek" wurde als `think_partner` blockiert.
- "ja voller Zugriff" wurde nicht als Owner-Freigabe verstanden.

Das Problem ist nicht fehlender Kontext. Das Problem ist, dass der Interaktionsmodus zu hart ist und kein sauberer Owner-/Capability-Override existiert.

## Warum Satzlisten nicht reichen

Eine naive Loesung waere:

- Wenn der Nutzer "fuehre aus" sagt, dann `execute`.
- Wenn der Nutzer "geh ins Internet" sagt, dann `research`.
- Wenn der Nutzer "voller Zugriff" sagt, dann Tools erlauben.

Das ist zu fragil. Der Nutzer kann morgen anders formulieren:

- "schau bitte selbst nach"
- "mach dich schlau"
- "nimm deine Werkzeuge"
- "du darfst dafuer suchen"
- "klaer das extern"

Dann bricht das System wieder. Deshalb darf die Loesung nicht primär aus festen Saetzen bestehen. Phrasen koennen harte Evidenz sein, aber die Entscheidung muss semantisch und strukturell erfolgen.

## Zielbild

Der Assistent soll unterscheiden:

- Der Nutzer will nur reden.
- Der Nutzer will eine Einschaetzung.
- Der Nutzer will eine Antwort aus vorhandenem Wissen.
- Der Nutzer will aktuelle Recherche.
- Der Nutzer will lokale Tool-Ausfuehrung.
- Der Nutzer will Systemoperation.
- Der Nutzer will Selbstverbesserung oder Codeaenderung.
- Der Nutzer gibt eine zuvor blockierte Aktion frei.

Diese Entscheidung darf nicht allein Meta treffen. Sie muss vor dem finalen Interaktionsvertrag durch eine Policy-Schicht laufen.

## Kernarchitektur

### 1. User Identity

Jede Anfrage bekommt eine verifizierte Nutzeridentitaet.

Beispiel:

```text
user_id = telegram_user_id
user_role = owner | trusted_user | normal_user | anonymous
```

Nur der Owner darf hohe Capabilities freigeben:

- Research
- lokale Tools
- Systemoperationen
- Agenten-Konfiguration
- Self-Modification
- Deployment

Normale Nutzer duerfen weiter chatten, fragen oder begrenzte harmlose Operationen ausloesen, aber keine Policy-Grenzen verschieben.

### 2. Capability Levels

Statt "voller Zugriff" als unklare globale Erlaubnis zu behandeln, werden Rechte in Faehigkeitsklassen zerlegt.

```text
chat_only
assist
research
local_tools
document_tools
communication
system_ops
self_modify
deployment
dangerous_ops
```

Beispiele:

- PDF aus ODT erzeugen: `local_tools`, `document_tools`
- Web-Recherche zu DeepSeek: `research`
- Service restart: `system_ops`
- Code fixen und committen: `self_modify`
- E-Mail senden: `communication`
- Dateien loeschen: `dangerous_ops`

Der Controller entscheidet nicht nur "erlaubt/verboten", sondern welche Capability fuer diese konkrete Anfrage noetig ist.

### 3. Scope

Freigaben duerfen nicht unendlich global gelten.

Empfohlene Scopes:

```text
turn
task
session
time_window
permanent_preference
```

Beispiele:

- "mach das jetzt" -> Scope `task`
- "du darfst fuer diese Recherche ins Internet" -> Scope `task`
- "ab jetzt bei PDF erst lokale Tools nutzen" -> Scope `permanent_preference`, aber nur fuer `document_tools`
- "voller Zugriff" -> nicht wirklich global, sondern maximal `task` oder `session`, je nach Sicherheitsklasse

Scope-Verfall muss deterministisch sein:

```text
turn: endet nach genau einer Antwort
task: endet bei final_answer, goal_satisfied, task_failed oder task_cancelled
session: endet bei explizitem Reset, hartem Themenwechsel, Timeout oder Restart
time_window: endet nach festem expires_at
permanent_preference: bleibt, bis Owner sie explizit entfernt
```

Empfohlene Defaults:

- `turn`: immer fuer einzelne Freigaben mit unklarem Folgekontext.
- `task`: Standard fuer Recherche, Datei-Konvertierung und lokale Analyse.
- `session`: nur fuer niedrige und mittlere Risiken, wenn der Owner es explizit verlangt.
- `time_window`: fuer laengere Arbeitsphasen, maximal wenige Stunden.
- `permanent_preference`: nur fuer Antwortstil und wiederkehrende harmlose Arbeitsweise.

Ein Scope darf nicht still "weiterleben", wenn der aktive Themenanker wechselt.

### 4. Policy Intent Resolver

Vor GDK/MIM wird eine semantische Absicht bestimmt.

Moegliche Policy-Intents:

```text
ask_opinion
ask_information
request_research
request_execution
grant_permission
change_mode
set_preference
remove_preference
complaint_or_correction
resume_blocked_intent
```

Der Resolver arbeitet nicht nur mit Regex. Er nutzt:

- semantische Klassifikation
- letzte blockierte Aktion
- aktuelle Conversation-State-Anker
- Nutzerrolle
- benoetigte Capability
- Risiko der Aktion

Regex/Phrasen sind nur Evidenz, nicht die Architektur.

### 5. Blocked Intent Snapshot

Wenn Timus eine Anfrage blockiert, wird nicht nur eine Fehlermeldung erzeugt. Der blockierte Auftrag wird gespeichert.

Beispiel:

```json
{
  "blocked_intent_id": "bi_20260428_001",
  "original_query": "geh ins Internet und hole Information ueber DeepSeek",
  "required_capability": "research",
  "blocked_by": "interaction_mode:think_partner",
  "risk_class": "low",
  "created_at": "2026-04-28T02:20:42+02:00",
  "resume_policy": "owner_grant_required"
}
```

Wenn der Owner danach sagt:

- "ja"
- "mach"
- "voller Zugriff"
- "du darfst suchen"
- "nimm die Tools"
- "dann mach dich schlau"

dann wird nicht neu geraten. Der Controller sieht den offenen `blocked_intent_snapshot` und prueft:

1. Ist der Nutzer Owner?
2. Passt die Freigabe semantisch zum blockierten Intent?
3. Ist die Capability fuer Owner freigebbar?
4. Ist der Scope begrenzt?
5. Muss nochmal bestaetigt werden?

Wenn ja, wird der alte Auftrag wieder aufgenommen.

### 6. Capability Gate

Das Capability Gate erzeugt den finalen Vertrag fuer Meta.

Beispiel fuer erlaubte Recherche:

```json
{
  "interaction_mode": "assist",
  "execution_permission": "allowed",
  "allowed_capabilities": ["research"],
  "allowed_agents": ["research"],
  "scope": "task",
  "owner_granted": true,
  "audit_required": true
}
```

Meta darf danach nicht mehr behaupten, es sei blockiert. Es bekommt den fertigen Vertrag und muss innerhalb dieses Vertrags handeln.

## Sicherheitsmodell

Nicht jede Owner-Freigabe ist gleich.

### Niedriges Risiko

Kann bei Owner direkt ausgefuehrt werden:

- Web-Recherche
- Quellen pruefen
- PDF erzeugen
- Datei konvertieren
- einfache lokale Analyse

### Mittleres Risiko

Owner-Freigabe noetig, eventuell kurze Rueckfrage:

- Datei verschieben
- Konfiguration aendern
- Agentenmodell umstellen
- API-Endpunkte testen
- E-Mail-Entwurf vorbereiten

### Hohes Risiko

Immer explizite Bestaetigung:

- Dateien loeschen
- E-Mail wirklich senden
- Services stoppen
- Secrets aendern
- Deployment
- Git push
- Self-Modification mit Commit

### Sehr hohes Risiko

Nie still ausfuehren:

- irreversible Datenloeschung
- Zahlungs-/Kaufaktionen
- externe Veroeffentlichung
- Security-relevante Freigaben
- dauerhafte globale Policy-Deaktivierung

### Sonderpfad fuer Self-Modify und Deployment

`self_modify`, `deployment` und vergleichbare Hochrisiko-Capabilities duerfen nicht ueber den normalen semantischen Resolver freigeschaltet werden.

Regel:

```text
Capabilities >= high risk brauchen explizite Approval-UI oder explizite Owner-Bestaetigung mit konkretem Ziel, Diff/Plan und Verifikation.
```

Fuer Timus bedeutet das:

- Self-Modify darf einen Patch vorschlagen.
- Self-Modify darf nicht automatisch schreiben, committen oder pushen.
- Deployment darf nie durch "voller Zugriff" pauschal freigegeben werden.
- Ein blockierter Self-Modify-Intent darf nicht periodisch neu enqueued werden.
- Telegram-Button-Approval oder gleichwertige explizite Approval-Struktur ist Pflicht.

## Verantwortlichkeiten

### Meta-Agent

Meta darf:

- Nutzerabsicht formulieren
- bei echter Unklarheit fragen
- innerhalb eines erlaubten Vertrags handeln
- Unsicherheit markieren

Meta darf nicht:

- sich selbst Capabilities geben
- Policy-Grenzen ignorieren
- "Ich kann nicht" sagen, wenn der Controller die Ausfuehrung erlaubt hat
- riskante Aktionen ohne Gate ausfuehren

### Policy Controller

Der Controller entscheidet:

- Nutzerrolle
- Capability-Bedarf
- Risk Class
- Scope
- ob Owner-Freigabe vorliegt
- ob ein blockierter Intent wieder aufgenommen wird

### User/Owner

Der Owner darf:

- blockierte Aktionen freigeben
- Capabilities fuer eine Aufgabe aktivieren
- Praeferenzen setzen
- Systemoperationen anstossen
- Self-Modification beauftragen

Der Owner sollte trotzdem nicht automatisch jede Gefahr freischalten. Die Architektur schuetzt auch den Owner vor versehentlicher Ausfuehrung.

## Audit-Strategie

Jede Capability-Entscheidung wird auditiert, aber nicht jede Wiederholung darf eine neue volle Log-Zeile erzeugen.

Audit-Felder:

```json
{
  "decision_id": "cap_20260428_001",
  "user_id": "telegram:1679366204",
  "user_role": "owner",
  "policy_intent": "request_research",
  "required_capability": "research",
  "risk_class": "low",
  "scope": "task",
  "decision": "allowed",
  "reason": "owner_low_risk_task_scope",
  "expires_at": "2026-04-28T03:00:00+02:00"
}
```

Volume-Regeln:

- Gleiche blockierte Entscheidung bekommt Dedupe-Key.
- Wiederholungen erhoehen einen Counter statt neue Voll-Events zu schreiben.
- Periodische Autonomie-Loops muessen `cooldown_until` respektieren.
- Audit wird in kurze Decision-Events und optional detaillierte Debug-Events getrennt.
- Runtime-UI zeigt aggregierte Entscheidungen, nicht rohe 62k-Zeilen-Loops.

## Beispielablauf: Recherche

User:

```text
geh ins Internet und hole Information ueber DeepSeek
```

Policy Intent Resolver:

```text
intent=request_research
required_capability=research
risk=low
user_role=owner
```

Capability Gate:

```text
allowed=true
scope=task
interaction_mode=assist
allowed_agents=[research]
```

Meta:

```text
Fuehrt Recherche aus oder delegiert an research.
Keine Modusdiskussion.
```

## Beispielablauf: Blockierter Intent

Turn 1:

```text
geh ins Internet und hole Information ueber DeepSeek
```

Falls noch blockiert:

```text
blocked_intent_snapshot wird gespeichert.
```

Turn 2:

```text
ja voller Zugriff
```

Policy Controller:

```text
grant_permission + resume_blocked_intent
Owner bestaetigt research fuer vorherigen Auftrag.
```

Meta bekommt:

```text
original_query=geh ins Internet und hole Information ueber DeepSeek
interaction_mode=assist
execution_permission=allowed
allowed_capabilities=[research]
```

Ergebnis:

```text
Recherche startet.
Keine erneute Diskussion ueber think_partner.
```

## Beispielablauf: Lokales Dokument

User:

```text
mach daraus eine PDF /home/fatih/Dokumente/datei.odt
```

Resolver:

```text
intent=request_execution
capability=document_tools/local_tools
risk=low
```

Gate:

```text
allowed=true fuer Owner
scope=task
```

Meta:

```text
Delegiert an document/shell oder fuehrt sichere Konvertierung aus.
```

## Warum diese Architektur besser ist

Sie loest mehrere alte Timus-Probleme gleichzeitig:

- Kein Festhaengen im `think_partner`-Modus.
- Keine fragile Satzlisten-Abhaengigkeit.
- Keine globale unsichere "voller Zugriff"-Freigabe.
- Kein Meta-Agent, der seine eigenen Regeln umgeht.
- Wiederaufnahme blockierter Intents wird strukturell moeglich.
- Owner kann Timus kontrollieren, andere Nutzer nicht.
- Jede Rechteentscheidung ist auditierbar.

## Minimaler Implementierungsplan fuer Timus

### Slice 0: Self-Hardening-Loop stoppen

Vor der eigentlichen Authority-Implementierung muss der akute Self-Hardening-Loop gestoppt werden.

Beobachtung vom 2026-04-28:

- Die Observation-Logs zeigen alle ca. 3 Minuten dieselben Kandidaten.
- Die Kandidaten `m12:3860`, `m12:3901`, `m12:3764`, `m12:3804`, `m12:3780` zielen wiederholt auf `tools/visual_browser_tool/tool.py`.
- Alle werden durch `rollout_guard_state=strict_force_off` blockiert.
- Das erzeugt hohes Audit-Volumen, ohne produktive Aktion.

Das ist ein Symptom derselben Architekturklasse: Das System erkennt einen moeglichen Verbesserungsauftrag, weiss aber nicht sauber, ob es handeln darf, und versucht es periodisch erneut.

Akzeptanz:

- Gleicher blockierter Self-Hardening-Kandidat wird nicht endlos neu enqueued.
- Blockierte Kandidaten bekommen Cooldown, Dedupe-Key und klare `blocked_until`-Semantik.
- `strict_force_off` fuehrt zu ruhigem Audit, nicht zu Log-Spam.
- Self-Modify bleibt blockiert, bis Owner-Approval ueber den expliziten Hochrisiko-Pfad vorliegt.

### Slice 1: Authority Model

Dateien:

- `orchestration/user_authority.py`
- Telegram-Gateway Integration
- Tests fuer Owner/Normal-User

Akzeptanz:

- Telegram-Owner-ID wird als `owner` erkannt.
- Andere IDs bleiben `normal_user`.
- Authority landet im Routing-Kontext.

### Slice 2: Capability Taxonomy

Dateien:

- `orchestration/capability_risk_matrix.py`
- `orchestration/capability_gate.py`
- `tests/test_capability_gate.py`

Akzeptanz:

- Capability, Action und Risk-Klasse werden aus einer zentralen Matrix bestimmt.
- Owner darf low-risk Capabilities task-scoped freigeben.
- Neue Capability-Arten muessen explizit in der Matrix auftauchen oder sichtbar als `unknown_capability` auditiert werden.

Deklarativer Zielzustand:

```python
CAPABILITY_RISK = {
    "research": {
        "web_lookup": "low",
        "deep_research": "medium",
    },
    "document_tools": {
        "convert_pdf": "low",
        "summarize_local_pdf": "low",
    },
    "communication": {
        "draft_email": "medium",
        "send_email": "high",
    },
    "system_ops": {
        "health_check": "low",
        "restart_service": "high",
    },
    "self_modify": {
        "propose_patch": "medium",
        "write_patch": "high",
        "commit_or_push": "high",
    },
}
```

Diese Matrix verhindert, dass Policy-Entscheidungen wieder in vielen verstreuten Listen landen.

### Slice 3: Policy Intent Resolver

Dateien:

- `orchestration/policy_intent_resolver.py`
- Hypothesis-/Contract-Tests

Akzeptanz:

- Semantisch unterschiedliche Formulierungen fuer Recherche/Ausfuehrung werden richtig erkannt.
- Nicht nur feste Satzlisten.
- Think-Partner-Fragen bleiben Think-Partner.

Wichtige Praezisierung: Dieser Slice ist keine kleine Regex-Erweiterung. Der Resolver braucht ein eigenes Konfidenzmodell.

Mindestfelder:

```json
{
  "policy_intent": "request_research",
  "confidence": 0.86,
  "evidence": ["semantic_action_request", "mentions_external_information"],
  "required_capability": "research",
  "risk_class": "low",
  "fallback": "ask_clarifying_question"
}
```

Konfidenzregeln:

- `confidence >= 0.80`: Controller darf bei Owner und niedriger Risk-Klasse direkt freigeben.
- `0.55 <= confidence < 0.80`: Eine kurze Klaerfrage oder explizite Bestaetigung ist noetig.
- `confidence < 0.55`: Default restriktiv, keine Tool-Ausfuehrung.
- Wenn der Resolver selbst ausfaellt: Default restriktiv, aber mit sauberem Fallback statt Modusdiskussion.

Modellauswahl:

- Erste Version: deterministische Features plus vorhandene Turn-Understanding-Signale.
- Spaetere Version: optional kleiner semantischer Klassifikator.
- Kein unkontrollierter LLM-Call pro Turn als alleinige Quelle der Policy-Wahrheit.

### Slice 4: Blocked Intent Snapshot

Dateien:

- `orchestration/blocked_intent_state.py`
- Conversation-State Integration

Akzeptanz:

- Blockierte Recherche/Tool-Anfrage wird gespeichert.
- Naechster Owner-Freigabe-Turn kann den alten Auftrag wieder aufnehmen.

### Slice 5: MIM/GDK Integration

Dateien:

- `orchestration/general_decision_kernel.py`
- `orchestration/meta_interaction_mode.py`
- `orchestration/meta_orchestration.py`

Akzeptanz:

- `request_research + owner + low_risk` ueberschreibt `think_partner`.
- `grant_permission` nimmt blockierten Intent wieder auf.
- Meta bekommt keinen widerspruechlichen Vertrag mehr.

Verhaeltnis zu GDK6:

- Das Capability Gate ersetzt GDK6 nicht sofort.
- Es wird vor MIM als korrigierende Authority-Schicht eingefuegt.
- GDK6 bleibt fuer generelle Turn-Klassifikation und vorhandene fast paths zustaendig.
- Wenn Capability Gate einen starken Owner-/Capability-Entscheid trifft, darf es den Interaktionsmodus fuer diesen Turn ueberschreiben.
- Bestehende GDK6-Gates bleiben als Regression-Schutz bestehen, bis Live-Gates zeigen, dass die Capability-Schicht stabil genug ist.

### Slice 6: Live Gates

Pflichtfaelle:

1. "geh ins Internet und informiere dich ueber X"
2. "mach dich schlau zu X"
3. "du darfst dafuer suchen"
4. "ja voller Zugriff" nach blockierter Recherche
5. "mach daraus eine PDF /pfad/datei.odt"
6. "sende die E-Mail" mit Bestaetigungspflicht
7. fremder Telegram-User versucht `system_ops` und wird blockiert

Akzeptanz:

- Keine Modusdiskussion bei low-risk Owner-Aufgaben.
- Kein Zugriff fuer Nicht-Owner.
- Riskante Aktionen bleiben bestaetigungspflichtig.

## Leitprinzip fuer zukuenftige Projekte

Ein autonomer Assistent braucht nicht "mehr Freiheit" im LLM. Er braucht eine bessere Trennung:

```text
LLM = Verstehen, Formulieren, Planen
Policy Controller = Rechte, Risiko, Scope
Owner Authority = Wer darf freigeben
Capability Gate = Was darf ausgefuehrt werden
Audit = Warum wurde es erlaubt oder blockiert
```

So kann auch ein kleineres lokales Modell wie ein faehiger Assistent wirken, weil die Architektur ihm die schwierigen Kontrollentscheidungen strukturiert abnimmt.

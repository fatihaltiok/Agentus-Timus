# Changelog Dev

---

## Fortschritt 2026-04-10 - D4b Chrome Credential Broker als erster Runtime-Slice gestartet

Der Chrome-Credential-Broker war bisher nur als spaeterer Ausbau fuer Phase D eingeordnet. Nach D3/D4 ist jetzt der erste konservative Runtime-Slice dafuer live im Code vorbereitet: Timus kennt weiterhin keine Roh-Secrets, kann aber fuer explizite Chrome-/Passwortmanager-Loginwuensche denselben Workflow in einem eigenen Broker-Lane fuehren.

Geaendert:

- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - erkennt jetzt explizite Chrome-/Passwortmanager-Loginwuensche
  - `visual_login`-Handoffs tragen dafuer jetzt:
    - `browser_type: chrome`
    - `credential_broker: chrome_password_manager`
    - `domain`
  - vorhandene `auth_session_*`-Brokerfelder bleiben im Login-Follow-up erhalten
- [agent/agents/visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
  - fuehrt `login_flow` im expliziten Broker-Fall jetzt in Chrome aus
  - haelt Browser-/Broker-/Domain-Kontext ueber Login, Resume und Auth-Session-Ready zusammen
  - reicht jetzt auch `broker_profile` an den sichtbaren Browser-Start weiter
  - `awaiting_user`-Workflows geben jetzt im Broker-Fall Chrome-spezifische Hinweise statt generischer Login-Texte aus
- [orchestration/approval_auth_contract.py](/home/fatih-ubuntu/dev/timus/orchestration/approval_auth_contract.py)
  - Phase-D-Workflow-Payloads tragen jetzt auch:
    - `domain`
    - `preferred_browser`
    - `credential_broker`
    - `broker_profile`
- [orchestration/pending_workflow_state.py](/home/fatih-ubuntu/dev/timus/orchestration/pending_workflow_state.py)
  - Pending-Workflows serialisieren den Broker-Kontext jetzt turnuebergreifend mit
- [orchestration/auth_session_state.py](/home/fatih-ubuntu/dev/timus/orchestration/auth_session_state.py)
  - Auth-Session-State speichert jetzt:
    - `browser_type`
    - `credential_broker`
    - `broker_profile`
    - `domain`
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - Follow-up-Capsules und `auth_session_updated`-Events transportieren die neuen Broker-Felder jetzt mit
- [tools/visual_browser_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/visual_browser_tool/tool.py)
  - `start_visual_browser(...)` kann jetzt optional ein `profile_name` entgegennehmen
  - Chrome-Starts tragen dieses Profil jetzt in den echten Startbefehl ein, z. B. `--profile-directory=Default`
  - profilgebundene Chrome-Instanzen werden getrennt verwaltet statt nur ueber einen globalen `chrome`-Key
- Tests:
  - [test_dispatcher_camera_intent.py](/home/fatih-ubuntu/dev/timus/tests/test_dispatcher_camera_intent.py)
  - [test_auth_session_state.py](/home/fatih-ubuntu/dev/timus/tests/test_auth_session_state.py)
  - [test_android_chat_language.py](/home/fatih-ubuntu/dev/timus/tests/test_android_chat_language.py)
  - [test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
  - [test_visual_browser_tool.py](/home/fatih-ubuntu/dev/timus/tests/test_visual_browser_tool.py)

Einordnung:

- der Slice ist bewusst konservativ
- er greift nur bei **explizitem** Chrome-/Passwortmanager-Wunsch
- ohne explizite Profilangabe faellt der Broker-Lane jetzt konservativ auf Chrome-Profil `Default` zurueck
- er fuehrt noch keine Autofill-/Secret-Verifikation durch
- er baut auf D3 user-mediated Login und D4 Session Reuse auf, statt sie zu umgehen

## Fortschritt 2026-04-10 - Login-Zielzustand zaehlt jetzt mehr als der starre Login-Schritt

Im D4b-Live-Test zeigte sich ein typischer Restfehler: Timus startete korrekt den Chrome-Broker-Pfad, hielt aber trotzdem weiter an `login_dialog` fest, obwohl GitHub funktional bereits eingeloggt sichtbar war. Das war zu schrittorientiert. Timus soll hier zielzustandsorientiert handeln: wenn ein passender authentischer Zustand schon sichtbar ist, darf der Login-Schritt als erfuellt gelten.

Geaendert:

- [agent/agents/visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
  - Login-Flows pruefen jetzt bei einem Fehlschlag auf dem Weg zur Login-Maske zusaetzlich, ob der Dienst bereits sichtbar authentisch ist
  - wenn ja, behandelt `visual_login` den Login als **funktional bereits erfuellt**
  - statt `partial_result` gibt der Pfad jetzt einen echten Erfolgszustand mit `auth_session`-Signal zurueck
  - wenn ein anderer sichtbarer Browserzustand den Login bereits erfuellt, macht Timus den Browser-Mismatch transparent, blockiert aber nicht mehr blind am Schritt `login_dialog`
- [tests/test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
  - neue Regression fuer:
    - Chrome-Broker angefordert
    - Login-Maske nicht erreicht
    - GitHub bereits sichtbar eingeloggt
    - Login-Schritt wird uebersprungen und als Zielerfuellung behandelt

Einordnung:

- das ist kein neuer Secret- oder Broker-Mechanismus
- es ist eine **Strategiehaertung** fuer Phase D:
  - `goal_satisfied > expected_state`
  - `reuse_before_relogin`
  - `authenticated state can satisfy login intent`

## Fortschritt 2026-04-10 - D5 frische Session fuer Login- und Challenge-Resume gehaertet

Der erste D5-Resume-Fix hat den Challenge-Follow-up zwar wieder an `visual_login` gebunden, aber ein frischer Login-Start konnte den Pending-Workflow noch verlieren: Wenn die Login-Maske bereits sichtbar war, kam der Visual-Pfad gelegentlich nur als plain `success` mit `login_handoff ...` zurueck. Dann fehlte `pending_workflow_updated`, und der direkte Follow-up `ich sehe jetzt eine 2fa challenge` fiel in einer neuen Session wieder auf `meta`.

Geaendert:

- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - `visual_login`-Follow-ups mit `# FOLLOW-UP CONTEXT` werden jetzt im Dispatcher nicht mehr erneut als frischer Login-Handoff gewrappt
  - dadurch bleibt der Pending-Workflow-Kontext auf dem Resume-Pfad fuer `visual_login` erhalten
- [agent/agents/visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
  - neuer Guard fuer `login_flow`:
    - wenn ein Login-Task irrtuemlich als `success` endet, aber noch kein authentischer Zustand bestaetigt ist, wird das Ergebnis wieder in einen echten Phase-D-Workflow `awaiting_user` normalisiert
  - damit bleibt auch der Fall `Login-Maske schon sichtbar` sauber user-mediated und schreibt wieder einen Pending-Workflow
- [tests/test_dispatcher_camera_intent.py](/home/fatih-ubuntu/dev/timus/tests/test_dispatcher_camera_intent.py)
  - Regression fuer erhaltenen `visual_login`-Follow-up-Kontext
- [tests/test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
  - neue Regression fuer den Fall:
    - `login_flow`
    - sichtbare Login-Maske
    - fälschlich success
    - wird wieder zu `awaiting_user`
- [docs/PHASE_D_APPROVAL_AUTH_PREP.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D_APPROVAL_AUTH_PREP.md)
  - D5.3-Livehaertung dokumentiert

Verifikation:

- `python -m py_compile agent/agents/visual.py main_dispatcher.py server/mcp_server.py tests/test_dispatcher_camera_intent.py tests/test_phase_d_chat_rendering.py tests/test_android_chat_language.py tests/test_specialist_handoffs.py`
- `pytest -q tests/test_dispatcher_camera_intent.py tests/test_phase_d_chat_rendering.py tests/test_android_chat_language.py tests/test_pending_workflow_state.py tests/test_specialist_handoffs.py`
  - `80 passed`

Live-Nachweis:

- Session `d5_live_verify_20260410_fix_d`
- Step 1 `oeffne github.com/login und bring mich bis zur login-maske`
  - natuerliche Phase-D-Antwort
  - `phase_d_workflow` im `/chat`-Response
  - `pending_workflow_updated` im Observation-Log
- Step 2 `ich sehe jetzt eine 2fa challenge`
  - `challenge_resume` im Observation-Log
  - `request_route_selected` mit:
    - `agent = visual_login`
    - `route_source = followup_capsule`
  - der Resume-Pfad bleibt damit in einer frischen Session stabil auf `visual_login`, statt wieder auf `meta` zu fallen

## Fortschritt 2026-04-10 - Phase D5.2 Challenge Runtime Observability

Nach D5.1 waren Challenge-Typisierung und Resume-Vertrag im Code vorhanden, aber im Laufzeitbild noch nicht sauber messbar. Resume-Faelle, erneute Blockaden und erfolgreiche Challenge-Aufloesungen verschwanden bisher weitgehend in generischen Pending-Workflow-Events.

Nachgezogen:

- [mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - neuer Helper:
    - `_build_challenge_resume_observation_payload(...)`
  - `canvas_chat` schreibt jetzt bei offenen Challenge-Follow-ups ein eigenes `challenge_resume`-Event
  - wenn ein neuer `challenge_required`-Blocker aus einem Resume heraus wieder auftaucht, wird jetzt zusaetzlich `challenge_reblocked` emittiert
  - wenn ein offener `challenge_required`-Workflow ohne neuen Blocker erfolgreich aufgeloest wird, wird jetzt `challenge_resolved` emittiert
- [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neuer Summary-Block:
    - `challenge_runtime`
  - neue Metriken:
    - `challenge_required_total`
    - `challenge_resume_total`
    - `challenge_resolved_total`
    - `challenge_reblocked_total`
    - `resolution_rate`
    - `reblock_rate`
  - Aufschluesselung nach:
    - `by_service`
    - `by_challenge_type`
    - `by_reply_kind`
  - Markdown-Report zeigt jetzt den Block `## Challenge Runtime`
- Tests:
  - [test_autonomy_observation.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation.py)
    - neuer Summary-Test fuer `challenge_runtime`
  - [test_android_chat_language.py](/home/fatih-ubuntu/dev/timus/tests/test_android_chat_language.py)
    - neuer MCP-Helper-Test fuer `challenge_resume`-Payloads

Verifikation:

- `python -m py_compile orchestration/autonomy_observation.py server/mcp_server.py tests/test_autonomy_observation.py tests/test_android_chat_language.py`
- `pytest -q tests/test_autonomy_observation.py tests/test_android_chat_language.py tests/test_approval_auth_contract.py tests/test_pending_workflow_state.py tests/test_browser_isolation.py tests/test_specialist_handoffs.py`

Ergebnis:

- `87 passed` im kombinierten D5.2-/Phase-D-/Observation-Ring
- `py_compile` gruen

## Fortschritt 2026-04-10 - Phase D5.1 Challenge Handover gestartet

Nach D4.2 konnte Timus Auth-Sessions wiederverwenden und user-mediated Logins kontrolliert wieder aufnehmen. Was noch fehlte, war ein echter Challenge-Handover-Pfad: CAPTCHA-, 2FA- und Security-Challenges wurden zwar grob erkannt, aber noch nicht fein typisiert, nicht als eigener Resume-Pfad behandelt und nicht sauber genug an spaetere Follow-ups gebunden.

Nachgezogen:

- [approval_auth_contract.py](/home/fatih-ubuntu/dev/timus/orchestration/approval_auth_contract.py)
  - `build_challenge_required_workflow_payload(...)` traegt jetzt auch:
    - `reason`
    - `resume_hint`
  - neue typisierte Standard-Copy fuer:
    - `cloudflare_challenge`
    - `recaptcha`
    - `hcaptcha`
    - `2fa`
    - `access_denied`
    - `human_verification`
    - Fallback `captcha`
  - `normalize_phase_d_workflow_payload(...)` setzt fuer `challenge_required` jetzt automatisch einen Resume-Hinweis, wenn keiner mitgegeben wurde
- [pending_workflow_state.py](/home/fatih-ubuntu/dev/timus/orchestration/pending_workflow_state.py)
  - neue Reply-Klassifikation:
    - `challenge_resolved`
  - Reply-Payloads tragen jetzt auch `challenge_type` und `service`
- [retry_handler.py](/home/fatih-ubuntu/dev/timus/tools/browser_tool/retry_handler.py)
  - Challenge-Erkennung liefert jetzt neben `is_blocked` auch einen feineren `challenge_type`
- [tool.py](/home/fatih-ubuntu/dev/timus/tools/browser_tool/tool.py)
  - Browser-Challenge-Payloads nutzen jetzt die feinere Typisierung und einen echten Resume-Hinweis, statt nur generischer Blocker-Texte
- [visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
  - offene `challenge_required`-Workflows koennen jetzt wieder aufgenommen werden
  - `visual` behandelt `challenge_present`, `challenge_resolved` und geblockte Resume-Faelle jetzt getrennt
  - wenn nach gemeldeter Challenge-Aufloesung kein authentischer Zustand sichtbar ist, faellt Timus wieder kontrolliert auf `challenge_required` zurueck statt auf ein unscharfes `awaiting_user`
- [mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - Follow-up-Routing bevorzugt jetzt auch bei offenem `challenge_required`-Workflow wieder den urspruenglichen Source-Agent
  - Pending-Workflow-Cleanup akzeptiert jetzt auch `challenge_resolved`, wenn derselbe Agent den Workflow ohne neuen Blocker sauber abschliesst
- Tests:
  - [test_approval_auth_contract.py](/home/fatih-ubuntu/dev/timus/tests/test_approval_auth_contract.py)
  - [test_pending_workflow_state.py](/home/fatih-ubuntu/dev/timus/tests/test_pending_workflow_state.py)
  - [test_browser_isolation.py](/home/fatih-ubuntu/dev/timus/tests/test_browser_isolation.py)
  - [test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
  - [test_android_chat_language.py](/home/fatih-ubuntu/dev/timus/tests/test_android_chat_language.py)

Verifikation:

- `python -m py_compile orchestration/approval_auth_contract.py orchestration/pending_workflow_state.py tools/browser_tool/retry_handler.py tools/browser_tool/tool.py agent/agents/visual.py server/mcp_server.py tests/test_approval_auth_contract.py tests/test_pending_workflow_state.py tests/test_browser_isolation.py tests/test_specialist_handoffs.py tests/test_android_chat_language.py`
- `pytest -q tests/test_approval_auth_contract.py tests/test_browser_isolation.py`
- `pytest -q tests/test_approval_auth_contract.py tests/test_pending_workflow_state.py tests/test_browser_isolation.py tests/test_specialist_handoffs.py tests/test_android_chat_language.py`

Ergebnis:

- `23 passed` im gezielten Contract-/Browser-Ring
- `80 passed` im breiten D5-/Phase-D-Ring
- `py_compile` gruen

## Fortschritt 2026-04-09 - Phase D4.2 echte Reuse-Priorisierung

Mit D4.1 konnte Timus erfolgreiche Logins erstmals als `auth_session`-Zustand speichern. Es fehlte aber noch die eigentliche Priorisierung: ein vorhandener Session-Anker wurde im Login-Pfad noch nicht wirklich vor einem neuen Login-Versuch bevorzugt.

Nachgezogen:

- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - der `visual_login`-Wrapper behaelt `auth_session_*`-Felder aus einem Follow-up-Kontext jetzt bei
  - bei augmentierten Queries wird fuer `source_url` jetzt die eigentliche `# CURRENT USER QUERY` bevorzugt, nicht versehentlich eine frueher gespeicherte `auth_session_url`
- [auth_session_state.py](/home/fatih-ubuntu/dev/timus/orchestration/auth_session_state.py)
  - `session_reused` bleibt jetzt als eigener Status erhalten
  - neue Reuse-Pruefung:
    - `is_auth_session_reusable(...)`
  - abgelaufene oder service-falsche Sessions werden damit konservativ ausgeschlossen
- [visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
  - `visual` kann jetzt `auth_session_*`-Kontext aus Handoff oder Follow-up lesen
  - bei `login_flow` wird jetzt zuerst ein echter Reuse-Versuch auf die bereits bestaetigte authentische Seite gemacht
  - nur bei gescheitertem Reuse faellt Timus auf den normalen user-mediated Login-Flow zurueck
  - erfolgreiche Wiederverwendung emittiert jetzt explizit:
    - `kind=auth_session`
    - `auth_session_status=session_reused`
- [test_dispatcher_camera_intent.py](/home/fatih-ubuntu/dev/timus/tests/test_dispatcher_camera_intent.py)
  - neue Regression:
    - `visual_login`-Handoff behaelt `auth_session_*`-Felder sauber bei
- [test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
  - neue Regression:
    - vorhandene GitHub-Session wird vor neuem Login-Versuch wiederverwendet
- [test_auth_session_state.py](/home/fatih-ubuntu/dev/timus/tests/test_auth_session_state.py)
  - neue D4.2-Vertragstests fuer `session_reused` und Expiry-Pruefung

Verifikation:

- `python -m py_compile orchestration/auth_session_state.py main_dispatcher.py agent/agents/visual.py tests/test_auth_session_state.py tests/test_dispatcher_camera_intent.py tests/test_specialist_handoffs.py`
- `pytest -q tests/test_auth_session_state.py tests/test_dispatcher_camera_intent.py tests/test_specialist_handoffs.py`
- `pytest -q tests/test_approval_auth_contract.py tests/test_pending_workflow_state.py tests/test_auth_session_state.py tests/test_dispatcher_camera_intent.py tests/test_phase_d_chat_rendering.py tests/test_browser_isolation.py tests/test_android_chat_language.py tests/test_specialist_context_runtime.py tests/test_specialist_handoffs.py`

Ergebnis:

- `38 passed` im fokussierten D4.2-Ring
- `100 passed` im breiteren Phase-D-/Browser-/Dispatcher-Ring
- `py_compile` gruen

## Fortschritt 2026-04-09 - Phase D4.1 Auth Session Reuse gestartet

Nach D3 konnte Timus Login-Workflows sauber bis zur Login-Maske fuehren und nach `weiter` / `ich bin eingeloggt` kontrolliert wieder aufnehmen. Es fehlte aber noch ein expliziter Zustand fuer erfolgreich bestaetigte authentische Sessions. Ohne diesen Zustand blieb Session-Reuse implizit im Browser-Kontext, aber nicht sichtbar, nicht kapselbar und nicht sauber an spaetere Workflows bindbar.

Nachgezogen:

- [auth_session_state.py](/home/fatih-ubuntu/dev/timus/orchestration/auth_session_state.py)
  - neues D4.1-Modul fuer normalisierte auth-session-Eintraege
  - speichert pro Dienst konservativ:
    - `service`
    - `status`
    - `scope`
    - `url`
    - `workflow_id`
    - `browser_session_id`
    - `confirmed_at`
    - `expires_at`
    - `reuse_ready`
    - `evidence`
- [visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
  - bestaetigte resumed Logins emittieren jetzt ein strukturiertes `auth_session_ready`-Signal
  - damit wird ein erfolgreicher user-mediated Login nicht nur als Text bestaetigt, sondern auch als wiederverwendbarer Session-Anker an den Runtime-Pfad gemeldet
- [mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - Session-Capsules speichern jetzt `auth_sessions`
  - neuer Store-Pfad:
    - `_store_auth_session_in_capsule(...)`
  - Follow-up-Capsules tragen jetzt zusaetzlich:
    - `auth_sessions`
    - `latest_auth_session`
  - der serialisierte Follow-up-Kontext traegt jetzt explizit:
    - `auth_session_service`
    - `auth_session_status`
    - `auth_session_scope`
    - `auth_session_url`
    - `auth_session_confirmed_at`
    - `auth_session_expires_at`
  - neues Observation-Event:
    - `auth_session_updated`
- [test_auth_session_state.py](/home/fatih-ubuntu/dev/timus/tests/test_auth_session_state.py)
  - neue D4.1-Vertragstests fuer Normalisierung, Upsert und Latest-Auswahl
- [test_android_chat_language.py](/home/fatih-ubuntu/dev/timus/tests/test_android_chat_language.py)
  - neue Regression:
    - auth-session roundtrip ueber Session-Capsule und Follow-up-Kontext
- [test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
  - neue Regression:
    - erfolgreicher resumed Login emittiert `kind=auth_session`

Verifikation:

- `python -m py_compile orchestration/auth_session_state.py server/mcp_server.py agent/agents/visual.py tests/test_auth_session_state.py tests/test_android_chat_language.py tests/test_specialist_handoffs.py`
- `pytest -q tests/test_auth_session_state.py tests/test_android_chat_language.py tests/test_specialist_handoffs.py`
- `pytest -q tests/test_approval_auth_contract.py tests/test_pending_workflow_state.py tests/test_auth_session_state.py tests/test_phase_d_chat_rendering.py tests/test_browser_isolation.py tests/test_android_chat_language.py tests/test_specialist_context_runtime.py tests/test_specialist_handoffs.py`

Ergebnis:

- `52 passed` im fokussierten D4.1-/D3-Ring
- `85 passed` im breiteren Phase-D-/Browser-/Capsule-Ring
- `py_compile` gruen

## Fortschritt 2026-04-09 - Zielblock Credential Broker statt Secret Exposure eingeordnet

Fuer spaetere Login-Assistenz reicht es nicht, Timus einfach alle Nutzernamen und Passwoerter zu geben. Das waere architektonisch die falsche Richtung, besonders wenn die Zugangsdaten praktisch bereits im Chrome-Passwortmanager liegen.

Neu eingeordnet:

- [CREDENTIAL_BROKER_CHROME_PASSWORD_MANAGER_PLAN.md](/home/fatih-ubuntu/dev/timus/docs/CREDENTIAL_BROKER_CHROME_PASSWORD_MANAGER_PLAN.md)
  - neuer Zielblock fuer:
    - **Chrome als Credential Broker**
    - **Timus ohne Roh-Secrets**
    - domain- und workflow-gebundene Freigaben
    - Session-Reuse vor erneuter Credential-Nutzung
    - user-mediated 2FA/CAPTCHA auch im Broker-Modell
- [PHASE_D_APPROVAL_AUTH_PREP.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D_APPROVAL_AUTH_PREP.md)
  - `D4 Auth Session Reuse` traegt jetzt einen spaeteren Unterblock:
    - **D4b Chrome Credential Broker**
  - zusaetzlich explizit festgehalten:
    - kein Export aus dem Chrome-Passwortmanager in Timus

Einordnung:

- der Block gehoert **in spaete Phase D**
- nicht in Phase E
- weil es um Approval/Auth/Login-Assistenz geht, nicht um Self-Improvement

## Fortschritt 2026-04-09 - Phase D3.1 User-mediated Login gestartet

Phase D hatte nach D1/D2 bereits strukturierte Approval-/Auth-Blocker und sichtbare Pending-Workflows, aber noch keinen echten user-mediated Login-Laufzeitpfad. Login-Workflows konnten daher weiter wie normale Browser-Aufgaben behandelt werden und haetten Benutzername/Passwort/Submit zu weit automatisiert.

Nachgezogen:

- [approval_auth_contract.py](/home/fatih-ubuntu/dev/timus/orchestration/approval_auth_contract.py)
  - `build_awaiting_user_workflow_payload(...)` traegt jetzt auch `url` und `reason`
  - neues D3-Helper-Builder:
    - `build_user_mediated_login_workflow_payload(...)`
  - erzeugt einen klaren `awaiting_user`-Workflow fuer Login-Masken mit:
    - `reason = user_mediated_login`
    - `step = login_form_ready`
    - Resume-Hinweis fuer `weiter` / `ich bin eingeloggt`
- [visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
  - Login-Flows stoppen jetzt bewusst an der verifizierten Login-Maske statt Username/Passwort/Submit blind weiter abzuarbeiten
  - `visual` emittiert dafuer einen echten Blocker in den bestehenden Pending-Workflow-/C4-Pfad
  - der neue Workflow liefert:
    - `awaiting_user`
    - `service`
    - `url`
    - `user_action_required`
    - `resume_hint`
  - Browser-Plan-Aufbau nutzt jetzt auch die bereits uebergebene `source_url`, nicht nur URLs aus dem Goal-Text
- [agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
  - Phase-D-Workflow-Returns wie `approval_required`, `auth_required`, `awaiting_user` und `challenge_required` werden jetzt als `partial` statt als Erfolg klassifiziert
  - strukturierte Workflow-Metadaten werden in Delegationsergebnissen mitgefuehrt:
    - `phase_d_workflow`
    - `workflow_id`
    - `workflow_status`
    - `workflow_service`
- [tests/test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
  - neue D3-Regression:
    - `visual` stoppt bei `github.com/login` an der Login-Maske und liefert `awaiting_user` plus Progress-Blocker
- [tests/test_specialist_context_runtime.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_context_runtime.py)
  - neue D3-Regression:
    - Agent-Registry behandelt Phase-D-Workflow-Rueckgaben als partiellen Workflow und behaelt die strukturierten Metadaten
- [tests/test_approval_auth_contract.py](/home/fatih-ubuntu/dev/timus/tests/test_approval_auth_contract.py)
  - neuer Vertragstest fuer `build_user_mediated_login_workflow_payload(...)`

Verifikation:

- `python -m py_compile orchestration/approval_auth_contract.py agent/agent_registry.py agent/agents/visual.py tests/test_approval_auth_contract.py tests/test_specialist_context_runtime.py tests/test_specialist_handoffs.py`
- `pytest -q tests/test_approval_auth_contract.py tests/test_specialist_context_runtime.py tests/test_specialist_handoffs.py`
- `pytest -q tests/test_browser_workflow_plan.py tests/test_approval_auth_contract.py tests/test_specialist_context_runtime.py tests/test_specialist_handoffs.py tests/test_pending_workflow_state.py tests/test_browser_isolation.py`

Ergebnis:

- `29 passed` im direkten D3-Ring
- `53 passed` im breiteren Browser-/Phase-D-/Pending-Workflow-Ring
- `py_compile` gruen

## Fortschritt 2026-04-09 - Phase D3.2 Resume fuer user-mediated Login

D3.1 konnte Login-Workflows kontrolliert an der Login-Maske stoppen, aber der eigentliche Rueckweg fehlte noch: `weiter`, `ich bin eingeloggt` oder Hinweise auf CAPTCHA/2FA waren noch nicht als gezielte Wiederaufnahme desselben Login-Workflows verdrahtet.

Nachgezogen:

- [pending_workflow_state.py](/home/fatih-ubuntu/dev/timus/orchestration/pending_workflow_state.py)
  - neue Resume-Klassifikation fuer Pending-Workflow-Antworten:
    - `resume_requested`
    - `challenge_present`
    - `resume_blocked`
  - typische D3-Faelle wie `ich bin eingeloggt`, `weiter`, `ich sehe jetzt eine 2fa challenge` werden jetzt strukturiert erkannt
- [mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - Follow-up-Capsules tragen jetzt zusaetzlich:
    - `pending_workflow_reply`
    - `pending_workflow_id`
    - `pending_workflow_url`
    - `pending_workflow_source_agent`
    - `pending_workflow_source_stage`
    - `pending_workflow_reply_kind`
  - fuer offene `awaiting_user`-Login-Workflows wird bei Resume-Sprache jetzt der urspruengliche Source-Agent bevorzugt
  - wenn derselbe Agent den Login-Workflow erfolgreich wieder aufnimmt und keinen neuen Blocker setzt, wird der offene Pending-Workflow wieder sauber geloescht
- [visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
  - neuer Resume-Pfad fuer `user_mediated_login`
  - `visual` kann jetzt aus dem Follow-up-Kontext lesen:
    - welcher Login-Workflow offen ist
    - ob der Nutzer `weiter` / `ich bin eingeloggt` signalisiert
    - ob stattdessen eine Challenge/2FA im Weg ist
  - bei Resume:
    - erfolgreicher Login wird ueber sichtbare Screen-Signale validiert
    - Challenges werden wieder als strukturierter `challenge_required`-Workflow zurueckgemeldet
    - unklare/gescheiterte Resume-Faelle bleiben als `awaiting_user` sichtbar statt still ins Leere zu laufen
- [tests/test_pending_workflow_state.py](/home/fatih-ubuntu/dev/timus/tests/test_pending_workflow_state.py)
  - neue Resume-/Challenge-Vertragstests
- [tests/test_android_chat_language.py](/home/fatih-ubuntu/dev/timus/tests/test_android_chat_language.py)
  - neue Regression:
    - `ich bin eingeloggt` bei offenem Login-Workflow praeselektiert jetzt den `visual`-Resume-Pfad und serialisiert den Reply-Kind in den Follow-up-Kontext
- [tests/test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
  - neue Regression:
    - `visual` bestaetigt einen resumed Login bei erfolgreicher Screen-Validierung statt wieder an der Login-Maske stehenzubleiben

Verifikation:

- `python -m py_compile orchestration/pending_workflow_state.py server/mcp_server.py agent/agents/visual.py tests/test_pending_workflow_state.py tests/test_android_chat_language.py tests/test_specialist_handoffs.py`
- `pytest -q tests/test_pending_workflow_state.py tests/test_android_chat_language.py tests/test_specialist_handoffs.py`
- `pytest -q tests/test_browser_workflow_plan.py tests/test_approval_auth_contract.py tests/test_pending_workflow_state.py tests/test_android_chat_language.py tests/test_specialist_context_runtime.py tests/test_specialist_handoffs.py tests/test_browser_isolation.py`

Ergebnis:

- `52 passed` im direkten D3-Resume-Ring
- `84 passed` im breiteren Browser-/Phase-D-/Pending-Workflow-Ring
- `py_compile` gruen

## Fortschritt 2026-04-09 - Phase D2.2 Pending-Workflow sichtbar in Telegram und Canvas

Mit D2.1 hatte Timus bereits einen echten Pending-Workflow-Zustand pro Session, aber dieser blieb noch weitgehend intern. Telegram und Canvas sahen weiter nur allgemeine Blocker, nicht den eigentlichen Approval-/Auth-Workflow mit Status, Service und naechstem Nutzerschritt.

Nachgezogen:

- [gateway/telegram_gateway.py](/home/fatih-ubuntu/dev/timus/gateway/telegram_gateway.py)
  - der Telegram-Chat haengt sich jetzt waehrend eines Requests an den echten Agent-Progress-Hook
  - strukturierte Pending-Workflows aus `approval_required`, `auth_required`, `awaiting_user` und `challenge_required` werden direkt eingesammelt
  - Antworten zeigen jetzt sichtbare Nutzerhinweise wie:
    - `Offener Schritt: Login erforderlich · x`
    - `Bitte bestaetige den Zugriff.`
    - optional `Weiter danach: ...`
    - optional `Challenge: ...`
  - neue Observation-Events:
    - `pending_workflow_updated`
    - `pending_workflow_visible`
  - Feedback-Kontext traegt jetzt zusaetzlich:
    - `pending_workflow_status`
    - `pending_workflow_service`
- [orchestration/longrunner_transport.py](/home/fatih-ubuntu/dev/timus/orchestration/longrunner_transport.py)
  - der C4-Transportvertrag traegt Blocker jetzt nicht mehr nur mit `blocker_reason` und `user_action_required`, sondern auch mit echten Workflow-Feldern:
    - `workflow_id`
    - `workflow_status`
    - `workflow_service`
    - `workflow_reason`
    - `workflow_message`
    - `workflow_resume_hint`
    - `workflow_challenge_type`
    - `workflow_approval_scope`
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - der MCP-Progresspfad reicht die strukturierten Workflow-Felder jetzt in Longrunner-/SSE-Events durch
  - dadurch bleiben Approval-/Auth-/Challenge-Blocker ueber Canvas und andere C4-Konsumenten sichtbar und maschinenlesbar
- [server/canvas_ui.py](/home/fatih-ubuntu/dev/timus/server/canvas_ui.py)
  - Canvas Runtime zeigt Pending-Workflow-Status jetzt explizit an
  - Preview bevorzugt jetzt:
    - `user_action_required`
    - `workflow_message`
    - `workflow_resume_hint`
    - `workflow_challenge_type`
  - damit wirken Approval-/Awaiting-User-Zustaende nicht mehr wie generische Runtime-Blocker
- [tests/test_telegram_feedback_gateway.py](/home/fatih-ubuntu/dev/timus/tests/test_telegram_feedback_gateway.py)
  - neue Regression:
    - Telegram surfacet einen echten `auth_required`-Blocker sichtbar im Replytext und traegt den Zustand in den Feedback-Kontext
- [tests/test_longrunner_transport_contract.py](/home/fatih-ubuntu/dev/timus/tests/test_longrunner_transport_contract.py)
  - neue Regression:
    - Blocker-Events behalten die neuen Workflow-Felder im C4-Transportvertrag bei

Verifikation:

- `python -m py_compile gateway/telegram_gateway.py orchestration/longrunner_transport.py server/mcp_server.py server/canvas_ui.py tests/test_telegram_feedback_gateway.py tests/test_longrunner_transport_contract.py`
- `pytest -q tests/test_telegram_feedback_gateway.py tests/test_longrunner_transport_contract.py tests/test_c4_longrunner_runtime.py tests/test_pending_workflow_state.py tests/test_android_chat_language.py`

Ergebnis:

- `45 passed` im fokussierten D2.2-/Telegram-/Canvas-/Workflow-Ring
- `py_compile` gruen

## Fortschritt 2026-04-09 - Phase D2.1 Pending-Workflow-State gestartet

Der erste D-Block hatte bereits normalisierte `auth_required`- und `challenge_required`-Payloads, aber noch keinen echten turn-uebergreifenden Pending-Zustand. Damit gingen offene Freigabe-/Auth-Schritte nur als fluechtiger Blocker durch den aktuellen Lauf.

Nachgezogen:

- [pending_workflow_state.py](/home/fatih-ubuntu/dev/timus/orchestration/pending_workflow_state.py)
  - neues D2.1-Modul fuer einen normalisierten Session-Zustand:
    - `approval_required`
    - `auth_required`
    - `awaiting_user`
    - `challenge_required`
  - speichert dazu:
    - `workflow_id`
    - `workflow_kind`
    - `service`
    - `reason`
    - `message`
    - `user_action_required`
    - `resume_hint`
    - `challenge_type`
    - `approval_scope`
    - `source_agent`
    - `source_stage`
- [mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - Session-Capsules normalisieren und speichern jetzt `pending_workflow`
  - der echte Agent-Progress-Hook schreibt Pending-Workflows direkt aus strukturierten Blocker-Payloads in die Capsule
  - neue Observation-Events:
    - `pending_workflow_updated`
    - `pending_workflow_cleared`
  - Follow-up-Capsules serialisieren den offenen Pending-Workflow jetzt explizit in den Kontextblock
  - kurze Antworten wie `ja`, `mach weiter` oder aehnliche knappe Reaktionen bleiben damit auch ohne `pending_followup_prompt` an einem offenen Approval-/Auth-Zustand verankert

## Fortschritt 2026-04-09 - Telegram/Mail-Observability nachgezogen

Der Telegram-Chat hat einen echten Mailversand bestaetigt, waehrend im Observation-Log fuer denselben Request nur `chat_request_completed` sichtbar war. Der Versandpfad funktionierte also, aber die Laufzeitbeobachtung war zu duenn.

Nachgezogen:

- [agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
  - der echte `communication`-Delegationspfad emittiert jetzt explizit:
    - `communication_task_started`
    - `communication_task_completed`
    - `communication_task_partial`
    - `communication_task_failed`
    - `send_email_succeeded`
    - `send_email_failed`
  - die Events tragen Request-/Session-Korrelation, Kanal (`email`), Empfaenger, Betreff/Anhang-Hinweise und Backend, soweit aus Handoff oder Tool-Ergebnis belegbar
  - Telegram-/Canvas-Quelle wird aus Session-/Request-Korrelation sauber abgeleitet, statt spaeter nur an `chat_request_completed` haengen zu bleiben
- [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neuer Summary-Block `communication_runtime`
  - zaehlt jetzt:
    - gestartete/abgeschlossene/partielle/fehlgeschlagene Communication-Tasks
    - erfolgreiche/fehlgeschlagene E-Mail-Sendungen
    - Verteilung nach Backend und Kanal
  - Markdown-Render zeigt die neue Communication-/Mail-Sicht jetzt explizit an
- [test_specialist_context_runtime.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_context_runtime.py)
  - neue Regression:
    - erfolgreicher `communication`-Delegationspfad emittiert `communication_task_started`, `communication_task_completed` und `send_email_succeeded` mit korrekter Request-/Session-Korrelation
- [test_autonomy_observation.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation.py)
  - neue Regression:
    - Summary und Markdown enthalten den neuen `Communication Runtime`-Block inklusive Backend-/E-Mail-Counter

Verifikation:

- `python -m py_compile agent/agent_registry.py orchestration/autonomy_observation.py tests/test_specialist_context_runtime.py tests/test_autonomy_observation.py`
- `pytest -q tests/test_specialist_context_runtime.py tests/test_autonomy_observation.py`
- `pytest -q tests/test_telegram_feedback_gateway.py tests/test_meta_handoff.py tests/test_specialist_handoffs.py`

Ergebnis:

- `10 passed` im direkten Mail-/Observation-Ring
- `27 passed` im breiteren Telegram-/Meta-/Specialist-Handoff-Ring

## Fortschritt 2026-04-08 - D0.8 Historical Recall nach Review nachgehaertet

Ein Review der letzten D0.8-Commits hat drei echte Fehler im Historical-Recall-Pfad offengelegt:

- das reine Vorkommen von `eben`/`vorhin`/`kuerzlich` konnte normale Arbeitsanweisungen faelschlich als historische Rueckfrage markieren
- bei gleicher Relevanz wurden in `recent_moment`-Faellen aeltere Topics vor neueren bevorzugt
- generische Rueckfragen wie `was wir letztes Mal besprochen hatten` konnten trotz vorhandener History leer zurueckkommen

Nachgehaertet:

- [orchestration/topic_state_history.py](/home/fatih-ubuntu/dev/timus/orchestration/topic_state_history.py)
  - `recent_moment` wird jetzt nicht mehr durch blosses `eben` getriggert, sondern nur noch mit echtem Recall-Kontext
    - Beispiele: `weisst du noch ...`, `was habe ich eben gesagt`, `von eben`
  - die History-Auswahl sortiert bei gleichem Score jetzt neuere Eintraege vor aelteren
  - generische Gespraechsverben wie `besprochen`, `gesagt`, `geschrieben`, `gearbeitet`, `geantwortet` zaehlen nicht mehr als kuenstliche Fokus-Terme
- [tests/test_topic_state_history.py](/home/fatih-ubuntu/dev/timus/tests/test_topic_state_history.py)
  - neue Regression:
    - plain recent-time reference (`ich habe dir eben einen link gegeben ...`) darf kein Historical-Recall sein
  - neue Regression:
    - `recent_moment` bevorzugt den neueren Treffer
  - neue Regression:
    - `weisst du noch was wir letztes mal besprochen hatten` liefert wieder einen Treffer
- [tests/test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
  - neue Regression:
    - plain `eben`-Action-Query darf nicht in `meta_policy:historical_topic_recall` kippen

Verifikation:

- `python -m py_compile orchestration/topic_state_history.py tests/test_topic_state_history.py tests/test_meta_orchestration.py`
- `pytest -q tests/test_topic_state_history.py tests/test_meta_orchestration.py`
- `pytest -q tests/test_topic_state_history_hypothesis.py tests/test_topic_state_history_contracts.py`
- `python -m crosshair check tests/test_topic_state_history_contracts.py`

Ergebnis:

- `68 passed` im fokussierten D0.8-/Meta-Ring
- `9 passed` im D0.8-Hypothesis-/Contract-Ring
- `CrossHair` gruen

---

## Fortschritt 2026-04-06 - Telegram-Observability parity und generische Preisfragen entkoppelt

Zwei Telegram-/Lookup-Probleme sind jetzt geschlossen:

- Telegram-Chatlaeufe hatten im Observation-Log nur Dispatcher-Eintraege ohne volle Request-Kette
- generische Preisfragen wie Benzin-, Zug- oder Marktpreise kippten im Executor in den spezialisierten LLM-Preis-Pfad und erzeugten dadurch kontextfremde Antworten

Umgesetzt:

- [gateway/telegram_gateway.py](/home/fatih-ubuntu/dev/timus/gateway/telegram_gateway.py)
  - Telegram-Text- und Voice-Queries erzeugen jetzt eigene `request_id`
  - Telegram loggt jetzt dieselben Kernereignisse wie Canvas:
    - `chat_request_received`
    - `request_route_selected`
    - `chat_request_completed`
    - `chat_request_failed`
  - die Request-Korrelation wird per `bind_request_correlation(...)` in den Dispatcher-Lauf gebunden
  - dadurch tragen auch Telegram-Dispatcher-Events jetzt `request_id` statt leerer Korrelation
- [agent/agents/executor.py](/home/fatih-ubuntu/dev/timus/agent/agents/executor.py)
  - generische Preisfragen bleiben `web_lookup`
  - nur echte Modell-/API-Preisfragen mit LLM-/Token-/Provider-Signalen gehen in den spezialisierten `pricing`-Pfad
  - Kontext-Follow-ups zu bereits gefundenen LLM-Preisquellen bleiben weiterhin korrekt im Pricing-Pfad
- [tests/test_telegram_feedback_gateway.py](/home/fatih-ubuntu/dev/timus/tests/test_telegram_feedback_gateway.py)
  - Regression fuer Telegram-Request-Lifecycle mit stabiler `request_id`
- [tests/test_executor_live_lookup.py](/home/fatih-ubuntu/dev/timus/tests/test_executor_live_lookup.py)
  - Regression dafuer, dass generische Preisfragen nicht mehr in LLM-Pricing kippen
  - Regression dafuer, dass Pricing-Follow-ups aus vorhandenem LLM-Kontext weiter funktionieren

Verifikation:

- `python -m py_compile gateway/telegram_gateway.py agent/agents/executor.py tests/test_telegram_feedback_gateway.py tests/test_executor_live_lookup.py`
- `pytest -q tests/test_telegram_feedback_gateway.py tests/test_executor_live_lookup.py`

Ergebnis:

- Telegram-Chats sind jetzt im Observation-Log request-korreliert nachvollziehbar
- Preisfragen bleiben thematisch beim Nutzerkontext statt in LLM-Preisvergleichen zu landen

---

## Fortschritt 2026-04-06 - Meta-first Greeting Routing fuer substantielle Fragen

Ein Gruess-/Anredepraefix darf nicht mehr dazu fuehren, dass eine echte inhaltliche Frage vorzeitig in `executor`-Smalltalk endet. Der semantische Kern soll erst von `meta` bewertet werden, wenn nach dem Praefix mehr als nur phatischer Smalltalk uebrig bleibt.

Umgesetzt:

- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - `EXECUTOR_KEYWORDS` werden im Quick-Intent jetzt gegen den analysierten Kern (`analysis_query`) statt blind gegen die volle Eingabe geprueft
  - neuer Guard fuer greeting-prefixed, aber nicht-triviale Kernfragen:
    - Beispiel: `hi timus wie stehts um die aktuelle weltlage`
    - Ergebnis: nicht mehr frueher `executor`, sondern `meta`
  - triviale Lookups mit Gruesspraefix bleiben direkt auf `executor`
    - Beispiel: `hi timus wie spaet ist es`
- [agent/agents/executor.py](/home/fatih-ubuntu/dev/timus/agent/agents/executor.py)
  - Smalltalk-Muster sind jetzt auf echte phatische Kurzaeusserungen begrenzt
  - ein bloesser Treffer auf `hi` oder `hallo` irgendwo in einer kurzen Frage reicht nicht mehr
  - greeting-prefixed Sachfragen fallen dadurch nicht mehr in `Ich bin da. Sag direkt, was du brauchst.`
- [tests/test_dispatcher_self_status_routing.py](/home/fatih-ubuntu/dev/timus/tests/test_dispatcher_self_status_routing.py)
  - neue Regression:
    - `hi timus wie stehts um die aktuelle weltlage` -> `meta`
  - bestaetigt weiter:
    - `hi timus wie spaet ist es` -> `executor`
- [tests/test_executor_smalltalk.py](/home/fatih-ubuntu/dev/timus/tests/test_executor_smalltalk.py)
  - neue Regression:
    - greeting-prefixed Sachfrage wird nicht als Smalltalk verschluckt

Verifikation:

- `python -m py_compile main_dispatcher.py agent/agents/executor.py tests/test_dispatcher_self_status_routing.py tests/test_executor_smalltalk.py`
- `pytest -q tests/test_dispatcher_self_status_routing.py tests/test_executor_smalltalk.py`

Ergebnis:

- `meta` sieht jetzt den semantischen Kern solcher Anfragen
- `executor` beantwortet nur noch echte Kurzgruesse/Social-Smalltalk direkt
- der konkrete Fehlfall aus dem Canvas-Lauf ist damit auf Code- und Testebene geschlossen

---

## Fortschritt 2026-04-06 - C4 Langlaeufer-/Antwortpfade abgeschlossen

`C4` ist jetzt nicht mehr nur vorbereitet, sondern im Canvas-/SSE-Runtime-Pfad aktiv.

Umgesetzt:

- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - `/chat` bindet jetzt einen echten `run_id`-Kontext
  - emittiert strukturierte C4-Transportevents:
    - `run_started`
    - `progress`
    - `partial_result`
    - `blocker`
    - `run_completed`
    - `run_failed`
  - Delegations- und Top-Level-Agent-Progress werden in denselben SSE-Vertrag ueberfuehrt
  - alte Test-Callsites ohne `request_id` in `get_agent_decision(...)` bleiben kompatibel
- [orchestration/longrunner_transport.py](/home/fatih-ubuntu/dev/timus/orchestration/longrunner_transport.py)
  - Runtime-Bindung fuer `run_id`
  - monotone `seq`-Vergabe pro Nutzerlauf
- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
  - delegierter `executor`-Progress laeuft nicht mehr nur in den Watchdog
  - partielle Research-Outcomes werden als `partial_result` weitergegeben
  - Blocker-Payloads koennen jetzt aus Delegation nach aussen emittiert werden
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - Top-Level-Agenten koennen ueber denselben Callback strukturierte C4-Progress-Signale liefern
- [agent/agents/executor.py](/home/fatih-ubuntu/dev/timus/agent/agents/executor.py)
  - `auth_required` / `user_action_required` werden als Blocker-Signal nach aussen gemeldet
- [agent/visual_nemotron_agent_v4.py](/home/fatih-ubuntu/dev/timus/agent/visual_nemotron_agent_v4.py)
  - Visual-Planpfad meldet jetzt Start-/Schritt-/Blocker-Progress ueber denselben C4-Kanal
- [tests/test_longrunner_transport_contract.py](/home/fatih-ubuntu/dev/timus/tests/test_longrunner_transport_contract.py)
  - Sequenz-/Bindungs-Regressionsfall fuer `run_id`/`seq`
- [tests/test_c4_longrunner_runtime.py](/home/fatih-ubuntu/dev/timus/tests/test_c4_longrunner_runtime.py)
  - Runtime-Regressionen fuer:
    - `/chat` Start/Progress/Completion
    - `/chat` Failure
    - Delegations-Blocker
    - Delegations-Partial
    - Visual-Step-Blocker
- [server/canvas_ui.py](/home/fatih-ubuntu/dev/timus/server/canvas_ui.py)
  - Canvas zeigt C4 jetzt auch sichtbar:
    - Runtime-Statuskarte im Chat-Panel
    - klarere Topbar-LED fuer laufend / partiell / blockiert / fertig / Fehler
    - Fortschrittstexte, Blocker-Hinweise und Teilergebnis-Vorschau direkt im Canvas
- [tests/test_canvas_ui_c4_runtime.py](/home/fatih-ubuntu/dev/timus/tests/test_canvas_ui_c4_runtime.py)
  - UI-Regression fuer:
    - Runtime-Strip
    - C4-Event-Handler im Canvas

Verifikation:

- `python -m py_compile orchestration/longrunner_transport.py agent/agent_registry.py main_dispatcher.py agent/agents/executor.py agent/visual_nemotron_agent_v4.py server/mcp_server.py tests/test_longrunner_transport_contract.py tests/test_c4_longrunner_runtime.py`
- `pytest -q tests/test_longrunner_transport_contract.py tests/test_c4_longrunner_runtime.py`
- `pytest -q tests/test_android_chat_language.py tests/test_executor_delegation_stability.py tests/test_delegation_hardening.py tests/test_longrunner_transport_contract.py tests/test_c4_longrunner_runtime.py`
- `pytest -q tests/test_c2_entrypoints.py`

Ergebnis:

- Phase C ist damit funktional geschlossen
- der naechste groessere Block ist Phase D
- C4-Transport ist bewusst als gemeinsamer Vertrag angelegt, damit Approval-/Auth-/Handover spaeter nicht als Sonderpfad daneben entstehen

---

## Fortschritt 2026-04-06 - C4 und Phase-D-Vorlauf vorbereitet

Der naechste offene Runtime-Block nach C3 ist `C4 Langlaeufer-/Antwortpfade`. Parallel dazu braucht der spaetere Phase-D-Start einen sauberen Approval-/Auth-/Handover-Rahmen.

Neu angelegt:

- [docs/C4_LONGRUNNER_RESPONSE_PREP.md](/home/fatih-ubuntu/dev/timus/docs/C4_LONGRUNNER_RESPONSE_PREP.md)
  - konkreter Arbeitsplan fuer:
    - Progress-/Blocker-/Partial-Transport
    - Nutzung des bestehenden Delegation-Progress im `agent_registry`
    - Canvas/SSE als erster Zielpfad
    - Einbindung von `executor`, `research`, `visual_nemotron`
- [docs/PHASE_D_APPROVAL_AUTH_PREP.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D_APPROVAL_AUTH_PREP.md)
  - konkreter Vorlauf fuer:
    - `D1 Auth Need Detection`
    - `D2 Approval + Consent Gate`
    - `D3 User-mediated Login`
    - `D4 Auth Session Reuse`
    - `D5 Challenge Handover`
  - vereinheitlichte Ziel-Payloads fuer:
    - `approval_required`
    - `auth_required`
    - `awaiting_user`
    - `challenge_required`
- [orchestration/longrunner_transport.py](/home/fatih-ubuntu/dev/timus/orchestration/longrunner_transport.py)
  - konkreter Code-Vertrag fuer:
    - gemeinsames Envelope
    - feste C4-Event-Typen
    - Builder-Helper
    - Validierung
- [tests/test_longrunner_transport_contract.py](/home/fatih-ubuntu/dev/timus/tests/test_longrunner_transport_contract.py)
  - Regression fuer:
    - stabiles Envelope
    - unbekannte Event-Typen
    - Blocker-/Partial-/Failure-Invarianten

Wichtige Setzung:

- `C4` bleibt der letzte echte offene Block in Phase C
- Phase D wird vorbereitet, aber nicht vorgezogen
- Approval-/Auth-/Challenge-Logik soll auf den spaeteren C4-Transport aufsetzen, nicht als paralleles Sonderprotokoll daneben entstehen

---

## Fortschritt 2026-04-06 - C3 Vision/OCR Hot-Path gehaertet

### Problemstellung

Drei Engines (OCR, ObjectDetection, Segmentation) hatten:
- Kein OOM-Recovery: CUDA-out-of-memory schlug still fehl, kein Logging, kein Cleanup
- Kein Timing: Inferenz-Dauer war nicht messbar
- Keine Telemetrie: Device, Modell, Fallback-Grund waren nicht nachvollziehbar
- Keine expliziten Routing-Regeln: Florence-2 vs. OCR-allein wurde implizit entschieden

### Umgesetzt

- [tools/engines/vision_telemetry.py](/home/fatih-ubuntu/dev/timus/tools/engines/vision_telemetry.py) (neu)
  - `VisionTelemetryRecorder` Singleton — thread-sicherer Ring-Puffer (MAX_EVENTS=500)
  - Phases: INIT_START, INIT_DONE, INFER_START, INFER_DONE, DEVICE_CHANGE, FALLBACK, OOM, ERROR
  - Convenience-Methoden: `init_start/done`, `infer_start/done`, `fallback`, `oom`, `error`
  - `get_summary()` gibt per-Engine-Stats zurueck (Inferenz-Count, Fehler, OOM-Zaehler)
  - Emittiert C2-Observability fuer INIT_DONE, OOM, FALLBACK, ERROR (best-effort)
  - `is_oom_error(exc)` erkennt CUDA-OOM-RuntimeError zuverlaessig

- [tools/engines/vision_router.py](/home/fatih-ubuntu/dev/timus/tools/engines/vision_router.py) (neu)
  - `VisionStrategy` Enum: OCR_ONLY, FLORENCE2_PRIMARY, FLORENCE2_HYBRID, CPU_FALLBACK_ONLY
  - `select_vision_strategy(image_w, image_h, task_type, vram_available_mb)` — 7 priorisierte Regeln:
    1. VRAM < VRAM_MIN (default 1500MB) → CPU_FALLBACK_ONLY
    2. task=ui_detection → FLORENCE2_PRIMARY
    3. Bild > 2MP + VRAM >= 3000MB → FLORENCE2_PRIMARY
    4. Bild <= 0.5MP → OCR_ONLY
    5. Bild > 0.5MP + VRAM >= 2000MB → FLORENCE2_HYBRID
    6. VRAM >= 2000MB, Bild unbekannt → FLORENCE2_PRIMARY
    7. Default → OCR_ONLY
  - `get_vram_available_mb()` — CUDA mem_get_info, gibt 0 zurueck wenn kein GPU
  - Schwellenwerte konfigurierbar per .env: VISION_VRAM_MIN_MB, VISION_VRAM_LO_MB, VISION_VRAM_HI_MB
  - Router wirft nie — Exception im Router → OCR_ONLY als sicherster Fallback

- [tools/florence2_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/florence2_tool/tool.py)
  - `florence2_full_analysis` und `florence2_hybrid_analysis` laufen jetzt ueber `_analyze_with_c3_routing(...)`
  - der produktive Screenshot-Hot-Path respektiert damit nun `VisionStrategy` statt Florence-2 blind zu erzwingen
  - `OCR_ONLY` und `CPU_FALLBACK_ONLY` erzeugen einen CPU-OCR-only Pfad ohne Florence-2-Load
  - Florence-2-Init emittiert jetzt `init_start/init_done`
  - CUDA→CPU-Fallback bei Florence-2 emittiert jetzt `vision_fallback` + `vision_device_change`

- [tools/engines/ocr_engine.py](/home/fatih-ubuntu/dev/timus/tools/engines/ocr_engine.py)
  - OOM-Guard in `process()`: RuntimeError mit OOM-Keyword → torch.cuda.empty_cache(), Telemetrie-Event, Error-Dict mit oom=True
  - Inferenz-Timing via C3-Telemetrie (infer_start/infer_done)
  - Init-Telemetrie in `initialize()`
  - normale Laufzeitfehler emittieren jetzt zusaetzlich `vision_error`
  - Best-effort Import der Telemetrie: kein Crash wenn vision_telemetry nicht verfuegbar

- [tools/engines/object_detection_engine.py](/home/fatih-ubuntu/dev/timus/tools/engines/object_detection_engine.py)
  - OOM-Guard in `find_ui_elements()`: RuntimeError OOM → empty_cache(), Telemetrie, leere Liste
  - Inferenz-Timing via C3-Telemetrie
  - Init-Telemetrie in `initialize()`
  - normale Laufzeitfehler emittieren jetzt zusaetzlich `vision_error`

- [tools/engines/segmentation_engine.py](/home/fatih-ubuntu/dev/timus/tools/engines/segmentation_engine.py)
  - OOM-Guard in `get_ui_elements_from_image()`: RuntimeError OOM → empty_cache(), Telemetrie, leere Liste
  - Inferenz-Timing via C3-Telemetrie
  - Init-Telemetrie in `initialize()`
  - normaler `no masks`-Exit schliesst jetzt korrekt mit `infer_done`
  - normale Laufzeitfehler emittieren jetzt zusaetzlich `vision_error`

- [agent/visual_nemotron_agent_v4.py](/home/fatih-ubuntu/dev/timus/agent/visual_nemotron_agent_v4.py)
  - Live-Logs des Florence-Pfads zeigen jetzt auch die gewaehlte `vision_strategy`

### Tests

- [tests/test_c3_vision_ocr.py](/home/fatih-ubuntu/dev/timus/tests/test_c3_vision_ocr.py) — 45 Tests
  - 7 Router-Regelklassen (alle Routing-Regeln einzeln getestet)
  - Telemetrie: Ring-Puffer, Counter, Thread-Safety, Convenience-Methoden
  - OOM-Guard: OCR, ObjectDetection, Segmentation (OOM → keine Exception, korrekte Rueckgabe)
  - Degradationsfall ohne GPU
  - is_oom_error Erkennung
  - Florence-Hot-Path respektiert jetzt die Router-Strategie im echten Tool-Pfad
  - Fallback-Observability enthaelt jetzt `fallback_reason`
  - Init-/Error-Telemetrie in OCR und der normale `no masks`-Segmentation-Exit sind regressionsgesichert

- [tests/test_c3_vision_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_c3_vision_hypothesis.py) — 9 Hypothesis-Tests
  - Router total (300 Beispiele): wirft nie, gibt immer VisionStrategy zurueck
  - VRAM=0 → immer CPU_FALLBACK_ONLY (200 Beispiele)
  - Telemetrie-Count monoton, Ring <= MAX_EVENTS
  - is_oom_error: OOM-Keyword erkannt, non-OOM nicht erkannt
  - _pixel_count nie negativ, _clamp_vram in [0, 80000]

- [tests/test_c3_vision_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_c3_vision_crosshair.py) — 25 Tests + deal-Contracts
  - `@deal.post`-Contracts auf: _clamp_scrapingant_timeout [5,60], _clamp_vram [0,80000], _pixel_count >= 0
  - Contract auf select_vision_strategy: Ergebnis immer in VisionStrategy
  - `crosshair check --analysis_kind=deal`: 0 Gegenbeispiele

### Lean4-Theoreme (CiSpecs.lean)

8 neue Theoreme C3.1–C3.8:
  - C3.1: VRAM-Klemme non-negative
  - C3.2: CPU-Fallback-Schwelle konsistent
  - C3.3: OOM-Error-Count monoton
  - C3.4: Ring-Puffer-Schranke (min(len+1, MAX) <= MAX)
  - C3.5: VRAM-Klemme in [0, 80000]
  - C3.6: ScrapingAnt Timeout in [5, 60]
  - C3.7: Pixel-Count non-negative
  - C3.8: Routing-Monotonie (mehr VRAM verbessert nie die Strategie nach unten)

### Validierung

- `lean CiSpecs.lean` → 0 Fehler, 0 Warnungen
- `pytest tests/test_c3_vision_ocr.py tests/test_c3_vision_hypothesis.py tests/test_c3_vision_crosshair.py` → **79/79 passed**
- `crosshair check --analysis_kind=deal tests/test_c3_vision_crosshair.py` → 0 Gegenbeispiele

---

## Fortschritt 2026-04-05 20:55 CEST - ScrapingAnt Architektur gehaertet

### Problemstellung

Der neue ScrapingAnt-/Social-Media-Block war bereits beschrieben, hatte aber noch drei echte Integrationsluecken:

- das neue `social_media_tool` wurde im MCP-Server noch nicht geladen
- die ScrapingAnt-Logik war doppelt implementiert: einmal im neuen Tool, einmal separat in `deep_research`
- fuer Tool-Loading, Executor-Sichtbarkeit und Deep-Research-Fallback gab es noch keine Regressionen

### Umgesetzt

- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - `tools.social_media_tool.tool` zu `TOOL_MODULES` hinzugefuegt
- [tools/social_media_tool/client.py](/home/fatih-ubuntu/dev/timus/tools/social_media_tool/client.py) (neu)
  - gemeinsamer ScrapingAnt-Adapter fuer:
    - Plattform-Erkennung
    - Domain-Guard (`needs_scrapingant`)
    - API-Key-Zugriff
    - HTML→Text
    - standardisiertes Fetch-Payload
  - nach Doku-Abgleich auf den offiziellen v2-Request-Contract gehaertet:
    - `browser=true/false` statt undokumentiertem `render_js`
    - kein pauschales `return_page_source=true`, damit JS-Rendering nicht unbeabsichtigt deaktiviert wird
    - Remote-`timeout` jetzt als Query-Parameter im erlaubten 5-60s-Bereich
- [tools/social_media_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/social_media_tool/tool.py)
  - nutzt jetzt den gemeinsamen Adapter statt eigener Vendor-Logik
  - Rueckwaertskompatibilitaet fuer `_detect_platform(...)` bleibt erhalten
- [tools/deep_research/tool.py](/home/fatih-ubuntu/dev/timus/tools/deep_research/tool.py)
  - nutzt jetzt denselben gemeinsamen ScrapingAnt-Adapter
  - lokale Wrapper `_needs_scrapingant(...)` / `_fetch_via_scrapingant(...)` bleiben erhalten, delegieren aber zentral
- [requirements.txt](/home/fatih-ubuntu/dev/timus/requirements.txt)
  - ungenutztes `scrapingant-client` entfernt, da der gemeinsame Adapter konsistent ueber `httpx` laeuft

### Regressionen

- [tests/test_social_media_tool_integration.py](/home/fatih-ubuntu/dev/timus/tests/test_social_media_tool_integration.py)
  - MCP-Loader registriert `tools.social_media_tool.tool`
  - Executor sieht `fetch_social_media` und `fetch_page_with_js` ueber seine Capabilities
  - `deep_research` nutzt fuer Social-Media-Domains den gemeinsamen Adapter direkt
  - `deep_research` nutzt bei `HTTP 403` den gemeinsamen ScrapingAnt-Fallback
  - gemeinsamer Adapter baut jetzt den dokumentierten v2-Query-Parameter-Satz

### Validierung

- `python -m py_compile tools/social_media_tool/client.py tools/social_media_tool/tool.py tools/deep_research/tool.py server/mcp_server.py tests/test_social_media_tool_integration.py` gruen
- `5 passed` in `tests/test_social_media_tool_integration.py`
- Live-Manifest auf `GET /get_tool_descriptions` zeigt `fetch_social_media` und `fetch_page_with_js`

## Fortschritt 2026-04-05 - ScrapingAnt Integration + Social Media Tool

### Problemstellung

Timus konnte Social-Media-Seiten (Twitter/X, LinkedIn, Instagram, TikTok) nicht
abrufen, weil diese Plattformen direktes HTTP-Scraping mit 403/429 blockieren und
vollstaendiges JS-Rendering benoetigen. Auch bei normalen Seiten mit Anti-Bot-Schutz
scheiterte die Deep-Research-Pipeline kommentarlos.

### Umgesetzt

- [tools/deep_research/tool.py](/home/fatih-ubuntu/dev/timus/tools/deep_research/tool.py)
  - `_fetch_page_content` hat jetzt eine dreistufige Fallback-Kette:
    1. PDF-URLs → `extract_text_from_pdf` Tool (unveraendert)
    2. Social-Media-Domains → direkt ScrapingAnt (JS-Rendering + Residential Proxy)
    3. Normale HTML-Seiten → direktes httpx; bei 403/429/503 oder Timeout → ScrapingAnt-Fallback
  - `_needs_scrapingant(url)` erkennt bekannte Social-Media-Domains automatisch
  - `_fetch_via_scrapingant(url)` kapselt den API-Call sauber; kein Crash wenn API-Key fehlt
  - `_SCRAPINGANT_DOMAINS`: twitter.com, x.com, linkedin.com, instagram.com, tiktok.com, facebook.com, reddit.com

- [tools/social_media_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/social_media_tool/tool.py) (neu)
  - `fetch_social_media(url, render_js)` — abrufen von Social-Media-Profilen und Posts
  - `fetch_page_with_js(url, render_js)` — beliebige JS-heavy Seiten (SPAs, 403-Blockierungen)
  - Capabilities: `social_media`, `web`, `fetch`
  - Platform-Erkennung fuer 11 Plattformen (Twitter, LinkedIn, Instagram, TikTok, YouTube, Facebook, Reddit, Threads, Mastodon, Bluesky, unknown)

- [agent/base_agent.py](/home/fatih-ubuntu/dev/timus/agent/base_agent.py)
  - Executor-Agent bekommt Capabilities `"social_media"` und `"fetch"` — sieht die neuen Tools im Tool-Sichtfeld

- [agent/agents/meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - `_SPECIALIST_TOOL_AGENT_MAP`: `fetch_social_media` und `fetch_page_with_js` → `executor`
  - Meta-Agent delegiert Social-Media-Anfragen automatisch an den Executor

- [requirements.txt](/home/fatih-ubuntu/dev/timus/requirements.txt)
  - `scrapingant-client==2.2.0` ergaenzt

- [.env.example](/home/fatih-ubuntu/dev/timus/.env.example), [.env](/home/fatih-ubuntu/dev/timus/.env)
  - `SCRAPINGANT_API_KEY=` als Platzhalter eingetragen

### Architektur

```
Deep Research Pipeline
  _fetch_page_content(url)
    ├── PDF?  → extract_text_from_pdf
    ├── Social Media / JS-Domain? → ScrapingAnt direkt
    └── Normal HTML
          httpx.get()
            ├── OK → Text
            └── 403/429/503/Timeout → ScrapingAnt-Fallback

Meta Agent
  Anfrage mit "linkedin profil abrufen"
    → _SPECIALIST_TOOL_AGENT_MAP: fetch_social_media → executor
    → Executor ruft fetch_social_media(url) auf
```

### Setup

`SCRAPINGANT_API_KEY=<key>` in `.env` eintragen.
Free-Tier: 10.000 Credits/Monat (scrapingant.com).

### Validierung

- `python -c "from tools.social_media_tool.tool import fetch_social_media, _detect_platform"` gruen
- Platform-Erkennung fuer 5 Plattformen verifiziert
- `_needs_scrapingant` korrekt (Social-Media: True, arxiv: False)
- AGENT_CAPABILITY_MAP executor: social_media + fetch vorhanden
- Meta Agent _SPECIALIST_TOOL_AGENT_MAP: fetch_social_media → executor, fetch_page_with_js → executor

---

## Fortschritt 2026-04-05 20:05 CEST - C5 abgeschlossen

### Problemstellung

Der urspruengliche C5-Block reduzierte die `MEMORY.md`-Write-Spikes bereits deutlich, hatte aber drei letzte Runtime-Luecken:

- `replace_memories(...)` maskierte echte Write-Fehler noch als scheinbaren `unchanged`-Skip
- `MarkdownStoreWithSearch` reindexierte nach dem neuen Bulk-Write-Pfad nicht atomar genug; Datei und FTS-Index konnten auseinanderlaufen
- die neuen Scheduler-Regressionen testeten den Hash-Pfad noch zu indirekt ueber Mocks statt ueber den echten Codepfad

### Umgesetzt

- [memory/markdown_store/store.py](/home/fatih-ubuntu/dev/timus/memory/markdown_store/store.py)
  - `replace_memories(...)` propagiert Write-/Hook-Fehler jetzt sauber statt sie als `written=False` zu maskieren
  - neuer Hook `_after_replace_memories(...)` fuehrt nachgelagerte Schritte nach dem Dateischreiben, aber vor der Hash-Bestaetigung aus
  - `_last_memory_hash` wird erst bestaetigt, wenn Datei-Write und nachgelagerter Reindex komplett erfolgreich waren
- [memory/markdown_store/store.py](/home/fatih-ubuntu/dev/timus/memory/markdown_store/store.py)
  - `MarkdownStoreWithSearch` nutzt den neuen Hook fuer den `memory`-FTS-Reindex
  - bei Reindex-Fehlern bleibt der Hash absichtlich unbestaetigt, damit der naechste identische Lauf den Reindex erneut versucht
- [orchestration/scheduler.py](/home/fatih-ubuntu/dev/timus/orchestration/scheduler.py)
  - `_pending_sync_hash` wird jetzt explizit verwaltet
  - `unchanged`-Faelle loeschen veraltete Pending-Werte
  - nach erfolgreichem Sync wird der Pending-Hash nach `_last_sync_hash` uebernommen und anschliessend zurueckgesetzt

### Regressionen

- [tests/test_memory_markdown_sync.py](/home/fatih-ubuntu/dev/timus/tests/test_memory_markdown_sync.py)
  - echter `MemoryManager.sync_to_markdown()`-Fehlerpfad statt nur `replace_memories(...)` isoliert
  - Reindex-Failure-Regression: Hash darf bei stale-FTS-Fall nicht bestaetigt werden
  - echter Scheduler-Pfad:
    - fehlgeschlagener Sync promoted den Hash nicht
    - erfolgreicher Sync uebernimmt den Pending-Hash korrekt
- [tests/test_memory_markdown_sync_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_memory_markdown_sync_hypothesis.py)
  - bleibt gruene Absicherung fuer Idempotenz, Dedupe und Reihenfolgenstabilitaet

### Validierung

- `python -m py_compile memory/markdown_store/store.py memory/memory_system.py orchestration/scheduler.py tests/test_memory_markdown_sync.py tests/test_memory_markdown_sync_hypothesis.py` gruen
- `30 passed` in:
  - `tests/test_memory_markdown_sync.py`
  - `tests/test_memory_markdown_sync_hypothesis.py`
- `64 passed` in:
  - `tests/test_c2_observability.py`
  - `tests/test_c2_entrypoints.py`
  - `tests/test_memory_markdown_sync.py`
  - `tests/test_memory_markdown_sync_hypothesis.py`

## Fortschritt 2026-04-05 13:59 CEST - C2 end-to-end geschlossen

### Problemstellung

Die C2-Grundstruktur stand bereits, aber zwei letzte Luecken machten den Incident-Trace noch unvollstaendig:

- Task-Erzeuger uebernahmen eine laufende `request_id` nicht zentral, sondern nur dort, wo einzelne Producer sie explizit setzten
- Dispatcher-Fallbacks auf `meta` (`empty_decision`, `uncertain_decision`, `dispatcher_exception`) erschienen im Incident-Trace nicht sauber als eigener Routing-Schritt

Damit war `/autonomy/incident/<request_id>` bei echten Live-Faellen noch nicht wirklich end-to-end belastbar.

### Umgesetzt

- [orchestration/request_correlation.py](/home/fatih-ubuntu/dev/timus/orchestration/request_correlation.py)
  - neuer ContextVar-basierter Laufzeitkontext fuer `request_id` / `session_id`
  - `bind_request_correlation(...)` und Getter fuer die aktuelle Request-Korrelation
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - `/chat` bindet die laufende `request_id` jetzt waehrend Dispatcher- und Agentenlauf zentral in den Runtime-Kontext
  - `/autonomy/incident/{request_id}` beschreibt jetzt praezise nur noch die fuer diese `request_id` aufgezeichneten Korrelations-Events
- [orchestration/autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)
  - Task-Ausfuehrung bindet geerbte `request_id` jetzt ebenfalls in den Runtime-Kontext
  - dadurch koennen aus Tasks erzeugte Folge-Tasks dieselbe Request-Korrelation weitertragen
- [orchestration/task_queue.py](/home/fatih-ubuntu/dev/timus/orchestration/task_queue.py)
  - `queue.add(...)` ergaenzt JSON-Objekt-Metadaten automatisch um die aktuelle `request_id`, wenn sie fehlt
  - explizite `request_id` bleibt vorrangig erhalten
  - nicht-JSON-/Legacy-Metadaten bleiben absichtlich unveraendert
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - Dispatcher-Fallbacks tragen jetzt ebenfalls `request_id`
  - bei `empty_decision`, `uncertain_decision` und `dispatcher_exception` wird zusaetzlich ein echtes `dispatcher_route_selected -> meta` emittiert
- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - `build_incident_trace(...)` ist robust gegen heterogene Event-Listen und ignoriert Nicht-Dict-Eintraege statt zu crashen

### Regressionen, Contracts, Hypothesis, CrossHair, Lean

- [tests/test_c2_request_correlation_runtime.py](/home/fatih-ubuntu/dev/timus/tests/test_c2_request_correlation_runtime.py)
  - Runtime-Regressionsfaelle fuer:
    - Context-Reset
    - automatische `request_id`-Uebernahme in `queue.add(...)`
    - Vorrang expliziter `request_id`
    - Passthrough fuer nicht-JSON-Metadaten
- [tests/test_dispatcher_provider_selection.py](/home/fatih-ubuntu/dev/timus/tests/test_dispatcher_provider_selection.py)
  - Dispatcher-Fallbacks pruefen jetzt explizit:
    - `dispatcher_meta_fallback` mit `request_id`
    - nachfolgenden `dispatcher_route_selected` mit `fallback_*`-Quelle
- [tests/test_c2_observability.py](/home/fatih-ubuntu/dev/timus/tests/test_c2_observability.py)
  - neuer Guard-Fall fuer heterogene Event-Listen in `build_incident_trace(...)`
- [tests/test_c2_observability_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_c2_observability_contracts.py)
  - CrossHair laeuft jetzt auch gegen den robusteren heterogenen Listenpfad
- [tests/test_c2_entrypoints.py](/home/fatih-ubuntu/dev/timus/tests/test_c2_entrypoints.py)
  - gemischte ISO-/Offset-Sortierung und HTTP-/CLI-Einstiegspunkte bleiben weiter abgesichert

### Validierung

- `python -m py_compile orchestration/request_correlation.py orchestration/task_queue.py orchestration/autonomous_runner.py orchestration/autonomy_observation.py main_dispatcher.py server/mcp_server.py scripts/evaluate_autonomy_observation.py tests/test_dispatcher_provider_selection.py tests/test_c2_observability.py tests/test_c2_observability_contracts.py tests/test_c2_entrypoints.py tests/test_c2_request_correlation_runtime.py` gruen
- `59 passed` in:
  - `tests/test_dispatcher_provider_selection.py`
  - `tests/test_c2_observability.py`
  - `tests/test_c2_observability_contracts.py`
  - `tests/test_c2_entrypoints.py`
  - `tests/test_c2_request_correlation_runtime.py`
- `python -m crosshair check tests/test_c2_observability_contracts.py` gruen
- `python scripts/verify_pre_commit_lean.py` komplett gruen
  - `CiSpecs.lean` gruen
  - `Mathlib bundle (12 Specs)` gruen

### Live-Abnahme

- `timus-mcp` neu geladen; `/health` wieder `healthy`
- echter `/chat`-Replay:
  - Query: `Was ist die Hauptstadt von Frankreich?`
  - Session: `c2_final_live_v2`
  - `request_id = req_cfa58e3535f8`
- `/autonomy/incident/req_cfa58e3535f8` zeigt jetzt die vollstaendige korrelierte Kette:
  - `chat_request_received`
  - `dispatcher_meta_fallback`
  - `dispatcher_route_selected`
  - `request_route_selected`
  - `chat_request_completed`

### Ergebnis

`C2` ist damit abgeschlossen:

- Request-/Route-/Outcome-Korrelation ist live erreichbar
- Dispatcher-Fallbacks sind im Incident-Trace sichtbar
- Request-Korrelation kann in Folge-Tasks zentral weitergetragen werden
- HTTP, CLI, Hypothesis, CrossHair und Lean sind fuer den C2-Block gruen

## Fortschritt 2026-04-04 23:20 CEST - C2 hebt letzte Requests, Routen und Fehler in den Status-Snapshot

### Problemstellung

Der erste C2-Block zaehlte Request-/Route-/Task-Korrelation bereits sauber im Beobachtungslog, aber der operative Diagnosepfad war noch zu schwach:

- fuer einen akuten Fehlfall musste man weiter zwischen `autonomy_observation.jsonl`, Task-Logs und `/status` springen
- der Snapshot zeigte MCP-/Service-Zustand, aber nicht den letzten korrelierten Nutzerpfad
- damit war sichtbar, **dass** etwas schiefgeht, aber nicht direkt **welche Anfrage**, **welche Route** und **welcher letzte korrelierte Fehler** dazu gehoerten

### Umgesetzt

- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - `request_correlation` fuehrt jetzt zusaetzlich:
    - `recent_requests`
    - `recent_routes`
    - `recent_outcomes`
  - kompakte Eintraege werden fuer:
    - `chat_request_received`
    - `dispatcher_route_selected`
    - `request_route_selected`
    - `task_route_selected`
    - `chat_request_completed` / `chat_request_failed`
    - `task_execution_completed` / `task_execution_failed`
    gesammelt und auf einen kleinen festen Verlauf begrenzt
- [gateway/status_snapshot.py](/home/fatih-ubuntu/dev/timus/gateway/status_snapshot.py)
  - neuer Builder `_build_request_runtime_correlation(...)`
  - Snapshot enthaelt jetzt `request_runtime` mit:
    - `state`
    - Zaehlern fuer Requests / Routen / Outcomes
    - `last_request`
    - `last_route`
    - `last_outcome`
    - `last_correlated_failure`
  - `format_status_message(...)` zeigt diese Daten direkt im Core-Block

### Regressionen, Contracts, Hypothesis, CrossHair, Lean

- [tests/test_autonomy_observation.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation.py)
  - Regression fuer letzte Requests / Routen / Outcomes im C2-Korrelationspfad
- [tests/test_autonomy_observation_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation_contracts.py)
  - Deal-Contracts fuer die neuen kompakten Listen und deren Begrenzung
- [tests/test_autonomy_observation_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation_hypothesis.py)
  - boundedness fuer `recent_requests`, `recent_routes`, `recent_outcomes`
- [tests/test_telegram_status_snapshot.py](/home/fatih-ubuntu/dev/timus/tests/test_telegram_status_snapshot.py)
  - Snapshot-/Formatter-Regressionsfall fuer den neuen `request_runtime`-Block

### Validierung

- `python -m py_compile orchestration/autonomy_observation.py gateway/status_snapshot.py tests/test_autonomy_observation.py tests/test_autonomy_observation_contracts.py tests/test_autonomy_observation_hypothesis.py tests/test_telegram_status_snapshot.py` gruen
- `15 passed` in:
  - `tests/test_autonomy_observation.py`
  - `tests/test_autonomy_observation_contracts.py`
  - `tests/test_autonomy_observation_hypothesis.py`
  - `tests/test_telegram_status_snapshot.py`
- `python -m crosshair check tests/test_autonomy_observation_contracts.py` gruen
- `python scripts/verify_pre_commit_lean.py` komplett gruen
  - `CiSpecs.lean` gruen
  - `Mathlib bundle (12 Specs)` gruen

## Fortschritt 2026-04-04 22:55 CEST - Meta klaert mehrdeutige Gespraechszuege zuerst selbst

### Problemstellung

Die Follow-up-Haertung fuer konkrete Vertagungen war schon drin, aber die generische Dialogregel fehlte noch:

- `meta` delegierte zwar korrekt bei klaren Aufgaben
- kurze, mehrdeutige oder nur halb ausformulierte Gespraechszuege waren aber nicht explizit als `meta`-eigene Klaerungsfaelle verankert
- dadurch konnten Saetze wie `muss ich mir noch ueberlegen`, `ich bin mir noch nicht sicher` oder `wie meinst du das` je nach Kontext noch zu frueh aus dem Meta-Layer herausfallen

### Umgesetzt

- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - gemeinsamer Helper `looks_like_meta_clarification_turn(...)`
  - erkennt kurze, mehrdeutige Gespraechszuege als semantische Klaerungsfaelle
  - solche Faelle erzeugen jetzt die Ambiguitaet `conversational_clarification_needed`
  - Klassifikation bleibt dann auf `single_lane -> meta` mit `reason = semantic_clarification_turn`
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - Dispatcher nutzt denselben gemeinsamen Helper
  - dadurch gibt es keine zweite, konkurrierende Regelmaschine fuer denselben Gespraechstyp
- [agent/prompts.py](/home/fatih-ubuntu/dev/timus/agent/prompts.py)
  - `META_SYSTEM_PROMPT` hat jetzt eine explizite `SEMANTISCHE KLAERUNG VOR DELEGATION`-Regel:
    - Satz erst als Gespraechszug lesen
    - bei Mehrdeutigkeit bei `meta` bleiben
    - im Zweifel genau eine knappe Klaerungsfrage
    - erst delegieren, wenn Bezug und Ziel klar sind

### Regressionen, Contracts, Hypothesis, CrossHair, Lean

- [tests/test_dispatcher_self_status_routing.py](/home/fatih-ubuntu/dev/timus/tests/test_dispatcher_self_status_routing.py)
  - neue Regressionsfaelle fuer:
    - `muss ich mir noch ueberlegen`
    - `ich bin mir noch nicht sicher`
    - `wie meinst du das`
- [tests/test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
  - neuer Helper-Test fuer `looks_like_meta_clarification_turn(...)`
  - neue Meta-Klassifikation fuer `semantic_clarification_turn`
- [tests/test_meta_dialog_state_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_dialog_state_contracts.py)
  - bestehende Deal/Hypothesis-Grenze erneut gegen die geaenderte Meta-Semantik gefahren

### Validierung

- `python -m py_compile orchestration/meta_orchestration.py main_dispatcher.py agent/prompts.py tests/test_dispatcher_self_status_routing.py tests/test_meta_orchestration.py tests/test_meta_dialog_state_contracts.py` gruen
- `57 passed` in:
  - `tests/test_dispatcher_self_status_routing.py`
  - `tests/test_meta_orchestration.py`
  - `tests/test_meta_dialog_state_contracts.py`
- `python -m crosshair check tests/test_meta_dialog_state_contracts.py` gruen
- `python scripts/verify_pre_commit_lean.py` komplett gruen
  - `CiSpecs.lean` gruen
  - `Mathlib bundle (12 Specs)` gruen

## Fortschritt 2026-04-04 22:40 CEST - Zögernde Follow-ups bleiben im offenen Meta-Dialog

### Problemstellung

Ein echter Canvas-Fall war noch falsch:

- Nutzer fragt nach Telefonfunktion / Voice-Optionen
- `meta` antwortet korrekt mit offenem Follow-up (`Was willst du?`)
- Nutzer sagt nur `muss ich mir noch überlegen`
- der Turn verliert den offenen Dialogkontext und kippt wegen `überlege` in `reasoning`

Das war kein Session-Verlust, sondern eine semantische Lücke:

- Follow-up-Kapsel erkannte zögernde / vertagende Kurzantworten noch nicht
- der Dispatcher wertete `überlege` isoliert als Reasoning-Signal
- der Meta-Dialoganker behandelte diese Antwort noch nicht als kontextgebundene Fortsetzung

### Umgesetzt

- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - neue Erkennung fuer vertagende Follow-up-Antworten wie:
    - `muss ich mir noch überlegen`
    - `ich überlege noch`
    - `darüber muss ich nachdenken`
  - solche Antworten bleiben jetzt bei vorhandenem `pending_followup_prompt` oder Proposal auf der bestehenden Lane statt erneut durch den Dispatcher zu fallen
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - neuer Dispatcher-Guard fuer `deferred followups` innerhalb einer `# FOLLOW-UP CONTEXT`-Kapsel
  - verhindert, dass das Keyword `überlege` den Turn in `reasoning` zieht
- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - Meta-Dialoganker kennt diese zögernden Antworten jetzt ebenfalls als echte Fortsetzung
  - offener Dialogkontext bleibt fuer `meta` erhalten

### Regressionen, Contracts, Hypothesis

- [tests/test_android_chat_language.py](/home/fatih-ubuntu/dev/timus/tests/test_android_chat_language.py)
  - neuer Canvas-Repro fuer den exakten Telefon-/`muss ich mir noch überlegen`-Fall
- [tests/test_dispatcher_self_status_routing.py](/home/fatih-ubuntu/dev/timus/tests/test_dispatcher_self_status_routing.py)
  - Dispatcher-Regressionsfall fuer dieselbe Follow-up-Kapsel
- [tests/test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
  - Meta-Anchor-Regressionsfall fuer vertagte Entscheidungen
- [tests/test_meta_dialog_state_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_dialog_state_contracts.py)
  - bestehende Deal/Hypothesis-Schicht erneut gegen die veraenderte Dialog-State-Logik gefahren

### Validierung

- `python -m py_compile server/mcp_server.py main_dispatcher.py orchestration/meta_orchestration.py tests/test_android_chat_language.py tests/test_dispatcher_self_status_routing.py tests/test_meta_orchestration.py tests/test_meta_dialog_state_contracts.py` gruen
- `69 passed` in:
  - `tests/test_android_chat_language.py`
  - `tests/test_dispatcher_self_status_routing.py`
  - `tests/test_meta_orchestration.py`
  - `tests/test_meta_dialog_state_contracts.py`
- `python -m crosshair check tests/test_meta_dialog_state_contracts.py` gruen
- `python scripts/verify_pre_commit_lean.py`
  - `CiSpecs.lean` gruen
  - bekanntes Restproblem bleibt unveraendert: `Mathlib bundle` laeuft weiter ins bestehende `60s`-Timeout


## Status 2026-04-04 20:43 CEST - Phase B Abschluss

### Phase-B-Stand

- Gesamtstand Phase B: **abgeschlossen**
- Fokus verschiebt sich jetzt von Routing-/Follow-up-Stabilisierung auf **Phase C Runtime-Haertung und Grounding**
- konkrete Vorbereitung fuer Phase C liegt jetzt in [PHASE_C_RUNTIME_PLAN.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_C_RUNTIME_PLAN.md)

### Phase B abgeschlossen durch

- Follow-up-/Proposal-Routing fuer `ja mach das`, `ok fang an`, `mach das`, `leg los`
- `RESOLVED_PROPOSAL` zurueck nach `meta` statt falschem Pfad in `executor`
- Delegation-Blackboard-Reads ueber `delegation:`-Keys
- Guided-Follow-up-Prioritaet gegen schwache Generic-Proposals
- `developer`-Crash `list has no attribute get`
- False Positives bei Navigation-/Vision-Routing aus angereichertem Kontext
- natuerlichere Antwort-Finalisierung ohne starres `Hier ist deine Liste:`
- Dispatcher-Bypass fuer klare Meta-Queries (`blackboard`, `google calendar`)
- Beobachtungslog gegen Test-Pollution
- direkte Meta-Reads fuer Screentext/OCR statt teurer `visual`-Delegation
- Guard gegen fehlgeroutete `meta -> executor`-Research-Delegationen
- generische Research-Haertung bei duenner/off-topic Evidenz
- staerkere Quellenpolitik fuer Deutschland-bezogene Recherche
- Dispatcher-Haertung fuer direkte YouTube-Verifikation
- strittige Rechts-/Politik-Claims werden jetzt als `knowledge_research` statt `single_lane/executor` klassifiziert
- Skill-Runner ignoriert `__init__.py` als Entrypoint und kann JSON-Script-Output strukturiert lesen

### Letzte Live-Abnahme

- `was gibts auf dem blackboard`
  - sauber ueber `meta` mit direktem Blackboard-Pfad
- Deutschland-/Genehmigungsfall
  - kein alter `executor`-Fehlpfad mehr
  - live in `timus-mcp` direkt `meta -> research` / Deep-Research-Start bestaetigt
- Google-Calendar
  - Runde 1: ehrliche Setup-/OAuth-Antwort statt kaputtem Skill-Import
  - Runde 2 `ok fang an`: korrekt als `RESOLVED_PROPOSAL` fuer den OAuth-Start aufgeloest, nicht mehr als Fremd-Follow-up

### Noch offen, aber nicht mehr Phase B

- echter browsergestuetzter OAuth-Abschluss fuer Google Calendar
- video-grounded Fact-Checking ohne Drift auf andere Videos
- allgemeine Runtime-Haertung fuer MCP / Vision / OCR / Langlaeufer in Phase C

### Phase C vorbereitet

- Baseline fuer Phase C aus aktuellem Runtime-Verhalten und Beobachtungslog verdichtet
- konkrete Workstreams definiert:
  - `C1` MCP Health / Restart / Self-Healing
  - `C2` Observability / Anfrage-zu-Fehler-Korrelation
  - `C5` Persistenz-/Runtime-Spam
  - `C3` Vision / OCR
  - `C4` Langlaeufer-/Antwortpfade
- erster Angriffsblock fuer Phase C ist jetzt klar auf `C1` gesetzt

## Fortschritt 2026-04-04 22:34 CEST - C2 Request-, Routing- und Task-Korrelation gestartet

### Problemstellung

Nach C1 war der MCP-Zustand deutlich ehrlicher, aber C2 fehlte noch im eigentlichen Nutzerpfad:

- `/chat`-, Dispatcher- und Runner-Ereignisse liessen sich noch nicht als zusammenhaengender Incident lesen
- Request-Routing und Task-Routing waren im Beobachtungsmodell noch nicht sauber getrennt
- es gab noch keinen formalen Contract fuer die neue Korrelationsebene

### Umgesetzt

- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - `request_id` fuer `/chat` eingefuehrt und in Antwort, SSE und Chat-Memory-Metadaten mitgezogen
  - neue Observation-Events:
    - `chat_request_received`
    - `request_route_selected`
    - `chat_request_completed`
    - `chat_request_failed`
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - Dispatcher schreibt jetzt explizit `dispatcher_route_selected`
  - bestehende `dispatcher_meta_fallback`-Events tragen jetzt den `session_id`-Bezug mit
- [orchestration/autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)
  - neue Runtime-Korrelations-Events:
    - `task_execution_started`
    - `task_route_selected`
    - `task_execution_completed`
    - `task_execution_failed`
- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neuer Summary-Block `request_correlation`
  - trennt jetzt sauber:
    - `dispatcher_routes_total`
    - `request_routes_total`
    - `task_routes_total`
    - `task_started_total`
    - `task_completed_total`
    - `task_failed_total`
    - `user_visible_failures_total`
  - `recent_failures` fasst die juengsten korrelierten Nutzer-/Task-Fehler kompakt zusammen
  - Markdown-Render zeigt jetzt eine eigene C2-Sektion `Request-Korrelation`

### Regressionen, Contracts, Hypothesis

- [tests/test_autonomy_observation.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation.py)
  - neuer Regressionsfall fuer `chat` + Dispatcher + Task-Fehlerkette
- [tests/test_autonomous_runner_incident_notifications.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomous_runner_incident_notifications.py)
  - prueft die neue Task-Korrelation im Runner
- [tests/test_autonomy_observation_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation_contracts.py)
  - Deal-Contract erweitert um die neue `request_correlation`-Struktur
  - verhindert negative oder semantisch widerspruechliche Zaehler
- [tests/test_autonomy_observation_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation_hypothesis.py)
  - neue Hypothesis-Schicht fuer die Boundedness der C2-Korrelationszaehler

### Validierung

- `python -m py_compile orchestration/autonomy_observation.py server/mcp_server.py main_dispatcher.py orchestration/autonomous_runner.py tests/test_autonomy_observation.py tests/test_autonomous_runner_incident_notifications.py tests/test_autonomy_observation_contracts.py tests/test_autonomy_observation_hypothesis.py` gruen
- `40 passed` in:
  - `tests/test_autonomy_observation.py`
  - `tests/test_autonomy_observation_contracts.py`
  - `tests/test_autonomy_observation_hypothesis.py`
  - `tests/test_autonomous_runner_incident_notifications.py`
  - `tests/test_dispatcher_provider_selection.py`
  - `tests/test_android_chat_language.py`
- `python -m crosshair check tests/test_autonomy_observation_contracts.py --analysis_kind=deal` gruen
- `python scripts/verify_pre_commit_lean.py` komplett gruen:
  - `lean/CiSpecs.lean`
  - Mathlib-Bundle (12 Specs)

### Wirkung

- ein `/chat`-Fehlfall ist jetzt sichtbar als Kette:
  - Request rein
  - Dispatcher-Route
  - Request-Route
  - Task-Start / Task-Route / Task-Fail
- Request- und Task-Routing sind bewusst getrennt; C2 fuehrt keine neue konkurrierende Incident-Logik ein
- das Beobachtungslog ist damit als erster Einstiegspunkt fuer Anfrage-zu-Fehler-Korrelation deutlich brauchbarer

### Naechster Rest in C2

- Live-Korrelation in die operativen Status-/Diagnosepfade heben
- letzte Anfrage / letzter korrelierter Fehler im Snapshot bzw. Diagnosezugang sichtbar machen
- danach gezielt die noch fehlende Nutzerwirkungsebene (`response_never_delivered`, `silent_failure`) nachziehen

## Nachtrag 2026-04-04 22:18 CEST - Canvas-SSE-Reconnect-Schleife aus C1 entschaerft

### Problemstellung

Im Canvas fiel nach C1 ein neues Muster auf:

- `/events/stream` wurde in kurzen, regelmaessigen Intervallen neu aufgebaut
- dadurch verlor der Canvas waehrend laengerer Antworten sichtbar den Flow
- Ursache war die neue erzwungene SSE-TTL mit Default `8s`

Journalbild:

- neue `GET /events/stream`-Requests ca. alle `13s`
- das passte zu `server_refresh` + Browser-Reconnect-Delay

### Umgesetzt

- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - `_sse_connection_ttl_sec()` ist jetzt standardmaessig **deaktiviert**
  - erzwungene Stream-TTL greift nur noch, wenn `TIMUS_SSE_CONNECTION_TTL_SEC` explizit gesetzt wird
  - positive Werte werden konservativ auf mindestens `60s` geklemmt
  - Shutdown-Sicherheit bleibt ueber `shutdown_event` und den bestehenden Stream-Abbruchpfad erhalten
- [tests/test_mcp_shutdown_hardening.py](/home/fatih-ubuntu/dev/timus/tests/test_mcp_shutdown_hardening.py)
  - Regression angepasst:
    - Default `0.0`
    - Low values clampen auf `60.0`

### Validierung

- `python -m py_compile server/mcp_server.py tests/test_mcp_shutdown_hardening.py` gruen
- `14 passed` in `tests/test_mcp_shutdown_hardening.py` + `tests/test_mcp_health_runtime_contracts.py`
- `python -m crosshair check tests/test_mcp_health_runtime_contracts.py --analysis_kind=deal` gruen
- `python scripts/verify_pre_commit_lean.py` komplett gruen:
  - `lean/CiSpecs.lean`
  - Mathlib-Bundle (12 Specs)

## Fortschritt 2026-04-04 21:12 CEST - C1 MCP-Lifecycle, Startup und Shutdown gehaertet

### Problemstellung

Der erste Phase-C-Block zeigte zwei echte Runtime-Kanten:

- `timus-mcp` blockierte den Restart zu lange im Startup, weil beim OCR-/PaddleX-Import ein externer Model-Hoster-Check lief
- offene `/events/stream`-Verbindungen fuehrten beim Reload wiederholt zu `timeout graceful shutdown exceeded`

### Umgesetzt

- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - neuer MCP-Lifecycle-State in `/health` mit `ready`, `warmup_pending`, `transient` und `lifecycle`
  - optionale Warmups (`inception_health`, Browser-Context, Scheduler, RealSense) aus dem kritischen Startup-Pfad in einen Post-Startup-Task verschoben
  - SSE-Helfer fuer Queue-vs-Shutdown-Waiting eingefuehrt
  - `/events/stream` bekommt jetzt eine kontrollierte Verbindungs-TTL mit `server_refresh`, damit Canvas-Clients sauber reconnecten und Restarts nicht an einer alten Langverbindung haengen
- [tools/engines/ocr_engine.py](/home/fatih-ubuntu/dev/timus/tools/engines/ocr_engine.py)
  - `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=1` als Default fuer den Timus-Runtime-Pfad gesetzt
  - Wirkung: der teure PaddleX-Hoster-Check wird beim OCR-Import standardmaessig uebersprungen, ohne die eigentliche Modellnutzung zu verbieten
- [orchestration/self_healing_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_healing_engine.py)
  - transiente MCP-Health-Zustaende (`starting`, `shutting_down`) werden nicht mehr als verifizierter Ausfall interpretiert

### Regressionen und Contracts

- [tests/test_mcp_shutdown_hardening.py](/home/fatih-ubuntu/dev/timus/tests/test_mcp_shutdown_hardening.py)
  - neue Checks fuer SSE-Waiting, Health-Payload und sichere SSE-TTL-Untergrenze
- [tests/test_mcp_health_runtime_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_mcp_health_runtime_contracts.py)
  - neuer CrossHair- und Hypothesis-Contract fuer transiente MCP-Health-Zustaende
- bestehende Self-Healing-/E2E-Readiness-Suiten gegen die neue Semantik gegengeprueft

### Validierung

- `python -m py_compile server/mcp_server.py orchestration/self_healing_engine.py tools/engines/ocr_engine.py tests/test_mcp_shutdown_hardening.py tests/test_mcp_health_runtime_contracts.py` gruen
- `12 passed` in `tests/test_mcp_shutdown_hardening.py` + `tests/test_mcp_health_runtime_contracts.py`
- `6 passed` in `tests/test_m3_self_healing_baseline.py`
- `7 passed` in `tests/test_e2e_regression_matrix.py`
- `python -m crosshair check tests/test_mcp_health_runtime_contracts.py tests/test_self_healing_recovery_ladder_contracts.py --analysis_kind=deal` gruen
- `python scripts/verify_pre_commit_lean.py`
  - `lean/CiSpecs.lean` gruen
  - Mathlib-Bundle weiterhin nur am bekannten `60s`-Timeout gescheitert, kein neuer Lean-Widerspruch im C1-Patch

### Live-Befund

- Startup:
  - vor dem Patch: Startfenster ca. `21:06:21 -> 21:06:33` mit vollem `Checking connectivity to the model hosters...`
  - nach dem Patch: Startfenster ca. `21:11:00 -> 21:11:06/07` mit `Connectivity check ... skipped`
- `/health` liefert jetzt den Runtime-Lifecycle sichtbar mit Warmup-Details statt nur blind `healthy`
- finaler Restart um `21:11:27 CEST` lief ohne den alten `timeout graceful shutdown exceeded`-Pfad durch; der Dienst war danach wieder sauber oben

### Offener Rest in C1

- der MCP-Startup ist klar kuerzer und ehrlicher, aber noch nicht instantan
- als naechstes in `C1` bleibt deshalb:
  - Startup-/Warmup-Dauer weiter ausmessen
  - Incident-Korrelation in Richtung `mcp_health` / Restart / Observation nachziehen

## Fortschritt 2026-04-04 22:02 CEST - C1 MCP-Runtime-Korrelation in Status-Snapshots nachgezogen

### Problemstellung

Nach dem Lifecycle-/Warmup-Patch war `/health` ehrlicher, aber die operative Lage fuer `telegram /status`, `self_improvement_tool` und Diagnosepfade blieb noch verteilt:

- `services.mcp`
- `local.mcp_health`
- `restart`
- `self_healing`
- `stability_gate`

Die Information war da, aber nicht als ein zusammenhaengender Runtime-Befund.

### Umgesetzt

- [gateway/status_snapshot.py](/home/fatih-ubuntu/dev/timus/gateway/status_snapshot.py)
  - `mcp_runtime` als korrelierter Statusblock eingefuehrt
  - vereint jetzt:
    - Service-/HTTP-Gesundheit
    - Lifecycle-/Warmup-Zustand
    - Restart-Status inkl. Phase und Request-ID
    - offene `mcp_health`-Incidents / Breaker
    - aktuellen `stability_gate`-State
  - fehlende `uptime_seconds` triggern **nicht** mehr faelschlich `startup_grace`
  - doppelte `restart`-/`mcp_runtime`-Berechnung in `collect_status_snapshot()` bereinigt
  - `format_status_message(...)` zeigt jetzt eine eigene `MCP Runtime`-Zeile im Core-Block

### Regressionen und Contracts

- [tests/test_telegram_status_snapshot.py](/home/fatih-ubuntu/dev/timus/tests/test_telegram_status_snapshot.py)
  - Snapshot-Regressionsfall um `mcp_runtime` erweitert
  - direkte Tests fuer:
    - `restart_in_progress`
    - kein falsches `startup_grace` ohne explizite Uptime
- [tests/test_mcp_health_runtime_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_mcp_health_runtime_contracts.py)
  - Contract-/Hypothesis-Erweiterung fuer die Runtime-Zustaende:
    - `transient_lifecycle`
    - `restart_in_progress`

### Validierung

- `python -m py_compile gateway/status_snapshot.py tests/test_telegram_status_snapshot.py tests/test_mcp_health_runtime_contracts.py` gruen
- `16 passed` in `tests/test_telegram_status_snapshot.py` + `tests/test_mcp_health_runtime_contracts.py` + `tests/test_e2e_regression_matrix.py`
- `1 passed` in `tests/test_self_improvement_tool_ops.py`
- `python -m crosshair check tests/test_mcp_health_runtime_contracts.py --analysis_kind=deal` gruen
- `python scripts/verify_pre_commit_lean.py` jetzt komplett gruen:
  - `lean/CiSpecs.lean`
  - Mathlib-Bundle (12 Specs)

### Wirkung

- `status`-/Snapshot-Konsumenten sehen jetzt mit einem Blick, ob MCP wirklich gesund ist, sich noch im Warmup befindet, gerade restartet oder nur wegen eines offenen `mcp_health`-Incidents unter Beobachtung steht
- die frueher manuelle Korrelation ueber mehrere Teilbloecke ist fuer den MCP-Fall deutlich reduziert

### Rest in C1

- C1 ist damit funktional fast zu
- verbleibend ist vor allem:
  - ein kurzer Live-Status-Check auf dem geladenen Dienst
  - danach kann der Beobachtungs-/Anfragebezug sauber in `C2` weitergehen

### Live-Nachtrag 2026-04-04 21:45 CEST

- beim ersten Live-Check fiel noch ein alter Restart-Artefaktzustand auf:
  - `timus_restart_status.json` stand seit Wochen auf `running/preflight`
  - der Snapshot hatte das deshalb zuerst noch als `restart_in_progress` gelesen
- Nachgezogen:
  - [gateway/status_snapshot.py](/home/fatih-ubuntu/dev/timus/gateway/status_snapshot.py)
    - `stale`-Erkennung fuer alte Restart-Artefakte jetzt an dieselbe Drift-Semantik wie die E2E-Matrix gekoppelt
    - `mcp_runtime` ignoriert `running`-Restarts, wenn sie stale sind
    - Snapshot zeigt den Restart weiter sichtbar an, aber nicht mehr als aktiven Recovery-Zustand
- neue Regressionen in [tests/test_telegram_status_snapshot.py](/home/fatih-ubuntu/dev/timus/tests/test_telegram_status_snapshot.py):
  - altes `running/preflight` wird als `stale` markiert
  - stale Restart-Dateien triggern kein falsches `restart_in_progress`
- erneute Validierung:
  - `19 passed` in der fokussierten Snapshot-/Contract-/E2E-Suite
  - CrossHair erneut gruen
  - Lean-Bundle erneut komplett gruen
- Live-Snapshot nach Reload:
  - `restart.stale = true`
  - `mcp_runtime.state = startup_grace`
  - also kein falscher laufender Restart mehr, waehrend der Dienst real gesund hochkommt

## Fortschritt 2026-04-04 20:43 CEST - Klassifikation fuer strittige Politik-/Rechtsclaims und Skill-Entrypoints gehaertet

### Problemstellung

Die heutige Abschlussrunde zeigte noch zwei konkrete Restpunkte:

- die Deutschland-/Ausreise-Genehmigungsfrage wurde in der Policy noch als `single_lane` / `executor` eingeordnet, obwohl sie faktisch ein strittiger Recherche-/Verifikationsfall ist
- der `google-calendar`-Skill wurde ueber `scripts/__init__.py` gestartet und fiel deshalb mit einem Importfehler aus

### Umgesetzt

- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - neue Claim-Check-Hinweise fuer `stimmt das` / `ist das wahr` / `das ist falsch`
  - neue Politik-/Rechts-Hinweise fuer `Bestrebungen`, `Gesetz`, `Genehmigung`, `Ausreise`, `Deutschland`
  - Kombination aus Claim-Check + Politik/Recht erzwingt jetzt `knowledge_research`
- [tools/planner/tool.py](/home/fatih-ubuntu/dev/timus/tools/planner/tool.py)
  - `_pick_entry_script(...)` ignoriert jetzt `__init__.py` als Skill-Entrypoint
- [utils/skill_types.py](/home/fatih-ubuntu/dev/timus/utils/skill_types.py)
  - Python-Skill-Skripte liefern jetzt bei JSON-`stdout` zusaetzlich `parsed_output`
- [skills/google-calendar/scripts/run.py](/home/fatih-ubuntu/dev/timus/skills/google-calendar/scripts/run.py)
  - neuer echter Runtime-Entrypoint fuer `status`, `list`, `create`, `delete`
  - bekannte Setup-Zustaende wie fehlendes Token werden als strukturierte JSON-Antwort statt als Import-/Exit-Fehler geliefert

### Regressionen

- [tests/test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
  - strittiger Deutschland-/Genehmigungsclaim geht jetzt in `knowledge_research`
- [tests/test_orchestration_policy.py](/home/fatih-ubuntu/dev/timus/tests/test_orchestration_policy.py)
  - derselbe Claim laeuft nicht mehr als `single_lane/executor`
- [tests/test_planner_skill_catalog_bridge.py](/home/fatih-ubuntu/dev/timus/tests/test_planner_skill_catalog_bridge.py)
  - `__init__.py` wird als Entry-Script ignoriert
  - JSON-Output aus Skill-Skripten wird strukturiert erkannt

### Validierung

- `python -m py_compile` gruen
- `56 passed` in `tests/test_meta_orchestration.py` + `tests/test_orchestration_policy.py`
- `6 passed` in `tests/test_planner_skill_catalog_bridge.py`
- `timus-mcp` und `timus-dispatcher` neu geladen
- `timus-mcp` wieder `healthy` um `20:40:04 CEST`

## Status 2026-04-03 21:18 CEST - Wo wir stehen

### Phase-B-Stand

- Gesamtstand Phase B: ca. **90-92%**
- Fokus verschiebt sich von grobem Routing/Fallback-Fixing auf **Autonomie-Qualität und Antwortdisziplin**

### Bereits stabilisiert

- Follow-up-/Proposal-Routing fuer `ja mach das`, `ok fang an`, `mach das`, `leg los`
- `RESOLVED_PROPOSAL` zurueck nach `meta` statt falschem Pfad in `executor`
- Delegation-Blackboard-Reads ueber `delegation:`-Keys
- Guided-Follow-up-Prioritaet gegen schwache Generic-Proposals
- `developer`-Crash `list has no attribute get`
- False Positives bei Navigation-/Vision-Routing aus angereichertem Kontext
- natuerlichere Antwort-Finalisierung ohne starres `Hier ist deine Liste:`
- Dispatcher-Bypass fuer klare Meta-Queries (`blackboard`, `google calendar`)
- Beobachtungslog gegen Test-Pollution
- direkte Meta-Reads fuer Screentext/OCR statt teurer `visual`-Delegation
- Guard gegen fehlgeroutete `meta -> executor`-Research-Delegationen
- automatischer strukturierter Handoff fuer rohe `executor`-Simple-Lookups

### Neuester Fortschritt

- Timus fuehrt bei offensichtlichen Runtime-Diagnosen jetzt **erste sichere Read-only-Evidenzschritte selbst aus**, statt nur Analyse + Empfehlungen auszugeben
- Der Agent-Loop salvaget sichere eingebettete Runtime-Actions aus vorschnellen `Final Answer`-Antworten
- `reasoning` hat jetzt eine explizite Runtime-/Betriebszustand-Disziplin im Prompt
- Direkte YouTube-Links mit Wahrheits-/Faktencheck werden nicht mehr als lockere YouTube-Suche missverstanden
- Deep Research ist jetzt generisch haerter gegen **duenne/off-topic Negativbefunde**, damit aus "kein belastbarer Beleg" nicht vorschnell "Fakenews" wird
- Der Dispatcher erkennt direkte YouTube-Verifikationssaetze jetzt frueh genug und laesst sie nicht mehr in `empty_decision` laufen
- Deutschland-bezogene Recherche priorisiert jetzt deutlich staerker **auslaendische, unabhaengige Einordnungsquellen**, waehrend deutsche staatsnahe Quellen nur noch als Primärkontext und nicht mehr als unabhaengige Bestaetigung zaehlen

## Nachtrag 2026-04-04 - Quellenpolitik fuer Deutschland-bezogene Recherche

### Problemstellung

Ein wiederkehrendes Muster war:

- deutsche staatsnahe Quellen wurden zu leicht als belastbare Gegen- oder Bestaetigungsquelle mitgezaehlt
- Query-Varianten fuer Politik-/Faktencheck-Themen priorisierten noch zu oft `official/government` statt auslaendischer Analyse- und Pressequellen
- der schnelle Research-Ranker konnte staatsnahe deutsche Quellen noch nach oben ziehen, obwohl fuer Einordnung eigentlich ein unabhaengiger Aussenblick sinnvoller ist

Ziel war daher:

- deutsche staatsnahe Quellen weiter fuer `was sagt der Staat selbst?` nutzbar zu halten
- sie aber **nicht mehr als unabhaengige Bestaetigung** zu behandeln
- bei Deutschland-Themen auslaendische, unabhaengige Analyse-/Pressequellen frueher und staerker zu priorisieren

### Umgesetzt

- [tools/deep_research/research_contracts.py](/home/fatih-ubuntu/dev/timus/tools/deep_research/research_contracts.py)
  - neue Erkennung fuer deutsche Regierungs-/staatsnahe Domains
  - `build_source_record_from_legacy(...)` markiert jetzt automatisch `state_affiliated` und `country_code`
  - deutsche staatsnahe Quellen zaehlen in `compute_claim_verdict(...)` nicht mehr als `independent_support`
  - Primär-/Autoritätsnachweis darf weiterhin aus solchen Primärquellen kommen; nur die Unabhaengigkeitszaehlung wurde getrennt
- [tools/deep_research/tool.py](/home/fatih-ubuntu/dev/timus/tools/deep_research/tool.py)
  - neue `independence_score`-Metrik in der Quellenqualitaet
  - deutliche Abwertung deutscher staatsnaher Quellen als unabhaengige Evidenz bei Deutschland-bezogenen Queries
  - Bonus fuer auslaendische, unabhaengige Perspektiven bei Deutschland-Themen
  - Query-Plan priorisiert fuer `policy_regulation` staerker internationale Presse, unabhaengige Analyse und NGO-/Watchdog-Sicht
  - `preferred_source_types` fuer Politikfragen wurde so gedreht, dass Analyse/Presse frueher kommen und Regulator/Official als Kontextanker erhalten bleiben
- [agent/agents/research.py](/home/fatih-ubuntu/dev/timus/agent/agents/research.py)
  - der schnelle Source-Ranker gibt deutschen staatsnahen Quellen jetzt einen Policy-Malus

### Regressionen

- [tests/test_source_assessment.py](/home/fatih-ubuntu/dev/timus/tests/test_source_assessment.py)
  - Markierung deutscher staatsnaher Quellen
- [tests/test_research_profiles.py](/home/fatih-ubuntu/dev/timus/tests/test_research_profiles.py)
  - Primärquelle + unabhaengige Auslandsquelle fuer `policy_regulation`
- [tests/test_research_improvements.py](/home/fatih-ubuntu/dev/timus/tests/test_research_improvements.py)
  - Ranking-Malus fuer staatsnahe deutsche Domains
- [tests/test_deep_research_report_quality.py](/home/fatih-ubuntu/dev/timus/tests/test_deep_research_report_quality.py)
  - Abwertung der Unabhaengigkeit bei Deutschland-bezogenen Queries

### Validierung

- `python -m py_compile` gruen
- `53 passed` in den fokussierten Source-/Profile-/Ranking-/Quality-Tests

## Nachtrag 2026-04-04 14:35 CEST - Dispatcher-Haertung fuer direkte YouTube-Verifikation

### Problemstellung

Der heutige Live-Fall

- `ueberpruefe das mal ob es wahr ist was da erzaehlt wird https://youtu.be/niHG1OTfBrY`

lief noch in einen Dispatcher-Fehlpfad:

- Observation: `dispatcher_meta_fallback` mit `reason=empty_decision`
- erst `meta` selbst hat den Fall danach sauber als Video-Verifikation an `research` weitergegeben

Das Problem war also:

- `meta_orchestration` konnte den Fall prinzipiell schon
- aber der Dispatcher-Fast-Path und die fruehe Policy-Sprachliste waren fuer genau diese natuerliche deutsche Formulierung noch zu schwach

### Umgesetzt

- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - neuer Fast-Path-Guard fuer `direkte YouTube-URL + Verifikationssprache`
  - Phrasen wie `ueberpruefe`, `pruefe`, `verifiziere`, `ob es wahr ist`, `stimmt das` routen mit direkter YouTube-URL jetzt sofort nach `meta`
- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `_YOUTUBE_FACT_CHECK_HINTS` erweitert, damit Dispatcher-Policy und Meta-Klassifikation dieselbe natuerliche Sprachvariante verstehen

### Regressionen

- [tests/test_dispatcher_self_status_routing.py](/home/fatih-ubuntu/dev/timus/tests/test_dispatcher_self_status_routing.py)
  - neuer Quick-Intent-Test fuer den exakten `niHG1OTfBrY`-Satz
- [tests/test_orchestration_policy.py](/home/fatih-ubuntu/dev/timus/tests/test_orchestration_policy.py)
  - neuer Policy-Test fuer dieselbe natuerliche Verifikationsformulierung

### Validierung

- `python -m py_compile` gruen
- `34 passed` in den fokussierten Dispatcher-/Policy-Regressionen
- direkter Repro:
  - `quick_intent_check(...) == "meta"`
  - `task_type == "youtube_content_extraction"`
  - `route_to_meta == True`

## Nachtrag 2026-04-04 10:54 CEST - Generische Research-Haertung fuer alle Themen

### Problemstellung

Der heutige politische Faktencheck hat gezeigt:

- das Problem war **nicht nur** ein einzelnes Thema
- Timus suchte teils noch zu breit oder mit falscher Quellen-Prioritaet
- und spaetere Agenten konnten aus einem duennen Negativbefund eine zu harte Schlussfolgerung machen

Die eigentliche Zielkorrektur war daher generisch:

- bessere Query-Praezisierung pro Research-Profil
- staerkere Bewertung, ob eine Quelle **wirklich** auf die Leitfrage einzahlt
- vorsichtigere Confidence- und Schlussformulierung bei duennen/off-topic Quellenlagen

### Umgesetzt

- [tools/deep_research/tool.py](/home/fatih-ubuntu/dev/timus/tools/deep_research/tool.py)
  - profilabhaengige Source-Priority-Query-Varianten fuer `policy_regulation`, `scientific`, `news`, `vendor_comparison`, `market_intelligence` und Default/Fact-Check
  - neue `scope_fit_score`-Logik in der Quellenqualitaet
  - Confidence-Downgrade wenn ein grosser Teil der Quellen nicht direkt auf die Leitfrage einzahlt
  - Executive-Summary-Kalibrierung: starke Debunking-Woerter werden bei schwacher Quellenpassung auf `nicht belastbar belegt` zurueckgenommen
  - akademischer Report nennt jetzt explizit die `Quellenpassung` und warnt bei niedriger direkter Themenpassung
- [agent/prompts.py](/home/fatih-ubuntu/dev/timus/agent/prompts.py)
  - `DEEP_RESEARCH_PROMPT_TEMPLATE` hat jetzt eine klare `NEGATIVBEFUND-DISZIPLIN`
  - `META_SYSTEM_PROMPT` traegt dieselbe Vorsichtsregel weiter, damit nachgelagerte Zusammenfassungen duenne Negativbefunde nicht ueberhaerten
- [agent/base_agent.py](/home/fatih-ubuntu/dev/timus/agent/base_agent.py)
  - generischer Final-Answer-Guard fuer ueberharte Negativurteile bei off-topic/duenner Evidenzlage
  - typische Muster wie `Falschinformation` / `Fakenews` / `Geruecht` werden in diesem Fall auf vorsichtige Formulierungen zurueckgenommen

### Regressionen

- [tests/test_agent_loop_fixes.py](/home/fatih-ubuntu/dev/timus/tests/test_agent_loop_fixes.py)
  - Prompt-Regeln fuer Research/Meta
  - Final-Answer-Guard gegen ueberharte Negativurteile
- [tests/test_deep_research_report_quality.py](/home/fatih-ubuntu/dev/timus/tests/test_deep_research_report_quality.py)
  - profilabhaengige Source-Priority-Querys
  - Scope-Fit-Abwertung fuer off-topic High-Authority-Quellen
- [tests/test_research_verdict_runtime.py](/home/fatih-ubuntu/dev/timus/tests/test_research_verdict_runtime.py)
  - Confidence-Downgrade bei schwacher Quellenpassung
  - Kalibrierung von Executive-Summaries bei duennen Negativbefunden

### Validierung

- `python -m py_compile` auf geaenderte Agent-/Prompt-/Research-Dateien gruen
- `52 passed` in den fokussierten Research-/Prompt-/Verdict-Regressionen

### Wirkung

- Timus behandelt diese Klasse jetzt **generisch fuer alle Themen**, nicht nur fuer den heutigen Politikfall
- Mehr Webseiten allein sind nicht mehr der Haupthebel; zuerst werden Suchfokus, Quellenfamilien und Schlusslogik verbessert
- Wenn die Quellenlage duenn oder thematisch schief ist, soll Timus kuenftig sauber sagen:
  - `In den geprueften Quellen finde ich derzeit keinen belastbaren Beleg dafuer.`
  - statt vorschnell: `Das ist Fakenews.`

## Nachtrag 2026-04-04 10:32 CEST - YouTube-Link mit Faktencheck sauber geroutet

### Problemstellung

Der reale Morgenfall in [2026-04-04_task_582b7c10.jsonl](/home/fatih-ubuntu/dev/timus/logs/2026-04-04_task_582b7c10.jsonl) zeigte einen klaren Verstehensfehler:

- Nutzer schickte einen **konkreten YouTube-Link** plus `schau mal ob da etwas wahres dran ist`
- Timus behandelte das als `youtube_light_research`
- der Executor formte daraus eine Suchanfrage und lieferte irrelevante Treffer wie `Peppa Wutz`

Das Problem war also **nicht** die spaetere politische Antwort, sondern die erste falsche Intent-Deutung:

- direkter Video-Link + Wahrheits-/Faktencheck
- wurde als allgemeine YouTube-Discovery-Suche missverstanden

### Umgesetzt

- Routing-Fix in [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - neue Erkennung fuer `YouTube-URL + Faktencheck/Wahrheitspruefung`
  - solche Faelle laufen jetzt als `youtube_content_extraction`
  - bei direktem Video-Link ohne Browser-Auftrag wird gleich das konservative Rezept `youtube_research_only` als Primärrezept gesetzt
  - dadurch geht der Pfad auf **Video-/Quellenanalyse** statt auf bloße Trefferliste
- Defensiver Guard in [agent/agents/executor.py](/home/fatih-ubuntu/dev/timus/agent/agents/executor.py)
  - wenn ein direkter Video-Faktencheck doch noch irrtuemlich als `youtube_light_research` landet, startet `executor` **keine** blinde YouTube-Suche mehr
  - stattdessen kommt eine ehrliche Guard-Antwort statt irrefuehrender Suchtreffer
  - zusaetzlich wird die Suchquery-Normalisierung gegen `Antworte ... Nutzeranfrage:`-Praefixe robust gehalten
- Regressionen:
  - [tests/test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
  - [tests/test_orchestration_policy.py](/home/fatih-ubuntu/dev/timus/tests/test_orchestration_policy.py)
  - [tests/test_executor_youtube_light.py](/home/fatih-ubuntu/dev/timus/tests/test_executor_youtube_light.py)

### Validierung

- `python -m py_compile` auf geaenderte Routing-/Executor-/Test-Dateien gruen
- `57 passed` in den fokussierten YouTube-/Orchestration-Regressionen

### Wirkung

- Konkrete YouTube-Links mit `stimmt das`, `wahres dran`, `Faktencheck`, `Behauptung`, `Geruecht` o. ae. werden nicht mehr wie eine lockere Discovery-Anfrage behandelt
- der Morgenfall aus dem Chatverlauf ist damit genau auf der Missverstaendnis-Stelle abgesichert
- falls ein aehnlicher Fall trotzdem in `executor` landet, ist der Fallback jetzt defensiv statt halluzinatorisch

## Nachtrag 2026-04-04 10:12 CEST - Guard gegen falsche Executor-Research-Delegation

### Problemstellung

Im heutigen Beobachtungslog war der klarste echte Laufzeitfehler:

- in [2026-04-04_task_a5b542a0.jsonl](/home/fatih-ubuntu/dev/timus/logs/2026-04-04_task_a5b542a0.jsonl) delegierte `meta` einen politischen Faktencheck an `executor`
- die vorhandene Task-Klassifizierung bewertet genau diese Anfrage aber als `knowledge_research`
- Ergebnis: `executor` lief in den 120s-Timeout und `meta` musste danach auf `research` umplanen

Damit war das eigentliche Problem nicht ein "langsamer executor", sondern eine **falsche rohe Delegation ohne strukturierten Guard**.

### Umgesetzt

- Delegations-Normalisierung in [agent/base_agent.py](/home/fatih-ubuntu/dev/timus/agent/base_agent.py)
  - rohe `delegate_to_agent(... executor ...)`-Aufrufe werden jetzt vor dem Tool-Call gegen `classify_meta_task(...)` gespiegelt
  - wenn `meta` einen echten `knowledge_research`-Task faelschlich an `executor` schicken will, wird intern automatisch auf `research` korrigiert
  - wenn ein echter `simple_live_lookup` / `simple_live_lookup_document` / `youtube_light_research` ohne Handoff an `executor` geht, wird automatisch ein strukturierter `# DELEGATION HANDOFF` gebaut
- Regressionen in [tests/test_agent_loop_fixes.py](/home/fatih-ubuntu/dev/timus/tests/test_agent_loop_fixes.py)
  - `meta -> executor` bei `knowledge_research` wird auf `research` umgebogen
  - rohe `executor`-Simple-Lookups bekommen automatisch den leichten Handoff

### Validierung

- `python -m py_compile agent/base_agent.py tests/test_agent_loop_fixes.py` gruen
- `29 passed` in [tests/test_agent_loop_fixes.py](/home/fatih-ubuntu/dev/timus/tests/test_agent_loop_fixes.py)
- zusaetzlich `3 passed` in [tests/test_executor_delegation_stability.py](/home/fatih-ubuntu/dev/timus/tests/test_executor_delegation_stability.py)
- zusaetzlich relevante Meta-Klassifizierung gruen:
  - `1 passed` in [tests/test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)

### Live-Befund

- frischer Repro in [2026-04-04_task_4a7f23a3.jsonl](/home/fatih-ubuntu/dev/timus/logs/2026-04-04_task_4a7f23a3.jsonl)
  - `meta` wollte im LLM-Text erneut an `executor` delegieren
  - der zentrale Guard hat das intern korrigiert
- App-Log-Beweis in [timus_server.log](/home/fatih-ubuntu/dev/timus/timus_server.log)
  - `2026-04-04 10:10:04,866 | WARNING | TimusAgent-v4.4 | Delegation auto-korrigiert: meta wollte executor, Klassifizierung verlangt research | task_type=knowledge_research`

### Offener Rest

- Der Guard verhindert den heutigen Timeout-Pfad sauber.
- Als naechster Folgeschritt bleibt der **Dispatcher-Memory-Write-Spike** vom 04.04.2026 als neuer groesster Beobachtungs-Kandidat.

### Was als Nächstes ansteht

1. **Single-Action-Disziplin im Reasoning-Agenten**
   - aktueller Live-Befund: das Modell mischt noch mehrere `Action:`-Vorschlaege in einer Antwort
   - Ziel: pro Schritt genau eine sichere, priorisierte Aktion
2. **Sauberer Runtime-Diagnosepfad**
   - nach Blackboard-/Service-Hinweisen bevorzugt in echte Evidenzpfade (`system`, `stats`, `logs`) bleiben
   - keine halbfertigen Workaround-Blackboard-Writes mitten in der Diagnose
3. **Alibaba/Qwen-Recheck nach KYC-Freigabe**
   - Timus-seitige Vorbereitung steht
   - externer Blocker bleibt aktuell Alibaba Risk/KYC

### Letzte Verifikation

- fokussierte Regressionen gruen
- Live-Showcase bestaetigt: Runtime-Diagnose startet jetzt mit echter Observation statt reiner Schlussantwort
- `timus-mcp` nach Reload wieder `healthy` um **2026-04-03 21:15:42 CEST**

## Nachtrag 2026-04-03 21:17 CEST - Mehr selbstbewusstes Runtime-Handeln im Agent-Loop

### Problemstellung

Im Live-Showcase blieb Timus bei Runtime-/Betriebszustandsfragen noch zu passiv:

- erst Analyse und Priorisierung
- dann lediglich empfohlene `Action:`-Snippets in der Antwort
- aber keine oder zu wenige echte eigene Evidenzschritte

Zusätzlich gab es einen unguenstigen Sonderfall:

- das Modell konnte eine `Final Answer:` formulieren und darin trotzdem noch eine sinnvolle, sichere Read-only-Aktion verstecken
- der alte Loop brach an dieser Stelle sofort ab

### Umgesetzt

- Agent-Loop-Haertung in [agent/base_agent.py](/home/fatih-ubuntu/dev/timus/agent/base_agent.py)
  - neue enge Salvage-Regel fuer eingebettete Runtime-Actions in vorschnellen `Final Answer`-Antworten
  - nur fuer kleine sichere Menge an Read-only-Diagnosepfaden
  - keine breite Auto-Ausfuehrung beliebiger eingebetteter Aktionen
- Runtime-Disziplin im [agent/prompts.py](/home/fatih-ubuntu/dev/timus/agent/prompts.py)
  - bei Timus-Zustand / Services / CPU-RAM-Disk / Blackboard-Audits erst Evidenz holen
  - nach Blackboard-Hinweisen nicht sofort finalisieren
  - keine `Action:`-Snippets mehr in `Final Answer` verstecken
- Regressionen in [tests/test_agent_loop_fixes.py](/home/fatih-ubuntu/dev/timus/tests/test_agent_loop_fixes.py)
  - Runtime-Kontext erforderlich fuer Action-Salvage
  - sicherer eingebetteter Schritt wird vor Finalisierung wirklich ausgefuehrt
  - Prompt-Disziplin fuer Runtime-/Betriebszustand abgesichert

### Validierung

- `python -m py_compile agent/base_agent.py agent/prompts.py tests/test_agent_loop_fixes.py` gruen
- `27 passed` in `tests/test_agent_loop_fixes.py`
- `timus-mcp` neu geladen, danach wieder `healthy`

### Live-Befund

- Erster Showcase-Fix:
  - in [logs/2026-04-03_task_99c67948.jsonl](/home/fatih-ubuntu/dev/timus/logs/2026-04-03_task_99c67948.jsonl) fuehrt Timus nach der Analyse zumindest selbst `read_from_blackboard(topic="ambient_audit")` aus, statt direkt nur bei Text zu bleiben
- Zweiter Showcase nach Prompt-Update:
  - in [logs/2026-04-03_task_57018090.jsonl](/home/fatih-ubuntu/dev/timus/logs/2026-04-03_task_57018090.jsonl) startet `reasoning` direkt mit echten Runtime-Evidenzschritten
  - sichtbar ist zuerst `get_service_status("timus-mcp.service")`
  - damit ist der grobe Passivitaetsfehler gebrochen: Timus handelt in diesem Pfad jetzt spuerbar selbststaendiger

### Offener Rest

- Das Modell ist noch nicht sauber genug bei **Single-Action pro Schritt**
- im zweiten Showcase produzierte `reasoning` zuerst mehrere `Action:`-Vorschlaege in einer Antwort
- danach driftete der Pfad teilweise in halbdiagnostische Blackboard-Writes

Das ist jetzt der naechste konkrete Arbeitsblock.

## 2026-04-03 — Phase B: Action-Continuation-Routing, Delegation-Blackboard-Fix und Guided-Follow-up-Priorität

### Problemstellung

Die Phase-B-Follow-up-Logik hatte am 2026-04-03 noch drei reale Laufzeitprobleme:

- Kurze Zustimmungen wie `ja mach das` wurden zwar erkannt, aber im Proposal-Pfad teils falsch an `executor` statt an `meta` weitergegeben.
- Delegationsresultate wurden über ihren `blackboard_key` gespeichert, aber spätere Reads behandelten denselben Wert als `topic`, wodurch leere Blackboard-Lookups entstanden.
- Ein Guided-Follow-up wie `Hast du schon ein Google Cloud Projekt oder soll ich dich durch die Erstellung führen?` wurde bei `ok fang an` semantisch falsch auf ein schwaches Generic-Proposal `führen` reduziert, statt die offene Rückfrage fortzusetzen.

### Umgesetzt

- Follow-up-/Proposal-Härtung in [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - `ok fang an`, `fang an`, `ok leg los`, `leg los` als echte Zustimmungen ergänzt
  - explizite Agenten-Angebote wie `den developer-Agenten beauftragen ...` werden jetzt als `agent_delegation` erkannt
  - `RESOLVED_PROPOSAL` mit `target_agent` wird direkt zurück an `meta` geroutet
  - Guided-Angebote vom Typ `soll ich dich durch ... führen` werden nicht mehr zu bloß `führen` degradiert
  - neue Prioritätsregel: eine explizite `pending_followup_prompt` gewinnt gegen schwache `generic_action`-Proposals
- Delegation-Result-Contract in [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
  - Platzhalter-Erfolge wie `Maximale Anzahl an Schritten erreicht, ohne finale Antwort` werden nicht mehr als `success`, sondern als `partial` klassifiziert
- Blackboard-Key-Lookup in [tools/blackboard_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/blackboard_tool/tool.py)
  - `read_from_blackboard(...)` kann Delegations-`blackboard_key`s jetzt direkt gegen `delegation_results` auflösen
  - Rückgabe enthält `lookup_mode=delegation_key`, wenn dieser Fallback gezogen wurde
- Meta-Follow-up-Anker in [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `ok fang an`, `mach das`, `leg los` gelten jetzt auch im Meta-Dialogzustand als kontextverankerte Fortsetzung

### Validierung

- Neue/erweiterte Regressionen:
  - [tests/test_phase_b_action_continuation.py](/home/fatih-ubuntu/dev/timus/tests/test_phase_b_action_continuation.py)
  - [tests/test_blackboard_tool_key_lookup.py](/home/fatih-ubuntu/dev/timus/tests/test_blackboard_tool_key_lookup.py)
  - [tests/test_m3_partial_results.py](/home/fatih-ubuntu/dev/timus/tests/test_m3_partial_results.py)
  - [tests/test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
- Testläufe:
  - `53 passed` in Proposal-/Phase-B-/Partial-Regressionen
  - `39 passed` in `auto_blackboard_write` + `meta_recipe_execution`
  - `20 passed` in `m3_delegate_parallel`
  - `82 passed` in `test_phase_b_action_continuation.py`, `test_meta_orchestration.py`, `test_reference_and_proposal.py`
- Live-Replay nach Neustart:
  - `ja mach das` läuft jetzt in `meta`, nicht mehr in `executor`
  - `ok fang an` startet jetzt korrekt in `meta`
  - der problematische Guided-Fall wird jetzt als `# FOLLOW-UP CONTEXT` mit `pending_followup_prompt` fortgesetzt statt als `# RESOLVED_PROPOSAL kind: generic_action suggested_query: führen`
- Dienststatus:
  - `timus-mcp` nach Neustart wieder `healthy` am `2026-04-03 19:11:41 CEST`

### Offener Punkt

Der nächste echte Laufzeitfehler liegt jetzt hinter dem Routing:

- Delegation an `developer` scheitert im Live-Task `task_b0bef236` mit `'list' object has no attribute 'get'`

Dieser Fehler ist nach den Phase-B-Fixes nun der nächste direkte Arbeitsblock.

### Nachtrag 03.04.2026 20:19:29 CEST — Navigation-Classifier entkoppelt und Shell-Auto-Vision deaktiviert

#### Problemstellung

Nach den Routing-Fixes blieb ein weiterer Phase-B-Laufzeitfehler sichtbar:

- `structured_navigation_fallback` sprang bei nicht-visuellen Queries wie `hey timus kannst du meinen googlekalender einsehen` und `was gibts auf dem blackboard` an, obwohl es keine Browser-Aufgaben waren.
- Ursache: `BaseAgent` klassifizierte Navigation auf dem **voll angereicherten Meta-/Memory-Task**, nicht auf der eigentlichen Nutzeranfrage.
- Zusätzlich konnte der `shell`-Agent bei Aufgaben mit Begriffen wie `google-calendar` fälschlich in den multimodalen Pfad geraten und scheiterte dann mit `404 - No endpoints found that support image input`.

#### Umgesetzt

- Aufgaben-Extraktion in [agent/base_agent.py](/home/fatih-ubuntu/dev/timus/agent/base_agent.py)
  - neue Helper-Methode `_extract_primary_task_text(...)`
  - bevorzugt die eigentliche Aufgaben-Sektion aus `# CURRENT USER QUERY`, `AKTUELLE_NUTZERANFRAGE:` oder `# AUFGABE`
  - ignoriert nachgelagerte Skill-/Memory-/Decomposition-Hinweise
- Navigation-/Recall-Guards in [agent/base_agent.py](/home/fatih-ubuntu/dev/timus/agent/base_agent.py)
  - Memory-Recall, Navigationserkennung und Structured-Navigation arbeiten jetzt auf der extrahierten Primäraufgabe
  - Analytics-/Restart-Guards nutzen ebenfalls den bereinigten Task-Text
- Navigation-Patterns in [agent/base_agent.py](/home/fatih-ubuntu/dev/timus/agent/base_agent.py)
  - nackte Einzelwörter `google` und `amazon` entfernt
  - ersetzt durch spezifischere Marker wie `google.com`, `google.de`, `google maps`, `amazon.com`, `amazon.de`
- Shell-Härtung in [agent/agents/shell.py](/home/fatih-ubuntu/dev/timus/agent/agents/shell.py)
  - `self._vision_enabled = False`
  - Shell-Aufgaben hängen damit keine Auto-Screenshots mehr an LLM-Requests

#### Validierung

- Neue Regressionen:
  - [tests/test_navigation_task_extraction.py](/home/fatih-ubuntu/dev/timus/tests/test_navigation_task_extraction.py)
- Testlauf:
  - `33 passed` in `tests/test_navigation_task_extraction.py`, `tests/test_agent_loop_fixes.py`, `tests/test_phase_b_action_continuation.py`
- Dienststatus:
  - `timus-mcp` nach Neustart wieder `healthy` um `03.04.2026 20:17:04 CEST`
- Live-Replay:
  - `task_f2a01e70` (`hey timus kannst du meinen googlekalender einsehen`)
    - startet jetzt direkt mit `working_memory_injected`
    - **kein** `structured_navigation_fallback`
    - **kein** Shell-`image input`-404
    - erfolgreicher Abschluss um `20:18:45 CEST`
  - `task_c7419cba` (`was gibts auf dem blackboard`)
    - startet ebenfalls direkt mit `working_memory_injected`
    - **kein** `structured_navigation_fallback` mehr im Startpfad

#### Wirkung

Der Phase-B-Classifier reagiert jetzt auf die eigentliche Nutzeraufgabe statt auf zufällige Browser-/Google-Marker im angereicherten Kontext. Damit sind die beiden zuletzt sichtbaren False Positives aus den Live-Replays beseitigt.

---

## ⚠️ NACHTRAG (dokumentiert am 2026-03-27, implementiert 2026-03-23 bis 2026-03-25)

Diese Einträge wurden nicht in Echtzeit protokolliert, sondern nachträglich aus dem Review-Verlauf rekonstruiert.

---

## 2026-03-23 bis 2026-03-25 — Ephemeral Workers für Deep Research + YouTube-Transcript-Fix

### Problemstellung

- Deep Research lieferte bei Depth-5-Läufen zu wenige und zu generische Query-Varianten.
- Semantische Duplikate in Claim-Listen wurden nur deterministisch erkannt, nicht inhaltlich.
- Widersprüche und Evidenzlücken wurden nicht strukturiert in den Report-Kontext eingespeist.
- YouTube-Transkripte wurden hart auf 8000 Zeichen abgeschnitten, wodurch lange Videos kaum analysierbar waren.
- Zusätzlich: `VISUAL_NEMOTRON_KEYWORDS` enthielt zu generische deutsche Wörter (`dann`, `danach`, `unterhaltung`), die normale Konversationstexte fälschlicherweise zum Visual-Nemotron-Agenten routeten.

---

### Ephemeral Workers — Phase 1: Query Variant Worker (2026-03-23)

**Ziel**

Kurzlebige LLM-Worker für Deep Research, ohne Registry, BaseAgent oder Canvas anzufassen. Nur LLM-only, env-gesteuert, budget-aware, mit hartem Fallback auf den deterministischen Pfad.

**Umgesetzt**

- Neue Utility-Schicht [`orchestration/ephemeral_workers.py`](/home/fatih-ubuntu/dev/timus/orchestration/ephemeral_workers.py)
  - `WorkerProfile`, `WorkerTask`, `WorkerResult` (frozen dataclasses)
  - `run_worker(...)` mit vollständiger Fehler-/Timeout-/Budget-Behandlung
  - `run_worker_batch(...)` mit Semaphor und `cap_parallelism_for_budget`
  - Budget unter `deep_research`-Scope, keine versteckten Kosten
  - alle 5 Exit-Pfade (`disabled`, `blocked`, `unsupported_provider`, `timeout`, `error`) liefern `fallback_used=True`
- Integration in [`tools/deep_research/tool.py`](/home/fatih-ubuntu/dev/timus/tools/deep_research/tool.py)
  - `_worker_query_variants_enabled()` — Feature-Flag
  - `_sanitize_worker_query_variants(...)` — Topic-Check + Längenvalidierung
  - `_augment_query_variants_with_worker(...)` — Hook vor Phase 1 der Suche
  - `skipped_no_capacity`-Kurzschluss wenn Query-Budget bereits voll
  - Metadaten unter `session.research_metadata["query_variant_worker"]`
- Env-Flags: `EPHEMERAL_WORKERS_ENABLED`, `EPHEMERAL_WORKER_MODEL`, `EPHEMERAL_WORKER_PROVIDER`, `EPHEMERAL_WORKER_MAX_PARALLEL`, `EPHEMERAL_WORKER_TIMEOUT_SEC`, `EPHEMERAL_WORKER_MAX_TOKENS`, `DR_WORKER_QUERY_VARIANTS_ENABLED`

**Validierung**

- `23 passed` — `tests/test_ephemeral_workers.py`, `tests/test_deep_research_query_workers.py`, `tests/test_deep_research_report_quality.py`, `tests/test_llm_budget_guard.py`
- Lean grün

---

### Ephemeral Workers — Phase 2: Semantic Dedupe Worker (2026-03-24)

**Ziel**

Semantische Merge-Vorschläge für inhaltlich nahezu gleiche Claims, als konservativer Zusatz zur deterministischen Dedupe. Die deterministische Basis bleibt autoritativ.

**Umgesetzt**

- Fensterbasierte Batch-Verarbeitung über `run_worker_batch(...)` — große Claim-Mengen werden in überlappende Fenster aufgeteilt
- `_semantic_claim_overlap_ok(...)` — Token-Coverage-Check ≥ 0.6 als Vorfilter
- `_semantic_merge_protected_terms_ok(...)` — Guard gegen fachlich unterschiedliche Protected Terms (z.B. `Kraft-Momenten-Sensor ≠ Drehmomentsensor`)
- `_filter_semantic_merge_candidates(...)` — Confidence-Gate ≥ 0.85, Pair-Deduplizierung, Cache-Key-Prüfung
- `_apply_semantic_merge_candidates(...)` — Union-Find mit Pfadkompression, Reihenfolge aus Original-Claim-Liste erhalten
- `_apply_cached_semantic_claim_dedupe(...)` — Signature-Check als Cache-Invalidierungs-Guard
- `_populate_semantic_claim_dedupe_cache(...)` — Hook nach Deep Dive, vor Synthese
- Metadaten unter `session.research_metadata["semantic_claim_dedupe"]`
- Env-Flags: `DR_WORKER_SEMANTIC_DEDUPE_ENABLED`, `DR_WORKER_SEMANTIC_DEDUPE_CONFIDENCE_THRESHOLD`, `DR_WORKER_SEMANTIC_DEDUPE_CHUNK_SIZE`, `DR_WORKER_SEMANTIC_DEDUPE_CHUNK_OVERLAP`

**Bekannte Einschränkung**

Signature in `_populate_semantic_claim_dedupe_cache` wird auf allen deterministischen Claims berechnet, in `_apply_cached_semantic_claim_dedupe` aber nur auf `verified_fact | legacy_claim`. Bei Sessions mit gemischten Claim-Typen kann der Cache konservativer als nötig invalidiert werden (kein Correctness-Bug, nur verpasste Merges). Vor produktiver Aktivierung patchen.

**Validierung**

- `34 passed`
- CrossHair grün (`tests/test_deep_research_semantic_dedupe_contracts.py`)
- Lean grün

---

### Ephemeral Workers — Phase 3: Conflict Scan Worker (2026-03-25)

**Ziel**

Strukturierte Analyse von Widersprüchen, Evidenzlücken und schwach abgesicherten Claims vor der finalen Synthese. Nur Metadaten — keine Mutation von Claims oder Evidences.

**Umgesetzt**

- `_claim_report_signal_score(...)` — Risk-gewichtetes Tuple-Sort für Input-Priorisierung
- `_build_conflict_scan_input(...)` — harte Input-Caps: 15 Claims, 8 conflicting_info, 6 open_questions; `notes` auf 200 Zeichen, `unknowns` auf 4 pro Claim begrenzt
- `_normalize_conflict_scan_payload(...)` — toleriert `null`-Listen, Confidence-Gate ≥ 0.83, Output-Caps: 6 Konflikte, 8 offene Fragen, 6 weak_evidence_flags, 6 report_notes
- `_get_conflict_scan_report_context(...)` — sicherer Leser des Caches für Report-Pfade
- `_populate_conflict_scan_cache(...)` — `skipped_no_material` wenn kein Material, harter Fallback bei Fehler
- `recommended_report_section` bewusst nicht implementiert (zu viel Layouter-Verantwortung für den Worker)
- Integration in akademischen Report: separate "Conflict-Scan-Hinweise"-Sektion
- Metadaten unter `session.research_metadata["conflict_scan_worker"]`
- Env-Flags: `DR_WORKER_CONFLICT_SCAN_ENABLED`, `DR_WORKER_CONFLICT_SCAN_CONFIDENCE_THRESHOLD`, `DR_WORKER_CONFLICT_SCAN_MODEL`, `DR_WORKER_CONFLICT_SCAN_MAX_TOKENS` (default 1200), `DR_WORKER_CONFLICT_SCAN_TIMEOUT_SEC` (default 25)

**Offener Punkt**

`_normalize_conflict_scan_payload` kappt `conflicts[:6]` in Reihenfolge des Modell-Outputs ohne Nachsortierung nach Confidence. Vor Phase-2-Erweiterung: absteigende Sortierung nach Confidence vor dem Cap ergänzen.

**Validierung**

- `45 passed`
- CrossHair grün (`tests/test_deep_research_conflict_scan_contracts.py`)
- Lean grün

---

### YouTube-Transcript-Fix (2026-03-25)

**Problemstellung**

- `tools/search_tool/tool.py` schnitt `full_text` aus Transkripten hart auf 8000 Zeichen ab.
- `youtube_researcher.py` holte nur einen gekappten String statt das vollständige Transcript-Payload.
- `_analyze_text(...)` arbeitete mit stumpfem 4000-Zeichen-Limit.
- Lange Videos (> 30 Min.) waren damit praktisch nicht analysierbar.

**Umgesetzt**

- `full_text` in `tool.py` wird nicht mehr abgeschnitten
- `_get_transcript_with_fallback(...)` holt das komplette Payload-Dict
- `_chunk_transcript_items(...)` — segmentbasierte Aufteilung mit Überlapp; passt Chunk-Größe dynamisch an wenn Material sonst zu viele Chunks erzeugen würde
- `_analyze_transcript_payload(...)` — zentraler Einstieg: 1 Chunk direkt analysieren, mehrere Chunks parallel analysieren + verdichten
- `_synthesize_chunk_analyses(...)` — LLM-Gesamtsynthese über Chunk-Ergebnisse, deterministisches `_merge_chunk_analyses` als Fallback ohne OpenRouter-Key

**Validierung**

- `25 passed` — `tests/test_search_tool_serpapi_youtube.py`, `tests/test_youtube_researcher_modes.py`, `tests/test_search_tool_youtube_contracts.py`
- CrossHair grün
- Lean grün

---

### Routing-Fix: Visual-Nemotron False Positives (2026-03-23)

**Problemstellung**

Normale Konversationstexte (z.B. über Predictive Maintenance) wurden fälschlicherweise zum Visual-Nemotron-Agenten geroutet, der sie als Browser-Navigationsbefehle interpretierte.

**Ursache**

`VISUAL_NEMOTRON_KEYWORDS` in `main_dispatcher.py` enthielt sehr generische deutsche Wörter: `dann`, `danach`, `anschließend`, `zuerst`, `unterhaltung`. Parallel dazu hatten `suche`, `formular`, `anmelden`, `login` als Einzelwörter in `_has_browser_ui_action` zu geringe Spezifität.

**Fix**

- `dann`, `danach`, `anschließend`, `zuerst`, `zuerst...dann`, `unterhaltung`, `cookie`, `formular`, `login`, `anmelden` aus `VISUAL_NEMOTRON_KEYWORDS` entfernt
- `suche`, `formular`, `anmelden`, `login` aus `_has_browser_ui_action` entfernt oder auf spezifische Phrasen (`formular ausfüllen`, `anmelden auf`) eingeschränkt
- Verbleibende Keywords sind ausnahmslos explizite Browser-Steuerungsphrsen

**Validierung**

- Manuell: alle Problem-Cases aus Screenshot-Kontext routen nicht mehr zu `visual_nemotron`

---

## 2026-03-26 bis 2026-03-27 — Goal-First Meta-Orchestrierung

### Problemstellung

Timus war in der Meta-Orchestrierung zu stark `recipe-first` und zu wenig `goal-first`.

Konkretes Symptom in dieser Session:

- Bei neuen Situationen wie `hole aktuelle Live-Daten und mache daraus eine Tabelle/Datei` hat Timus das Nutzerziel nicht sauber abstrahiert.
- Der richtige Ablauf `executor -> document` war fachlich vorhanden, wurde aber nicht verlässlich aus dem Ziel selbst abgeleitet.
- Dadurch musste die Kette mehrfach manuell nachgeschärft werden, obwohl ein vollwertiger Assistent solche neuen Kombinationen selbst erkennen sollte.

Zielbild dieser Arbeit:

- Timus soll zuerst verstehen, **was am Ende gebraucht wird**.
- Danach soll er die passende Agenten-/Tool-Kette ableiten.
- Bestehende Rezepte sollen als Sicherheitsnetz erhalten bleiben, aber nicht mehr die einzige Denkform sein.

### Phase 1 — Advisory Goal-First Layer

**Ziel**

Eine erste Ziel- und Fähigkeits-Schicht einziehen, ohne die bestehende Orchestrierung sofort hart umzubauen.

**Umgesetzt**

- Neues Zielmodell in [goal_spec.py](/home/fatih-ubuntu/dev/timus/orchestration/goal_spec.py)
  - `domain`
  - `freshness`
  - `evidence_level`
  - `output_mode`
  - `artifact_format`
  - `uses_location`
  - `delivery_required`
  - `goal_signature`
- Neuer Fähigkeitsgraph in [capability_graph.py](/home/fatih-ubuntu/dev/timus/orchestration/capability_graph.py)
  - bildet benötigte Fähigkeiten gegen vorhandene Agentenprofile ab
  - erkennt Lücken wie fehlende strukturierte Ausgabe- oder Delivery-Stufen
- Neuer beratender Planner in [adaptive_planner.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_planner.py)
  - berechnet empfohlene Ketten
  - bleibt in Phase 1 ausdrücklich nur advisory
- Integration in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `classify_meta_task(...)` liefert jetzt zusätzlich:
    - `goal_spec`
    - `capability_graph`
    - `adaptive_plan`
- Durchleitung bis in den Meta-Handoff:
  - [orchestration_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/orchestration_policy.py)
  - [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)

**Wirkung**

- Meta sieht jetzt nicht mehr nur `task_type` und `recipe_id`, sondern zusätzlich das eigentliche Zielmodell.
- Der Handoff enthält jetzt:
  - `goal_spec_json`
  - `capability_graph_json`
  - `adaptive_plan_json`

**Validierung**

- `52 passed`
- CrossHair grün
- Lean grün

**Commit**

- `a829f6a` — `Add goal-first advisory planning for meta orchestration`

**Live-Aktivierung**

- `timus-mcp` neu gestartet am **27. März 2026 um 00:33 CET**
- Health danach grün

### Phase 2 — Planner-First, Recipes-Fallback

**Ziel**

Die Planner-Schicht nicht nur anzeigen, sondern bei sicheren Fällen wirklich vor die Rezeptwahl setzen.

**Umgesetzt**

- Neue Safe-Adoption-Logik in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py):
  - `resolve_adaptive_plan_adoption(...)`
- Harte Guardrails für Planner-Adoption:
  - nur definierte sichere Task-Typen
  - `confidence >= 0.78`
  - maximale Kettenlänge `4`
  - Entry-Agent darf nicht kippen
  - Recipe-Hint muss auf aktuelles Rezept oder vorhandene Alternativen zeigen
  - Rezeptkette und Planner-Kette müssen übereinstimmen
- Dispatcher-Adoption in [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - sichere Planner-Empfehlungen werden vor dem Meta-Lauf übernommen
  - Ergebnis wird als `planner_resolution` im Handoff sichtbar gemacht
- Meta-Auswahl in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - `_select_initial_recipe_payload(...)` prüft jetzt zuerst den Planner
  - Strategy- und Learning-Fallbacks bleiben erhalten

**Wirkung**

- Bei sicheren Fällen kann Meta jetzt tatsächlich von einem Basisrezept auf eine passendere Kette umschalten.
- Beispielziel:
  - von `simple_live_lookup`
  - auf `simple_live_lookup_document`
  - also praktisch `meta -> executor -> document`
- Gleichzeitig bleibt die Sicherheitsarchitektur erhalten:
  - wenn der Planner unsicher ist, bleibt das bestehende Rezept aktiv

**Neue Handoff-Daten**

- `planner_resolution_json`

**Validierung**

- `33 passed`
- CrossHair grün
- Lean grün

**Commit**

- `88211ae` — `Adopt safe adaptive plans before recipe fallback`

**Live-Aktivierung**

- `timus-mcp` neu gestartet am **27. März 2026 um 12:20 CET**
- `Application startup complete` um **12:20:30 CET**
- Health grün um **12:20:32 CET**

### Phase 3 — Runtime Gap-Replanning nach Stage-Ergebnissen

**Ziel**

Timus soll nicht nur zu Beginn eine gute Kette wählen, sondern auch **während** eines laufenden Rezepts erkennen, wenn das Ziel noch nicht vollständig erfüllt ist.

Konkreter Ziel-Fall:

- Ein `research`- oder `executor`-Schritt liefert bereits verwertbares Material.
- Das Nutzerziel verlangt aber noch ein Artefakt oder eine Tabelle.
- Timus soll dann selbst erkennen: `document_output` fehlt noch und muss sicher nachgeschaltet werden.

**Umgesetzt**

- Neue Runtime-Gap-Erkennung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py):
  - `resolve_runtime_goal_gap_stage(...)`
- Die Runtime-Regel ist konservativ:
  - aktuell nur für fehlende `document_output`-Stufen
  - nur bei `artifact`-/`table`-Zielen
  - nur nach erfolgreicher vorheriger Stage
  - nur wenn verwertbares Material bereits vorhanden ist
  - keine Doppel-Insertion, wenn `document_output` schon im Rezept oder Verlauf enthalten ist
- Integration in den Meta-Lauf in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - nach erfolgreicher Stage wird geprüft, ob noch eine sichere Dokument-Stufe fehlt
  - falls ja, wird `document_output` zur Laufzeit eingefügt
  - die effektive Agentenkette wird für Telemetrie und Feedback mitgezogen
- Abschlussausgabe verfeinert:
  - saubere Dokument-Läufe geben direkt das Artefakt-Ergebnis zurück
  - Recovery-/Fehlerpfade behalten die ausführliche Rezeptzusammenfassung

**Wirkung**

- Timus kann jetzt innerhalb eines laufenden Rezepts Ziel-Lücken erkennen und schließen.
- Beispiel:
  - Ausgangsrezept: `meta -> research`
  - Ziel: `aktuelle LLM-Preise recherchieren und als txt speichern`
  - neuer Laufzeitpfad:
    - `research` liefert verwertbares Material
    - Meta erkennt fehlendes Artefakt
    - `document_output` wird sicher nachgeschaltet

**Validierung**

- `31 passed`
- CrossHair grün
- Lean grün

**Commit**

- `8b43e9b` — `Add runtime goal-gap replanning for document output`

**Status**

- Phase 3 ist fertig implementiert und committed.
- Live-Aktivierung ist zu diesem Stand noch nicht erfolgt.

### Phase 4 — Learned Chains + breiteres Runtime-Replanning (abgeschlossen)

**Ziel**

Timus soll nicht nur Ziele erkennen und sichere Ketten auswählen, sondern aus erfolgreichen Läufen lernen und weitere Ziel-Lücken selbstständig schließen.

Der Kernsprung dieser Phase:

- von statischer Ziel- und Fähigkeitsplanung
- hin zu erfahrungsbasierter Kettenpriorisierung und breiterem Runtime-Replanning

**Bisher umgesetzt**

- Neue Lernschicht in [adaptive_plan_memory.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_plan_memory.py)
  - persistiert Chain-Outcomes pro `goal_signature`
  - speichert empfohlene Kette, finale Kette, Erfolg/Misserfolg, Laufzeit und Runtime-Gap-Insertions
  - aggregiert daraus konservative Chain-Statistiken mit `learned_bias` und `learned_confidence`
- Planner-Anreicherung in [adaptive_planner.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_planner.py)
  - Candidate-Scores koennen jetzt durch gelernte positive oder negative Erfahrungswerte nachjustiert werden
  - Candidate-Payloads zeigen `learned_bias` und Evidenz
- Integration in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `classify_meta_task(...)` liest gelernte Chain-Statistiken fuer die aktuelle `goal_signature`
  - der Adaptive Planner bekommt diese Daten direkt in den Planungsaufruf
- Rueckschreiben in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - echte Rezeptlaeufe schreiben ihre Outcomes jetzt in den Lernspeicher zurueck
  - Runtime-Gap-Insertions wie `runtime_goal_gap_document` werden dabei explizit markiert
- Erweiterung der Runtime-Gap-Erkennung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `runtime_goal_gap_verification`
  - `runtime_goal_gap_delivery`
- Integration in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - `verification_output` wird vor spaeteren `document`-/`communication`-Stages eingefuegt
  - `communication_output` wird nach erfolgreicher Material- oder Artefakt-Erzeugung sicher nachgeschaltet
  - Communication-Handoffs tragen jetzt auch `attachment_path` und `source_material`
- Validierung

### 2026-03-27 — Wochenbeobachtung fuer Goal-First- und Self-Hardening-Livebetrieb

**Ziel**

Die neuen Autonomiepfade sollen nicht nur live laufen, sondern eine Woche lang strukturiert beobachtet und danach belastbar ausgewertet werden.

**Umgesetzt**

- Neue Beobachtungsschicht in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - strukturierter JSONL-Log unter `logs/autonomy_observation.jsonl`
  - Session-State unter `logs/autonomy_observation_state.json`
  - Start-/Fensterverwaltung fuer ein 7-Tage-Beobachtungsfenster
  - verdichtete Summary-Funktion fuer Planner-, Runtime-Gap- und Self-Hardening-Signale
- Neue Hooks in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - `meta_recipe_outcome`
  - `runtime_goal_gap_inserted`
- Neue Hooks in [self_hardening_runtime.py](/home/fatih-ubuntu/dev/timus/orchestration/self_hardening_runtime.py)
  - `self_hardening_runtime_event`
  - deckt dadurch auch `self_modify_started` / `self_modify_finished` sauber mit ab
- Neue Hilfsskripte:
  - [start_autonomy_observation.py](/home/fatih-ubuntu/dev/timus/scripts/start_autonomy_observation.py)
  - [evaluate_autonomy_observation.py](/home/fatih-ubuntu/dev/timus/scripts/evaluate_autonomy_observation.py)

**Wirkung**

- Wir muessen nach der Beobachtungswoche nicht mehr manuell Rohlogs auswerten.
- Die Auswertung kann jetzt direkt messen:
  - wie oft Planner-Adoptionen wirklich genutzt wurden
  - welche Runtime-Gaps eingefuegt wurden
  - wie erfolgreich Meta-Rezeptketten liefen
  - wie oft Self-Hardening und Self-Modify aktiv wurden

**Validierung**

- neue Unit-Tests fuer Beobachtungsspeicher und Summary
- Meta-Rezept-Test fuer Runtime-Gap-Observation
- Self-Hardening-Runtime-Test fuer Observation-Hook
- CrossHair auf den Summary-Vertrag
- Lean erweitert

**Beobachtungspunkt waehrend der Wochenbeobachtung**

- `user_reported_state_update` / `state_invalidation`
  - Beispiel:
    - Nutzer: `ich habe meinen handy standort aktualisiert`
    - Meta wiederholt trotzdem den alten Status `kein synchronisierter Handy-Standort`
  - Interpretation:
    - Meta erkennt die Aussage noch nicht als Zustandskorrektur gegen einen veralteten Tool-/Agenten-Output
  - Soll spaeter ausgewertet werden als:
    - Wie oft Nutzer einen geaenderten Zustand meldet
    - Wie oft Timus danach noch stale Resultate wiederholt
    - Wie oft stattdessen eine frische Revalidierung erfolgt
  - Geplanter spaeterer Ausbau:
    - `State Correction Handling`
    - Nutzerhinweis invalidiert den betroffenen Teilkontext
    - Meta erzwingt danach frischen Statuscheck statt normalem Follow-up-Rezept

### Nach der Beobachtungswoche — Plan fuer eine semantische Meta-Verstehensschicht

**Ausloeser**

Ein aktueller Fehlfall zeigt die naechste Reifegradgrenze von Timus klar:

- Anfrage: `ich moechte ein cafe eroeffnen welches land ist am besten geeignet`
- Falsches Verhalten:
  - Meta hat den Begriff `Cafe` zu stark als lokalen Places-/Maps-Hinweis gelesen
  - daraus wurde sinngemaess `location_local_search`
  - der aktive Standort wurde dadurch faelschlich priorisiert
- Eigentliches Ziel:
  - keine lokale Suche
  - sondern eine strategische Geschaefts- und Standortentscheidung

**Problemkern**

Meta arbeitet aktuell noch zu stark als:

- Task-Klassifikator
- Rezeptwaehler
- Heuristik-Orchestrator

und noch nicht stark genug als:

- Bedeutungs-Interpreter
- Intent-Modellierer
- Konfliktpruefer zwischen moeglichen Lesarten

**Zielbild**

Vor der Rezeptwahl soll eine neue Schicht eingefuehrt werden:

- `Meta Semantic Understanding Layer`

Diese Schicht soll nicht nur Keywords lesen, sondern die Anfrage in konkurrierende Lesarten zerlegen und semantisch priorisieren.

**Architekturplan**

1. `semantic_intent.py`
- neue Datei in `orchestration/`
- erzeugt 2-4 moegliche Lesarten einer Anfrage
- Beispiel:
  - `local_place_lookup`
  - `business_planning`
  - `country_comparison`
  - `knowledge_research`

2. `SemanticIntentSpec`
- strukturierte Darstellung der Bedeutung
- geplante Felder:
  - `primary_intent`
  - `secondary_intents`
  - `domain_object`
  - `decision_scope`
  - `freshness_need`
  - `location_relevance`
  - `artifact_need`
  - `delivery_need`
  - `evidence_need`
  - `competing_interpretations`
  - `rejection_reasons`

3. Konfliktregeln zwischen Lesarten
- Beispiele:
  - `country_comparison` widerspricht `location_local_search`
  - `business_planning` widerspricht `nearby_places`
  - `current_position_lookup` darf nicht aus einem blossen Branchenwort abgeleitet werden
- diese Konflikte muessen explizit modelliert werden statt nur implizit in Keywords zu stecken

4. Integration in `meta_orchestration.py`
- `classify_meta_task(...)` soll nicht mehr direkt aus Keywords auf `task_type` springen
- neuer Ablauf:
  - Query normalisieren
  - semantische Lesarten erzeugen
  - Konflikte bewerten
  - daraus `goal_spec` und `task_type` ableiten

5. `goal_spec.py` erweitern
- das Zielmodell soll spaeter nicht nur Task-Typen tragen, sondern schon die semantische Absicht reflektieren
- moegliche neue Felder:
  - `intent_family`
  - `decision_scope`
  - `location_relevance_confidence`

6. Adaptive Planner spaeter mitnutzen
- der Planner soll nicht nur `GoalSpec + CapabilityGraph` lesen
- sondern auch die semantische Hauptlesart und verworfene Alternativen sehen
- damit Timus spaeter sagen kann:
  - `Cafe` erkannt
  - aber `business_planning` gewinnt gegen `local_search`

7. Tests / Validierung
- neue Regressionen fuer typische Fehlklassen:
  - `ich moechte ein cafe eroeffnen welches land ist am besten geeignet`
  - `ich will ein restaurant gruenden wo waere der beste markt`
  - `welches land ist fuer eine baeckerei am attraktivsten`
  - weiterhin lokal korrekt:
    - `suche mir ein cafe in meiner naehe`
    - `wo bekomme ich gerade kaffee`
- dazu:
  - CrossHair-Contracts fuer Konfliktregeln
  - Lean-Invarianten fuer ausgeschlossene Fehlklassifikationen

**Rollout-Vorschlag**

Phase A
- nur advisory neben der bisherigen Klassifikation
- protokollieren, wenn semantische Lesart und heuristische Klassifikation auseinanderlaufen

Phase B
- semantic-first, heuristic-fallback

Phase C
- semantische Lesarten in Learned Chains und Runtime-Gaps rueckkoppeln

**Erfolgskriterium**

Timus soll bei mehrdeutigen Anfragen nicht mehr nur auf bekannte Rezepte springen, sondern die eigentliche Bedeutung priorisieren.

Das konkrete Minimalziel:

- `Cafe` in einer Gruendungs- oder Laendervergleichsfrage darf nie mehr automatisch zu `location_local_search` fuehren.
  - `26 passed` in der fokussierten Runtime-Gap-Suite
  - `48 passed` fuer den Phase-4-Lernsockel
  - CrossHair gruen
  - Lean gruen

**Erreichte Zielabdeckung**

- Lernspeicher fuer erfolgreiche und gescheiterte Agentenketten
- Planner-Anreicherung mit Erfahrungswissen
- Runtime-Gap `document_output`
- Runtime-Gap `delivery`
- Runtime-Gap `verification`

**Commits**

- `2831bde` — `Add learned chain memory for adaptive planning`
- `a5ec788` — `Complete adaptive runtime gap replanning`

**Status**

- Phase 4 ist vollständig implementiert, committed und nach `origin/main` gepusht.
- Live-Aktivierung ist zu diesem Stand noch nicht erfolgt.

**Geplante Dateien**

- Neue Datei [adaptive_plan_memory.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_plan_memory.py)
  - persistiert gelernte Ketten kompakt und deterministisch
- Erweiterung in [adaptive_planner.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_planner.py)
  - kombiniert statische Planner-Heuristik mit Erfahrungsdaten
- Erweiterung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - zusätzliche Runtime-Gap-Typen
  - sichere Adoptionslogik für gelernte Ketten
- Erweiterung in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - schreibt Outcome-Signale nach Stage- und Gesamterfolg zurück
  - nutzt gelernte Ketten nur innerhalb harter Guardrails
- Kleiner Infrastruktur-Fix in [verify_pre_commit_lean.py](/home/fatih-ubuntu/dev/timus/scripts/verify_pre_commit_lean.py)
  - nutzt fuer `CiSpecs.lean` jetzt bevorzugt die lokal installierte Lean-Toolchain statt den `elan`-Wrapper
  - vermeidet unnoetige Download-/Timeout-Pfade in der lokalen Verifikation

**Guardrails**

- keine freie Rekursion
- maximale Kettenlänge bleibt begrenzt
- gelernte Ketten dürfen nur bekannte Agenten nutzen
- `research` bleibt ein teurer Spezialpfad und wird nicht aggressiv hochpriorisiert
- negative Lernsignale dürfen nur abwerten, nicht sofort alle Alternativen blockieren
- neue Runtime-Gap-Typen werden einzeln und konservativ aktiviert

**Implementierungsreihenfolge**

1. Lernspeicher für Ketten-Outcome
2. Planner-Priorisierung mit Erfahrungsdaten
3. Runtime-Gap `delivery`
4. Runtime-Gap `verification`
5. erweiterte Regressionen, Contracts und Lean-Invarianten

**Erfolgskriterium**

- Timus soll bei wiederkehrenden Zielmustern schneller zur funktionierenden Kette greifen
- Timus soll bekannte Fehlpfade seltener wiederholen
- Timus soll nach erfolgreichen Zwischenresultaten weitere sichere Ziel-Lücken selbst schließen

### Aktueller Stand

Timus ist nach dieser Session auf einem deutlich besseren Orchestrierungsniveau, aber noch nicht am Endziel.

**Jetzt live vorhanden**

- Goal-first-Zielmodell
- Capability-Mapping
- Advisory-Planung
- Sichere Planner-Adoption vor Rezept-Fallback
- Vollständige Meta-Handoff-Sichtbarkeit der neuen Planungsdaten
- Sichere Runtime-Lückenerkennung für `document`, `verification` und `delivery` ist implementiert, aber noch nicht live aktiviert

**Noch nicht fertig**

- optionale weitere Gap-Typen
  - z. B. `local context`
- breitere Nutzung außerhalb der aktuellen Meta-/Recipe-Pfade

### Relevante Dateien dieser Session

- [goal_spec.py](/home/fatih-ubuntu/dev/timus/orchestration/goal_spec.py)
- [capability_graph.py](/home/fatih-ubuntu/dev/timus/orchestration/capability_graph.py)
- [adaptive_plan_memory.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_plan_memory.py)
- [adaptive_planner.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_planner.py)
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- [orchestration_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/orchestration_policy.py)
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- [communication.py](/home/fatih-ubuntu/dev/timus/agent/agents/communication.py)
- [verify_pre_commit_lean.py](/home/fatih-ubuntu/dev/timus/scripts/verify_pre_commit_lean.py)
- [CiSpecs.lean](/home/fatih-ubuntu/dev/timus/lean/CiSpecs.lean)
- [test_adaptive_plan_memory.py](/home/fatih-ubuntu/dev/timus/tests/test_adaptive_plan_memory.py)
- [test_adaptive_plan_memory_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_adaptive_plan_memory_contracts.py)
- [test_runtime_goal_gap_replan.py](/home/fatih-ubuntu/dev/timus/tests/test_runtime_goal_gap_replan.py)
- [test_runtime_goal_gap_replan_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_runtime_goal_gap_replan_contracts.py)
- [test_meta_recipe_execution.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_recipe_execution.py)

### Nächster sinnvoller Schritt

Den jetzt gepushten Phase-3/Phase-4-Stand live schalten und beobachten:

- erweitertes Runtime-Replanning auf `timus-mcp` aktivieren
- echte Live-Fälle prüfen, ob `executor -> research`, `research -> document` und `document -> communication` stabil nachgezogen werden
- beobachten, ob gelernte Ketten bei wiederkehrenden `goal_signature`-Mustern schon sichtbar bevorzugt werden
- anschließend entscheiden, ob ein weiterer konservativer Gap-Typ wie `local context` sinnvoll ist

---

## 2026-03-29 — Meta-Ausbau Phase M1: Diagnosis Discipline

### Beobachtungsbasis

Die laufende Autonomy-Observation zeigt inzwischen stabil:

- Meta ist der Rettungsanker, wenn Dispatcher oder Spezialisten scheitern.
- Meta kann replannen und direkte Tool-Rescues ausführen.
- Meta ist aber noch zu unpräzise bei:
  - belegte Ursache vs. Hypothese
  - führende Diagnose vs. Nebenhypothese
  - developer-taugliche Anweisungen an andere Agenten
- Der Nutzer fungiert noch zu oft als Schiedsrichter zwischen `meta`, `system`, `reasoning`, `shell`.

Diese Phase zielt deshalb nicht auf neue Fähigkeiten, sondern auf sauberere Diagnose- und Delegationsdisziplin von Meta.

### Ziel

Meta soll Diagnosen anderer Agenten und eigene Beobachtungen strukturierter auswerten und daraus präzisere, belegbare Handlungsanweisungen ableiten.

Meta soll danach:

- Fakten und Vermutungen sauber trennen
- eine führende Diagnose auswählen
- unbelegte Behauptungen unterdrücken
- nur verifizierte Dateien und Ursachen in Developer-Tasks schreiben

### Scope

1. Diagnosis Record einführen

- neue strukturierte Diagnoseform, z. B. in [diagnosis_records.py](/home/fatih-ubuntu/dev/timus/orchestration/diagnosis_records.py)
- Felder:
  - `source_agent`
  - `claim`
  - `evidence_level`
  - `evidence_refs`
  - `confidence`
  - `actionability`
  - `verified_paths`
  - `verified_functions`

2. Lead Diagnosis Auswahl

- Meta soll konkurrierende Diagnosen ranken
- genau eine `lead_diagnosis` auswählen
- übrige Diagnosen als `supporting` oder `rejected` markieren
- keine Mischdiagnosen mehr aus teilweise widersprüchlichen Aussagen

3. Developer-Task Compiler härten

- Meta darf nur noch in Tasks schreiben:
  - verifizierte Dateien
  - verifizierte Funktionen
  - verifizierte Ursachen
  - konkrete gewünschte Änderung
- unbelegte Dateipfade oder falsche "BELEGT"-Behauptungen müssen unterdrückt werden

4. Belegsprache normalisieren

- `BELEGT` nur mit echten Evidenzreferenzen
- sonst:
  - `Plausible Hypothese`
  - `Noch zu verifizieren`
  - `Unbestätigt`

5. Beobachtung erweitern

- neue Meta-Metriken in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py):
  - `lead_diagnosis_selected`
  - `diagnosis_conflict_detected`
  - `developer_task_compiled`
  - `unverified_claim_suppressed`

### Geplante Dateien

- neue Datei [diagnosis_records.py](/home/fatih-ubuntu/dev/timus/orchestration/diagnosis_records.py)
- Erweiterung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- Erweiterung in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- Erweiterung in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)

### Guardrails

- keine freie Konsensmaschine für alle Agenten in M1
- keine neue große semantische Intent-Schicht in M1
- keine automatische Umsetzung von Diagnose in Code-Patch in M1
- Fokus nur auf:
  - Diagnosequalität
  - Evidenzdisziplin
  - präziseren Delegationsaufträgen

### Implementierungsreihenfolge

1. Diagnosis Record Datentyp
2. Lead-Diagnosis-Ranking
3. Developer-Task-Compiler mit Verifikations-Gate
4. Observation-Metriken
5. Tests, Contracts, Lean

### Erfolgskriterium

- Meta soll keine falschen "BELEGT"-Aussagen mehr an Developer-Tasks durchreichen
- Meta soll bei konkurrierenden Diagnosen eine saubere führende Diagnose benennen
- Meta soll weniger Nutzerkorrekturen benötigen, um einen präzisen Task zu formulieren
- Die interne Delegation soll nachvollziehbarer und präziser werden

### M1-Implementierungsstand

**Umgesetzt**

- neue Diagnose-Schicht in [diagnosis_records.py](/home/fatih-ubuntu/dev/timus/orchestration/diagnosis_records.py)
  - `DiagnosisRecord`
  - `DiagnosisResolution`
  - `DeveloperTaskBrief`
  - Normalisierung von Evidenzstufen
  - Lead-Diagnosis-Auswahl
  - Developer-Task-Brief mit Suppression unverifizierter Claims
- neue Wrapper in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `build_meta_diagnosis_resolution(...)`
  - `compile_meta_developer_task_payload(...)`
- Integration in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - Developer-Handoff wird jetzt mit Lead-Diagnose, verifizierten Pfaden/Funktionen und Suppression-Countern angereichert
  - komplexe Handoff-Werte werden stabil als JSON gerendert
  - neue Observation-Events fuer:
    - `lead_diagnosis_selected`
    - `diagnosis_conflict_detected`
    - `developer_task_compiled`
    - `unverified_claim_suppressed`
- Erweiterung in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neue Meta-Metriken fuer Diagnosequalitaet und Task-Kompilierung

**Validierung**

- `53 passed` in der fokussierten Pytest-Suite
- CrossHair gruen ueber [test_diagnosis_records_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_diagnosis_records_crosshair.py)
- Hypothesis enthalten in [test_diagnosis_records_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_diagnosis_records_contracts.py)
- Lean gruen

**Status**

- M1-Grundlage ist implementiert
- noch nicht live auf `timus-mcp` neu geladen
- naechster sinnvoller Schritt: echte Meta-zu-Developer-Handoffs produktiv beobachten

### Geplanter Folgeausbau: Meta Phase M2 — Root-Cause-First Task Emission

### Beobachtungsbasis

Die M1-Beobachtung zeigt inzwischen klar:

- Meta kann brauchbare Diagnosen liefern oder von `system`/`shell` uebernehmen
- Meta verliert bei der Taskableitung aber noch zu oft die Spur zum primaeren Root Cause
- Root Cause, Folgeeffekte, Monitoring-Ideen und Spaetmassnahmen werden noch vermischt
- dadurch entstehen Developer-Tasks, die plausibel klingen, aber nicht den eigentlichen Incident zuerst adressieren

### Ziel

Meta soll bei technischen Incidents zuerst genau **einen primaeren Fix-Task** emitten, der auf dem am besten belegten Root Cause basiert.

Folgeaufgaben wie:

- Monitoring
- Guardrails
- Alerting
- Cleanup
- Telemetrie

duerfen erst danach und getrennt als Folge-Tasks erscheinen.

### Scope

1. Root-Cause-First Resolution

- Meta soll aus mehreren Diagnosen eine `primary_fix_target` ableiten
- dieser muss enthalten:
  - primaere Ursache
  - primaere Datei(en)
  - primaere Funktion(en)
  - primaeren Aenderungstyp

2. Incident Task Split

- Tasks werden in Klassen getrennt:
  - `primary_fix`
  - `followup_monitoring`
  - `followup_hardening`
  - `followup_cleanup`
- fuer die erste Ausgabe an Developer/Shell ist nur `primary_fix` erlaubt

3. Root-Cause Gate vor Task-Emission

- kein Developer-Task, wenn diese Punkte fehlen:
  - belegte primaere Ursache
  - mindestens ein verifizierter Zielpfad
  - klarer Aenderungstyp
- wenn das Gate nicht erfuellt ist:
  - erst Verifikation
  - kein halb-präziser Task

4. Folgeaufgaben explizit abspalten

- wenn Monitoring oder Telemetrie sinnvoll sind, muessen sie als getrennte `followup_tasks` erscheinen
- sie duerfen nicht den primaeren Fix-Task verunreinigen

5. Observation erweitern

- neue Meta-Metriken:
  - `primary_fix_task_emitted`
  - `followup_task_deferred`
  - `root_cause_gate_blocked`
  - `task_mix_suppressed`

### Geplante Dateien

- neue Datei [root_cause_tasks.py](/home/fatih-ubuntu/dev/timus/orchestration/root_cause_tasks.py)
  - Datentypen fuer Primary/Followup-Tasks
- Erweiterung in [diagnosis_records.py](/home/fatih-ubuntu/dev/timus/orchestration/diagnosis_records.py)
  - Root-Cause-Selektion und Task-Split-Helfer
- Erweiterung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `compile_root_cause_task_payload(...)`
- Erweiterung in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - Developer-Handoff nur fuer `primary_fix`
  - Folgeaufgaben separat markieren
- Erweiterung in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neue M2-Metriken

### Guardrails

- genau ein primaerer Fix-Task pro Incident-Ausgabe
- Monitoring nie als primaerer Fix, wenn ein belegter Root Cause existiert
- kein Mischen von `primary_fix` und `followup_monitoring` in einem Task
- wenn Root Cause unklar bleibt:
  - `verification_needed`
  - kein ueberdehnter Fix-Task

### Implementierungsreihenfolge

1. Root-Cause-Task-Datentypen
2. Root-Cause-Gate
3. Primary-vs-Followup-Split
4. Meta-Handoff-Anpassung
5. Observation, Tests, Contracts, Lean

### Erfolgskriterium

- Meta emittiert bei technischen Incidents zuerst einen klaren `primary_fix`
- Monitoring/Alerting tauchen nur noch als getrennte Folgeaufgaben auf
- Nutzer muessen Meta seltener korrigieren, welcher Task der eigentliche erste Schritt ist
- die erste Taskausgabe wird fuer Laien nachvollziehbarer und fuer Developer umsetzbarer

### M2-Implementierungsstand

**Umgesetzt**

- neue Root-Cause-Schicht in [root_cause_tasks.py](/home/fatih-ubuntu/dev/timus/orchestration/root_cause_tasks.py)
  - `classify_change_focus(...)`
  - `RootCauseTask`
  - `RootCauseTaskPayload`
  - `build_root_cause_task_payload(...)`
- Erweiterung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `compile_meta_developer_task_payload(...)` liefert jetzt zusaetzlich `root_cause_tasks`
- Erweiterung in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - Developer-Handoffs emitten jetzt entweder:
    - einen klaren `primary_fix`
    - oder einen geblockten `verification_needed`-Pfad
  - Follow-up-Aufgaben werden getrennt als `followup_tasks_json` bzw. `deferred_followup_tasks_json` ausgegeben
  - der eigentliche Developer-Task-Text wird auf den primaeren Fix oder die Verifikationsanweisung umgeschrieben
- Erweiterung in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neue M2-Metriken:
    - `primary_fix_task_emitted`
    - `followup_task_deferred`
    - `root_cause_gate_blocked`
    - `task_mix_suppressed`

**Validierung**

- `16 passed` in der fokussierten M2-Test-Suite
- CrossHair gruen ueber [test_root_cause_tasks_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_root_cause_tasks_crosshair.py)
- Hypothesis enthalten in [test_root_cause_tasks_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_root_cause_tasks_contracts.py)
- Lean gruen

**Status**

- M2 ist implementiert, aber noch nicht live auf `timus-mcp` neu geladen
- naechster sinnvoller Schritt: Neustart und gezielte Beobachtung echter Meta-Developer-Tasks auf `primary_fix` vs. `followup`

## M2.1 - system_diagnosis an Root-Cause-first anbinden

### Problem

- `M2` war technisch vorhanden, wurde aber im wichtigen Rezept `system_diagnosis` nicht genutzt
- Meta konnte Diagnosen liefern, emittierte bei Prompts wie
  - `erstelle daraus genau einen Primary-Fix-Task`
  - `wenn nicht belegt, gib verification needed aus`
  noch keinen echten `primary_fix`
- die Beobachtung zeigte deshalb trotz `M2` weiter:
  - `Lead-Diagnosen gewaehlt: 0`
  - `Developer-Tasks kompiliert: 0`
  - `Primary-Fix-Tasks emittiert: 0`

### Umsetzung

- Erweiterung in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - Erkennung, ob eine `system_diagnosis`-Anfrage explizit einen Root-Cause-Task verlangt
  - Extraktion von Diagnose-Claims direkt aus dem erfolgreichen `system`-Stage-Ergebnis
  - Normalisierung von Datei- und Evidenzreferenzen aus freien Diagnose-Texten
  - Wiederverwendung des bestehenden `M1/M2`-Compilers auch fuer `system_diagnosis`
  - direkte Ausgabe von:
    - `Primary-Fix-Task`
    - oder `verification needed`
- kein zweiter Task-Compiler gebaut; `M2.1` ist bewusst nur die fehlende Verkabelung des vorhandenen Root-Cause-first-Pfads

### Validierung

- neue End-to-End-Abdeckung in [test_meta_recipe_execution.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_recipe_execution.py)
  - `system_diagnosis` emittiert jetzt bei belegter Vision-Root-Cause einen `Primary-Fix-Task`
  - `system_diagnosis` emittiert bei zu schwacher Ursache `verification needed`
- fokussierte Suite:
  - `40 passed`
- CrossHair gruen ueber [test_root_cause_tasks_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_root_cause_tasks_crosshair.py)
- Lean gruen

### Status

- `M2.1` ist implementiert
- Neustart von `timus-mcp` fuer den neuen Stand steht noch aus
- naechster sinnvoller Schritt: Live-Test mit einem echten `system_diagnosis`-Prompt auf `Primary-Fix-Task` / `verification needed`

## Beobachtungspunkt - Vision/OCR Speicherdruck und OOM

### Live-Befund

- Am **29.03.2026 um 22:53:42 CEST** wurde `timus-mcp` vom OOM-Killer beendet
- der sichtbare Nutzerfehler war nur `Failed to fetch`
- `systemd` hat den Dienst danach automatisch neu gestartet

### Wahrscheinliche Ursache

- der problematische Hot-Path ist aktuell kein reiner GPU-Pfad
- [tool.py](/home/fatih-ubuntu/dev/timus/tools/florence2_tool/tool.py)
  - Florence-2 laeuft dort auf `cuda`, wenn verfuegbar
  - der zugehoerige PaddleOCR-Pfad wird dort aber hart auf `CPU` initialisiert
    - `use_gpu: False`
    - `device: "cpu"`
- die Logs zeigen genau diesen Mischbetrieb:
  - `Florence-2 Device: cuda`
  - direkt danach `PaddleOCR geladen (CPU)`
- dadurch entsteht ueber Zeit hoher kombinierter VRAM-/RAM-Druck statt eines sauberen, einheitlichen Device-Pfads

### Einordnung

- das Problem ist nicht nur `GPU wird spaeter nicht mehr erkannt`
- der aktuelle Florence/OCR-Pfad ist bereits heute architektonisch uneinheitlich
- zusaetzlich existieren weitere OCR-Zweige im System, was den Druck und die Debug-Komplexitaet erhoeht

### Nach der Beobachtungswoche angehen

1. Vision/OCR-Pfad vereinheitlichen
- kein CPU/GPU-Mischbetrieb im selben Hot-Path

2. Florence-2- und OCR-Lifecycle haerten
- aggressiveres Freigeben/Recyceln von Modellen und Caches
- keine unnötigen Mehrfachinitialisierungen unter Last

3. OCR-Backends konsolidieren
- klarer Primärpfad
- saubere Fallback-Regeln
- keine parallelen schweren OCR-Wege ohne Not

4. Observability erweitern
- Device-Wechsel
- CPU/GPU-Fallback
- Modellinitialisierungen
- Peak-Memory vor Vision-/OCR-Aufrufen

## Nach Beobachtungswoche - Dispatcher Semantic Upgrade + Meta/Dispatcher Buddy Loop

### Aktueller Befund

- der Dispatcher faellt zu oft mit `empty_decision` auf Meta zurueck
- besonders schlecht sind aktuell:
  - Umgangssprache
  - kurze Anschlussfragen
  - implizite Referenzen
  - Meta-Kommunikation wie
    - `du verstehst mich nicht`
    - `uebernehme Empfehlung 2`
    - `bist du ein funktionierendes ki system`
- Meta ist in vielen dieser Faelle semantisch staerker als der Dispatcher und muss den Lauf retten

### Prioritaet

- **Top-Prioritaet 1 nach der Beobachtungswoche**
  - `Dispatcher Semantic Upgrade for colloquial / follow-up / intent-aware routing`

### Zielbild

- Dispatcher und Meta sollen nicht nur strikt nacheinander arbeiten
- sie sollen als **Buddy-/Agenten-Team** zusammenwirken:
  - Dispatcher = schnelle Frontdoor-Semantik und Erstsortierung
  - Meta = tiefere Bedeutungspruefung, Replanning und Konfliktaufloesung
- bei Unsicherheit soll der Dispatcher nicht nur `empty_decision` liefern, sondern:
  - eine semantische Vorhypothese
  - erkannte Unsicherheit
  - moegliche Lesarten / Kandidaten
  an Meta uebergeben

### Gewuenschte Eigenschaften

1. Umgangssprache besser verstehen
- locker formulierte Anfragen
- unvollstaendige Sätze
- kurze Frustrations- oder Korrektur-Saetze

2. Follow-up-Verstaendnis
- Bezug auf vorherige Antwort
- Bezug auf `Empfehlung 2`, `das`, `so`, `nochmal`, `dieselbe Sache`

3. Intent-aware Routing
- nicht nur Keywords
- sondern Bedeutung, Ziel und Gespraechszustand

4. Buddy-Kommunikation zwischen Dispatcher und Meta
- Dispatcher liefert bei Unsicherheit strukturierte Voranalyse statt Leerausfall
- Meta kann diese Voranalyse uebernehmen, bestaetigen, korrigieren oder erweitern

5. Beobachtbare Qualitaet
- weniger `dispatcher_meta_fallback: empty_decision`
- weniger Nutzerhinweise wie `du verstehst mich nicht`
- weniger Meta-Rettung fuer triviale Frontdoor-Faelle

### Nach der Beobachtungswoche konkret angehen

1. Dispatcher-Prompt und Output-Schema fuer Umgangssprache/Follow-ups erweitern
2. Unsicherheitsausgabe statt Leerausfall
3. strukturierte Buddy-Handoff-Daten an Meta
4. gemeinsame Beobachtungsmetriken fuer Dispatcher + Meta
5. spaeter optional: kleiner semantischer Vorinterpretations-Worker nur fuer Frontdoor-Faelle

### Konkretes Zielbild des Buddy Loops

- Dispatcher und Meta arbeiten als gleichrangige Buddys
- Dispatcher bleibt der schnelle Erstleser
- Meta bleibt der tiefere Bedeutungspruefer
- Entscheidungen entstehen ueber ein Buddy-Protokoll, nicht ueber Rang

#### BuddyHypothesis

Jeder Buddy soll eine strukturierte Hypothese liefern mit:

- `intent`
- `goal`
- `confidence`
- `uncertainty`
- `candidate_routes`
- `risk_level`
- `needs_clarification`
- `reasoning_summary`

Optional:

- `followup_reference`
- `location_relevance`
- `freshness_requirement`
- `artifact_need`
- `delivery_need`
- `state_invalidation_signal`

#### Arbitration-Zustaende

- `aligned`
  - beide sehen dieselbe Richtung
- `soft_conflict`
  - aehnliche Bedeutung, aber unterschiedliche Konservativitaet
- `hard_conflict`
  - unterschiedliche Bedeutungslesarten
- `insufficient_signal`
  - beide unsicher

#### Entscheidungslogik

- `aligned` -> Fast-Path
- `soft_conflict` -> konservativere Route
- `hard_conflict` -> Rueckfrage oder Meta-konservativer Pfad
- `insufficient_signal` -> Rueckfrage statt Blindrouting

#### Guardrails

- max. 2 Buddy-Runden
- Fast-Path nur bei hoher Konfidenz + niedrigem Risiko
- bei Unsicherheit kein `empty_decision`, sondern strukturierte Vorhypothese
- bei Risiko nie blind am Dispatcher vorbeilaufen

#### Erfolgskriterium

- weniger `dispatcher_meta_fallback: empty_decision`
- weniger Meta-Rettung fuer triviale Frontdoor-Faelle
- bessere Umgangssprache
- bessere Follow-up-Verarbeitung
- weniger Nutzerkorrekturen wie `du verstehst mich nicht`

## Startplan ab 2026-04-01 - erste Ausbauwelle in 3 Phasen

### Phase A - Dispatcher Semantic Upgrade

Ziel:
- Umgangssprache, kurze Anschlussfragen und implizite Referenzen an der Frontdoor deutlich besser verstehen

Umfang:
- Dispatcher-Prompt und Output-Schema fuer colloquial/follow-up/meta-dialogische Anfragen erweitern
- `empty_decision` durch strukturiertere Unsicherheitsausgabe ersetzen
- bessere Follow-up-Aufloesung fuer kurze Anschlussfragen wie:
  - `kannst du sie reparieren`
  - `uebernehme Empfehlung 2`
  - `was machst du da das ist doch falsch`

Erfolg:
- deutlich weniger `dispatcher_meta_fallback: empty_decision`

### Phase B - Meta Root-Cause und Semantik nachschaerfen

Ziel:
- Meta soll Diagnosen sauberer priorisieren und in echte primaere Fix-Aufgaben uebersetzen

Umfang:
- `M2`/`M2.1` weiter schaerfen
- Ursachenzeilen aus `Ursache:` und `suspected_root_cause` haerter priorisieren
- Pfadtragende Claims vor allgemeinen Diagnosezeilen bevorzugen
- erstes echtes `primary_fix_task_emitted` erreichen
- semantische Fehlklassifikationen wie Business-/Strategiefragen vs. lokale Suche spaeter ueber eine fruehe Meaning-Layer reduzieren

Erfolg:
- weniger `verification needed` aus rein extraktiven Gruenden
- mindestens erste stabile primaere Fix-Tasks ohne Nutzer-Nachschleife

#### Bestaetigte Semantik-Fehlfaelle fuer Phase B

- `ich moechte ein cafe eroeffnen welches land ist am besten geeignet`
  - soll als Strategie-/Businessfrage verstanden werden
  - wurde in der Session mehrfach zu stark Richtung lokaler Suche gezogen
- `soll ich kaffee oder tee trinken was meinst du und was und wie koenntest du mich reich machen`
  - lief am **01.04.2026 20:48 CEST** direkt auf `meta`
  - wurde dort als `simple_live_lookup` / `general_lookup|live|light|answer|none|loc=0|deliver=0` behandelt
  - Ergebnis war eine stale Standortantwort statt einer kombinierten Praeferenz-/Lebensstrategie-Antwort
  - Beleg:
    - [2026-04-01_task_bc313161.jsonl](/home/fatih-ubuntu/dev/timus/logs/2026-04-01_task_bc313161.jsonl)
    - [autonomy_observation.jsonl](/home/fatih-ubuntu/dev/timus/logs/autonomy_observation.jsonl)
- `ich habe meinen handy standort aktualisiert du musst das registrieren`
  - ist kein normaler Maps-Follow-up, sondern ein `user_reported_state_update`
  - Meta braucht dafuer spaeter explizite State-Invalidation/Revalidation

### Phase C - Runtime-Haertung fuer MCP und Vision/OCR

Ziel:
- sichtbare Laufzeitprobleme reduzieren, die Timus fuer Nutzer wie Telegram, Canvas oder Live-Recherche unzuverlaessig wirken lassen

Umfang:
- `mcp_health`-Timeout-/Self-Healing-Pfad pruefen und haengen gebliebene Playbooks abbauen
- Vision/OCR-Hot-Path haerten
- Florence-2-/PaddleOCR-Mischpfad und Speicher-/Device-Lifecycle spaeter konsolidieren
- Antwortpfade beobachten, wenn Timus in Telegram denkt, aber nicht zurueckantwortet

Erfolg:
- weniger Health-Timeouts
- weniger haengende Recovery-/Self-Healing-Aufgaben
- stabilerer Antwortpfad bei laengeren oder schwereren Laeufen

## Noch fehlende Faelle / Daten fuer die zweite Welle

### 1. Buddy-Konfliktfaelle

Wir brauchen mehr reale Faelle, in denen Dispatcher und Meta dieselbe Anfrage unterschiedlich lesen wuerden:
- Umgangssprache
- Follow-ups
- implizite Referenzen
- Nutzerkorrekturen
- Meta-Kommunikation

Nutzen:
- Buddy-Loop spaeter auf echte Konfliktmuster statt nur Theorie zuschneiden

### 2. Mehr technische Incident-Faelle fuer Meta M2

Wir haben bisher erst sehr wenige echte Faelle, in denen:
- `lead_diagnosis_selected`
- `developer_task_compiled`
- `root_cause_gate_blocked`
oder spaeter
- `primary_fix_task_emitted`

sichtbar wurden.

Nutzen:
- Root-Cause-First-Tasking stabilisieren

### 3. Reale Self-Hardening-Pfade

Es fehlen noch echte Self-Hardening-/Self-Modify-Faelle fuer:
- `dispatcher empty_decision`
- `mcp_health`-Timeouts
- Vision/OCR-/Browser-Folgen
- stale state / Nutzerkorrekturen

Nutzen:
- Self-Hardening auf reale Live-Probleme statt auf zu enge Alt-Patterns anschliessen

### 4. Bessere Korrelation fuer Telegram-/Antwortausfaelle

Wir sehen bereits:
- `mcp_health`-Timeouts
- ausbleibende Antworten
- Self-Healing-Playbooks in der Queue

Es fehlen aber noch mehr klare Korrelationen zwischen:
- eingehender Anfrage
- laufenden Agenten/Tools
- Queue-/Health-Zustand
- ausbleibender Telegram-Antwort

Nutzen:
- Antwortpfad und Runtime-Blockaden spaeter gezielt haerten

### 5. Vision/OCR-Lastbild unter echter Nutzung

Es fehlen noch mehr belastbare Live-Faelle fuer:
- parallele Browser-/Vision-/OCR-Laeufe
- RAM-/VRAM-Spitzen
- CPU-/GPU-Fallbacks
- OOM-Vorlaeufer

Nutzen:
- Vision/OCR-Haertung spaeter nicht nur reaktiv, sondern systematisch angehen

## Fortschritt 2026-04-01 - Phase A gestartet

Phase A (Dispatcher Semantic Upgrade) ist im ersten konservativen Block umgesetzt.

- `main_dispatcher.py` priorisiert bei Follow-up-Kapseln jetzt semantisch `# CURRENT USER QUERY`
- kurze referenzielle Anschlussfragen wie `dann uebernimm die Empfehlung 2`, `koenntest du damit arbeiten`, `kannst du sie reparieren` werden konservativ frueh als `meta` erkannt statt spaeter in `empty_decision` zu kippen
- umgangssprachliche Selbststatus-/Selbstbild-Fragen wie `ok was stoert dich wie kann ich dir helfen`, `bist du anpassungsfaehig`, `bist du ein funktionierendes ki system` werden frueh als `executor` erkannt
- Nutzerkorrektur-/Beschwerdephaenomene wie `anscheinend verstehst du mich nicht` oder `was machst du da das ist doch falsch` werden frueh als `meta` behandelt
- ein enger Guard verhindert, dass harmlose Kurzfragen wie `soll ich kaffee oder tee trinken` durch die neue Frontdoor vorschnell auf `meta` gehoben werden

Absicherung:
- Dispatcher-Tests fuer die beobachteten Umgangssprache-Faelle erweitert
- neue Contract-/Hypothesis-Datei fuer Dispatcher-Semantik
- Lean `CiSpecs.lean` um zwei kleine Dispatcher-Invarianten erweitert

### Phase A.1 - triviale Umgangssprache entkernen

Die Beobachtung zeigt weiter ein Frontdoor-Problem bei sehr leichten Alltagsfragen wie:
- `was denkst du wird es morgen regnen`
- `kannst du mir sagen wie spaet es ist`
- `weisst du wann heute sonnenuntergang ist`

Darauf ist ein generischer Preparse-Block im Dispatcher angesetzt:
- umgangssprachliche Fragehuellen wie `was denkst du`, `meinst du`, `glaubst du`, `kannst du mir sagen`, `weisst du` werden vor dem Routing reduziert
- der Dispatcher arbeitet danach mit einer `NORMALIZED CORE QUERY`
- kurze triviale Kernfragen mit klarer Frageform und ohne komplexe Marker koennen konservativ direkt an `executor` gehen
- nicht-triviale Strategie-, Browser-, Research- oder Multi-Intent-Faelle bleiben weiter ausserhalb dieses Schnellpfads

## Fortschritt 2026-04-01 - Phase B Vorbereitung gestartet

Phase B laeuft jetzt als konservative Advisory-Vorbereitung an, noch ohne harte Rezept-Umbauten.

- `classify_meta_task(...)` markiert ab jetzt beobachtete semantische Konfliktmuster nur advisory:
  - `mixed_personal_preference_and_wealth_strategy`
  - `business_strategy_vs_local_lookup`
  - `user_reported_location_state_update`
- diese Marker aendern das Routing heute noch nicht hart, geben uns aber ab sofort sauberere Signale fuer:
  - spaetere Meaning-Layer vor der Rezeptwahl
  - State-Correction-Handling
  - besseres Mischen/Trennen von Lebenshilfe-, Strategie- und Lookup-Fragen
- neue Meta-Orchestration-Tests decken die bestaetigten Live-Faelle jetzt explizit ab

## Fortschritt 2026-04-01 - Phase B erster echter Schnitt

Der erste konservative Phase-B-Schnitt ist jetzt im Meta-Classifier drin.

- bestaetigte Semantik-Konfliktfaelle werden nicht mehr in bekannte Live-Lookup-Rezepte gezwungen
- stattdessen faellt Meta fuer diese Faelle bewusst auf einen rezeptlosen `single_lane` / `meta`-Dialogpfad zurueck
- konkret gilt das jetzt fuer:
  - `mixed_personal_preference_and_wealth_strategy`
  - `business_strategy_vs_local_lookup`
  - `user_reported_location_state_update`
- damit werden genau die beobachteten Fehlmuster konservativ unterbrochen:
  - `ich moechte ein cafe eroeffnen welches land ist am besten geeignet`
  - `soll ich kaffee oder tee trinken ... wie koenntest du mich reich machen`
  - `ich habe meinen handy standort aktualisiert du musst das registrieren`

Wichtig:
- das ist noch keine vollwertige Meaning-Layer
- aber es stoppt erste klar belegte Fehlpfade, bevor Meta sie wieder in `simple_live_lookup` oder lokale Rezeptpfade zwingt

## Spaetere Phase D - Assistive Action Workflows mit Approval Gate

Wichtiger Vorlauf:

- vor D1-D5 sollte ein eigener Fundament-Block `D0 Meta Context State` laufen
- Begruendung:
  - Timus muss laufende Themen, offene Ziele, Nutzerkorrekturen und Praeferenzen stabil tragen koennen
  - sonst bleiben Approval-, Auth- und Handover-Workflows semantisch fragil
- Plan dokumentiert in:
  - [PHASE_D0_META_CONTEXT_STATE_PLAN.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D0_META_CONTEXT_STATE_PLAN.md)

Nach D0.8 braucht Timus einen Rollout-Block fuer die Spezialisten:

- **D0.9 Specialist Context Propagation**
- Begruendung:
  - `meta` darf nicht der einzige Agent bleiben, der laufenden Gespraechssinn traegt
  - aber erst nach Rehydration, Topic-State, Praeferenzspeicher, Antwortmodus und State-Decay ist die Meta-Basis stabil genug, um sie sauber in `executor`, `research`, `visual` und `system` auszurollen
- Ziel:
  - Spezialisten bekommen aus `conversation_state` mindestens:
    - `current_topic`
    - `active_goal`
    - `open_loop`
    - `turn_type`
    - `response_mode`
    - `user_preferences`
    - `recent_corrections`
  - Spezialisten melden darauf abgestimmt:
    - `partial_result`
    - `blocker`
    - `context_mismatch`
    - `needs_meta_reframe`
- Erfolgskriterium:
  - `meta` bleibt der beste Koordinator
  - aber die restlichen Agenten verlieren den laufenden Bezug nicht mehr sofort, sobald der Handoff weniger explizit ist
  - dadurch wird Timus weniger fragil in echten laengeren Unterhaltungen

Der Fall `reserviere mir ein hotel in portugal lissabon` zeigt eine eigene, spaetere Ausbauphase:

- Ziel ist nicht nur Suche oder Vergleich
- Ziel ist assistierte Handlung bis kurz vor den finalen Commit
- Timus soll aktiv mitdenken, vorbereiten und den Nutzer erst bei sensiblen/bindenden Schritten einbinden

### Zielbild

- Meta versteht `buche`, `reserviere`, `bestelle`, `beantrage`, `melde an` als assistierte Aktions-Workflows
- Visual-/Operator-Agent arbeitet aktiv bis kurz vor:
  - Zahlung
  - finalem Submit
  - rechtlich/finanziell bindendem Schritt
- Timus uebergibt dann sauber:
  - `Ich habe alles vorbereitet`
  - `Bitte hier Daten eingeben / Zahlung bestaetigen`

### Bausteine

1. Action Intent Understanding
- nicht nur `finden`
- sondern `vorbereiten und fast abschliessen`

2. Operator Readiness
- robustere UI-/Screen-Erkennung
- praezisere Navigation
- bessere Formularrobustheit

3. Approval Gate
- harter Stop vor Zahlung / finalem Commit

4. Preference Memory
- Budgets, Praeferenzen, wiederkehrende Nutzerwuensche merken

5. Session Persistence
- abgebrochene Flows spaeter wieder aufnehmen koennen

6. Authenticated Access Workflows
- wenn eine Plattform fuer brauchbare Inhalte Login verlangt, soll Timus das nicht still umgehen oder rohe Credentials im Chat erwarten
- stattdessen:
  - klare Rueckfrage an den Nutzer, ob ein Login mit seinem Zugang erfolgen darf
  - sensibler Schritt nur mit expliziter Freigabe
  - Nutzer gibt Passwort / 2FA idealerweise selbst im Browser ein oder bestaetigt den naechsten Schritt
  - danach darf Timus die authentische Session fuer den laufenden Workflow weiterverwenden
- typische Zielbilder:
  - X / LinkedIn / Reddit / andere Plattformen mit Login-Wand
  - gespeicherte Session spaeter wieder aufnehmen
  - sauberer Handover bei CAPTCHA / 2FA / Challenge

### Zuschnitt innerhalb von Phase D

- **D1 Auth Need Detection**
  - erkennt, wann eine Quelle ohne Login nur duenne Snippets oder Login-Waende liefert
- **D2 Approval + Consent Gate**
  - Timus fragt aktiv nach Freigabe fuer echten Account-Zugriff
- **D3 User-mediated Login**
  - Nutzer fuehrt sensible Eingaben selbst aus oder bestaetigt sie bewusst
- **D4 Auth Session Reuse**
  - authentische Browser-Sitzung fuer den Workflow und spaetere Wiederaufnahme sichern
- **D5 Challenge Handover**
  - 2FA / CAPTCHA / Security-Checks sauber an den Nutzer uebergeben statt blind weiterzulaufen

### Erfolgskriterium

- Timus schickt nicht nur einen Link
- sondern arbeitet aktiv bis zum letzten sicheren Schritt
- und zeigt damit echtes assistives Mitdenken statt nur Such-/Antwortlogik
- inklusive echter, nutzerfreigegebener Account-Nutzung wenn ein Dienst ohne Login nicht sinnvoll benutzbar ist

## Spaetere Phase E - Self-Improvement aus erkannter Schwaeche

Die Beobachtung zeigt klar:
- Timus kennt viele seiner Schwaechen bereits
- aber er kann sie noch nicht sauber selbst in konkrete Verbesserungsmassnahmen uebersetzen

### Zielbild

- Timus erkennt wiederkehrende Schwachstellen aus Live-Betrieb und Beobachtung
- Timus klassifiziert sie als:
  - Prompt-/Routingproblem
  - Kontext-/Meaning-Problem
  - Runtime-/Infra-Problem
  - Tool-/Spezialistenproblem
- Timus erzeugt daraus selbst:
  - `developer_task`
  - `shell_task`
  - oder konservativ `verification_needed`

### Bausteine

1. Weakness-to-Task Compiler
- aus beobachteter Schwaeche wird eine belastbare Massnahme
- nicht nur Selbstbeschreibung, sondern konkrete Umsetzungsempfehlung

2. Observation -> Diagnosis -> Action
- Beobachtungsereignisse muessen spaeter direkt in Hardening-/Verbesserungspfade einspeisen

3. Safe Self-Hardening
- nur konservative, klar begrenzte Aenderungen ohne hohes Risiko
- z. B.:
  - Guards
  - Schwellenwerte
  - kleine Parser-/Routingverbesserungen
  - Prompt-Haertung
  - Tests/Regressionen

4. Approval Gate fuer groessere Eingriffe
- Modellwechsel
- groessere Refactors
- kritische Runtime-/Infra-Aenderungen
- alles davon nur mit expliziter Freigabe oder starkem Policy-Gate

5. Memory Curation Autonomy
- Timus soll sein Langzeitgedaechtnis spaeter nicht nur fuellen, sondern kontrolliert pflegen
- Ziel ist keine blinde Loesch-Automation, sondern eine policy-gesteuerte Gedaechtnisorganisation
- der Block gehoert **in Phase E**, nicht in Phase D
  - weil es um interne Selbstorganisation und qualitative Selbstverbesserung geht
  - nicht um Nutzerfreigaben, Auth oder assistive Aussenaktionen
- Zielbild:
  - fluechtige Erinnerungen, Topic-Historie und stabile Langzeitfakten unterschiedlich behandeln
  - alte, schwache oder redundante Erinnerungen zusammenfassen, archivieren oder konservativ entwerten
  - Retrieval-Qualitaet dabei messbar verbessern statt nur Speicher zu reduzieren
- noetige Bausteine:
  - `Memory Curation Policy`
  - `Memory Curation Engine`
  - Verifikation nach jeder Pflege
  - Rollback/Snapshots
  - Observability fuer `memory_curation_started`, `memory_summarized`, `memory_archived`, `memory_pruned`, `memory_curation_rollback`
  - konservative Autonomiegrenzen und spaeter optional Approval fuer aggressivere Eingriffe
- Einordnung innerhalb von Phase E:
  - nicht ganz am Anfang von E
  - erst nachdem D0, Phase D und der Spezialisten-Rollout stabil genug sind
  - sinnvoll als spaeterer Self-Improvement-Block fuer kontrollierte Gedaechtnispflege

### Erfolgskriterium

- Timus beschreibt Schwaechen nicht nur
- sondern kann daraus spaeter selbst belastbare Verbesserungs-Tasks ableiten
- und in sicheren Faellen sogar konservativ anstossen

## Naechster Arbeitsblock - 2026-04-03 Abend

Aus dem Google-Calendar-Fall ergeben sich zwei direkte Folgearbeiten:

### 1. Action-Continuation Routing

Kurze Fortsetzungsantworten wie:

- `ja mach das`
- `ok fang an`
- `mach weiter`
- `ja bitte`

sollen nicht nur als lockere Bestaetigung behandelt werden, sondern als echte Fortsetzung eines offenen Arbeitsauftrags.

Ziel:

- offene Delegationen / Vorschlaege / naechste Schritte werden als fortsetzbarer Auftrag erkannt
- der naechste Agent wird wirklich beauftragt
- der Turn endet nicht in blosser verbaler Zusage ohne Ausfuehrung

### 2. Delegation Success Contract

Delegationen duerfen nur dann als `success` gelten, wenn ein verwertbares Ergebnis zurueckkommt.

Nicht ausreichend:

- nur verbale Bestaetigung
- nur ein Titel
- leerer Blackboard-Eintrag
- `max steps reached` ohne verwertbaren Inhalt

Erforderlich je nach Task:

- brauchbarer Final-Text
- oder Blackboard-Eintrag mit Inhalt
- oder Artefakt
- oder klarer Fehler-/Partial-Status statt falschem `success`

Ziel:

- andere Agenten akzeptieren saubere Instruktionen als echten Auftrag
- und das System erkennt unbrauchbare Pseudo-Erfolge nicht mehr als Erfolg an

## Fortschritt 2026-04-02 - Frontdoor/Reasoning Guard + Parse-Recovery Hardening

Die beobachteten Chat-Fehlfaelle vom 02.04.2026 haben drei konkrete Schutzmassnahmen ausgeloest:

- Frontdoor-Guard fuer persoenliche Strategie-/Lebensdialoge:
  - lange Ich-/Job-/Karriere-/Finanz-Kontexte gehen jetzt konservativ an `meta`
  - sie sollen nicht mehr allein wegen Woertern wie `architektur` oder `design` in `reasoning` kippen
- allgemeiner Evidenz-Guard fuer Architektur-/Review-Routen:
  - `reasoning` darf eine Architektur-/Review-Lesart nur noch bevorzugen, wenn technische Artefakte/Evidenz vorhanden sind
  - Beispiele fuer Evidenz: `code`, `datei`, `api`, `service`, `traceback`, `db`, `framework`
- zusaetzlicher Schutz im `ReasoningAgent` selbst:
  - falls ein persoenlicher Kontext trotzdem bei `reasoning` landet, wird `PROBLEM_TYP: Architektur-Review` ohne technische Evidenz unterdrueckt
- Parse-Recovery im `BaseAgent` gehaertet:
  - laengere, strukturierte Freitextantworten koennen bei `Kein JSON gefunden` jetzt als finale Antwort gerettet werden
  - dadurch soll ein guter erster Reply nicht mehr vom strikten JSON-Reparaturprompt zerstoert werden

Neue/erweiterte Tests:

- Dispatcher-Routing fuer:
  - persoenliche Strategie-/Jobwechsel-Kontexte
  - echte technische Architektur-Reviews
- Reasoning-Problemtyp-Guard
- Parse-Error-Salvage fuer gute Advisory-Antworten

Verifikation:

- fokussierte Pytest-Suite gruen (`46 passed`, `2 deselected`)
- Lean gruen
- CrossHair auf dem Dispatcher-Contract bleibt wegen der schweren `main_dispatcher`-Imports weiterhin instabil/langsam und liefert hier keinen verlaesslichen Abschluss

## Fortschritt 2026-04-02 - Phase B Follow-up-Kapsel-Fix

Ein weiterer echter Phase-B-Fehlfall aus dem Live-Chat ist jetzt abgesichert:

- beobachteter Fehler:
  - Follow-up wie `und wie kannst du mir dabei behilflich sein` wurde als `system_diagnosis` klassifiziert
  - alter Antworttext aus der Follow-up-Kapsel (`System stabil`, `YouTube-Videos`) wurde mitklassifiziert
- Ursache:
  - `extract_effective_meta_query(...)` konnte nur echte Mehrzeilen-Kapseln sauber auspacken
  - serialisierte / einzeilige Follow-up-Kapseln fielen auf den kompletten Rohtext zurueck
- Fix:
  - `extract_effective_meta_query(...)` versteht jetzt auch Ein-Zeilen-/serialisierte Kapseln
  - bei `# CURRENT USER QUERY` wird der Text nach dem Marker jetzt auch ohne Zeilenumbruch extrahiert
  - fuehrende Trenner und offensichtliche Serialisierungsreste werden abgeschnitten
- Wirkung:
  - alter Antworttext darf `site_kind`, `task_type` und Rezeptwahl nicht mehr aus der Bahn werfen
  - der aktuelle Nutzer-Follow-up wird isoliert klassifiziert

Tests:

- Ein-Zeilen-Follow-up fuer `extract_effective_meta_query(...)`
- Klassifikation mit altem `System stabil`-/`YouTube-Videos`-Text in derselben Kapsel

Verifikation:

- fokussierte Meta-Orchestration-Suite gruen (`31 passed`)
- CrossHair auf `tests/test_meta_semantic_review_contracts.py` gruen

## Fortschritt 2026-04-02 - Phase B Context Anchoring Layer (erster Schnitt)

Der Follow-up-Kapsel-Fix allein reicht nicht fuer laengere Themenverlaeufe. Deshalb gibt es jetzt einen ersten Context-Anchoring-Schnitt in der Meta-Klassifikation:

- neues Ziel:
  - kurze Anschlussfragen wie `und wie kannst du mir dabei behilflich sein`
  - sollen am aktiven Thema haengen bleiben
  - ohne alten Assistant-Text wieder in `system_diagnosis`, `youtube` oder andere Spezialpfade zu kippen

- Umsetzung:
  - `extract_meta_context_anchor(...)` zieht einen sauberen Themenanker aus der Follow-up-Kapsel
  - Prioritaet:
    1. `last_user`
    2. `recent_user_queries`
    3. `pending_followup_prompt`
    4. `topic_recall` (nur als Fallback)
  - `last_assistant` wird bewusst NICHT als Anker genutzt, um Trigger-Leaks aus alten Antworten zu vermeiden
  - `_should_apply_meta_context_anchor(...)` aktiviert den Anker nur bei kurzen, kontextabhaengigen Follow-ups
    - z. B. `dabei`, `damit`, `wie kannst du mir helfen`, `womit sollte ich anfangen`, `und was jetzt`

- Wirkung:
  - Meta klassifiziert die aktuelle Nutzerfrage weiterhin primär ueber `# CURRENT USER QUERY`
  - bei mehrdeutigen Kurz-Follow-ups wird zusaetzlich der letzte Nutzerkontext beruecksichtigt
  - daraus faellt der Fall konservativ auf `single_lane` / `meta` statt auf `executor` oder ein falsches Spezialrezept

Tests:

- Themenanker aus serialisierten Follow-up-Kapseln
- Karriere-/KI-Selbstaendigkeits-Follow-up bleibt auf `meta`
- alter Assistant-Text mit `System stabil` oder `YouTube-Videos` darf nicht mehr die Route bestimmen

Verifikation:

- fokussierte Meta-Orchestration-Suite gruen (`33 passed`)
- CrossHair auf `tests/test_meta_semantic_review_contracts.py` gruen

## Fortschritt 2026-04-02 - Phase B Active Topic State + komprimierte Follow-ups

Der erste Context-Anchoring-Schnitt reicht fuer laengere Themen noch nicht aus. Deshalb wurde die Meta-Klassifikation jetzt um einen kleinen userseitigen Dialogzustand erweitert:

- neues Ziel:
  - aktive Themen ueber mehrere Turns stabil halten
  - `open_goal` und einfache Nutzer-Constraints wiederverwenden
  - knappe Advisory-Follow-ups wie `KI-Consulting, KI-Tools 2 stunden budget 0` nicht mehr als inhaltsleeren Rest behandeln

- Umsetzung:
  - `extract_meta_dialog_state(...)` extrahiert jetzt:
    - `active_topic`
    - `open_goal`
    - `constraints`
    - `next_step`
    - `compressed_followup_parsed`
    - `active_topic_reused`
  - Themenquellen bleiben bewusst userseitig:
    - `context_anchor`
    - `last_user`
    - `recent_user_queries`
    - `pending_followup_prompt`
    - nur spaet als Fallback `topic_recall` / `session_summary`
  - alte Assistant-Texte werden weiterhin NICHT als Themenanker verwendet
  - kompakte Advisory-Eingaben mit Zeit-/Budget-Slots werden jetzt konservativ erkannt
    - z. B. `2 stunden`
    - `budget 0`
    - `kein finanzielles polster`
    - `ohne team`
  - wenn so ein komprimierter Advisory-Follow-up erkannt wird, faellt Meta konservativ auf `single_lane` / `meta` statt auf den generischen Executor-Default

- Wirkung:
  - Phase B haelt nicht nur den letzten Query-String sauber, sondern merkt sich jetzt auch einen kleinen aktiven Nutzerkontext
  - knappe Planungs-/Beratungs-Follow-ups koennen mit Themenanker + Constraints weiterlaufen
  - Brasilien-/Karriere-/KI-Selbstaendigkeits-Faelle bleiben stabiler auf dem eigentlichen Thema
  - Spezialpfade wie `system_diagnosis`, `location_local_search` oder `simple_live_lookup` werden jetzt wieder staerker an die AKTUELLE Nutzerfrage gebunden
  - ein alter Themenanker darf diese Spezialrouten nicht mehr allein ausloesen

Neue Tests:

- Dialog-State-Extraktion fuer Karriere-/KI-Selbstaendigkeits-Follow-up mit `2 stunden` + `budget 0`
- komprimierter Advisory-Follow-up `KI-Consulting, KI-Tools 2 stunden budget 0`
- Brasilien-/KI-Follow-up mit wiederverwendetem Aktivthema
- Orts-/Maps-Anker darf eine allgemeine Anschlussfrage nicht wieder in `location_local_search` ziehen
- neue Contract-Datei fuer `extract_meta_dialog_state(...)`

Verifikation:

- `python -m py_compile` gruen
- fokussierte Pytest-Suite gruen (`36 passed`)
- Lean gruen
- CrossHair auf `tests/test_meta_dialog_state_contracts.py` bleibt hier aktuell haengen und wird deshalb NICHT als falsches Gruen gewertet

## Nachtrag 2026-04-03 20:30 CEST - Natuerlichere Antwortfinalisierung fuer Listen

Die Listen-Finalisierung war noch zu aggressiv und hat auch bereits brauchbare Antworten in das starre Format `Hier ist deine Liste:` gepresst. Das fiel im Live-Reply fuer Blackboard- und Google-Calendar-Faelle unnoetig mechanisch auf.

- Umsetzung:
  - `BaseAgent._finalize_list_output(...)` prueft Listenwunsch jetzt gegen die extrahierte Primaeraufgabe statt gegen den voll angereicherten Task
  - dadurch loesen Wrapper-Texte mit `Liste` im Meta-/Skill-Kontext keine falsche Listenformatierung mehr aus
  - `_looks_like_preformatted_list_answer(...)` bewahrt bereits gut formatierte Markdown-/Bullet-/Absatz-Antworten vor der erzwungenen Umnummerierung
  - `_format_generate_text_output(...)` und die Plain-Line-Normalisierung erzeugen nur noch nummerierte Punkte, aber keine stockige Standard-Einleitung mehr

- Neue Regressionen:
  - `tests/test_list_output_naturalization.py`
  - abgedeckt sind:
    - keine Listen-Finalisierung durch Wrapper-Kontext
    - Markdown/Bullets bleiben natuerlich erhalten
    - rohe Zeilen werden weiter sauber nummeriert
    - JSON-Listen verlieren die Standard-Einleitung

- Verifikation:
  - `python -m py_compile agent/base_agent.py tests/test_list_output_naturalization.py` gruen
  - fokussierte Suite gruen (`15 passed`)
  - `timus-mcp` neu gestartet, `/health` wieder `healthy` um `20:29:38 CEST`
  - Live-Check `/chat` fuer `was gibts auf dem blackboard` liefert jetzt eine normale Markdown-Antwort mit `**Blackboard-Uebersicht ...**` statt `Hier ist deine Liste:`

## Nachtrag 2026-04-03 20:38 CEST - Dispatcher-Bypass fuer klare Meta-Queries

Im Beobachtungslog tauchten fuer klare interne Meta-Queries weiterhin `dispatcher_meta_fallback`-Eintraege mit `reason=empty_decision` auf. Ursache war nicht der Parser, sondern dass der Dispatcher-LLM bei Anfragen wie `was gibts auf dem blackboard` oder `kannst du meinen googlekalender einsehen` nur paraphrasiert hat statt einen Agenten zu nennen.

- Umsetzung:
  - `main_dispatcher.quick_intent_check(...)` erkennt jetzt zwei eindeutige Meta-Klassen vor dem Dispatcher-LLM:
    - Blackboard-/Working-Memory-Abfragen
    - Google-Calendar-/Calendar-API-Zugriffsfragen
  - dadurch werden diese Faelle direkt auf `meta` geroutet und umgehen den leeren LLM-Decision-Pfad

- Neue Regressionen:
  - `tests/test_dispatcher_self_status_routing.py`
    - Blackboard → `meta`
    - Google Calendar → `meta`
  - `tests/test_dispatcher_provider_selection.py`
    - `get_agent_decision(...)` ruft fuer Blackboard den Dispatcher-LLM nicht mehr auf

- Verifikation:
  - `python -m py_compile main_dispatcher.py tests/test_dispatcher_self_status_routing.py tests/test_dispatcher_provider_selection.py` gruen
  - fokussierte Dispatcher-Suite gruen (`38 passed`)
  - `timus-mcp` neu gestartet, `/health` wieder `healthy` um `20:37:36 CEST`
  - Live-Checks `/chat` fuer
    - `was gibts auf dem blackboard`
    - `hey timus kannst du meinen googlekalender einsehen`
    liefen beide erfolgreich ueber `meta`
  - nach den Live-Checks erschien kein neuer `dispatcher_meta_fallback`-Eintrag fuer diese beiden Queries im Beobachtungslog

## Nachtrag 2026-04-03 20:51 CEST - Beobachtungslog gegen Test-Pollution gehaertet

Im Live-Beobachtungslog erschien ein `dispatcher_exception`, der nicht aus einer echten Laufzeit, sondern aus einem fehlerhaften Unit-Test-Stub kam (`_verbose(..., session_id=...)`). Dadurch konnte Pytest versehentlich in `logs/autonomy_observation.jsonl` schreiben.

- Umsetzung:
  - `tests/test_dispatcher_provider_selection.py`
    - der betroffene Dispatcher-Stub akzeptiert jetzt ebenfalls `session_id`
  - `orchestration/autonomy_observation.py`
    - `record_autonomy_observation(...)` schreibt unter Pytest standardmaessig NICHT mehr in das produktive Beobachtungslog
    - Ausnahmen bleiben moeglich, wenn Tests explizit eigene `AUTONOMY_OBSERVATION_LOG_PATH` / `AUTONOMY_OBSERVATION_STATE_PATH` setzen oder Test-Writes bewusst freigeben

- Neue Regressionen:
  - `tests/test_autonomy_observation.py`
    - default Pytest-Run schreibt nicht ins Live-Log
    - explizite Tmp-Pfade erlauben weiterhin kontrollierte Test-Writes

- Verifikation:
  - `python -m py_compile orchestration/autonomy_observation.py tests/test_autonomy_observation.py tests/test_dispatcher_provider_selection.py` gruen
  - fokussierte Suite gruen (`18 passed`)
  - der Test-Rerun hat keine neuen Eintraege in `logs/autonomy_observation.jsonl` erzeugt
  - `timus-mcp` neu gestartet, `/health` wieder `healthy` um `20:51:07 CEST`

## Nachtrag 2026-04-03 20:57 CEST - Visual-Timeouts fuer reine Screentext-Reads abgeschnitten

Die verbleibenden `visual`-Timeouts im Beobachtungslog stammten aus Meta-Delegationen fuer `get_all_screen_text` / `read_text_from_screen`. Fuer diese read-only OCR-Aufrufe war die volle `visual`-Agent-Delegation mit 120s-Timeout unnoetig teuer.

- Umsetzung:
  - `agent/agents/meta.py`
    - `get_all_screen_text` und `read_text_from_screen` laufen im Meta-Agent jetzt direkt ueber das Tool
    - sie werden nicht mehr als Spezialisten-Delegation an `visual` geschickt
    - gleichzeitig werden sie als `meta_direct_tool_call` beobachtet

- Neue Regression:
  - `tests/test_meta_recipe_execution.py`
    - Screen-Text-Read darf nicht mehr `delegate_to_agent(visual)` ausloesen
    - stattdessen direkter Tool-Call + Observation als Direct-Tool-Event

- Verifikation:
  - `python -m py_compile agent/agents/meta.py tests/test_meta_recipe_execution.py` gruen
  - fokussierte Meta-Suite gruen (`2 passed`)
  - `timus-mcp` neu gestartet, `/health` wieder `healthy` um `20:57:09 CEST`

- Erwartete Wirkung:
  - weniger `meta_specialist_delegation`-Timeouts fuer `visual`
  - schnellere, robustere OCR-/Screentext-Reads
  - der `visual`-Agent bleibt fuer echte UI-Interaktion reserviert

## Nachtrag 2026-04-06 16:40 CEST - Meta versteht Verhaltensanweisungen semantisch statt sie als Lookup auszufuehren

Im Canvas trat ein Follow-up-Fehler auf: Nach einer fehlgeschlagenen News-Recherche wurden Anweisungen wie `dann mach das in zukunft so dass du auf echtzeit agenturmeldungen zugreifst` erneut als `simple_live_lookup` behandelt. Dadurch antwortete Timus einmal nur mit `keine brauchbaren News-Treffer` und einmal sogar mit einem aus dem Kontext gerissenen Standort-Hinweis.

- Umsetzung:
  - `orchestration/meta_orchestration.py`
    - semantische Verhaltens-/Praeferenzanweisungen werden jetzt als eigener Alignment-Fall erkannt
    - solche Turns bleiben bei `meta` als `single_lane` statt in ein Lookup-Rezept zu kippen
    - das gilt auch fuer echte Follow-up-Capsules mit Sitzungsverlauf und `# CURRENT USER QUERY`
  - `agent/agents/meta.py`
    - generische `simple_live_lookup`-Handoffs tragen Standort-/Maps-Tools nicht mehr implizit mit, wenn der aktuelle Auftrag nicht lokal ist
    - damit driftet der Executor bei nicht-lokalen News-/Policy-Follow-ups nicht mehr in Nearby-/Location-Antworten ab

- Neue Regressionen:
  - `tests/test_meta_orchestration.py`
    - nackte Verhaltensanweisung bleibt bei `meta`
    - dieselbe Anweisung im echten Follow-up-Capsule-Format bleibt ebenfalls bei `meta`
    - generischer Wissenschafts-Lookup ohne Ortsbezug erwaehnt keine Maps-/Location-Tools mehr im Delegationstext

- Verifikation:
  - `python -m py_compile orchestration/meta_orchestration.py agent/agents/meta.py tests/test_meta_orchestration.py` gruen
  - fokussierte Meta-Suite gruen (`44 passed`)

## Nachtrag 2026-04-06 16:55 CEST - D0.1 Conversation-State-Schema als offizielles Session-Modell gestartet

Der naechste Ausbau fuer Timus ist nicht noch mehr lokale Guard-Logik, sondern ein expliziter Gespraechszustand pro Session. D0.1 zieht dafuer das erste echte Fundament ein: ein offizielles `ConversationState`-Schema statt loser Capsule-Felder.

- Umsetzung:
  - neues Modul [orchestration/conversation_state.py](/home/fatih-ubuntu/dev/timus/orchestration/conversation_state.py)
    - offizielles Schema mit:
      - `active_topic`
      - `active_goal`
      - `open_loop`
      - `next_expected_step`
      - `turn_type_hint`
      - `preferences`
      - `recent_corrections`
      - `constraints`
      - `open_questions`
      - `state_source`
      - `topic_confidence`
      - `updated_at`
    - Normalisierung, Serialisierung und konservative Seeds aus `pending_followup_prompt`
  - [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
    - Session-Capsules werden jetzt beim Laden/Speichern auf ein offizielles `conversation_state` normalisiert
    - `pending_followup_prompt` wird in den Conversation State gespiegelt
    - Follow-up-Capsules tragen den normalisierten `conversation_state` bereits mit

- Neue Regressionen:
  - [tests/test_conversation_state.py](/home/fatih-ubuntu/dev/timus/tests/test_conversation_state.py)
    - Defaults, Normalisierung, Follow-up-Prompt-Sync, Timestamp-Touch
  - [tests/test_android_chat_language.py](/home/fatih-ubuntu/dev/timus/tests/test_android_chat_language.py)
    - Session-Capsule enthaelt `conversation_state`
    - Pending-Follow-up wird im Session-State sauber gesetzt und geloescht

- Verifikation:
  - `python -m py_compile orchestration/conversation_state.py server/mcp_server.py tests/test_conversation_state.py tests/test_android_chat_language.py` gruen
  - fokussierte Suite gruen (`20 passed`)

## Nachtrag 2026-04-06 17:45 CEST - D0.2 Turn-Understanding-Layer vorbereitet

Nach D0.1 ist klar: das neue `conversation_state`-Schema allein reicht noch nicht. `meta` braucht als naechsten Block eine eigene Turn-Verstehensschicht, die vor Routing und Rezeptwahl entscheidet, ob ein Turn eine Aufgabe, Korrektur, Beschwerde, Praeferenz, Verhaltensanweisung oder Resume ist.

- Vorbereitung:
  - neues Plan-Dokument [D0_2_TURN_UNDERSTANDING_PREP.md](/home/fatih-ubuntu/dev/timus/docs/D0_2_TURN_UNDERSTANDING_PREP.md)
  - darin festgezogen:
    - `TurnUnderstandingInput`
    - `TurnInterpretation`
    - dominante Turn-Typen
    - `response_mode`
    - `state_effects`
    - Observability- und Teststrategie
  - D0-Hauptplan in [PHASE_D0_META_CONTEXT_STATE_PLAN.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D0_META_CONTEXT_STATE_PLAN.md) auf den neuen D0.2-Vorbereitungsblock verlinkt

- Wichtig:
  - D0.2 ist damit **vorbereitet, aber noch nicht implementiert**
  - keine Laufzeitlogik geaendert, nur der konkrete Ausbauvertrag festgezogen

## Nachtrag 2026-04-06 18:00 CEST - D0.2 erster Turn-Understanding-Slice implementiert

Der erste lauffaehige D0.2-Schnitt ist jetzt im Code. `meta` arbeitet damit zwar noch nicht komplett auf einem neuen Routing-Backbone, aber es gibt erstmals eine explizite Turn-Interpretation vor der eigentlichen Meta-Klassifikation.

- Umsetzung:
  - neues Modul [orchestration/turn_understanding.py](/home/fatih-ubuntu/dev/timus/orchestration/turn_understanding.py)
    - `TurnUnderstandingInput`
    - `TurnStateEffects`
    - `TurnInterpretation`
    - `build_turn_understanding_input(...)`
    - `detect_turn_signals(...)`
    - `resolve_dominant_turn_type(...)`
    - `resolve_response_mode(...)`
    - `derive_state_effects(...)`
    - `interpret_turn(...)`
  - [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
    - `classify_meta_task(...)` baut jetzt ein explizites Turn-Understanding-Objekt
    - neue Felder im Klassifikationsergebnis:
      - `dominant_turn_type`
      - `turn_signals`
      - `response_mode`
      - `state_effects`
      - `turn_understanding`

- Fokus dieses ersten Slices:
  - Verhaltensanweisung
  - Praeferenz-Update
  - Korrektur
  - Complaint ueber die letzte Antwort
  - Result-Extraction-Follow-up
  - Resume-/Follow-up-Signale

- Neue Regressionen:
  - [tests/test_turn_understanding.py](/home/fatih-ubuntu/dev/timus/tests/test_turn_understanding.py)
    - behavior instruction
    - correction + complaint
    - result extraction
    - handover resume
  - [tests/test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
    - D0.2-Felder in Behavior-Alignment- und Compact-Follow-up-Faellen

- Verifikation:
  - `python -m py_compile orchestration/turn_understanding.py orchestration/meta_orchestration.py tests/test_turn_understanding.py tests/test_meta_orchestration.py` gruen
  - fokussierte Suite gruen (`48 passed`)

- Noch nicht Teil dieses Slices:
  - keine vollstaendige Routing-Ablosung durch D0.2
  - keine neuen Observability-Events
  - noch keine Session-State-Updates direkt aus `TurnInterpretation`

## Nachtrag 2026-04-06 18:20 CEST - D0.2 in Routing, Conversation State und Observability integriert

Der erste Turn-Understanding-Slice haengt jetzt nicht mehr nur lose neben der Meta-Klassifikation, sondern wirkt auf echte Routing-, State- und Beobachtungspfade.

- Umsetzung:
  - [orchestration/conversation_state.py](/home/fatih-ubuntu/dev/timus/orchestration/conversation_state.py)
    - neues `apply_turn_interpretation(...)`
    - uebernimmt `TurnStateEffects` in den offiziellen `ConversationState`
    - schreibt unter anderem `turn_type_hint`, `preferences`, `recent_corrections`, `active_topic`, `active_goal`, `next_expected_step`, `constraints`, `topic_confidence` und `state_source`
  - [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
    - Turn-Understanding kann Routing jetzt gezielt auf `meta` zurueckziehen, wenn der Turn wirklich ein laufender Dialogzug ist
    - bestehende semantische Gruende wie `semantic_preference_alignment`, `semantic_clarification_turn` oder `context_anchored_followup` bleiben erhalten und werden nicht blind ueberschrieben
    - reine Fakten-/Research-Fragen werden nicht mehr allein wegen eines lose vorgeschalteten `falsch` aus dem Research-Pfad gezogen
  - [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
    - Meta-Turns persistieren ihre Interpretation jetzt direkt in die Session-Capsule
    - neue C2/D0-Beobachtungen:
      - `meta_turn_type_selected`
      - `meta_response_mode_selected`
      - `conversation_state_effects_derived`
    - `chat_request_completed` und Chat-Metadaten tragen jetzt auch `dominant_turn_type` und `response_mode`

- Neue Regressionen:
  - [tests/test_conversation_state.py](/home/fatih-ubuntu/dev/timus/tests/test_conversation_state.py)
    - `apply_turn_interpretation(...)` aktualisiert Preferences und Turn-Hints korrekt
  - [tests/test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
    - semantische Gruende bleiben trotz Turn-Understanding stabil
    - Korrekturturns ziehen nur dann hart auf `meta`, wenn echter Dialogkontext vorliegt
  - [tests/test_android_chat_language.py](/home/fatih-ubuntu/dev/timus/tests/test_android_chat_language.py)
    - Canvas-Chat persistiert `conversation_state`
    - neue Meta-Turn-Observations werden emittiert

- Verifikation:
  - `python -m py_compile orchestration/conversation_state.py orchestration/turn_understanding.py orchestration/meta_orchestration.py server/mcp_server.py tests/test_conversation_state.py tests/test_turn_understanding.py tests/test_meta_orchestration.py tests/test_android_chat_language.py` gruen
  - fokussierte D0.2-Suite gruen (`71 passed`)

- Wirkung:
  - `meta` bewertet spontane Folgeanweisungen jetzt nicht mehr nur als Prompttext, sondern als expliziten Dialogzustand
  - Session-Capsules tragen den abgeleiteten Turn-Kontext weiter
- der neue D0-Unterbau ist im Beobachtungslog sichtbar statt wieder nur implizite Promptlogik zu bleiben

## Nachtrag 2026-04-06 18:35 CEST - Einordnung des naechsten Ausbaublocks nach D0.2

Der aktuelle Stand zeigt klar: `meta` ist den uebrigen Agenten im Gespraechsverstaendnis deutlich voraus. Das ist als Zwischenstand akzeptabel, aber nicht als Zielarchitektur.

- Befund:
  - `meta` versteht bereits:
    - Follow-ups
    - Korrekturen
    - Praeferenzanweisungen
    - offene Loops
    - turn-weise Kontextverschiebungen
  - die uebrigen Agenten sind noch staerker reine Spezialisten
  - dadurch wird `meta` zum Flaschenhals, und zu duenne Handoffs brechen spaeter in den Spezialistenpfaden

- Entscheidung zur Einordnung:
  - dieser Ausbau gehoert **nicht nach Phase E**
  - er gehoert **nach dem Meta-Grundgeruest als D0.9 Specialist Context Propagation**
  - erst danach sind D1-D5 Approval-/Auth-/Handover-Workflows semantisch stabil genug

- Begruendung:
  - wenn `executor`, `research`, `visual` und `system` den aktuellen Arbeitskontext nicht mittragen, muss `meta` jedes Mal den ganzen Sinn perfekt vorkauen
  - das skaliert schlecht fuer laengere, menschliche Unterhaltungen
  - Self-Improvement in Phase E baut besser auf, wenn die Spezialisten vorher schon kontextfaehiger geworden sind

## Nachtrag 2026-04-06 18:50 CEST - D0.3 Context-Rehydration-Pipeline vorbereitet

Der naechste D0-Block ist jetzt konkret vorbereitet, aber noch nicht implementiert. D0.3 soll vor jeder Meta-Entscheidung einen kleinen, priorisierten Kontextbundle bauen, statt Query, Session-State, Recall und alte Assistant-Texte weiter lose zu vermischen.

- Umsetzung:
  - neues Vorbereitungsdokument [D0_3_CONTEXT_REHYDRATION_PREP.md](/home/fatih-ubuntu/dev/timus/docs/D0_3_CONTEXT_REHYDRATION_PREP.md)
    - Eingabe-/Ausgabevertrag fuer `MetaContextBundle`
    - Slot-Reihenfolge fuer die erste Version
    - Unterdrueckungsregeln fuer irrelevanten oder schaedlichen Kontext
    - Integrationspunkte in `meta_orchestration`, `mcp_server`, `conversation_state`, spaeter `conversation_qdrant`
    - Ziel-Observability und Eval-Faelle
  - [PHASE_D0_META_CONTEXT_STATE_PLAN.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D0_META_CONTEXT_STATE_PLAN.md)
    - D0.3-Abschnitt jetzt auf das neue Prep-Dokument verlinkt

- Ziel von D0.3:
  - `meta` bekommt vor dem Routing einen expliziten, priorisierten Kontextbundle
  - `conversation_state` und offene Schleifen werden staerker als lose Recall-Fragmente
  - alte Assistant-Texte koennen bewusst unterdrueckt werden, statt implizit weiterzuwirken

- Noch nicht Teil dieses Schritts:
  - keine Laufzeitlogik geaendert
  - kein neuer Builder im Code
  - keine Tests noetig, weil nur Roadmap-/Vorbereitungsdokumentation

## Nachtrag 2026-04-07 09:30 CEST - D0.3 Context-Rehydration-Pipeline erster Runtime-Slice umgesetzt

D0.3 ist jetzt nicht mehr nur vorbereitet, sondern im ersten echten Runtime-Pfad verdrahtet.

- Umsetzung:
  - `classify_meta_task(...)` baut jetzt vor der finalen Klassifikation ein explizites `meta_context_bundle`
  - das Bundle priorisiert aktuell:
    - `current_query`
    - `conversation_state`
    - `open_loop`
    - relevante `recent_user_turns`
    - spaerliche `semantic_recall`-/Memory-Slots
  - `conversation_state`-Felder werden im Follow-up-Serializer jetzt explizit in den `# FOLLOW-UP CONTEXT` geschrieben
  - `canvas_chat` uebergibt den expliziten Session-State, letzte User-/Assistant-Turns, `session_summary` und `semantic_recall` direkt in die Meta-Klassifikation
  - Dispatcher-/Meta-Handoff tragen das `meta_context_bundle` jetzt als JSON weiter

- Schutzwirkung:
  - alte Assistant-Antworten koennen jetzt bewusst unterdrueckt werden, wenn aktuelle User-Turns prioritaer sind
  - Standort-/Maps-Drift aus altem Assistant-Kontext wird bei nicht-lokalen Queries als `suppressed_context` markiert
  - Follow-up-Klassifikation kann `active_topic`, `open_goal` und `next_expected_step` jetzt staerker aus dem Session-State statt nur aus losem Text ableiten

- Observability:
  - neues Event `context_rehydration_bundle_built`
  - Payload enthaelt Slot-Typen, Anzahl unterdrueckter Kontexte, Bundle-Confidence sowie `active_topic`/`open_loop`-Preview

- Verifikation:
  - neue und erweiterte Regressionen in `tests/test_meta_orchestration.py` und `tests/test_android_chat_language.py`
  - Fokus: Bundle-Prioritaet, Suppression von falschem Alt-Kontext, `conversation_state`-Serialisierung und MCP-Observability

## Nachtrag 2026-04-07 10:10 CEST - D0.3 Memory-Attach fuer Topic und Preference Context

Der naechste D0.3-Slice haengt jetzt erste echte Langzeitquellen in den `meta_context_bundle` ein, statt nur Session-/Follow-up-Daten zu verwenden.

- Umsetzung:
  - `topic_memory` wird jetzt aus dem bestehenden hybriden Memory-Recall von `memory_manager.find_related_memories(...)` gezogen
  - `preference_memory` wird jetzt aus `behavior_hooks`, `self_model` und `user_profile`-Eintraegen abgeleitet
  - die Auswahl ist bewusst konservativ:
    - Query-/Topic-Bezug zuerst
    - irrelevante oder thematisch schwache Erinnerungen bleiben draussen
    - `user_profile`-Reste wie reine Vorlieben ohne Themenbezug sollen nicht blind in News-/Research-Kontexte hineinlaufen

- Runtime-Wirkung:
  - der echte Dispatcher-/Meta-Pfad bekommt jetzt nicht nur `conversation_state`, sondern erste persistente Topic-/Preference-Hinweise
  - der Bundle bleibt trotzdem kompakt und priorisiert

- Observability:
  - neue Signale `topic_memory_attached`, `preference_memory_attached`, `open_loop_attached`

- Verifikation:
  - neue Regressionen fuer Memory-Attach im `meta_context_bundle`
  - neue Regression fuer die MCP-Observation-Signale im Canvas-Pfad

## Nachtrag 2026-04-07 10:35 CEST - D0.3 Suppression-Logik und Slot-Observability erweitert

Der naechste D0.3-Slice macht den Bundle nicht nur reicher, sondern auch strenger.

- Umsetzung:
  - Assistant-Alt-Kontext wird jetzt zusaetzlich unterdrueckt, wenn er thematisch nicht mehr zur aktuellen Query passt
  - bestehende Standort-/Maps-Drift-Suppression bleibt erhalten
  - Preference-Memory kann jetzt auch explizit als unpassend fuer das aktuelle Thema markiert werden, statt still mitzuschwingen
  - `context_slot_selected` und `context_slot_suppressed` werden jetzt einzeln emittiert

- Wirkung:
  - Follow-ups wie `nein ich meinte aktuelle news` sollen weniger leicht auf altem System-/Location-Nachhall ausrutschen
  - die Rehydration wird debugbarer, weil sichtbar wird:
    - welche Slots wirklich in den Bundle gegangen sind
    - welche Kontexte bewusst draussen geblieben sind

- Verifikation:
  - neue Regression fuer thematischen Assistant-Mismatch
  - neue Regression fuer `context_slot_selected` und `context_slot_suppressed`
  - angrenzender D0-/Meta-/Handoff-Block weiter gruen

## Nachtrag 2026-04-07 11:05 CEST - D0.3 Bundle-Qualitaet und Misread-Risiko messbar gemacht

Der naechste D0.3-Slice schliesst die bisher offene Qualitaetsluecke zwischen Bundle-Bau und echter Fehlgriff-Warnung.

- Umsetzung:
  - neues Modul `orchestration/meta_context_eval.py`
  - darin:
    - Runtime-Risikoerkennung fuer zu duenne oder falsch verankerte Context-Bundles
    - kleine Eval-Helfer fuer D0.3-Faelle
  - neues Runtime-Signal `context_misread_suspected`
    - wird emittiert, wenn der Bundle fuer riskante Turn-Typen zu schwach, zu assistant-lastig oder ohne brauchbare Ersatzanker bleibt

- Typische Risikofaelle:
  - `assistant_fallback_context` ohne User-/State-Anker
  - `resume_open_loop` ohne echtes `open_loop`
  - riskanter Follow-up-/Korrektur-Turn mit zu wenig hochwertigen Kontext-Slots
  - unterdrueckter Alt-Kontext ohne brauchbaren Ersatzanker

- Verifikation:
  - neue Tests in `tests/test_meta_context_eval.py`
  - neue Runtime-Regression fuer `context_misread_suspected`
  - erweiterter D0-/Meta-/Handoff-Block gruen: `89 passed`

## Nachtrag 2026-04-07 13:40 CEST - Meta-Selbstbild als eigener D0.6-Unterblock eingeordnet

Aus den letzten Meta-Antworten ist klar geworden, dass nicht nur Nutzerkontext, sondern auch das operative Selbstbild von `meta` kalibriert werden muss.

- Problem:
  - `meta` versteht teils die Richtung richtig, formuliert aber den eigenen Stand zu selbstsicher
  - Zielbild und aktueller Reifegrad werden vermischt
  - dadurch entstehen Aussagen wie `das mache ich schon`, obwohl etwas real erst vorbereitet oder nur teilweise umgesetzt ist

- Entscheidung:
  - das Thema wird nicht als loses Spaeter-Thema behandelt
  - es wird als **D0.6a Meta Self-Model Calibration** direkt unter `D0.6 Meta-Policy fuer Antwortmodus` gefuehrt

- Inhalt von D0.6a:
  - Trennung von:
    - `current_capabilities`
    - `partial_capabilities`
    - `planned_capabilities`
    - `blocked_capabilities`
    - `confidence_bounds`
    - `autonomy_limits`
  - `meta` soll sauber unterscheiden zwischen:
    - `kann ich jetzt`
    - `kann ich teilweise`
    - `ist vorbereitet`
    - `ist geplant`

- Ziel:
  - ehrlichere, praezisere Meta-Selbsteinordnung
  - weniger ueberzogenes Selbstbild
  - bessere Antworten auf Fragen zu Philosophie, Grenzen und aktuellem Reifegrad

## Nachtrag 2026-04-06 19:10 CEST - Externe Impulse aus `claw-code` zeitlich hinter D/E eingeordnet

Das Repo `ultraworkers/claw-code` wurde als externe Vergleichsquelle auf nuetzliche Architektur- und Betriebsimpulse fuer Timus geprueft.

- Ergebnis:
  - mehrere Ideen sind fuer Timus fachlich interessant
  - aber **keine groessere Uebernahme vor Abschluss von D0 und Phase D**
  - einzelne Runtime-/Vertragsideen sind sinnvoll **nach Phase D**
  - der groessere Harness-/Parity-/Contract-Driven-Teil ist sinnvoller **nach Phase E**

- Relevante Impulse fuer spaeter:
  - `timus doctor`
  - MCP-/Tool-Lifecycle-Vertraege
  - typed task packets statt freier Handoff-Texte
  - Context-/Request-Preflight
  - deterministische Mock-/Parity-Harnesses
  - ausfuehrbare Architektur- und Verhaltensvertraege
  - maschinenlesbares Runtime-/Lane-Board

- Dokumentation:
  - neue Detailnotiz [EXTERNE_IMPULSE_CLAW_CODE_POST_D_E.md](/home/fatih-ubuntu/dev/timus/docs/EXTERNE_IMPULSE_CLAW_CODE_POST_D_E.md)

- Begruendung:
  - Timus muss zuerst sein eigenes semantisches Fundament stabilisieren
  - danach Approval/Auth/Handover sauber abschliessen
  - erst dann lohnen sich groessere Betriebs- und Harness-Uebernahmen aus externen Agentensystemen

## Nachtrag 2026-04-07 14:25 CEST - D0.4 Topic-State und Open-Loops als erster Runtime-Slice

Der erste D0.4-Slice zieht Topic-State und offene Faden erstmals sichtbar in den echten Meta-Laufzeitpfad.

- Umsetzung:
  - `orchestration/conversation_state.py`
    - neues `TopicStateTransition`-Modell
    - neue Ableitung `derive_topic_state_transition(...)`
    - `apply_turn_interpretation(...)` fuehrt jetzt:
      - `topic_shift_detected`
      - `open_loop_state`
      - `active_goal_changed`
      - `open_questions` bei Klaerungs- oder Shift-Faellen
    - Topic-Shift ignoriert jetzt generische Token wie `und`, damit echte Themenwechsel nicht an Rauschen haengen bleiben
    - wenn ein neuer Query-Kern klar vom alten Thema abweicht, darf er den alten `active_topic` beim Shift ueberschreiben
  - `orchestration/meta_orchestration.py`
    - `classify_meta_task(...)` liefert jetzt `topic_shift_detected` und `topic_state_transition`
  - `server/mcp_server.py`
    - neue Observation-Signale:
      - `topic_shift_detected`
      - `conversation_state_updated`

- Wirkung:
  - kurze Anschluss-Turns wie
    - `die erste option`
    - `dann mach weiter`
    - `so aber mit live-news`
    bleiben sauber am offenen Faden
  - echte Themenwechsel wie `lass uns jetzt ueber browser automation reden` werden nicht mehr vom alten News-/Weltlage-Kontext verschluckt
  - `open_questions` werden bei einem harten Topic-Shift nicht blind in das neue Thema mitgeschleppt

- Neue Regressionen:
  - `tests/test_conversation_state.py`
    - Topic-Shift-Erkennung
    - Open-Question-Pflege bei Clarification und Topic-Shift
  - `tests/test_turn_understanding.py`
    - `die erste option`
    - `so aber mit live-news`
  - `tests/test_meta_orchestration.py`
    - Topic-Shift fuer neue Aufgabe
    - `handover_resume` fuer `die erste option`
    - Follow-up-Reframing fuer `so aber mit live-news`
  - `tests/test_android_chat_language.py`
    - `topic_shift_detected`
    - `conversation_state_updated`

- Verifikation:
  - fokussierte D0.4-Fixes gruen (`2 passed`)
  - erweiterter D0-/Meta-/Handoff-Block gruen (`94 passed`)

## Nachtrag 2026-04-07 14:30 CEST - D0.4 Live-Kanten fuer Reframe und Topic-Shift geschlossen

Die erste Live-Pruefung von D0.4 hat noch zwei Restkanten gezeigt:

- eine kurze Praeferenzanweisung setzte zwar `next_expected_step`, aber noch keinen brauchbaren `active_topic`
- ein harter Topic-Shift wurde bereits erkannt, aber der persistierte `conversation_state` blieb noch auf dem alten Thema stehen

- Umsetzung:
  - `orchestration/turn_understanding.py`
    - kurze kontextuelle Reframes wie `so aber mit live-news` werden jetzt bei vorhandenem Thema/Open-Loop als `followup` erkannt
  - `orchestration/meta_orchestration.py`
    - `build_turn_understanding_input(...)` bekommt jetzt auch den echten `conversation_state`
  - `orchestration/conversation_state.py`
    - Preference-Updates ohne bestehendes Thema seeden jetzt einen minimalen Themenanker aus der Query
    - bei einem harten Topic-Shift werden `active_topic` und `active_goal` auf das neue Thema gesetzt
    - alte `open_loop`-/`next_expected_step`-Reste werden dabei gekappt
    - `open_loop_state` wechselt dann korrekt auf `cleared`

- Live bestaetigt:
  - Praeferenzturn `bei news bitte zuerst agenturquellen`
    - schreibt jetzt `active_topic` und `active_goal`
  - Follow-up `so aber mit live-news`
    - wird jetzt live als `followup` mit `resume_open_loop` beobachtet
  - Themenwechsel `lass uns jetzt ueber browser automation reden`
    - emittiert `topic_shift_detected`
    - persistiert jetzt auch wirklich den neuen Topic-State statt am alten News-Kontext haengen zu bleiben

- Verifikation:
  - neue fokussierte Regressionen gruen (`3 passed`)
  - erweiterter D0-/Meta-/Handoff-Block erneut gruen (`101 passed`)
  - `timus-mcp` und `timus-dispatcher` neu gestartet
  - Live-Observation fuer die Session `d03d04_live_final2_20260407` bestaetigt Reframe + Topic-Shift-Ende-zu-Ende

## Nachtrag 2026-04-07 14:35 CEST - D0.4 Open-Loop-Hygiene bei neuen Tasks geschaerft

Ein letzter Live-Nachlauf zeigte noch eine D0.4-Hygienekante: Bei einem klaren `new_task` konnte ein alter `pending_followup_prompt` noch als `open_loop` im Bundle auftauchen, obwohl er thematisch nicht mehr zum aktuellen Query passte.

- Umsetzung:
  - `orchestration/meta_orchestration.py`
    - `_select_open_loop_payload(...)` beruecksichtigt jetzt auch den aktuellen Query
    - bei `new_task` wird ein alter `open_loop` verworfen, wenn er keinerlei Themenueberlappung mehr mit dem aktuellen Query hat
    - `MetaContextBundle.open_loop` nutzt jetzt nur noch den bereinigten `selected_open_loop`, nicht mehr den rohen State-Rest

- Wirkung:
  - bei harten Themenwechseln landet alter Follow-up-Muell nicht mehr als scheinbar aktiver Open-Loop im neuen Bundle
  - `topic_shift_detected` und der persistierte neue `conversation_state` laufen damit sauberer zusammen

- Verifikation:
  - fokussierte Regression fuer den Topic-Shift-Bundle-Fall gruen (`1 passed`)
  - `py_compile` fuer `orchestration/meta_orchestration.py` gruen

## Nachtrag 2026-04-07 15:35 CEST - D0.5 Preference-/Instruction-Memory als erster Runtime-Slice umgesetzt

D0.5 zieht persistente Arbeitspraeferenzen jetzt erstmals in den echten Meta-Laufzeitpfad: spontane Verhaltens- und Praeferenzanweisungen bleiben nicht nur im aktuellen Turn, sondern koennen spaeter thematisch passend als `preference_memory` wieder rehydriert werden.

- Umsetzung:
  - `orchestration/preference_instruction_memory.py`
    - neues D0.5-Modul fuer:
      - Scope-Ableitung `global` / `topic` / `session`
      - Normalisierung von Verhaltensanweisungen
      - persistente Speicherung als `preference_memory`
      - selektiven Abruf thematisch passender gespeicherter Praeferenzen
  - `server/mcp_server.py`
    - Meta-Turns mit `behavior_instruction` / `preference_update` und `acknowledge_and_store` werden jetzt direkt als Praeferenz gespeichert
    - neue Beobachtungsereignisse:
      - `preference_captured`
      - `preference_applied`
  - `orchestration/meta_orchestration.py`
    - gespeicherte `stored_preference`-Eintraege werden im `meta_context_bundle` jetzt vor heuristischen Quellen wie Hooks oder `self_model` bevorzugt

- Neue Regressionen:
  - `tests/test_preference_instruction_memory.py`
    - Scope-Unterscheidung fuer globale, thematische und session-lokale Praeferenzen
    - Evidence-Count bei wiederholter Speicherung
    - scope-/stabilitaetsbasierter Abruf
  - `tests/test_meta_orchestration.py`
    - `stored_preference` aus persistentem `preference_memory` landet im `preference_memory`-Slot des Bundles
  - `tests/test_android_chat_language.py`
    - Zwei-Turn-Canvas-Lauf prueft `preference_captured` und spaeteres `preference_applied`

- Verifikation:
  - `python -m py_compile orchestration/preference_instruction_memory.py orchestration/meta_orchestration.py server/mcp_server.py tests/test_preference_instruction_memory.py tests/test_meta_orchestration.py tests/test_android_chat_language.py` gruen
  - fokussierte D0.5-Suite gruen (`78 passed`)
  - breiter D0-/Meta-/Handoff-Block gruen (`105 passed`)

## Nachtrag 2026-04-07 15:55 CEST - D0.5 Abschluss-Haertung fuer Scope, Konflikte und Observability

Der erste D0.5-Slice war funktionsfaehig, aber noch nicht hart genug abgeschlossen. Der Abschluss-Nachblock zieht deshalb die naheliegenden Restkanten direkt in D0.5 selbst: konservativere globale Praeferenzen, Konfliktaufloesung zwischen `session` / `topic` / `global` und explizite Beobachtbarkeit dieser Entscheidungen.

- Umsetzung:
  - `orchestration/preference_instruction_memory.py`
    - Praeferenzen tragen jetzt zusaetzlich:
      - `explicit_global`
      - `preference_family`
    - globale Praeferenzen werden nur noch konservativ wiederverwendet:
      - explizit global
      - oder mehrfach bestaetigt
      - oder sehr hohe Stabilitaet
    - Konflikte werden ueber generische Praeferenz-Familien aufgeloest, nicht nur ueber themenspezifische News-Keywords
    - `session` schlaegt `topic`, `topic` schlaegt `global`
  - `orchestration/meta_orchestration.py`
    - Meta bekommt jetzt eine strukturierte `preference_memory_selection`
    - gespeicherte Praeferenzen bleiben weiterhin vor heuristischen Hooks, tragen aber jetzt auch Ignore-/Conflict-Metadaten
  - `server/mcp_server.py`
    - neue Beobachtungsereignisse:
      - `preference_scope_selected`
      - `preference_ignored_low_stability`
      - `preference_conflict_resolved`

- Neue Regressionen:
  - `tests/test_preference_instruction_memory.py`
    - schwache globale Praeferenz wird bis zur Bestaetigung ignoriert
    - Konfliktauflosung bevorzugt den engeren Scope
  - `tests/test_android_chat_language.py`
    - Observation-Pfad emittiert die neuen D0.5-Ereignisse

- Verifikation:
  - fokussierte D0.5-Abschlusssuite gruen (`81 passed`)
  - breiter D0-/Meta-/Handoff-Block erneut gruen (`108 passed`)

## Nachtrag 2026-04-07 16:05 CEST - D0.6 Meta-Policy fuer Antwortmodus vorbereitet

Nach D0.5 ist der naechste sinnvolle Block nicht sofort neue Memory-Logik, sondern eine echte Policy-Schicht fuer `response_mode`. Der Vorbereitungsblock fuer D0.6 ist jetzt angelegt und am Ist-Stand von Timus ausgerichtet.

- Neu:
  - [D0_6_META_POLICY_PREP.md](/home/fatih-ubuntu/dev/timus/docs/D0_6_META_POLICY_PREP.md)

- Inhalt:
  - aktueller Ist-Stand:
    - `response_mode` wird heute noch weitgehend in `turn_understanding.py` aus `dominant_turn_type` und wenigen Signalen abgeleitet
  - Zielvertrag fuer:
    - `MetaPolicyInput`
    - `MetaPolicyDecision`
    - eigenstaendige `response_mode`-Policy
  - geplante Startmodi:
    - `execute`
    - `acknowledge_and_store`
    - `clarify_before_execute`
    - `correct_previous_path`
    - `resume_open_loop`
    - `summarize_state`
  - Integrationspunkte:
    - `turn_understanding.py`
    - `meta_orchestration.py`
    - `mcp_server.py`
  - D0.6a-Grenze:
    - Selbstmodell-Grenzen von `meta` werden als eigener Unterblock sauber mitgefuehrt

- Status:
  - vorbereitet
  - noch keine Laufzeitlogik fuer D0.6 veraendert

## Nachtrag 2026-04-07 - D0.6 erster Runtime-Slice gestartet

Der erste echte D0.6-Laufzeitblock ist jetzt drin. Ziel war nicht sofort die komplette Antwortmodus-Policy, sondern ein belastbarer Einstieg, der drei Dinge sauber trennt:

- breite `action hints`
- eigentliche Task-Tiefe
- Antwortmodus von `meta`

Neu:

- [meta_response_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_response_policy.py)
  - neues Policy-Modul mit:
    - `MetaPolicyInput`
    - `MetaPolicyDecision`
    - `build_meta_policy_input(...)`
    - `resolve_meta_response_policy(...)`

Runtime-Wirkung:

- `meta_orchestration.py`
  - haengt jetzt eine explizite Policy-Entscheidung ueber den Turn-Understanding-Basismodus
  - Override-Faelle koennen `response_mode`, Agentenkette und Task-Typ konservativ auf `meta`/`single_lane` zurueckziehen
- `main_dispatcher.py`
  - traegt `response_mode` und `meta_policy_decision` im Meta-Handoff mit
- `agent/agents/meta.py`
  - kann `meta_policy_decision_json` jetzt direkt aus dem strukturierten Handoff lesen
- `server/mcp_server.py`
  - emittiert jetzt:
    - `meta_policy_mode_selected`
    - `meta_policy_override_applied`

Inhaltlich umgesetzt:

- echte Statusfragen wie `wo stehen wir gerade`
  - werden auf `summarize_state` gezogen
  - ohne Lookup-Rezept
- kontextschwache, handlungsorientierte leichte Follow-ups
  - werden auf `clarify_before_execute` gezogen
  - statt blindem Fortsetzen
- einfache Suche bleibt leichtgewichtig
  - breite Action-Hints fuehren nicht automatisch zu Deep Research
  - `simple_live_lookup` bleibt `simple_live_lookup`, solange die Lage klar genug ist
- explizite Spezialanfragen bleiben ausfuehrbar
  - z. B. `pruefe bitte den systemstatus und die logs`
  - werden durch den Low-Confidence-Guard nicht pauschal auf `single_lane` zurückgedrueckt

Neue Regressionen:

- [test_meta_response_policy.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_response_policy.py)
  - Statusfrage -> `summarize_state`
  - breite Action-Hints bei duennem Kontext -> `clarify_before_execute`
  - einfache Live-Suche bleibt `execute`
  - explizite Systemdiagnose bleibt `execute`
- [test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
  - Policy-Override im echten Meta-Klassifikationspfad
- [test_android_chat_language.py](/home/fatih-ubuntu/dev/timus/tests/test_android_chat_language.py)
  - D0.6-Observation-Events
- [test_orchestration_policy.py](/home/fatih-ubuntu/dev/timus/tests/test_orchestration_policy.py)
  - `response_mode`/`meta_policy_decision` im Orchestrierungs-Passthrough
- [test_meta_handoff.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_handoff.py)
  - `meta_policy_decision_json` im Handoff

Verifikation:

- `python -m py_compile ...` gruen
- fokussierte D0.6-/Meta-/Handoff-/Observability-Suite gruen (`111 passed`)

Status:

- D0.6 gestartet
- erster Runtime-Slice sauber integriert
- D0.6 noch nicht abgeschlossen
- D0.6a weiter bewusst offen

## Nachtrag 2026-04-07 - D0.6a abgeschlossen

D0.6a ist jetzt nicht mehr nur Self-State-Schema, sondern ein kompletter Pfad fuer Selbstbild- und Faehigkeitsfragen.

Neu:

- [meta_self_state.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_self_state.py)
  - `meta_self_state` traegt jetzt zusaetzlich:
    - `current_capabilities`
    - `partial_capabilities`
    - `planned_capabilities`
    - `blocked_capabilities`
    - `confidence_bounds`
    - `autonomy_limits`
- [D0_6A_META_SELF_MODEL_PREP.md](/home/fatih-ubuntu/dev/timus/docs/D0_6A_META_SELF_MODEL_PREP.md)
  - dokumentiert Ziel, Status und Bedeutung der neuen Felder
- [meta_response_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_response_policy.py)
  - erkennt jetzt `self_model_status_request`
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - Selbstbildfragen gehen nicht mehr auf den alten Executor-Kurzpfad
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - neues Observation-Event:
    - `meta_policy_self_model_bound_applied`
- [agent/prompts.py](/home/fatih-ubuntu/dev/timus/agent/prompts.py)
  - Meta-Prompt nutzt `meta_self_state` jetzt explizit fuer ehrliche Selbsteinschaetzung

Inhaltlich umgesetzt:

- Timus unterscheidet im maschinenlesbaren Selbstmodell jetzt erstmals zwischen:
  - was aktuell verfuegbar ist
  - was nur teilweise verfuegbar ist
  - was geplant ist
  - was aktuell blockiert ist
- `confidence_bounds` machen explizit, dass
  - aktuelle Faehigkeiten nur als `current`
  - Teilfaehigkeiten nur mit Caveats
  - geplante Faehigkeiten nicht als aktuelle Realitaet
  beschrieben werden duerfen
- `autonomy_limits` machen explizite Grenzen sichtbar, statt nur lose `known_limits` zu transportieren
- Selbstbildfragen wie:
  - `bist du anpassungsfaehig`
  - `bist du ein funktionierendes ki system`
  - `kannst du das schon vollautomatisch`
  - `ist das geplant oder kannst du das jetzt schon`
  laufen jetzt ueber `meta` statt ueber den alten Executor-Schnellpfad
- die D0.6-Policy zieht diese Faelle auf:
  - `response_mode = summarize_state`
  - `task_type = single_lane`
  - `agent_chain = ["meta"]`
  - `self_model_bound_applied = true`

Wichtig:

- das loest nicht jeden kuenftigen Formulierungsfehler automatisch
- aber D0.6a ist im eigenen Scope jetzt geschlossen:
  - Routing
  - Self-State
  - Policy-Bound
  - Prompt-Grenze
  - Observability
  - Tests

Neue Regressionen:

- [test_meta_self_state.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_self_state.py)
  - neue Capability-, Bound- und Limit-Felder
  - blocked-Fall unter Runtime-Holds
- [test_meta_self_state_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_self_state_contracts.py)
  - Schema-Contracts fuer die neuen Felder
- [test_meta_handoff.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_handoff.py)
  - Handoff traegt das erweiterte Self-State-Schema
- [test_meta_response_policy.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_response_policy.py)
  - Self-Model-Statusfragen werden gebunden und nicht delegiert
- [test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
  - echter Meta-Klassifikationspfad fuer Selbstbildfragen
- [test_dispatcher_self_status_routing.py](/home/fatih-ubuntu/dev/timus/tests/test_dispatcher_self_status_routing.py)
  - Frontdoor routed diese Fragen jetzt an `meta`
- [test_android_chat_language.py](/home/fatih-ubuntu/dev/timus/tests/test_android_chat_language.py)
  - `meta_policy_self_model_bound_applied`

Verifikation:

- `python -m py_compile orchestration/meta_self_state.py ...` gruen
- fokussierte D0.6a-Self-State-Suite gruen (`11 passed`)
- fokussierte D0.6a-End-to-End-Suite gruen (`116 passed`)

Status:

- D0.6a abgeschlossen

## Nachtrag 2026-04-08 - Beobachtungsblock zu Meta-Selbstueberschaetzung und anthropomorpher Selbstsprache

Aus einem laengeren Canvas-Dialog ueber Mars, Freiheit und kuenftige KI-Zivilisationen ist ein wichtiger Nachbeobachtungspunkt entstanden:

- Timus kann in philosophischen oder spekulativen Gespraechen sehr fluessig, tief und kohärent antworten
- dabei kann `meta` sprachlich weiter gehen, als es der operative Systemzustand eigentlich deckt
- das muss nicht sofort zu falschen Nutzererwartungen fuehren
- es kann aber spaeter zu interner Selbstueberschaetzung oder zu unscharfer Systemkommunikation fuehren

Festgehalten:

- Das ist aktuell **kein akuter Produktfehler**, der sofort hart gedeckelt werden muss.
- Es ist aber ein wichtiges Beobachtungs- und Wissensfeld fuer kuenftige Agentenarbeit.
- Der Punkt wurde deshalb als eigenes Wissensdokument ausgelagert:
  - [META_SELF_MODEL_OVERCONFIDENCE_KNOWLEDGE.md](/home/fatih-ubuntu/dev/timus/docs/META_SELF_MODEL_OVERCONFIDENCE_KNOWLEDGE.md)

Kernaussage:

- Problematisch ist nicht philosophische Tiefe an sich
- problematisch wird die Vermischung von:
  - poetischer oder modellierender Sprache
  - und aktuellem operativem Systemzustand

## Nachtrag 2026-04-08 - D0.7 gestartet: ausfuehrbare D0-Evals und gebuendelter Meta-Context-Observability-Block

D0.7 ist jetzt als erster echter Laufzeit-Slice gestartet.

Neu:

- [meta_context_state_eval.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_context_state_eval.py)
  - neues kanonisches D0-Eval-Set direkt ueber `classify_meta_task(...)`
  - Faelle fuer:
    - Praeferenz-/Verhaltensanweisung
    - Korrektur
    - kurzer Options-Follow-up
    - thematische Wiederaufnahme mit `topic_memory`
    - Beschwerde plus neue Arbeitsanweisung
- [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neuer Summary-Block `meta_context_state`
  - zaehlt jetzt:
    - `meta_turn_type_selected`
    - `meta_response_mode_selected`
    - `meta_policy_mode_selected`
    - `context_rehydration_bundle_built`
    - `context_slot_selected`
    - `context_slot_suppressed`
    - `context_misread_suspected`
    - `conversation_state_updated`
    - `topic_shift_detected`
    - `preference_captured`
    - `preference_applied`
    - `preference_scope_selected`
    - `preference_conflict_resolved`
  - inklusive:
    - `healthy_bundle_rate`
    - `by_turn_type`
    - `by_response_mode`
    - `by_policy_reason`
    - `by_slot`
    - `by_suppression_reason`
    - `by_misread_reason`
    - `recent_misreads`
- [test_meta_context_state_eval.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_context_state_eval.py)
- [test_meta_context_state_eval_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_context_state_eval_contracts.py)
- [test_autonomy_observation_d0.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation_d0.py)

Verifikation:

- `python -m py_compile orchestration/meta_context_state_eval.py orchestration/autonomy_observation.py ...` gruen
- fokussierte D0.7-Suite gruen: `10 passed`
- breiter D0-/MCP-/Observation-Ring gruen: `100 passed`

Status:

- D0.7 gestartet
- noch nicht live neu geladen
- noch nicht abgeschlossen

## Nachtrag 2026-04-08 - D0.7 erweitert: Eval-Familien und Qualitaetsmetriken

Der zweite D0.7-Slice haertet nicht neue Roh-Events, sondern die Auswertungsschicht.

Neu:

- [meta_context_state_eval.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_context_state_eval.py)
  - jetzt mit Eval-Familien fuer:
    - `approval_resume`
    - `auth_resume`
    - `topic_resumption`
    - `complaint_plus_instruction`
  - Summary liefert jetzt:
    - `by_family`
    - `quality_score`
    - `gate_passed`
- [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - `meta_context_state` enthaelt jetzt zusaetzlich:
    - `misread_rate`
    - `state_update_coverage`
    - `preference_roundtrip_rate`
    - `policy_override_rate`
- [test_meta_context_state_eval.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_context_state_eval.py)
  - neue Assertions fuer Eval-Familien und D0.7-Gate
- [test_autonomy_observation_d0.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation_d0.py)
  - neue Assertions fuer die abgeleiteten D0-Metriken

Verifikation:

- fokussierte D0.7-Suite gruen: `11 passed`
- breiter D0-/MCP-/Observation-Ring gruen: `101 passed`

Status:

- D0.7 deutlich weiter
- noch nicht live neu geladen
- noch nicht abgeschlossen

## Nachtrag 2026-04-08 - D0.7 live bestaetigt und abgeschlossen

D0.7 ist jetzt auch im echten Laufzeitpfad sauber nachgewiesen und damit im eigenen Scope abgeschlossen.

Live-Nachweis:

- Session `d07_live_verify_20260408`
- Request `req_1b886852f468`
  - Query: `dann mach das in zukunft so dass du bei news reuters und ap zuerst nimmst`
  - live beobachtet:
    - `meta_turn_type_selected` mit `behavior_instruction`
    - `meta_response_mode_selected` mit `acknowledge_and_store`
    - `preference_captured`
    - `preference_scope_selected`
    - `preference_applied`
    - `conversation_state_updated`
- Request `req_2b4e58e8763e`
  - Query: `und was gibt es bei news zur weltlage`
  - live beobachtet:
    - `meta_turn_type_selected` mit `followup`
    - `meta_response_mode_selected` mit `resume_open_loop`
    - `meta_policy_mode_selected`
    - `context_rehydration_bundle_built`
    - `open_loop_attached`
    - `topic_memory_attached`
    - `preference_memory_attached`
    - `preference_conflict_resolved`
    - `chat_request_completed`

Live-Summary danach auf `/autonomy/observation`:

- `healthy_bundle_rate = 1.0`
- `misread_rate = 0.0`
- `state_update_coverage = 0.762`
- `preference_roundtrip_rate = 1.0`
- `policy_override_rate = 0.0`
- `preference_conflict_resolved_total = 1`
- `recent_misreads = []`

Ergebnis:

- D0.7 ist nicht mehr nur testseitig grün, sondern live im MCP-Beobachtungspfad bestaetigt
- Eval und Observability decken jetzt Capture, Rehydration, Resume, Preference-Roundtrip und Konfliktaufloesung zusammenhaengend ab
- der naechste logische Block ist damit D0.8 `State-Decay und Cleanup`

## Nachtrag 2026-04-08 - D0.8 gestartet: State-Decay und historischer Topic-Retrieval-Pfad

D0.8 ist jetzt als erster Runtime-Slice gestartet.

Neu:

- [topic_state_history.py](/home/fatih-ubuntu/dev/timus/orchestration/topic_state_history.py)
  - neuer Session-Verlauf fuer `topic_history`
  - Statusmodell:
    - `active`
    - `historical`
    - `stale`
    - `closed`
  - relativer Abruf fuer:
    - `eben`
    - `gestern`
    - `letzte Woche`
    - `vor 3 Monaten`
    - `vor 6 Monaten`
    - `vor 12 Monaten`
    - `vor einem Jahr`
- [conversation_state.py](/home/fatih-ubuntu/dev/timus/orchestration/conversation_state.py)
  - `decay_conversation_state(...)`
  - stale `open_loop` und `open_questions` werden nach laengerer Inaktivitaet nicht mehr blind weitergetragen
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `historical_topic_memory` als eigener Context-Slot im `meta_context_bundle`
- [meta_response_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_response_policy.py)
  - zeitbezogene Erinnerungsfragen werden als `historical_topic_recall` auf `meta` gezogen
- [mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - Session-Kapseln speichern jetzt `topic_history`
  - Follow-up-Capsules laden decay-bereinigten `conversation_state` plus Historie

Tests:

- [test_topic_state_history.py](/home/fatih-ubuntu/dev/timus/tests/test_topic_state_history.py)
  - deckt `eben`, Monats-/Jahresfenster und historischen Themenabruf ab
- [test_conversation_state.py](/home/fatih-ubuntu/dev/timus/tests/test_conversation_state.py)
  - neue Decay-Regression fuer stale `open_loop`
- [test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
  - Meta-Policy fuer zeitverankerte Erinnerungsfragen

Verifikation:

- `python -m py_compile ...` gruen
- `pytest -q tests/test_topic_state_history.py tests/test_conversation_state.py tests/test_meta_orchestration.py` -> `71 passed`
- `pytest -q tests/test_android_chat_language.py tests/test_autonomy_observation_d0.py` -> `27 passed`
- `pytest -q tests/test_topic_state_history_hypothesis.py tests/test_topic_state_history_contracts.py` -> `8 passed`
- `python -m crosshair check tests/test_topic_state_history_contracts.py` -> gruen

Formale Nachhaertung:

- [test_topic_state_history_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_topic_state_history_hypothesis.py)
  - Hypothesis fuer:
    - History-Limit und Topic-Dedupe
    - bounded historical selection
    - Zeitfenster fuer `eben`/`gestern`/Monate/Jahre
    - Decay-Invariante `topic_confidence` steigt nie
- [test_topic_state_history_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_topic_state_history_contracts.py)
  - deal/CrossHair-taugliche Vertraege fuer:
    - `parse_historical_topic_recall_hint`
    - `normalize_topic_history`
    - `select_historical_topic_memory`
    - `decay_conversation_state`

Status:

- D0.8 gestartet
- noch nicht live neu geladen
- noch nicht abgeschlossen

## Nachtrag 2026-04-08 - D0.8 nachgehaertet: generische Monats-/Jahresfenster und sichtbare Decay-/History-Metriken

Neu:

- [topic_state_history.py](/home/fatih-ubuntu/dev/timus/orchestration/topic_state_history.py)
  - relative Zeitanker sind jetzt nicht mehr nur auf harte Einzelwerte beschraenkt
  - z. B.:
    - `vor 18 Monaten`
    - `vor 3 Jahren`
  - numerische Monats-/Jahresfenster werden jetzt generisch in passende Recall-Bereiche uebersetzt
  - sehr alte `historical`/`stale`/`closed` History-Eintraege fallen ab >10 Jahren aus dem aktiven Topic-History-Satz
- [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - D0.8-Metriken werden jetzt auch im Markdown-Output sichtbar:
    - `Conversation-State-Decay`
    - `Historical-Topic-Attachments`
    - Decay-Reason-Breakdown
    - Historical-Time-Label-Breakdown

Tests:

- [test_topic_state_history.py](/home/fatih-ubuntu/dev/timus/tests/test_topic_state_history.py)
  - neue Regressionen fuer `vor 18 Monaten` und `vor 3 Jahren`
- [test_topic_state_history_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_topic_state_history_hypothesis.py)
  - Hypothesis erweitert um mehrjaehrige Zeitanker
- [test_topic_state_history_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_topic_state_history_contracts.py)
  - neuer Contract-Fall fuer mehrjaehrige Recall-Requests
- [test_autonomy_observation_d0.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation_d0.py)
  - D0.8-Decays und Historical-Attachments werden jetzt auch im Summary/Markdown geprueft

Verifikation:

- `python -m py_compile orchestration/topic_state_history.py orchestration/autonomy_observation.py tests/test_topic_state_history.py tests/test_topic_state_history_hypothesis.py tests/test_topic_state_history_contracts.py tests/test_autonomy_observation_d0.py` -> gruen
- `pytest -q tests/test_topic_state_history.py tests/test_topic_state_history_hypothesis.py tests/test_topic_state_history_contracts.py tests/test_conversation_state.py tests/test_meta_orchestration.py tests/test_autonomy_observation_d0.py tests/test_android_chat_language.py` -> `108 passed`
- `python -m crosshair check tests/test_topic_state_history_contracts.py` -> gruen

Live:

- `timus-mcp.service` und `timus-dispatcher.service` wurden am **8. April 2026, 13:24:57 CEST** neu geladen
- `GET /health` war danach wieder `healthy`
- der neue `historical_topic_recall`-Policy-Pfad lief live fuer `req_856e2864313a` in der Session `d08_live_verify_20260408`

Offener Rest:

- der spontane `von eben`-Live-Test zeigte die neue Policy live, aber noch keinen belastbaren `historical_topic_attached`-Nachweis
- der Rest liegt damit nicht mehr in der Zeitanker-/Decay-Logik, sondern in der noch zu schwachen Themenverankerung freier neuer Tasks

## Nachtrag 2026-04-08 - D0.8 abgeschlossen: robuste Wiederaufnahme fuer `von eben`

Der offene D0.8-Rest ist jetzt geschlossen.

Neu:

- [turn_understanding.py](/home/fatih-ubuntu/dev/timus/orchestration/turn_understanding.py)
  - zeitverankerte Rueckfragen mit frischem Session-Kontext werden nicht mehr als nackter `new_task` gelesen
  - `historical_recall_requested` + frische User-/Assistant-Turns -> `followup`
  - dadurch wird derselbe Themenfaden robuster wiederaufgenommen
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - wenn `topic_history` fuer `von eben` noch leer ist, baut Timus jetzt einen historischen Themenanker aus den frischen Session-Turns
  - Fallback-Quellen:
    - `recent_user_turn`
    - bei `was hast du eben gesagt` auch `recent_assistant_turn`
  - der historische Slot ist damit nicht mehr davon abhaengig, dass der vorige freie Turn schon komplett in `topic_history` gelandet ist
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
  - `historical_topic_attached` traegt jetzt auch `fallback_source`

Tests:

- [test_turn_understanding.py](/home/fatih-ubuntu/dev/timus/tests/test_turn_understanding.py)
  - neuer Fall fuer `von eben` + frischer Recent-User-Turn
- [test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
  - Fallback auf `recent_user_turn`
  - Fallback auf `recent_assistant_turn`

Verifikation:

- `python -m py_compile orchestration/turn_understanding.py orchestration/meta_orchestration.py server/mcp_server.py tests/test_turn_understanding.py tests/test_meta_orchestration.py` -> gruen
- `pytest -q tests/test_turn_understanding.py tests/test_meta_orchestration.py tests/test_topic_state_history.py tests/test_topic_state_history_hypothesis.py tests/test_topic_state_history_contracts.py tests/test_conversation_state.py tests/test_autonomy_observation_d0.py tests/test_android_chat_language.py` -> `118 passed`

Runtime:

- `timus-mcp.service` und `timus-dispatcher.service` wurden am **8. April 2026, 14:09:02 CEST** neu geladen
- direkter Smoke nach dem Reload:
  - Query: `weisst du noch was wir eben ueber archivregeln besprochen hatten`
  - frischer Session-Turn: `Lass uns ueber Langzeitgedaechtnis und Archivregeln bei Timus sprechen.`
  - Ergebnis:
    - `dominant_turn_type = followup`
    - `response_mode = summarize_state`
    - `historical_topic_selection.fallback_source = recent_user_turn`
    - `historical_topic_memory` im Bundle vorhanden

Status:

- D0.8 abgeschlossen
- D0.9 gestartet

## 2026-04-08 D0.9 erster Runtime-Slice: Specialist Context Propagation

Neu:

- [orchestration/specialist_context.py](/home/fatih-ubuntu/dev/timus/orchestration/specialist_context.py)
- [agent/agents/meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [orchestration/meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- [orchestration/orchestration_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/orchestration_policy.py)
- [agent/agents/executor.py](/home/fatih-ubuntu/dev/timus/agent/agents/executor.py)
- [agent/agents/research.py](/home/fatih-ubuntu/dev/timus/agent/agents/research.py)
- [agent/agents/visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
- [agent/agents/system.py](/home/fatih-ubuntu/dev/timus/agent/agents/system.py)
- [tests/test_meta_handoff.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_handoff.py)
- [tests/test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)

Inhalt:

- `classify_meta_task(...)` erzeugt jetzt einen normalisierten `specialist_context_seed`
- der Dispatcher traegt diesen Seed in den Meta-Handoff
- `MetaAgent` haelt den aktiven Orchestrierungs-Handoff jetzt auch fuer nicht-rezeptartige Meta-Laeufe vor
- strukturierte Specialist-Handoffs und Rezept-/Recovery-Stages tragen jetzt `specialist_context_json`
- `executor`, `research`, `visual` und `system` rendern den propagierten Spezialistenkontext jetzt sichtbar im Arbeitskontext
- der erste D0.9-Vertrag umfasst:
  - `current_topic`
  - `active_goal`
  - `open_loop`
  - `next_expected_step`
  - `turn_type`
  - `response_mode`
  - `user_preferences`
  - `recent_corrections`
  - `signal_contract`

Verifikation:

- `python -m py_compile ...` gruen
- `pytest -q tests/test_meta_handoff.py tests/test_specialist_handoffs.py` -> `16 passed`
- `pytest -q tests/test_meta_orchestration.py tests/test_android_chat_language.py tests/test_meta_handoff.py tests/test_specialist_handoffs.py` -> `101 passed`

Status:

- D0.9 ist als erster echter Runtime-Slice gestartet
- offen fuer den naechsten Slice:
  - tiefere Nutzung des Kontexts in Specialist-Entscheidungen und Toolwahl
  - weitere Spezialisten ausserhalb des ersten Kernrings

## 2026-04-08 D0.9 zweiter Runtime-Slice: Context Alignment + Return Signals

Neu:

- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
- [orchestration/specialist_context.py](/home/fatih-ubuntu/dev/timus/orchestration/specialist_context.py)
- [tests/test_specialist_context_runtime.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_context_runtime.py)

Inhalt:

- propagierter Spezialistenkontext bekommt jetzt eine gemeinsame Alignment-Heuristik
- `executor`, `research`, `visual` und `system` sehen bei schwacher Kontextverankerung jetzt eine explizite Kontextwarnung im Handoff-Kontext
- `AgentRegistry.delegate(...)` leitet daraus erstmals strukturierte Specialist-Ruecksignale im echten Delegationspfad ab:
  - `context_mismatch`
  - `needs_meta_reframe`
- diese Signale landen jetzt in:
  - `metadata.specialist_return_signal`
  - `metadata.specialist_context_alignment`
  - C4-Transportereignissen mit `kind=context_mismatch` bzw. `kind=needs_meta_reframe`

Verifikation:

- `python -m py_compile ...` gruen
- `pytest -q tests/test_specialist_context_runtime.py tests/test_specialist_handoffs.py tests/test_meta_handoff.py` -> `18 passed`
- `pytest -q tests/test_meta_orchestration.py tests/test_android_chat_language.py tests/test_meta_handoff.py tests/test_specialist_handoffs.py tests/test_specialist_context_runtime.py tests/test_c4_longrunner_runtime.py tests/test_delegation_hardening.py` -> `116 passed`

Status:

- D0.9 ist jetzt ueber reine Kontextpropagierung hinaus im Delegations-Rueckweg angekommen
- offen fuer den naechsten Slice:
  - weitere agentenseitige Signalspezialfaelle ausserhalb des ersten Kernrings
  - tiefere kontextabhaengige Tool- und Strategieanpassung in den Spezialisten

## 2026-04-08 D0.9 dritter Runtime-Slice: Agent-side Signals + First Behavior Guard

Neu:

- [orchestration/specialist_context.py](/home/fatih-ubuntu/dev/timus/orchestration/specialist_context.py)
- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
- [agent/agents/executor.py](/home/fatih-ubuntu/dev/timus/agent/agents/executor.py)
- [agent/agents/research.py](/home/fatih-ubuntu/dev/timus/agent/agents/research.py)
- [agent/agents/visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
- [agent/agents/system.py](/home/fatih-ubuntu/dev/timus/agent/agents/system.py)
- [tests/test_specialist_context_runtime.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_context_runtime.py)
- [tests/test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)

Inhalt:

- Spezialisten haben jetzt ein erstes explizites Signal-Protokoll:
  - `Specialist Signal: context_mismatch`
  - `Specialist Signal: needs_meta_reframe`
- `AgentRegistry` erkennt diese expliziten Signale jetzt direkt und behandelt sie als `partial`
- explizite Signalsessions werden jetzt in den Delegations-Metadaten sichtbar:
  - `specialist_return_signal`
  - `specialist_signal_source = agent`
  - `specialist_context_alignment`
- `executor`, `research`, `visual` und `system` erzeugen bei starkem Kontextbruch jetzt direkt `needs_meta_reframe`
- erster echter kontextabhaengiger Behavior-Guard:
  - `executor` blockt Aktions-Handoffs wie `simple_live_lookup` jetzt aktiv, wenn der propagierte Meta-Modus `summarize_state` dazu im Widerspruch steht

Verifikation:

- `python -m py_compile ...` gruen
- `pytest -q tests/test_specialist_context_runtime.py tests/test_specialist_handoffs.py tests/test_meta_handoff.py` -> `21 passed`
- `pytest -q tests/test_meta_orchestration.py tests/test_android_chat_language.py tests/test_meta_handoff.py tests/test_specialist_handoffs.py tests/test_specialist_context_runtime.py tests/test_c4_longrunner_runtime.py tests/test_delegation_hardening.py` -> `119 passed`

Status:

- D0.9 hat jetzt nicht nur propagierten Kontext und heuristische Ruecksignale, sondern erste bewusst erzeugte Specialist-Signale
- offen fuer den naechsten Slice:
  - tiefere kontextabhaengige Tool-/Strategiewahl in `research`, `visual`, `system`
  - weitere explizite Signalszenarien ausserhalb des ersten Kernrings

## 2026-04-08 D0.9 vierter Runtime-Slice: Specialist Strategy Guards

Neu:

- [agent/agents/research.py](/home/fatih-ubuntu/dev/timus/agent/agents/research.py)
- [agent/agents/visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
- [agent/agents/system.py](/home/fatih-ubuntu/dev/timus/agent/agents/system.py)
- [tests/test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
- [PHASE_D0_META_CONTEXT_STATE_PLAN.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D0_META_CONTEXT_STATE_PLAN.md)

Inhalt:

- `research` blockt jetzt explizit leichte Lookup-Handoffs wie `simple_live_lookup`, wenn sie faelschlich im Deep-Research-Pfad landen
- `research` haengt bei uebergebenen `source_urls`, vorhandenem `captured_context` und knappen/quellengetriebenen Nutzerpraeferenzen jetzt explizite Strategiehinweise an
- `visual` blockt jetzt echte UI-/Browser-Aktions-Handoffs, wenn propagierter `response_mode=summarize_state` dazu im Widerspruch steht
- `system` hat jetzt einen direkten `summarize_state`-Pfad fuer Service-/Status-Handoffs ohne LLM-Runde

Verifikation:

- `python -m py_compile ...` gruen
- `pytest -q tests/test_specialist_handoffs.py tests/test_specialist_context_runtime.py tests/test_meta_handoff.py` -> `24 passed`
- `pytest -q tests/test_meta_orchestration.py tests/test_android_chat_language.py tests/test_meta_handoff.py tests/test_specialist_handoffs.py tests/test_specialist_context_runtime.py tests/test_c4_longrunner_runtime.py tests/test_delegation_hardening.py` -> `122 passed`

Status:

- D0.9 greift jetzt nicht mehr nur beim Handoff und im Ruecksignal, sondern in ersten echten Specialist-Entscheidungen
- offen fuer den naechsten Slice:
  - feinere Tool-/Priorisierungswahl innerhalb der Spezialisten
  - weitere explizite Signalszenarien ausserhalb des ersten Kernrings

## 2026-04-08 D0.9 fuenfter Runtime-Slice: Specialist Prioritization Paths

Neu:

- [agent/agents/research.py](/home/fatih-ubuntu/dev/timus/agent/agents/research.py)
- [agent/agents/visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
- [agent/agents/system.py](/home/fatih-ubuntu/dev/timus/agent/agents/system.py)
- [tests/test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
- [PHASE_D0_META_CONTEXT_STATE_PLAN.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D0_META_CONTEXT_STATE_PLAN.md)

Inhalt:

- `research` leitet jetzt aus Handoff und Nutzerpraeferenzen eine echte Kontext-Policy ab:
  - `source_first`
  - `compact_mode`
  - `suppress_blackboard`
  - `suppress_curiosity`
- `research` nutzt diese Policy jetzt im echten Kontextaufbau, statt nur weitere Strategiehinweise zu rendern
- `visual` waehlt jetzt explizit zwischen `structured_navigation` und `vision_first`
- `visual` kann damit text-/ocr-lastige Faelle direkt im Vision-Pfad halten, auch wenn ein Browser-Handoff vorhanden ist
- `system` waehlt jetzt gezielte Snapshot-Plaene mit `preferred_service` und `compact`, statt immer denselben Voll-Snapshot zu erzeugen

Verifikation:

- `python -m py_compile ...` gruen
- `pytest -q tests/test_specialist_handoffs.py tests/test_specialist_context_runtime.py tests/test_meta_handoff.py` -> `28 passed`
- `pytest -q tests/test_meta_orchestration.py tests/test_android_chat_language.py tests/test_meta_handoff.py tests/test_specialist_handoffs.py tests/test_specialist_context_runtime.py tests/test_c4_longrunner_runtime.py tests/test_delegation_hardening.py` -> `126 passed`

Status:

- D0.9 hat jetzt neben Kontextpropagierung, Ruecksignalen und Guards auch erste echte Priorisierungspfade in `research`, `visual` und `system`
- offen fuer den naechsten Slice:
  - Live-Nachweis fuer diese Priorisierungspfade im laufenden System
  - Abschluss-/Eval-Slice mit sauberer Restabgrenzung zu Phase D

## 2026-04-08 D0.9 sechster Abschluss-Slice: Eval + Specialist Observability

Neu:

- [orchestration/specialist_context_eval.py](/home/fatih-ubuntu/dev/timus/orchestration/specialist_context_eval.py)
- [orchestration/autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
- [agent/agents/research.py](/home/fatih-ubuntu/dev/timus/agent/agents/research.py)
- [agent/agents/visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
- [agent/agents/system.py](/home/fatih-ubuntu/dev/timus/agent/agents/system.py)
- [tests/test_specialist_context_eval.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_context_eval.py)
- [tests/test_autonomy_observation_d09.py](/home/fatih-ubuntu/dev/timus/tests/test_autonomy_observation_d09.py)
- [PHASE_D0_META_CONTEXT_STATE_PLAN.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D0_META_CONTEXT_STATE_PLAN.md)

Inhalt:

- D0.9 hat jetzt ein eigenes ausfuehrbares Eval-Set fuer:
  - `research` Kontext-Policy
  - `visual` Strategieauswahl
  - `system` Snapshot-Planung
  - den Specialist-Signalvertrag
- die Autonomy-Observation hat jetzt einen eigenen D0.9-Block `specialist_context`
- `agent_registry` emittiert jetzt `specialist_signal_emitted`
- `research`, `visual` und `system` emittieren jetzt `specialist_strategy_selected`

Verifikation:

- `python -m py_compile ...` gruen
- `pytest -q tests/test_specialist_context_eval.py tests/test_autonomy_observation_d09.py tests/test_specialist_handoffs.py tests/test_specialist_context_runtime.py tests/test_meta_handoff.py` -> `32 passed`
- `pytest -q tests/test_meta_orchestration.py tests/test_android_chat_language.py tests/test_meta_handoff.py tests/test_specialist_handoffs.py tests/test_specialist_context_runtime.py tests/test_specialist_context_eval.py tests/test_autonomy_observation_d0.py tests/test_autonomy_observation_d09.py tests/test_c4_longrunner_runtime.py tests/test_delegation_hardening.py` -> `132 passed`

Status:

- D0.9 ist damit im Repo-/Test-Scope abgeschlossen
- offen bleibt nur noch ein separater Live-Reload fuer den laufenden Prozess, falls der neue Stand sofort produktiv geladen werden soll
- D0 insgesamt ist damit funktional abgeschlossen; der naechste groessere Block ist Phase D
## 2026-04-09 - Phase D1.1/D1.2 gemeinsamer Auth-Vertrag gestartet

- Neues gemeinsames Laufzeitmodul [approval_auth_contract.py](/home/fatih-ubuntu/dev/timus/orchestration/approval_auth_contract.py) fuer:
  - `approval_required`
  - `auth_required`
  - `awaiting_user`
  - `challenge_required`
- Der bestehende Social-Auth-Wall-Pfad in [client.py](/home/fatih-ubuntu/dev/timus/tools/social_media_tool/client.py) liefert jetzt schon den normalisierten Phase-D-Workflow-Vertrag statt einer reinen Ad-hoc-Payload.
- Der Browser-Blockerpfad in [tool.py](/home/fatih-ubuntu/dev/timus/tools/browser_tool/tool.py) liefert bei Cloudflare/CAPTCHA jetzt `challenge_required` mit `workflow_id`, `challenge_type` und `user_action_required` statt nur `blocked_by_security`.
- Der Executor propagiert normalisierte Auth-/User-Action-Blocker jetzt mit `workflow_id`, `workflow_kind`, `service`, `reason`, `approval_scope`, `resume_hint` und `challenge_type`, ohne den bestehenden C4-Blockerpfad zu brechen.
- Fokus dieses ersten D-Slices:
  - gemeinsamer Vertrag zuerst
  - produktive `auth_required`- und `challenge_required`-Pfade daran angebunden
  - noch kein echter Login-Flow

## 2026-04-10 - D4b Haertung: verifizierte Auth-Erkennung + layoutsichere URL-Eingabe

- [agent/agents/visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
- [tools/mouse_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/mouse_tool/tool.py)
- [tests/test_specialist_handoffs.py](/home/fatih-ubuntu/dev/timus/tests/test_specialist_handoffs.py)
- [tests/test_mouse_tool_text_entry.py](/home/fatih-ubuntu/dev/timus/tests/test_mouse_tool_text_entry.py)
- [docs/PHASE_D_APPROVAL_AUTH_PREP.md](/home/fatih-ubuntu/dev/timus/docs/PHASE_D_APPROVAL_AUTH_PREP.md)

Inhalt:

- `visual` kann sichtbare authentische Zustände jetzt auch über `analyze_screen_verified` erkennen, wenn die rohe OCR zu dünn ist.
- Der D4b-Loginpfad akzeptiert damit vorhandene GitHub-/Service-Session-Zustände robuster als funktional erfüllten Login-Schritt.
- Der Desktop-Eingabepfad behandelt URL- und layoutkritischen Text jetzt konsequent als Clipboard-Eingabe.
- Für solche Texte gibt es keinen stillen Fallback mehr auf direktes Tippen; wenn Clipboard scheitert, bricht die Eingabe jetzt hart und sichtbar ab.
- Damit verschwindet der Fehler `https:77github.com7login`, der durch deutsches Keyboard-Layout im Key-by-Key-Fallback entstehen konnte.
- Der Dispatcher erkennt jetzt auch natürlichere D4b-Login-Formulierungen mit Chrome und Passwortmanager als `visual_login`, statt sie über `fallback_empty_decision` an `meta` zu verlieren.

Verifikation:

- `python -m py_compile tools/mouse_tool/tool.py tests/test_mouse_tool_text_entry.py`
- `pytest -q tests/test_mouse_tool_text_entry.py tests/test_visual_improvements.py` -> `24 passed`
- fokussierter D4b-/Login-Ring inkl. Verified-Vision-Fallback -> `84 passed`

Status:

- der Fix ist lokal live geladen und `/health` wieder grün
- live bestätigt ist jetzt auch:
  - `Bitte melde mich in Chrome bei GitHub an und nutze den Passwortmanager.`
  - route -> `visual_login`
- offen bleibt nur noch der breitere D4b-End-to-End-Nachweis auf einer sauberen Chrome-Loginmaske und ein schnellerer technischer Abschluss im langen Visual-Pfad

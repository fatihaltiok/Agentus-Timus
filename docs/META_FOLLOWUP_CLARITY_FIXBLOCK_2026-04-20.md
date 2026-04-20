## Meta Follow-up Clarity Fixblock

### Problem

Meta verliert bei mehrschichtigen Gespraechen den roten Faden, obwohl das Thema im
Gespräch schon klar ist. Der Fehler sitzt nicht in Telegram selbst, sondern in
Timus-Kernpfaden:

- generische Assistentenfragen wie `Was brauchst du?` werden als
  `pending_followup_prompt` gespeichert und verdrängen das eigentliche Ziel
- query-fremde `preference_memory` wie `Twilio` leakt in fachlich andere Themen
- kurze oder implizite Folgefragen werden nicht hart genug an `active_topic` und
  `active_goal` gebunden
- Meta behandelt Folgefragen zu oft wie neue, vage Turns statt wie thematische
  Fortsetzungen

### Ziel

Meta soll pro Turn klar priorisieren:

1. aktuelle Nutzerfrage
2. aktives Thema und aktives Ziel
3. nur thematisch passendes Langzeitgedaechtnis
4. keine generischen Rueckfragen als Open Loop

### Fixblock

#### 1. Follow-up Prompt Hygiene

- nur konkrete, handlungsleitende Rueckfragen duerfen als
  `pending_followup_prompt` gespeichert werden
- generische Rueckfragen wie `Was brauchst du?` oder `Wie kann ich helfen?`
  duerfen weder `open_loop` noch `next_expected_step` ueberschreiben

#### 2. Topic Continuity First

- kurze Folgefragen mit Referenzsprache wie `dort`, `da`, `dabei`, `darueber`
  werden an `active_topic` und `active_goal` gebunden, wenn im State ein klarer
  Themenanker vorhanden ist
- bei Folgefragen darf ein bestehendes Thema nicht durch generische
  Assistentenreste oder query-fremde Memory-Hits ersetzt werden

#### 3. Domain-Gated Preference Memory

- `preference_memory` darf nur dann in den Meta-Kontext, wenn sie thematisch zur
  aktuellen Frage oder zum aktiven Ziel passt
- globale oder alte Preferences ohne Domain-Overlap werden fuer den Turn
  suppressiert

#### 4. Meta Context Bundle Tightening

- `meta_context_bundle` priorisiert bei Folgefragen:
  - `current_query`
  - `conversation_state`
  - `open_loop`
  - relevante `recent_user_turn`
  - relevante `historical_topic_memory`
- query-fremde `preference_memory`, `assistant_fallback_context` und
  irrelevante `topic_memory` werden aktiv ausgefiltert

### Erfolgskriterien

- Kanada-Folgefragen bleiben bei `Kanada`
- generische Rueckfragen werden nicht mehr als Open Loop gespeichert
- Twilio-/Telefonie-Praeferenzen tauchen bei Kanada-/Auswanderungsfragen nicht
  mehr im Meta-Bundle auf
- Meta klassifiziert implizite Folgefragen stabiler als `followup` statt als
  entkoppelten `new_task`

### Status

- umgesetzt im Kernpfad
- Fokus nicht auf Telegram-spezifischem Transport, sondern auf Timus-Core:
  - `conversation_state`
  - `mcp_server`
  - `turn_understanding`
  - `meta_orchestration`
  - `meta_response_policy`
  - `preference_instruction_memory`
  - `meta_clarity_contract`

### Implementierte Schwerpunkte

- generische Rueckfragen wie `Was brauchst du?` werden nicht mehr als
  `pending_followup_prompt` konserviert
- referentielle Folgefragen wie `wie kann ich dort arbeiten` oder
  `koennte ich da fuss fassen` werden mit bestehendem Themenanker robuster als
  `followup` behandelt
- query-fremde Ziel-/Telefonie-Praeferenzen werden bei fachlich anderen Themen
  ueber Domain-Gating aus dem Meta-Kontext gehalten
- `resume_open_loop` behaelt bei echtem Themenanker seinen stateful Charakter und
  wird nicht unnötig durch `open_loop_not_reliable` entwertet
- der Klarheitsvertrag laesst fuer stateful Folgefragen wieder relevante
  `topic_memory` zu

### Verifikation

- `python -m py_compile orchestration/meta_clarity_contract.py orchestration/meta_response_policy.py orchestration/preference_instruction_memory.py orchestration/meta_orchestration.py`
- `pytest -q tests/test_preference_instruction_memory.py tests/test_meta_orchestration.py` -> `72 passed`
- `pytest -q tests/test_conversation_state.py tests/test_meta_orchestration.py tests/test_preference_instruction_memory.py tests/test_meta_response_policy.py tests/test_dispatcher_self_status_routing.py tests/test_agent_loop_fixes.py` -> `158 passed`

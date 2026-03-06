# Tagesbericht — 2026-03-06
**Session:** Tagesarbeit | **Version:** Timus v4.2 | **Branch:** main

---

## Was wurde heute gemacht

### M16 — Echte Lernfähigkeit (Feedback Loop + Qdrant Migration)

Timus hatte bisher keine echte Lernfähigkeit: Aktionen wurden ausgeführt,
aber kein Signal hat das Verhalten dauerhaft verändert. `behavior_hooks` waren
plain Strings ohne Gewicht. ChromaDB lief auf prototype-level ohne
Payload-Filter oder Production-Support.

M16 schließt diese Lücke in 5 Phasen.

---

### Phase 1 — Telegram Feedback Channel

**Ziel:** Jede Timus-Aktion bekommt Feedback-Buttons. Signale werden gespeichert.

**`orchestration/feedback_engine.py`** (neu):
- `FeedbackEngine`-Klasse mit SQLite-Backend (`feedback_events`-Tabelle)
- `record_signal(action_id, signal, hook_names, context)` — signal ∈ `{positive, negative, neutral}`
- `get_hook_stats(hook_name)` → `{pos, neg, neutral, weight: float}`
- `get_recent_events(limit)` — letzte N Events abrufbar
- `process_pending()` — Heartbeat-Hook zählt heutige Events
- Singleton `get_feedback_engine()` für alle Module

**`utils/telegram_notify.py`** (erweitert):
- Neue Funktion `send_with_feedback(msg, action_id, hook_names)`:
  - Baut `InlineKeyboardMarkup` mit 3 Buttons: 👍 👎 🤷
  - Callback-Data als JSON: `{"fb": "positive", "aid": action_id, "hooks": [...]}`
  - Vollständige Bot-Lifecycle-Verwaltung (open/close)

**`gateway/telegram_gateway.py`** (erweitert):
- `handle_callback_query(update, context)` — neuer Handler für InlineKeyboard-Klicks:
  - Parsed JSON Callback-Data
  - Ruft `FeedbackEngine.record_signal()` auf
  - Antwortet mit `answerCallbackQuery` (Telegram ACK + Emoji-Bestätigung)
- `CallbackQueryHandler` registriert, `allowed_updates` um `callback_query` erweitert

---

### Phase 2 — Weighted Behavior Hooks

**Ziel:** behavior_hooks bekommen Gewichtungen; Feedback ändert die Weights dauerhaft.

**`memory/soul_engine.py`** (erweitert):

Neue `WeightedHook`-Dataclass:
```python
@dataclass
class WeightedHook:
    text: str
    weight: float = 1.0       # Feedback-Gewicht
    feedback_count: int = 0   # Anzahl erhaltener Signale

    def apply_feedback(signal)  # weight ± FEEDBACK_DELTA, clamp [0.05, 2.0]
    def decay(rate=0.97)        # Täglicher Decay Richtung 1.0
    def is_active(threshold)    # True wenn weight ≥ threshold
```

Neue Soul Engine Methoden:
- `get_weighted_hooks()` — liest `weighted_hooks` aus SOUL.md (Fallback: `behavior_hooks`)
- `set_weighted_hooks(hooks)` — schreibt zurück mit weight + feedback_count
- `apply_hook_feedback(hook_name, signal)` — sucht Hook per Teilstring, wendet Signal an
- `decay_hooks()` — alle weights ×0.97 täglich, gibt Anzahl geänderter Hooks zurück
- `get_active_hooks(threshold=0.3)` — filtert inaktive Hooks raus

---

### Phase 3 — Qdrant Migration

**Ziel:** ChromaDB durch Qdrant ersetzt — lokal, kein Cloud-Account, Rust-Core, 10–50× schneller.

**`memory/qdrant_provider.py`** (neu):
- Drop-in für ChromaDB-Interface (duck typing): `add()`, `query()`, `get()`, `delete()`, `count()`
- Named Vectors: `"content"` (sentence-transformers Embedding)
- Payload-Filter via `_build_filter()`: `$gte`, `$lte`, `$in`, `$and` unterstützt
- `_to_qdrant_id()`: beliebige Strings → deterministische UUIDs (uuid5)
- Fallback auf Null-Vektor wenn Embedding-Provider nicht verfügbar

**`scripts/migrate_chromadb_to_qdrant.py`** (neu):
- Liest alle ChromaDB-Einträge batch-weise (100 pro Batch)
- Schreibt in Qdrant mit gleicher Payload-Struktur
- Fortschrittsanzeige + Validierung (count vorher == count nachher)
- `--dry-run` Modus zum sicheren Testen

**`memory/memory_system.py`** (erweitert):
- Backend-Switch: `MEMORY_BACKEND=qdrant` → `QdrantProvider`, sonst ChromaDB
- Nahtloser Fallback auf ChromaDB bei Qdrant-Fehler

---

### Phase 4 — Curiosity Engine + Session Reflection

**Ziel:** Feedback-History fließt in adaptive Topic-Auswahl und automatische Hook-Updates ein.

**`orchestration/curiosity_engine.py`** (erweitert):
- `_topic_scores: dict[str, float]` — Feedback-gewichtete Topic-Scores (init: 1.0)
- `update_topic_score(topic, signal)` — positiv: +0.1, negativ: −0.1, clamp [0.1, 3.0]
- `_decay_stale_topic_scores()` — Topics ohne Feedback > 7 Tage → score ×0.9
- `_load_topic_scores_from_feedback()` — Initialisierung aus FeedbackEngine-History
- `_extract_topics()` nutzt jetzt `topic_scores` als Multiplikator (Feedback-bevorzugte Topics öfter)

**`orchestration/session_reflection.py`** (erweitert):
- `_apply_reflection_to_hooks(summary)` — nach jeder Session-Reflexion:
  - `what_worked[:3]` → `FeedbackEngine.record_signal(signal="positive")`
  - `what_failed[:3]` → `FeedbackEngine.record_signal(signal="negative")`
  - `soul.apply_hook_feedback()` für thematisch passende Hooks
- Nur aktiv wenn `AUTONOMY_M16_ENABLED=true`

---

### Phase 5 — Integration, Lean, Verifikation

**`orchestration/autonomous_runner.py`** (erweitert):
- `_m16_feature_enabled()` — Feature-Flag-Funktion
- M16 FeedbackEngine wird bei Start initialisiert
- Heartbeat: `process_pending()` bei jedem Tick
- Heartbeat: `decay_hooks()` täglich (alle 96 Ticks = 24h)

**`lean/CiSpecs.lean`** — +9 neue Theoreme (23 gesamt, alle via `by omega`):
- `m16_hook_weight_lower/upper` — Weight ∈ [0, 100] nach Feedback
- `m16_decay_monotone` — Decay-Ergebnis ≤ ursprüngliches Gewicht
- `m16_topic_score_lower/upper` — Topic-Score ∈ [0, 100]
- `m16_negative_signal` — negatives Signal senkt Score streng
- `m16_feedback_count` — Count ≥ 0 nach jedem Signal
- `m16_qdrant_limit_positive` — Fetch-Limit immer ≥ 1
- `m16_neutral_noop` — 🤷 verändert Weight nicht

**`tools/lean_tool/tool.py`** — +2 Mathlib-Specs (12 gesamt):
- `m16_weighted_avg_in_bounds` — pos/(pos+neg) ∈ [0,1]
- `m16_feedback_ratio` — pos_rate + neg_rate ≤ 1

---

### M16 — Aktivierung (Phase 0: send_with_feedback live)

**Ziel:** M16 nicht nur implementiert, sondern wirklich eingeschaltet. Feedback-Buttons erscheinen ab sofort bei Ambient-Context und Curiosity-Pushes.

- `AUTONOMY_M16_ENABLED=true` in `.env` gesetzt
- `orchestration/ambient_context_engine.py` + `orchestration/curiosity_engine.py`: Telegram-Nachrichten gehen jetzt über `send_with_feedback()` statt `send_telegram()`
- Jede autonome Push-Aktion bekommt 👍 👎 🤷 Buttons — Signale fließen direkt in `FeedbackEngine` und `WeightedHooks` ein

---

### M13 — Eigene Tool-Generierung

**Ziel:** Timus erkennt wenn ihm ein Tool fehlt und generiert es selbst via Developer-Agent. AST-geprüft, Telegram-reviewed, per importlib aktiviert.

**Neue Dateien:**
- `orchestration/tool_generator_engine.py` — Kern-Engine: LLM-Generierung, AST-Sicherheitscheck, importlib-Aktivierung
- `tools/tool_generator_tool/tool.py` — MCP-Tool: `generate_tool`, `list_generated_tools`, `activate_tool`
- `tests/test_m13_tool_generator.py` — 28/28 Tests grün
- `verify_m13.py` — 50/50 Checks grün

**Sicherheits-Layer:**
- AST-Check blockiert `eval`, `exec`, `__import__` im generierten Code
- `MAX_CODE_LENGTH=5000` — kein unbegrenzter Code
- Telegram-Review [✅/❌] vor Aktivierung (Stufe 1)
- `gateway/telegram_gateway.py`: `tool_approve`/`tool_reject` Callbacks
- `autonomous_runner.py`: `_m13_feature_enabled()`

**Lean:** Theoreme 26 (`code_length_bound`) + 27 (`tool_approval_guard`), gesamt 27 Theoreme

**ENV:**
```env
AUTONOMY_M13_ENABLED=false
```

---

### M14 — E-Mail-Autonomie

**Ziel:** Timus entscheidet selbst wann E-Mails sinnvoll sind. Policy-Layer mit Whitelist + Topic-Klassen + Confidence-Schwelle schützt vor ungewollten Aktionen.

**Neue Dateien:**
- `orchestration/email_autonomy_engine.py` — Entscheidungslogik: Whitelist-Guard, Topic-Check, Confidence-Threshold
- `utils/smtp_email.py` — SMTP-Backend (Dual-Backend: smtp | msgraph)
- `tools/email_autonomy_tool/tool.py` — MCP-Tool: `send_autonomous_email`, `get_email_queue`
- `tests/test_m14_email_autonomy.py` — 27/27 Tests grün

**Flow:**
1. Timus entscheidet: E-Mail sinnvoll? → Whitelist + Topic + Confidence prüfen
2. Entwurf → Telegram-Bestätigung [✅/❌] (Stufe 1)
3. Nach Bestätigung: senden via SMTP oder Microsoft Graph

**Lean:** Theoreme 24 (`whitelist_guard`) + 25 (`confidence_threshold`)

**ENV:**
```env
AUTONOMY_M14_ENABLED=false
EMAIL_BACKEND=smtp
M14_EMAIL_WHITELIST=email@example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
```

---

### Canvas — Flow-Tab + Farbige Delegations-Strahlen

**Ziel:** Live-Diagramm im Canvas das zeigt wie Agenten kommunizieren. Wanderndes Licht entlang der Delegationspfade mit Status-Farben.

**`agent/agent_registry.py`:**
- `_delegation_sse_hook` jetzt auch bei `"completed"` und `"error"` — vorher nur `"running"`

**`server/canvas_ui.py`:**
- `BEAM_COLORS` — gelb (running), grün (completed), rot (error)
- `animateDelegationBeam(fromId, toId, status)` — alle 3 Canvas-Gradienten dynamisch coloriert
- `flashNode(agentId, status)` — Zielknoten leuchtet statusfarben auf
- `handleSSE` — ruft parallel `animateFlowBeam()` auf wenn Flow-Tab aktiv
- **Neuer Flow-Tab** mit vollständigem System-Hierarchie-Graph:
  - 23 Nodes: Telegram/Terminal → Dispatcher → MetaAgent → 11 Executor-Agenten + AutonomousRunner → 7 Autonomie-Motoren (M1/M3/M8/M13/M14/M15/M16)
  - dagre LR-Layout, Zoom-Controls (＋/－/Fit), Minimap, Drag+Wheel-Zoom
  - CDN: dagre@0.8.5 + cytoscape-dagre@2.5.0

---

## Ergebnisse

| Metrik | Wert |
|--------|------|
| Tests (pytest) — M16 | **78/78 grün** |
| verify_m16.py | **79/79 Checks grün** |
| Tests — M13 | **28/28 grün** |
| verify_m13.py | **50/50 Checks grün** |
| Tests — M14 | **27/27 grün** |
| Lean CiSpecs.lean | **27 Theoreme, 0 Fehler** |
| Mathlib-Specs | **12 Specs** |
| Neue Dateien gesamt | 14 |
| Modifizierte Dateien gesamt | 13 |

---

## Neue Dateien

| Datei | Beschreibung |
|-------|-------------|
| `orchestration/feedback_engine.py` | Feedback-Speicherung + Hook-Statistiken |
| `memory/qdrant_provider.py` | Qdrant Drop-in für ChromaDB |
| `scripts/migrate_chromadb_to_qdrant.py` | Einmalige Migration |
| `tests/test_m16_feedback.py` | 20 Tests: FeedbackEngine |
| `tests/test_m16_hooks.py` | 18 Tests: WeightedHook + SoulEngine |
| `tests/test_m16_qdrant.py` | 17 Tests: QdrantProvider |
| `tests/test_m16_integration.py` | 23 Tests: Curiosity + Reflexion |
| `verify_m16.py` | 79 automatische Checks |
| `orchestration/tool_generator_engine.py` | M13: LLM-Tool-Generierung + AST-Check |
| `tools/tool_generator_tool/tool.py` | M13: MCP-Interface |
| `tests/test_m13_tool_generator.py` | M13: 28 Tests |
| `verify_m13.py` | M13: 50 Checks |
| `orchestration/email_autonomy_engine.py` | M14: E-Mail-Entscheidungslogik |
| `utils/smtp_email.py` | M14: SMTP-Backend |
| `tools/email_autonomy_tool/tool.py` | M14: MCP-Interface |
| `tests/test_m14_email_autonomy.py` | M14: 27 Tests |

## Neue ENV-Flags

```env
# M16 — Lernfähigkeit
AUTONOMY_M16_ENABLED=true    # Heute aktiviert
M16_FEEDBACK_DELTA=0.15
M16_HOOK_MIN_WEIGHT=0.05
M16_HOOK_DECAY_RATE=0.97
MEMORY_BACKEND=chromadb      # chromadb oder qdrant
QDRANT_PATH=./data/qdrant_db
QDRANT_COLLECTION=timus_memory

# M13 — Tool-Generierung
AUTONOMY_M13_ENABLED=false

# M14 — E-Mail-Autonomie
AUTONOMY_M14_ENABLED=false
EMAIL_BACKEND=smtp
M14_EMAIL_WHITELIST=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
```

---

## Commits heute

| Hash | Beschreibung |
|------|-------------|
| `b10646d` | feat(v4.1): M16 aktivieren + M14 E-Mail-Autonomie + M13 Tool-Generierung |
| `26b8054` | chore: TIMUS_INVENTORY.md → docs/archive/ |
| `966991c` | docs: ARCHITECTURE.md anlegen (v4.1, vollständig) |
| `20be119` | feat(canvas): Flow-Tab + farbige Delegations-Strahlen (gelb/grün/rot) |

---

## Offene Aufgaben (Roadmap)

### 🔴 Sofort aktivierbar
- `MEMORY_BACKEND=qdrant` testen → Migration mit `migrate_chromadb_to_qdrant.py`
- `AUTONOMY_M13_ENABLED=true` + SMTP-Zugangsdaten → M14 live
- `TRIGGER_EVENING_ENABLED=true` → automatischer Tagesbericht um 20:00

### 🟡 Mittelfristig
- Demo-Video produzieren (M15 + M16 live zeigen: Timus erkennt selbst, bekommt Feedback, lernt)
- GitHub: CONTRIBUTING.md + Docker-Setup (damit jemand in 5 Min starten kann)
- HuggingFace Space mit Live-Demo

### 🟢 Niedrig
- Qdrant Cloud / externe SSD als Speicher-Erweiterung
- `TRIGGER_MORNING_ENABLED=true` → Morgen-Routine (E-Mail-Zusammenfassung 08:00)

---

## Stand Autonomie

| Milestone | Status |
|-----------|--------|
| M1–M7 Kern-Autonomie | ✅ live |
| M8 Session Reflection | ✅ implementiert (Flag: false) |
| M9 Agent Blackboard | ✅ live |
| M10 Proactive Triggers | ✅ implementiert (Flag: false) |
| M11 Goal Queue | ✅ live |
| M12 Self-Improvement | ✅ implementiert (Flag: false) |
| M13 Tool-Generierung | ✅ implementiert (Flag: false) |
| M14 E-Mail-Autonomie | ✅ implementiert (Flag: false) |
| M15 Ambient Context Engine | ✅ live |
| **M16 Echte Lernfähigkeit** | ✅ live (heute aktiviert) |

**Nächster Schritt:** Demo-Video — M15 + M16 gemeinsam zeigen (Timus erkennt selbst was zu tun ist, bekommt Feedback, lernt dauerhaft).

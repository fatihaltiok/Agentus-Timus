# Plan: Timus v4.3 — Optimierungen & Öffentlichkeit

**Datum:** 2026-03-06 | **Basis:** v4.2 (27 Lean-Theoreme, 27 Lean-Mathlib-Specs)

---

## Aktueller Stand (Ausgangspunkt)

```
Feature-Flags AKTIV:    M8 Reflection, M9 Blackboard, M10 Triggers, M11 Goals,
                        M12 Self-Improvement, M15 Ambient, M16 Feedback
Feature-Flags INAKTIV:  M13 Tool-Generierung, M14 E-Mail-Autonomie
Speicher-Backend:       ChromaDB (Qdrant implementiert, nicht aktiviert)
Lean:                   27 Theoreme (CiSpecs.lean), 12 Mathlib-Specs
Agenten-Upgrades:       Research, Developer, Visual, Meta, Communication → ausstehend
GitHub:                 kein Docker, kein CONTRIBUTING.md, kein ROADMAP.md
```

---

## Phasenübersicht

```
Phase 1 — M13 + M14 aktivieren          → Gate: 55 Tests + Lean 29 Theoreme
Phase 2 — Qdrant-Migration              → Gate: 17 Tests + Lean 31 Theoreme
Phase 3 — Agenten-Verbesserungen        → Gate: 40+ neue Tests + Lean 36 Theoreme
Phase 4 — GitHub / Docker / Öffentlich  → Gate: Docker Build-Test + Lean unverändert
```

---

## Phase 1 — M13 + M14 live schalten

### Ziel
M13 (Tool-Generierung) und M14 (E-Mail-Autonomie) vollständig aktivieren:
Feature-Flags setzen, SMTP-Zugangsdaten eintragen, Live-Verhalten im Telegram testen.

### Aufgaben

#### 1a — .env ergänzen

```env
# M13 — Tool-Generierung
AUTONOMY_M13_ENABLED=true

# M14 — E-Mail-Autonomie
AUTONOMY_M14_ENABLED=true
EMAIL_BACKEND=smtp
M14_EMAIL_WHITELIST=<deine-email>
M14_EMAIL_CONFIDENCE=0.85
M14_EMAIL_TOPIC_WHITELIST=research,alert,summary,bericht
SMTP_HOST=smtp.gmail.com      # oder eigener SMTP
SMTP_PORT=465
SMTP_USER=<user>
SMTP_PASSWORD=<app-password>  # Gmail: App-Passwort (nicht Account-Passwort)
IMAP_HOST=imap.gmail.com
```

#### 1b — Lean: 2 neue Theoreme (gesamt: 29)

```lean
-- 28. M14 SMTP-Retry-Bound: retry_count ≤ MAX_RETRIES → kein Overflow
-- Quelle: utils/smtp_email.py — Retry-Loop bei Verbindungsfehler
theorem m14_retry_bound (attempts max_retries : Int)
    (h : attempts ≤ max_retries) (hm : 0 < max_retries) :
    attempts < max_retries + 1 := by omega

-- 29. M13 Approval-Gate: status ≥ 1 (approved) ↔ aktivierbar
-- Quelle: orchestration/tool_generator_engine.py:activate
theorem m13_approved_activatable (status : Int) (h : 1 ≤ status) :
    0 < status := by omega
```

### Verifikations-Gate Phase 1

```bash
# 1. Bestehende Tests
pytest tests/test_m13_tool_generator.py -v     # 28/28 erwartet
pytest tests/test_m14_email_autonomy.py -v     # 27/27 erwartet

# 2. Lean
lean lean/CiSpecs.lean
# Erwartet: 29 Theoreme, 0 Fehler

# 3. Manueller Live-Test
# Chat: "Generiere ein Tool das Wetter für Berlin abruft"
# Erwartung: Telegram-Nachricht mit Code-Preview + [✅/❌]-Buttons
# Chat: "Sende eine Test-E-Mail an <whitelist-adresse>"
# Erwartung: Telegram-Bestätigung → nach ✅ → E-Mail landet im Postfach
```

**Checkpoint:** 55/55 Tests grün, 29 Lean-Theoreme, Telegram-Flow funktioniert → Commit + Push

---

## Phase 2 — Qdrant-Migration

### Ziel
ChromaDB durch Qdrant ersetzen. Alle bestehenden Gedächtnis-Einträge migrieren.
10–50× schnellere semantische Suche, Production-Level-Backend.

### Aufgaben

#### 2a — Migration ausführen

```bash
# Dry-Run zuerst (kein Schreiben)
python scripts/migrate_chromadb_to_qdrant.py --dry-run

# Wenn Dry-Run OK: echte Migration
python scripts/migrate_chromadb_to_qdrant.py

# Validierung: Anzahl vorher == nachher
# Script gibt aus: "Migriert: N Einträge. Qdrant count: N. ✅"
```

#### 2b — .env umstellen

```env
MEMORY_BACKEND=qdrant
QDRANT_PATH=./data/qdrant_db
QDRANT_COLLECTION=timus_memory
```

#### 2c — Lean: 2 neue Theoreme (gesamt: 31)

```lean
-- 30. Qdrant Migration Progress: migrated ≤ total (Fortschritt nie überschreitet Quelle)
-- Quelle: scripts/migrate_chromadb_to_qdrant.py — Batch-Loop
theorem qdrant_migration_progress (migrated total : Int)
    (h : migrated ≤ total) (ht : 0 ≤ total) :
    migrated ≤ total := by omega

-- 31. Qdrant Batch-Größe: batch_size > 0 → verarbeitbar (kein Leerlauf-Loop)
-- Quelle: migrate_chromadb_to_qdrant.py — BATCH_SIZE=100
theorem qdrant_batch_nonempty (batch_size : Int) (h : 0 < batch_size) :
    0 < batch_size := by omega
```

#### 2d — Fallback-Test
Wenn Qdrant-Client-Import fehlschlägt → automatisch zurück auf ChromaDB (bereits im Code).
Test: `QDRANT_PATH=/invalid/path` → Timus läuft weiter (ChromaDB-Fallback).

### Verifikations-Gate Phase 2

```bash
# 1. Qdrant-Tests
pytest tests/test_m16_qdrant.py -v             # 17/17 erwartet

# 2. Lean
lean lean/CiSpecs.lean
# Erwartet: 31 Theoreme, 0 Fehler

# 3. Funktions-Test
# Chat: "Was weißt du über Deep Research?"
# Erwartung: Antwort nutzt semantisches Gedächtnis (Qdrant-Backend)
# Log: "Qdrant Collection 'timus_memory' geladen" (kein "ChromaDB")

# 4. Performance-Vergleich (optional)
python -c "
from memory.qdrant_provider import QdrantProvider
import time
q = QdrantProvider()
print('Count:', q.count())
"
```

**Checkpoint:** 17/17 Tests, 31 Lean-Theoreme, Qdrant-Log bestätigt → Commit + Push

---

## Phase 3 — Agenten-Verbesserungen

### Ziel
5 Agenten gezielt verbessern. Jede Verbesserung hat eigene Tests und Lean-Verifikation.

---

### 3a — Research Agent: Source-Ranking + Duplikat-Filter

**Problem:** Mehrere Quellen mit gleichem Inhalt werden alle einbezogen.
Ranking bevorzugt nicht zwingend verlässlichere Quellen.

**Änderungen in `agent/agents/research.py`:**
- `_deduplicate_sources(sources)` — URL-Normalisierung + Cosine-Ähnlichkeit > 0.92 → Duplikat
- `_rank_sources(sources)` — Score aus: Domain-Autorität (arxiv/nature/github = +2),
  Aktualität (< 6 Monate = +1), Verifiziert (M16 positives Signal = +1)

**Neue Lean-Theoreme:**
```lean
-- 32. Research Dedup: unique_count ≤ total_count
theorem research_dedup_bound (unique total : Int)
    (h : unique ≤ total) (ht : 0 ≤ unique) :
    unique ≤ total := by omega

-- 33. Research Ranking Score: score ∈ [0, 10]
theorem research_ranking_score_bound (score : Int) :
    0 ≤ max 0 (min 10 score) ∧ max 0 (min 10 score) ≤ 10 := by omega
```

**Tests:** `tests/test_research_improvements.py` — 12 Tests:
- Duplikate aus gleicher Domain → genau 1 bleibt
- arxiv-URL → höchster Score
- Ranking-Reihenfolge stabil (deterministisch)

---

### 3b — Developer Agent: Auto-Test nach Code-Generierung

**Problem:** Developer-Agent schreibt Code, führt aber keine Tests aus.
Fehler fallen erst beim nächsten manuellen Run auf.

**Änderungen in `agent/agents/developer.py`:**
- Nach Code-Schreiben: `_auto_run_tests(changed_files)` — erkennt zugehörige Test-Datei
  (Pattern: `tools/X/tool.py` → `tests/test_X*.py`)
- Wenn Test-Datei vorhanden: `pytest <test_file> -x --timeout=30` via subprocess
- Ergebnis in Blackboard schreiben: `{"agent": "developer", "topic": "test_result", "key": filepath, "value": "passed|failed"}`
- Bei Fehler: Blackboard-Eintrag + Telegram-Benachrichtigung (nicht blockierend)

**MAX_TEST_ITERATIONS = 3** — verhindert Endlosschleife bei persistentem Fehler.

**Neue Lean-Theoreme:**
```lean
-- 34. Developer Auto-Test Attempts: attempts ≤ MAX_TEST_ITERATIONS
theorem developer_test_attempts_bound (attempts max_iter : Int)
    (h : attempts ≤ max_iter) (hm : 0 < max_iter) :
    attempts < max_iter + 1 := by omega
```

**Tests:** `tests/test_developer_improvements.py` — 10 Tests:
- Test-Datei gefunden → pytest ausgeführt
- Kein Test-File → graceful skip (kein Fehler)
- MAX_TEST_ITERATIONS wird respektiert
- Blackboard-Eintrag nach Test-Run vorhanden

---

### 3c — Visual Agent: Robusteres Retry-Verhalten

**Problem:** Fehlgeschlagene Klicks werden 1× wiederholt ohne Strategie.
Bei dynamischen UIs (Ladeanimation etc.) kommt es zu Endlosfehlern.

**Änderungen in `agent/agents/visual.py`:**
- `_click_with_retry(element, max_retries=3, backoff_ms=500)`:
  - Versuch 1: Direktklick
  - Versuch 2: Kurz warten (500ms) + erneut Screenshot + Koordinaten neu berechnen
  - Versuch 3: Alternative Klick-Methode (Koordinaten statt Element-Selektor)
  - Nach MAX_RETRIES: strukturierter Fehler mit Screenshot als Kontext
- `_wait_for_stable_screenshot(timeout_ms=2000)` — wartet bis 2 aufeinanderfolgende
  Screenshots > 95% identisch sind (Seite hat aufgehört zu laden)

**MAX_VISUAL_RETRIES = 3** (ENV: `VISUAL_MAX_RETRIES=3`)

**Neue Lean-Theoreme:**
```lean
-- 35. Visual Retry terminiert: retry_count ≤ MAX_RETRIES
theorem visual_retry_terminates (retry max_r : Int)
    (h : retry ≤ max_r) (hm : 0 < max_r) :
    retry < max_r + 1 := by omega
```

**Tests:** `tests/test_visual_improvements.py` — 8 Tests:
- Klick-Erfolg bei Versuch 1 → kein weiterer Versuch
- Klick-Fehler → korrekte Anzahl Retries
- MAX_RETRIES respektiert (kein 4. Versuch)

---

### 3d — Meta Agent: Bessere Decomposition

**Problem:** Komplexe Ziele (>5 Teilschritte) werden als flache Liste generiert
statt als priorisierte Hierarchie mit Abhängigkeiten.

**Änderungen in `agent/agents/meta.py`:**
- Neue Prompt-Sektion für Decomposition-Aufgaben:
  ```
  Wenn eine Aufgabe >3 Teilschritte hat:
  1. Identifiziere Abhängigkeiten (A muss vor B fertig sein)
  2. Gruppiere in max. 3 Phasen (Phase 1: Fundament, Phase 2: Kern, Phase 3: Finish)
  3. Priorisiere: P0 (blockiert alles) → P1 (Kern) → P2 (optional)
  4. Schätze Komplexität: S/M/L pro Teilschritt
  ```
- `MAX_DECOMPOSITION_DEPTH = 3` — max. 3 Hierarchieebenen

**Neue Lean-Theoreme:**
```lean
-- 36. Meta Decomposition Depth: depth ≤ MAX_DECOMPOSITION_DEPTH
theorem meta_decomposition_depth (depth max_depth : Int)
    (h : depth ≤ max_depth) (hm : 0 < max_depth) :
    depth < max_depth + 1 := by omega
```

**Tests:** `tests/test_meta_improvements.py` — 10 Tests:
- Aufgabe mit 2 Schritten → flache Liste (keine künstliche Hierarchie)
- Aufgabe mit 6 Schritten → 3-Phasen-Struktur
- Abhängigkeiten korrekt erkannt (B nach A)

---

### 3e — Communication Agent: E-Mail-Drafting-Flow

**Problem:** E-Mails werden direkt gesendet wenn der Agent dazu aufgefordert wird.
Kein Entwurf-Review, kein Bestätigungs-Loop.

**Änderungen in `agent/agents/communication.py`:**
- `_draft_email_with_review(to, subject, body)`:
  1. Entwurf generieren
  2. Telegram: Entwurf-Preview + [✅ Senden][✏️ Überarbeiten][❌ Abbrechen]
  3. Bei ✏️: Feedback-Text abwarten → Entwurf überarbeiten → zurück zu Schritt 2
  4. Bei ✅: senden via EMAIL_BACKEND
  5. Bei ❌: abbrechen ohne Versand
- Maximale Überarbeitungs-Runden: `MAX_DRAFT_REVISIONS = 3`

**Lean-Theoreme:** (nutzt bereits m14_retry_bound aus Phase 1 — kein neues nötig)

**Tests:** `tests/test_communication_improvements.py` — 10 Tests:
- Draft-Flow: Telegram-Nachricht enthält Entwurf + 3 Buttons
- Überarbeitungs-Counter respektiert MAX_DRAFT_REVISIONS
- Abbrechen → kein Versand

---

### Verifikations-Gate Phase 3

```bash
# 1. Alle neuen Tests
pytest tests/test_research_improvements.py -v    # 12/12
pytest tests/test_developer_improvements.py -v   # 10/10
pytest tests/test_visual_improvements.py -v      # 8/8
pytest tests/test_meta_improvements.py -v        # 10/10
pytest tests/test_communication_improvements.py -v # 10/10

# 2. Gesamter Test-Suite (Regression)
pytest tests/ -x --timeout=60 -q
# Erwartet: alle bestehenden Tests weiterhin grün

# 3. Lean
lean lean/CiSpecs.lean
# Erwartet: 36 Theoreme, 0 Fehler

# 4. Live-Verifikation
# Research: "Recherchiere aktuelle LLM-Paper" → Quellen ohne Duplikate, arxiv oben
# Developer: Code ändern → Test automatisch ausgeführt → Ergebnis in Blackboard
# Visual: Klick auf nicht-existierendes Element → 3 Retries → saubere Fehlermeldung
```

**Checkpoint:** 50/50 neue Tests, 36 Lean-Theoreme, 0 Regressionen → Commit + Push

---

## Phase 4 — GitHub aufräumen + Docker

### Ziel
Timus in 5 Minuten startbar für jeden Externen. Professionelle Repository-Struktur
die für Demo-Video, HuggingFace Space und Investoren-Gespräche taugt.

### Aufgaben

#### 4a — Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "-m", "server.mcp_server"]
```

#### 4b — docker-compose.yml

```yaml
version: "3.9"
services:
  timus:
    build: .
    ports: ["5000:5000"]
    env_file: .env
    volumes:
      - ./data:/app/data       # Qdrant-DB + SQLite persistent
      - ./memory:/app/memory   # Markdown-Gedächtnis persistent
    restart: unless-stopped

  # Optional: Qdrant als separater Service (für Produktion)
  # qdrant:
  #   image: qdrant/qdrant
  #   ports: ["6333:6333"]
  #   volumes: ["./data/qdrant_db:/qdrant/storage"]
```

#### 4c — CONTRIBUTING.md
Inhalt:
- Voraussetzungen (Python 3.11, API-Keys)
- Schnellstart (Docker vs. lokal)
- Projekt-Struktur erklären (tools/, agent/, orchestration/, memory/)
- Wie neue Tools hinzugefügt werden (tool.py Template)
- Test-Konvention (pytest + Lean)
- PR-Richtlinien

#### 4d — ROADMAP.md
Inhalt:
- Was bereits fertig ist (M1–M16 mit Beschreibung)
- Was als nächstes kommt (Demo-Video, HuggingFace, Portfolio-Projekte)
- Wie man beitragen kann (Issues, Feature-Requests)
- Vision: "Timus als Open-Source-Framework für autonome Agenten-Systeme"

#### 4e — README.md ergänzen
- Architecture-Diagramm (ASCII oder Mermaid) einfügen
- "Quick Start" Block oben (Docker: 3 Befehle)
- Feature-Matrix (was Timus kann vs. AutoGPT/AutoGen/CrewAI)
- Demo-Video Link (Platzhalter bis Video fertig)

#### 4f — .env.example aktualisieren
Alle neuen Flags aus Phase 1–3 eintragen (mit Kommentaren, ohne echte Werte).

### Verifikations-Gate Phase 4

```bash
# 1. Docker Build
docker build -t timus:latest .
# Erwartet: Build erfolgreich, kein Error

# 2. Docker Start
docker compose up -d
curl http://localhost:5000/health
# Erwartet: {"status": "ok"}

# 3. Docker Stop + Cleanup
docker compose down

# 4. Lean (unverändert)
lean lean/CiSpecs.lean
# Erwartet: 36 Theoreme, 0 Fehler (keine neuen nötig für Phase 4)

# 5. Markdown lint (optional)
npx markdownlint-cli "*.md" "docs/*.md"
```

**Checkpoint:** Docker läuft, /health antwortet, README hat Quick-Start → Commit + Push + Tag v4.3

---

## Gesamtübersicht: Lean-Theoreme

| Phase | Neue Theoreme | Gesamt |
|-------|--------------|--------|
| Ausgangspunkt | — | 27 |
| Phase 1 (M13+M14) | 28: m14_retry_bound, 29: m13_approved_activatable | 29 |
| Phase 2 (Qdrant) | 30: qdrant_migration_progress, 31: qdrant_batch_nonempty | 31 |
| Phase 3 (Agenten) | 32–36: dedup, ranking, dev_test, visual_retry, meta_depth | 36 |
| Phase 4 (Docker) | — | 36 |

Alle Theoreme: `by omega` (Int-Arithmetik) — kein simp, kein decide, keine Mathlib-Abhängigkeit für CiSpecs.lean.

---

## Gesamtübersicht: Tests

| Phase | Neue Tests | Kumulativ (neu) |
|-------|-----------|----------------|
| Phase 1 | 55 (M13+M14 bestehend) | 55 |
| Phase 2 | 17 (Qdrant bestehend) | 72 |
| Phase 3 | 50 (5 neue Test-Dateien) | 122 |
| Phase 4 | 1 (Docker health) | 123 |

---

## Implementierungsreihenfolge

```
Phase 1 (M13+M14 live)   — 1–2 Std.  — sofort, low risk
Phase 2 (Qdrant)         — 30 Min.   — nach Phase 1
Phase 3 (Agenten)        — 2–3 Tage  — 5 unabhängige Sub-Phasen (parallel möglich)
Phase 4 (Docker/GitHub)  — 1 Tag     — nach Phase 3
```

---

## Kritische Dateien

| Datei | Phase | Änderung |
|-------|-------|---------|
| `.env` | 1+2 | M13/M14 Flags, SMTP, QDRANT |
| `lean/CiSpecs.lean` | 1+2+3 | +9 neue Theoreme (28–36) |
| `agent/agents/research.py` | 3a | _deduplicate_sources, _rank_sources |
| `agent/agents/developer.py` | 3b | _auto_run_tests |
| `agent/agents/visual.py` | 3c | _click_with_retry, _wait_for_stable_screenshot |
| `agent/agents/meta.py` | 3d | Decomposition-Prompt + MAX_DECOMPOSITION_DEPTH |
| `agent/agents/communication.py` | 3e | _draft_email_with_review |
| `Dockerfile` | 4 | NEU |
| `docker-compose.yml` | 4 | NEU |
| `CONTRIBUTING.md` | 4 | NEU |
| `ROADMAP.md` | 4 | NEU |
| `README.md` | 4 | Architecture-Diagramm, Quick-Start |
| `.env.example` | 4 | Alle neuen Flags |
| `tests/test_research_improvements.py` | 3a | NEU — 12 Tests |
| `tests/test_developer_improvements.py` | 3b | NEU — 10 Tests |
| `tests/test_visual_improvements.py` | 3c | NEU — 8 Tests |
| `tests/test_meta_improvements.py` | 3d | NEU — 10 Tests |
| `tests/test_communication_improvements.py` | 3e | NEU — 10 Tests |

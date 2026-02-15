# Timus - Weitere Schritte: Optimierungen & Verbesserungen

**Erstellt:** 2026-02-14
**Basierend auf:** Vollstaendige Code-Analyse (240 Python-Dateien, 49 Tool-Module, 52 Test-Dateien)
**Gesamtbewertung:** 7/10 — Exzellente Architektur, aber technische Schulden

---

## Bewertung nach Bereich

| Bereich | Note | Kommentar |
|---------|------|-----------|
| Architektur | 9/10 | Modulare Struktur nach Refactoring vorbildlich |
| Code-Qualitaet | 8/10 | Sauber, aber bare excepts und print() |
| Performance | 7/10 | Sync Calls in async Context |
| Sicherheit | 6/10 | .env Risiko, Path Traversal |
| Dokumentation | 6/10 | README gut, API-Docs fehlen |
| Tests | 4/10 | Kritische Module ohne Tests |

---

## KRITISCH — Sofort beheben

### 1. .env aus Git-Historie entfernen

**Problem:** `.env` (7 KB mit echten API-Keys) wurde committed.
Die `.gitignore` ignoriert sie zwar jetzt, aber die Keys sind in der Git-Historie.

```bash
# Keys SOFORT rotieren:
# - OPENAI_API_KEY
# - ANTHROPIC_API_KEY
# - INCEPTION_API_KEY
# - DEEPSEEK_API_KEY
# - OPENROUTER_API_KEY
# - DATAFORSEO_USER/PASS

# Optional: Historie bereinigen
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env' \
  --prune-empty --tag-name-filter cat -- --all
git push --force
```

### 2. Bare Except-Bloecke ersetzen (29 Stellen)

**Problem:** `except:` ohne Typ verschluckt KeyboardInterrupt, SystemExit und maskiert echte Fehler.

| Datei | Zeile |
|-------|-------|
| `agent/dynamic_tool_mixin.py` | 276 |
| `agent/dynamic_tool_agent.py` | 303, 348 |
| `memory/memory_system.py` | 161, 169 |
| `tools/som_tool/tool.py` | 405, 408 |
| `tools/deep_research/tool.py` | 339 |
| `tools/cookie_banner_tool/tool.py` | 211 |

**Fix:**
```python
# VORHER:
try:
    result = do_something()
except:
    pass

# NACHHER:
try:
    result = do_something()
except Exception as e:
    log.warning(f"Fehler bei do_something: {e}")
```

### 3. Geloeschte Dateien committen

**Problem:** `git status` zeigt 7 Dateien als `D` (deleted) die nie committed wurden.

```bash
git add agent/creative_agent.py agent/deep_research_agent.py \
       agent/developer_agent.py agent/reasoning_agent.py \
       agent/reasoning_agent_backup.py agent/reasoning_agent_improved.py \
       agent/timus_react.py tools/moondream_tool/
git commit -m "chore: Veraltete Agent-Dateien und moondream_tool entfernt"
```

### 4. .env.example vervollstaendigen

**Problem:** Aktuelle `.env.example` enthaelt nur `ACTIVE_MONITOR=2`.

**Fehlende Keys:**
```bash
# === LLM Provider ===
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
INCEPTION_API_KEY=...
DEEPSEEK_API_KEY=...
OPENROUTER_API_KEY=...

# === Services ===
DATAFORSEO_USER=...
DATAFORSEO_PASS=...

# === Vision/Desktop ===
VISION_MODEL=claude-sonnet-4-5-20250929
ACTIVE_MONITOR=1
USE_MOUSE_FEEDBACK=1
USE_SCREEN_CHANGE_GATE=false
WHISPER_DEVICE=cuda          # oder "cpu" fuer Systeme ohne GPU

# === Server ===
MCP_URL=http://127.0.0.1:5000
MCP_TIMEOUT=300
LOG_LEVEL=INFO

# === Optional ===
AUTO_OPEN_FILES=true
ELEVENLABS_API_KEY=...
```

### 5. Legacy Agent-Dateien archivieren

**Problem:** Alte Agent-Versionen existieren parallel zur neuen Struktur und verwirren.

| Datei | Groesse | Status |
|-------|---------|--------|
| `agent/vision_executor_agent.py` | 12 KB | Veraltet |
| `agent/vision_cookie_agent.py` | 14 KB | Veraltet |
| `agent/qwen_visual_agent.py` | 29 KB | Veraltet |

**Empfehlung:** In `archive/` verschieben oder loeschen, falls die Funktionalitaet in den neuen Modulen abgedeckt ist.

---

## HOCH — Diese Woche

### 6. print() durch Logging ersetzen (1.473 Stellen)

**Problem:** 1.473 `print()` Aufrufe in 75 Dateien statt strukturiertem Logging.

**Schlimmste Dateien:**
| Datei | print() Anzahl |
|-------|----------------|
| `test_vision_stability.py` | 107 |
| `test_production_navigation.py` | 63 |
| `timus_voice_dispatcher.py` | 48 |
| `test_inworld_tts.py` | 45 |

**Fix (automatisierbar):**
```python
# Am Dateianfang:
import logging
log = logging.getLogger(__name__)

# Ersetze:
print(f"Tool {name} geladen")     ->  log.info("Tool %s geladen", name)
print(f"DEBUG: {value}")           ->  log.debug("Wert: %s", value)
print(f"FEHLER: {e}")              ->  log.error("Fehler: %s", e)
```

### 7. Test-Coverage erhoehen

**Problem:** Kritische Module haben KEINE Tests:

| Modul | Risiko | Vorhandene Tests |
|-------|--------|-----------------|
| `tools/memory_tool/` | Hoch | Keine |
| `tools/developer_tool/` | Hoch | Keine |
| `tools/deep_research/` | Hoch | Keine |
| `tools/som_tool/` | Hoch | Keine |
| `tools/qwen_vl_tool/` | Mittel | Keine |
| `agent/base_agent.py` | Hoch | Keine Unit-Tests |
| `agent/providers.py` | Hoch | Keine |
| `memory/memory_system.py` | Hoch | Keine |

**Empfehlung:** Mindestens Smoke-Tests fuer alle 49 Tools + Unit-Tests fuer `base_agent.py` und `providers.py`.

### 8. Test-Dateien organisieren

**Problem:** 52 Test-Dateien liegen im Root-Verzeichnis statt in `tests/`.

```bash
# Verschieben:
mkdir -p tests/integration tests/unit
mv test_*.py tests/integration/
# Bestehende tests/ Dateien bleiben:
# tests/test_skill_parser.py
# tests/test_hallucination.py
# tests/test_dynamic_tool_discovery.py
```

### 9. Dependencies pinnen

**Problem:** Kritische Packages ohne Versionsnummer in `requirements.txt`:

| Package | Gepinnt? |
|---------|----------|
| `fastapi==0.111.0` | Ja |
| `chromadb==0.4.24` | Ja |
| `numpy==1.26.4` | Ja |
| `openai` | **Nein** |
| `httpx` | **Nein** |
| `tiktoken` | **Nein** |
| `transformers` | **Nein** |
| `pyautogui` | **Nein** |
| `playwright` | **Nein** |

**Fix:**
```bash
pip freeze | grep -iE "(openai|httpx|tiktoken|transformers|pyautogui|playwright)" >> requirements.txt
```

Ausserdem fehlt eine `requirements-dev.txt`:
```txt
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=4.0
black>=24.0
ruff>=0.3
mypy>=1.8
```

### 10. Retry-Logik fuer API-Calls

**Problem:** Keine Retry-Logik bei `RateLimitError` oder transienten Fehlern.

**Betroffene Module:**
- `tools/deep_research/tool.py` — importiert `RateLimitError`, nutzt es aber nicht
- `agent/base_agent.py` — LLM Calls ohne Retry
- `agent/shared/mcp_client.py` — HTTP Calls ohne Retry

**Fix mit tenacity:**
```python
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

@retry(
    retry=retry_if_exception_type((RateLimitError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(3)
)
async def call_llm(self, messages):
    ...
```

---

## MITTEL — Naechste 2 Wochen

### 11. Synchrone HTTP-Calls durch async ersetzen (13 Stellen)

**Problem:** `requests.post()` blockiert den Event Loop in async Kontexten.

| Datei | Zeile | Call |
|-------|-------|------|
| `agent/shared/mcp_client.py` | 50 | `requests.post` (call_sync) |
| `tools/inception_tool/tool.py` | - | `requests` |
| `tools/search_tool/tool.py` | - | `requests` |
| `tools/document_parser/tool.py` | - | `requests` |

**Fix:** `call_sync()` in `mcp_client.py` ist OK (wird bewusst synchron genutzt).
Die Tool-Dateien sollten auf `httpx.AsyncClient` umgestellt werden.

### 12. Hardcoded URLs und Ports zentralisieren

**Problem:** `http://localhost:5000` / `http://127.0.0.1:5000` an 4+ Stellen hardcoded.

| Datei | Zeile |
|-------|-------|
| `main_dispatcher.py` | 545 |
| `agent/base_agent.py` | 37 |
| `agent/shared/mcp_client.py` | 21 |
| `tools/browser_controller/controller.py` | 8 |

Alle nutzen bereits `os.getenv("MCP_URL", ...)` als Fallback — **aber nicht konsistent**.

**Fix:** Eine zentrale Konfigurationsdatei:
```python
# config/settings.py
import os

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:5000")
MCP_TIMEOUT = int(os.getenv("MCP_TIMEOUT", "300"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))
```

### 13. Memory-System auf async umstellen

**Problem:** `memory/memory_system.py` nutzt synchrones `sqlite3.connect()`.

```python
# VORHER (blockiert):
with sqlite3.connect(self.db_path) as conn:
    conn.execute("SELECT ...")

# NACHHER (non-blocking):
import aiosqlite
async with aiosqlite.connect(self.db_path) as conn:
    await conn.execute("SELECT ...")
```

Zusaetzlich: Connection Pooling fehlt — jede Query oeffnet eine neue Verbindung.

### 14. Path Traversal Schutz

**Problem:** `tools/developer_tool/tool.py` nutzt `resolve()` aber prueft nicht ob der Pfad ausserhalb von `PROJECT_ROOT` liegt.

```python
# VORHER:
path = (PROJECT_ROOT / path_str).resolve()
if path.exists() and path.is_file():
    return path.read_text()

# NACHHER:
path = (PROJECT_ROOT / path_str).resolve()
if not str(path).startswith(str(PROJECT_ROOT.resolve())):
    raise ValueError(f"Pfad ausserhalb des Projekts: {path}")
if path.exists() and path.is_file():
    return path.read_text()
```

### 15. MCP Server Haertung

**Concurrency Limits:**
```python
# GPU-Tools koennen nicht unbegrenzt parallel laufen
gpu_semaphore = asyncio.Semaphore(2)

@app.post("/")
async def handle_jsonrpc(request: Request):
    # Request-Groesse limitieren
    body = await request.body()
    if len(body) > 10_000_000:  # 10MB
        return JSONResponse({"error": "Request too large"}, 413)
```

**Metrics (optional aber empfohlen):**
```python
from prometheus_client import Counter, Histogram

tool_calls = Counter("mcp_tool_calls_total", "Tool calls", ["tool_name"])
tool_duration = Histogram("mcp_tool_duration_seconds", "Tool duration", ["tool_name"])
```

---

## NIEDRIG — Backlog

### 16. Structured Logging (JSON)

Fuer Produktion und Log-Aggregation:
```python
import json_logging
json_logging.init_fastapi(enable_json=True)
```

### 17. Type Hints vervollstaendigen

Kritische Dateien ohne Type Hints:
- `agent/base_agent.py` — Viele Methoden ohne Return-Types
- `memory/memory_system.py` — Parameter-Types fehlen

Langfristig: `mypy --strict` als CI-Check

### 18. Architektur-Diagramme erstellen

Fehlende Visualisierungen:
- Agent-Interaktion und Dispatcher-Flow
- Tool-Registry Discovery Ablauf
- Memory-System Datenfluss (Session -> Persistent -> ChromaDB)
- MCP Server Request-Lifecycle

### 19. Dead Code bereinigen

**Ungenutzte Test-Dateien (nach Moondream-Entfernung):**
- `test_moondream_simple.py` — referenziert geloeschtes Tool
- `test_moondream_tool.py` — referenziert geloeschtes Tool
- `test_mcp_moondream.py` — referenziert geloeschtes Tool
- `test_optimized_moondream.py` — referenziert geloeschtes Tool

**Ungenutzter Code scannen:**
```bash
pip install vulture
vulture agent/ tools/ server/ memory/ --min-confidence 80
```

### 20. GPU-Concurrency und Ressourcen-Management

**Problem:** Qwen-VL, PaddleOCR und SoM-Tool teilen sich die GPU ohne Koordination.

**Empfehlung:**
```python
# Globaler GPU-Lock
import asyncio
gpu_lock = asyncio.Semaphore(1)  # Nur 1 GPU-Task gleichzeitig

async def run_gpu_task(func, *args):
    async with gpu_lock:
        return await func(*args)
```

### 21. Vision Agent Routing vereinfachen

**Problem:** `main_dispatcher.py` hat 7+ verschiedene Vision-Agent-Typen:

```python
"visual": "SPECIAL_VISION_QWEN",
"vision_qwen": "SPECIAL_VISION_QWEN",
"visual_nemotron": "SPECIAL_VISUAL_NEMOTRON",
"vision": "SPECIAL_VISION_QWEN",
"qwen": "SPECIAL_VISION_QWEN",
"visual_agent": "SPECIAL_VISUAL",
```

**Empfehlung:** Auf 2-3 klar definierte Varianten reduzieren:
- `visual` — Standard (Claude Vision)
- `visual_desktop` — Desktop-Automatisierung (Nemotron + PyAutoGUI)

### 22. Whisper Device Fallback

**Problem:** `tools/voice_tool/tool.py` crasht auf CPU-only Systemen:

```python
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")  # Crasht ohne GPU!
```

**Fix:**
```python
import torch
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
```

---

## Zusammenfassung der Aufwandsschaetzung

| Prioritaet | Anzahl Tasks | Geschaetzter Aufwand |
|------------|-------------|---------------------|
| Kritisch | 5 Tasks | 1-2 Tage |
| Hoch | 5 Tasks | 3-5 Tage |
| Mittel | 5 Tasks | 1-2 Wochen |
| Niedrig | 7 Tasks | Laufend / Backlog |

**Empfohlene Reihenfolge:**
1. API-Keys rotieren + .env aus Historie entfernen
2. Bare excepts fixen + geloeschte Dateien committen
3. .env.example + Legacy-Files archivieren
4. Tests + print()->logging (parallelisierbar)
5. Dependencies pinnen + Retry-Logik
6. Async-Migration + Server-Haertung

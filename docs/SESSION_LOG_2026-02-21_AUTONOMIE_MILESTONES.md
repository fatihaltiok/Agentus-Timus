# Session-Log: Timus Autonomie-Ausbau (M0–M5 + Systemd)
**Datum:** 2026-02-21
**Dauer:** ~1 Tag
**Ziel:** Timus von einem interaktiven Assistenten zu einem vollautonomen, 24/7-laufenden System ausbauen

---

## Ausgangslage

Timus war ein leistungsfähiger Multi-Agenten-Assistent, der aber nur auf direkte Nutzereingaben reagieren konnte. Der vorhandene `ProactiveScheduler` in `orchestration/scheduler.py` existierte, war aber nicht mit `run_agent()` verbunden. Tasks wurden in einer einfachen `tasks.json` gespeichert (nicht thread-safe). Kein Fernzugriff, kein Selbst-Monitoring.

**Orientierung:** OpenClaw-Framework (Multi-Channel, Cron/Webhooks, Skill-System)

---

## Meilenstein-Übersicht

| Meilenstein | Beschreibung | Status |
|---|---|---|
| M0 | Basis-Audit: Bugs, Kompatibilität, Architektur | ✅ Abgeschlossen |
| M1 | Scheduler aktivieren + mit run_agent() verbinden | ✅ Abgeschlossen |
| M2 | Telegram-Bot Gateway | ✅ Abgeschlossen |
| M3 | SQLite Task-Queue (ersetzt tasks.json) | ✅ Abgeschlossen |
| M4 | Self-Healing & Model-Failover | ✅ Abgeschlossen |
| M5 | System-Monitor + Task-Erinnerungen | ✅ Abgeschlossen |
| +  | systemd Auto-Start Services | ✅ Abgeschlossen |

---

## M0 — Basis-Audit

### Ziele
- Alle Python-Fehler und Import-Probleme finden
- Kompatibilität der Module prüfen
- Architektur verstehen

### Gefundener Bug: `tools/summarizer/tool.py`

**Problem:** Die Datei importierte `ensure_browser_initialized` aus `tools.shared_context`, wo die Funktion nicht existiert.

```python
# FALSCH (vorher)
from tools.shared_context import (openai_client, log, ensure_browser_initialized)

# RICHTIG (Korrektur)
from tools.shared_context import (openai_client, log)
from tools.browser_tool.tool import ensure_browser_initialized
```

**Ergebnis:** Nach diesem Fix waren alle 53 registrierten Tools im MCP-Server ladbar.

### Architektur-Erkenntnisse
- `orchestration/scheduler.py` → `ProactiveScheduler` vorhanden aber unverbunden
- `tasks.json` → flache JSON-Datei, nicht thread-safe, keine Prioritäten
- Kein Fernzugriff (Telegram/Webhook)
- Kein Selbst-Monitoring
- OpenAI-Key in `.env` war abgelaufen (401-Fehler) → neuer Key eingetragen

---

## M1 — Scheduler aktivieren

### Ziel
Den vorhandenen `ProactiveScheduler` mit dem echten `run_agent()` verbinden.

### Neu erstellt: `orchestration/autonomous_runner.py`

**Funktion:** Bridge zwischen Scheduler-Heartbeat und Task-Ausführung.

**Ablauf:**
1. `AutonomousRunner.start(tools_desc)` → startet `ProactiveScheduler`
2. Heartbeat-Event → `_worker_loop()` wird geweckt
3. `_worker_loop()` → holt nächsten Task aus Queue via `claim_next()`
4. Task wird ausgeführt via `failover_run_agent()` (Self-Healing aus M4)
5. Ergebnis → `queue.complete()` oder `queue.fail()` (mit Retry-Logik)
6. Bei totalem Ausfall → Telegram-Alert an Nutzer

**Wichtige Funktionen:**
```python
class AutonomousRunner:
    async def start(self, tools_desc: str) -> None
    async def stop(self) -> None
    async def trigger_now(self) -> None     # Manueller Trigger
    async def _worker_loop(self) -> None
    async def _execute_task(self, task: dict) -> None
    async def _send_failure_alert(self, ...) -> None

def add_task(description, target_agent=None, priority=...) -> str
```

---

## M2 — Telegram-Bot Gateway

### Ziel
Fernzugriff auf Timus über Telegram (Bot: @agentustimus_bot).

### Konfiguration
```
TELEGRAM_BOT_TOKEN=8201854248:AAGigpTAX8I4JfYKCQsH0zp4NMIPU8_2ZO4
TELEGRAM_ALLOWED_IDS=1679366204  # Nur dieser Nutzer
```

### Neu erstellt: `gateway/telegram_gateway.py`

**Bot-Befehle:**

| Befehl | Funktion |
|---|---|
| `/start` | Begrüßung + Session-ID anzeigen |
| `/tasks` | Alle Queue-Tasks mit Priorität und Status |
| `/task <text>` | Neuen Task zur autonomen Queue hinzufügen |
| `/remind HH:MM <text>` | Zeitgesteuerte Erinnerung setzen |
| `/remind YYYY-MM-DDTHH:MM <text>` | ISO-Erinnerung |
| `/status` | Scheduler-Status + Queue-Stats + Live CPU/RAM/Disk |
| `<normaler Text>` | Direkt an Timus Agent-Pipeline |

**Technische Details:**
- Session-Mapping: Telegram-User-ID → persistente Timus-Session-ID
- Typing-Indikator während langer Verarbeitungszeit
- Automatisches Aufteilen langer Antworten (Telegram-Limit: 4096 Zeichen)
- Zeitparser für Erinnerungen: `HH:MM` (heute/morgen automatisch), ISO-8601

---

## M3 — SQLite Task-Queue

### Ziel
`tasks.json` durch eine thread-safe, prioritätsfähige SQLite-Queue ersetzen.

### Neu erstellt: `orchestration/task_queue.py`

**Schema:**
```sql
CREATE TABLE tasks (
    id           TEXT PRIMARY KEY,
    description  TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 2,  -- 0=CRITICAL, 1=HIGH, 2=NORMAL, 3=LOW
    task_type    TEXT NOT NULL DEFAULT 'manual',
    target_agent TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    retry_count  INTEGER NOT NULL DEFAULT 0,
    max_retries  INTEGER NOT NULL DEFAULT 3,
    created_at   TEXT NOT NULL,
    run_at       TEXT,          -- NULL = sofort, sonst ISO-8601 (für Erinnerungen)
    started_at   TEXT,
    completed_at TEXT,
    result       TEXT,
    error        TEXT,
    metadata     TEXT
);
```

**Atomares Task-Claiming (kein Race Condition):**
```sql
UPDATE tasks SET status='in_progress', started_at=?
WHERE id = (
    SELECT id FROM tasks
    WHERE status = 'pending'
      AND (run_at IS NULL OR run_at <= ?)
    ORDER BY priority ASC, created_at ASC
    LIMIT 1
)
RETURNING *
```

**Prioritäten:** CRITICAL(0) > HIGH(1) > NORMAL(2) > LOW(3)
**Retry-Logik:** Bei Fehler → `pending` zurück (bis `max_retries` erreicht) → dann `failed`
**SQLite WAL-Modus:** Parallele Reads möglich
**Migration:** Bestehende `tasks.json` wird beim ersten Start automatisch importiert

---

## M4 — Self-Healing & Model-Failover

### Ziel
Bei Modell-Ausfällen automatisch auf Backup-Modelle wechseln, bei Totalausfall Telegram-Alert.

### Neu erstellt: `utils/error_classifier.py`

Klassifiziert Exceptions in:
- `API_ERROR` → retriable
- `RATE_LIMIT` → retriable (längere Pause)
- `AUTH_ERROR` → nicht retriable (Key-Problem)
- `CONTENT_FILTER` → nicht retriable
- `TIMEOUT` → retriable + failover
- `TOOL_FAIL` → retriable
- `MODEL_ERROR` → retriable + failover
- `UNKNOWN` → retriable

### Neu erstellt: `utils/model_failover.py`

**Failover-Ketten:**
```python
FAILOVER_CHAINS = {
    "research":    ["reasoning", "meta", "executor"],
    "reasoning":   ["meta", "executor"],
    "development": ["meta", "executor"],
    "creative":    ["executor"],
    "meta":        ["executor"],
    "executor":    [],
    "visual":      ["executor"],
}
```

**Ablauf:**
1. Primär-Agent ausführen
2. Bei retriable Fehler → exponentieller Backoff + Retry (max 3x)
3. Bei failover-Fehler → nächster Agent in der Kette
4. Bei leerem `result` → auch Failover
5. Alle Versuche ausgeschöpft → `None` + Alert

---

## M5 — System-Monitor + Task-Erinnerungen

### Ausgangslage
Ursprünglich war RSS-Polling geplant. Nutzer hat entschieden: "ich lese solche Infos nicht." → Pivot zu System-Monitoring.

### Neu erstellt: `gateway/system_monitor.py`

**Funktion:** Überwacht CPU, RAM und Disk. Sendet Telegram-Alert bei Überschreitung.

**Konfiguration:**
```
MONITOR_ENABLED=true
MONITOR_INTERVAL_MINUTES=5
MONITOR_CPU_THRESHOLD=85
MONITOR_RAM_THRESHOLD=85
MONITOR_DISK_THRESHOLD=90
```

**Alert-Cooldown:** Gleicher Alert max. alle 30 Minuten (kein Spam).

**Systemwerte beim Setup:**
- CPU: 5.3% (normal)
- RAM: 31.6% (normal)
- Disk: 85.5% ⚠️ (nah am Schwellwert von 90%)

**Task-Erinnerungen:** Implementiert über `/remind`-Befehl im Telegram-Bot (siehe M2) + `run_at`-Feld in der SQLite-Queue.

---

## Systemd Auto-Start

### Ziel
Timus startet automatisch beim Systemboot und überlebt Abstürze.

### Fix: Daemon-Modus in `main_dispatcher.py`

Ohne TTY (systemd-Service) würde `input()` sofort `EOFError` werfen und den Dispatcher beenden. Fix in `_cli_loop()`:

```python
if not sys.stdin.isatty():
    log.info("Daemon-Modus: CLI deaktiviert. Stoppe via SIGTERM.")
    stop_event = asyncio.Event()
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)
    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    await stop_event.wait()
    return
```

### Erstellt: `/etc/systemd/system/timus-mcp.service`

```ini
[Unit]
Description=Timus MCP Server (Tool Registry)
After=network.target

[Service]
Type=simple
User=fatih-ubuntu
WorkingDirectory=/home/fatih-ubuntu/dev/timus
ExecStart=/home/fatih-ubuntu/miniconda3/envs/timus/bin/uvicorn \
    server.mcp_server:app --host 127.0.0.1 --port 5000 --log-level info
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Erstellt: `/etc/systemd/system/timus-dispatcher.service`

```ini
[Unit]
Description=Timus Main Dispatcher (Autonomous Agent)
After=network.target timus-mcp.service
Requires=timus-mcp.service

[Service]
Type=simple
User=fatih-ubuntu
WorkingDirectory=/home/fatih-ubuntu/dev/timus
ExecStart=/home/fatih-ubuntu/miniconda3/envs/timus/bin/python main_dispatcher.py
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
```

### Installation (muss manuell ausgeführt werden)

```bash
sudo cp /home/fatih-ubuntu/dev/timus/timus-mcp.service /etc/systemd/system/
sudo cp /home/fatih-ubuntu/dev/timus/timus-dispatcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable timus-mcp.service timus-dispatcher.service
sudo systemctl start timus-mcp.service
sleep 3
sudo systemctl start timus-dispatcher.service
```

---

## Neue Dateien (Übersicht)

| Datei | Beschreibung |
|---|---|
| `orchestration/autonomous_runner.py` | Scheduler↔Agent Bridge |
| `orchestration/task_queue.py` | SQLite Task-Queue (ersetzt tasks.json) |
| `gateway/telegram_gateway.py` | Telegram-Bot (@agentustimus_bot) |
| `gateway/webhook_gateway.py` | HMAC-authentifizierter Webhook-Server |
| `gateway/event_router.py` | Event → Task-Queue Router |
| `gateway/system_monitor.py` | CPU/RAM/Disk Monitor mit Telegram-Alerts |
| `utils/error_classifier.py` | Exception → ErrorType Klassifizierer |
| `utils/model_failover.py` | Automatischer Agenten-Failover |
| `timus-mcp.service` | systemd Unit für MCP-Server |
| `timus-dispatcher.service` | systemd Unit für Dispatcher |

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `main_dispatcher.py` | `main_loop()` startet Runner+Telegram+Monitor; Daemon-Fix in `_cli_loop()` |
| `tools/summarizer/tool.py` | Import-Bug behoben |
| `.env` | Neuer OpenAI-Key, Telegram-Config, Monitor-Config |

---

## .env Neue Variablen

```bash
# Heartbeat-Scheduler
HEARTBEAT_ENABLED=true
HEARTBEAT_INTERVAL_MINUTES=15

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_IDS=1679366204

# Webhook (deaktiviert)
WEBHOOK_ENABLED=false
WEBHOOK_PORT=8765
WEBHOOK_SECRET=

# System-Monitor
MONITOR_ENABLED=true
MONITOR_INTERVAL_MINUTES=5
MONITOR_CPU_THRESHOLD=85
MONITOR_RAM_THRESHOLD=85
MONITOR_DISK_THRESHOLD=90
```

---

## Nach dem Neustart: Checkliste

```bash
# 1. Services installieren (falls noch nicht geschehen)
sudo cp ~/dev/timus/timus-mcp.service /etc/systemd/system/
sudo cp ~/dev/timus/timus-dispatcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable timus-mcp timus-dispatcher

# 2. Services starten
sudo systemctl start timus-mcp
sleep 3
sudo systemctl start timus-dispatcher

# 3. Status prüfen
sudo systemctl status timus-mcp timus-dispatcher

# 4. Logs beobachten
journalctl -u timus-dispatcher -f

# 5. Telegram: /start schicken an @agentustimus_bot
# 6. Telegram: /status → sollte Scheduler, Queue und Systemwerte zeigen
```

---

## Architektur nach dieser Session

```
                    ┌─────────────────────────────────────────┐
                    │           TIMUS (Autonomous)            │
                    │                                         │
  Telegram ─────→  │  TelegramGateway                        │
  Webhook  ─────→  │  WebhookServer  → EventRouter           │
  Heartbeat ─────→ │  ProactiveScheduler                     │
                    │       ↓                                 │
                    │  AutonomousRunner                       │
                    │       ↓                                 │
                    │  SQLite TaskQueue  ←── /task, /remind   │
                    │       ↓                                 │
                    │  failover_run_agent()                   │
                    │       ↓                                 │
                    │  [executor|research|reasoning|...]      │
                    │       ↓                                 │
                    │  MCP Server (53 Tools)                  │
                    │       ↓                                 │
                    │  SystemMonitor → Telegram Alert         │
                    └─────────────────────────────────────────┘
```

---

*Erstellt am 2026-02-21 — Timus v3.4 (Autonomous + Telegram)*

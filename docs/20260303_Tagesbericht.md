# Tagesbericht: LLM-Selbstüberwachung, Web-Fetch, Shell-Erweiterung, Service-Neustart
**Datum:** 2026-03-03
**Autor:** Claude Code (Session)
**Status:** ✅ Abgeschlossen

---

## Zusammenfassung

Fünf Themenbereiche in einer Session: LLM-Selbstüberwachung mit zwei neuen Schichten (event-getrieben + zeitbasiert), Web-Fetch-Tool für eigenständigen URL-Abruf, Dispatcher-Fix für URL-Routing, Shell-Agent-Erweiterung mit Install-Befugnissen und konfigurierbarem Timeout, sowie autonomer Service-Neustart-Mechanismus. Insgesamt 9 Commits.

---

## 1. LLM-Selbstüberwachung: Schicht 2 + 3 (v3.3)

### Ausgangslage

Timus' 5-Minuten-Heartbeat (Schicht 1) arbeitet rein regelbasiert — Schwellwerte, DB-Counts, Circuit-Breaker. Keine echte Ursachenanalyse, keine Mustererkennung über Zeit.

### Schicht 2 — Event-getrieben (`qwen3.5-plus`)

**Datei:** `orchestration/self_healing_engine.py`

Neue Methode `_diagnose_incident_with_llm()`: Wird bei jedem **neuen** Incident ausgelöst (`upsert.get("created") == True`). Wiederholungen werden ignoriert.

```
Neuer Incident → qwen3.5-plus via OpenRouter (~0.5s)
→ {"root_cause", "confidence", "recommended_action", "urgency", "pattern_hint"}
→ details["llm_diagnosis"] in DB persistiert
→ Recovery-Playbook bekommt Diagnose mit
```

Feature-Flag: `AUTONOMY_LLM_DIAGNOSIS_ENABLED=true`

### Schicht 3 — Zeitbasiert (`deepseek-v3.2`)

**Datei:** `orchestration/meta_analyzer.py` (neu)

Klasse `MetaAnalyzer` läuft alle 60 Minuten (`heartbeat_count % 12 == 0`):
- Liest 24h Scorecard-Snapshots aus SQLite
- Liest letzte 15 Incidents
- Ruft `deepseek/deepseek-v3.2` via OpenRouter auf (~2s)
- Speichert Ergebnis als `canvas_event` (event_type="meta_analysis")

```json
{
  "trend": "stable",
  "weakest_pillar": "planning",
  "key_insight": "Planning-Score sinkt jeden Abend durch Midnight-Deadlines",
  "action_suggestion": "AUTONOMY_COMMITMENT_OVERDUE_CANCEL_HOURS auf 1.0 senken",
  "risk_level": "low"
}
```

Feature-Flag: `AUTONOMY_META_ANALYSIS_ENABLED=true`

**Commit:** `bd7fb35`

---

## 2. Web-Fetch-Tool: Agenten öffnen eigenständig URLs (v3.3)

### Problem

Timus-Agenten konnten URLs nicht direkt lesen — nur suchen (DataForSEO) oder Desktop-Browser steuern. URLs in Nutzeranfragen wurden ignoriert oder an den falschen Agenten (visual statt research) weitergeleitet.

### Lösung

**Datei:** `tools/web_fetch_tool/tool.py` (neu)

Zwei MCP-Tools mit intelligentem Fallback:

```
fetch_url("https://example.com")
  → requests + BeautifulSoup  (~1s, 90% aller Seiten)
  → 401/403 oder SPA erkannt?
    → Playwright Chromium     (~5s, JavaScript-Rendering)
```

SPA-Erkennung via Heuristik: wenig sichtbarer Text bei viel JS-Code → automatisch Playwright.

Output: `title`, `content` (bis 50k), `markdown` (html2text), `links[]`

Sicherheit: Blacklist für `localhost`, private IP-Ranges, `file://`, Path-Traversal.

**`fetch_multiple_urls`:** Bis zu 10 URLs parallel via `asyncio.gather`.

**Agenten-Zugriff:** 7 von 13 Agenten haben Zugriff (executor, research, reasoning, meta, development, visual, data).

**Tests:** 26 offline-fähige Tests in `tests/test_web_fetch_tool.py` — alle grün.

### Dispatcher-Fix

**Datei:** `main_dispatcher.py`

Regel 8 ergänzt: URL-Inhalt lesen → immer `research` (nicht `visual`). Zuvor wurde "https://" als Browser-Steuerung interpretiert.

**Commits:** `c9de886`, `cdf4546`, `b1b0f6d`

---

## 3. Shell-Agent: Erweiterung Befugnisse + Timeout

### Problem

- `_MAX_TIMEOUT = 30s` — zu kurz für pip-Installationen (oft 60–180s)
- Shell-Agent erkannte Installations-Anfragen nicht (fehlende Keywords)
- Kein dediziertes Tool für Package-Installation

### Lösung

**Datei:** `tools/shell_tool/tool.py`

| Änderung | Detail |
|----------|--------|
| `_MAX_TIMEOUT` | Via `SHELL_MAX_TIMEOUT` ENV konfigurierbar, default 300s |
| `_INSTALL_TIMEOUT` | Via `SHELL_INSTALL_TIMEOUT` ENV, default 180s |
| `install_package` | Neues MCP-Tool: pip/pip3/apt/apt-get/conda, Injection-Schutz, Audit-Log |

**`install_package`-Sicherheit:**
- Paketname: nur `[a-zA-Z0-9._\-\[\]>=<!=~^*]+` erlaubt
- Manager: nur whitelisted (`pip`, `pip3`, `apt`, `apt-get`, `conda`)
- Audit-Log-Eintrag bei jedem Aufruf

**`main_dispatcher.py`:** 20+ neue SHELL_KEYWORDS ergänzt:
`"pip install"`, `"apt install"`, `"paket installieren"`, `"starte die datei"`, etc.

**`requirements.txt`:** `html2text==2024.2.26` nachgetragen (fehlte, wurde für Web-Fetch benötigt).

**Commits:** `ced4c31`, `4c66743`

---

## 4. Autonomer Service-Neustart (v3.3)

### Problem

Falls Timus nicht reagiert oder träge ist, war bisher ein manueller Eingriff nötig.

### Lösung

**Datei:** `tools/shell_tool/tool.py` — neues MCP-Tool `restart_timus`

```
restart_timus(mode="full")       → Dispatcher stopp → MCP neu → Health-Check → Dispatcher neu
restart_timus(mode="mcp")        → Nur MCP-Server
restart_timus(mode="dispatcher") → Nur Dispatcher
restart_timus(mode="status")     → Service-Status abfragen
```

Health-Check: 8 Versuche × 3s auf `http://127.0.0.1:5000/health`.

**`scripts/restart_timus.sh`:** CLI-Äquivalent mit Farb-Output und journalctl-Logs.

**`scripts/sudoers_timus`:** NOPASSWD-Template für passwortfreien `sudo systemctl`.
Bereits installiert: `/etc/sudoers.d/timus-restart` (`r--r-----`).

**Commits:** `38e4e31`, `9243540`

---

## 5. README: Architektur-Vergleichstabelle

Neue Sektion direkt nach dem Logo — sichtbar für jeden GitHub-Besucher als Erstes:

- Tabelle: Timus vs. typisches KI-Projekt (13 Eigenschaften)
- Verweis auf Forschungsbegriff *Introspective Autonomous Systems* / *MAPE-K Loop*
- Deutliche Botschaft: "Das ist kein Chatbot. Das ist ein autonomes KI-Betriebssystem."

**Commit:** `666d8b4`

---

## Commits dieser Session

| Hash | Beschreibung |
|------|-------------|
| `bd7fb35` | feat(monitoring): LLM-Selbstüberwachung Schicht 2 + 3 (v3.3) |
| `c9de886` | feat(tools): Web-Fetch-Tool v1.0 — Hybrid requests→Playwright (v3.3) |
| `cdf4546` | docs(readme): Phase 15 — Web-Fetch-Tool dokumentiert |
| `b1b0f6d` | fix(dispatcher): URL-Inhalt lesen → research statt visual |
| `4c66743` | chore(deps): html2text==2024.2.26 ergänzt |
| `ced4c31` | feat(shell): install_package-Tool + erweiterter Timeout + Dispatcher-Routing |
| `38e4e31` | feat(shell): restart_timus-Tool + Neustart-Skripte |
| `9243540` | docs(readme): Phase 16 — Autonomer Service-Neustart dokumentiert |
| `666d8b4` | docs(readme): Architektur-Vergleichstabelle — Timus ist kein 0815-Projekt |

---

## Neue Dateien

| Datei | Inhalt |
|-------|--------|
| `tools/web_fetch_tool/tool.py` | Web-Fetch MCP-Tool (fetch_url, fetch_multiple_urls) |
| `tools/web_fetch_tool/__init__.py` | Modul-Init |
| `tests/test_web_fetch_tool.py` | 26 offline-Tests |
| `orchestration/meta_analyzer.py` | MetaAnalyzer Schicht 3 |
| `scripts/restart_timus.sh` | CLI-Neustart-Skript |
| `scripts/sudoers_timus` | NOPASSWD-Template (bereits installiert) |

---

## Aktueller Stand

**Version:** v3.3
**Autonomie-Schichten:** Schicht 1 (regelbasiert) + Schicht 2 (LLM event-getrieben) + Schicht 3 (LLM zeitbasiert) aktiv
**Neues Feature-Flags in `.env`:**
```
AUTONOMY_LLM_DIAGNOSIS_ENABLED=true
AUTONOMY_META_ANALYSIS_ENABLED=true
AUTONOMY_META_ANALYSIS_INTERVAL_HEARTBEATS=12
SHELL_MAX_TIMEOUT=300
SHELL_INSTALL_TIMEOUT=180
```

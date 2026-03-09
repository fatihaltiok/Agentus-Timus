# Timus Production Readiness P0

Stand: 2026-03-09

## Ziel
P0 definiert die minimalen Release-Gates, ohne die Timus nicht als produktionsnah gelten soll.

## P0-Gates
1. `syntax_compile`
   Kritische Kernmodule muessen via `py_compile` importierbar bleiben.

2. `security_bandit`
   Python-Code in `agent/`, `gateway/`, `orchestration/`, `server/`, `tools/`
   wird statisch auf typische Security-Schwachstellen geprueft.

3. `security_pip_audit`
   Python-Abhaengigkeiten werden auf bekannte Schwachstellen geprueft.

4. `production_smoke`
   Deterministische Smoke-Suite fuer Kernpfade:
   - Dispatcher/Run-Agent Logging
   - Error-Path Persistence
   - Telegram Reply/Feedback
   - Dispatcher Browser-Routing
   - Restart Hardening

## Lokal ausfuehren
```bash
python scripts/run_production_gates.py --allow-missing-security-tools
```

Mit installierten Security-Tools:
```bash
python scripts/run_production_gates.py
```

## CI-Definition
Der CI-Workflow muss diese Gates blockierend ausfuehren. Lean 4, CrossHair und die breiteren
Regression-Suiten bleiben weiterhin zusaetzliche Qualitaetsgates, aber P0 ist der minimale
Produktions-Freigabe-Block.

## Aktueller Blocker-Stand
- `P0` ist aktuell gruen: `syntax_compile`, `security_bandit`, `security_pip_audit` und `production_smoke` bestehen

## Restliche Betriebsrisiken ausserhalb des aktuellen P0-Gates
- `pip check` ist aktuell ebenfalls sauber
- die zuvor offenen Environment-Konflikte wurden durch Upgrade auf `kubernetes==35.0.0`, `torchaudio==2.10.0`, Anpassung von `tokenizers` und Entfernung des ungetrackten Legacy-Pakets `moondream` bereinigt
- verbleibende Risiken liegen jetzt eher auf den naechsten Produktionsachsen wie Kostenfuehrung, Ops-Dashboard und breiterer E2E-Haertung

## Noch bewusst NICHT Teil von P0 Phase 1
- globales Token-/Kosten-Dashboard
- Budget-Abbruch pro Session/Agent
- Canary-/Rollout-Steuerung fuer alle neuen Features
- Visual-Plan/State-Maschine fuer komplexe Webseiten

Diese Themen bleiben P0/P1-Folgeschritte, aber Phase 1 schafft die erste reproduzierbare
Freigabeschranke.

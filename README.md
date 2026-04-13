# Timus

<p align="center">
  <img src="assets/branding/timus-logo-glow.png" alt="Timus Logo" width="760">
</p>

Timus ist ein selbstgehostetes, zustandsbehaftetes Multi-Agenten-System fuer Canvas, Telegram, Android und Terminal. Das System verbindet einen FastAPI-basierten MCP-Server, Dispatcher-Routing, Meta-Orchestrierung, persistentes Gespraechsgedaechtnis, Browser-/Vision-Pfade, Runtime-Observability und kontrollierte Self-Improvement-Schleifen.

Diese README beschreibt den aktuellen Produkt- und Architekturstand. Historische Detailentwicklung liegt in der technischen Doku und im Dev-Changelog.

## Kurzuebersicht

Stand: **13. April 2026**

- **Phase C abgeschlossen**
  - Runtime-Haertung
  - Request-/Incident-Korrelation
  - C4-/Longrunner-Transport
  - Canvas-Runtime-Sicht
  - C3: Vision/OCR Hot-Path-Haertung (Telemetrie, Explicit Router, OOM-Guards)
- **Phase D abgeschlossen**
  - D0: Conversation State, Turn Understanding, Topic History, Preference-/Instruction-Memory, State-Decay, Historical Topic Retrieval, Specialist Context Propagation
  - D1: Auth Need Detection
  - D2: Approval + Consent Gate
  - D3: user-mediated Login
  - D4: Session Reuse + Chrome Credential Broker
  - D5: Challenge Handover + Resume
- **Phase E aktiv (E1–E4 abgeschlossen)**
  - E1: Improvement Signal Pipeline, Cross-Source-Kandidaten, Incident-/Observation-Einzug, Freshness/Decay, Operator-Views
  - E2: Weakness-to-Task Compiler, Evidence-aware Promotion Gate
  - E3: Execution Bridge, Managed Autonomy, Guardrails gegen Improvement-Loops
  - E4: Terminaler Improvement-Contract (blocked / ended\_unverified / verified), Retry-Semantik

Kurz gesagt: Timus ist heute kein stateless Chat-Agent und kein bloßer Tool-Router mehr, sondern ein persistenter Arbeitsagent mit zustandsbewusster Meta-Schicht, kontextfaehigen Spezialisten, sichtbarer Laufzeit und kontrollierter Selbstverbesserungsschleife.

## Was Timus heute kann

- mehrere Spezialisten koordinieren:
  - `meta`
  - `executor`
  - `research`
  - `visual`
  - `system`
  - weitere Rollen wie `shell`, `document`, `communication`
- denselben Nutzer ueber mehrere Turns, Themenwechsel und Wiederaufnahmen konsistent begleiten
- Themen, Anweisungen und Praeferenzen strukturiert merken und spaeter wiederverwenden
- historische Gespraechskontexte ueber Zeitanker wie `eben`, `gestern`, `letzte Woche` oder `vor 3 Monaten` wiederaufnehmen
- Langlaeufer, Blocker, Teilergebnisse und Fehler sichtbar transportieren
- Approval-/Auth-/Login-Workflows als echte Zustandsmaschine behandeln statt als losen Chattext
- Self-Improvement-Kandidaten aus Reflection, Runtime, Incidents und Observation dedupliziert und priorisiert erzeugen
- autonome Improvement-Tasks kontrolliert enqueuen, ausfuehren und mit Governance-Guardrails gegen Loops und Ueberbehauptung absichern
- OCR/Vision-Anfragen explizit routen (VisionStrategy), OOM-Events erkennen und telemetrisch erfassen ohne den Hot-Path zu gefaehrden
- Social-Media-Seiten und JavaScript-schwere Quellen ueber ScrapingAnt rendern und auslesen

## Systembild

```text
Canvas / Telegram / Android / Terminal
                |
                v
       MCP Server (FastAPI)
                |
                v
        Main Dispatcher
                |
                v
        Meta Orchestration
                |
      +---------+---------+---------+---------+
      |         |         |         |         |
      v         v         v         v         v
   executor   research   visual    system   weitere Spezialisten
      |         |         |         |
      +---------+---------+---------+
                |
                v
          Tool Registry V2
                |
                v
    Browser / Web / OCR / Vision / Files / Search / ...

Querliegende Schichten:
- Conversation State + Topic History
- Preference / Instruction Memory
- Pending Workflow + Auth Session State
- Longrunner / C4 Transport
- Autonomy Observation
- Improvement Candidate Pipeline (E1–E4)
- Vision Router + Telemetrie (C3)
```

## Kernkomponenten

| Bereich | Hauptdateien | Aufgabe |
| --- | --- | --- |
| MCP-Server | `server/mcp_server.py` | HTTP-API, `/chat`, SSE, Session-Capsules, Health, zentrale Observation-Hooks |
| Dispatcher | `main_dispatcher.py` | Frontdoor-Routing, schnelle Intent-Pfade, Specialist-Delegation |
| Meta-Orchestrierung | `agent/agents/meta.py`, `orchestration/meta_orchestration.py`, `orchestration/meta_response_policy.py` | Turn-Verstehen, Kontext-Bundle, Antwortmodus, Handoffs |
| Gespraechszustand | `orchestration/conversation_state.py`, `orchestration/topic_state_history.py`, `orchestration/turn_understanding.py` | aktives Thema, aktives Ziel, Open Loops, Turn-Typen, Rehydration |
| Memory | `orchestration/preference_instruction_memory.py` | thematische Präferenzen und Instruktionen |
| Specialist Context | `orchestration/specialist_context.py`, `orchestration/specialist_context_eval.py`, `agent/agent_registry.py` | Context-Propagation, Alignment, Ruecksignale |
| Approval/Auth | `orchestration/approval_auth_contract.py`, `orchestration/pending_workflow_state.py`, `orchestration/auth_session_state.py` | Approval, Login-Handover, Session-Reuse, Challenge-Resume |
| Observability | `orchestration/autonomy_observation.py` | Request-Korrelation, Runtime-Metriken, Phase-D-/Phase-E-Signale |
| Self-Improvement | `orchestration/improvement_candidates.py`, `orchestration/self_improvement_engine.py`, `orchestration/session_reflection.py` | Improvement-Kandidaten, Dedupe, Priorisierung, Freshness, Operator-Views |
| Improvement Execution | `orchestration/improvement_task_execution.py`, `orchestration/improvement_task_autonomy.py`, `orchestration/autonomous_runner.py` | autonome Task-Ausfuehrung, Cooldown-Guardrails, terminaler Contract |
| Vision/OCR Router | `tools/engines/vision_router.py`, `tools/engines/vision_telemetry.py` | explizites Strategie-Routing (7 Regeln), thread-safe Telemetrie-Ringpuffer, OOM-Erkennung |

## Aktuelle Entwicklungsrichtung

### Phase D — abgeschlossen

Alle D-Slices sind live:

- `D1` Auth Need Detection
- `D2` Approval + Consent Gate
- `D3` user-mediated Login
- `D4` Session Reuse + Chrome Credential Broker (D4b)
- `D5` Challenge Handover + Resume

### Phase E — E1 bis E4 abgeschlossen

Phase E fokussiert kontrollierte Selbstverbesserung statt ungegrenzter Autonomie.

Abgeschlossen:

- `E1` Improvement Signal Pipeline: Normalisierung, Taxonomie, Dedupe, Priorisierung, Incident-/Observation-Einzug, Freshness/Decay, Operator-Views
- `E2` Weakness-to-Task Compiler: Evidence-aware Compiler, Promotion Gate
- `E3` Execution Bridge + Managed Autonomy: Guardrails gegen Improvement-Loops und Erfolgs-Ueberbehauptung, Cooldown-Regeln fuer terminale Wiederholungen
- `E4` Terminaler Improvement-Contract: `blocked` / `ended_unverified` / `verified`, Retry-Semantik, Queue-Status-Haertung

Naechster Block:

- `E5` Verifikationsschicht und Outcome-Messung

## Kanaele

- **Canvas**: reichster Kanal mit Chat, Runtime-Status, Longrunner-Anzeige und C4-SSE-Events
- **Telegram**: leichter mobiler Kanal mit sauberer Request-Korrelation und kurzen Follow-ups
- **Android**: mobiler nativer Kanal; der Repo-Fokus liegt aktuell auf Backend und Orchestrierung
- **Terminal**: direkter Operator-Zugang fuer Entwicklung, Diagnose und Runtime-Steuerung

## Schnellstart

### Lokal

```bash
git clone git@github.com:fatihaltiok/Agentus-Timus.git
cd Agentus-Timus

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Start in getrennten Terminals:

```bash
python server/mcp_server.py
python main_dispatcher.py
```

### Health Check

```bash
curl -sS http://127.0.0.1:5000/health
```

### Produktive systemd-Dienste

Typischerweise laufen:

- `timus-mcp`
- `timus-dispatcher`

Restart:

```bash
sudo systemctl restart timus-mcp timus-dispatcher
```

## Empfohlene Lesereihenfolge im Code

1. `server/mcp_server.py`
2. `main_dispatcher.py`
3. `agent/agents/meta.py`
4. `orchestration/meta_orchestration.py`
5. `orchestration/conversation_state.py`
6. `orchestration/specialist_context.py`
7. `orchestration/approval_auth_contract.py`
8. `orchestration/autonomy_observation.py`
9. `orchestration/improvement_candidates.py`
10. `orchestration/improvement_task_execution.py`
11. `tools/engines/vision_router.py`

## Wichtige Dokumente

- [Timus Architektur-Blueprint fuer Folgeprojekte](docs/TIMUS_ARCHITEKTUR_BLUEPRINT_FUER_FOLGEPROJEKTE_2026-04-11.md)
- [Zwischenprojekt: Allgemeine Mehrschritt-Planung](docs/ZWISCHENPROJEKT_ALLGEMEINE_MEHRSCHRITT_PLANUNG_2026-04-12.md)
- [Phase D Vorbereitung - Approval, Auth und User Handover](docs/PHASE_D_APPROVAL_AUTH_PREP.md)
- [Phase E Plan - Self-Improvement und kontrollierte Selbstpflege](docs/PHASE_E_SELF_IMPROVEMENT_PLAN.md)
- [Phase D0 Meta Context State Plan](docs/PHASE_D0_META_CONTEXT_STATE_PLAN.md)
- [Changelog Dev](docs/CHANGELOG_DEV.md)
- [Technische Gesamtdokumentation](docs/TIMUS_TECHNISCHE_GESAMTDOKUMENTATION_2026-04-06.md)

## Nicht Ziel dieser README

Diese README ist keine vollstaendige Entwicklungschronik und kein Ersatz fuer die technischen Plaene. Sie soll schnell beantworten:

- Was ist Timus?
- Wie ist das System aufgebaut?
- Wo steht das Projekt aktuell?
- Wo starte ich beim Lesen oder Betreiben?

Fuer feingranulare Fortschritte, Slice-Historie und Runtime-Nachweise sind die verlinkten Plan- und Changelog-Dateien die richtige Quelle.

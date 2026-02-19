# Timus Florence-2 + Nemotron Integrationsplan

Stand: 2026-02-19
Owner: Timus Core

## Ziel
Qwen2-VL als primaeren Vision-Pfad in `visual_nemotron_agent_v4` ersetzen durch:
1. Florence-2 lokal fuer UI-Detection + OCR mit Positionen.
2. Nemotron (OpenRouter) fuer Aktionsentscheidung.
3. Lokalen OpenAI-kompatiblen Fallback fuer LLM-Ausfallfaelle.

## Wichtige Timus-Anpassungen
Der bestehende Projektplan wird auf Timus-Architektur angepasst:
1. Tool-Registrierung erfolgt ueber `tools/tool_registry_v2.py` mit `@tool`, nicht ueber ein separates `tool_registry`-Dict.
2. MCP-Tool-Schemas werden automatisch aus `registry_v2` erzeugt.
3. Ziel-Agent-Datei ist `agent/visual_nemotron_agent_v4.py`.
4. Der bestehende Agent-Loop bleibt erhalten; wir ersetzen nur den Vision-Analysepfad.

## Architekturprinzipien fuer diese Migration
1. Keine Umgehung von MCP-/Policy-/Lane-Pfaden.
2. Keine harte Abhaengigkeit auf OpenRouter ohne Fallback.
3. Bestehende Milestone-5/6 Regression-Gates muessen weiterhin gruen bleiben.
4. Rollout mit Feature-Flags, damit schneller Rueckbau moeglich ist.

## Phase 1: Vorbereitung
1. Abhaengigkeiten sicherstellen:
   - `timm`, `einops`, `transformers`, `torch`, `Pillow`.
2. Optional Modelle vorab cachen:
   - `microsoft/Florence-2-base-ft`
   - optional lokales Fallback-Modell.
3. ENV-Konzept festlegen:
   - `FLORENCE2_ENABLED` (default: true fuer neuen Pfad)
   - `FLORENCE2_MODEL`
   - `LOCAL_LLM_URL`
   - `LOCAL_LLM_MODEL` (optional)

## Phase 2: Florence-Tool als Timus-Tool integrieren
Dateien:
1. `tools/florence2_tool/__init__.py`
2. `tools/florence2_tool/tool.py`
3. `tools/florence2_tool/setup_florence2.py` (optional/diagnostisch)

Umsetzung:
1. Florence-Kernfunktionen in `tool.py` kapseln (lazy model load, singleton).
2. MCP-RPCs als `@tool(...)` registrieren:
   - `florence2_health`
   - `florence2_full_analysis`
   - `florence2_detect_ui`
   - `florence2_ocr`
   - `florence2_analyze_region`
3. Rueckgabeformate stabil und JSON-seriell halten.

## Phase 3: MCP-Server anbinden
Datei:
1. `server/mcp_server.py`

Umsetzung:
1. `TOOL_MODULES` um `tools.florence2_tool.tool` erweitern.
2. Keine Sonderlogik fuer Schemas noetig; `registry_v2` liefert diese automatisch.
3. Health pruefen:
   - `/health`
   - `/get_tool_schemas/openai` enthaelt `florence2_*`.

## Phase 4: VisualNemotron v4 migrieren
Datei:
1. `agent/visual_nemotron_agent_v4.py`

Umsetzung:
1. In `VisionClient` neuen Florence-Primary-Pfad implementieren:
   - Screenshot -> MCP `florence2_full_analysis` -> strukturierte Beschreibung.
2. Bestehenden Nemotron-Entscheidungsfluss unveraendert lassen.
3. Bestehende Fallbacks erhalten:
   - GPT-4 Vision (optional)
   - Qwen-VL (bestehender Backup-Pfad), initial weiterhin verfuegbar.
4. Schrittweise Umschaltung per Flag:
   - `FLORENCE2_ENABLED=true` -> Florence primary
   - `FLORENCE2_ENABLED=false` -> alter Pfad.

## Phase 5: LLM-Fallback-Strategie
Dateien:
1. `agent/visual_nemotron_agent_v4.py`
2. optional `.env.example`

Umsetzung:
1. Nemotron bleibt Standard (`OPENROUTER_API_KEY`).
2. Bei Timeout/API-Fehler:
   - lokaler OpenAI-kompatibler Endpoint ueber `LOCAL_LLM_URL`.
3. Fallback nur fuer Decision-Layer, nicht fuer Florence-Detection.

## Phase 6: Tests und Verifikation
Checks:
1. Tool-Registrierung:
   - Florence-Tools im `/get_tool_schemas/openai` sichtbar.
2. Lokale Tool-Smoketests:
   - `florence2_health`
   - `florence2_full_analysis` auf Test-Screenshot.
3. Visual-Agent-Smoketest:
   - ein kurzer Task mit begrenzten Steps.
4. Bestehende Gates:
   - `pytest -q tests/test_milestone5_quality_gates.py`
   - `pytest -q tests/test_milestone6_e2e_readiness.py`
   - optional `python verify_milestone6.py`

## Phase 7: Rollout und Rueckfallplan
1. Rollout hinter Feature-Flag (`FLORENCE2_ENABLED`).
2. Bei Regression:
   - Flag auf `false`, alter Vision-Pfad aktiv.
3. Nach Stabilisierung:
   - Qwen-primary Pfad entkoppeln oder archivieren.

## Akzeptanzkriterien
1. Florence-Tools sind im MCP registriert und aufrufbar.
2. `visual_nemotron_agent_v4` nutzt Florence als Primary-Visionpfad.
3. Fallbacks funktionieren bei OpenRouter-Ausfall.
4. Milestone-5/6 Tests bleiben gruen.
5. Kein Bruch der bestehenden Dispatcher-/Memory-Architektur.

## Geplante Aenderungsdateien
1. `tools/florence2_tool/__init__.py` (neu)
2. `tools/florence2_tool/tool.py` (neu)
3. `tools/florence2_tool/setup_florence2.py` (neu, optional fuer Diagnose)
4. `server/mcp_server.py` (update)
5. `agent/visual_nemotron_agent_v4.py` (update)
6. optional `docs/timusnemotron.md` (dieses Dokument)

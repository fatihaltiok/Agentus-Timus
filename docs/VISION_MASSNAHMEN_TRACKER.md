# Vision Massnahmen Tracker (Milestone-gated)

Stand: 2026-02-20

Regel:
- Nach jedem Milestone wird das definierte Gate ausgefuehrt.
- Weiter zum naechsten Milestone nur bei 100% gruen.
- Bei rot wird im selben Milestone nachgebessert.

## Statusuebersicht

| Milestone | Ziel | Status | Gate |
|---|---|---|---|
| M0 | Baseline + Test-Gates | gruen (abgeschlossen) | `pytest -q tests/test_browser_isolation.py tests/test_florence2_hybrid_paddleocr.py tests/vision/test_m0_baseline_inventory.py` |
| M1 | Debug-Overlay-System | gruen (abgeschlossen) | `pytest -q tests/vision/test_debug_screenshot_tool.py tests/vision/test_verification_overlay_integration.py` |
| M2 | Koordinaten + DPI/Viewport | gruen (abgeschlossen) | `pytest -q tests/vision/test_coordinate_converter.py tests/vision/test_browser_dpr_scaling.py tests/vision/test_som_coordinate_contract.py` |
| M3 | OpenCV Multi-Scale Fallback | gruen (abgeschlossen) | `pytest -q tests/vision/test_opencv_template_matcher_tool.py tests/vision/test_hybrid_opencv_fallback.py` |
| M4 | Adaptive Reflection Vision | gruen (abgeschlossen) | `pytest -q tests/vision/test_reflection_visual_patterns.py tests/vision/test_reflection_adaptive_config.py tests/test_memory_hybrid_v2.py` |
| M5 | E2E Stabilitaet + Regression | gruen (abgeschlossen) | `pytest -q tests/e2e/test_vision_pipeline_e2e.py tests/e2e/test_vision_fail_recovery_e2e.py` |
| M6 | Abschlussvalidierung + Architekturabgleich | gruen (abgeschlossen) | `pytest -q tests/vision/test_architecture_alignment.py && pytest -q` |

## M0 - Baseline und Inventory

Umgesetzt:
- `tests/vision/test_m0_baseline_inventory.py` hinzugefuegt.
- Baseline-Pruefungen fuer:
  - Pflichtpfade (Dispatcher, MCP, Vision-Tools, Kern-Tests)
  - Tool-Registrierungsdeklarationen in Schluessel-Tools
  - Dispatcher-Routing fuer `visual`/`vision_qwen`/`visual_nemotron`
  - Gepinnte CI-Versionen aus `requirements-ci.txt`

Abschluss:
- Gate erfolgreich bestanden (24 passed).

Zusatzfix fuer stabile Gate-Ausfuehrung:
- `tools/browser_tool/persistent_context.py` gehaertet:
  - deterministische Shutdown-Timeouts
  - Force-Kill-Fallback fuer haengende Browserprozesse
  - `TIMUS_BROWSER_BACKEND=mock` Test-Backend (automatisch unter pytest, per Env auf real ueberschreibbar)

## M1 - Debug-Overlay-System

Ist-Stand:
- `tools/debug_screenshot_tool/tool.py` vorhanden und integriert.
- `tools/verification_tool/tool.py` schreibt bei Fail-Path Debug-Artefakte.
- Gate erfolgreich bestanden (4 passed).

## M2 - Koordinaten + DPI/Viewport

Umgesetzt:
- Neuer zentraler Converter: `utils/coordinate_converter.py`
  - normalisiert/pixel Umrechnung
  - Monitor-Offset + DPI/DPR Mapping
  - robuster Key-Contract (`x/y`, `click_x/click_y`, `center_x/center_y`)
- `tools/som_tool/tool.py`:
  - harte Aufloesungsannahmen entfernt (Referenzaufloesung jetzt dynamisch)
  - `use_zoom` ist kein No-op mehr (zweiter Zoom-Pass mit Rueckprojektion)
  - konsistenter Output-Contract um `center_x/center_y` erweitert
- `tools/browser_controller/controller.py`:
  - Vision-Klickpfad zieht Koordinaten robust aus allen Contract-Varianten
- `tools/visual_grounding_tool/tool.py`:
  - DPI/Offset-Umrechnung zentralisiert
  - Output fuer Text-Elemente auf konsistenten Koordinatenvertrag gehoben
- `tools/browser_tool/persistent_context.py` + `tools/browser_tool/tool.py`:
  - Viewport/DPR-Kontext explizit im Session-Status

Abschluss:
- M2-Gate erfolgreich bestanden (8 passed).
- Zusatz-Regression (M0+M1+M2 kombiniert) erfolgreich: 36 passed.

## M3 - OpenCV Multi-Scale Fallback

Umgesetzt:
- Neuer Tool-Pfad:
  - `tools/opencv_template_matcher_tool/tool.py`
  - `tools/opencv_template_matcher_tool/__init__.py`
- Neues Template-Asset-Verzeichnis:
  - `assets/templates/README.md`
- Runtime-Integration:
  - `server/mcp_server.py` importiert `tools.opencv_template_matcher_tool.tool`
- Pipeline-Fallback:
  - `tools/hybrid_detection_tool/tool.py` erweitert um OpenCV-Template-Fallback
  - Tool-Parameter erweitert (`template_name`, `enable_template_fallback`)
- Screen-Contract-Anbindung:
  - `tools/screen_contract_tool/tool.py` nutzt optional `template_name` und mapped Methode auf `template_matching`

Tests:
- `tests/vision/test_opencv_template_matcher_tool.py`
- `tests/vision/test_hybrid_opencv_fallback.py`

Abschluss:
- M3-Gate erfolgreich bestanden (4 passed).
- Zusatz-Regression (M0-M3 kombiniert) erfolgreich: 40 passed.

## M4 - Adaptive Reflection fuer Vision

Umgesetzt:
- `memory/reflection_engine.py` erweitert:
  - Analyse von Debug-Artefakten zu wiederkehrenden visuellen Failure-Signaturen
  - `vision_adaptive_config` Load/Save mit Pending/History-Workflow
  - explizite Freigabe-/Ablehnungs-APIs (`approve_vision_adaptation`, `reject_vision_adaptation`)
  - keine Auto-Aktivierung ohne Human-Freigabe
- `tools/reflection_tool/tool.py` erweitert:
  - `reflection_analyze_visual_patterns`
  - `reflection_list_pending_adaptations`
  - `reflection_approve_adaptation`
  - `reflection_reject_adaptation`
- `data/vision_adaptive_config.json` neu (Policy mit `auto_apply=false`)
- `tools/hybrid_detection_tool/tool.py`:
  - nutzt nur `active`-Werte aus Adaptive-Config (keine pending Werte)
  - adaptive OpenCV-Threshold + Template-Kandidaten (nur nach Freigabe wirksam)

Tests:
- `tests/vision/test_reflection_visual_patterns.py`
- `tests/vision/test_reflection_adaptive_config.py`

Abschluss:
- M4-Gate erfolgreich bestanden (17 passed inkl. `tests/test_memory_hybrid_v2.py`).
- Zusatz-Regression (M0-M4 kombiniert) erfolgreich: 57 passed.

## M5 - E2E Stabilitaet + Regression

Umgesetzt:
- `tests/e2e/test_vision_pipeline_e2e.py`:
  - stabiler Success-Path (wiederholbar, Laufzeitgrenze, konsistente Koordinaten/Methode)
  - Pipeline-Qualitaets-Logs (`pipeline_log`, `attempt_count`, finaler Stage-Record)
- `tests/e2e/test_vision_fail_recovery_e2e.py`:
  - Recovery-Path: erster Klick fehlschlaegt, zweiter Versuch erfolgreich (`recovered=True`, `attempt_count=2`)
  - Failure-Stabilitaet: wiederholte Runs mit konsistentem unrecovered Ergebnis (`success=False`, `attempt_count=2`)

Abschluss:
- M5-Gate erfolgreich bestanden (4 passed).

## M6 - Abschlussvalidierung + Architekturabgleich

Umgesetzt:
- Neuer Architekturabgleich-Test:
  - `tests/vision/test_architecture_alignment.py`
  - prueft MCP-Registrierung zentraler Vision-Module, Koordinaten-/DPI-Contracts,
    Hybrid-Recovery-/Pipeline-Qualitaetsmarker, sichere Adaptive-Policy und
    Existenz der Milestone-Test-Suiten.
- Pytest-Standardlauf stabilisiert:
  - `pytest.ini` erweitert um
    - `testpaths = tests` (fokussierter Standardlauf auf gepflegte Suite)
    - `pythonpath = .` (robuste Paket-Imports fuer Top-Level-Module)
- Executor-Haertung fuer synchrone Tools:
  - `tools/tool_registry_v2.py`: Sync-Tools laufen standardmaessig direkt statt
    ueber `asyncio.to_thread` (optional per `TIMUS_SYNC_TOOL_USE_THREADPOOL=1`).
    Damit werden reproduzierbare Haenger in dieser Laufumgebung vermieden.
- Namespace klargezogen:
  - `utils/__init__.py` hinzugefuegt.

Abschluss:
- M6-Gate erfolgreich bestanden:
  - `pytest -q tests/vision/test_architecture_alignment.py` -> `5 passed`
  - `pytest -q` -> `220 passed, 3 skipped, 2 warnings`

## Nachweise pro Milestone

Pro Milestone dokumentieren:
1. Datum/Uhrzeit des Gate-Runs
2. Exakte Kommandos
3. Ergebnis (pass/fail + Kernfehler)
4. Durchgefuehrte Fixes im selben Milestone

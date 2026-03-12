# Zwischenstandsbericht 2026-03-11

## Kontext

Dieser Bericht fasst den aktuellen Stand nach den letzten Arbeiten an

- dem strukturierten Visual-Webflow,
- der mobilen Timus-Konsole,
- dem Voice-/Browser-Audio-Pfad,
- sowie kleineren Stabilitäts- und Research-Fixes

zusammen.

## 1. Visual-Agent: Webflow-Refactor

Der Visual-Agent wurde in vier Phasen von einem loseren "sehen und klicken"-Pfad zu einem strukturierteren Webflow-Modell weitergeführt.

### Phase 1: Plan-Schema + State-Modell

In `orchestration/browser_workflow_plan.py` existiert jetzt ein strukturierter Browser-Workflow-Kern:

- `BrowserWorkflowPlan`
- `BrowserWorkflowStep`
- `BrowserStateEvidence`

Ergänzt wurden:

- erlaubte Aktionen
- erlaubte Zustände
- erlaubte Evidenztypen
- erlaubte Recovery-Typen

Erste Referenzflows:

- `booking_search`
- `login_flow`
- `simple_form`

### Phase 2: Planner-Integration

Der `visual`-Agent nutzt den strukturierten Browser-Plan jetzt im Prompt-Kontext. Schritte werden nicht mehr nur als freie Liste an das Modell gegeben, sondern enthalten explizit:

- `action`
- `target`
- `expected_state`
- `timeout`
- `fallback`
- `success_signal`

### Phase 3: Ausführungs-Engine mit Recovery

In `agent/agents/visual.py` wurde eine echte strukturierte Ausführung ergänzt:

- schrittweise Plan-Ausführung
- harte State-Verifikation
- Fallback-Ketten statt kosmetischer Retries
- Ausführungs-Logging pro Schritt

Wichtige Eigenschaften:

- Zustände werden über Evidenz verifiziert (`url_contains`, `visible_text`, `dom_selector`, `visual_marker`)
- Recovery wechselt die Strategie tatsächlich
- der alte LLM-Navigationspfad bleibt als Fallback erhalten

### Phase 4: Verifikation + Benchmarks

Die Browser-Eval-Schicht in `orchestration/browser_workflow_eval.py` misst jetzt nicht nur Marker, sondern auch:

- State-Abdeckung
- Evidenz-Abdeckung
- Verifikationsschritte
- Recovery-Abdeckung

Damit existiert jetzt ein belastbarerer Benchmark-Rahmen für die ersten drei Referenzflows.

## 2. Mobile Konsole

Die mobile Konsole unter `console.fatih-altiok.com` wurde weiter als Hauptoberfläche vorbereitet.

### Bereits umgesetzt

- Reverse Proxy + HTTPS + Auth
- mobile Canvas-/Konsole-Struktur
- Status- und Chat-Schnitt
- Datei-/Dokumentpfade
- Voice-Orb und Voice-Zustandsanzeige

### Wichtiger Voice-Fix

Der frühere serverseitige Mikrofonpfad wurde für die Web-Konsole entschärft.

Neu:

- Browser nimmt Audio selbst auf
- Upload an `/voice/transcribe`
- Server transkribiert Audio-Bytes mit Whisper
- kein lokaler Mikrofonzugriff des Service-Prozesses für die Web-Konsole

Betroffene Dateien:

- `server/canvas_ui.py`
- `server/mcp_server.py`
- `tools/voice_tool/tool.py`

## 3. Weitere Fixes aus diesem Arbeitsblock

### Research / YouTube / DataForSEO

Der YouTube-Suchpfad wurde auf einen robusteren Live-Modus umgestellt:

- `tools/search_tool/tool.py`
- `tools/deep_research/youtube_researcher.py`

### Memory-Smoke-Fix

`memory.memory_system` priorisiert bei expliziter Session und `prefer_unresolved` jetzt das offene Session-Event sauberer.

Datei:

- `memory/memory_system.py`

## 4. Verifikation

Der aktuelle Stand wurde wiederholt gegen die vorhandenen Gates und gezielte Tests geprüft.

Wesentliche Ergebnisse:

- strukturierte Browser- und Visual-Tests grün
- Konsole-/Voice-Tests grün
- `python scripts/run_production_gates.py` mehrfach auf `READY`

Der Stand ist damit konsistent mit dem bestehenden Produktions-Gate-System.

## 5. Relevante Commits

Die wichtigsten Commits dieses Abschnitts:

- `50f78bd` `fix(research): prefer live youtube search for dataforseo`
- `f3f5369` `fix(memory): prioritize unresolved session recall`
- `fde2167` `feat(visual): add structured browser workflow execution`
- `1dd4d81` `fix(console): use browser audio transcription flow`
- `5ff3898` `chore(state): refresh roadmap and memory snapshots`

## 6. Offener Stand

Weiterhin offen bzw. bewusst noch nicht abgeschlossen:

- echtes Live-Tuning des Mobile-Layouts
- weitere Stabilisierung der Voice-Ausgabe im realen Smartphone-Betrieb
- Ausbau der allgemeinen Site-Profile für weitere Webseiten wie `x.com`, `youtube`, `linkedin`, `outlook`
- nächste Visual-Ausbaustufe über die aktuellen Referenzflows hinaus

## 7. Nächster sinnvoller Schritt

Der nächste sinnvolle Schritt ist, auf diesem Stand weiter aufzubauen, statt neue Parallelbaustellen zu öffnen:

1. Visual-Agent für weitere Webseitenklassen generalisieren
2. Mobile-/Voice-Livebetrieb gezielt nachschärfen
3. anschließend nächste größere Architekturachse angehen

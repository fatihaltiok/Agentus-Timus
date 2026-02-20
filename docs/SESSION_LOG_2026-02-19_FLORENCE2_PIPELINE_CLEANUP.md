# Session Log — 2026-02-19
# Florence-2 Pipeline Cleanup & Hybrid Vision Integration

**Datum:** 2026-02-19
**Bearbeiter:** Claude Sonnet 4.6 (Claude Code)
**Referenz:** `docs/ABSCHLUSSBERICHT_Florence2_Integration_2026-02-19.md`

---

## Übersicht

Aufbauend auf der Florence-2 Integration vom selben Tag wurden in dieser Session
vier eigenständige Problemstellungen identifiziert und behoben sowie eine neue
Hybrid-Vision-Pipeline (PaddleOCR + Florence-2 OD) konzipiert und implementiert.

---

## Problem 1 — Qwen-VL blockiert VRAM trotz Florence-2 Integration

### Problemstellung
Nach der Florence-2 Integration war `QWEN_VL_ENABLED=1` in der `.env` aktiv.
Beim Serverstart versuchte der MCP-Server die Qwen-VL Engine zu laden:
- Florence-2-large-ft: ~3 GB VRAM
- Qwen2-VL-2B-Instruct: ~5 GB VRAM
- Gesamt: ~8 GB — plus alle anderen Prozesse → VRAM-Druck auf RTX 5070 Ti (16 GB)

Zudem war die Qwen-VL Engine laut Docstring für **RTX 3090** optimiert, nicht für
die vorhandene RTX 5070 Ti.

### Lösungsweg
1. `.env`: `QWEN_VL_ENABLED=1` → `QWEN_VL_ENABLED=0`
2. `server/mcp_server.py` `TOOL_MODULES`: `tools.qwen_vl_tool.tool` entfernt
3. `agent/visual_nemotron_agent_v4.py` `VisionClient`:
   - `_qwen_analyze()` entfernt
   - `_resize_for_qwen()` entfernt
   - `qwen_timeout` Attribut entfernt
   - Docstring + `analyze()` von dreistufig → zweistufig aktualisiert
   - FALLBACK-2 Qwen-VL Block entfernt, Fehlermeldung ergänzt

### Ergebnis
- Qwen-VL Engine lädt nicht mehr beim Serverstart → kein unnötiger VRAM-Verbrauch
- `VisionClient` ist sauber zweistufig: **Florence-2 → GPT-4 Vision (Fallback)**
- Kein toter Code mehr im MCP-Server

---

## Problem 2 — `qwen_web_automation` Fehler im MainDispatcher (Method not found)

### Problemstellung
Log-Ausgabe:
```
⏱️ Status | Agent VISUAL | TOOL_ACTIVE | qwen_web_automation
❌ MCP Tool Fehler: Method not found
⏱️ Status | Agent VISUAL | ERROR | qwen_web_automation: Method not found
```

Ursache: `main_dispatcher.py` hatte einen `SPECIAL_VISION_QWEN`-Block (~155 Zeilen),
der `qwen_web_automation` via JSON-RPC aufrief. Das Tool war aber aus dem MCP-Server
entfernt worden. Zusätzlich mappten alle visuellen Agent-Namen auf `SPECIAL_VISION_QWEN`:

```python
"visual"      → "SPECIAL_VISION_QWEN"
"vision_qwen" → "SPECIAL_VISION_QWEN"
"vision"      → "SPECIAL_VISION_QWEN"
"qwen"        → "SPECIAL_VISION_QWEN"
```

### Lösungsweg
1. `AGENT_CLASS_MAP` in `main_dispatcher.py`: alle vier `SPECIAL_VISION_QWEN`-Einträge
   auf `SPECIAL_VISUAL_NEMOTRON` umgeleitet (Florence-2 + Nemotron)
2. Gesamten `SPECIAL_VISION_QWEN`-Block entfernt (Meta-Planung + `qwen_web_automation`-Aufruf)

### Ergebnis
- `agent_name="visual"` landet jetzt direkt im `SPECIAL_VISUAL_NEMOTRON`-Pfad
- Kein `Method not found`-Fehler mehr
- `SPECIAL_VISION_QWEN` existiert nicht mehr im Codebase

---

## Problem 3 — Workflow-Analyse & Präzisionslücken identifiziert

### Problemstellung
Analyse des aktiven Workflows ergab vier Schwachstellen:

| # | Problem | Impact |
|---|---|---|
| 3a | `summary_prompt` enthält nur Mittelpunkte, keine Elementgröße | Nemotron kann nicht einschätzen ob ein 5px vs. 120px Button |
| 3b | Keine Bildschirmauflösung im Prompt | Nemotron kann Koordinaten nicht auf Plausibilität prüfen |
| 3c | Mikro-Artefakte (< 10px) von Florence-2 im Prompt | Rauschen in Nemotron-Entscheidung |
| 3d | Koordinaten-Fallback in `execute_action` nutzt GPT-4 Vision | Inkonsistent, API-Kosten, langsamer als lokales Florence-2 |
| 3e | UI-Scan nur alle 3 Schritte, nicht nach Klick | `self.desktop.elements` bis zu 2 Schritte veraltet nach UI-Änderung |

Diese Punkte wurden durch die Hybrid-Pipeline (Problem 4) vollständig adressiert.

---

## Problem 4 / Hauptverbesserung — Hybrid Vision Pipeline

### Problemstellung
`florence2_full_analysis` führte 3 serielle Florence-2 Inferenzen aus:
`<CAPTION>` + `<OD>` + `<OCR_WITH_REGION>`. Das integrierte Florence-2 OCR
(`<OCR_WITH_REGION>`) ist kein spezialisiertes OCR-Tool — es liefert keine
Confidence-Scores und ist weniger präzise als dedizierte OCR-Engines.

PaddleOCR war im Projekt bereits vorhanden (`tools/engines/ocr_engine.py`),
wurde aber im Vision-Agenten-Pfad nicht genutzt.

### Lösungsweg — Neue Hybrid-Architektur

**Neue Aufgabenteilung:**
- **Florence-2**: nur `<CAPTION>` + `<OD>` → Beschreibung + UI-Elemente mit Bboxes
- **PaddleOCR**: Text-Erkennung + Bboxes + Confidence-Scores (läuft auf CPU, kein VRAM-Konflikt)

**Implementierte Änderungen in `tools/florence2_tool/tool.py`:**

1. Lazy PaddleOCR Instanz (`_get_paddle_ocr()`) — separate Instanz, unabhängig
   von der zentralen `ocr_engine_instance`, läuft bewusst auf CPU
2. `_paddle_ocr_texts(image)` — liefert `[{text, bbox, center, confidence}]`
3. `_hybrid_analysis(image)`:
   - Mikro-Element-Filter: `MIN_DIM=10` — Elemente < 10px in einer Dimension werden ignoriert
   - Elementgröße im Prompt: `size=WxHpx`
   - Bildschirmauflösung im Prompt: `Auflösung: 1920x1080px`
   - Klar getrennte Sektionen: `INTERAKTIVE ELEMENTE` (Florence-2) vs. `TEXT AUF DEM BILDSCHIRM` (PaddleOCR)
4. Neues MCP-Tool `florence2_hybrid_analysis` registriert

**Implementierte Änderungen in `agent/visual_nemotron_agent_v4.py`:**

5. `VisionClient._florence2_analyze()` → ruft `florence2_hybrid_analysis` auf,
   Fallback zu `florence2_full_analysis` bei Fehler
6. `_vision_click` → nutzt `florence2_detect_ui` statt GPT-4 Vision für
   Koordinaten-Fallback (lokal, kein API-Aufruf)
7. Scan nach Klick: nach `click`/`click_and_focus` ohne Fehler →
   `await asyncio.sleep(0.8)` + `scan_elements()` sofort

### Ergebnis — Neues summary_prompt Format

```
Auflösung: 1920x1080px
Bildschirm: Eine Browser-Seite mit Suchfeld und Navigationselementen

INTERAKTIVE ELEMENTE (12):
[1] BUTTON center=(420,310) size=80x30px
[2] INPUT center=(200,310) size=300x30px
...

TEXT AUF DEM BILDSCHIRM (8):
[A] "Hotel buchen" @ (150,200) conf=0.97
[B] "2 Personen" @ (300,250) conf=0.95
...
```

---

## Geänderte Dateien (Gesamtübersicht)

| Datei | Art | Beschreibung |
|---|---|---|
| `.env` | GEÄNDERT | `QWEN_VL_ENABLED=1` → `0` |
| `server/mcp_server.py` | GEÄNDERT | `tools.qwen_vl_tool.tool` aus `TOOL_MODULES` entfernt |
| `agent/visual_nemotron_agent_v4.py` | GEÄNDERT | Qwen aus VisionClient entfernt; hybrid + florence2_detect_ui Fallback; Scan nach Klick |
| `main_dispatcher.py` | GEÄNDERT | `SPECIAL_VISION_QWEN`-Block entfernt; alle Aliases → `SPECIAL_VISUAL_NEMOTRON` |
| `tools/florence2_tool/tool.py` | GEÄNDERT | PaddleOCR lazy init; `_hybrid_analysis()`; `florence2_hybrid_analysis` Tool |

---

## Workflow vorher vs. nachher

### Vorher
```
Screenshot → Florence-2 (<CAPTION> + <OD> + <OCR_WITH_REGION>) → summary_prompt
                                                                         ↓
                                                               Nemotron → PyAutoGUI
```
- Qwen-VL Engine im Hintergrund geladen (VRAM-Verschwendung)
- Koordinaten-Fallback via GPT-4 Vision (API-Kosten)
- OCR ohne Confidence-Scores
- Mikro-Artefakte im Prompt
- UI-Scan alle 3 Schritte

### Nachher
```
Screenshot ──┬── Florence-2 (<CAPTION> + <OD>) → INTERAKTIVE ELEMENTE + size
             └── PaddleOCR (CPU)               → TEXT + confidence
                            ↓
              Merged summary_prompt (Auflösung + getrennte Sektionen)
                            ↓
              Nemotron → florence2_detect_ui (lokal) → PyAutoGUI
                            ↓
              Nach Klick: sofortiger UI-Scan (0.8s delay)
```

---

## Nächste Schritte (optional)

1. **Produktionstest**: Agent VISUAL mit Booking.com-Task starten und Log auf
   `PaddleOCR geladen (CPU)` + `florence2_hybrid_analysis` prüfen
2. **PaddleOCR Sprache**: ggf. `lang="de"` oder `lang="german"` für deutschsprachige
   Seiten konfigurieren (aktuell: `en`)
3. **`florence2_full_analysis` deprecieren**: Sobald `florence2_hybrid_analysis`
   im Produktionsbetrieb stabil, kann das alte Tool aus dem MCP-Server entfernt werden

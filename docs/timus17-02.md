# Session Log — 17. Februar 2026

## Aufgabe: Meta-Agent JSON-Parsing + Loop-Detection Hardening

### Problem
Zwei Bugs verhinderten erfolgreiche Browser-Automatisierung:

1. **Meta-Agent JSON-Parsing:** Der Regex `\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}` konnte verschachteltes JSON aus Nemotron-Responses nicht parsen. Nemotron liefert `<think>...</think>`-Blocks und mehrstufig verschachteltes JSON — der Regex fand nur flaches JSON. Ergebnis: Fallback-Plan mit nur 3 generischen Schritten (navigate, wait, verify) ohne Suchbegriffe.

2. **Loop-Detection:** `recent_actions` war ein FIFO-Fenster mit 20 Eintraegen. Nach 20 anderen Aktionen wurde der Counter fuer eine wiederholte Aktion auf 0 zurueckgesetzt — identische Klicks auf (500,300) konnten 12x durchkommen. Zusaetzlich fehlte `_loop_warning` im Return-Dict bei `should_skip=True`.

3. **LoopDetector (VisualNemotronAgent):** MD5-Hash ueber `screenshot.tobytes()` war nicht robust gegen minimale Pixel-Aenderungen (Anti-Aliasing, Cursor-Blink). Ausserdem wurden nur exakte Action-Matches erkannt — Klicks auf (500,300) vs (510,305) galten als unterschiedlich.

### Loesung

#### Fix 1: Robustes JSON-Extraction (Brace-Counting)
- Neue Utility-Funktion `extract_json_robust()` in `agent/shared/json_utils.py`
- Entfernt `<think>...</think>` Blocks (Nemotron)
- Entfernt Markdown Code-Blocks
- Findet aeusserstes `{ ... }` via Brace-Counting (beliebige Verschachtelungstiefe)
- Wird in `meta.py` und `base_agent.py` importiert (keine zirkulaere Abhaengigkeit)

#### Fix 2: Task-aware Fallback-Plan
- Neue Methode `_extract_search_terms()` extrahiert Suchbegriffe aus dem Task
- Patterns: "such nach X auf Y", "search for X on Y"
- Fallback-Plan enthaelt jetzt type+click Steps fuer Suchbegriffe

#### Fix 3: Persistenter Loop-Counter
- Neues `action_call_counts: Dict[str, int]` in BaseAgent (vergisst nie)
- FIFO-Fenster von 20 auf 40 erhoeht
- `_loop_warning` wird jetzt auch bei `should_skip=True` im Return-Dict gesetzt

#### Fix 4: Perceptual Hashing + Proximity
- `_perceptual_hash()`: 8x8 Average-Hash statt MD5 (robust gegen Pixel-Rauschen)
- `_actions_similar()`: Koordinaten-Proximity-Check (±30px) statt exakter Match

### Geaenderte Dateien

| Datei | Aktion |
|-------|--------|
| `agent/shared/json_utils.py` | Neu erstellt — `extract_json_robust()` mit Brace-Counting |
| `agent/agents/meta.py` | JSON-Parsing auf `extract_json_robust` umgestellt, `_extract_search_terms()` + Fallback erweitert |
| `agent/base_agent.py` | `action_call_counts` Dict, Fenster 20->40, `_loop_warning` bei skip, `extract_json_robust` Import |
| `agent/visual_nemotron_agent_v4.py` | LoopDetector: `_perceptual_hash()`, `_actions_similar()` mit Proximity |

### Verifizierung
- Syntax-Check: alle 4 Dateien bestanden (`ast.parse`)
- Keine zirkulaeren Imports (json_utils in shared, importiert von meta.py und base_agent.py)

### Git
- Commit: `125f99d` — fix: Meta-Agent JSON-Parsing (Brace-Counting) + Loop-Detection Hardening
- Gepusht nach: `origin/main`

### Naechste Schritte (offen)
- Unit-Tests fuer `extract_json_robust()` mit Nemotron-Responses (inkl. `<think>` Blocks)
- Unit-Tests fuer `action_call_counts` Persistenz und `_loop_warning` bei skip
- Manueller Test: ebay.de Task ausfuehren, pruefen dass Plan Suchbegriffe enthaelt
- Perceptual Hash Threshold tunen (aktuell exakter Match, evtl. Hamming-Distance einfuehren)

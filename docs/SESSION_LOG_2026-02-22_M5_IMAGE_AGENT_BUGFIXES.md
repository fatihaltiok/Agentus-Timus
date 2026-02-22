# Session-Log 2026-02-22 — M5 ImageAgent + Upload-Bugfixes

**Datum:** 2026-02-22
**Schwerpunkte:** M5 ImageAgent (Qwen 3.5 Plus), Upload-Pfad-Bugfixes (file_system_tool + mcp_server + canvas_ui)

---

## Bugfix — Upload-Pipeline (relative Pfade)

### Problem

Beim Hochladen einer Bilddatei über den Canvas-Chat konnte der Agent die Datei nicht finden:

1. `file_system_tool/_resolve_path`: Relative Pfade wurden gegen `Path.home()` (`/home/fatih-ubuntu`) aufgelöst statt gegen `project_root` (`/home/fatih-ubuntu/dev/timus`). Ein Upload-Pfad wie `data/uploads/xyz.jpeg` wurde zu `/home/fatih-ubuntu/data/uploads/xyz.jpeg` statt `/home/fatih-ubuntu/dev/timus/data/uploads/xyz.jpeg`.

2. `canvas_ui.py`: Das Frontend trug den relativen Pfad in das Chat-Input-Feld ein — der Agent bekam nie einen absoluten Pfad.

### Lösung (3 Dateien)

**`tools/file_system_tool/tool.py`:**
- `_PROJECT_ROOT = Path(__file__).resolve().parents[2]` hinzugefügt
- `_resolve_path`: relative Pfade → `_PROJECT_ROOT / path` statt `Path.home() / path`

**`server/mcp_server.py`:**
- Upload-Response enthält jetzt `abs_path: str(dest.resolve())` zusätzlich zu `path` (rel)

**`server/canvas_ui.py`:**
- Chat-Input verwendet `data.abs_path || data.path` — Agent bekommt immer absoluten Pfad

---

## M5 — ImageAgent

### Problem

Kein Agent war für das Analysieren hochgeladener Bilddateien zuständig:
- `reasoning` → kein Vision-Support
- `visual` → nur Live-Screenshots (Desktop-Automation), nicht Datei-Analyse
- `creative` → nur Bild-Erstellen, nicht Analysieren

### Modell-Wahl

Ursprünglich war `claude-sonnet-4-6` (Anthropic) erwogen — zu teuer.
Gewählt: `qwen/qwen3.5-plus-02-15` (OpenRouter) — Vision-fähig (text, image, video), deutlich günstiger ($0,40/$2,40 per M Token).

### Implementierung (4 Dateien)

**`agent/prompts.py`** — `IMAGE_PROMPT_TEMPLATE` hinzugefügt:
- Deutsch-sprachig, beschreibt Aufgabe: Bildinhalte analysieren (Personen, Objekte, Text, Farben, Kontext)

**`agent/agents/image.py`** *(neu)*:
- `ImageAgent(BaseAgent)`, `max_iterations=1` (kein Tool-Loop, direkter LLM-Call)
- Extrahiert absoluten Bildpfad per Regex aus dem Task-String
- Liest Datei von Disk → Base64-Encoding
- Automatische MIME-Type-Erkennung (jpg/jpeg/png/webp/gif/bmp/tiff/avif)
- Baut OpenAI-kompatible Vision-Message (type: image_url, data:mime;base64,...)
- Ruft `_call_llm` direkt auf (OpenRouter via `_call_openai_compatible`)

**`agent/providers.py`**:
- `"image": ("IMAGE_MODEL", "IMAGE_MODEL_PROVIDER", "qwen/qwen3.5-plus-02-15", ModelProvider.OPENROUTER)`

**`main_dispatcher.py`**:
- Import `ImageAgent`
- `AGENT_CLASS_MAP`: `image`, `bild`, `foto` → `ImageAgent`
- `quick_intent_check`: `_IMAGE_EXTENSIONS` Regex — bei Bild-Erweiterungen im Query → `"image"` (höchste Priorität, vor allen anderen Checks)
- Dispatcher-Prompt: Agent 14 `image` beschrieben mit Beispielen und Regel Nr. 6

---

## Commits dieser Session

1. `fix(upload): abs_path in Upload-Response + relativer Pfad gegen project_root`
2. `feat(agents): M5 ImageAgent — Qwen3.5 Plus, automatisches Bild-Routing`
3. `docs: README + Session-Log für M5 + Upload-Bugfixes`

---

## Stand nach dieser Session

- **13 spezialisierte Agenten** (M1–M5 vollständig)
- **Upload-Pipeline** zuverlässig: absoluter Pfad → Agent findet Datei immer
- **Bild-Analyse**: automatisches Routing bei Bild-Erweiterungen → ImageAgent → Qwen3.5 Plus

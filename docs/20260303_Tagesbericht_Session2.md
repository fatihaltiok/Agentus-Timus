# Tagesbericht Session 2: Deep Research v6.0, PDF-Layout-Fix, OpenAI-Key-Fix, Reasoning-Timeout
**Datum:** 2026-03-03 (Session 2, ca. 10:00–23:30 Uhr)
**Autor:** Fatih Altiok + Claude Code
**Status:** ✅ Abgeschlossen
**Commits:** 11 Commits

---

## Zusammenfassung

Intensiver Tag mit zwei großen Themensträngen. Vormittags: Fertigstellung und Stabilisierung von **Deep Research v6.0** — YouTube-Integration, ImageCollector, WeasyPrint-PDF und alle 6 Phasen des Implementierungsplans. Nachmittags: Debugging eines leeren Narrativs durch OpenAI-Key-Problem und CSS-Flexbox-Bug im PDF. Abends: README-Update mit v3.4-Inhalten. Spät abends: Diagnose und Fix eines 504-Timeout-Problems beim Reasoning-Agent via Telegram.

Insgesamt 11 Commits, 3 vollständige Fehlerketten diagnostiziert und behoben.

---

## 1. Deep Research v6.0 — Phase 1–6 Vollintegration

### Ausgangslage

Deep Research v5.1 erzeugte zwei Ausgabedateien: einen analytischen Markdown-Bericht und einen narrativen Lesebericht. YouTube-Quellen, Bilder und PDF-Export fehlten.

### Phase 1 — DataForSEO YouTube-Tools (`search_youtube`, `get_youtube_subtitles`)

**Datei:** `tools/search_tool/tool.py`

Zwei neue `@tool`-Funktionen:

- `search_youtube(query, max_results, language_code)` — POST `/v3/serp/youtube/organic/live/advanced`
- `get_youtube_subtitles(video_id, language_code)` — POST `/v3/serp/youtube/video_subtitles/live/advanced`, Fallback de→en, max 8000 Zeichen

**Commit:** `feat(search): search_youtube + get_youtube_subtitles via DataForSEO`

---

### Phase 2 — YouTubeResearcher

**Datei:** `tools/deep_research/youtube_researcher.py`

```
search_youtube() → bis zu 3 Videos
→ get_youtube_subtitles() → Transkript
→ qwen3.5-plus (OpenRouter) → Fakten-Extraktion + key_quote
→ NVIDIA NIM (Nemotron Nano 2 VL) → Thumbnail-Analyse
→ session.unverified_claims mit source_type="youtube"
```

Eingebaut in `start_deep_research()` mit Feature-Flag `DEEP_RESEARCH_YOUTUBE_ENABLED=true`.

**Commit:** `feat(deep_research): YouTubeResearcher — DataForSEO + qwen3.5-plus + NVIDIA NIM`

---

### Phase 3 — Längerer Lesebericht (2500–5000 Wörter)

**Datei:** `tools/deep_research/tool.py` — `_create_narrative_synthesis_report()`

- `max_completion_tokens=6000` (war: 2500)
- Prompt-Erweiterungen: Mindestlänge 2500 Wörter, YouTube-Quellen mit `[Video: Titel]`, direkte Zitate

**Commit:** `feat(deep_research): Längerer Lesebericht (2500-5000 Wörter, YouTube integriert)`

---

### Phase 4 — ImageCollector

**Datei:** `tools/deep_research/image_collector.py`

```
collect_images_for_sections(sections, query, max_images=4)
→ search_images (DataForSEO) → Download via requests → Pillow-Validierung
→ Fallback: DALL-E generate_image
→ Speicherort: results/img_{sha256[:8]}.jpg
```

**Commit:** `feat(deep_research): ImageCollector — Web-Bild + DALL-E Fallback`

---

### Phase 5 — PDF-Builder (fpdf2 → WeasyPrint)

**Ursprünglich:** `tools/deep_research/pdf_builder.py` mit fpdf2.

**Problem:** fpdf2 kann keine codierten Sonderzeichen (ä, ö, ü, ß) ohne externe Fonts korrekt rendern. Unicode-Texte wurden verstümmelt.

**Lösung:** Kompletter Wechsel auf **WeasyPrint + Jinja2**:

- `pdf_builder.py` → rendert Jinja2-Template zu HTML → WeasyPrint → PDF
- `report_template.html` → A4-Layout, Titelseite (dunkelblau + Gold), Inhaltsverzeichnis, Abschnitte mit Bildern, Quellenverzeichnis
- Volle Unicode-Unterstützung durch HTML/CSS-Rendering

**Commits:**
- `feat(deep_research): ResearchPDFBuilder — A4 PDF mit Bildern (fpdf2)`
- `refactor(deep_research): fpdf2 → WeasyPrint + Jinja2 für professionelles PDF-Layout`

---

### Phase 6 — Vollintegration

**Datei:** `tools/deep_research/tool.py` — `generate_research_report()`

Alle 3 Ausgabedateien pro Recherche:

| Datei | Inhalt |
|-------|--------|
| `DeepResearch_Academic_*.md` | Analytischer Bericht mit Faktenverifikation |
| `DeepResearch_Bericht_*.md` | Narrativer Lesebericht (2500–5000 Wörter) |
| `DeepResearch_PDF_*.pdf` | A4-PDF mit Titelseite, Bildern, Quellenverzeichnis |

Feature-Flags: `DEEP_RESEARCH_YOUTUBE_ENABLED`, `DEEP_RESEARCH_IMAGES_ENABLED`, `DEEP_RESEARCH_PDF_ENABLED`

**Commit:** `feat(deep_research): v6.0 Vollintegration — YouTube+Bilder+PDF+5000-Wörter-Bericht`

---

## 2. Debugging: OpenAI Client + leeres Narrativ

### Problem

Erster echter Recherche-Lauf ergab: Narrativer Bericht war leer (0 Wörter). Ursache unklar.

### Diagnose

**Fehlerkette 1 — Falsches Backend:**
`_make_client()` hatte gpt-5.2 zu **Inception Labs** (mercury-coder) geroutet. Das ist falsch — Inception Labs ist nur für den Developer Agent. Timus nutzte für Deep Research den falschen LLM-Endpoint.

**Fehlerkette 2 — OpenAI API Key abgelaufen:**
Der bisherige Key war ungültig (401). Fatih stellte einen neuen Key bereit.

**Fehlerkette 3 — `max_tokens` vs. `max_completion_tokens`:**
gpt-5.2 ist ein neueres OpenAI-Modell und braucht `max_completion_tokens` statt `max_tokens`. Der alte Parameter wurde stillschweigend ignoriert → Narrativ wurde intern auf Standardlänge abgeschnitten oder leer zurückgegeben.

### Fix

```python
# tools/deep_research/tool.py

# Revert: Einfacher OpenAI-Client ohne Inception-Routing
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Neue Hilfsfunktion
NEW_API_MODELS = {"gpt-5", "gpt-4.5", "o1", "o3", "o4", "gpt-5.2"}

def _get_token_param_name(model: str) -> str:
    for prefix in NEW_API_MODELS:
        if prefix in model.lower():
            return "max_completion_tokens"
    return "max_tokens"
```

Ergebnis dritter Lauf: **8 Quellen, 109 Fakten, 2941 Wörter, PDF 3,5 MB** ✅

**Commit:** `fix(deep_research): OpenAI client für gpt-5.2 + CSS float statt flex im PDF`

---

## 3. PDF-Layout-Fix: Flexbox → Float

### Problem

PDF Seite 3 zeigte nur eine Überschrift, der Inhalt erschien auf Seite 4. Leere Seite entstand durch WeasyPrint + CSS `display: flex`.

### Ursache

WeasyPrint behandelt Flex-Container als atomare Einheit. Ist der Container zu groß für die aktuelle Seite, bricht WeasyPrint **vor** dem Container um — die Überschrift, die außerhalb des Containers steht, bleibt allein auf der vorherigen Seite zurück.

### Fix

```css
/* VORHER — problematisch in WeasyPrint */
.section-with-image { display: flex; gap: 6mm; align-items: flex-start; }
.section-text { flex: 1; }
.section-image-wrap { flex: 0 0 75mm; }

/* NACHHER — korrekte Seitenumbrüche */
.section-image-wrap {
    float: right;
    width: 75mm;
    margin: 0 0 4mm 6mm;
}
.section-with-image::after {
    content: ""; display: table; clear: both;
}
```

CSS Float erlaubt natürliche Seitenumbrüche — Text fließt um das Bild herum, Seiten brechen innerhalb des Textflusses.

---

## 4. README-Update v3.4

**Datei:** `README.md` (1392 → 1486 Zeilen, +9 Änderungen)

Dokumentierte Neuerungen:

1. Einleitungstext: v3.4-Feature-Highlight unter dem Timus-Logo
2. Vergleichstabelle: "Erstellt automatisch PDF-Forschungsberichte"
3. Phase 17: Deep Research v6.0 vollständig dokumentiert
4. Aktueller Stand v3.4 (2026-03-03) Block
5. Mermaid-Diagramm: DR/DRY/DRI/DRP Knoten
6. Tools-Tabelle: deep_research v5.0→v6.0, `search_youtube`, `get_youtube_subtitles`
7. Projektstruktur: `deep_research/` Unterordner mit 5 Dateien
8. ENV-Variablen: `DEEP_RESEARCH_*` Feature-Flags
9. Nutzungsbeispiele: DeepResearchAgent v6.0

**Commit:** `docs(readme): Deep Research v6.0 — Phase 17, YouTube+Bilder+PDF, v3.4`

---

## 5. Reasoning-Timeout-Fix: NVIDIA NIM → OpenRouter

### Problem

Telegram-Nutzer erhielt bei Anfragen wie "vergleiche mich mit OpenClaw" eine Timeout-Meldung, danach einen **504 Gateway Timeout**.

### Diagnose

```
Anfrage "vergleich" → REASONING_KEYWORDS → ReasoningAgent
→ REASONING_MODEL=qwen/qwq-32b, REASONING_MODEL_PROVIDER=nvidia
→ Thinking-Modus aktiv (NEMOTRON_ENABLE_THINKING=true)
→ Komplexe Vergleichsfrage → QwQ-32B denkt > 2 Minuten
→ NVIDIA NIM bricht serverseitig mit 504 ab (kein Client-Timeout-Problem)
```

Das gleiche Problem hatte bereits Nemotron 49B auf NIM (2026-02-24 dokumentiert). Der Wechsel zu QwQ-32B hatte das Problem nur verlagert, nicht gelöst.

### Fix

```
REASONING_MODEL_PROVIDER=nvidia → openrouter
NVIDIA_TIMEOUT=120 → 360  (Fallback für zukünftige NIM-Nutzung)
```

OpenRouter verteilt die Last auf mehrere Provider und hat keinen harten Gateway-Timeout für lange Thinking-Sessions. **Test erfolgreich**, Vergleichsanfrage lieferte vollständige Antwort.

**Commit:** `fix(config): Reasoning Agent von NVIDIA NIM auf OpenRouter umgestellt`

---

## Commit-Übersicht

| Zeit | Hash | Beschreibung |
|------|------|--------------|
| 10:14 | `ef3bf0c` | feat(deep_research): Narrativer Lesebericht v5.1 |
| 11:09 | `a06bbce` | feat(search): search_youtube + get_youtube_subtitles |
| 11:14 | `e5414b0` | feat(deep_research): YouTubeResearcher |
| 11:46 | `703b573` | feat(deep_research): Längerer Lesebericht (2500-5000 Wörter) |
| 11:49 | `a4667b5` | feat(deep_research): ImageCollector |
| 11:51 | `29bbee7` | feat(deep_research): ResearchPDFBuilder (fpdf2) |
| 11:58 | `818abe2` | feat(deep_research): v6.0 Vollintegration |
| 12:06 | `9c1f503` | refactor(deep_research): fpdf2 → WeasyPrint + Jinja2 |
| 12:11 | `83998b8` | fix(deep_research): PDF-Layout deutsches Datum + Leerräume |
| 16:53 | `4e2f16c` | fix(deep_research): OpenAI client + CSS float statt flex |
| 18:18 | `1414ccf` | docs(readme): Deep Research v6.0 — Phase 17, v3.4 |
| 23:12 | `a2f57cc` | fix(config): Reasoning Agent NVIDIA NIM → OpenRouter |

---

## Systemzustand nach Session

| Komponente | Stand |
|------------|-------|
| Deep Research | v6.0 ✅ — 3 Ausgabedateien, YouTube, Bilder, PDF |
| Reasoning Agent | QwQ-32B via OpenRouter ✅ (kein 504 mehr) |
| OpenAI API | gpt-5.2 ✅ — neuer Key, `max_completion_tokens` korrekt |
| WeasyPrint PDF | Float-Layout ✅ — keine leeren Seiten mehr |
| README | v3.4 ✅ — Phase 17, Mermaid, Tools-Tabelle |
| Autonomy Score | 86.25/100 (very_high) |

---

## Erkenntnisse

1. **NVIDIA NIM ist instabil für lange Thinking-Tasks** — jedes Heavy-Reasoning-Modell (Nemotron 49B, QwQ-32B) liefert früher oder später 504. OpenRouter ist die robustere Alternative.
2. **WeasyPrint + Flexbox = Seitenumbruch-Probleme** — Float ist die sichere Wahl für mehrspaltige PDF-Layouts mit WeasyPrint.
3. **OpenAI API-Versionen divergieren** — neuere Modelle (gpt-5.x, o-Reihe) brauchen `max_completion_tokens` statt `max_tokens`. Eine zentrale Hilfsfunktion verhindert stille Fehler.
4. **Feature-Flags zahlen sich aus** — alle neuen Deep-Research-Komponenten (YouTube, Bilder, PDF) können unabhängig deaktiviert werden, was Debugging erheblich vereinfacht.

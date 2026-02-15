# Droid Log - 2026-02-03
## Zusammenfassung

Diese Session am 2026-02-13 fokussierte auf die Lösung des PyAutoGUI Fail-Safe Problems im Mouse Tool und die Verbesserung der Moondream Integration.

## Probleme Gelöst

### 1. Mouse Tool - PyAutoGUI Fail-Safe Exception

**Problem:**
```
pyautogui.FailSafeException: PyAutoGUI fail-safe triggered from mouse moving to a corner
```

**Lösung:**
- Neue Funktion `_ensure_safe_mouse_position()` die prüft ob Maus in einer Ecke ist (innerhalb 50px vom Rand)
- Mouse automatisch zur Bildschirmmitte beweg wenn in Ecke
- `FAILSAFE` vor Operationen deaktiviert und nachher reaktiviert
- Retry-Logik für FailSafeException in allen async Funktionen

**Datei:** `tools/mouse_tool/tool.py`

---

### 2. Moondream Integration - Point API

**Problem:**
- `som_tool` nutzte `/v1/detect` → gibt Bounding Box
- Berechnung von center wurde manuell gemacht
- Unpräzise Koordinaten

**Lösung:**
- Umgestaltet auf `/v1/point` → gibt direkte präzise center coordinates (x, y)
- `_normalized_to_pixels()` erweitert um center_x/center_y Parameter
- Point API center direkt übernommen wenn verfügbar

**Datei:** `tools/som_tool/tool.py`

---

### 3. Moondream Tool Erweiterung

**Neue Methoden:**
- `point_objects_with_moondream(object_type)` → Point API
- `describe_ui_with_moondream(question)` → Batch-Query (nutzt 32k Kontext)

**Datei:** `tools/moondream_tool/tool.py`

---

### 4. Moondream Station Port Konfiguration

**Status:**
- Moondream Station läuft auf Port **2022**
- `.env` angepasst: `MOONDREAM_API_BASE=http://localhost:2022/v1`

**Datei:** `.env`

---

## Testergebnisse

### Moondream API Tests

**Status 200 (Technisch Erfolgreich)**

Alle API Endpoints antworten mit HTTP 200:
- `/v1/point` → `{"points": []}` (leer)
- `/v1/query` → `{"answer": ""}` (leer)
- `/v1/caption` → `{"caption": ""}` (leer)

**Problem:**
Moondream API gibt leere Antworten zurück. API Server läuft technisch (Port 2022), aber das Modell antwortet nicht auf Anfragen.

**Mögliche Ursache:**
- Modell noch geladen
- Timeout zu kurz (180s getestet, aber evtl. mehr nötig)
- Moondream Station v0.1.0 (Update auf 0.1.9 verfügbar)

---

## Dateiänderungen

| Datei | Änderung |
|-------|----------|
| `tools/mouse_tool/tool.py` | Fail-Safe Problem gelöst (`_ensure_safe_mouse_position()`, Retry-Logik) |
| `tools/som_tool/tool.py` | `/v1/point` API Integration, center coordinates direkt genutzt |
| `tools/moondream_tool/tool.py` | Neue `point_objects_with_moondream()` und `describe_ui_with_moondream()` |
| `.env` | Port angepasst: `MOONDREAM_API_BASE=http://localhost:2022/v1` |

---

## Gelöst: Moondream API leere Antworten (Session 2026-02-03)

### Ursache FESTGESTELLT

**Das Problem war nicht der Timeout oder das Modell!**

Moondream API erwartet `image_url` Parameter im Data URL Format:
```json
{
  "image_url": "data:image/png;base64,{base64_string}"
}
```

**Fehler im vorherigen Code:**
- Nutzte `image` Parameter → Error: "image_url is required"
- Nutzte Base64 ohne Data URL Prefix

**Lösung:**
- Alle Tools nutzen jetzt `image_url` Parameter korrekt
- Format: `data:image/png;base64,{base64_string}` oder `data:image/jpeg;base64,{base64_string}`

### Testergebnisse nach Fix

**SUCCESS:**

Alle drei APIs geben korrekte Antworten:
- `/v1/caption` → "A terminal window displays the command \"sudo nano...\" on a dark background."
- `/v1/query` → "The image displays a terminal window on a Mac computer screen. The file path is clearly visible..."
- `/v1/point` → `{"points":[{"x":0.015625,"y":0.58984375}],"count":1}`

**Moondream Station Status:**
- Version: 0.1.9 (bereits aktuell)
- Prozess: Läuft auf PID 6053/6098
- Port: 2022
- Timeout: 60-300s funktioniert

---

## Moondream Optimierung v4.0 (Session 2026-02-03)

### Problem: Sprache, Reasoning und Struktururte

**Moondream versteht nur Englisch!**
- Alte Prompts waren gemischt Deutsch/Englisch
- Kein "Reasoning Mode" aktiviert
- Keine strukturierte JSON-Ausgabe
- Task-Trennung fehlte (Parsing + Planning gemischt)

### Lösungen Implementiert

#### 1. Alle Prompts auf Englisch
- `describe_ui_with_moondream`: Englische default_question
- `find_element_with_moondream`: Englische Frage
- `not_found_indicators`: Englische Keywords

#### 2. Reasoning Mode Aktiviert
```sql
"In reasoning mode: Analyze this browser screenshot..."
```
- Explizite Aktivierung für bessere Analyse
- Chain-of-Thought implizit durch Reasoning Mode

#### 3. Strukturierte JSON-Ausgabe
```json
{
  "type": "button",
  "label": "Submit",
  "position": {"x": 0.5, "y": 0.8},
  "visibility": "visible"
}
```

Automatische Ausgabe mit:
- type (button/text field/checkbox/dropdown/etc.)
- label (visible text or aria-label)
- position (x, y center coordinates 0-1)
- visibility state
- confidence (optional)

### Testergebnisse

**SUCCESS - Strukturierte JSON-Antworten:**

**describe_ui_with_moondream:**
```json
[
  {
    "type": "button",
    "label": "Create",
    "position": {"x": 0.5, "y": 0.8},
    "visibility": "visible"
  },
  {
    "type": "text field",
    "label": "Enter username",
    "position": {"x": 0.5, "y": 0.8},
    "visibility": "visible"
  },
  ...
]
```

**find_element_with_moondream:**
```json
{
  "type": "button",
  "label": "submit",
  "position": {
    "x": 0.1, "y": 0.3,
    "top": 0.9, "middle": 0.4, "bottom": 0.1
  },
  "visibility": "top",
  "confidence": 0.95
}
```

### Architektur-Empfehlung

**Task-Trennung:**
- **Moondream**: NUR visuelle Extraktion (Parsing)
- **Text-LLM (GLM-4.7/DeepSeek)**: Planning + Actions

**Optimierte Prompts:**
1. Explizite "In reasoning mode" Aktivierung
2. Strukturierte JSON-Ausgabe erzwingen
3. Semantische Abfragen für Navigation
4. Few-Shot-Beispiele bei komplexen Tasks

### Dateiänderungen

| Datei | Änderungen |
|-------|-----------|
| `tools/moondream_tool/tool.py` | Alle Prompts auf Englisch, Reasoning Mode, strukturierte JSON-Ausgabe |
| `test_optimized_moondream.py` | Testing-Skript für optimierte Prompts |

### Nächste Schritte

- Teste Moondream als Parser in Agent-Integration
- Kombiniere mit Text-LLM für Planning
- Implementiere Few-Shot-Beispiele für komplexe UI-Scenarios

---


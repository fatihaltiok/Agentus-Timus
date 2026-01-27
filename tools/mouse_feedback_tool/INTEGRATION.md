# Mouse Feedback Tool - MCP Server Integration

## Schnellstart

### 1. Tool-Verzeichnis erstellen
```bash
mkdir -p ~/dev/timus/tools/mouse_feedback_tool
cp tool.py ~/dev/timus/tools/mouse_feedback_tool/
cp __init__.py ~/dev/timus/tools/mouse_feedback_tool/
```

### 2. In MCP Server registrieren

**Option A: TOOL_MODULES Liste (empfohlen)**

In deiner `mcp_server.py` oder Konfiguration:

```python
TOOL_MODULES = [
    # Bestehende Tools...
    "tools.som_tool.tool",
    "tools.browser_tool.tool",
    # NEU:
    "tools.mouse_feedback_tool.tool",
]
```

**Option B: Dynamisch laden**

```python
# In mcp_server.py
from tools.mouse_feedback_tool import (
    move_with_feedback,
    search_for_element,
    get_cursor_at_position,
    click_with_verification,
    find_text_field_nearby,
    get_mouse_position
)
```

### 3. Server neu starten
```bash
python server/mcp_server.py
```

---

## Verfügbare RPC Methoden

### `move_with_feedback(target_x, target_y, stop_on_interactive=True)`
Bewegt Maus schrittweise mit Cursor-Feedback.
```json
{"method": "move_with_feedback", "params": {"target_x": 500, "target_y": 300}}
→ {"x": 495, "y": 298, "cursor_type": "ibeam", "is_text_field": true}
```

### `search_for_element(center_x, center_y, radius=50, element_type="any")`
Spiral-Scan nach Element in Region.
```json
{"method": "search_for_element", "params": {"center_x": 500, "center_y": 300, "radius": 100, "element_type": "text_field"}}
→ {"found": true, "x": 510, "y": 295, "cursor_type": "ibeam"}
```

### `find_text_field_nearby(x, y, radius=80)`
Sucht Textfeld in der Nähe einer ungenauen Position.
```json
{"method": "find_text_field_nearby", "params": {"x": 500, "y": 300}}
→ {"found": true, "x": 505, "y": 302, "instruction": "Nutze click_at(505, 302) dann type_text()"}
```

### `click_with_verification(x, y)`
Verifiziert Cursor vor Klick.
```json
{"method": "click_with_verification", "params": {"x": 500, "y": 300}}
→ {"success": true, "cursor_before_click": "ibeam", "was_text_field": true}
```

### `get_cursor_at_position(x, y)`
Prüft Cursor-Typ an Position.
```json
{"method": "get_cursor_at_position", "params": {"x": 500, "y": 300}}
→ {"cursor_type": "hand", "is_clickable": true}
```

### `get_mouse_position()`
Aktuelle Mausposition.
```json
{"method": "get_mouse_position", "params": {}}
→ {"x": 500, "y": 300, "cursor_type": "arrow"}
```

---

## Integration mit VisualAgent

### Neuer Workflow (mit Mouse Feedback)

```
1. SoM: scan_ui_elements(["chat input"])
   → Element [3] bei ungefähr (500, 300)

2. NEU: find_text_field_nearby(500, 300, radius=80)
   → Exakte Position: (505, 298), cursor_type: "ibeam"

3. click_with_verification(505, 298)
   → Verifiziert: war Textfeld ✓

4. type_text("Hallo")
   → Text eingegeben
```

### VisualAgent System Prompt Erweiterung

```
# NEUES TOOL: Mouse Feedback

Bei UNGENAUEN Koordinaten von SoM:
1. Nutze find_text_field_nearby(x, y, radius=80) 
2. Das Tool sucht spiralförmig nach dem Textfeld
3. Gibt exakte Koordinaten zurück wo Cursor "ibeam" wird

VORTEIL: Cursor-Typ als Feedback statt nur Screenshots!
```

---

## Umgebungsvariablen

```bash
# .env
MOUSE_TOOL_DEBUG=1          # Debug-Logging
MOUSE_STEP_SIZE=30          # Pixel pro Bewegungsschritt  
MOUSE_STEP_DELAY=0.02       # Sekunden zwischen Schritten
HOVER_WAIT_TIME=0.15        # Sekunden für Hover-Effekt
ACTIVE_MONITOR=1            # Monitor-Index
```

---

## Cursor-Typen

| Cursor | Konstante | Bedeutung |
|--------|-----------|-----------|
| ➜ Arrow | `arrow` | Normaler Bereich |
| ⌶ I-beam | `ibeam` | Textfeld! |
| 👆 Hand | `hand` | Klickbar (Link/Button) |
| ⏳ Wait | `wait` | Laden |
| ✛ Crosshair | `crosshair` | Präzise Auswahl |
| ↔ Resize | `resize_h` | Horizontal Resize |
| ↕ Resize | `resize_v` | Vertikal Resize |
| ✜ Move | `move` | Verschieben |
| 🚫 Forbidden | `forbidden` | Nicht erlaubt |

---

## Dependencies

```bash
pip install pyautogui pillow mss python-dotenv

# Windows (Cursor Detection)
# - Nutzt ctypes (built-in)

# Linux (Cursor Detection)  
pip install python-xlib
```

---

## Architektur

```
┌─────────────────────────────────────────────────────────┐
│                    VisualAgent                          │
└─────────────────────┬───────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
┌─────────────────┐     ┌─────────────────────────────────┐
│    SoM Tool     │     │    Mouse Feedback Tool          │
│ (Grob-Position) │     │ (Fein-Position via Cursor)      │
└────────┬────────┘     └────────────────┬────────────────┘
         │                               │
         │    ┌──────────────────────────┘
         │    │
         ▼    ▼
┌─────────────────────────────────────────────────────────┐
│                    PyAutoGUI                            │
│              (Maus & Tastatur)                          │
└─────────────────────────────────────────────────────────┘
```

---

## Test

```bash
cd ~/dev/timus/tools/mouse_feedback_tool
python tool.py test
```

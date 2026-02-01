# Timus Vision System - Stabilitäts-Guide

## 🎯 Übersicht

Dieses Guide erklärt das **3-Layer Vision-System** für stabile Bildschirm-Navigation.

**Basierend auf:** GPT-5.2's Empfehlung "Locate → Verify → Act → Verify"

---

## 🏗️ System-Architektur

```
┌─────────────────────────────────────────────────────┐
│ Layer 0: Screen-Change-Gate (70-95% Call-Reduktion)│
│  └─ should_analyze_screen()                         │
├─────────────────────────────────────────────────────┤
│ Layer 1: Schnelle Sensoren (Deterministisch)       │
│  ├─ visual_grounding_tool (OCR)                     │
│  ├─ icon_recognition_tool (Template Matching)      │
│  └─ text_finder_tool                                │
├─────────────────────────────────────────────────────┤
│ Layer 2: Object Detection                           │
│  ├─ visual_segmentation_tool (YOLOS)               │
│  └─ som_tool (Set-of-Mark)                          │
├─────────────────────────────────────────────────────┤
│ Layer 3: VLM (Semantik)                             │
│  └─ moondream_tool (Moondream 3 lokal)             │
├─────────────────────────────────────────────────────┤
│ Layer 4: Intelligente Kombination                   │
│  ├─ hybrid_detection_tool                           │
│  └─ screen_contract_tool (JSON-Verträge)           │
└─────────────────────────────────────────────────────┘
```

---

## 🔧 Neue Tools (v1.0)

### 1. Screen-Change-Gate (`screen_change_detector`)

**Problem:** Zu viele Vision-Calls verschwenden Rechenzeit und führen zu Inkonsistenzen.

**Lösung:** Vision nur bei echter Screen-Änderung.

**Methoden:**

#### `should_analyze_screen(roi, force_pixel_diff)`
Prüft ob eine Screen-Analyse nötig ist.

```python
# Beispiel: Vor jeder Vision-Analyse
result = await should_analyze_screen()

if result["changed"]:
    # Screen hat sich geändert - analysiere
    screen_state = await analyze_screen_state(...)
else:
    # Keine Änderung - nutze Cache
    screen_state = cached_state
```

**ROI-Support** (nur bestimmten Bereich prüfen):
```python
# Nur Formular-Bereich überwachen
result = await should_analyze_screen(
    roi={"x": 100, "y": 200, "width": 600, "height": 400}
)
```

**Performance:**
- Hash-Vergleich: ~0.1ms (identische Bilder)
- Pixel-Diff: ~5-10ms (bei unterschiedlichem Hash)
- **Ersparnis: 70-95% Vision-Calls**

#### `get_screen_change_stats()`
Gibt Performance-Statistiken zurück.

```python
stats = await get_screen_change_stats()
# {
#   "total_checks": 100,
#   "changes_detected": 15,
#   "cache_hits": 85,
#   "avg_check_time_ms": 1.2,
#   "cache_hit_rate": 0.85,
#   "change_rate": 0.15,
#   "performance": "excellent",
#   "savings_estimate": "85% Vision-Calls gespart"
# }
```

#### `set_change_threshold(threshold)`
Ändert Sensitivität.

```python
# Sehr sensitiv (kleinste Änderungen)
await set_change_threshold(0.0001)

# Normal (empfohlen)
await set_change_threshold(0.001)

# Weniger sensitiv (nur große Änderungen)
await set_change_threshold(0.01)
```

---

### 2. Screen Contract Tool (`screen_contract_tool`)

**Problem:** Navigation ist unvorhersagbar - Klicks ohne Verifikation führen zu Drift.

**Lösung:** JSON-basiertes Vertragssystem - "Keine Aktion ohne Beweis".

**Konzepte:**

#### ScreenState (Vertrag 1: Was ist da?)
```python
{
  "screen_id": "login_screen",
  "timestamp": 1706543210.5,
  "anchors": [
    {
      "name": "logo",
      "type": "text",
      "found": true,
      "confidence": 0.95
    },
    {
      "name": "title",
      "type": "text",
      "found": true,
      "confidence": 0.92
    }
  ],
  "elements": [
    {
      "name": "username_field",
      "element_type": "text_field",
      "x": 450,
      "y": 300,
      "bbox": {"x1": 350, "y1": 290, "x2": 550, "y2": 310},
      "confidence": 0.88,
      "method": "hybrid",
      "text": "Benutzername"
    },
    {
      "name": "login_button",
      "element_type": "button",
      "x": 450,
      "y": 450,
      "bbox": {"x1": 400, "y1": 440, "x2": 500, "y2": 460},
      "confidence": 0.92,
      "method": "ocr",
      "text": "Anmelden"
    }
  ],
  "warnings": [],
  "missing": []
}
```

#### ActionPlan (Vertrag 2: Was wird gemacht?)
```python
{
  "goal": "Login durchführen",
  "screen_id": "login_screen",
  "steps": [
    {
      "op": "click",
      "target": "username_field",
      "verify_before": [
        {
          "type": "element_found",
          "target": "username_field",
          "min_confidence": 0.8
        }
      ],
      "verify_after": [
        {
          "type": "cursor_type",
          "target": "ibeam"
        }
      ]
    },
    {
      "op": "type",
      "target": "username_field",
      "params": {
        "text": "test@example.com"
      },
      "verify_after": [
        {
          "type": "field_contains",
          "target": "username_field",
          "params": {"text": "test@example.com"}
        }
      ]
    },
    {
      "op": "click",
      "target": "login_button",
      "verify_before": [
        {
          "type": "element_found",
          "target": "login_button"
        }
      ],
      "verify_after": [
        {
          "type": "screen_changed",
          "target": "screen"
        }
      ]
    }
  ],
  "abort_conditions": [
    {
      "type": "text_contains",
      "target": "error",
      "params": {"text": "Fehler"}
    }
  ]
}
```

**Methoden:**

#### `analyze_screen_state(screen_id, anchor_specs, element_specs, extract_ocr)`
Analysiert Screen und gibt ScreenState zurück.

```python
state = await analyze_screen_state(
    screen_id="login_screen",
    anchor_specs=[
        {"name": "logo", "type": "text", "text": "MyApp"},
        {"name": "title", "type": "text", "text": "Anmeldung"}
    ],
    element_specs=[
        {"name": "username", "type": "text_field", "text": "Benutzername"},
        {"name": "password", "type": "text_field", "text": "Passwort"},
        {"name": "login_btn", "type": "button", "text": "Anmelden"}
    ],
    extract_ocr=False
)
```

#### `execute_action_plan(plan_dict)`
Führt ActionPlan aus.

```python
result = await execute_action_plan({
    "goal": "Login durchführen",
    "screen_id": "login_screen",
    "steps": [...]  # Siehe oben
})

# Result:
# {
#   "success": true,
#   "completed_steps": 3,
#   "total_steps": 3,
#   "execution_time_ms": 2450.5,
#   "logs": [...]
# }
```

#### `verify_screen_condition(condition_dict, screen_state_dict)`
Verifiziert einzelne Bedingung.

```python
verified = await verify_screen_condition({
    "type": "element_found",
    "target": "login_button",
    "min_confidence": 0.8
})
# {"verified": true/false}
```

---

## 📊 Workflow-Beispiel: Login-Form ausfüllen

### **Ohne** Screen-Change-Gate & Contracts (alte Methode):
```python
# Problem: Vision läuft bei jedem Step, auch wenn nichts passiert
# → 10-20 Vision-Calls, viele unnötig

for step in steps:
    # Ganzen Screen analysieren (langsam!)
    elements = await find_all_elements()  # Vision-Call 1

    # Element finden
    element = find_by_name(elements, "username")

    # Klicken (ohne Verifikation!)
    click_at(element.x, element.y)

    # Wieder analysieren...
    elements = await find_all_elements()  # Vision-Call 2
    # usw...
```

**Probleme:**
- ❌ Zu viele Vision-Calls
- ❌ Keine Verifikation vor/nach Aktion
- ❌ Bei Fehler wird einfach weitergemacht
- ❌ Kein deterministisches Verhalten

---

### **Mit** Screen-Change-Gate & Contracts (neue Methode):
```python
# 1. Initiale Analyse (mit Change-Gate)
change_check = await should_analyze_screen()

if change_check["changed"]:
    state = await analyze_screen_state(
        screen_id="login_form",
        anchor_specs=[
            {"name": "logo", "type": "text", "text": "MyApp"}
        ],
        element_specs=[
            {"name": "username", "type": "text_field", "text": "Benutzername"},
            {"name": "password", "type": "text_field", "text": "Passwort"},
            {"name": "login_btn", "type": "button", "text": "Anmelden"}
        ]
    )
else:
    state = cached_state  # Keine Analyse nötig!

# 2. ActionPlan definieren (mit Verify-Before/After)
plan = {
    "goal": "Login durchführen",
    "screen_id": "login_form",
    "steps": [
        {
            "op": "click",
            "target": "username",
            "verify_before": [
                {"type": "element_found", "target": "username"}
            ],
            "verify_after": [
                {"type": "cursor_type", "target": "ibeam"}
            ]
        },
        {
            "op": "type",
            "target": "username",
            "params": {"text": "test@example.com"},
            "verify_after": [
                {"type": "field_contains", "target": "username",
                 "params": {"text": "test"}}
            ]
        },
        {
            "op": "click",
            "target": "password",
            "verify_before": [
                {"type": "element_found", "target": "password"}
            ]
        },
        {
            "op": "type",
            "target": "password",
            "params": {"text": "secret123"}
        },
        {
            "op": "click",
            "target": "login_btn",
            "verify_before": [
                {"type": "element_found", "target": "login_btn"}
            ],
            "verify_after": [
                {"type": "screen_changed", "target": "screen"}
            ]
        }
    ]
}

# 3. Plan ausführen (mit automatischen Retries)
result = await execute_action_plan(plan)

if result["success"]:
    print(f"✅ Login erfolgreich in {result['execution_time_ms']}ms")
else:
    print(f"❌ Fehlgeschlagen bei Step {result['failed_step']}: {result['error_message']}")
```

**Vorteile:**
- ✅ Screen-Change-Gate spart 70-95% Vision-Calls
- ✅ Jede Aktion hat Verify-Before/After
- ✅ Automatische Retries bei Fehlern
- ✅ Deterministisches Verhalten
- ✅ Debugbar (Logs, Failed-Step-Index)

---

## 🎯 Best Practices

### 1. **Immer Screen-Change-Gate nutzen**
```python
# ✅ Gut
change_check = await should_analyze_screen()
if change_check["changed"]:
    state = await analyze_screen_state(...)

# ❌ Schlecht
state = await analyze_screen_state(...)  # Analysiert immer, auch wenn unnötig
```

### 2. **Anker definieren für jeden Screen**
```python
# ✅ Gut - Anker beweisen "richtiger Screen"
anchor_specs = [
    {"name": "logo", "type": "text", "text": "MyApp"},
    {"name": "page_title", "type": "text", "text": "Anmeldung"}
]

# ❌ Schlecht - keine Anker
anchor_specs = []  # Unsicher ob im richtigen Screen
```

### 3. **Verify-Before und Verify-After nutzen**
```python
# ✅ Gut - mit Verifikation
{
    "op": "click",
    "target": "submit_btn",
    "verify_before": [
        {"type": "element_found", "target": "submit_btn"}
    ],
    "verify_after": [
        {"type": "screen_changed", "target": "screen"}
    ]
}

# ❌ Schlecht - ohne Verifikation
{
    "op": "click",
    "target": "submit_btn"
}  # Klickt blind, auch wenn Element nicht existiert
```

### 4. **ROI für spezifische Bereiche**
```python
# ✅ Gut - nur Formular-Bereich überwachen
roi = {"x": 100, "y": 200, "width": 600, "height": 400}
change_check = await should_analyze_screen(roi=roi)

# ❌ Weniger effizient - ganzer Screen
change_check = await should_analyze_screen()
```

### 5. **Abort-Conditions für Fehler**
```python
# ✅ Gut - mit Abort-Conditions
"abort_conditions": [
    {
        "type": "text_contains",
        "target": "error",
        "params": {"text": "Fehler"}
    },
    {
        "type": "text_contains",
        "target": "error",
        "params": {"text": "fehlgeschlagen"}
    }
]
```

---

## 📈 Performance-Metriken

### Erwartete Verbesserungen:

| Metrik | Vorher | Nachher | Verbesserung |
|--------|--------|---------|--------------|
| **Vision-Calls pro Navigation** | 10-20 | 2-4 | **70-90%** |
| **Durchschnittliche Latenz** | 30-50s | 8-15s | **60-75%** |
| **Erfolgsrate (erste Versuch)** | 60-70% | 85-95% | **+25-35%** |
| **Fehler durch Drift** | Häufig | Selten | **-90%** |

### Performance-Tracking:
```python
# Screen-Change-Gate Stats
stats = await get_screen_change_stats()
print(f"Cache-Hit-Rate: {stats['cache_hit_rate'] * 100}%")
print(f"Ersparte Calls: {stats['savings_estimate']}")
print(f"Avg Check-Zeit: {stats['avg_check_time_ms']}ms")

# Plan-Execution Stats
result = await execute_action_plan(plan)
print(f"Ausführungszeit: {result['execution_time_ms']}ms")
print(f"Steps: {result['completed_steps']}/{result['total_steps']}")
```

---

## 🔍 Debugging

### Screen-State prüfen:
```python
state = await analyze_screen_state(...)

# Prüfe Anker
for anchor in state["anchors"]:
    if not anchor["found"]:
        print(f"⚠️ Anker fehlt: {anchor['name']}")

# Prüfe Elemente
for elem in state["elements"]:
    print(f"Element '{elem['name']}': {elem['x']}, {elem['y']} (conf: {elem['confidence']})")

# Prüfe fehlende Elemente
if state["missing"]:
    print(f"❌ Fehlende Elemente: {state['missing']}")
```

### Action-Plan Logs:
```python
result = await execute_action_plan(plan)

# Zeige Logs
for log_entry in result["logs"]:
    print(log_entry)

# Bei Fehler
if not result["success"]:
    print(f"❌ Fehlgeschlagen bei Step {result['failed_step']}")
    print(f"Fehler: {result['error_message']}")
```

---

## 🚀 Quick-Start Checklist

1. ✅ Screen-Change-Gate vor jeder Analyse nutzen
2. ✅ Anker für jeden Screen definieren
3. ✅ ActionPlan mit Verify-Before/After erstellen
4. ✅ ROI nutzen für spezifische Bereiche
5. ✅ Abort-Conditions definieren
6. ✅ Performance-Stats monitoren

---

**Version:** 1.0
**Datum:** 2026-02-01
**Basis:** GPT-5.2 Empfehlungen + Timus Hybrid-System

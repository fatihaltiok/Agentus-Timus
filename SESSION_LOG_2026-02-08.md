# VisualNemotronAgent v4 - Entwicklungssession Log
**Datum:** 2026-02-08  
**Ziel:** Desktop-Automatisierung mit echten Maus-Tools

---

## ✅ Was wurde erreicht

### 1. VisualNemotronAgent v4 erstellt
**Datei:** `agent/visual_nemotron_agent_v4.py`

**Features:**
- PyAutoGUI für echte Maus/Klick-Aktionen (statt Playwright)
- GPT-4 Vision als PRIMARY (~3-5s pro Analyse)
- SoM Tool als Fallback für UI-Element-Scanning
- Loop-Erkennung (verhindert Endlosschleifen)
- Debug-Logging (Screenshots + Analysen in `/tmp/v4_debug/`)

**Architektur:**
```
GPT-4 Vision (PRIMARY) → Koordinaten → PyAutoGUI Klick
     ↓ (Fallback)
Qwen-VL (langsam, 120s timeout)
```

### 2. Dispatcher aktualisiert
**Datei:** `main_dispatcher.py`

**Änderungen:**
- Import: `visual_nemotron_agent_v4` mit Priorität v4 > v3 > v2
- `_structure_task()` Funktion für Task-Strukturierung
- Handler nutzt jetzt `run_desktop_task()` für Desktop-Automation

### 3. Debug-System implementiert
**Datei:** `tools/v4_debug_viewer.py`

**Befehle:**
```bash
python tools/v4_debug_viewer.py list      # Alle Screenshots anzeigen
python tools/v4_debug_viewer.py view      # Letzten Screenshot öffnen
python tools/v4_debug_viewer.py analysis  # Letzte GPT-4 Analyse
python tools/v4_debug_viewer.py clear     # Debug-Dateien löschen
```

**Speicherort:** `/tmp/v4_debug/`
- `screenshot_*.png` - Was GPT-4 sieht
- `analysis_*.txt` - GPT-4 Beschreibung + Task

---

## ⚠️ Bekannte Probleme

### Problem 1: Qwen-VL ist zu langsam
**Symptom:** 60s+ Timeout statt 5-10s
**Ursache:** Läuft wahrscheinlich auf CPU statt GPU
**Lösung:** 
- GPT-4 Vision als PRIMARY (implementiert)
- Qwen-VL nur als Fallback

**Diagnose:**
```bash
nvidia-smi  # Zeigt GPU-Nutzung
# Qwen-VL sollte ~10GB VRAM nutzen
```

### Problem 2: SoM Tool findet keine Elemente
**Symptom:** `0 UI-Elemente gescannt`
**Ursache:** Moondream Server nicht erreichbar oder falsch konfiguriert
**Lösung:**
- GPT-4 Vision für Koordinaten direkt nutzen
- `find_element_by_description()` implementiert

### Problem 3: Altes Qwen-Tool noch aktiv
**Symptom:** Logs zeigen `tools.qwen_vl_tool` statt `VisualNemotronV4`
**Ursache:** Dispatcher wählt falschen Agenten
**Workaround:**
```bash
# Explizit v4 nutzen:
"visual_nemotron: starte browser und gehe zu amazon.de"
```

### Problem 4: Browser Crash bei Loops
**Symptom:** `Target page, context or browser has been closed`
**Ursache:** Qwen-VL wiederholt dieselben Aktionen
**Lösung:**
- Loop-Erkennung in v4 implementiert
- Max 3 identische Screenshots erlaubt

---

## 🔧 Offene Aufgaben

### Hochpriorität:
1. **Qwen-VL GPU-Problem lösen**
   - Prüfe: `python -c "import torch; print(torch.cuda.is_available())"`
   - Prüfe: `nvidia-smi` während Qwen läuft
   - Lösung: Qwen-VL auf GPU zwingen (nicht `device=auto`)

2. **SoM Tool debuggen**
   - Moondream Server läuft auf Port 2020?
   - Test: `curl http://localhost:2020/v1/point -d '{"image_url": "...", "object": "button"}'`

3. **v4 als Standard setzen**
   - `VISUAL_NEMOTRON_KEYWORDS` erweitern
   - Priorität: "starte browser" → immer v4

### Mittelpriorität:
4. **Screenshot-Größe optimieren**
   - Aktuell: 1920x1200 (viel zu groß für GPT-4)
   - Bessere Resize-Logik für Vision-Modelle

5. **Retry-Logik verbessern**
   - Bei Fehler: Screenshot neu + andere Strategie
   - Max 3 Versuche pro Schritt

6. **Nemotron Prompt optimieren**
   - Aktuell: Gibt manchmal Code statt Aktionen
   - Besser: Strukturierte JSON-Schema Enforcement

---

## 📁 Wichtige Dateien

| Datei | Zweck |
|-------|-------|
| `agent/visual_nemotron_agent_v4.py` | Haupt-Agent mit Desktop-Tools |
| `main_dispatcher.py` | Dispatcher mit v4 Integration |
| `tools/v4_debug_viewer.py` | Debug-Tool für Screenshots |
| `tools/som_tool/tool.py` | SoM UI-Element-Erkennung |
| `tools/mouse_tool/tool.py` | PyAutoGUI Maus-Steuerung |
| `/tmp/v4_debug/` | Debug-Screenshots + Analysen |

---

## 🧪 Test-Befehle

```bash
# v4 direkt testen:
cd /home/fatih-ubuntu/dev/timus
python -c "
import asyncio
from agent.visual_nemotron_agent_v4 import run_desktop_task
async def test():
    result = await run_desktop_task(
        task='Öffne Amazon und suche nach NVIDIA',
        url='https://amazon.de',
        max_steps=5
    )
    print(result)
asyncio.run(test())
"

# Debug anzeigen:
python tools/v4_debug_viewer.py list

# Logs anzeigen:
tail -f /tmp/v4_debug/*.txt
```

---

## 💡 Erkenntnisse

1. **GPT-4 Vision ist schneller als Qwen-VL** (3s vs 60s+)
2. **PyAutoGUI ist zuverlässiger als Playwright** (echte Maus)
3. **Debug-Logging ist essentiell** für Vision-Modelle
4. **Loop-Erkennung verhindert Crashes**

---

## 📝 Nächste Schritte (v4.1)

1. Qwen-VL GPU-Problem beheben
2. v4 als Standard-Agent für alle Visual-Tasks
3. Screenshot-Annotation (markierte Elemente)
4. Bessere Fehler-Recovery
5. Performance-Optimierung (parallele Vision-Calls)

---

**Session beendet:** 2026-02-08 19:50  
**Nächste Session:** TBD

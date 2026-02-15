# Qwen2.5-VL Visual Agent für Timus

Lokales Vision-Language-Model (Qwen2.5-VL) für Web-Automation auf deiner RTX 3090.

## 🚀 Features

- **Lokale GPU-Inference** - Keine API-Kosten, volle Privatsphäre
- **RTX 3090 optimiert** - bfloat16, CUDA acceleration
- **Web-Automation** - Klicks, Tippen, Scrollen via Playwright + PyAutoGUI
- **Strukturierte Aktionen** - JSON-basierte Koordinaten-Extraktion
- **Multi-Step Workflows** - Kontext via Action-History

## 📁 Neue Dateien

```
tools/engines/qwen_vl_engine.py       # Core Engine (Singleton)
tools/qwen_vl_tool/tool.py          # MCP-Tool Integration
agent/qwen_visual_agent.py          # Visual Agent
setup_qwen_vl.py                     # Setup-Skript
data/qwen_screenshots/              # Screenshot-Speicher (automatisch erstellt)
```

## ⚙️ Schnellstart

### 1. Setup ausführen

```bash
cd /home/fatih-ubuntu/dev/timus
python setup_qwen_vl.py
```

Das Skript:
- Prüft CUDA und VRAM
- Installiert `transformers`, `accelerate`, `qwen-vl-utils`
- Konfiguriert `.env`
- Lädt Modell in GPU (erster Start dauert ~2-5 Minuten)

### 2. MCP-Server neu starten

```bash
export QWEN_VL_ENABLED=1
python server/mcp_server.py
```

### 3. Test via Agent

```bash
# Direkter Agent-Test
python agent/qwen_visual_agent.py \
    --url "https://www.google.com" \
    --task "Klicke in die Suchleiste, tippe 'Künstliche Intelligenz', drücke Enter"
```

### 4. Test via MCP-Tool

```python
# In einem anderen Terminal
curl -X POST http://localhost:5000 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "qwen_web_automation",
    "params": {
      "url": "https://www.t-online.de",
      "task": "Finde den E-Mail-Login-Bereich oben rechts und klicke darauf",
      "headless": false,
      "max_iterations": 8
    },
    "id": 1
  }'
```

## 🔧 Konfiguration (`.env`)

```env
# Aktivierung
QWEN_VL_ENABLED=1

# Modell-Auswahl
QWEN_VL_MODEL=Qwen/Qwen2.5-VL-3B-Instruct   # Schneller, ~8GB VRAM
# QWEN_VL_MODEL=Qwen/Qwen2.5-VL-7B-Instruct # Besser, ~16GB VRAM

# Hardware
QWEN_VL_DEVICE=cuda     # auto, cuda, cpu
QWEN_VL_MAX_TOKENS=512
QWEN_VL_SCREENSHOT_SIZE=1920,1080

# Agent-Verhalten
QWEN_MAX_RETRIES=3
QWEN_MAX_ITERATIONS=10
QWEN_WAIT_BETWEEN_ACTIONS=1.0
QWEN_HEADLESS=0         # 1 = unsichtbar
QWEN_BROWSER=chromium   # chromium, firefox, webkit

# HuggingFace (optional, für private Modelle)
HF_TOKEN=dein_token_hier
```

## 🖥️ Systemanforderungen

| Modell | VRAM | RAM | Download |
|--------|------|-----|----------|
| 3B-Instruct | ~8 GB | 16 GB | ~6 GB |
| 7B-Instruct | ~16 GB | 32 GB | ~14 GB |

- **GPU**: NVIDIA RTX 3090 (24GB) ✓ perfekt
- **CUDA**: 12.1+
- **Python**: 3.9+

## 📖 Verwendung im Code

### Als Python-Modul

```python
from agent.qwen_visual_agent import QwenVisualAgent

agent = QwenVisualAgent()

result = agent.run_task(
    url="https://example.com",
    task="Klicke auf den roten Button",
    headless=False,
    max_iterations=5
)

print(f"Erfolg: {result['success']}")
print(f"Schritte: {result['iterations']}")
```

### Als Engine direkt

```python
from tools.engines.qwen_vl_engine import qwen_vl_engine_instance
from PIL import Image

# Screenshot analysieren
image = Image.open("screenshot.png")
result = qwen_vl_engine_instance.analyze_screenshot(
    image=image,
    task="Finde den Login-Button",
    history=[]
)

for action in result["actions"]:
    print(f"{action.action}: ({action.x}, {action.y})")
```

## 🎯 Aktionstypen

Das Modell gibt JSON-Aktionen zurück:

```json
[
  {"action": "click", "x": 1450, "y": 320},
  {"action": "type", "text": "user@example.com"},
  {"action": "press", "key": "Enter"},
  {"action": "scroll_down", "y": 500},
  {"action": "wait", "seconds": 2},
  {"action": "done"}
]
```

## 🔍 Fehlerbehebung

### "CUDA out of memory"
```bash
# Kleineres Modell verwenden
export QWEN_VL_MODEL=Qwen/Qwen2.5-VL-3B-Instruct
```

### "Model not found"
```bash
# HuggingFace Login (falls erforderlich)
huggingface-cli login
# oder
export HF_TOKEN=dein_token
```

### "Engine nicht initialisiert"
```bash
# Im Server-Log prüfen
export QWEN_VL_ENABLED=1
python server/mcp_server.py 2>&1 | grep -i qwen
```

## 📊 Performance

| Task | 3B Modell | 7B Modell |
|------|-----------|-----------|
| Screenshot-Analyse | ~2-3s | ~4-6s |
| Login-Workflow | ~15-30s | ~20-40s |
| VRAM-Nutzung | ~8GB | ~16GB |

## 🔗 Links

- [Qwen2.5-VL Paper](https://arxiv.org/abs/2409.12191)
- [HuggingFace Model](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct)
- [Transformers Docs](https://huggingface.co/docs/transformers)

---

**Hinweis**: Das Modell wird beim ersten Start automatisch von HuggingFace heruntergeladen (~6GB für 3B, ~14GB für 7B). Das kann je nach Internetverbindung 5-20 Minuten dauern.

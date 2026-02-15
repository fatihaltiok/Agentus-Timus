# Intel D435 + Moondream3 Preview Setup

Speicher-optimierte Konfiguration für D435 Kamera mit Moondream3.

## Schnellstart

```bash
# 1. Kopiere D435-Konfiguration
cp .env.d435.preview .env

# 2. Qwen-VL deaktivieren (automatisch in .env)
# QWEN_VL_ENABLED=0

# 3. Moondream3 Server starten
python -m moondream.server --model moondream3-2b --port 2021

# 4. D435 starten (im Hintergrund)
python tools/d435_tool/d435_server.py &

# 5. Timus starten
python server/mcp_server.py
```

## Architektur

```
┌─────────────┐    USB 3.0     ┌──────────────┐
│ Intel D435  │───────────────→│ D435 Tool    │
│ (RGB+Depth) │                │ (Frame Grab) │
└─────────────┘                └──────┬───────┘
                                    │
                                    ▼
┌──────────────┐              ┌──────────────┐
│ Moondream3   │←─────────────│ Frame Buffer │
│ (2B Model)   │   HTTP API   │ (640x480)    │
│ ~2-3GB VRAM  │              └──────────────┘
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Vision Agent │←→ Tasks
└──────────────┘
```

## Speicher-Nutzung

| Komponente | VRAM | CPU RAM |
|------------|------|---------|
| Moondream3 2B | 2-3 GB | 4 GB |
| D435 Stream | 0 GB | 500 MB |
| Timus Agent | 0 GB | 1 GB |
| **Gesamt** | **2-3 GB** | **5.5 GB** |

## Optional: Qwen-VL on-demand

```python
# Qwen-VL nur bei Bedarf laden
await call_tool("load_qwen_vl", {"model": "2B"})
# ... komplexe Vision Tasks ...
await call_tool("unload_qwen_vl")
```

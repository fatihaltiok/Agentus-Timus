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

# 4. Timus starten (MCP lädt RealSense-Tools automatisch)
python server/mcp_server.py

# 5. Kamera testen
rs-enumerate-devices
# optional via MCP Tool: realsense_status / capture_realsense_snapshot

# 6. Live-Stream aktivieren (dauerhaftes Sehen)
# via MCP Tool: start_realsense_stream
# oder ENV vor Server-Start:
# REALSENSE_STREAM_AUTO_START=true
```

## Architektur

```
┌─────────────┐    USB 3.0     ┌──────────────────────┐
│ Intel D435  │───────────────→│ RealSense MCP Tool   │
│ (RGB+Depth) │                │ (status + snapshot)  │
└─────────────┘                └──────────┬───────────┘
                                          │
                                          ▼
┌──────────────┐                    ┌──────────────┐
│ Moondream3   │←──────────────────→│ Vision Agent │
│ (2B Model)   │      Frames        │ (Image/Visual)│
└──────────────┘                    └──────────────┘
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

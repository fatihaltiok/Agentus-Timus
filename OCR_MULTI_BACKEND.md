# Multi-Backend OCR Engine v3.0

## Übersicht

Die neue OCR Engine unterstützt **4 verschiedene Backends** mit automatischer Auswahl und Fallback-Mechanismus:

1. **EasyOCR** (Default) - Beste Balance zwischen Geschwindigkeit und Genauigkeit
2. **Tesseract** - Schnell, gut mit Preprocessing, bewährt
3. **TrOCR** (Hugging Face) - Für schwierige Einzelzeilen, neuronales Netz
4. **PaddleOCR** (NEU) - Production-ready, sehr präzise, chinesische Layout-Erkennung

## Konfiguration

Über **.env** Datei:

```bash
# Backend auswählen
OCR_BACKEND=easyocr  # easyocr, tesseract, trocr, paddleocr, auto

# GPU nutzen (falls verfügbar)
OCR_GPU=1  # 1 = ja, 0 = nein

# Sprachen (komma-getrennt)
OCR_LANGUAGES=de,en  # Deutsch und Englisch
```

### Backend-Auswahl: `auto`

Wenn `OCR_BACKEND=auto`, wählt die Engine automatisch:
1. EasyOCR (wenn installiert)
2. Tesseract (Fallback)
3. TrOCR (Fallback)
4. PaddleOCR (Fallback)

## Verwendung

### Python API

```python
from tools.engines.ocr_engine import ocr_engine_instance
from PIL import Image

# Engine initialisieren
ocr_engine_instance.initialize()

# Bild laden
image = Image.open("screenshot.png")

# OCR durchführen (mit Bounding Boxes)
result = ocr_engine_instance.process(image, with_boxes=True)

print(result)
# {
#   "extracted_text": [
#     {"text": "Login", "confidence": 0.95, "bbox": [100, 200, 150, 220]},
#     {"text": "Password", "confidence": 0.92, "bbox": [100, 250, 180, 270]}
#   ],
#   "full_text": "Login Password",
#   "backend": "easyocr",
#   "count": 2
# }
```

### Rückwärtskompatibilität

```python
# Nur Text zurückgeben (ohne Boxes)
text = ocr_engine_instance.run_ocr(image)
print(text)  # "Login Password"
```

### Über RPC (MCP Server)

```python
import httpx

response = await httpx.post("http://127.0.0.1:5000/rpc", json={
    "jsonrpc": "2.0",
    "method": "read_text_from_screen",
    "params": {"with_boxes": True},
    "id": 1
})
```

## Backend-Vergleich

| Backend    | Geschwindigkeit | Genauigkeit | Layout | Sprachen | GPU  |
|------------|----------------|-------------|--------|----------|------|
| EasyOCR    | ⭐⭐⭐          | ⭐⭐⭐⭐     | ⭐⭐⭐  | 80+      | ✅   |
| Tesseract  | ⭐⭐⭐⭐⭐       | ⭐⭐⭐       | ⭐⭐    | 100+     | ❌   |
| TrOCR      | ⭐⭐            | ⭐⭐⭐⭐     | ⭐      | 100+     | ✅   |
| PaddleOCR  | ⭐⭐⭐⭐        | ⭐⭐⭐⭐⭐   | ⭐⭐⭐⭐ | 80+      | ✅   |

### Empfehlungen

**Für UI-Element-Erkennung:**
- **EasyOCR** (beste Balance)
- **PaddleOCR** (wenn höchste Präzision wichtig ist)

**Für Geschwindigkeit:**
- **Tesseract** (wenn GPU nicht verfügbar)

**Für schwierige Texte:**
- **TrOCR** (handgeschrieben, verzerrt)
- **PaddleOCR** (komplexe Layouts, Tabellen)

**Für asiatische Sprachen:**
- **PaddleOCR** (spezialisiert auf Chinesisch)

## Test-Script

```bash
# Vergleiche alle verfügbaren Backends
python3 test_ocr_backends.py
```

Das Script:
- Macht einen Screenshot
- Testet alle installierten Backends
- Vergleicht Geschwindigkeit und Genauigkeit
- Gibt Empfehlungen

### Beispiel-Output:

```
🏆 Ranking nach Geschwindigkeit:
  1. tesseract    -  2.34s | 42 Blöcke | Conf: 78.5%
  2. easyocr      -  4.12s | 38 Blöcke | Conf: 91.2%
  3. paddleocr    -  5.67s | 45 Blöcke | Conf: 94.1%
  4. trocr        -  8.92s |  1 Blöcke | Conf: 100.0%

💡 Empfehlung:
  🚀 Schnellstes: tesseract (2.34s)
  🎯 Beste Confidence: paddleocr (94.1%)
  📝 Meiste Textblöcke: paddleocr (45 Blöcke)

🌟 Beste Balance (Geschwindigkeit + Genauigkeit):
  ⭐ easyocr - Score: 0.423
     Zeit: 4.12s | Conf: 91.2%
```

## Installation

### EasyOCR
```bash
pip install easyocr
```

### Tesseract
```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng

# Python-Wrapper
pip install pytesseract
```

### TrOCR
```bash
pip install transformers torch
```

### PaddleOCR
```bash
pip install paddlepaddle paddleocr
```

## Architektur

```
OCREngine (Singleton)
├─ Backend-Manager
│  ├─ EasyOCR Reader
│  ├─ Tesseract (pytesseract)
│  ├─ TrOCR (Hugging Face)
│  └─ PaddleOCR Reader
│
├─ initialize()
│  └─ Lädt gewähltes Backend
│
├─ process(image, with_boxes)
│  └─ Gibt strukturierte Ergebnisse zurück
│
└─ run_ocr(image)
   └─ Rückwärtskompatibilität (nur Text)
```

## Beispiel-Ergebnisse

### Mit Bounding Boxes (`with_boxes=True`)

```python
{
  "extracted_text": [
    {
      "text": "Username:",
      "confidence": 0.96,
      "bbox": [120, 150, 220, 175]
    },
    {
      "text": "Password:",
      "confidence": 0.94,
      "bbox": [120, 200, 230, 225]
    },
    {
      "text": "Login",
      "confidence": 0.98,
      "bbox": [320, 250, 380, 280]
    }
  ],
  "full_text": "Username: Password: Login",
  "backend": "easyocr",
  "count": 3
}
```

### Ohne Bounding Boxes (`with_boxes=False`)

```python
{
  "extracted_text": [
    {"text": "Username:", "confidence": 0.96},
    {"text": "Password:", "confidence": 0.94},
    {"text": "Login", "confidence": 0.98}
  ],
  "full_text": "Username: Password: Login",
  "backend": "easyocr",
  "count": 3
}
```

## Integration in Visual Grounding Tool

Das Visual Grounding Tool (`tools/visual_grounding_tool/tool.py`) nutzt **Tesseract** mit speziellen Vorverarbeitungs-Methoden:
- Adaptive Threshold
- Otsu Binarization
- Fuzzy-Matching für Button-Texte

Die zentrale OCR Engine kann parallel verwendet werden:

```python
# Visual Grounding (Button-Suche)
coords = await find_text_coordinates("Login")

# OCR Engine (Gesamter Bildschirm)
result = ocr_engine_instance.process(screenshot, with_boxes=True)
```

## Fehlerbehandlung

```python
# Prüfe ob Engine initialisiert ist
if not ocr_engine_instance.is_initialized():
    print("OCR Engine nicht verfügbar!")
    ocr_engine_instance.initialize()

# Fehler bei der Verarbeitung
result = ocr_engine_instance.process(image)
if "error" in result:
    print(f"OCR-Fehler: {result['error']}")
```

## Performance-Tipps

1. **GPU nutzen** (`OCR_GPU=1`)
   - EasyOCR: 3-5x schneller
   - TrOCR: 10x schneller
   - PaddleOCR: 4-6x schneller

2. **Backend-Auswahl nach Use-Case**
   - Einfache UI: Tesseract (schnell)
   - Komplexe UI: EasyOCR oder PaddleOCR
   - Präzision wichtig: PaddleOCR

3. **Preprocessing für Tesseract**
   - Visual Grounding Tool hat bereits Preprocessing
   - Adaptive Threshold funktioniert am besten

4. **Sprachen einschränken**
   - `OCR_LANGUAGES=de` statt `de,en,fr,es...`
   - Reduziert Modellgröße und erhöht Geschwindigkeit

## Changelog

### v3.0 (27. Januar 2026)
- ✅ Multi-Backend Support (EasyOCR, Tesseract, TrOCR, PaddleOCR)
- ✅ Konfigurierbar per .env
- ✅ Automatische Backend-Auswahl
- ✅ Strukturierte Ergebnisse mit Bounding Boxes
- ✅ GPU-Support für alle kompatiblen Backends
- ✅ Rückwärtskompatibilität zu v1.0/v2.0

### v2.0
- Visual Grounding mit Tesseract
- Fuzzy-Matching für Button-Texte

### v1.0
- TrOCR (Hugging Face) als einziges Backend

## Weitere Informationen

- **EasyOCR Docs:** https://github.com/JaidedAI/EasyOCR
- **Tesseract Docs:** https://github.com/tesseract-ocr/tesseract
- **TrOCR Docs:** https://huggingface.co/microsoft/trocr-base-printed
- **PaddleOCR Docs:** https://github.com/PaddlePaddle/PaddleOCR

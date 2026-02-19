"""
Florence-2 Tool für Timus MCP-Server.

Registriert 5 Tools via @tool Decorator (registry_v2):
    florence2_health          — Modell-Status prüfen
    florence2_full_analysis   — Vollanalyse → fertiger Prompt für Nemotron
    florence2_detect_ui       — UI-Elemente + Bounding Boxes
    florence2_ocr             — Text + Positionen
    florence2_analyze_region  — Bereich-Analyse mit optionaler Frage

Alle Tool-Funktionen sind async (Timus-Konvention).
GPU-Arbeit läuft in asyncio.to_thread (non-blocking).

Modell: microsoft/Florence-2-large-ft (empfohlen, ~3GB VRAM)
Fallback: microsoft/Florence-2-base-ft (~1.5GB VRAM)

Feature-Flag: FLORENCE2_ENABLED=true (default) / false
Modell-Override: FLORENCE2_MODEL=microsoft/Florence-2-large-ft
"""

import asyncio
import os
import time
import logging
from pathlib import Path
from typing import Optional
from io import BytesIO

log = logging.getLogger("timus.florence2")

# ---------------------------------------------------------------------------
# Timus Tool-Registry
# ---------------------------------------------------------------------------
from tools.tool_registry_v2 import tool, P, C, ToolCategory

# ---------------------------------------------------------------------------
# Singleton: Modell nur einmal laden
# ---------------------------------------------------------------------------
_model = None
_processor = None
_device: str = "cpu"
_model_path: str = os.getenv("FLORENCE2_MODEL", "microsoft/Florence-2-large-ft")
_enabled: bool = os.getenv("FLORENCE2_ENABLED", "true").lower() not in {"0", "false", "no", "off"}


def _load_model():
    """Lädt Florence-2 einmalig in den Speicher (lazy, thread-safe genug für MCP)."""
    global _model, _processor, _device

    if _model is not None:
        return _model, _processor

    if not _enabled:
        raise RuntimeError("Florence-2 ist deaktiviert (FLORENCE2_ENABLED=false)")

    import torch
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForCausalLM

    log.info(f"Lade Florence-2: {_model_path}")
    t0 = time.time()

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if _device == "cuda" else torch.float32

    _processor = AutoProcessor.from_pretrained(
        _model_path,
        trust_remote_code=True,
    )

    _model = AutoModelForCausalLM.from_pretrained(
        _model_path,
        torch_dtype=dtype,
        trust_remote_code=True,
    ).to(_device)

    _model.eval()
    elapsed = time.time() - t0
    log.info(f"Florence-2 geladen auf {_device} in {elapsed:.1f}s")
    return _model, _processor


def _unload_model():
    """Gibt VRAM frei (für Notfall-Szenarien)."""
    global _model, _processor
    if _model is not None:
        import torch
        del _model
        del _processor
        _model = None
        _processor = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        log.info("Florence-2 aus VRAM entladen")


# ---------------------------------------------------------------------------
# Kernfunktionen (intern)
# ---------------------------------------------------------------------------

def _load_image(source):
    """Lädt ein Bild aus Pfad, Bytes oder BytesIO."""
    from PIL import Image
    if isinstance(source, Image.Image):
        return source.convert("RGB")
    if isinstance(source, (str, Path)):
        return Image.open(source).convert("RGB")
    if isinstance(source, bytes):
        return Image.open(BytesIO(source)).convert("RGB")
    if isinstance(source, BytesIO):
        return Image.open(source).convert("RGB")
    raise ValueError(f"Unbekanntes Bildformat: {type(source)}")


def _run_task(image, task: str, text_input: str = "") -> dict:
    """Führt einen Florence-2 Task aus."""
    import torch

    model, processor = _load_model()
    prompt = task if not text_input else f"{task}{text_input}"

    inputs = processor(
        text=prompt,
        images=image,
        return_tensors="pt",
    ).to(_device, torch.float16 if _device == "cuda" else torch.float32)

    with torch.no_grad():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=1024,
            num_beams=3,
            do_sample=False,
        )

    raw = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    return processor.post_process_generation(
        raw,
        task=task,
        image_size=(image.width, image.height),
    )


def _detect_ui(image) -> dict:
    result = _run_task(image, "<OD>")
    od = result.get("<OD>", {})
    elements = []
    for label, bbox in zip(od.get("labels", []), od.get("bboxes", [])):
        elements.append({
            "label": label,
            "bbox": [round(v) for v in bbox],
            "center": [round((bbox[0] + bbox[2]) / 2), round((bbox[1] + bbox[3]) / 2)],
        })
    return {"elements": elements, "count": len(elements),
            "image_size": [image.width, image.height], "device": _device}


def _ocr(image) -> dict:
    result = _run_task(image, "<OCR_WITH_REGION>")
    ocr = result.get("<OCR_WITH_REGION>", {})
    texts = []
    for text, quad in zip(ocr.get("labels", []), ocr.get("quad_boxes", [])):
        xs, ys = quad[0::2], quad[1::2]
        bbox = [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))]
        texts.append({
            "text": text.strip(),
            "bbox": bbox,
            "center": [round((bbox[0] + bbox[2]) / 2), round((bbox[1] + bbox[3]) / 2)],
        })
    texts = [t for t in texts if t["text"]]
    return {"texts": texts, "full_text": " ".join(t["text"] for t in texts), "count": len(texts)}


def _caption(image, detailed: bool = False) -> str:
    task = "<DETAILED_CAPTION>" if detailed else "<CAPTION>"
    return _run_task(image, task).get(task, "")


def _full_analysis(image) -> dict:
    caption = _caption(image)
    ui = _detect_ui(image)
    ocr = _ocr(image)

    all_elements = []
    for el in ui["elements"]:
        all_elements.append({"type": "ui_element", "label": el["label"],
                              "bbox": el["bbox"], "center": el["center"]})
    for tx in ocr["texts"]:
        all_elements.append({"type": "text", "label": tx["text"],
                             "bbox": tx["bbox"], "center": tx["center"]})

    lines = [
        f"[{i+1}] {el['type'].upper()}: \"{el['label']}\" @ ({el['center'][0]}, {el['center'][1]})"
        for i, el in enumerate(all_elements)
    ]
    summary_prompt = (
        f"Bildschirm-Beschreibung: {caption}\n\n"
        f"Gefundene Elemente ({len(all_elements)}):\n" + "\n".join(lines)
    )

    return {
        "caption": caption,
        "ui_elements": ui["elements"],
        "text_elements": ocr["texts"],
        "all_elements": all_elements,
        "element_count": len(all_elements),
        "summary_prompt": summary_prompt,
        "image_size": [image.width, image.height],
        "model": _model_path,
        "device": _device,
    }


# ---------------------------------------------------------------------------
# MCP-Tools (@tool Decorator → registry_v2 + jsonrpcserver global_methods)
# ---------------------------------------------------------------------------

@tool(
    name="florence2_health",
    description="Prüft ob Florence-2 geladen und einsatzbereit ist. Gibt Modell-Pfad und Gerät zurück.",
    parameters=[],
    capabilities=["vision", "health"],
    category=ToolCategory.VISION,
    returns="dict",
)
async def florence2_health() -> dict:
    """Gibt Status des Florence-2 Modells zurück."""
    if not _enabled:
        return {"status": "disabled", "reason": "FLORENCE2_ENABLED=false",
                "model": _model_path, "loaded": False}
    loaded = _model is not None
    return {
        "status": "ready" if loaded else "not_loaded",
        "loaded": loaded,
        "model": _model_path,
        "device": _device,
        "enabled": _enabled,
    }


@tool(
    name="florence2_full_analysis",
    description=(
        "Vollständige Screenshot-Analyse: UI-Elemente + OCR + Bounding Boxes. "
        "Liefert einen fertigen summary_prompt direkt für Nemotron. "
        "Primärer Einstiegspunkt für visual_nemotron_agent_v4."
    ),
    parameters=[
        P("image_path", "string", "Absoluter Pfad zum Screenshot (PNG/JPEG)"),
    ],
    capabilities=["vision", "ui_detection", "ocr", "automation"],
    category=ToolCategory.VISION,
    returns="dict",
    timeout=60.0,
)
async def florence2_full_analysis(image_path: str) -> dict:
    """Vollanalyse eines Screenshots für Nemotron-Pipeline."""
    try:
        image = await asyncio.to_thread(_load_image, image_path)
        return await asyncio.to_thread(_full_analysis, image)
    except Exception as e:
        log.error(f"florence2_full_analysis Fehler: {e}")
        return {"error": str(e), "success": False}


@tool(
    name="florence2_detect_ui",
    description="Erkennt UI-Elemente (Buttons, Felder, Icons) mit exakten Pixel-Positionen und Bounding Boxes.",
    parameters=[
        P("image_path", "string", "Absoluter Pfad zum Screenshot"),
    ],
    capabilities=["vision", "ui_detection", "automation"],
    category=ToolCategory.VISION,
    returns="dict",
    timeout=30.0,
)
async def florence2_detect_ui(image_path: str) -> dict:
    """UI-Elemente mit Bounding Boxes erkennen."""
    try:
        image = await asyncio.to_thread(_load_image, image_path)
        return await asyncio.to_thread(_detect_ui, image)
    except Exception as e:
        log.error(f"florence2_detect_ui Fehler: {e}")
        return {"error": str(e), "success": False}


@tool(
    name="florence2_ocr",
    description="OCR mit Bounding Boxes — Text und exakte Pixelpositionen aus einem Screenshot.",
    parameters=[
        P("image_path", "string", "Absoluter Pfad zum Screenshot"),
    ],
    capabilities=["vision", "ocr", "automation"],
    category=ToolCategory.VISION,
    returns="dict",
    timeout=30.0,
)
async def florence2_ocr(image_path: str) -> dict:
    """Text + Positionen aus Screenshot extrahieren."""
    try:
        image = await asyncio.to_thread(_load_image, image_path)
        return await asyncio.to_thread(_ocr, image)
    except Exception as e:
        log.error(f"florence2_ocr Fehler: {e}")
        return {"error": str(e), "success": False}


@tool(
    name="florence2_analyze_region",
    description=(
        "Analysiert einen spezifischen Bildbereich per Bounding Box. "
        "Optional: Frage stellen (VQA). Nützlich für Detailansichten."
    ),
    parameters=[
        P("image_path", "string", "Absoluter Pfad zum Screenshot"),
        P("bbox", "array", "Bounding Box [x1, y1, x2, y2] in Pixeln"),
        P("question", "string", "Optionale Frage zum Bereich (VQA)", required=False, default=""),
    ],
    capabilities=["vision", "ocr", "ui_detection"],
    category=ToolCategory.VISION,
    returns="string",
    timeout=30.0,
)
async def florence2_analyze_region(image_path: str, bbox: list, question: str = "") -> str:
    """Bereich eines Screenshots analysieren."""
    try:
        image = await asyncio.to_thread(_load_image, image_path)
        region = image.crop(bbox)
        if question:
            return await asyncio.to_thread(
                lambda: _run_task(region, "<VQA>", question).get("<VQA>", "")
            )
        return await asyncio.to_thread(
            lambda: _run_task(region, "<DETAILED_CAPTION>").get("<DETAILED_CAPTION>", "")
        )
    except Exception as e:
        log.error(f"florence2_analyze_region Fehler: {e}")
        return f"Fehler: {e}"

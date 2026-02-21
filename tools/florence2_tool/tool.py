"""
Florence-2 Tool für Timus MCP-Server.

Registriert 6 Tools via @tool Decorator (registry_v2):
    florence2_health          — Modell-Status prüfen
    florence2_full_analysis   — Vollanalyse → fertiger Prompt für Nemotron
    florence2_hybrid_analysis — Hybrid: Florence-2 (CAPTION+OD) + PaddleOCR
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
log.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Timus Tool-Registry
# ---------------------------------------------------------------------------
from tools.tool_registry_v2 import tool, P, C, ToolCategory

# ---------------------------------------------------------------------------
# Singleton: Modell nur einmal laden
# ---------------------------------------------------------------------------
_model = None
_processor = None
_paddle_ocr = None
_paddle_ocr_init_failed = False
_device: str = "cpu"
_model_path: str = os.getenv("FLORENCE2_MODEL", "microsoft/Florence-2-large-ft")
_enabled: bool = os.getenv("FLORENCE2_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
# FLORENCE2_DEVICE: "auto" (default) | "cpu" | "cuda"
# "auto" = CUDA wenn verfügbar, sonst CPU
# "cpu"  = erzwinge CPU (sicher, kein CUDA-Conflict, ~5-10s statt ~1s)
_device_override: str = os.getenv("FLORENCE2_DEVICE", "auto").lower()
MIN_DIM = 10


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

    if _device_override == "cpu":
        _device = "cpu"
    elif _device_override == "cuda":
        _device = "cuda"
    else:
        _device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info(f"Florence-2 Device: {_device} (override={_device_override})")

    _processor = AutoProcessor.from_pretrained(
        _model_path,
        trust_remote_code=True,
    )

    def _load_on_device(target_device: str):
        dtype = torch.float16 if target_device == "cuda" else torch.float32
        return AutoModelForCausalLM.from_pretrained(
            _model_path,
            torch_dtype=dtype,
            trust_remote_code=True,
        ).to(target_device)

    # CUDA→CPU Fallback: wenn GPU busy/unavailable → automatisch CPU
    if _device == "cuda":
        try:
            _model = _load_on_device("cuda")
        except Exception as cuda_err:
            log.warning(
                f"Florence-2 CUDA fehlgeschlagen ({cuda_err.__class__.__name__})"
                f" → CPU-Fallback"
            )
            _device = "cpu"
            _model = _load_on_device("cpu")
    else:
        _model = _load_on_device(_device)

    _model.eval()
    elapsed = time.time() - t0
    log.info(f"Florence-2 geladen auf {_device} in {elapsed:.1f}s")
    return _model, _processor


def _unload_model():
    """Gibt VRAM frei (für Notfall-Szenarien)."""
    global _model, _processor, _paddle_ocr, _paddle_ocr_init_failed
    if _model is not None:
        import torch
        del _model
        del _processor
        _model = None
        _processor = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        log.info("Florence-2 aus VRAM entladen")
    if _paddle_ocr is not None:
        _paddle_ocr = None
        log.info("PaddleOCR Instanz entladen")
    _paddle_ocr_init_failed = False


def _get_paddle_ocr():
    """Lädt PaddleOCR lazy auf CPU (keine VRAM-Konkurrenz mit Florence-2)."""
    global _paddle_ocr, _paddle_ocr_init_failed
    if _paddle_ocr is not None:
        return _paddle_ocr
    if _paddle_ocr_init_failed:
        return None

    try:
        from paddleocr import PaddleOCR
    except Exception as e:
        _paddle_ocr_init_failed = True
        log.warning(f"PaddleOCR Import fehlgeschlagen: {e}")
        return None

    # Unterstützt alte und neue PaddleOCR-API-Varianten.
    configs = [
        {
            "use_angle_cls": True,
            "lang": "en",
            "use_gpu": False,
            "show_log": False,
        },
        {
            "lang": "en",
            "device": "cpu",
            "enable_hpi": False,
            "enable_mkldnn": False,
            "cpu_threads": 4,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        },
        {
            "lang": "en",
            "device": "cpu",
            "enable_hpi": False,
            "enable_mkldnn": False,
            "cpu_threads": 4,
        },
    ]
    last_err = None
    for cfg in configs:
        try:
            _paddle_ocr = PaddleOCR(**cfg)
            log.info(f"PaddleOCR geladen (CPU) mit Config: {sorted(cfg.keys())}")
            return _paddle_ocr
        except Exception as e:
            last_err = e

    _paddle_ocr_init_failed = True
    log.warning(f"PaddleOCR nicht verfügbar: {last_err}")
    return _paddle_ocr


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


def _paddle_ocr_texts(image) -> tuple[list, str]:
    """Text + Positionen via PaddleOCR. Gibt (liste, backend_status) zurück."""
    import numpy as np

    ocr = _get_paddle_ocr()
    if ocr is None:
        return [], "paddleocr_unavailable"

    texts = []
    try:
        results = ocr.ocr(np.array(image), cls=True)
    except TypeError as e:
        # Neuere PaddleOCR-Versionen unterstützen kein cls-Argument mehr.
        if "cls" in str(e):
            try:
                results = ocr.ocr(np.array(image))
            except Exception as inner_e:
                log.warning(f"PaddleOCR Laufzeitfehler: {inner_e}")
                return [], "paddleocr_error"
        else:
            log.warning(f"PaddleOCR Laufzeitfehler: {e}")
            return [], "paddleocr_error"
    except Exception as e:
        log.warning(f"PaddleOCR Laufzeitfehler: {e}")
        return [], "paddleocr_error"

    def _push_text(pts, text, conf):
        x1 = int(min(p[0] for p in pts))
        y1 = int(min(p[1] for p in pts))
        x2 = int(max(p[0] for p in pts))
        y2 = int(max(p[1] for p in pts))
        texts.append({
            "text": str(text).strip(),
            "bbox": [x1, y1, x2, y2],
            "center": [(x1 + x2) // 2, (y1 + y2) // 2],
            "confidence": round(float(conf), 2),
        })

    # Legacy-Format: [[ [pts, (text, conf)], ... ]]
    if isinstance(results, list) and results and isinstance(results[0], list):
        for line in results[0]:
            try:
                pts, rec = line
                if not rec or len(rec) < 2:
                    continue
                text, conf = rec
                _push_text(pts, text, conf)
            except Exception:
                continue
    # Neuere Formate: Liste von Dicts (ppocr v3)
    elif isinstance(results, list):
        for item in results:
            try:
                rec_texts = item.get("rec_texts") or []
                rec_scores = item.get("rec_scores") or []
                polys = item.get("rec_polys") or item.get("dt_polys") or []
                for i, text in enumerate(rec_texts):
                    pts = polys[i] if i < len(polys) else None
                    conf = rec_scores[i] if i < len(rec_scores) else 0.0
                    if pts is None:
                        continue
                    _push_text(pts, text, conf)
            except Exception:
                continue

    filtered = [t for t in texts if t["text"] and (t["bbox"][2] - t["bbox"][0]) >= 5]
    return filtered, "paddleocr"


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


def _hybrid_analysis(image) -> dict:
    caption = _caption(image)
    ui = _detect_ui(image)
    texts, ocr_backend = _paddle_ocr_texts(image)

    ui_elems = [
        e for e in ui["elements"]
        if (e["bbox"][2] - e["bbox"][0]) >= MIN_DIM
        and (e["bbox"][3] - e["bbox"][1]) >= MIN_DIM
    ]

    ui_lines = []
    for i, e in enumerate(ui_elems):
        b = e["bbox"]
        w, h = b[2] - b[0], b[3] - b[1]
        ui_lines.append(
            f"[{i + 1}] {e['label'].upper()} "
            f"center=({e['center'][0]},{e['center'][1]}) size={w}x{h}px"
        )

    txt_lines = [
        f"[{chr(65 + i)}] \"{t['text']}\" "
        f"@ ({t['center'][0]},{t['center'][1]}) conf={t['confidence']}"
        for i, t in enumerate(texts)
    ]

    summary_prompt = (
        f"Auflösung: {image.width}x{image.height}px\n"
        f"Bildschirm: {caption}\n\n"
        f"INTERAKTIVE ELEMENTE ({len(ui_elems)}):\n"
        + ("\n".join(ui_lines) if ui_lines else "(keine erkannt)")
        + f"\n\nTEXT AUF DEM BILDSCHIRM ({len(texts)}):\n"
        + ("\n".join(txt_lines) if txt_lines else "(kein Text erkannt)")
    )

    return {
        "caption": caption,
        "ui_elements": ui_elems,
        "text_elements": texts,
        "element_count": len(ui_elems),
        "text_count": len(texts),
        "summary_prompt": summary_prompt,
        "image_size": [image.width, image.height],
        "model": _model_path,
        "device": _device,
        "ocr_backend": ocr_backend,
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
    name="florence2_hybrid_analysis",
    description=(
        "Hybrid Screenshot-Analyse: Florence-2 für CAPTION + UI-Detection "
        "und PaddleOCR für Text mit Confidence und Bounding Boxes."
    ),
    parameters=[
        P("image_path", "string", "Absoluter Pfad zum Screenshot (PNG/JPEG)"),
    ],
    capabilities=["vision", "ui_detection", "ocr", "automation"],
    category=ToolCategory.VISION,
    returns="dict",
    timeout=60.0,
)
async def florence2_hybrid_analysis(image_path: str) -> dict:
    """Hybridanalyse: UI via Florence-2, OCR via PaddleOCR."""
    try:
        image = await asyncio.to_thread(_load_image, image_path)
        return await asyncio.to_thread(_hybrid_analysis, image)
    except Exception as e:
        log.error(f"florence2_hybrid_analysis Fehler: {e}")
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

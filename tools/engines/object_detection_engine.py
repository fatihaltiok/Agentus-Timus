# tools/engines/object_detection_engine.py (Refactored)

import logging
import os
import time
from PIL import Image
import torch
from typing import List, Dict, Any

# Importiere den zentralen Logger.
from tools.shared_context import log

# C3 Telemetrie (best-effort import)
try:
    from tools.engines.vision_telemetry import vision_telemetry, is_oom_error
    _C3_TELEMETRY = True
except Exception:
    vision_telemetry = None  # type: ignore[assignment]
    _C3_TELEMETRY = False

    def is_oom_error(exc: BaseException) -> bool:  # type: ignore[misc]
        msg = str(exc).lower()
        return isinstance(exc, RuntimeError) and "out of memory" in msg
from utils.hf_model_pinning import resolve_pinned_revision

# Fange den Import-Fehler ab, damit der Server nicht abstürzt, wenn Pakete fehlen.
try:
    from transformers import YolosImageProcessor, YolosForObjectDetection
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    log.error("KRITISCH: 'transformers' und/oder 'timm' sind nicht installiert. Die ObjectDetectionEngine ist nicht verfügbar.")
    YolosImageProcessor, YolosForObjectDetection = None, None
    TRANSFORMERS_AVAILABLE = False

class ObjectDetectionEngine:
    """
    Eine Singleton-Klasse zur Erkennung von UI-Elementen mit dem YOLOS-Modell.
    Die Initialisierung des Modells erfolgt explizit über die `initialize`-Methode.
    """
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(ObjectDetectionEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Der Konstruktor initialisiert nur die Zustandsvariablen, lädt aber keine Modelle.
        if hasattr(self, 'initialized'):
            return
        
        self.model: Any = None
        self.image_processor: Any = None
        self.device: str = "cpu"
        self.initialized: bool = False

    def initialize(self):
        """
        Lädt das YOLOS-Modell und den Prozessor in den Speicher.
        Diese Methode wird zentral vom `mcp_server` beim Start aufgerufen.
        """
        if self.initialized:
            log.info("ObjectDetectionEngine ist bereits initialisiert.")
            return

        if not TRANSFORMERS_AVAILABLE:
            log.warning("Kann ObjectDetectionEngine nicht initialisieren, da erforderliche Pakete fehlen.")
            return

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info(f"Initialisiere ObjectDetectionEngine (YOLOS) auf Gerät '{self.device}'...")
        
        try:
            # Lade das Modell und den Prozessor
            model_name = os.getenv("YOLOS_MODEL", "hustvl/yolos-tiny")
            _t0 = 0.0
            if _C3_TELEMETRY and vision_telemetry:
                _t0 = vision_telemetry.init_start("object_detection", model_name, self.device)
            revision = resolve_pinned_revision(model_name, "YOLOS_MODEL_REVISION")
            self.model = YolosForObjectDetection.from_pretrained(model_name, revision=revision).to(self.device)
            self.image_processor = YolosImageProcessor.from_pretrained(model_name, revision=revision)
            self.initialized = True
            if _C3_TELEMETRY and vision_telemetry:
                vision_telemetry.init_done("object_detection", model_name, self.device, _t0, success=True)
            log.info(f"✅ ObjectDetectionEngine (YOLOS) '{model_name}' erfolgreich initialisiert.")
        except Exception as e:
            self.initialized = False
            if _C3_TELEMETRY and vision_telemetry:
                vision_telemetry.init_done(
                    "object_detection",
                    os.getenv("YOLOS_MODEL", "hustvl/yolos-tiny"),
                    self.device,
                    _t0,
                    success=False,
                    error_class=type(e).__name__,
                    error_msg=str(e),
                )
                vision_telemetry.error("object_detection", os.getenv("YOLOS_MODEL", "hustvl/yolos-tiny"), self.device, e)
            log.error(f"Konnte YOLOS-Modell nicht laden: {e}", exc_info=True)
            # Wir werfen hier keinen Fehler mehr, damit der Server auch ohne diese Engine starten kann.
            # Der `initialized`-Status reicht aus, um die Funktion zu blockieren.

    def find_ui_elements(self, image: Image.Image, confidence_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """
        Analysiert ein Bild und gibt eine Liste der gefundenen UI-Elemente zurück.
        """
        if not self.initialized:
            log.warning("Aufruf von find_ui_elements, aber die Engine ist nicht initialisiert.")
            return []
        
        # C3 Telemetrie: Timing + OOM-Guard
        img_w, img_h = (image.size if hasattr(image, "size") else (0, 0))
        _model_name = os.getenv("YOLOS_MODEL", "hustvl/yolos-tiny")
        _t0 = time.monotonic() if _C3_TELEMETRY else 0.0
        if _C3_TELEMETRY and vision_telemetry:
            vision_telemetry.infer_start("object_detection", _model_name, self.device,
                                         image_w=img_w, image_h=img_h)

        try:
            inputs = self.image_processor(images=image, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.model(**inputs)

            target_sizes = torch.tensor([image.size[::-1]])
            results = self.image_processor.post_process_object_detection(
                outputs, threshold=confidence_threshold, target_sizes=target_sizes)[0]

            elements = []
            for score, label_idx, box in zip(results["scores"], results["labels"], results["boxes"]):
                label = self.model.config.id2label[label_idx.item()]
                box_coords = [round(i, 2) for i in box.tolist()]
                elements.append({
                    "type": label,
                    "confidence": round(score.item(), 4),
                    "bbox": box_coords
                })

            if _C3_TELEMETRY and vision_telemetry:
                vision_telemetry.infer_done("object_detection", _model_name, self.device,
                                            _t0, image_w=img_w, image_h=img_h, success=True)
            log.info(f"✅ {len(elements)} UI-Elemente durch Objekterkennung gefunden.")
            return elements

        except RuntimeError as e:
            if is_oom_error(e):
                log.error(f"❌ ObjectDetection OOM auf {self.device}: {e}")
                if _C3_TELEMETRY and vision_telemetry:
                    vision_telemetry.oom("object_detection", _model_name, self.device, str(e))
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
                return []
            log.error(f"Fehler während der YOLOS-Inferenz: {e}", exc_info=True)
            if _C3_TELEMETRY and vision_telemetry:
                vision_telemetry.infer_done("object_detection", _model_name, self.device,
                                            _t0, image_w=img_w, image_h=img_h, success=False,
                                            error_class=type(e).__name__, error_msg=str(e))
                vision_telemetry.error("object_detection", _model_name, self.device, e)
            return []

        except Exception as e:
            log.error(f"Fehler während der YOLOS-Inferenz: {e}", exc_info=True)
            if _C3_TELEMETRY and vision_telemetry:
                vision_telemetry.infer_done("object_detection", _model_name, self.device,
                                            _t0, image_w=img_w, image_h=img_h, success=False,
                                            error_class=type(e).__name__, error_msg=str(e))
                vision_telemetry.error("object_detection", _model_name, self.device, e)
            return []

# Erstelle die globale Singleton-Instanz.
# Diese wird nun vom Server importiert, initialisiert und im shared_context abgelegt.
object_detection_engine_instance = ObjectDetectionEngine()
log.info("✅ Singleton-Instanz der ObjectDetectionEngine erstellt.")

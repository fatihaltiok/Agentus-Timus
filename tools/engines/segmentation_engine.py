# tools/engines/segmentation_engine.py (Refactored)

import logging
import os
import time
from typing import Any, List, Dict

import torch
import numpy as np
from PIL import Image

# Importiere den zentralen Logger
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

# Fange Import-Fehler ab, um den Serverstart nicht zu blockieren
try:
    from transformers import SamModel, SamProcessor, CLIPProcessor, CLIPForImageClassification
    TRANSFORMERS_AVAILABLE = True
    log.info("✅ Transformers erfolgreich importiert")
except ImportError as e:
    log.error(f"⚠️ Transformers nicht verfügbar: {e}")
    SamModel, SamProcessor, CLIPProcessor, CLIPForImageClassification = None, None, None, None
    TRANSFORMERS_AVAILABLE = False

class SegmentationEngine:
    """
    Eine Singleton-Klasse zur Segmentierung von Bildern mit SAM, gefolgt von einer
    Klassifizierung der Segmente mit CLIP, um UI-Elemente zu identifizieren.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Implementiert das Singleton-Pattern. Stellt sicher, dass nur eine einzige
        Instanz dieser ressourcenintensiven Klasse existiert.
        """
        # Prüfe, ob die Klassenvariable `_instance` bereits eine Instanz enthält.
        if not cls._instance:
            # Wenn nicht, erstelle eine neue Instanz mit der `__new__`-Methode der
            # übergeordneten Klasse (object).
            log.debug("Erstelle neue Singleton-Instanz für SegmentationEngine.")
            cls._instance = super(SegmentationEngine, cls).__new__(cls)
        else:
            # Wenn bereits eine Instanz existiert, gib einfach nur eine Warnung aus
            # und gib die bestehende Instanz zurück.
            log.debug("SegmentationEngine-Instanz existiert bereits. Gebe bestehende Instanz zurück.")
        
        # Gib immer die in `_instance` gespeicherte Instanz zurück.
        return cls._instance

    def __init__(self):
        """Initialisiert nur die Zustandsvariablen, lädt aber keine Modelle."""
        if hasattr(self, 'initialized'):
            return
        
        self.sam_model: Any = None
        self.sam_processor: Any = None
        self.clip_model: Any = None
        self.clip_processor: Any = None
        self.device: str = "cpu"
        self.initialized: bool = False

    def initialize(self):
        """
        Lädt die SAM- und CLIP-Modelle. Wird zentral vom Server aufgerufen.
        """
        if self.initialized:
            log.info("SegmentationEngine ist bereits initialisiert.")
            return

        if not TRANSFORMERS_AVAILABLE:
            log.warning("⚠️ Kann SegmentationEngine nicht initialisieren, da 'transformers' fehlt.")
            return

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info(f"🔄 Initialisiere SegmentationEngine (SAM+CLIP) auf Gerät '{self.device}'...")

        try:
            sam_model_name = os.getenv("SAM_MODEL", "facebook/sam-vit-base")
            _t0 = 0.0
            if _C3_TELEMETRY and vision_telemetry:
                _t0 = vision_telemetry.init_start("segmentation", sam_model_name, self.device)
            sam_revision = resolve_pinned_revision(sam_model_name, "SAM_MODEL_REVISION")
            log.info("📥 Lade SAM-Modell...")
            self.sam_model = SamModel.from_pretrained(sam_model_name, revision=sam_revision).to(self.device)
            self.sam_processor = SamProcessor.from_pretrained(sam_model_name, revision=sam_revision)

            clip_model_name = os.getenv("CLIP_MODEL", "openai/clip-vit-base-patch32")
            clip_revision = resolve_pinned_revision(clip_model_name, "CLIP_MODEL_REVISION")
            log.info("📥 Lade CLIP-Modell...")
            self.clip_model = CLIPForImageClassification.from_pretrained(
                clip_model_name,
                revision=clip_revision,
            ).to(self.device)
            self.clip_processor = CLIPProcessor.from_pretrained(
                clip_model_name,
                revision=clip_revision,
            )

            self.initialized = True
            if _C3_TELEMETRY and vision_telemetry:
                vision_telemetry.init_done("segmentation", sam_model_name, self.device, _t0, success=True)
            log.info("✅ SegmentationEngine (SAM+CLIP) erfolgreich initialisiert.")
        except Exception as e:
            self.initialized = False
            if _C3_TELEMETRY and vision_telemetry:
                vision_telemetry.init_done(
                    "segmentation",
                    os.getenv("SAM_MODEL", "facebook/sam-vit-base"),
                    self.device,
                    _t0,
                    success=False,
                    error_class=type(e).__name__,
                    error_msg=str(e),
                )
                vision_telemetry.error("segmentation", os.getenv("SAM_MODEL", "facebook/sam-vit-base"), self.device, e)
            log.error(f"❌ Fehler beim Laden der Segmentierungs-Modelle: {e}", exc_info=True)

    def get_ui_elements_from_image(self, image: Image.Image) -> List[Dict[str, Any]]:
        """
        Segmentiert ein Bild und klassifiziert die Segmente, um UI-Elemente zu finden.
        """
        if not self.initialized:
            log.warning("Aufruf von get_ui_elements_from_image, aber die Engine ist nicht initialisiert.")
            return []

        log.info(f"Segmentiere Bild der Größe {image.size} mit SAM...")

        # C3 Telemetrie: Timing + OOM-Guard
        img_w, img_h = (image.size if hasattr(image, "size") else (0, 0))
        _sam_name = os.getenv("SAM_MODEL", "facebook/sam-vit-base")
        _t0 = time.monotonic() if _C3_TELEMETRY else 0.0
        if _C3_TELEMETRY and vision_telemetry:
            vision_telemetry.infer_start("segmentation", _sam_name, self.device,
                                         image_w=img_w, image_h=img_h)

        try:
            if not all([self.sam_model, self.sam_processor, self.clip_model, self.clip_processor]):
                raise RuntimeError("Ein oder mehrere Modelle der SegmentationEngine sind nicht geladen.")

            inputs = self.sam_processor(image, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.sam_model(**inputs, output_scores=True)
            
            # KORREKTUR: Fehlende Argumente hier wieder eingefügt.
            masks = self.sam_processor.image_processor.post_process_masks(
                outputs.pred_masks.cpu(), 
                inputs["original_sizes"].cpu(), 
                inputs["reshaped_input_sizes"].cpu()
            )[0]
            
            iou_scores = outputs.iou_scores.cpu()[0]
            
            high_quality_masks = []
            for i, score_tensor in enumerate(iou_scores[0]):
                if score_tensor.item() > 0.45: # Dein optimierter Schwellenwert
                    high_quality_masks.append(masks[0][i])
            
            if not high_quality_masks:
                log.warning("SAM hat keine hochwertigen Segmente gefunden.")
                if _C3_TELEMETRY and vision_telemetry:
                    vision_telemetry.infer_done("segmentation", _sam_name, self.device,
                                                _t0, image_w=img_w, image_h=img_h, success=True)
                return []

            # Schritt 3: Jede hochwertige Maske mit CLIP klassifizieren
            candidate_labels = ["button", "icon", "text input field", "checkbox", "slider", "menu bar", "window title bar"]
            final_elements = []
            
            log.info(f"Klassifiziere {len(high_quality_masks)} hochwertige Segmente mit CLIP...")
            
            # KORREKTUR: Diese Schleife gehört IN den try-Block.
            for mask_tensor in high_quality_masks:
                mask_pil = Image.fromarray((mask_tensor.cpu().numpy() * 255).astype(np.uint8))
                masked_image = Image.new("RGB", image.size)
                masked_image.paste(image, mask=mask_pil)
                
                # CLIP-Klassifizierung
                clip_inputs = self.clip_processor(text=candidate_labels, images=masked_image, return_tensors="pt", padding=True)
                model_inputs = {"pixel_values": clip_inputs["pixel_values"].to(self.device)}
                with torch.no_grad():
                    logits = self.clip_model(**model_inputs).logits
                
                probs = logits.softmax(dim=-1)
                best_prob_index = probs.argmax().item()
                confidence = probs[0][best_prob_index].item()
                
                if confidence > 0.1:
                    best_label = candidate_labels[best_prob_index]
                    y_indices, x_indices = np.where(mask_tensor.cpu().numpy() > 0.5)
                    if len(y_indices) > 0 and len(x_indices) > 0:
                        x1, x2 = int(x_indices.min()), int(x_indices.max())
                        y1, y2 = int(y_indices.min()), int(y_indices.max())
                        
                        # Filterung zu großer oder zu kleiner Boxen
                        if (x2 - x1) < (image.width * 0.9) and (y2 - y1) < (image.height * 0.9) and (x2 - x1) > 10:
                            element = {'type': best_label, 'confidence': float(f"{confidence:.4f}"), 'bbox': [x1, y1, x2 - x1, y2 - y1]}
                            final_elements.append(element)
            
            # KORREKTUR: Log-Ausgabe und return gehören NACH die Schleife.
            if _C3_TELEMETRY and vision_telemetry:
                vision_telemetry.infer_done("segmentation", _sam_name, self.device,
                                            _t0, image_w=img_w, image_h=img_h, success=True)
            log.info(f"✅ {len(final_elements)} UI-Elemente nach Segmentierung und Filterung gefunden.")
            return final_elements

        except RuntimeError as e:
            if is_oom_error(e):
                log.error(f"❌ Segmentation OOM auf {self.device}: {e}")
                if _C3_TELEMETRY and vision_telemetry:
                    vision_telemetry.oom("segmentation", _sam_name, self.device, str(e))
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
                return []
            log.error(f"Fehler während der Segmentierung/Klassifizierung: {e}", exc_info=True)
            if _C3_TELEMETRY and vision_telemetry:
                vision_telemetry.infer_done("segmentation", _sam_name, self.device,
                                            _t0, image_w=img_w, image_h=img_h, success=False,
                                            error_class=type(e).__name__, error_msg=str(e))
                vision_telemetry.error("segmentation", _sam_name, self.device, e)
            return []

        except Exception as e:
            log.error(f"Fehler während der Segmentierung/Klassifizierung: {e}", exc_info=True)
            if _C3_TELEMETRY and vision_telemetry:
                vision_telemetry.infer_done("segmentation", _sam_name, self.device,
                                            _t0, image_w=img_w, image_h=img_h, success=False,
                                            error_class=type(e).__name__, error_msg=str(e))
                vision_telemetry.error("segmentation", _sam_name, self.device, e)
            return []

# Erstelle eine globale Instanz der SegmentationEngine
# Diese wird von den visuellen Tools verwendet
segmentation_engine_instance = SegmentationEngine()

# tools/engines/segmentation_engine.py

import logging
from PIL import Image
import torch
import numpy as np

try:
    from transformers import SamModel, SamProcessor, ClipProcessor, ClipModel
except ImportError:
    SamModel, SamProcessor, ClipProcessor, ClipModel = None, None, None, None

log = logging.getLogger(__name__)

class SegmentationEngine:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SegmentationEngine, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized') and self.initialized:
            return
            
        if SamModel is None:
            log.error("Die 'transformers'-Bibliothek ist nicht oder nicht korrekt installiert.")
            self.initialized = False
            return

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info(f"SegmentationEngine wird auf Gerät '{self.device}' initialisiert.")
        
        self.sam_model, self.sam_processor, self.clip_model, self.clip_processor = None, None, None, None
        
        try:
            log.info("Lade SAM-Modell (facebook/sam-vit-base)...")
            self.sam_model = SamModel.from_pretrained("facebook/sam-vit-base").to(self.device)
            self.sam_processor = SamProcessor.from_pretrained("facebook/sam-vit-base")
            log.info("✅ SAM-Modell geladen.")

            log.info("Lade CLIP-Modell (openai/clip-vit-base-patch32)...")
            self.clip_model = ClipModel.from_pretrained("openai/clip-vit-base-patch32").to(self.device)
            self.clip_processor = ClipProcessor.from_pretrained("openai/clip-vit-base-patch32")
            log.info("✅ CLIP-Modell geladen.")

        except Exception as e:
            log.error(f"Fehler beim Laden eines Hugging Face Modells: {e}", exc_info=True)
            self.initialized = False
            raise RuntimeError(f"Konnte Modelle nicht laden: {e}")

        self.initialized = True
        log.info("SegmentationEngine erfolgreich initialisiert.")

    def get_ui_elements_from_image(self, image: Image.Image) -> list:
        if not self.initialized: return []
        log.info(f"Segmentiere Bild der Größe {image.size}...")
        
        try:
            inputs = self.sam_processor(images=image, return_tensors="pt").to(self.device)
            with torch.no_grad(): outputs = self.sam_model(**inputs)
            masks = self.sam_processor.image_processor.post_process_masks(outputs.pred_masks.cpu(), inputs["original_sizes"].cpu(), inputs["reshaped_input_sizes"].cpu())[0]
            
            candidate_labels = ["button", "icon", "text input field", "checkbox", "slider", "menu", "window title"]
            final_elements = []
            
            for mask_tensor in masks[0]:
                mask_pil = Image.fromarray((mask_tensor.cpu().numpy() * 255).astype(np.uint8))
                masked_image = Image.new("RGB", image.size); masked_image.paste(image, mask=mask_pil)
                
                clip_inputs = self.clip_processor(text=candidate_labels, images=masked_image, return_tensors="pt", padding=True).to(self.device)
                with torch.no_grad(): clip_outputs = self.clip_model(**clip_inputs)
                
                logits_per_image = clip_outputs.logits_per_image
                probs = logits_per_image.softmax(dim=1)
                best_prob_index = probs.argmax().item()
                best_label = candidate_labels[best_prob_index]
                confidence = probs[0][best_prob_index]

                # KORREKTUR: Wir loggen jetzt JEDEN Kandidaten, bevor wir ihn filtern.
                log.info(f"  -> Kandidat gefunden: Typ='{best_label}', Zuversicht={confidence:.4f}")

                # KORREKTUR: Wir senken den Schwellenwert, um mehr Ergebnisse zu sehen.
                if confidence > 0.1:
                    y_indices, x_indices = np.where(mask_tensor.cpu().numpy() > 0.5)
                    if len(y_indices) > 0 and len(x_indices) > 0:
                        x1, x2 = int(x_indices.min()), int(x_indices.max())
                        y1, y2 = int(y_indices.min()), int(y_indices.max())
                        bbox = [x1, y1, x2 - x1, y2 - y1]
                        
                        final_elements.append({
                            'type': best_label,
                            'confidence': float(f"{confidence:.4f}"),
                            'bbox': bbox
                        })

            log.info(f"✅ {len(final_elements)} UI-Elemente nach Filterung gefunden.")
            return final_elements

        except Exception as e:
            log.error(f"Fehler während der Bildverarbeitung in der Engine: {e}", exc_info=True)
            return []

segmentation_engine_instance = SegmentationEngine()
# tools/engines/segmentation_engine.py (Refactored)

import logging
from typing import Any, List, Dict

import torch
import numpy as np
from PIL import Image

# Importiere den zentralen Logger
from tools.shared_context import log

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
            log.info("📥 Lade SAM-Modell...")
            self.sam_model = SamModel.from_pretrained("facebook/sam-vit-base").to(self.device)
            self.sam_processor = SamProcessor.from_pretrained("facebook/sam-vit-base")

            log.info("📥 Lade CLIP-Modell...")
            self.clip_model = CLIPForImageClassification.from_pretrained("openai/clip-vit-base-patch32").to(self.device)
            self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

            self.initialized = True
            log.info("✅ SegmentationEngine (SAM+CLIP) erfolgreich initialisiert.")
        except Exception as e:
            self.initialized = False
            log.error(f"❌ Fehler beim Laden der Segmentierungs-Modelle: {e}", exc_info=True)

    def get_ui_elements_from_image(self, image: Image.Image) -> List[Dict[str, Any]]:
        """
        Segmentiert ein Bild und klassifiziert die Segmente, um UI-Elemente zu finden.
        """
        if not self.initialized:
            log.warning("Aufruf von get_ui_elements_from_image, aber die Engine ist nicht initialisiert.")
            return []

        log.info(f"Segmentiere Bild der Größe {image.size} mit SAM...")
        
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
            log.info(f"✅ {len(final_elements)} UI-Elemente nach Segmentierung und Filterung gefunden.")
            return final_elements
            
        except Exception as e:
            log.error(f"Fehler während der Segmentierung/Klassifizierung: {e}", exc_info=True)
            return []

# Erstelle eine globale Instanz der SegmentationEngine
# Diese wird von den visuellen Tools verwendet
segmentation_engine_instance = SegmentationEngine()
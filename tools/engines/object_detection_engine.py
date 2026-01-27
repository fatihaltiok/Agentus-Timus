# tools/engines/object_detection_engine.py (Refactored)

import logging
from PIL import Image
import torch
from typing import List, Dict, Any

# Importiere den zentralen Logger.
from tools.shared_context import log

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
            model_name = 'hustvl/yolos-tiny'
            self.model = YolosForObjectDetection.from_pretrained(model_name).to(self.device)
            self.image_processor = YolosImageProcessor.from_pretrained(model_name)
            self.initialized = True
            log.info(f"✅ ObjectDetectionEngine (YOLOS) '{model_name}' erfolgreich initialisiert.")
        except Exception as e:
            self.initialized = False
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
        
        # Die Kernlogik der Inferenz bleibt unverändert.
        try:
            inputs = self.image_processor(images=image, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.model(**inputs)

            target_sizes = torch.tensor([image.size[::-1]])
            results = self.image_processor.post_process_object_detection(outputs, threshold=confidence_threshold, target_sizes=target_sizes)[0]
            
            elements = []
            for score, label_idx, box in zip(results["scores"], results["labels"], results["boxes"]):
                label = self.model.config.id2label[label_idx.item()]
                box_coords = [round(i, 2) for i in box.tolist()]
                elements.append({
                    "type": label,
                    "confidence": round(score.item(), 4),
                    "bbox": box_coords
                })
            
            log.info(f"✅ {len(elements)} UI-Elemente durch Objekterkennung gefunden.")
            return elements
        except Exception as e:
            log.error(f"Fehler während der YOLOS-Inferenz: {e}", exc_info=True)
            return []

# Erstelle die globale Singleton-Instanz.
# Diese wird nun vom Server importiert, initialisiert und im shared_context abgelegt.
object_detection_engine_instance = ObjectDetectionEngine()
log.info("✅ Singleton-Instanz der ObjectDetectionEngine erstellt.")
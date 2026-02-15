# tools/engines/ocr_engine.py (Multi-Backend OCR Engine v3.0)
"""
Multi-Backend OCR Engine mit Unterstützung für:
- EasyOCR (Default, beste Balance)
- Tesseract (Schnell, gut mit Preprocessing)
- TrOCR (Hugging Face, für schwierige Einzelzeilen)
- PaddleOCR (Optional, production-ready)

Konfiguration per .env:
    OCR_BACKEND=easyocr  # easyocr, tesseract, trocr, paddleocr, auto
    OCR_GPU=1            # 1 = GPU nutzen (falls verfügbar), 0 = nur CPU
    OCR_LANGUAGES=de,en  # Sprachen für OCR
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import cv2

import torch
from PIL import Image

# Importiere den zentralen Logger
from tools.shared_context import log

# ===== BACKEND IMPORTS =====
# EasyOCR
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    log.warning("⚠️ EasyOCR nicht installiert. 'pip install easyocr'")
except RuntimeError as e:
    # Fix für torchvision/torch Inkompatibilität (z.B. operator torchvision::nms does not exist)
    EASYOCR_AVAILABLE = False
    log.warning(f"⚠️ EasyOCR kann nicht geladen werden (torch/torchvision Inkompatibilität): {e}")

# Tesseract
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    log.warning("⚠️ Pytesseract nicht installiert. 'pip install pytesseract'")

# TrOCR (Hugging Face)
try:
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    TROCR_AVAILABLE = True
except ImportError:
    TROCR_AVAILABLE = False
    log.warning("⚠️ Transformers nicht installiert. 'pip install transformers'")

# PaddleOCR
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    # Nicht als Warning, da es optional ist
    log.debug("PaddleOCR nicht installiert (optional).")


class OCREngine:
    """
    Multi-Backend OCR Engine mit automatischer Backend-Auswahl.
    Singleton-Pattern für ressourcenschonendes Modell-Loading.
    """
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(OCREngine, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return

        # Konfiguration aus .env
        self.backend = os.getenv("OCR_BACKEND", "easyocr").lower()
        self.use_gpu = os.getenv("OCR_GPU", "1") == "1"
        self.languages = os.getenv("OCR_LANGUAGES", "de,en").split(",")

        # Backend-spezifische Instanzen
        self.easyocr_reader = None
        self.paddleocr_reader = None
        self.trocr_processor = None
        self.trocr_model = None

        # Device
        self.device = "cuda" if torch.cuda.is_available() and self.use_gpu else "cpu"

        # Status
        self.initialized = False
        self.active_backend = None

        log.info(f"🔧 OCREngine Konfiguration: backend={self.backend}, gpu={self.use_gpu}, languages={self.languages}")

    def initialize(self):
        """
        Initialisiert das gewählte OCR-Backend.
        """
        if self.initialized:
            log.info("OCREngine ist bereits initialisiert.")
            return

        # Auto-Auswahl: Bevorzuge EasyOCR > Tesseract > TrOCR > PaddleOCR
        if self.backend == "auto":
            if EASYOCR_AVAILABLE:
                self.backend = "easyocr"
            elif TESSERACT_AVAILABLE:
                self.backend = "tesseract"
            elif TROCR_AVAILABLE:
                self.backend = "trocr"
            elif PADDLEOCR_AVAILABLE:
                self.backend = "paddleocr"
            else:
                log.error("❌ Kein OCR-Backend verfügbar! Installiere easyocr, pytesseract oder transformers.")
                return

        # Backend initialisieren
        try:
            if self.backend == "easyocr" and EASYOCR_AVAILABLE:
                self._init_easyocr()
            elif self.backend == "tesseract" and TESSERACT_AVAILABLE:
                self._init_tesseract()
            elif self.backend == "trocr" and TROCR_AVAILABLE:
                self._init_trocr()
            elif self.backend == "paddleocr" and PADDLEOCR_AVAILABLE:
                self._init_paddleocr()
            else:
                log.error(f"❌ Backend '{self.backend}' nicht verfügbar oder nicht installiert!")
                return

            self.initialized = True
            self.active_backend = self.backend
            log.info(f"✅ OCREngine initialisiert mit Backend: {self.active_backend} (Device: {self.device})")

        except Exception as e:
            log.error(f"❌ Fehler bei Initialisierung von {self.backend}: {e}", exc_info=True)
            self.initialized = False

    def _init_easyocr(self):
        """Initialisiert EasyOCR."""
        log.info("Initialisiere EasyOCR...")
        self.easyocr_reader = easyocr.Reader(
            self.languages,
            gpu=self.use_gpu
        )
        log.info(f"✅ EasyOCR geladen mit Sprachen: {self.languages}")

    def _init_tesseract(self):
        """Initialisiert Tesseract (keine Modellladung nötig)."""
        log.info("Tesseract als Backend ausgewählt (keine Modellladung nötig).")
        # Prüfe ob tesseract-ocr installiert ist
        try:
            pytesseract.get_tesseract_version()
            log.info(f"✅ Tesseract Version: {pytesseract.get_tesseract_version()}")
        except Exception as e:
            raise RuntimeError(f"Tesseract-OCR binary nicht gefunden: {e}")

    def _init_trocr(self):
        """Initialisiert TrOCR (Hugging Face)."""
        log.info("Initialisiere TrOCR (Hugging Face)...")
        model_name = "microsoft/trocr-base-printed"
        self.trocr_processor = TrOCRProcessor.from_pretrained(model_name)
        self.trocr_model = VisionEncoderDecoderModel.from_pretrained(model_name).to(self.device)
        log.info(f"✅ TrOCR geladen: {model_name} auf {self.device}")

    def _init_paddleocr(self):
        """Initialisiert PaddleOCR."""
        log.info("Initialisiere PaddleOCR...")
        # Bestimme Sprache (PaddleOCR nutzt andere Codes)
        lang_map = {"de": "german", "en": "en", "ch": "ch"}
        ocr_lang = lang_map.get(self.languages[0], "en")

        self.paddleocr_reader = PaddleOCR(
            use_angle_cls=True,
            lang=ocr_lang,
            use_gpu=self.use_gpu,
            show_log=False
        )
        log.info(f"✅ PaddleOCR geladen mit Sprache: {ocr_lang}")

    def is_initialized(self) -> bool:
        """Gibt zurück ob die Engine initialisiert ist."""
        return self.initialized

    def process(self, image: Image.Image, with_boxes: bool = False) -> Dict[str, Any]:
        """
        Führt OCR auf einem Bild durch und gibt strukturierte Ergebnisse zurück.

        Args:
            image: PIL Image
            with_boxes: Wenn True, gibt auch Bounding Boxes zurück

        Returns:
            {
                "extracted_text": [{"text": "...", "confidence": 0.95, "bbox": [x1,y1,x2,y2]}],
                "full_text": "Gesamter Text...",
                "backend": "easyocr"
            }
        """
        if not self.initialized:
            log.warning("OCREngine nicht initialisiert!")
            return {"error": "OCR Engine nicht initialisiert", "extracted_text": [], "full_text": ""}

        try:
            if self.active_backend == "easyocr":
                return self._process_easyocr(image, with_boxes)
            elif self.active_backend == "tesseract":
                return self._process_tesseract(image, with_boxes)
            elif self.active_backend == "trocr":
                return self._process_trocr(image, with_boxes)
            elif self.active_backend == "paddleocr":
                return self._process_paddleocr(image, with_boxes)
            else:
                return {"error": f"Unbekanntes Backend: {self.active_backend}", "extracted_text": [], "full_text": ""}

        except Exception as e:
            log.error(f"Fehler bei OCR-Verarbeitung: {e}", exc_info=True)
            return {"error": str(e), "extracted_text": [], "full_text": ""}

    def _process_easyocr(self, image: Image.Image, with_boxes: bool) -> Dict[str, Any]:
        """Verarbeitet mit EasyOCR."""
        img_array = np.array(image)
        results = self.easyocr_reader.readtext(img_array)

        extracted_text = []
        for bbox, text, confidence in results:
            entry = {
                "text": text,
                "confidence": float(confidence)
            }
            if with_boxes:
                # bbox ist [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                x1 = int(min(p[0] for p in bbox))
                y1 = int(min(p[1] for p in bbox))
                x2 = int(max(p[0] for p in bbox))
                y2 = int(max(p[1] for p in bbox))
                entry["bbox"] = [x1, y1, x2, y2]

            extracted_text.append(entry)

        full_text = " ".join(item["text"] for item in extracted_text)

        return {
            "extracted_text": extracted_text,
            "full_text": full_text,
            "backend": "easyocr",
            "count": len(extracted_text)
        }

    def _process_tesseract(self, image: Image.Image, with_boxes: bool) -> Dict[str, Any]:
        """Verarbeitet mit Tesseract."""
        # Preprocessing für bessere Ergebnisse
        img_array = np.array(image)
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # Adaptive Threshold
        processed = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        # OCR mit Bounding Boxes
        lang = "+".join(self.languages)
        ocr_data = pytesseract.image_to_data(
            processed,
            output_type=pytesseract.Output.DICT,
            lang=lang,
            config='--psm 11'  # Sparse text
        )

        extracted_text = []
        n_boxes = len(ocr_data['text'])

        for i in range(n_boxes):
            text = ocr_data['text'][i].strip()
            conf = int(ocr_data['conf'][i]) if ocr_data['conf'][i] != '-1' else 0

            if not text or conf < 50:
                continue

            entry = {
                "text": text,
                "confidence": conf / 100.0
            }

            if with_boxes:
                x1 = ocr_data['left'][i]
                y1 = ocr_data['top'][i]
                x2 = x1 + ocr_data['width'][i]
                y2 = y1 + ocr_data['height'][i]
                entry["bbox"] = [x1, y1, x2, y2]

            extracted_text.append(entry)

        full_text = " ".join(item["text"] for item in extracted_text)

        return {
            "extracted_text": extracted_text,
            "full_text": full_text,
            "backend": "tesseract",
            "count": len(extracted_text)
        }

    def _process_trocr(self, image: Image.Image, with_boxes: bool) -> Dict[str, Any]:
        """
        Verarbeitet mit TrOCR.
        Hinweis: TrOCR ist ein Zeilenmodell, kein Layout-Modell.
        Gibt nur den Gesamttext zurück, keine einzelnen Boxen.
        """
        pixel_values = self.trocr_processor(images=image, return_tensors="pt").pixel_values.to(self.device)
        generated_ids = self.trocr_model.generate(pixel_values)
        text = self.trocr_processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

        extracted_text = [{
            "text": text,
            "confidence": 1.0  # TrOCR gibt keine Confidence zurück
        }]

        if with_boxes:
            # TrOCR kann keine Boxen liefern, gebe Bild-Dimensionen zurück
            w, h = image.size
            extracted_text[0]["bbox"] = [0, 0, w, h]

        return {
            "extracted_text": extracted_text,
            "full_text": text,
            "backend": "trocr",
            "count": 1
        }

    def _process_paddleocr(self, image: Image.Image, with_boxes: bool) -> Dict[str, Any]:
        """Verarbeitet mit PaddleOCR."""
        img_array = np.array(image)
        results = self.paddleocr_reader.ocr(img_array, cls=True)

        extracted_text = []

        if results and results[0]:
            for line in results[0]:
                bbox_points = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text_info = line[1]  # (text, confidence)
                text = text_info[0]
                confidence = text_info[1]

                entry = {
                    "text": text,
                    "confidence": float(confidence)
                }

                if with_boxes:
                    x1 = int(min(p[0] for p in bbox_points))
                    y1 = int(min(p[1] for p in bbox_points))
                    x2 = int(max(p[0] for p in bbox_points))
                    y2 = int(max(p[1] for p in bbox_points))
                    entry["bbox"] = [x1, y1, x2, y2]

                extracted_text.append(entry)

        full_text = " ".join(item["text"] for item in extracted_text)

        return {
            "extracted_text": extracted_text,
            "full_text": full_text,
            "backend": "paddleocr",
            "count": len(extracted_text)
        }

    def run_ocr(self, image: Image.Image) -> str:
        """
        Rückwärtskompatible Methode: Gibt nur den Text zurück.

        Args:
            image: PIL Image

        Returns:
            Extrahierter Text als String
        """
        result = self.process(image, with_boxes=False)
        return result.get("full_text", "")


# ===== GLOBALE INSTANZ =====
ocr_engine_instance = OCREngine()
log.info(f"✅ Multi-Backend OCREngine erstellt (Backend: {ocr_engine_instance.backend})")

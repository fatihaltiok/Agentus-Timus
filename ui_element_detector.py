import logging
import asyncio
from typing import Union, Optional
from PIL import Image
import torch
from segment_anything import SamPredictor, sam_model_registry
from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool

log = logging.getLogger(__name__)

class UIElementDetector:
    def __init__(self, sam_checkpoint, clip_model_name):
        self.sam = sam_model_registry["vit_b"](checkpoints=sam_checkpoint)
        self.predictor = SamPredictor(self.sam)
        self.clip_model = torch.hub.load("openai/clip", clip_model_name).eval()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.clip_model.to(self.device)

    def _get_bbox(self, mask):
        y, x = torch.where(mask)
        x_min, x_max = x.min().item(), x.max().item()
        y_min, y_max = y.min().item(), y.max().item()
        return [x_min, y_min, x_max - x_min, y_max - y_min]

    def _classify_element(self, mask):
        return "button"

@method
async def get_ui_elements_from_image(image_path: str) -> Union[Success, Error]:
    """
    Extrahiert UI-Elemente aus einem Bild.
    """
    log.info(f"Extrahiere UI-Elemente aus Bild: {image_path}")
    try:
        detector = UIElementDetector(sam_checkpoint="path/to/checkpoint", clip_model_name="ViT-B/32")
        image = Image.open(image_path).convert("RGB")
        detector.predictor.set_image(image)
        masks, scores = await asyncio.to_thread(detector.predictor.predict_with_point_coords,
                                                point_coords=None,
                                                point_labels=None,
                                                box=None,
                                                mask_input=None,
                                                multimask_output=False)
        ui_elements = []
        for mask, score in zip(masks, scores):
            bbox = detector._get_bbox(mask)
            element_type = detector._classify_element(mask)
            ui_elements.append({'type': element_type, 'bbox': bbox, 'confidence': score})
        return Success({"ui_elements": ui_elements})
    except Exception as e:
        log.error(f"Fehler beim Extrahieren von UI-Elementen: {e}", exc_info=True)
        return Error(code=-32033, message=f"Extraktion von UI-Elementen fehlgeschlagen: {e}")

register_tool("get_ui_elements_from_image", get_ui_elements_from_image)

log.info("✅ UI Element Detector Tool (get_ui_elements_from_image) registriert.")

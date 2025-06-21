from PIL import Image
import torch
from transformers import SamModel, SamProcessor, CLIPModel, CLIPProcessor

class SegmentationEngine:
    __instance = None

    @staticmethod
    def get_instance():
        """ Static access method. """
        if SegmentationEngine.__instance is None:
            SegmentationEngine()
        return SegmentationEngine.__instance

    def __init__(self):
        """ Virtually private constructor. """
        if SegmentationEngine.__instance is not None:
            raise Exception("This class is a singleton!")
        else:
            SegmentationEngine.__instance = self
            self.sam_model = SamModel.from_pretrained("facebook/sam-vit-base")
            self.sam_processor = SamProcessor.from_pretrained("facebook/sam-vit-base")
            self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.sam_model.to(self.device)
            self.clip_model.to(self.device)


    def get_ui_elements_from_image(self, image: Image.Image):
        """
        Segmentiert ein Bild mit SAM, klassifiziert die Segmente mit CLIP und gibt eine Liste von UI-Elementen zurück.
        """

        inputs = self.sam_processor(image, return_tensors="pt").to(self.device)
        sam_outputs = self.sam_model(**inputs)

        # Hier müsste die Logik für die Auswahl der Masken und die Bounding Box Berechnung implementiert werden.
        # Placeholder für die Bounding Boxes
        bboxes = [[0, 0, 100, 50], [150, 80, 75, 60]]

        ui_elements = []
        for bbox in bboxes:
            cropped_image = image.crop(bbox)
            clip_inputs = self.clip_processor(text=["button", "input field", "image"], images=cropped_image, return_tensors="pt", padding=True).to(self.device)
            clip_outputs = self.clip_model(**clip_inputs)
            logits_per_image = clip_outputs.logits_per_image  # this is the image-text similarity score
            probs = logits_per_image.softmax(dim=1)
            predicted_class_idx = probs.argmax(dim=1).item()
            predicted_class = self.clip_processor.tokenizer.decode([predicted_class_idx])

            ui_elements.append({'type': predicted_class, 'bbox': bbox})

        return ui_elements

from PIL import Image
import numpy as np

def read_image(image_path: str) -> np.ndarray:
    """Liest ein Bild von image_path ein und gibt es als NumPy-Array zurück."""
    with Image.open(image_path) as img:
        return np.array(img)
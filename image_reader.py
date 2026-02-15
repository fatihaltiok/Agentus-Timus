import os
from PIL import Image
from typing import Union

def load_image(file_path: Union[str, os.PathLike]) -> Image.Image:
    """
    Load an image from the given file path using Pillow.

    Parameters
    ----------
    file_path : str or os.PathLike
        Path to the image file to be loaded.

    Returns
    -------
    PIL.Image.Image
        The loaded image object.

    Raises
    ------
    FileNotFoundError
        If the specified file does not exist.
    OSError
        If the file cannot be opened as an image.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Image file not found: {file_path}")

    try:
        img = Image.open(file_path)
        # Ensure the image is fully loaded before the file is closed
        img.load()
        return img
    except OSError as e:
        raise OSError(f"Failed to load image '{file_path}': {e}") from e
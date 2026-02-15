import os
from typing import Union, Optional

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None


def load_image(
    path: str,
    *,
    as_numpy: bool = False,
    grayscale: bool = False,
    resize: Optional[tuple[int, int]] = None,
) -> Union["Image.Image", "np.ndarray"]:
    """
    Lädt ein Bild von der angegebenen Dateipfade.

    Parameters
    ----------
    path : str
        Pfad zur Bilddatei (z. B. PNG, JPG, BMP).
    as_numpy : bool, optional
        Wenn True, wird das Bild als NumPy-Array zurückgegeben.
        Standardmäßig False, sodass ein PIL.Image-Objekt zurückgegeben wird.
    grayscale : bool, optional
        Wenn True, wird das Bild in Graustufen konvertiert.
    resize : tuple[int, int] | None, optional
        Optionaler Zielgrößen-Tupel (Breite, Höhe). Falls angegeben, wird das Bild
        vor dem Rückgabewert skaliert.

    Returns
    -------
    Image.Image | np.ndarray
        Das geladene Bild entweder als PIL.Image-Objekt oder als NumPy-Array.

    Raises
    ------
    FileNotFoundError
        Wenn die angegebene Datei nicht existiert.
    ValueError
        Wenn weder Pillow noch OpenCV installiert sind.
    OSError
        Bei Problemen beim Laden der Bilddatei.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Die Datei '{path}' existiert nicht.")

    # Versuche zuerst Pillow zu verwenden
    if Image is not None:
        try:
            img = Image.open(path)
            if grayscale:
                img = img.convert("L")
            if resize:
                img = img.resize(resize, Image.ANTIALIAS)
            return img
        except OSError as e:
            # Pillow konnte das Bild nicht laden; versuche OpenCV
            pass

    # Fallback: OpenCV
    if cv2 is not None:
        try:
            flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
            img = cv2.imread(path, flag)
            if img is None:
                raise OSError(f"OpenCV konnte die Datei '{path}' nicht lesen.")
            if resize:
                img = cv2.resize(img, resize, interpolation=cv2.INTER_AREA)
            if as_numpy:
                return img
            else:
                # Konvertiere BGR (OpenCV) zu RGB (Pillow)
                if not grayscale:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                return Image.fromarray(img)
        except OSError as e:
            raise OSError(f"Fehler beim Laden der Bilddatei mit OpenCV: {e}") from e

    raise ValueError("Weder Pillow noch OpenCV sind installiert. Bitte installieren Sie mindestens eine dieser Bibliotheken.")


def load_image_from_bytes(
    image_bytes: bytes,
    *,
    as_numpy: bool = False,
    grayscale: bool = False,
    resize: Optional[tuple[int, int]] = None,
) -> Union["Image.Image", "np.ndarray"]:
    """
    Lädt ein Bild aus einem Bytes-Objekt (z. B. aus HTTP-Antwort).

    Parameters
    ----------
    image_bytes : bytes
        Binäre Daten des Bildes.
    as_numpy : bool, optional
        Wenn True, wird das Bild als NumPy-Array zurückgegeben.
    grayscale : bool, optional
        Wenn True, wird das Bild in Graustufen konvertiert.
    resize : tuple[int, int] | None, optional
        Optionaler Zielgrößen-Tupel (Breite, Höhe). Falls angegeben, wird das Bild
        vor dem Rückgabewert skaliert.

    Returns
    -------
    Image.Image | np.ndarray
        Das geladene Bild entweder als PIL.Image-Objekt oder als NumPy-Array.

    Raises
    ------
    ValueError
        Wenn die Bildbytes nicht dekodiert werden können.
    """
    if Image is not None:
        try:
            from io import BytesIO

            img = Image.open(BytesIO(image_bytes))
            if grayscale:
                img = img.convert("L")
            if resize:
                img = img.resize(resize, Image.ANTIALIAS)
            return img if not as_numpy else np.array(img)
        except Exception as e:
            pass

    if cv2 is not None:
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
            img = cv2.imdecode(nparr, flag)
            if img is None:
                raise ValueError("OpenCV konnte das Bild aus Bytes nicht dekodieren.")
            if resize:
                img = cv2.resize(img, resize, interpolation=cv2.INTER_AREA)
            if as_numpy:
                return img
            else:
                if not grayscale:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                return Image.fromarray(img)
        except Exception as e:
            raise ValueError(f"Fehler beim Dekodieren der Bildbytes mit OpenCV: {e}") from e

    raise ValueError("Weder Pillow noch OpenCV sind installiert. Bitte installieren Sie mindestens eine dieser Bibliotheken.")


if __name__ == "__main__":
    # Beispieltests für die Loader-Funktionen
    import sys

    def _test_load_image():
        test_path = "sample.jpg"
        if not os.path.isfile(test_path):
            print(f"Testbild '{test_path}' nicht gefunden. Bitte legen Sie ein Bild mit diesem Namen im Arbeitsverzeichnis an.")
            sys.exit(1)

        print("Lade Bild mit Pillow (oder OpenCV als Fallback)...")
        try:
            img = load_image(test_path, grayscale=False, resize=(256, 256))
            print(f"Geladenes Bild: {img}")
            print(f"Bildgröße: {img.size if isinstance(img, Image.Image) else img.shape}")
        except Exception as e:
            print(f"Fehler beim Laden des Bildes: {e}")

    def _test_load_image_from_bytes():
        test_path = "sample.jpg"
        with open(test_path, "rb") as f:
            data = f.read()
        print("Lade Bild aus Bytes...")
        try:
            img = load_image_from_bytes(data, grayscale=True, resize=(128, 128))
            print(f"Geladenes Bild aus Bytes: {img}")
            print(f"Bildgröße: {img.size if isinstance(img, Image.Image) else img.shape}")
        except Exception as e:
            print(f"Fehler beim Laden des Bildes aus Bytes: {e}")

    _test_load_image()
    _test_load_image_from_bytes()
    print("Tests abgeschlossen.")
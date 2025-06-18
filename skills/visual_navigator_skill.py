import cv2
import pyautogui
import numpy as np

def click_element_on_screen(element_description: str):
    # Lade das Bild des zu findenden Elements
    template = cv2.imread(element_description, cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise ValueError(f"Bild {element_description} konnte nicht geladen werden.")

    # Screenshot des Bildschirms
    screenshot = pyautogui.screenshot()
    screen = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)

    # Template Matching
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    # Definiere einen Schwellenwert für die Erkennung
    threshold = 0.8
    if max_val >= threshold:
        # Finde die Position des besten Matches
        top_left = max_loc
        h, w = template.shape
        center_x = top_left[0] + w // 2
        center_y = top_left[1] + h // 2

        # Klicke auf die Mitte des erkannten Elements
        pyautogui.click(center_x, center_y)
    else:
        raise ValueError("Element konnte nicht auf dem Bildschirm gefunden werden.")

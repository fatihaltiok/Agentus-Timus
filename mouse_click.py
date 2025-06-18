import pyautogui

def click_at_coordinates(x: int, y: int):
    """Führt einen Mausklick an den angegebenen Koordinaten aus."""
    pyautogui.click(x, y)

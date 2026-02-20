#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
visual_nemotronv4_web_interaction_skill.py

A reusable skill for automating web interactions using a 5‑phase workflow:
1. Initialization (open URL, close overlays/consent)
2. Screen capture & OCR
3. UI element detection & localization
4. Perform actions (click, type, scroll) with retry logic
5. Verify result & cleanup

The module provides modular, well‑documented functions that can be imported
and reused in other projects. It uses Selenium for browser automation,
OpenCV for template matching, and pytesseract for OCR. Logging is
configured to aid debugging.

Author: Inception
"""

import logging
import time
from typing import List, Tuple, Callable, Dict, Any, Optional

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import cv2
import numpy as np
import pytesseract

# ----------------------------------------------------------------------
# Logging configuration
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def _wait_for_page_load(driver: webdriver.Chrome, timeout: int = 30) -> None:
    """Wait until the document readyState is 'complete'."""
    logger.debug("Waiting for page to load fully.")
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        logger.warning("Page load timed out after %s seconds.", timeout)

def _close_overlays(driver: webdriver.Chrome) -> None:
    """Attempt to close common overlay elements such as cookie consent or pop‑ups."""
    logger.debug("Attempting to close overlays/consent dialogs.")
    overlay_selectors = [
        (By.CSS_SELECTOR, "button[aria-label='Accept all']"),
        (By.CSS_SELECTOR, "button[title='Close']"),
        (By.CSS_SELECTOR, ".consent-button"),
        (By.XPATH, "//button[contains(text(),'Accept')]"),
    ]
    for by, value in overlay_selectors:
        try:
            elem = driver.find_element(by, value)
            elem.click()
            logger.info("Closed overlay using selector: %s", value)
            time.sleep(0.5)  # small pause after click
        except NoSuchElementException:
            continue
        except Exception as exc:
            logger.exception("Unexpected error while closing overlay: %s", exc)

# ----------------------------------------------------------------------
# Phase 1: Initialization
# ----------------------------------------------------------------------
def initialize_browser(
    url: str,
    timeout: int = 30,
    headless: bool = False,
    **kwargs,
) -> webdriver.Chrome:
    """
    Launch a Selenium Chrome browser, navigate to the given URL, and perform
    initial cleanup (close overlays/consent dialogs).

    Parameters
    ----------
    url : str
        Target URL to open.
    timeout : int, optional
        Maximum time to wait for page load.
    headless : bool, optional
        Run Chrome in headless mode.
    **kwargs
        Additional arguments passed to ``webdriver.Chrome`` (e.g., service, options).

    Returns
    -------
    webdriver.Chrome
        Configured Selenium WebDriver instance.

    Raises
    ------
    WebDriverException
        If the browser cannot be started or the page fails to load.
    """
    logger.info("Initializing browser for URL: %s", url)
    chrome_options = ChromeOptions()
    if headless:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options, **kwargs)
    driver.set_page_load_timeout(timeout)
    try:
        driver.get(url)
        _wait_for_page_load(driver, timeout)
        _close_overlays(driver)
        logger.info("Browser initialized and ready.")
        return driver
    except Exception as exc:
        driver.quit()
        logger.exception("Failed to initialize browser: %s", exc)
        raise WebDriverException(f"Initialization failed: {exc}")

# ----------------------------------------------------------------------
# Phase 2: Screen capture & OCR
# ----------------------------------------------------------------------
def capture_screen_and_ocr(
    driver: webdriver.Chrome,
    lang: str = "eng",
    ocr_config: str = "--psm 6",
) -> Tuple[np.ndarray, str]:
    """
    Capture a screenshot of the current page and run OCR on it.

    Parameters
    ----------
    driver : webdriver.Chrome
        Selenium WebDriver instance.
    lang : str, optional
        Language(s) to use for OCR.
    ocr_config : str, optional
        Tesseract configuration string.

    Returns
    -------
    Tuple[np.ndarray, str]
        The screenshot as a NumPy array (BGR) and the extracted text.
    """
    logger.debug("Capturing screenshot for OCR.")
    try:
        png = driver.get_screenshot_as_png()
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        text = pytesseract.image_to_string(image, lang=lang, config=ocr_config)
        logger.info("OCR completed; extracted %d characters.", len(text))
        return image, text
    except Exception as exc:
        logger.exception("OCR failed: %s", exc)
        raise

# ----------------------------------------------------------------------
# Phase 3: UI element detection & localization
# ----------------------------------------------------------------------
def locate_ui_elements(
    driver: webdriver.Chrome,
    templates: List[Tuple[str, str]],
    threshold: float = 0.8,
    max_attempts: int = 3,
    wait_interval: int = 2,
) -> List[Dict[str, Any]]:
    """
    Locate UI elements on the page by template matching.

    Parameters
    ----------
    driver : webdriver.Chrome
        Selenium WebDriver instance.
    templates : List[Tuple[str, str]]
        List of tuples (element_name, image_path) for template images.
    threshold : float, optional
        Matching threshold (0‑1). Default 0.8.
    max_attempts : int, optional
        Number of attempts to locate each template.
    wait_interval : int, optional
        Seconds to wait between attempts.

    Returns
    -------
    List[Dict[str, Any]]
        List of dictionaries with keys: 'name', 'bbox' (x, y, w, h), 'center' (x, y).
    """
    logger.info("Locating UI elements via template matching.")
    results = []
    # Capture current page screenshot
    screenshot, _ = capture_screen_and_ocr(driver)
    gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

    for name, img_path in templates:
        logger.debug("Processing template: %s", name)
        template = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            logger.warning("Template image not found or unreadable: %s", img_path)
            continue
        w, h = template.shape[::-1]

        attempts = 0
        while attempts < max_attempts:
            attempts += 1
            res = cv2.matchTemplate(gray_screenshot, template, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= threshold)
            if len(loc[0]) > 0:
                # Take the first match
                y, x = loc[0][0], loc[1][0]
                bbox = (x, y, w, h)
                center = (x + w // 2, y + h // 2)
                results.append({"name": name, "bbox": bbox, "center": center})
                logger.info("Found element '%s' at %s.", name, bbox)
                break
            else:
                logger.debug("Element '%s' not found on attempt %d/%d.", name, attempts, max_attempts)
                time.sleep(wait_interval)
        else:
            logger.warning("Failed to locate element '%s' after %d attempts.", name, max_attempts)
    return results

# ----------------------------------------------------------------------
# Phase 4: Perform actions with retry logic
# ----------------------------------------------------------------------
def perform_actions(
    driver: webdriver.Chrome,
    actions: List[Dict[str, Any]],
    retries: int = 2,
    retry_interval: int = 1,
    timeout: int = 10,
) -> None:
    """
    Execute a sequence of actions (click, type, scroll) on the page.

    Parameters
    ----------
    driver : webdriver.Chrome
        Selenium WebDriver instance.
    actions : List[Dict[str, Any]]
        Each dict must contain:
            - 'type': 'click' | 'type' | 'scroll'
            - 'target': For 'click'/'type', a dict with 'by' and 'value' (e.g., {'by': 'xpath', 'value': '//button'}).
            - 'text': For 'type' actions, the string to type.
            - 'scroll_to': For 'scroll' actions, a tuple (x, y) coordinates.
    retries : int, optional
        Number of retry attempts per action.
    retry_interval : int, optional
        Seconds to wait between retries.
    timeout : int, optional
        Maximum time to wait for element presence.

    Raises
    ------
    Exception
        If an action fails after all retries.
    """
    logger.info("Performing actions with retry logic.")
    for idx, action in enumerate(actions, start=1):
        action_type = action.get("type")
        logger.debug("Executing action %d: %s", idx, action_type)
        attempt = 0
        while attempt <= retries:
            attempt += 1
            try:
                if action_type == "click":
                    target = action["target"]
                    elem = WebDriverWait(driver, timeout).until(
                        EC.element_to_be_clickable((target["by"], target["value"]))
                    )
                    elem.click()
                    logger.info("Clicked element %d.", idx)
                elif action_type == "type":
                    target = action["target"]
                    text = action["text"]
                    elem = WebDriverWait(driver, timeout).until(
                        EC.element_to_be_clickable((target["by"], target["value"]))
                    )
                    elem.clear()
                    elem.send_keys(text)
                    logger.info("Typed into element %d.", idx)
                elif action_type == "scroll":
                    x, y = action["scroll_to"]
                    driver.execute_script(f"window.scrollTo({x}, {y});")
                    logger.info("Scrolled to (%d, %d).", x, y)
                else:
                    raise ValueError(f"Unsupported action type: {action_type}")
                # If we reach here, action succeeded
                break
            except (NoSuchElementException, TimeoutException,
                    ElementClickInterceptedException,
                    ElementNotInteractableException) as exc:
                logger.warning("Attempt %d/%d failed for action %d: %s", attempt, retries + 1, idx, exc)
                if attempt > retries:
                    logger.error("Action %d failed after %d attempts.", idx, retries + 1)
                    raise Exception(f"Action '{action_type}' failed: {exc}") from exc
                time.sleep(retry_interval)
            except Exception as exc:
                logger.exception("Unexpected error during action %d: %s", idx, exc)
                raise

# ----------------------------------------------------------------------
# Phase 5: Verify result & cleanup
# ----------------------------------------------------------------------
def verify_result(
    driver: webdriver.Chrome,
    verification_func: Callable[[webdriver.Chrome], bool],
    timeout: int = 10,
) -> bool:
    """
    Verify the outcome of the performed actions using a user‑provided
    verification function.

    Parameters
    ----------
    driver : webdriver.Chrome
        Selenium WebDriver instance.
    verification_func : Callable[[webdriver.Chrome], bool]
        Function that takes the driver and returns True if verification passes.
    timeout : int, optional
        Maximum time to wait for verification.

    Returns
    -------
    bool
        True if verification succeeds, False otherwise.
    """
    logger.info("Verifying result.")
    start = time.time()
    while time.time() - start < timeout:
        try:
            if verification_func(driver):
                logger.info("Verification succeeded.")
                return True
            else:
                logger.debug("Verification function returned False; retrying.")
        except Exception as exc:
            logger.debug("Verification function raised exception: %s", exc)
        time.sleep(1)
    logger.warning("Verification timed out after %s seconds.", timeout)
    return False

def cleanup(driver: webdriver.Chrome) -> None:
    """
    Close the browser and clean up resources.

    Parameters
    ----------
    driver : webdriver.Chrome
        Selenium WebDriver instance.
    """
    logger.info("Cleaning up: closing browser.")
    try:
        driver.quit()
        logger.info("Browser closed successfully.")
    except Exception as exc:
        logger.exception("Error while closing browser: %s", exc)

# ----------------------------------------------------------------------
# Example usage (test stub)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Example configuration
    test_url = "https://example.com"
    test_templates = [
        ("example_button", "templates/example_button.png"),
    ]

    # Define actions
    test_actions = [
        {
            "type": "click",
            "target": {"by": By.XPATH, "value": "//button[text()='More information']"},
        },
        {
            "type": "scroll",
            "scroll_to": (0, 500),
        },
    ]

    # Define a simple verification function
    def verify_example(driver: webdriver.Chrome) -> bool:
        try:
            elem = driver.find_element(By.CSS_SELECTOR, "h1")
            return "Example Domain" in elem.text
        except NoSuchElementException:
            return False

    # Run the workflow
    driver = None
    try:
        driver = initialize_browser(test_url, headless=False, timeout=20)
        # Locate UI elements (not used in this simple test)
        locate_ui_elements(driver, test_templates, threshold=0.9)
        # Perform actions
        perform_actions(driver, test_actions, retries=2, retry_interval=1, timeout=15)
        # Verify result
        result = verify_result(driver, verify_example, timeout=10)
        logger.info("Verification result: %s", result)
    finally:
        if driver:
            cleanup(driver)
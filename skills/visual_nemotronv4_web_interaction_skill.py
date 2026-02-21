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
import os
import sys
import time
from pathlib import Path
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
LOG_DIR = Path("skills/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "visual_nemotronv4_errors.log"

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Console handler for general info
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
console_handler.setFormatter(console_formatter)

# File handler for detailed error logs
file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler.setFormatter(file_formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

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
# Configuration parsing
# ----------------------------------------------------------------------
def get_config(
    url: Any,
    timeout: Any = 30,
    retries: Any = 2,
) -> Dict[str, Any]:
    """
    Validate and normalize configuration parameters for the skill.

    Parameters
    ----------
    url : Any
        Target URL to open.
    timeout : Any, optional
        Maximum time to wait for page load and element presence.
    retries : Any, optional
        Number of retry attempts for actions.

    Returns
    -------
    dict
        Normalized configuration with keys 'url', 'timeout', 'retries'.

    Raises
    ------
    ValueError
        If any parameter is of an invalid type or value.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non‑empty string.")
    if not isinstance(timeout, int) or timeout <= 0:
        raise ValueError("timeout must be a positive integer.")
    if not isinstance(retries, int) or retries < 0:
        raise ValueError("retries must be a non‑negative integer.")
    config = {"url": url.strip(), "timeout": timeout, "retries": retries}
    logger.debug("Configuration validated: %s", config)
    return config

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
# Dry‑run simulation
# ----------------------------------------------------------------------
def dry_run(url: str, simulate_ui: bool = True) -> Dict[str, Any]:
    """
    Simulate a full workflow without launching a real browser. Useful
    for unit testing and CI pipelines where a browser may not be
    available.

    Parameters
    ----------
    url : str
        The URL to simulate. If it equals 'about:blank' a deterministic
        simulation is performed.
    simulate_ui : bool, optional
        If True, simulate UI element detection and OCR; otherwise skip
        those steps.

    Returns
    -------
    dict
        A dictionary containing simulated results:
            - 'url': the input URL
            - 'screenshot': a dummy NumPy array
            - 'ocr_text': deterministic string
            - 'ui_elements': list of dummy UI elements
            - 'actions_performed': list of simulated actions

    Raises
    ------
    ValueError
        If url is not a string.
    """
    if not isinstance(url, str):
        raise ValueError("url must be a string.")
    logger.info("Starting dry run simulation for URL: %s", url)

    # Simulated screenshot (blank image)
    screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)

    # Simulated OCR text
    ocr_text = "Simulated OCR output for URL: " + url

    # Simulated UI elements
    ui_elements = []
    if simulate_ui:
        ui_elements = [
            {"name": "dummy_button", "bbox": (100, 200, 150, 50), "center": (175, 225)},
            {"name": "dummy_input", "bbox": (300, 400, 200, 40), "center": (400, 420)},
        ]
        logger.debug("Simulated UI elements: %s", ui_elements)

    # Simulated actions
    actions_performed = [
        {"type": "click", "target": {"by": By.XPATH, "value": "//button[@id='dummy']"}},
        {"type": "type", "target": {"by": By.CSS_SELECTOR, "value": "#dummy_input"}, "text": "test"},
        {"type": "scroll", "scroll_to": (0, 500)},
    ]
    logger.debug("Simulated actions: %s", actions_performed)

    result = {
        "url": url,
        "screenshot": screenshot,
        "ocr_text": ocr_text,
        "ui_elements": ui_elements,
        "actions_performed": actions_performed,
    }
    logger.info("Dry run simulation completed.")
    return result

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
            "target": {"by": By.XPATH, "value": "//button[text()='More information']
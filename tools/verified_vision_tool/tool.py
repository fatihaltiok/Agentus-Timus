"""
Verified Vision Tool - Zuverlässige Screenshot-Analyse durch Multi-Layer Verifikation.

Kombiniert:
1. Qwen-VL (schnelle visuelle Extraktion)
2. OCR (Text-Verifikation auf dem Screen)
3. Text-LLM (Plausibilitätsprüfung & Reasoning)

Features:
- Retry-Logik mit exponentiellem Backoff
- Multi-Backend OCR (Tesseract, Paddle, EasyOCR)
- Confidence-Scoring
- Fallback-Kaskade
- Strukturierte JSON-Ausgabe

Version: 1.0
"""

import asyncio
import base64
import io
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

import httpx
import mss
from PIL import Image
from dotenv import load_dotenv
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

from utils.openai_compat import prepare_openai_params

# Versuche OCR-Backends zu importieren
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
    # Lazy initialization - erst bei Bedarf
    _paddle_ocr = None
except ImportError:
    PADDLE_AVAILABLE = False

# Setup
load_dotenv()
logger = logging.getLogger("verified_vision_tool")

# Konfiguration
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))

# Qwen-VL Engine fuer Layer 1 (ersetzt Moondream)
try:
    from tools.engines.qwen_vl_engine import qwen_vl_engine_instance
    QWEN_VL_AVAILABLE = True
except ImportError:
    QWEN_VL_AVAILABLE = False

# LLM Client für Verifikation (lazy initialization)
from openai import OpenAI
_LLM_CLIENT = None

def get_llm_client():
    """Lazy initialization des LLM Clients."""
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        if VERIFICATION_MODEL.startswith("deepseek"):
            _LLM_CLIENT = OpenAI(
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
            )
        else:
            _LLM_CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _LLM_CLIENT

VERIFICATION_MODEL = os.getenv("VERIFICATION_MODEL", "gpt-4.1-nano")


@dataclass
class VerifiedElement:
    """Ein verifiziertes UI-Element mit Multi-Source Daten."""
    element_type: str
    label: str
    position: Dict[str, float]  # {x, y, width, height} normalized 0-1
    confidence: float
    sources: List[str] = field(default_factory=list)  # ['moondream', 'ocr', 'llm']
    verified: bool = False
    ocr_text: str = ""
    reasoning: str = ""


class VerifiedVisionEngine:
    """
    Engine für verifizierte visuelle Analyse.

    Layer 1: Qwen-VL (schnelle Extraktion)
    Layer 2: OCR (Text-Verifikation)
    Layer 3: LLM (Plausibilitätsprüfung)
    """

    def __init__(self):
        self.elements: List[VerifiedElement] = []
        self.raw_screenshot: Optional[Image.Image] = None
        self.screen_width: int = 1920
        self.screen_height: int = 1080
        self.monitor_offset_x: int = 0
        self.monitor_offset_y: int = 0

    def _capture_screenshot(self) -> Image.Image:
        """Macht Screenshot mit Monitor-Info."""
        with mss.mss() as sct:
            if ACTIVE_MONITOR < len(sct.monitors):
                monitor = sct.monitors[ACTIVE_MONITOR]
            else:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

            self.screen_width = monitor["width"]
            self.screen_height = monitor["height"]
            self.monitor_offset_x = monitor["left"]
            self.monitor_offset_y = monitor["top"]

            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            self.raw_screenshot = img
            return img

    def _image_to_base64(self, img: Image.Image, max_size: Tuple[int, int] = (800, 600)) -> str:
        """Konvertiert PIL Image zu Base64 Data URL."""
        img_copy = img.copy()
        if max_size:
            img_copy.thumbnail(max_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img_copy.save(buffer, format="JPEG", quality=85)
        b64 = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/jpeg;base64,{b64}"

    async def _call_vision_model(
        self,
        image: Image.Image,
        question: str,
        max_retries: int = 2
    ) -> Optional[Dict]:
        """Ruft Qwen-VL Engine fuer visuelle Analyse auf."""
        if not QWEN_VL_AVAILABLE or not qwen_vl_engine_instance.is_initialized():
            logger.warning("Qwen-VL nicht verfuegbar fuer Vision-Analyse")
            return None

        for attempt in range(max_retries):
            try:
                answer = await asyncio.to_thread(
                    qwen_vl_engine_instance.analyze_screenshot, image, question
                )
                if answer:
                    return {"answer": answer}
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.0)
            except Exception as e:
                logger.error(f"Qwen-VL error (attempt {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.0)

        return None

    async def _run_ocr(self, img: Image.Image, region: Optional[Tuple[int, int, int, int]] = None) -> str:
        """Führt OCR auf Bild oder Region aus."""
        if region:
            x, y, w, h = region
            img = img.crop((x, y, x + w, y + h))

        ocr_results = []

        # Versuche Tesseract
        if TESSERACT_AVAILABLE:
            try:
                text = pytesseract.image_to_string(img)
                if text.strip():
                    ocr_results.append(("tesseract", text.strip()))
            except Exception as e:
                logger.debug(f"Tesseract failed: {e}")

        # Versuche PaddleOCR (langsamer aber genauer)
        if PADDLE_AVAILABLE:
            try:
                global _paddle_ocr
                if _paddle_ocr is None:
                    _paddle_ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)

                # PIL zu numpy array
                import numpy as np
                img_array = np.array(img)
                result = _paddle_ocr.ocr(img_array, cls=True)

                if result and result[0]:
                    texts = [line[1][0] for line in result[0]]
                    ocr_results.append(("paddle", " ".join(texts)))
            except Exception as e:
                logger.debug(f"PaddleOCR failed: {e}")

        # Kombiniere Ergebnisse oder nimm bestes
        if ocr_results:
            # Nimm das längste Ergebnis (meistens das beste)
            best = max(ocr_results, key=lambda x: len(x[1]))
            return best[1]

        return ""

    async def _verify_with_llm(
        self,
        moondream_elements: List[Dict],
        ocr_text: str,
        screenshot_desc: str
    ) -> List[VerifiedElement]:
        """Verifiziert Moondream-Ergebnisse mit Text-LLM."""

        prompt = f"""You are a UI verification expert. Analyze the following data and verify the detected UI elements.

SCREENSHOT DESCRIPTION:
{screenshot_desc}

OCR TEXT FOUND ON SCREEN:
{ocr_text}

MOONDREAM DETECTED ELEMENTS:
{json.dumps(moondream_elements, indent=2)}

TASK:
1. Verify each detected element - is it plausible given the OCR text and screenshot?
2. Check if positions make sense (x,y between 0-1)
3. Identify any missing obvious elements (submit buttons, main navigation)
4. Rate confidence for each element (0.0-1.0)

Respond with ONLY a JSON array in this format:
[
  {{
    "element_type": "button",
    "label": "Submit",
    "position": {{"x": 0.5, "y": 0.8, "width": 0.1, "height": 0.05}},
    "confidence": 0.95,
    "verified": true,
    "reasoning": "Button text 'Submit' clearly visible in OCR at bottom center"
  }}
]

Rules:
- verified = true only if element is clearly confirmed by OCR or visual description
- Reduce confidence if position seems wrong (e.g., all at 0.5, 0.8)
- Add missing elements if they're obvious in OCR but not in Moondream list"""

        try:
            api_params = prepare_openai_params({
                "model": VERIFICATION_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a precise UI verification system. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 2000
            })

            response = await asyncio.to_thread(
                get_llm_client().chat.completions.create,
                **api_params
            )

            content = response.choices[0].message.content.strip()

            # Extrahiere JSON aus möglichem Markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            verified_data = json.loads(content)

            verified_elements = []
            for elem in verified_data:
                ve = VerifiedElement(
                    element_type=elem.get("element_type", "unknown"),
                    label=elem.get("label", ""),
                    position=elem.get("position", {"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.1}),
                    confidence=elem.get("confidence", 0.5),
                    verified=elem.get("verified", False),
                    reasoning=elem.get("reasoning", ""),
                    sources=["moondream", "ocr", "llm"] if elem.get("verified") else ["moondream", "llm"]
                )
                verified_elements.append(ve)

            return verified_elements

        except Exception as exc:
            logger.error(f"LLM verification failed: {exc}")
            # Fallback: Konvertiere Moondream-Ergebnisse ohne Verifikation
            return [
                VerifiedElement(
                    element_type=elem.get("type", "unknown"),
                    label=elem.get("label", ""),
                    position=elem.get("position", {"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.1}),
                    confidence=elem.get("confidence", 0.5),
                    verified=False,
                    sources=["moondream"],
                    reasoning="Raw Moondream result (LLM verification failed)"
                )
                for elem in moondream_elements
            ]

    async def analyze_screen(
        self,
        target_elements: Optional[List[str]] = None,
        verify_with_ocr: bool = True,
        verify_with_llm: bool = True
    ) -> List[VerifiedElement]:
        """Hauptmethode für verifizierte Screen-Analyse."""
        self.elements = []

        # Layer 1: Screenshot + Qwen-VL
        logger.info("Layer 1: Capturing screenshot...")
        screenshot = self._capture_screenshot()
        image_url = self._image_to_base64(screenshot, max_size=(800, 600))

        search_types = target_elements or ["buttons", "input fields", "links", "text fields"]

        logger.info(f"Layer 1: Qwen-VL analyzing for {search_types}...")
        question = (
            f"Analyze this UI screenshot. Identify all {', '.join(search_types)}. "
            f"Return a JSON array with: type, label (visible text), position (x,y as normalized 0-1 center), "
            f"and estimated confidence (0-1). Format: [{{type: 'button', label: 'Submit', position: {{x: 0.5, y: 0.8}}, confidence: 0.9}}]"
        )
        vision_result = await self._call_vision_model(screenshot, question)

        if not vision_result:
            logger.error("Vision analysis failed completely (Qwen-VL)")
            return []

        moondream_answer = vision_result.get("answer", "")

        # Parse Moondream JSON
        moondream_elements = []
        try:
            if "```json" in moondream_answer:
                json_str = moondream_answer.split("```json")[1].split("```")[0].strip()
            elif "```" in moondream_answer:
                json_str = moondream_answer.split("```")[1].split("```")[0].strip()
            elif moondream_answer.strip().startswith("["):
                json_str = moondream_answer.strip()
            else:
                json_str = moondream_answer

            moondream_elements = json.loads(json_str)
            if not isinstance(moondream_elements, list):
                moondream_elements = [moondream_elements]
        except json.JSONDecodeError:
            logger.warning("Moondream returned non-JSON, attempting to parse...")
            moondream_elements = [{
                "type": "unknown",
                "label": moondream_answer[:100],
                "position": {"x": 0.5, "y": 0.5},
                "confidence": 0.3
            }]

        logger.info(f"Layer 1: Moondream found {len(moondream_elements)} elements")

        # Layer 2: OCR Verifikation
        ocr_text = ""
        if verify_with_ocr:
            logger.info("Layer 2: Running OCR verification...")
            ocr_text = await self._run_ocr(screenshot)
            logger.info(f"Layer 2: OCR found text: {ocr_text[:200]}...")

        # Layer 3: LLM Verifikation
        if verify_with_llm:
            logger.info("Layer 3: LLM verification & plausibility check...")
            self.elements = await self._verify_with_llm(
                moondream_elements,
                ocr_text,
                moondream_answer
            )
            verified_count = sum(1 for e in self.elements if e.verified)
            logger.info(f"Layer 3: {verified_count}/{len(self.elements)} elements verified")
        else:
            self.elements = [
                VerifiedElement(
                    element_type=elem.get("type", "unknown"),
                    label=elem.get("label", ""),
                    position=elem.get("position", {"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.1}),
                    confidence=elem.get("confidence", 0.5),
                    verified=False,
                    sources=["moondream"],
                    reasoning="Raw Moondream result (verification disabled)"
                )
                for elem in moondream_elements
            ]

        return self.elements

    def get_elements_by_confidence(self, min_confidence: float = 0.7) -> List[VerifiedElement]:
        """Gibt Elemente mit mindestens angegebenem Confidence-Score."""
        return [e for e in self.elements if e.confidence >= min_confidence]

    def get_clickable_elements(self) -> List[VerifiedElement]:
        """Gibt verifizierte klickbare Elemente zurück."""
        clickable_types = ["button", "link", "submit", "input", "checkbox"]
        return [
            e for e in self.elements
            if e.verified and e.element_type.lower() in clickable_types
        ]

    def to_dict_list(self) -> List[Dict]:
        """Konvertiert zu Dict-Liste für JSON-RPC."""
        return [
            {
                "type": e.element_type,
                "label": e.label,
                "position": e.position,
                "confidence": e.confidence,
                "verified": e.verified,
                "sources": e.sources,
                "pixel_x": int(e.position["x"] * self.screen_width) + self.monitor_offset_x,
                "pixel_y": int(e.position["y"] * self.screen_height) + self.monitor_offset_y,
                "click_coordinates": {
                    "x": int(e.position["x"] * self.screen_width) + self.monitor_offset_x,
                    "y": int(e.position["y"] * self.screen_height) + self.monitor_offset_y
                },
                "reasoning": e.reasoning
            }
            for e in self.elements
        ]


# Globale Engine-Instanz
vision_engine = VerifiedVisionEngine()


# =============================================================================
# RPC METHODEN
# =============================================================================

@tool(
    name="analyze_screen_verified",
    description="Analysiert den Bildschirm mit verifizierter Multi-Layer Vision. Kombiniert Qwen-VL (schnell), OCR (genau), und LLM (reasoning).",
    parameters=[
        P("target_elements", "array", "Liste zu suchender Element-Typen", required=False, default=None),
        P("min_confidence", "number", "Mindest-Confidence für Ergebnisse (0.0-1.0)", required=False, default=0.7),
        P("verify_with_ocr", "boolean", "OCR-Verifikation aktivieren", required=False, default=True),
        P("verify_with_llm", "boolean", "LLM-Plausibilitätsprüfung aktivieren", required=False, default=True),
    ],
    capabilities=["vision", "verification"],
    category=C.VISION
)
async def analyze_screen_verified(
    target_elements: Optional[List[str]] = None,
    min_confidence: float = 0.7,
    verify_with_ocr: bool = True,
    verify_with_llm: bool = True
) -> dict:
    """Analysiert den Bildschirm mit verifizierter Multi-Layer Vision."""
    try:
        elements = await vision_engine.analyze_screen(
            target_elements=target_elements,
            verify_with_ocr=verify_with_ocr,
            verify_with_llm=verify_with_llm
        )

        if not elements:
            return {
                "verified_elements": [],
                "total": 0,
                "verified_count": 0,
                "ocr_text": "",
                "message": "No elements detected. Check if screen is visible and Qwen-VL is running."
            }

        filtered = [e for e in elements if e.confidence >= min_confidence]
        verified_count = sum(1 for e in filtered if e.verified)

        return {
            "verified_elements": vision_engine.to_dict_list(),
            "filtered_elements": [
                e for e in vision_engine.to_dict_list()
                if e["confidence"] >= min_confidence
            ],
            "total": len(elements),
            "filtered_count": len(filtered),
            "verified_count": verified_count,
            "high_confidence_elements": len([e for e in elements if e.confidence >= 0.8]),
            "screen_dimensions": {
                "width": vision_engine.screen_width,
                "height": vision_engine.screen_height
            },
            "message": f"{len(elements)} elements detected, {verified_count} verified, {len(filtered)} above confidence threshold {min_confidence}"
        }

    except Exception as e:
        logger.error(f"Error in analyze_screen_verified: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="find_element_verified",
    description="Sucht ein spezifisches Element mit verifizierter Vision.",
    parameters=[
        P("element_description", "string", "Beschreibung des gesuchten Elements (z.B. Submit button, Email input)"),
        P("min_confidence", "number", "Mindest-Confidence für Treffer", required=False, default=0.7),
    ],
    capabilities=["vision", "verification"],
    category=C.VISION
)
async def find_element_verified(
    element_description: str,
    min_confidence: float = 0.7
) -> dict:
    """Sucht ein spezifisches Element mit verifizierter Vision."""
    try:
        await vision_engine.analyze_screen(
            target_elements=["buttons", "input fields", "links", "icons"],
            verify_with_ocr=True,
            verify_with_llm=True
        )

        element_description_lower = element_description.lower()
        candidates = []

        for elem in vision_engine.elements:
            score = 0.0

            if elem.label.lower() in element_description_lower:
                score += 0.5
            if elem.element_type.lower() in element_description_lower:
                score += 0.3
            score += elem.confidence * 0.2
            if elem.verified:
                score += 0.2

            if score > 0.3:
                candidates.append((score, elem))

        if not candidates:
            return {
                "found": False,
                "element": None,
                "candidates": [],
                "message": f"No element matching '{element_description}' found"
            }

        candidates.sort(reverse=True, key=lambda x: x[0])
        best_score, best_elem = candidates[0]

        if best_elem.confidence < min_confidence:
            return {
                "found": True,
                "element": {
                    "type": best_elem.element_type,
                    "label": best_elem.label,
                    "position": best_elem.position,
                    "click_coordinates": {
                        "x": int(best_elem.position["x"] * vision_engine.screen_width) + vision_engine.monitor_offset_x,
                        "y": int(best_elem.position["y"] * vision_engine.screen_height) + vision_engine.monitor_offset_y
                    },
                    "confidence": best_elem.confidence,
                    "verified": best_elem.verified
                },
                "warning": f"Low confidence ({best_elem.confidence:.2f} < {min_confidence})",
                "alternatives": [
                    {"type": e.element_type, "label": e.label, "confidence": e.confidence}
                    for _, e in candidates[1:4]
                ]
            }

        return {
            "found": True,
            "element": {
                "type": best_elem.element_type,
                "label": best_elem.label,
                "position": best_elem.position,
                "click_coordinates": {
                    "x": int(best_elem.position["x"] * vision_engine.screen_width) + vision_engine.monitor_offset_x,
                    "y": int(best_elem.position["y"] * vision_engine.screen_height) + vision_engine.monitor_offset_y
                },
                "confidence": best_elem.confidence,
                "verified": best_elem.verified,
                "sources": best_elem.sources,
                "reasoning": best_elem.reasoning
            },
            "match_score": best_score,
            "alternatives": [
                {"type": e.element_type, "label": e.label, "confidence": e.confidence}
                for _, e in candidates[1:4]
            ] if len(candidates) > 1 else []
        }

    except Exception as e:
        logger.error(f"Error in find_element_verified: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="get_verified_click_coordinates",
    description="Gibt verifizierte Klick-Koordinaten für ein Element zurück. Kombination aus Type + optional Label.",
    parameters=[
        P("element_type", "string", "Element-Typ (z.B. button)", required=False, default="button"),
        P("element_label", "string", "Optionales Label des Elements", required=False, default=None),
    ],
    capabilities=["vision", "verification"],
    category=C.VISION
)
async def get_verified_click_coordinates(
    element_type: str = "button",
    element_label: Optional[str] = None
) -> dict:
    """Gibt verifizierte Klick-Koordinaten für ein Element zurück."""
    search_desc = f"{element_label} {element_type}" if element_label else element_type
    return await find_element_verified(search_desc)

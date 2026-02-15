# Verified Vision Tool Package
"""
Zuverlässige Screenshot-Analyse durch Multi-Layer Verifikation.

Dieses Tool kombiniert Moondream (schnelle visuelle Extraktion), 
OCR (Text-Verifikation), und Text-LLM (Plausibilitätsprüfung) für 
zuverlässigere UI-Element-Erkennung.
"""

from .tool import (
    analyze_screen_verified,
    find_element_verified,
    get_verified_click_coordinates,
    VerifiedVisionEngine,
    VerifiedElement
)

__all__ = [
    "analyze_screen_verified",
    "find_element_verified",
    "get_verified_click_coordinates",
    "VerifiedVisionEngine",
    "VerifiedElement"
]

__version__ = "1.0.0"

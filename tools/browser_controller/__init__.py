"""
Browser Controller v2 - DOM-First Hybrid Architecture

Kombiniert:
- Playwright (DOM-First) für Browser-Automation
- Vision (GPT-4/Qwen) als Fallback
- SoM Tool für UI-Element-Erkennung
- Verification Tool für Post-Checks
- State Tracking für Loop-Detection

Version: 2.0.0
Datum: 2026-02-10
"""

from .controller import HybridBrowserController
from .state_tracker import UIStateTracker, UIState
from .dom_parser import DOMParser, DOMElement

__all__ = [
    'HybridBrowserController',
    'UIStateTracker',
    'UIState',
    'DOMParser',
    'DOMElement',
]

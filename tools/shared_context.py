# tools/shared_context.py

import logging
from typing import Optional, List

# Wir importieren die Typen auf oberster Ebene
from openai import OpenAI
import chromadb.types

# =================================================================
# PASSIVER CONTAINER FÜR GETEILTE RESSOURCEN
# =================================================================
# Diese Datei definiert nur die "Behälter" für die globalen Objekte.
# Die Initialisierung und Befüllung dieser Variablen erfolgt AUSSCHLIESSLICH
# im `startup_event` des `mcp_server.py`.
# =================================================================

# --- Geteilte API-Clients ---
openai_client: Optional[OpenAI] = None
inception_client: Optional[OpenAI] = None

# --- Geteilte Datenbank-Verbindung ---
memory_collection: Optional[chromadb.types.Collection] = None

# --- Geteilte Browser-Context-Manager (NEU: Phase A1) ---
# Wird im mcp_server lifespan initialisiert
browser_context_manager: Optional["PersistentContextManager"] = None

# --- Geteilte Konstanten ---
CONSENT_SELECTORS: List[str] = [
    "button#onetrust-accept-btn-handler", "button[aria-label='Alle akzeptieren']",
    "button[aria-label='Accept all']", ".cmpboxbtnyes", ".fc-cta-consent",
    "[data-testid='cookie-banner-accept']", "button[data-accept-action='all']",
]

# --- Hardware ---
device: str = "cpu"

# --- Geteilte Engines ---
# Segmentation Engine für visuelle UI-Element-Erkennung
try:
    from tools.engines.segmentation_engine import segmentation_engine_instance
except ImportError:
    segmentation_engine_instance = None

# Object Detection Engine für einfachere UI-Element-Erkennung
try:
    from tools.engines.object_detection_engine import object_detection_engine_instance
except ImportError:
    object_detection_engine_instance = None

# Qwen2.5-VL Vision Language Model Engine für UI-Automation
try:
    from tools.engines.qwen_vl_engine import qwen_vl_engine_instance
except ImportError:
    qwen_vl_engine_instance = None

# OCR Engine
ocr_engine = None

# --- Globaler Logger ---
log = logging.getLogger("timus.context")
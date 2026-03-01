"""ImageAgent — Bild-Analyse mit Qwen 3.5 Plus (OpenRouter).

Workflow:
1. Bild von Disk lesen + Base64-Encoding
2. Bild-Analyse via Qwen 3.5 Plus (Vision)
3. Falls Suchintent erkannt → Delegation an research-Agent mit Bild-Beschreibung als Kontext
"""

import logging
import asyncio
import base64
import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

from agent.base_agent import BaseAgent
from agent.prompts import IMAGE_PROMPT_TEMPLATE
from utils.realsense_capture import RealSenseError, capture_realsense_frame
from utils.realsense_stream import (
    RealSenseStreamError,
    get_realsense_stream_manager,
)

log = logging.getLogger("TimusAgent-ImageAgent")

_MIME_MAP = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
    ".bmp":  "image/bmp",
    ".tiff": "image/tiff",
    ".tif":  "image/tiff",
    ".avif": "image/avif",
}

# Keywords die eine Suche/Recherche zum Bildinhalt anfordern
_SEARCH_KEYWORDS = [
    "suche", "such mir", "recherchiere", "recherche",
    "informationen zu", "informationen über", "informationen ueber",
    "wer ist", "was ist das", "finde heraus", "finde informationen",
    "mehr wissen", "mehr informationen", "hintergrund",
    "kontext", "erkläre mir", "erklär mir", "erzähl mir",
    "was weißt du", "was weisst du", "wer sind",
    "woher kommt", "was bedeutet",
]

_CAMERA_KEYWORDS = [
    "kamera",
    "camera",
    "realsense",
    "d435",
    "webcam",
    "tiefenkamera",
    "depth camera",
]

_CAMERA_INTENT_KEYWORDS = [
    "was siehst",
    "was siehst du",
    "analysiere",
    "beschreibe",
    "erkenne",
    "schau",
    "sieh",
    "zeige",
    "snapshot",
    "aufnahme",
    "foto",
    "bild",
]

_CAMERA_SHORTCUT_PHRASES = [
    "kannst du mich sehen",
    "kannst du mich gerade sehen",
    "siehst du mich",
    "was siehst du",
    "schau dir das an",
    "sieh dir das an",
    "schau mal hier",
]

_NON_CAMERA_HINTS = [
    "http://",
    "https://",
    "www.",
    ".py",
    ".js",
    ".ts",
    ".csv",
    ".xlsx",
    "datei",
    "code",
    "skript",
    "recherchiere",
    "google",
]


class ImageAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(
            IMAGE_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=1,
            agent_type="image",
        )

    def _wants_search(self, task: str) -> bool:
        """Prüft ob der Nutzer eine Suche/Recherche zum Bildinhalt möchte."""
        task_lower = task.lower()
        return any(kw in task_lower for kw in _SEARCH_KEYWORDS)

    def _wants_camera_capture(self, task: str) -> bool:
        task_lower = task.lower()
        has_camera = any(kw in task_lower for kw in _CAMERA_KEYWORDS)
        has_intent = any(kw in task_lower for kw in _CAMERA_INTENT_KEYWORDS)
        if has_camera and has_intent:
            return True

        has_shortcut = any(phrase in task_lower for phrase in _CAMERA_SHORTCUT_PHRASES)
        has_non_camera_hint = any(hint in task_lower for hint in _NON_CAMERA_HINTS)
        has_local_video = any(os.path.exists(f"/dev/video{i}") for i in range(12))
        return has_shortcut and has_local_video and not has_non_camera_hint

    async def _capture_from_realsense(self) -> tuple[Optional[Path], Optional[str]]:
        """Captures a RealSense snapshot and returns (path, warning_message)."""
        output_dir = os.getenv("REALSENSE_CAPTURE_DIR", "").strip() or None
        prefix = os.getenv("REALSENSE_CAPTURE_PREFIX", "timus_d435")
        include_depth = os.getenv("REALSENSE_CAPTURE_DEPTH", "0").strip().lower() in {
            "1", "true", "yes", "on"
        }
        stream_autostart = os.getenv("REALSENSE_STREAM_AUTO_START_FOR_IMAGE", "1").strip().lower() in {
            "1", "true", "yes", "on"
        }
        stream_width = int(os.getenv("REALSENSE_STREAM_WIDTH", "1280"))
        stream_height = int(os.getenv("REALSENSE_STREAM_HEIGHT", "720"))
        stream_fps = float(os.getenv("REALSENSE_STREAM_FPS", "10"))
        stream_max_age_sec = float(os.getenv("REALSENSE_STREAM_MAX_AGE_SEC", "3.0"))

        stream_manager = get_realsense_stream_manager()

        if stream_autostart and not stream_manager.is_running():
            try:
                await asyncio.to_thread(
                    stream_manager.start,
                    stream_width,
                    stream_height,
                    stream_fps,
                    None,
                )
            except Exception as exc:
                log.warning(f"Konnte RealSense-Stream nicht starten, nutze Snapshot-Fallback: {exc}")

        try:
            live = await asyncio.to_thread(
                stream_manager.export_latest_frame,
                output_dir,
                f"{prefix}_live",
                stream_max_age_sec,
                "jpg",
            )
            live_path = live.get("path")
            if live_path:
                return Path(live_path), None
        except RealSenseStreamError:
            pass
        except Exception as exc:
            log.warning(f"Live-Frame Export fehlgeschlagen, nutze Snapshot-Fallback: {exc}")

        try:
            capture = await asyncio.to_thread(
                capture_realsense_frame,
                output_dir,
                prefix,
                include_depth,
                12.0,
            )
        except RealSenseError as exc:
            return None, f"Kameraaufnahme fehlgeschlagen: {exc}"
        except Exception as exc:
            return None, f"Unerwarteter Kamerafehler: {exc}"

        color_path = capture.get("color_path")
        if not color_path:
            return None, "Kameraaufnahme fehlgeschlagen: Kein Farbframe erhalten."
        return Path(color_path), None

    async def run(self, task: str) -> str:
        camera_snapshot_note = ""

        # Dateipfad aus der Aufgabe extrahieren
        path_match = re.search(
            r"(/[\w./\-]+\.(?:jpg|jpeg|png|webp|gif|bmp|tiff?|avif))",
            task, re.IGNORECASE
        )

        if path_match:
            img_path = Path(path_match.group(1))
        elif self._wants_camera_capture(task):
            img_path, warning = await self._capture_from_realsense()
            if warning:
                return (
                    f"{warning}\n\n"
                    "Prüfe die Kamera mit `rs-enumerate-devices` und versuche es erneut."
                )
            camera_snapshot_note = f"(Kamera-Snapshot: {img_path})\n\n"
        else:
            return (
                "Kein gueltiger Bildpfad in der Anfrage gefunden. "
                "Du kannst einen absoluten Bildpfad angeben oder nach einer Kameraaufnahme fragen "
                "(z.B. 'Analysiere das Kamerabild von der D435')."
            )

        if not img_path.exists():
            return f"Bilddatei nicht gefunden: {img_path}"

        suffix = img_path.suffix.lower()
        mime = _MIME_MAP.get(suffix, "image/jpeg")

        try:
            img_b64 = base64.b64encode(img_path.read_bytes()).decode()
        except Exception as e:
            log.error(f"Fehler beim Lesen der Bilddatei: {e}")
            return f"Fehler beim Lesen der Bilddatei: {e}"

        system_prompt = IMAGE_PROMPT_TEMPLATE.format(current_date=date.today().isoformat())

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": task},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{img_b64}"},
                    },
                ],
            },
        ]

        log.info(f"ImageAgent analysiert: {img_path.name} ({mime}, {len(img_b64)//1024} KB b64)")
        image_analysis = await self._call_llm(messages)
        if camera_snapshot_note:
            image_analysis = camera_snapshot_note + image_analysis

        # Suche/Recherche delegieren wenn gewünscht
        if self._wants_search(task):
            log.info("ImageAgent: Suchintent erkannt → delegiere an research-Agent")
            try:
                from tools.delegation_tool.tool import delegate_to_agent

                research_task = (
                    f"Recherchiere Informationen zu folgendem Bildinhalt:\n\n"
                    f"**Bild-Analyse:** {image_analysis}\n\n"
                    f"**Ursprüngliche Anfrage:** {task}\n\n"
                    f"Finde relevante Hintergründe, Fakten und Kontext zu dem was im Bild zu sehen ist."
                )

                research_result = await delegate_to_agent(
                    agent_type="research",
                    task=research_task,
                    from_agent="image",
                    session_id=getattr(self, "conversation_session_id", None),
                )

                if isinstance(research_result, dict):
                    status = research_result.get("status", "success")
                    research_text = research_result.get("result", str(research_result))
                    if status == "partial":
                        note = "\n\n_(Hinweis: Recherche wurde nur teilweise abgeschlossen)_"
                    elif status == "error":
                        research_text = research_result.get("error", str(research_result))
                        note = "\n\n_(Hinweis: Recherche fehlgeschlagen)_"
                    else:
                        note = ""
                else:
                    research_text = str(research_result)
                    note = ""

                return (
                    f"## Bild-Analyse\n\n{image_analysis}\n\n"
                    f"---\n\n"
                    f"## Recherche-Ergebnisse\n\n{research_text}{note}"
                )

            except Exception as e:
                log.error(f"Delegation an research fehlgeschlagen: {e}")
                return f"{image_analysis}\n\n_(Recherche konnte nicht durchgeführt werden: {e})_"

        return image_analysis

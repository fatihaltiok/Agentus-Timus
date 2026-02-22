"""ImageAgent — Bild-Analyse mit Qwen 3.5 Plus (OpenRouter)."""

import base64
import re
import logging
from datetime import date
from pathlib import Path

from agent.base_agent import BaseAgent
from agent.prompts import IMAGE_PROMPT_TEMPLATE

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


class ImageAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(
            IMAGE_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=1,
            agent_type="image",
        )

    async def run(self, task: str) -> str:
        # Dateipfad aus der Aufgabe extrahieren
        path_match = re.search(r"(/[\w./\-]+\.(?:jpg|jpeg|png|webp|gif|bmp|tiff?|avif))", task, re.IGNORECASE)
        if not path_match:
            return "Kein gueltiger Bildpfad in der Anfrage gefunden. Bitte absoluten Pfad angeben."

        img_path = Path(path_match.group(1))
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
        return await self._call_llm(messages)

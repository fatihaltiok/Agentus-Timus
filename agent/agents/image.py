"""ImageAgent — Bild-Analyse mit Qwen 3.5 Plus (OpenRouter).

Workflow:
1. Bild von Disk lesen + Base64-Encoding
2. Bild-Analyse via Qwen 3.5 Plus (Vision)
3. Falls Suchintent erkannt → Delegation an research-Agent mit Bild-Beschreibung als Kontext
"""

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

    async def run(self, task: str) -> str:
        # Dateipfad aus der Aufgabe extrahieren
        path_match = re.search(
            r"(/[\w./\-]+\.(?:jpg|jpeg|png|webp|gif|bmp|tiff?|avif))",
            task, re.IGNORECASE
        )
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
        image_analysis = await self._call_llm(messages)

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
                )

                if isinstance(research_result, dict):
                    research_text = research_result.get("result", str(research_result))
                else:
                    research_text = str(research_result)

                return (
                    f"## Bild-Analyse\n\n{image_analysis}\n\n"
                    f"---\n\n"
                    f"## Recherche-Ergebnisse\n\n{research_text}"
                )

            except Exception as e:
                log.error(f"Delegation an research fehlgeschlagen: {e}")
                return f"{image_analysis}\n\n_(Recherche konnte nicht durchgeführt werden: {e})_"

        return image_analysis

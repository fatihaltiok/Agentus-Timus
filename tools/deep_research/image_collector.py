# tools/deep_research/image_collector.py
"""
ImageCollector — sammelt Bilder für Deep Research v6.0 PDF-Berichte.

Strategie je Abschnitt:
1. Web-Bild via DataForSEO Google Images suchen und herunterladen
2. Fallback: DALL-E-Bild generieren
3. Fallback 2: Abschnitt ohne Bild
"""

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests as requests_lib
from dotenv import load_dotenv

from tools.planner.planner_helpers import call_tool_internal

load_dotenv(override=True)
logger = logging.getLogger("image_collector")

_RESULTS_DIR = Path(os.getenv("TIMUS_RESULTS_DIR", "/home/fatih-ubuntu/dev/timus/results"))
_DOWNLOAD_TIMEOUT = 10
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _extract_generated_image_path(result: dict) -> Optional[str]:
    artifacts = result.get("artifacts")
    if isinstance(artifacts, list):
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if path:
                return path

    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        for key in ("image_path", "saved_as", "path", "filepath"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for key in ("saved_as", "image_path", "path", "filepath"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


@dataclass
class ImageResult:
    local_path: str    # Absoluter Pfad zur heruntergeladenen/generierten Datei
    caption: str       # Bildunterschrift
    section_title: str # Zugehöriger Abschnitt
    source: str        # "web" | "dalle"


class ImageCollector:
    """Sammelt Bilder für die Abschnitte eines Deep-Research-Berichts."""

    async def collect_images_for_sections(
        self,
        sections: List[str],
        query: str,
        max_images: int = 4,
    ) -> List[ImageResult]:
        """
        Sammelt max. `max_images` Bilder für die angegebenen Abschnitte.

        Args:
            sections: Liste von Abschnittstiteln (## Überschriften aus dem Bericht)
            query: Hauptrecherche-Thema (für Kontext)
            max_images: Maximale Bildanzahl

        Returns:
            Liste von ImageResult-Objekten
        """
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        async def _safe_collect(section: str) -> Optional[ImageResult]:
            topic = f"{section} {query}".strip()
            try:
                return await self._collect_one(section, topic)
            except Exception as e:
                logger.warning(f"Bild für '{section}' fehlgeschlagen (unkritisch): {e}")
                return None

        gathered = await asyncio.gather(*[_safe_collect(s) for s in sections[:max_images]])
        results: List[ImageResult] = [img for img in gathered if img is not None]

        logger.info(f"🖼️ {len(results)} Bilder gesammelt ({len(sections[:max_images])} Abschnitte)")
        return results

    # ------------------------------------------------------------------
    # Interne Methoden
    # ------------------------------------------------------------------

    async def _collect_one(self, section_title: str, topic: str) -> Optional[ImageResult]:
        """Versucht Web-Download, dann DALL-E, dann gibt None zurück."""
        # Versuch 1: Web-Bild
        url = await self._find_web_image(topic)
        if url:
            local_path = await self._download_image(url)
            if local_path:
                return ImageResult(
                    local_path=local_path,
                    caption=section_title,
                    section_title=section_title,
                    source="web",
                )

        # Versuch 2: DALL-E
        local_path = await self._generate_dalle_image(topic)
        if local_path:
            return ImageResult(
                local_path=local_path,
                caption=section_title,
                section_title=section_title,
                source="dalle",
            )

        return None

    async def _find_web_image(self, topic: str) -> Optional[str]:
        """Sucht via DataForSEO Google Images nach einem Bild-URL."""
        try:
            results = await call_tool_internal(
                "search_images", {"query": topic, "max_results": 8}
            )
            if not isinstance(results, list):
                return None

            for item in results:
                # DataForSEO gibt bei Images-Suche direkte Bild-URLs zurück
                # entweder in 'url' oder in zusätzlichen Feldern
                for field in ("url", "image_url", "encoded_url", "source_url"):
                    candidate = item.get(field, "")
                    if not candidate:
                        continue
                    ext = Path(candidate.split("?")[0]).suffix.lower()
                    if ext in _IMAGE_EXTENSIONS:
                        return candidate
        except Exception as e:
            logger.warning(f"Web-Bild-Suche fehlgeschlagen: {e}")
        return None

    async def _download_image(self, url: str) -> Optional[str]:
        """Lädt ein Bild herunter, prüft es mit Pillow und speichert es lokal."""
        def _do_download():
            resp = requests_lib.get(url, timeout=_DOWNLOAD_TIMEOUT, stream=True)
            resp.raise_for_status()

            # Größencheck
            content_length = int(resp.headers.get("Content-Length", 0))
            if content_length > _MAX_IMAGE_BYTES:
                raise ValueError(f"Bild zu groß: {content_length} Bytes")

            data = b""
            for chunk in resp.iter_content(chunk_size=8192):
                data += chunk
                if len(data) > _MAX_IMAGE_BYTES:
                    raise ValueError("Bild zu groß (stream)")
            return data

        try:
            data = await asyncio.to_thread(_do_download)
        except Exception as e:
            logger.warning(f"Download fehlgeschlagen ({url[:60]}...): {e}")
            return None

        # Pillow-Validierung + Speichern (ein Import, eine BytesIO-Instanz)
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
        filename = f"img_{url_hash}.jpg"
        local_path = _RESULTS_DIR / filename
        try:
            from PIL import Image
            import io
            buf = io.BytesIO(data)
            img = Image.open(buf)
            img.verify()          # Korruptionscheck (schließt intern)
            buf.seek(0)           # Zurückspulen für convert
            img = Image.open(buf).convert("RGB")
            img.save(str(local_path), "JPEG", quality=85)
            logger.info(f"🖼️ Bild gespeichert: {local_path}")
            return str(local_path)
        except Exception as e:
            logger.warning(f"Bild-Speichern fehlgeschlagen: {e}")
            return None

    async def _generate_dalle_image(self, topic: str) -> Optional[str]:
        """Generiert ein DALL-E-Bild und gibt den lokalen Pfad zurück."""
        try:
            result = await call_tool_internal("generate_image", {
                "prompt": (
                    f"Sachliche Illustration zu: {topic}. "
                    "Sauber, professionell, kein Text im Bild, "
                    "neutraler Hintergrund, infografischer Stil."
                ),
                "size": "1536x1024",
                "quality": "medium",
            })

            if not isinstance(result, dict):
                return None

            generated_path = _extract_generated_image_path(result)
            if generated_path:
                full_path = Path(generated_path)
                if not full_path.is_absolute():
                    full_path = Path("/home/fatih-ubuntu/dev/timus") / generated_path
                if full_path.exists():
                    return str(full_path)

            # Wenn temporäre URL zurückgegeben
            image_url = result.get("image_url")
            if image_url:
                return await self._download_image(image_url)

        except Exception as e:
            logger.warning(f"DALL-E Bild-Generierung fehlgeschlagen: {e}")
        return None

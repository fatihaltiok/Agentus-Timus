# tools/deep_research/youtube_researcher.py
"""
YouTubeResearcher — analysiert relevante YouTube-Videos für Deep Research v6.0.

Für jedes Video:
1. Transkript via DataForSEO abrufen
2. Fakten per LLM aus dem Text extrahieren (qwen3.5-plus via OpenRouter)
3. Thumbnail per NVIDIA NIM visuell analysieren (Fallback: leer)
4. Fakten als unverified_claims in die Session eintragen
"""

import asyncio
import logging
import os
from typing import List, Optional, TYPE_CHECKING

from dotenv import load_dotenv
from openai import OpenAI

from tools.planner.planner_helpers import call_tool_internal

if TYPE_CHECKING:
    from tools.deep_research.tool import DeepResearchSession

load_dotenv()
logger = logging.getLogger("youtube_researcher")

# --- Modell-Konfiguration ---
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
_ANALYSIS_MODEL = os.getenv("YOUTUBE_ANALYSIS_MODEL", "qwen/qwen3-235b-a22b")

_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
_NVIDIA_KEY = os.getenv("NVIDIA_API_KEY", "")
_VISION_MODEL = os.getenv("YOUTUBE_VISION_MODEL", "nvidia/llama-3.2-90b-vision-instruct")


class YouTubeResearcher:
    """Analysiert YouTube-Videos und reichert eine DeepResearchSession mit Fakten an."""

    async def research_topic_on_youtube(
        self,
        query: str,
        session: "DeepResearchSession",
        max_videos: int = 3,
    ) -> int:
        """
        Sucht Videos zum Thema und analysiert Transkript + Thumbnail.

        Args:
            query: Recherche-Thema
            session: Laufende DeepResearchSession (wird in-place erweitert)
            max_videos: Maximal zu analysierende Videos

        Returns:
            Anzahl erfolgreich analysierter Videos
        """
        videos = await self._search_videos(query)
        if not videos:
            logger.info("📺 Keine YouTube-Videos gefunden")
            return 0

        analyzed = 0
        for video in videos[:max_videos]:
            try:
                transcript = await self._get_transcript(video["video_id"])
                text_facts = {}
                visual_info = {}

                if transcript and len(transcript) > 100:
                    text_facts = await self._analyze_text(transcript, query)

                thumbnail_url = video.get("thumbnail_url", "")
                if thumbnail_url:
                    visual_info = await self._analyze_thumbnail(thumbnail_url, query)

                self._add_to_session(session, video, text_facts, visual_info)
                analyzed += 1
                logger.info(
                    f"📺 Video analysiert: '{video.get('title', video['video_id'])}' "
                    f"— {len(text_facts.get('facts', []))} Fakten"
                )
            except Exception as e:
                logger.warning(f"Video {video['video_id']} übersprungen: {e}")

        return analyzed

    # ------------------------------------------------------------------
    # Interne Methoden
    # ------------------------------------------------------------------

    async def _search_videos(self, query: str) -> List[dict]:
        try:
            result = await call_tool_internal("search_youtube", {"query": query, "max_results": 5})
            if isinstance(result, list):
                logger.info(f"📺 YouTube-Suche: {len(result)} Videos für '{query[:40]}'")
                return result
            # Fehler-Dict von call_tool_internal → detailliert loggen
            if isinstance(result, dict) and result.get("error"):
                logger.warning(f"📺 YouTube-Suche Fehler: {result['error']}")
            else:
                logger.warning(f"📺 YouTube-Suche: unerwartetes Format {type(result).__name__}: {str(result)[:100]}")
            return []
        except Exception as e:
            logger.warning(f"YouTube-Suche fehlgeschlagen: {e}")
            return []

    async def _get_transcript(self, video_id: str) -> Optional[str]:
        try:
            result = await call_tool_internal(
                "get_youtube_subtitles", {"video_id": video_id, "language_code": "de"}
            )
            if isinstance(result, dict):
                return result.get("full_text") or ""
            return ""
        except Exception as e:
            logger.warning(f"Transkript für {video_id} fehlgeschlagen: {e}")
            return None

    async def _analyze_text(self, text: str, query: str) -> dict:
        """Extrahiert Fakten aus dem Transkript via qwen3.5-plus (OpenRouter)."""
        if not _OPENROUTER_KEY:
            logger.warning("OPENROUTER_API_KEY fehlt — Text-Analyse übersprungen")
            return {}

        prompt = (
            f"Thema: {query}\n\n"
            f"YouTube-Transkript (Auszug):\n{text[:4000]}\n\n"
            "Extrahiere die wichtigsten Fakten aus diesem Transkript.\n"
            "Antworte NUR als JSON:\n"
            '{"facts": ["Fakt 1", "Fakt 2", ...], "key_quote": "wörtliches Zitat", "relevance": 7}'
        )

        def _call():
            oc = OpenAI(api_key=_OPENROUTER_KEY, base_url=_OPENROUTER_BASE)
            resp = oc.chat.completions.create(
                model=_ANALYSIS_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=600,
            )
            return resp.choices[0].message.content or ""

        try:
            raw = await asyncio.to_thread(_call)
            # JSON aus Antwort extrahieren
            import json, re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logger.warning(f"Text-Analyse fehlgeschlagen: {e}")
        return {}

    async def _analyze_thumbnail(self, thumbnail_url: str, query: str) -> dict:
        """Analysiert das Thumbnail via NVIDIA NIM Vision (Fallback: leer)."""
        if not _NVIDIA_KEY:
            return {}

        prompt = (
            f"Was ist auf diesem YouTube-Thumbnail zu sehen? "
            f"Beziehe dich auf das Thema: '{query}'. "
            "Antworte auf Deutsch, max 2 Sätze."
        )

        def _call():
            nc = OpenAI(api_key=_NVIDIA_KEY, base_url=_NVIDIA_BASE)
            resp = nc.chat.completions.create(
                model=_VISION_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": thumbnail_url}},
                        {"type": "text", "text": prompt},
                    ],
                }],
                temperature=0.2,
                max_tokens=150,
            )
            return resp.choices[0].message.content or ""

        try:
            description = await asyncio.to_thread(_call)
            return {"visual_description": description}
        except Exception as e:
            logger.warning(f"Thumbnail-Analyse fehlgeschlagen (unkritisch): {e}")
            return {}

    def _add_to_session(
        self,
        session: "DeepResearchSession",
        video: dict,
        text_facts: dict,
        visual_info: dict,
    ) -> None:
        """Fügt extrahierte Fakten als unverified_claims in die Session ein."""
        title = video.get("title", video["video_id"])
        url = video.get("url", f"https://www.youtube.com/watch?v={video['video_id']}")
        channel = video.get("channel_name", "")

        facts = text_facts.get("facts", [])
        key_quote = text_facts.get("key_quote", "")
        relevance = text_facts.get("relevance", 5)
        visual_desc = visual_info.get("visual_description", "")

        # Zusammenfassender Fakt mit Video-Kontext
        if facts or key_quote:
            combined = "; ".join(facts[:5])
            if key_quote:
                combined += f' | Zitat: "{key_quote}"'
            if visual_desc:
                combined += f" | Bild: {visual_desc}"

            session.unverified_claims.append({
                "fact": combined,
                "source": url,
                "source_title": title,
                "source_type": "youtube",
                "channel": channel,
                "relevance": relevance,
                "video_id": video["video_id"],
                "thumbnail_url": video.get("thumbnail_url", ""),
            })

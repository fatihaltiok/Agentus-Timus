# tools/deep_research/youtube_researcher.py
"""
YouTubeResearcher — analysiert relevante YouTube-Videos für Deep Research v6.1.

Änderungen v6.1:
- Bilinguale Suche: deutschsprachige UND englischsprachige Queries
- Transkript-Fallback: erst 'de', dann 'en' (erfasst internationale Podcasts + Interviews)
- max_videos 3 → 5 (mehr Podcast-/Interview-Abdeckung)
- Zusätzliche Query-Varianten: <Thema> podcast, <Thema> interview, <Thema> explained

Für jedes Video:
1. Transkript via DataForSEO abrufen (de → en Fallback)
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

# Maximale Videos pro Recherche (konfigurierbar via ENV)
_MAX_VIDEOS = int(os.getenv("YOUTUBE_MAX_VIDEOS", "5"))


def _build_queries(query: str) -> List[str]:
    """
    Baut eine Liste von Such-Queries auf: deutsch + englisch + Inhaltstypen.
    Ziel: Podcasts, Interviews, Erklärvideos auf beiden Sprachen erfassen.
    """
    q = query.strip()
    return [
        q,                                  # Original-Query (DE oder EN)
        f"{q} podcast",                     # Podcast-Suche
        f"{q} interview",                   # Interview-Suche
        f"{q} explained",                   # Englischsprachige Erklärvideos
        f"{q} erklärt",                     # Deutschsprachige Erklärvideos
    ]


class YouTubeResearcher:
    """Analysiert YouTube-Videos bilingual und reichert eine DeepResearchSession mit Fakten an."""

    async def research_topic_on_youtube(
        self,
        query: str,
        session: "DeepResearchSession",
        max_videos: int = _MAX_VIDEOS,
    ) -> int:
        """
        Sucht Videos zum Thema auf Deutsch UND Englisch und analysiert Transkript + Thumbnail.

        Args:
            query:      Recherche-Thema
            session:    Laufende DeepResearchSession (wird in-place erweitert)
            max_videos: Maximal zu analysierende Videos (default: YOUTUBE_MAX_VIDEOS=5)

        Returns:
            Anzahl erfolgreich analysierter Videos
        """
        # Bilinguale Suche: alle Query-Varianten, Duplikate nach video_id filtern
        videos = await self._search_videos_multilingual(query, max_videos)
        if not videos:
            logger.info("📺 Keine YouTube-Videos gefunden")
            return 0

        analyzed = 0
        for video in videos[:max_videos]:
            try:
                transcript = await self._get_transcript_with_fallback(video["video_id"])
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

        logger.info(f"📺 YouTube gesamt: {analyzed}/{len(videos)} Videos erfolgreich analysiert")
        return analyzed

    # ------------------------------------------------------------------
    # Interne Methoden
    # ------------------------------------------------------------------

    async def _search_videos_multilingual(self, query: str, max_videos: int) -> List[dict]:
        """
        Durchsucht YouTube mit mehreren Query-Varianten (DE + EN + Podcast/Interview).
        Dedupliziert nach video_id — jedes Video nur einmal.
        """
        seen_ids: set = set()
        all_videos: List[dict] = []

        for q in _build_queries(query):
            if len(all_videos) >= max_videos * 2:
                break  # Genug Kandidaten gesammelt
            try:
                result = await call_tool_internal("search_youtube", {"query": q, "max_results": 5})
                if isinstance(result, list):
                    for v in result:
                        vid = v.get("video_id", "")
                        if vid and vid not in seen_ids:
                            seen_ids.add(vid)
                            all_videos.append(v)
                    logger.info(f"📺 Query '{q[:50]}': {len(result)} Treffer")
                elif isinstance(result, dict) and result.get("error"):
                    logger.warning(f"📺 Query '{q[:50]}' Fehler: {result['error']}")
            except Exception as e:
                logger.warning(f"📺 Query '{q[:50]}' fehlgeschlagen: {e}")

        logger.info(f"📺 Bilinguale Suche: {len(all_videos)} einzigartige Videos gefunden")
        return all_videos

    async def _get_transcript_with_fallback(self, video_id: str) -> Optional[str]:
        """
        Versucht Transkript auf Deutsch zu laden, fällt auf Englisch zurück.
        Erfasst so deutsche Beiträge UND englische Podcasts/Interviews.
        """
        for lang in ("de", "en"):
            try:
                result = await call_tool_internal(
                    "get_youtube_subtitles", {"video_id": video_id, "language_code": lang}
                )
                if isinstance(result, dict):
                    text = result.get("full_text") or ""
                    if len(text) > 100:
                        logger.debug(f"📺 Transkript ({lang}) für {video_id}: {len(text)} Zeichen")
                        return text
            except Exception as e:
                logger.warning(f"Transkript ({lang}) für {video_id} fehlgeschlagen: {e}")
        return None

    async def _analyze_text(self, text: str, query: str) -> dict:
        """Extrahiert Fakten aus dem Transkript via LLM (DE + EN Inhalte)."""
        if not _OPENROUTER_KEY:
            logger.warning("OPENROUTER_API_KEY fehlt — Text-Analyse übersprungen")
            return {}

        prompt = (
            f"Thema: {query}\n\n"
            f"YouTube-Transkript (Auszug — kann Deutsch oder Englisch sein):\n{text[:4000]}\n\n"
            "Extrahiere die wichtigsten Fakten aus diesem Transkript. "
            "Antworte auf DEUTSCH, auch wenn das Transkript auf Englisch ist.\n"
            "Antworte NUR als JSON:\n"
            '{"facts": ["Fakt 1", "Fakt 2", ...], "key_quote": "wörtliches Zitat (übersetzt wenn nötig)", "relevance": 7}'
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

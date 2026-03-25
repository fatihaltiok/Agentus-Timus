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
import json
import logging
import os
import re
from typing import Any, List, Optional, TYPE_CHECKING

from dotenv import load_dotenv
from openai import OpenAI

from agent.shared.json_utils import extract_json_robust
from tools.planner.planner_helpers import call_tool_internal

if TYPE_CHECKING:
    from tools.deep_research.tool import DeepResearchSession

load_dotenv(override=True)
logger = logging.getLogger("youtube_researcher")

# --- Modell-Konfiguration ---
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Primär: Qwen3.5-122B analysiert Video direkt (Bild + Audio + Bewegung)
_VIDEO_MODEL = os.getenv("YOUTUBE_VIDEO_MODEL", "qwen/qwen3.5-122b-a10b")
# Fallback Text-Analyse (nur Transkript, kein Video-Verständnis)
_ANALYSIS_MODEL = os.getenv("YOUTUBE_ANALYSIS_MODEL", "qwen/qwen3-235b-a22b")

# Optionale NVIDIA-Thumbnail-Analyse (nur wenn NVIDIA_API_KEY gesetzt)
_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
_NVIDIA_KEY = os.getenv("NVIDIA_API_KEY", "")
_VISION_MODEL = os.getenv("YOUTUBE_VISION_MODEL", "nvidia/llama-3.2-90b-vision-instruct")

# Maximale Videos pro Recherche (konfigurierbar via ENV)
_MAX_VIDEOS = int(os.getenv("YOUTUBE_MAX_VIDEOS", "5"))
_TRANSCRIPT_CHUNK_CHARS = max(1200, int(os.getenv("YOUTUBE_TRANSCRIPT_CHUNK_CHARS", "6000")))
_TRANSCRIPT_CHUNK_OVERLAP = max(0, int(os.getenv("YOUTUBE_TRANSCRIPT_CHUNK_OVERLAP", "600")))
_TRANSCRIPT_MAX_CHUNKS = max(1, int(os.getenv("YOUTUBE_TRANSCRIPT_MAX_CHUNKS", "24")))
_TRANSCRIPT_ANALYSIS_INPUT_MAX = max(1500, int(os.getenv("YOUTUBE_TRANSCRIPT_ANALYSIS_INPUT_MAX", "7000")))


def _build_queries(query: str) -> List[str]:
    """
    Baut eine Liste von Such-Queries auf: deutsch + englisch + Inhaltstypen.
    Duplikate (z.B. wenn Query bereits "podcast" enthält) werden gefiltert.
    """
    q = query.strip()
    candidates = [
        q,
        f"{q} podcast",
        f"{q} interview",
        f"{q} explained",
        f"{q} erklärt",
    ]
    seen: set = set()
    unique: List[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


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

        async def _analyze_video(video: dict) -> bool:
            """
            Primär: Qwen2.5-VL analysiert das Video direkt (URL → Video-Verständnis).
            Fallback: Transcript-/Video-Kontext-Analyse + optionale NVIDIA-Thumbnail-Analyse.
            """
            try:
                video_id = video["video_id"]
                thumbnail_url = video.get("thumbnail_url", "")

                # Primär: Qwen VL schaut das Video direkt an
                video_facts = await self._analyze_video_with_qwen(video_id, query)

                if video_facts.get("facts"):
                    # Qwen VL erfolgreich — enthält Fakten + visuelle Beschreibung
                    text_facts = {k: v for k, v in video_facts.items() if k != "visual_description"}
                    visual_info = {"visual_description": video_facts.get("visual_description", "")}
                    logger.info(
                        f"📺 Qwen-VL: '{video.get('title', video_id)}' "
                        f"— {len(video_facts.get('facts', []))} Fakten (Video-Analyse)"
                    )
                else:
                    # Fallback: Transkript, Video-Kontext und NVIDIA-Thumbnail parallel
                    async def _maybe_thumbnail() -> dict:
                        if thumbnail_url:
                            return await self._analyze_thumbnail(thumbnail_url, query)
                        return {}

                    transcript_payload, visual_info, video_context = await asyncio.gather(
                        self._get_transcript_with_fallback(video_id),
                        _maybe_thumbnail(),
                        self._get_video_context(video_id),
                    )
                    if not isinstance(visual_info, dict):
                        visual_info = {}

                    context_text = self._video_context_to_text(video_context)
                    if video_context.get("description"):
                        visual_info["video_description"] = str(video_context.get("description", "")).strip()
                    if video_context.get("comments"):
                        visual_info["comment_highlights"] = [
                            str(item.get("text", "")).strip()
                            for item in video_context.get("comments", [])[:3]
                            if isinstance(item, dict) and str(item.get("text", "")).strip()
                        ]
                    if isinstance(transcript_payload, dict):
                        visual_info["transcript_segments"] = len(transcript_payload.get("items") or [])
                        visual_info["transcript_language"] = str(transcript_payload.get("language_code", "")).strip()

                    text_facts = {}
                    transcript_text = ""
                    if isinstance(transcript_payload, dict):
                        transcript_text = str(transcript_payload.get("full_text") or "").strip()
                    if transcript_payload and (len(transcript_text) > 100 or (transcript_payload.get("items") or [])):
                        text_facts = await self._analyze_transcript_payload(transcript_payload, query)
                    elif context_text and len(context_text) > 100:
                        text_facts = await self._analyze_text(context_text, query)
                    logger.info(
                        f"📺 Fallback: '{video.get('title', video_id)}' "
                        f"— {len(text_facts.get('facts', []))} Fakten "
                        f"({'Transkript' if transcript_payload else 'Video-Kontext'})"
                    )

                self._add_to_session(session, video, text_facts, visual_info)
                return True
            except Exception as e:
                logger.warning(f"Video {video['video_id']} übersprungen: {e}")
                return False

        results = await asyncio.gather(*[_analyze_video(v) for v in videos[:max_videos]])
        analyzed = sum(1 for ok in results if ok)

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
                result = await call_tool_internal("search_youtube", {"query": q, "max_results": 5, "mode": "live"})
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

    @staticmethod
    def _chunk_transcript_items(
        items: List[dict[str, Any]],
        max_chars: int = _TRANSCRIPT_CHUNK_CHARS,
        overlap_chars: int = _TRANSCRIPT_CHUNK_OVERLAP,
        max_chunks: int = _TRANSCRIPT_MAX_CHUNKS,
    ) -> List[str]:
        """Teilt ein Transkript segmentbasiert in ueberlappende Chunks auf."""
        texts = [
            str(item.get("text", "")).strip()
            for item in items
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        if not texts:
            return []

        total_chars = sum(len(text) + 1 for text in texts)
        effective_max_chars = max(400, int(max_chars or _TRANSCRIPT_CHUNK_CHARS))
        effective_overlap = max(0, int(overlap_chars or 0))
        effective_max_chunks = max(1, int(max_chunks or _TRANSCRIPT_MAX_CHUNKS))

        # Wenn das Material sonst zu viele Chunks erzeugen wuerde, vergroessere die Chunk-Groesse
        # statt spaeter Material still abzuschneiden.
        if total_chars > effective_max_chars * effective_max_chunks:
            effective_max_chars = max(
                effective_max_chars,
                int(total_chars / effective_max_chunks) + effective_overlap + 200,
            )

        chunks: List[str] = []
        current: List[str] = []
        current_len = 0
        index = 0

        while index < len(texts):
            text = texts[index]
            separator = 1 if current else 0
            projected = current_len + separator + len(text)

            if current and projected > effective_max_chars:
                chunk_text = " ".join(current).strip()
                if chunk_text:
                    chunks.append(chunk_text)

                overlap: List[str] = []
                overlap_len = 0
                if effective_overlap > 0:
                    for previous in reversed(current):
                        next_len = overlap_len + len(previous) + (1 if overlap else 0)
                        if next_len > effective_overlap and overlap:
                            break
                        overlap.insert(0, previous)
                        overlap_len = next_len

                current = overlap
                current_len = sum(len(item) for item in current) + max(len(current) - 1, 0)
                continue

            current.append(text)
            current_len = projected
            index += 1

        if current:
            chunk_text = " ".join(current).strip()
            if chunk_text:
                chunks.append(chunk_text)

        return chunks

    async def _get_transcript_with_fallback(self, video_id: str) -> Optional[dict]:
        """
        Lädt DE- und EN-Transkript parallel, bevorzugt Deutsch.
        Erfasst so deutsche Beiträge UND englische Podcasts/Interviews.
        """
        async def _fetch(lang: str) -> Optional[dict]:
            try:
                result = await call_tool_internal(
                    "get_youtube_subtitles", {"video_id": video_id, "language_code": lang, "mode": "standard"}
                )
                if isinstance(result, dict):
                    items = result.get("items") or []
                    text = str(result.get("full_text") or "").strip()
                    if len(text) > 100 or items:
                        payload = dict(result)
                        payload["language_code"] = lang
                        logger.debug(
                            "📺 Transkript (%s) für %s: %s Zeichen, %s Segmente",
                            lang,
                            video_id,
                            len(text),
                            len(items),
                        )
                        return payload
            except Exception as e:
                logger.warning(f"Transkript ({lang}) für {video_id} fehlgeschlagen: {e}")
            return None

        de_payload, en_payload = await asyncio.gather(_fetch("de"), _fetch("en"))
        return de_payload or en_payload

    @staticmethod
    def _merge_chunk_analyses(chunk_results: List[dict]) -> dict:
        """Deterministischer Fallback, falls die Gesamtsynthese fehlschlaegt."""
        seen_facts: set[str] = set()
        merged_facts: List[str] = []
        best_quote = ""
        best_relevance = 0
        relevance_values: List[int] = []

        for result in chunk_results:
            if not isinstance(result, dict):
                continue
            for fact in result.get("facts") or []:
                cleaned = str(fact or "").strip()
                if not cleaned:
                    continue
                key = cleaned.lower()
                if key in seen_facts:
                    continue
                seen_facts.add(key)
                merged_facts.append(cleaned)
                if len(merged_facts) >= 10:
                    break
            quote = str(result.get("key_quote") or "").strip()
            relevance = int(result.get("relevance") or 0)
            if relevance > 0:
                relevance_values.append(relevance)
            if quote and (not best_quote or relevance >= best_relevance):
                best_quote = quote
                best_relevance = relevance

        average_relevance = int(round(sum(relevance_values) / len(relevance_values))) if relevance_values else 0
        return {
            "facts": merged_facts[:8],
            "key_quote": best_quote,
            "relevance": max(best_relevance, average_relevance, 0),
        }

    async def _synthesize_chunk_analyses(self, chunk_results: List[dict], query: str) -> dict:
        """Verdichtet Chunk-Analysen zu einem Gesamtbild fuer ein langes Video-Transkript."""
        if not _OPENROUTER_KEY:
            return self._merge_chunk_analyses(chunk_results)

        chunk_lines: List[str] = []
        for index, result in enumerate(chunk_results, start=1):
            if not isinstance(result, dict):
                continue
            facts = [str(item).strip() for item in result.get("facts") or [] if str(item).strip()]
            quote = str(result.get("key_quote") or "").strip()
            relevance = int(result.get("relevance") or 0)
            line = f"Chunk {index}: Fakten={facts[:5]} | Relevanz={relevance}"
            if quote:
                line += f' | Zitat="{quote[:220]}"'
            chunk_lines.append(line)

        if not chunk_lines:
            return {}

        prompt = (
            f"Thema: {query}\n\n"
            "Unten stehen Teilauswertungen eines langen YouTube-Transkripts.\n"
            "Verdichte sie zu einer konsistenten Gesamtsynthese auf DEUTSCH.\n"
            "Beruecksichtige nur Punkte, die im Material wirklich vorkommen. "
            "Doppelte oder sehr aehnliche Fakten zusammenfassen.\n\n"
            f"{chr(10).join(chunk_lines[:_TRANSCRIPT_MAX_CHUNKS])}\n\n"
            'Antworte NUR als JSON: {"facts": ["Fakt 1", "Fakt 2", ...], "key_quote": "wichtigstes Zitat", "relevance": 8}'
        )

        def _call():
            oc = OpenAI(api_key=_OPENROUTER_KEY, base_url=_OPENROUTER_BASE)
            resp = oc.chat.completions.create(
                model=_ANALYSIS_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=700,
            )
            return resp.choices[0].message.content or ""

        try:
            raw = await asyncio.to_thread(_call)
            parsed = extract_json_robust(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            logger.warning(f"Chunk-Gesamtsynthese fehlgeschlagen: {e}")
        return self._merge_chunk_analyses(chunk_results)

    async def _analyze_transcript_payload(self, payload: dict, query: str) -> dict:
        """Analysiert ein komplettes Transkript, bei Bedarf ueber mehrere Chunks."""
        if not isinstance(payload, dict):
            return {}

        items = payload.get("items") or []
        full_text = str(payload.get("full_text") or "").strip()
        if not full_text and items:
            full_text = " ".join(
                str(item.get("text", "")).strip()
                for item in items
                if isinstance(item, dict) and str(item.get("text", "")).strip()
            ).strip()
        if len(full_text) <= 100:
            return {}

        chunks = self._chunk_transcript_items(items) if items else []
        if not chunks:
            chunks = [full_text]

        if len(chunks) == 1 and len(chunks[0]) <= _TRANSCRIPT_ANALYSIS_INPUT_MAX:
            return await self._analyze_text(chunks[0], query)

        logger.info("📺 Transkript wird gechunked analysiert: %s Chunks", len(chunks))
        chunk_results: List[dict] = []
        total_chunks = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            if len(chunk) <= 100:
                continue
            result = await self._analyze_text(chunk, query, chunk_index=index, total_chunks=total_chunks)
            if isinstance(result, dict) and ((result.get("facts") or []) or result.get("key_quote")):
                chunk_results.append(result)

        if not chunk_results:
            return await self._analyze_text(full_text, query)
        if len(chunk_results) == 1:
            return chunk_results[0]
        return await self._synthesize_chunk_analyses(chunk_results, query)

    async def _get_video_context(self, video_id: str) -> dict:
        """Lädt Metadaten und optional Kommentare/Chapters für ein Video."""
        try:
            result = await call_tool_internal(
                "get_youtube_video_info",
                {"video_id": video_id, "language_code": "de", "mode": "live"},
            )
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.warning(f"📺 Video-Info fehlgeschlagen ({video_id}): {e}")
        return {}

    @staticmethod
    def _video_context_to_text(video_context: dict) -> str:
        """Verdichtet Video-Metadaten zu einem analysierbaren Textfallback."""
        if not isinstance(video_context, dict):
            return ""

        parts: list[str] = []
        title = str(video_context.get("title", "")).strip()
        channel_name = str(video_context.get("channel_name", "")).strip()
        description = str(video_context.get("description", "")).strip()

        if title:
            parts.append(f"Titel: {title}")
        if channel_name:
            parts.append(f"Kanal: {channel_name}")
        if description:
            parts.append(f"Beschreibung: {description[:2000]}")

        chapter_titles = [
            str(chapter.get("title", "")).strip()
            for chapter in video_context.get("chapters", [])[:5]
            if isinstance(chapter, dict) and str(chapter.get("title", "")).strip()
        ]
        if chapter_titles:
            parts.append("Kapitel: " + "; ".join(chapter_titles))

        comment_texts = [
            str(comment.get("text", "")).strip()
            for comment in video_context.get("comments", [])[:3]
            if isinstance(comment, dict) and str(comment.get("text", "")).strip()
        ]
        if comment_texts:
            parts.append("Kommentare: " + " | ".join(comment_texts))

        return "\n".join(parts).strip()

    async def _analyze_video_with_qwen(self, video_id: str, query: str) -> dict:
        """
        Primär-Analyse: Qwen2.5-VL schaut das YouTube-Video direkt an.
        Versteht Bild, Bewegung, Sprache und Kontext in einem Schritt.
        Gibt leeres Dict zurück wenn Qwen VL nicht verfügbar oder fehlschlägt.
        """
        if not _OPENROUTER_KEY:
            return {}

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        prompt = (
            f"Analysiere dieses YouTube-Video zum Thema: '{query}'\n"
            "Extrahiere die wichtigsten Fakten, Argumente und Erkenntnisse aus dem Video.\n"
            "Beziehe sowohl den gesprochenen Inhalt als auch visuelle Elemente ein "
            "(Grafiken, Demos, Animationen, eingeblendete Texte).\n"
            "Antworte auf DEUTSCH, auch wenn das Video auf Englisch ist.\n"
            "Antworte NUR als JSON:\n"
            '{"facts": ["Fakt 1", "Fakt 2", ...], '
            '"key_quote": "wichtigstes Zitat (auf Deutsch)", '
            '"relevance": 8, '
            '"visual_description": "was ist visuell zu sehen (Grafiken, Demos, etc.)"}'
        )

        def _call() -> str:
            oc = OpenAI(api_key=_OPENROUTER_KEY, base_url=_OPENROUTER_BASE)
            resp = oc.chat.completions.create(
                model=_VIDEO_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "video_url", "video_url": {"url": video_url}},
                        {"type": "text", "text": prompt},
                    ],
                }],
                temperature=0.2,
                max_tokens=800,
            )
            return resp.choices[0].message.content or ""

        try:
            raw = await asyncio.to_thread(_call)
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                result = json.loads(m.group())
                logger.info(f"📺 Qwen-VL direkte Video-Analyse: {video_id} OK")
                return result
        except Exception as e:
            logger.warning(f"📺 Qwen-VL Video-Analyse fehlgeschlagen ({video_id}): {e} — Fallback auf Transkript")
        return {}

    async def _analyze_text(
        self,
        text: str,
        query: str,
        chunk_index: Optional[int] = None,
        total_chunks: Optional[int] = None,
    ) -> dict:
        """Fallback: Extrahiert Fakten aus dem Transkript via Text-LLM (DE + EN Inhalte)."""
        if not _OPENROUTER_KEY:
            logger.warning("OPENROUTER_API_KEY fehlt — Text-Analyse übersprungen")
            return {}

        cleaned_text = str(text or "").strip()
        if not cleaned_text:
            return {}
        excerpt = cleaned_text[:_TRANSCRIPT_ANALYSIS_INPUT_MAX]
        chunk_hint = (
            f"Dies ist Transcript-Teil {chunk_index} von {total_chunks}. "
            "Fokussiere dich nur auf Inhalte aus diesem Teil und erfinde keine Punkte aus anderen Abschnitten.\n"
            if chunk_index is not None and total_chunks is not None
            else ""
        )
        prompt = (
            f"Thema: {query}\n\n"
            f"{chunk_hint}"
            f"YouTube-Transkript (kann Deutsch oder Englisch sein):\n{excerpt}\n\n"
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
            parsed = extract_json_robust(raw)
            if isinstance(parsed, dict):
                return parsed
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
        video_description = str(visual_info.get("video_description", "")).strip()
        comment_highlights = visual_info.get("comment_highlights") or []

        if facts or key_quote:
            combined = "; ".join(facts[:5])
            if key_quote:
                combined += f' | Zitat: "{key_quote}"'
            if visual_desc:
                combined += f" | Bild: {visual_desc}"
            if video_description:
                combined += f" | Beschreibung: {video_description[:500]}"
            if comment_highlights:
                combined += f" | Kommentare: {' | '.join(comment_highlights[:2])}"

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

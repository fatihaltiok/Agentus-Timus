# tools/deep_research/trend_researcher.py
"""
TrendResearcher — analysiert wissenschaftliche und Open-Source-Trends für Deep Research v6.0.

Quellen:
- ArXiv          → Atom-XML-API (kostenlos, kein Key nötig)
- GitHub         → Search API (kostenlos, 60 req/h anonym; mit GITHUB_TOKEN: 5000 req/h)
- HuggingFace    → Models + Papers API (kostenlos, HF_TOKEN optional)
- Edison         → PaperQA3 via Edison Scientific Platform (ACHTUNG: 10 Credits/Monat!)

Alle Researcher folgen dem YouTubeResearcher-Pattern:
  research() → _fetch() → [_analyze() optional] → _add_to_session()
  → session.unverified_claims mit source_type="arxiv"/"github"/"huggingface"/"edison"
"""

import asyncio
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import List, Optional, TYPE_CHECKING

import httpx
from dotenv import load_dotenv
from openai import OpenAI

if TYPE_CHECKING:
    from tools.deep_research.tool import DeepResearchSession

load_dotenv()
logger = logging.getLogger("trend_researcher")

# --- Konfiguration ---
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
_ANALYSIS_MODEL = os.getenv("TREND_ANALYSIS_MODEL", "qwen/qwen3-235b-a22b")

# Mindest-Relevanzscore für ArXiv-Paper (0–10); Paper darunter werden verworfen
# v7.0: Default 6 → 5 (mehr ArXiv-Paper landen im Report)
# ENV: ARXIV_RELEVANCE_THRESHOLD — für strengere Filterung: 7 oder 8
_RELEVANCE_THRESHOLD = int(os.getenv("ARXIV_RELEVANCE_THRESHOLD", "5"))

_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
_HF_TOKEN = os.getenv("HF_TOKEN", "")
_EDISON_KEY = os.getenv("EDISON_API_KEY", "")

_HTTP_TIMEOUT = 30.0


# ==============================================================================
# ArXivResearcher
# ==============================================================================

class ArXivResearcher:
    """Sucht aktuelle wissenschaftliche Paper via ArXiv Atom-XML-API (keine Authentifizierung nötig)."""

    BASE_URL = "https://export.arxiv.org/api/query"
    _ARXIV_NS = "http://www.w3.org/2005/Atom"

    async def research(self, query: str, session: "DeepResearchSession", max_papers: int = 3) -> int:
        """
        Sucht Paper und fügt Kernaussagen als unverified_claims in die Session ein (v7.0).

        NEU: Mehr Kandidaten (25 statt 15), topic-aware Fallback-Score, Datum-Sortierung.

        Returns:
            Anzahl erfolgreich analysierter Paper
        """
        # v7.0: Max-Kandidaten erhöht von 15 → 25
        papers = await self._fetch_papers(query, max_results=max(max_papers + 2, 25))
        if not papers:
            logger.info("📄 ArXiv: Keine Paper gefunden")
            return 0

        # v7.0: Sekundäre Sortierung nach Datum (aktuellste bevorzugen)
        papers.sort(key=lambda p: p.get("published", ""), reverse=True)

        # Diagnostics
        try:
            from tools.deep_research.diagnostics import get_current
            diag = get_current()
            if diag is not None:
                diag.arxiv_fetched = len(papers)
                diag.arxiv_threshold = _RELEVANCE_THRESHOLD
        except Exception:
            pass

        query_words = set(query.lower().split())
        analyzed = 0
        skipped = 0
        for paper in papers:
            if analyzed >= max_papers:
                break
            try:
                analysis = await self._analyze_abstract(
                    paper["title"], paper["abstract"], query
                )
                relevance = analysis.get("relevance", 5)

                # v7.0: Topic-aware Fallback-Score statt fixem Score=5
                if relevance == 5:
                    title_words = set(paper["title"].lower().split())
                    overlap = len(query_words & title_words)
                    relevance = min(10, 5 + overlap)
                    analysis["relevance"] = relevance
                    logger.debug(
                        f"📄 ArXiv Fallback-Score: '{paper['title'][:40]}' "
                        f"overlap={overlap} → relevance={relevance}"
                    )

                if relevance < _RELEVANCE_THRESHOLD:
                    skipped += 1
                    logger.info(
                        f"📄 ArXiv: '{paper['title'][:50]}' verworfen "
                        f"(Relevanz {relevance}/10 < {_RELEVANCE_THRESHOLD})"
                    )
                    continue
                self._add_to_session(session, paper, analysis)
                analyzed += 1
                logger.info(
                    f"📄 ArXiv: '{paper['title'][:60]}' akzeptiert "
                    f"(Relevanz: {relevance}/10)"
                )
            except Exception as e:
                logger.warning(f"ArXiv-Paper übersprungen: {e}")

        if skipped > 0:
            logger.info(f"📄 ArXiv: {skipped} irrelevante Paper gefiltert")

        # Diagnostics
        try:
            from tools.deep_research.diagnostics import get_current
            diag = get_current()
            if diag is not None:
                diag.arxiv_accepted = analyzed
        except Exception:
            pass

        return analyzed

    async def _fetch_papers(self, query: str, max_results: int) -> List[dict]:
        """Ruft Paper via Atom-XML-API ab — sortiert nach Relevanz, nicht Datum (v7.0)."""
        params = {
            "search_query": f"ti:{query} OR abs:{query}",  # enger Suchbereich: nur Titel + Abstract
            "max_results": max(max_results + 5, 25),        # v7.0: mind. 25 Kandidaten
            "sortBy": "relevance",                           # relevanteste Paper zuerst
            "sortOrder": "descending",
        }
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                return self._parse_atom(resp.text)
        except Exception as e:
            logger.warning(f"ArXiv-Fetch fehlgeschlagen: {e}")
            return []

    def _parse_atom(self, xml_text: str) -> List[dict]:
        """Parst ArXiv Atom-XML und extrahiert relevante Felder."""
        papers = []
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": self._ARXIV_NS}
            for entry in root.findall("atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                summary_el = entry.find("atom:summary", ns)
                published_el = entry.find("atom:published", ns)
                id_el = entry.find("atom:id", ns)

                title = (title_el.text or "").strip().replace("\n", " ")
                abstract = (summary_el.text or "").strip().replace("\n", " ")
                published_raw = (published_el.text or "")[:10] if published_el is not None else ""
                arxiv_url = (id_el.text or "").strip()

                # ArXiv-ID aus URL extrahieren (z.B. http://arxiv.org/abs/2603.12345v1 → 2603.12345)
                arxiv_id = ""
                m = re.search(r"arxiv\.org/abs/([^\s/v]+)", arxiv_url)
                if m:
                    arxiv_id = m.group(1)

                # Autoren
                authors = []
                for author_el in entry.findall("atom:author", ns):
                    name_el = author_el.find("atom:name", ns)
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                if title and abstract and arxiv_id:
                    papers.append({
                        "title": title,
                        "abstract": abstract,
                        "published": published_raw,
                        "arxiv_id": arxiv_id,
                        "url": f"https://arxiv.org/abs/{arxiv_id}",
                        "authors": authors,
                    })
        except ET.ParseError as e:
            logger.warning(f"ArXiv XML-Parse-Fehler: {e}")
        return papers

    async def _analyze_abstract(self, title: str, abstract: str, query: str) -> dict:
        """
        Extrahiert Kernaussage aus Abstract via LLM (qwen3.5+ via OpenRouter).

        Falls kein OPENROUTER_KEY: Fallback auf ersten Satz des Abstracts.
        """
        if not _OPENROUTER_KEY:
            logger.debug("OPENROUTER_API_KEY fehlt — ArXiv-Analyse Fallback (keine Relevanzprüfung)")
            sentences = abstract.split(". ")
            key_finding = sentences[0][:300] if sentences else abstract[:300]
            # Ohne LLM keine Relevanzprüfung möglich → Threshold-Wert setzen damit Paper nicht blockiert werden
            return {"key_finding": key_finding, "relevance": _RELEVANCE_THRESHOLD, "abstract_summary": abstract[:300]}

        prompt = (
            f"Thema: {query}\n\n"
            f"Paper-Titel: {title}\n\n"
            f"Abstract:\n{abstract[:2000]}\n\n"
            "Bewerte die Relevanz dieses Papers für das Thema (0–10):\n"
            "  0 = völlig themenfremd | 5 = teilweise verwandt | 10 = exakt zum Thema\n"
            "Sei streng: Nur Papers die direkt zum Thema beitragen, erhalten ≥ 6.\n"
            "Extrahiere außerdem die wichtigste Kernaussage bezogen auf das Thema.\n"
            "Antworte NUR als JSON (keine weiteren Erklärungen):\n"
            '{"key_finding": "...", "abstract_summary": "...", "relevance": <0-10>}'
        )

        def _call() -> str:
            oc = OpenAI(api_key=_OPENROUTER_KEY, base_url=_OPENROUTER_BASE)
            resp = oc.chat.completions.create(
                model=_ANALYSIS_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=400,
            )
            return resp.choices[0].message.content or ""

        try:
            raw = await asyncio.to_thread(_call)
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logger.warning(f"ArXiv-Abstrakt-Analyse fehlgeschlagen: {e}")

        # Fallback
        sentences = abstract.split(". ")
        return {
            "key_finding": sentences[0][:300] if sentences else abstract[:300],
            "relevance": 5,
            "abstract_summary": abstract[:300],
        }

    def _add_to_session(self, session: "DeepResearchSession", paper: dict, analysis: dict) -> None:
        """Fügt Paper-Fakten als unverified_claims in die Session ein."""
        key_finding = analysis.get("key_finding", paper["abstract"][:300])
        relevance = analysis.get("relevance", 5)
        abstract_summary = analysis.get("abstract_summary", paper["abstract"][:300])
        authors_str = ", ".join(paper["authors"][:3])
        if len(paper["authors"]) > 3:
            authors_str += " et al."

        session.unverified_claims.append({
            "fact": (
                f"ArXiv-Paper: '{paper['title']}' ({paper['published']}). "
                f"Kernaussage: {key_finding}"
            ),
            "source": paper["url"],
            "source_title": paper["title"],
            "source_type": "arxiv",
            "authors": authors_str,
            "published_date": paper["published"],
            "arxiv_id": paper["arxiv_id"],
            "abstract_summary": abstract_summary,
            "relevance": relevance,
        })


# ==============================================================================
# GitHubTrendingResearcher
# ==============================================================================

class GitHubTrendingResearcher:
    """Sucht relevante GitHub-Repositories via GitHub Search API."""

    SEARCH_URL = "https://api.github.com/search/repositories"

    async def research(self, query: str, session: "DeepResearchSession", max_repos: int = 3) -> int:
        """
        Sucht Top-Repositories und fügt sie als unverified_claims ein.

        Returns:
            Anzahl hinzugefügter Repositories
        """
        repos = await self._fetch_repos(query, max_results=max(max_repos + 2, 5))
        if not repos:
            logger.info("🐙 GitHub: Keine Repositories gefunden")
            return 0

        added = 0
        for repo in repos[:max_repos]:
            self._add_to_session(session, repo)
            added += 1
            logger.info(
                f"🐙 GitHub: '{repo['full_name']}' ({repo['stars']:,}★) hinzugefügt"
            )

        return added

    async def _fetch_repos(self, query: str, max_results: int) -> List[dict]:
        """Ruft Repositories via GitHub Search API ab."""
        params = {
            "q": f"{query} in:name,description,readme",
            "sort": "stars",
            "order": "desc",
            "per_page": max_results,
        }
        headers = {"Accept": "application/vnd.github+json"}
        if _GITHUB_TOKEN:
            headers["Authorization"] = f"token {_GITHUB_TOKEN}"

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(self.SEARCH_URL, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return self._parse_repos(data.get("items", []))
        except Exception as e:
            logger.warning(f"GitHub-Fetch fehlgeschlagen: {e}")
            return []

    def _parse_repos(self, items: list) -> List[dict]:
        """Extrahiert relevante Felder aus der GitHub API-Antwort."""
        repos = []
        for item in items:
            repos.append({
                "full_name": item.get("full_name", ""),
                "name": item.get("name", ""),
                "description": (item.get("description") or "")[:400],
                "stars": item.get("stargazers_count", 0),
                "language": item.get("language") or "Unbekannt",
                "topics": item.get("topics", [])[:5],
                "url": item.get("html_url", ""),
                "updated_at": (item.get("updated_at") or "")[:10],
            })
        return repos

    def _add_to_session(self, session: "DeepResearchSession", repo: dict) -> None:
        """Fügt Repository als unverified_claim ein."""
        name = repo["full_name"]
        stars = repo["stars"]
        language = repo["language"]
        desc = repo["description"][:200] if repo["description"] else "Keine Beschreibung verfügbar"

        session.unverified_claims.append({
            "fact": f"GitHub-Projekt: '{name}' ({stars:,}★, {language}). {desc}",
            "source": repo["url"],
            "source_title": repo["name"],
            "source_type": "github",
            "full_name": name,
            "stars": stars,
            "language": language,
            "topics": repo["topics"],
            "updated_at": repo["updated_at"],
        })


# ==============================================================================
# HuggingFaceResearcher
# ==============================================================================

class HuggingFaceResearcher:
    """Sucht relevante KI-Modelle und Daily Papers auf HuggingFace."""

    MODELS_URL = "https://huggingface.co/api/models"
    PAPERS_URL = "https://huggingface.co/api/papers"

    async def research(self, query: str, session: "DeepResearchSession", max_items: int = 3) -> int:
        """
        Sucht Modelle und Papers parallel und fügt sie als unverified_claims ein.

        Returns:
            Gesamtanzahl hinzugefügter Einträge
        """
        models_task = self._fetch_models(query, limit=max_items)
        papers_task = self._fetch_papers(query)

        models, papers = await asyncio.gather(models_task, papers_task, return_exceptions=True)

        added = 0
        if isinstance(models, list):
            for model in models[:max(1, max_items // 2 + 1)]:
                self._add_model_to_session(session, model)
                added += 1
                logger.info(f"🤗 HuggingFace-Modell: '{model['id']}' hinzugefügt")
        else:
            logger.warning(f"HF Models-Fetch fehlgeschlagen: {models}")

        if isinstance(papers, list):
            for paper in papers[:max(1, max_items // 2)]:
                self._add_paper_to_session(session, paper)
                added += 1
                logger.info(f"🤗 HuggingFace-Paper: '{paper.get('title', '')[:60]}' hinzugefügt")
        else:
            logger.warning(f"HF Papers-Fetch fehlgeschlagen: {papers}")

        if added == 0:
            logger.info("🤗 HuggingFace: Keine Einträge gefunden")

        return added

    async def _fetch_models(self, query: str, limit: int) -> List[dict]:
        """Ruft Top-Modelle via HF Models API ab."""
        params = {
            "search": query,
            "sort": "downloads",
            "limit": limit + 3,
            "full": "false",
        }
        headers = {}
        if _HF_TOKEN:
            headers["Authorization"] = f"Bearer {_HF_TOKEN}"

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(self.MODELS_URL, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list):
                    return []
                return [
                    {
                        "id": m.get("id", ""),
                        "downloads": m.get("downloads", 0),
                        "likes": m.get("likes", 0),
                        "pipeline_tag": m.get("pipeline_tag", ""),
                        "tags": (m.get("tags") or [])[:5],
                        "url": f"https://huggingface.co/{m.get('id', '')}",
                    }
                    for m in data
                    if m.get("id")
                ]
        except Exception as e:
            logger.warning(f"HF-Models-Fetch fehlgeschlagen: {e}")
            return []

    async def _fetch_papers(self, query: str) -> List[dict]:
        """Ruft aktuelle HF Daily Papers ab."""
        params = {"q": query}
        headers = {}
        if _HF_TOKEN:
            headers["Authorization"] = f"Bearer {_HF_TOKEN}"

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(self.PAPERS_URL, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                # API gibt entweder Liste oder {"papers": [...]}
                if isinstance(data, list):
                    papers_raw = data
                elif isinstance(data, dict):
                    papers_raw = data.get("papers", [])
                else:
                    return []

                return [
                    {
                        "title": p.get("title", ""),
                        "abstract": (p.get("summary") or p.get("abstract") or "")[:500],
                        "arxiv_id": p.get("id", ""),
                        "url": f"https://huggingface.co/papers/{p.get('id', '')}",
                        "upvotes": p.get("upvotes", 0),
                    }
                    for p in papers_raw
                    if p.get("title")
                ]
        except Exception as e:
            logger.warning(f"HF-Papers-Fetch fehlgeschlagen: {e}")
            return []

    def _add_model_to_session(self, session: "DeepResearchSession", model: dict) -> None:
        """Fügt HF-Modell als unverified_claim ein."""
        model_id = model["id"]
        downloads = model["downloads"]
        pipeline = model["pipeline_tag"] or "general"
        tags_str = ", ".join(model["tags"][:4]) if model["tags"] else ""

        fact = f"HuggingFace-Modell: '{model_id}' ({downloads:,} Downloads, Task: {pipeline})."
        if tags_str:
            fact += f" Tags: {tags_str}."

        session.unverified_claims.append({
            "fact": fact,
            "source": model["url"],
            "source_title": model_id,
            "source_type": "huggingface",
            "hf_type": "model",
            "downloads": downloads,
            "likes": model["likes"],
            "pipeline_tag": pipeline,
            "tags": model["tags"],
        })

    def _add_paper_to_session(self, session: "DeepResearchSession", paper: dict) -> None:
        """Fügt HF Daily Paper als unverified_claim ein."""
        title = paper["title"]
        abstract = paper["abstract"]
        upvotes = paper["upvotes"]

        fact = f"HuggingFace Daily Paper: '{title}'."
        if abstract:
            fact += f" {abstract[:200]}"

        session.unverified_claims.append({
            "fact": fact,
            "source": paper["url"],
            "source_title": title,
            "source_type": "huggingface",
            "hf_type": "paper",
            "upvotes": upvotes,
            "arxiv_id": paper["arxiv_id"],
        })


# ==============================================================================
# EdisonResearcher
# ==============================================================================

class EdisonResearcher:
    """
    PaperQA3-basierte wissenschaftliche Literatursuche via Edison Scientific Platform.

    ACHTUNG: Kostenloser Plan = 10 Credits/Monat!
    Standardmäßig DEAKTIVIERT via DEEP_RESEARCH_EDISON_ENABLED=false.
    Nur manuell aktivieren wenn explizit wissenschaftliche Literatur gewünscht.
    """

    async def research(self, query: str, session: "DeepResearchSession", max_items: int = 1) -> int:
        """
        Führt eine PaperQA3 Literatursuche via Edison durch.

        Returns:
            1 wenn erfolgreich, 0 sonst
        """
        if not _EDISON_KEY:
            logger.debug("EDISON_API_KEY nicht gesetzt — Edison übersprungen")
            return 0

        try:
            from edison_client import EdisonClient, JobNames  # type: ignore[import]
        except ImportError:
            logger.warning("edison-client nicht installiert (pip install edison-client)")
            return 0

        try:
            client = EdisonClient(api_key=_EDISON_KEY)
            task_data = {
                "name": JobNames.LITERATURE,
                "query": query,
                "runtime_config": {"timeout": 180, "max_steps": 20},
            }
            logger.info(f"🔬 Edison: Starte PaperQA3-Suche für '{query[:60]}'...")
            response = await asyncio.to_thread(client.run_tasks_until_done, task_data)
            self._add_to_session(session, response)
            logger.info("🔬 Edison: Literatursuche abgeschlossen")
            return 1
        except Exception as e:
            logger.warning(f"Edison-Recherche fehlgeschlagen: {e}")
            return 0

    def _add_to_session(self, session: "DeepResearchSession", response) -> None:
        """Fügt Edison-Ergebnis als unverified_claim ein."""
        try:
            answer = getattr(response, "answer", "") or ""
            formatted_answer = getattr(response, "formatted_answer", "") or ""
            has_successful = getattr(response, "has_successful_answer", False)

            session.unverified_claims.append({
                "fact": f"Edison Scientific (PaperQA3): {answer[:500]}",
                "source": "https://platform.edisonscientific.com",
                "source_title": "Edison Literature Search",
                "source_type": "edison",
                "formatted_answer": formatted_answer,
                "has_successful_answer": has_successful,
            })
        except Exception as e:
            logger.warning(f"Edison-Session-Eintrag fehlgeschlagen: {e}")


# ==============================================================================
# TrendResearcher (Orchestrator)
# ==============================================================================

class TrendResearcher:
    """
    Orchestriert ArXiv, GitHub, HuggingFace und Edison parallel.

    Alle Fehler werden intern abgefangen — kein Fehler bricht den Gesamt-Workflow ab.
    Edison wird nur ausgeführt wenn DEEP_RESEARCH_EDISON_ENABLED=true gesetzt ist.
    """

    async def research_trends(
        self,
        query: str,
        session: "DeepResearchSession",
        max_per_source: int = 3,
    ) -> int:
        """
        Führt alle Trend-Recherchen parallel aus.

        Args:
            query: Recherche-Thema (wird automatisch ins Englische übersetzt)
            session: Laufende DeepResearchSession (in-place erweitert)
            max_per_source: Max. Einträge pro Quelle

        Returns:
            Gesamtanzahl hinzugefügter Einträge
        """
        # ArXiv, GitHub und HuggingFace sind englischsprachige APIs —
        # deutsche/nicht-englische Queries werden übersetzt
        api_query = await self._translate_query_for_apis(query)

        tasks = []
        if os.getenv("DEEP_RESEARCH_ARXIV_ENABLED", "true").lower() != "false":
            tasks.append(self._run_safe(
                ArXivResearcher().research(api_query, session, max_per_source),
                "ArXiv",
            ))
        if os.getenv("DEEP_RESEARCH_GITHUB_ENABLED", "true").lower() != "false":
            tasks.append(self._run_safe(
                GitHubTrendingResearcher().research(api_query, session, max_per_source),
                "GitHub",
            ))
        if os.getenv("DEEP_RESEARCH_HF_ENABLED", "true").lower() != "false":
            tasks.append(self._run_safe(
                HuggingFaceResearcher().research(api_query, session, max_per_source),
                "HuggingFace",
            ))

        # Edison nur wenn explizit aktiviert (10 Credits/Monat Limit!)
        if os.getenv("DEEP_RESEARCH_EDISON_ENABLED", "false").lower() == "true":
            tasks.append(self._run_safe(
                EdisonResearcher().research(query, session),
                "Edison",
            ))

        results = await asyncio.gather(*tasks)
        total = sum(r for r in results if isinstance(r, int))
        logger.info(f"📊 Trend-Recherche abgeschlossen: {total} Einträge aus {len(tasks)} Quellen")
        return total

    async def _translate_query_for_apis(self, query: str) -> str:
        """
        Übersetzt nicht-englische Queries ins Englische für ArXiv/GitHub/HuggingFace.

        Heuristik: Deutsche Sonderzeichen oder häufige deutsche Wörter → übersetzen.
        Ohne OPENROUTER_KEY: Query unverändert zurückgeben.
        """
        if not _OPENROUTER_KEY:
            return query

        # Schnelle Heuristik für deutschen Text
        german_indicators = (
            any(c in query for c in "äöüÄÖÜß")
            or any(
                f" {w} " in f" {query.lower()} "
                for w in ("und", "der", "die", "das", "von", "für", "über", "mit",
                          "auf", "bei", "nach", "aus", "ein", "eine", "ist")
            )
        )
        if not german_indicators:
            return query

        def _call() -> str:
            oc = OpenAI(api_key=_OPENROUTER_KEY, base_url=_OPENROUTER_BASE)
            resp = oc.chat.completions.create(
                model=_ANALYSIS_MODEL,
                messages=[{
                    "role": "user",
                    "content": (
                        "Translate this search query to English for academic paper search. "
                        "Reply ONLY with the translated query, nothing else:\n"
                        f"{query}"
                    ),
                }],
                temperature=0.1,
                max_tokens=100,
            )
            return (resp.choices[0].message.content or "").strip()

        try:
            translated = await asyncio.to_thread(_call)
            if translated and 3 < len(translated) < 500:
                logger.info(
                    f"🌐 Query übersetzt: '{query[:40]}' → '{translated[:40]}'"
                )
                return translated
        except Exception as e:
            logger.debug(f"Query-Übersetzung fehlgeschlagen: {e}")

        return query

    async def _run_safe(self, coro, source_name: str = "") -> int:
        """Führt eine Coroutine aus und fängt alle Fehler ab (gibt 0 zurück)."""
        try:
            return await coro
        except Exception as e:
            logger.warning(f"Trend-Researcher '{source_name}' Fehler (unkritisch): {e}")
            return 0

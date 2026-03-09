"""
orchestration/curiosity_engine.py — Curiosity Engine v2.8

Timus wacht in unregelmäßigen Abständen auf, extrahiert dominante Themen
aus den letzten 72h, sucht eigenständig nach neuen Informationen und
schreibt den User proaktiv per Telegram an — aber nur wenn die Information
wirklich überraschend ist (Gatekeeper-Filter).

ENV-Variablen:
  CURIOSITY_ENABLED=true
  CURIOSITY_MIN_HOURS=3      # Frühestes Aufwachen
  CURIOSITY_MAX_HOURS=14     # Spätestes Aufwachen
  CURIOSITY_GATEKEEPER_MIN=7 # Score-Schwelle (1-10)
  CURIOSITY_MAX_PER_DAY=2    # Anti-Spam: max. N Nachrichten pro Tag

AUTOR: Timus Development
DATUM: 2026-02-25
"""

import asyncio
import json
import logging
import os
import random
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("CuriosityEngine")

MEMORY_DB_PATH = Path.home() / "dev" / "timus" / "data" / "timus_memory.db"

# ENV-Konfiguration
CURIOSITY_ENABLED = os.getenv("CURIOSITY_ENABLED", "true").lower() == "true"
CURIOSITY_MIN_HOURS = int(os.getenv("CURIOSITY_MIN_HOURS", "3"))
CURIOSITY_MAX_HOURS = int(os.getenv("CURIOSITY_MAX_HOURS", "14"))
GATEKEEPER_MIN = int(os.getenv("CURIOSITY_GATEKEEPER_MIN", "7"))
MAX_PER_DAY = int(os.getenv("CURIOSITY_MAX_PER_DAY", "2"))

# Stopwörter für Topic-Extraktion
_STOPWORDS = {
    # Artikel, Pronomen, Konjunktionen (DE)
    "und", "oder", "aber", "eine", "einer", "einem", "einen", "der", "die",
    "das", "den", "dem", "dass", "ich", "du", "wir", "sie", "es", "ein",
    "auf", "mit", "von", "zu", "in", "an", "bei", "für", "aus", "nach",
    "über", "unter", "vor", "als", "wie", "wenn", "dann", "also", "noch",
    "auch", "schon", "nur", "ja", "nein", "ok", "bitte", "kein", "keine",
    "keinen", "diesem", "dieser", "dieses", "jetzt", "hier", "dort", "mal",
    "sehr", "mehr", "jetzt", "immer", "nicht", "kann", "wird", "wird",
    "sein", "beim", "beim", "habe", "haben", "hatte", "hatten", "worden",
    # Verbformen (DE) — häufig in Gesprächen extrahiert
    "läuft", "laufen", "steht", "stehen", "geht", "gehen", "macht", "machen",
    "sehen", "schau", "schaut", "lesen", "lies", "liest", "schreib", "schreibt",
    "sagst", "sagen", "sagst", "zeigt", "zeigen", "prüfe", "prüft", "prüfen",
    "teste", "testet", "testen", "starte", "startet", "starten", "stoppe",
    "kannst", "könnte", "könnten", "sollte", "sollten", "müsste", "dürfte",
    "warte", "warten", "suche", "suchen", "finde", "finden", "öffne", "öffnen",
    "erstell", "erstelle", "erstellen", "änder", "ändere", "ändern", "schick",
    "schicke", "schicken", "zeige", "zeigen", "nehme", "nehmen", "geben",
    # Kurzwörter und Gesprächsfüller (DE/EN)
    "bitte", "danke", "okay", "alles", "etwas", "einfach", "kurz", "genau",
    "richtig", "falsch", "stimmt", "passt", "klar", "super", "gut", "schlecht",
    "toll", "cool", "nice", "sure", "yes", "yep", "nope", "hmm", "aha",
    # Artikel, Pronomen, Hilfswörter (EN)
    "the", "a", "an", "is", "are", "was", "be", "to", "of", "and", "in",
    "it", "for", "on", "with", "at", "by", "this", "that", "have", "has",
    "not", "do", "can", "will", "from", "or", "but", "what", "how",
    "just", "also", "now", "here", "there", "then", "than", "when", "if",
    "so", "me", "my", "we", "he", "she", "they", "you", "your", "its",
    "been", "had", "did", "get", "got", "let", "make", "use", "see",
}


class CuriosityEngine:
    """
    Autonome Wissensdurchsuchung mit Gatekeeper-Filter.

    - Fuzzy Heartbeat: alle 3-14h (konfigurierbar)
    - Topic-Extraktion: letzte 72h aus SQLite + Session
    - Serendipity-Suche: LLM generiert Edge-Query
    - Gatekeeper: nur wirklich neue/überraschende Artikel (Score >= 7)
    - Telegram-Push mit Soul-Engine-Ton
    """

    def __init__(self, telegram_app: Any = None):
        """
        Args:
            telegram_app: Telegram Application-Objekt (mit .bot.send_message).
                         Kann auch None sein — dann wird Bot direkt instanziiert.
        """
        self._app = telegram_app
        self._running = False
        # M16: Topic-Scores für adaptive Auswahl (feedback-gewichtet)
        self._topic_scores: Dict[str, float] = {}
        self._topic_last_feedback: Dict[str, str] = {}  # topic → ISO timestamp

    # ---------------------------------------------------------------
    # Fuzzy Loop
    # ---------------------------------------------------------------

    async def _curiosity_loop(self) -> None:
        """Hauptloop: schläft, wacht auf, führt Zyklus aus."""
        self._running = True
        log.info("🔍 Curiosity Engine gestartet")

        while self._running:
            min_minutes = CURIOSITY_MIN_HOURS * 60
            max_minutes = CURIOSITY_MAX_HOURS * 60
            # Fallback falls MIN >= MAX
            if min_minutes >= max_minutes:
                minutes = min_minutes
            else:
                minutes = random.randint(min_minutes, max_minutes)

            log.info("Curiosity schläft %d min (%.1fh)", minutes, minutes / 60)
            try:
                await asyncio.sleep(minutes * 60)
            except asyncio.CancelledError:
                break

            if not self._running:
                break

            try:
                await self._run_curiosity_cycle()
            except Exception as e:
                log.error("Curiosity-Zyklus fehlgeschlagen: %s", e, exc_info=True)

    def stop(self) -> None:
        self._running = False

    # ---------------------------------------------------------------
    # Haupt-Zyklus
    # ---------------------------------------------------------------

    async def _run_curiosity_cycle(self) -> Optional[str]:
        """
        Führt einen vollständigen Curiosity-Zyklus durch:
        1. Topics extrahieren
        2. Suchanfrage generieren
        3. Suchen + Gatekeeper
        4. Telegram pushen

        Returns:
            Status-String für Tests/Logs.
        """
        if not CURIOSITY_ENABLED:
            log.debug("Curiosity Engine deaktiviert")
            return "disabled"

        # Tagesgrenze prüfen
        if self._is_daily_limit_reached():
            log.info("Curiosity: Tageslimit erreicht (%d/Tag), kein Push", MAX_PER_DAY)
            return "daily_limit"

        # Topics extrahieren
        topics = self._extract_topics()
        if not topics:
            log.info("Curiosity: Keine Topics gefunden")
            return "no_topics"

        log.info("Curiosity: Topics extrahiert: %s", topics)

        # Suchanfrage via LLM generieren
        try:
            query = await self._generate_search_query(topics)
        except Exception as e:
            log.warning("Curiosity: Suchanfrage-Generierung fehlgeschlagen: %s", e)
            return "query_error"

        if not query or len(query) < 5:
            log.info("Curiosity: Leere Suchanfrage, überspringe")
            return "empty_query"

        log.info("Curiosity: Suchanfrage = %r", query)

        # Suchen + Gatekeeper
        try:
            result = await self._search_and_gate(query, topics)
        except Exception as e:
            log.warning("Curiosity: Suche fehlgeschlagen: %s", e)
            return "search_error"

        if not result:
            log.info("Curiosity: Kein Ergebnis den Gatekeeper passiert (Score < %d)", GATEKEEPER_MIN)
            return "gatekeeper_blocked"

        # Duplikat prüfen
        if self._is_duplicate(result["url"]):
            log.info("Curiosity: URL bereits gesendet (Duplikat-Schutz)")
            return "duplicate"

        # Telegram-Push
        try:
            message = await self._push_telegram(result, topics)
        except Exception as e:
            log.warning("Curiosity: Telegram-Push fehlgeschlagen: %s", e)
            return "telegram_error"

        # In DB loggen
        self._log_sent(
            topic=", ".join(topics[:3]),
            url=result["url"],
            title=result.get("title", ""),
            score=result.get("score", 0),
        )

        # In Memory-System loggen
        try:
            from memory.memory_system import memory_manager
            memory_manager.log_interaction_event(
                agent_name="curiosity",
                user_input=f"[Curiosity-Thema] {', '.join(topics[:3])}",
                assistant_response=message or "",
            )
        except Exception as e:
            log.debug("Curiosity: Memory-Logging fehlgeschlagen: %s", e)

        log.info("✅ Curiosity Push gesendet: %s", result.get("title", "?"))
        return "sent"

    # ---------------------------------------------------------------
    # Topic-Extraktion
    # ---------------------------------------------------------------

    def _extract_topics(self) -> List[str]:
        """
        Extrahiert Top-3 Themen aus:
        1. Session-Kurzzeit (get_dynamic_state)
        2. DB-Langzeit (letzte 72h Interaction Events)
        """
        topics_combined: Counter = Counter()

        # Quelle 1: Session
        try:
            from memory.memory_system import memory_manager
            state = memory_manager.session.get_dynamic_state()
            for topic in state.get("top_topics", []):
                if topic and topic.lower() not in _STOPWORDS and len(topic) >= 5:
                    topics_combined[topic.lower()] += 3  # Session-Boost
        except Exception as e:
            log.debug("Session-Topics fehlgeschlagen: %s", e)

        # Quelle 2: Datenbank 72h
        try:
            cutoff = (datetime.now() - timedelta(hours=72)).isoformat()
            with sqlite3.connect(MEMORY_DB_PATH) as con:
                rows = con.execute(
                    "SELECT user_input FROM interaction_events WHERE created_at >= ? LIMIT 200",
                    (cutoff,),
                ).fetchall()

            from memory.memory_system import memory_manager
            for row in rows:
                text = row[0] or ""
                terms = memory_manager.session._extract_topic_terms(text)
                for term in terms:
                    if term and len(term) >= 5 and term.lower() not in _STOPWORDS:
                        topics_combined[term.lower()] += 1
        except Exception as e:
            log.debug("DB-Topics fehlgeschlagen: %s", e)

        # M16: Topic-Scores mit Feedback-Gewichtung kombinieren
        self._decay_stale_topic_scores()
        weighted: Counter = Counter()
        for topic, base_count in topics_combined.items():
            feedback_boost = self.get_topic_score(topic)
            weighted[topic] = int(base_count * feedback_boost)

        # Top-3 zurückgeben
        return [topic for topic, _ in (weighted if weighted else topics_combined).most_common(3)]

    # ---------------------------------------------------------------
    # Suchanfrage via LLM
    # ---------------------------------------------------------------

    async def _generate_search_query(self, topics: List[str]) -> str:
        """
        Generiert eine Edge-Suchanfrage via LLM.
        Gibt den Query-String zurück.
        """
        topics_str = ", ".join(topics) if topics else "KI, Agenten, Python"

        prompt = (
            f"Du bist Timus. Fatih beschäftigt sich gerade mit: [{topics_str}].\n\n"
            "Erstelle EINE präzise Google-Suchanfrage, die eine völlig neue, unerwartete "
            "oder hochaktuelle Information, ein Tool oder einen Artikel findet — kein Basics-"
            "Tutorial, sondern den 'Edge': neue Releases, unbekannte Libraries, Forschungs-"
            "ergebnisse, Gegenthesen oder überraschende Anwendungsfälle aus 2026.\n\n"
            "Antworte NUR als JSON: {\"query\": \"...\"}"
        )

        raw = await self._llm_call(prompt, max_tokens=100, temperature=0.8)
        if not raw:
            # Fallback: einfache Suchanfrage aus Topics
            return f"{topics[0]} 2026 neue Entwicklungen" if topics else ""

        # JSON parsen
        try:
            raw_clean = raw.strip()
            if raw_clean.startswith("```"):
                raw_clean = re.sub(r"```[a-z]*\n?", "", raw_clean).replace("```", "").strip()
            data = json.loads(raw_clean)
            return str(data.get("query", "")).strip()
        except Exception:
            # Fallback: Query direkt extrahieren
            m = re.search(r'"query"\s*:\s*"([^"]+)"', raw)
            if m:
                return m.group(1).strip()
            return raw.strip()[:200]

    # ---------------------------------------------------------------
    # Suche + Gatekeeper
    # ---------------------------------------------------------------

    async def _search_and_gate(
        self, query: str, topics: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Sucht via DataForSEO und bewertet Top-3 Ergebnisse.
        Gibt den Artikel zurück, der den Gatekeeper passiert hat — oder None.
        """
        # Suche
        try:
            from tools.search_tool.tool import _search_sync
            results = await asyncio.to_thread(
                _search_sync,
                query,
                engine="google",
                vertical="organic",
                max_results=5,
                language_code="de",
                location_code=2276,
                device="desktop",
            )
        except Exception as e:
            log.warning("DataForSEO-Suche fehlgeschlagen: %s", e)
            return None

        if not results:
            log.debug("Curiosity: Keine Suchergebnisse für %r", query)
            return None

        # Top-3 bewerten
        topic_str = ", ".join(topics[:3]) if topics else "KI"
        best_result = None
        best_score = 0

        for item in results[:3]:
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
            url = item.get("url", item.get("link", ""))

            if not url:
                continue

            # Duplikat-Vorprüfung
            if self._is_duplicate(url):
                log.debug("Curiosity: %r bereits gesendet, überspringe", url)
                continue

            score_data = await self._gatekeeper_score(title, snippet, url, topic_str)
            score = score_data.get("score", 0)
            log.debug("Gatekeeper: Score=%d für %r", score, title[:60])

            if score >= GATEKEEPER_MIN and score > best_score:
                best_score = score
                best_result = {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "score": score,
                    "reason": score_data.get("reason", ""),
                }

        return best_result

    async def _gatekeeper_score(
        self, title: str, snippet: str, url: str, topic: str
    ) -> Dict[str, Any]:
        """Bewertet einen Artikel via LLM. Gibt {'score': int, 'reason': str} zurück."""
        prompt = (
            f"Bewerte folgenden Artikel für jemanden, der sich gut mit [{topic}] auskennt.\n\n"
            f"Titel: {title}\n"
            f"Snippet: {snippet}\n"
            f"URL: {url}\n\n"
            "Kriterien (je 0-10):\n"
            "- Überraschungswert: Ist das wirklich neu/unbekannt?\n"
            "- Tiefe: Kein Tutorial/Basics?\n"
            "- Aktualität: < 30 Tage bevorzugt?\n"
            f"- Relevanz zu [{topic}]?\n\n"
            'Antworte als JSON: {"score": 7, "reason": "kurze Begründung"}\n'
            "Vergib score < 7 wenn der Inhalt bekannt, oberflächlich oder veraltet ist."
        )

        raw = await self._llm_call(prompt, max_tokens=100, temperature=0.2)
        if not raw:
            return {"score": 0, "reason": "LLM-Fehler"}

        try:
            raw_clean = raw.strip()
            if raw_clean.startswith("```"):
                raw_clean = re.sub(r"```[a-z]*\n?", "", raw_clean).replace("```", "").strip()
            data = json.loads(raw_clean)
            return {
                "score": int(data.get("score", 0)),
                "reason": str(data.get("reason", "")),
            }
        except Exception:
            m = re.search(r'"score"\s*:\s*(\d+)', raw)
            if m:
                return {"score": int(m.group(1)), "reason": ""}
            return {"score": 0, "reason": "Parse-Fehler"}

    # ---------------------------------------------------------------
    # Telegram Push
    # ---------------------------------------------------------------

    async def _push_telegram(
        self, result: Dict[str, Any], topics: List[str]
    ) -> Optional[str]:
        """
        Formuliert und sendet eine Telegram-Nachricht mit Soul-Engine-Ton.
        Gibt den gesendeten Text zurück.
        """
        # Soul-Ton bestimmen
        try:
            from memory.soul_engine import get_soul_engine
            tone_config = get_soul_engine().get_tone_config()
            tone = tone_config["tone"]
            intro_hint = tone_config["intro_hint"]
        except Exception:
            tone = "neutral"
            intro_hint = "Hey, ich bin gerade auf etwas gestoßen..."

        topic_str = ", ".join(topics[:2]) if topics else "KI"

        # Nachricht via LLM formulieren
        msg_prompt = (
            f"Du bist Timus, ein KI-Assistent. Dein aktueller Ton ist: {tone}.\n"
            f"Typischer Einstiegssatz für diesen Ton: '{intro_hint}'\n\n"
            f"Thema: {topic_str}\n"
            f"Titel: {result.get('title', '')}\n"
            f"Snippet: {result.get('snippet', '')}\n"
            f"URL: {result.get('url', '')}\n"
            f"Gatekeeper-Begründung: {result.get('reason', '')}\n\n"
            "Formuliere eine kurze, prägnante Telegram-Nachricht (~4-5 Zeilen) im Timus-Stil.\n"
            "Nutze Markdown (kein HTML). Format:\n"
            "[Timus-Intro im passenden Ton]\n\n"
            "📌 *[Titel]*\n"
            "[Snippet — 1-2 Sätze, das Wichtigste]\n"
            "🔗 [URL]\n\n"
            "Antworte NUR mit der fertig formatierten Nachricht."
        )

        raw_msg = await self._llm_call(msg_prompt, max_tokens=300, temperature=0.7)

        if not raw_msg:
            # Fallback: direkte Formatierung
            raw_msg = (
                f"{intro_hint}\n\n"
                f"📌 *{result.get('title', 'Kein Titel')}*\n"
                f"{result.get('snippet', '')[:200]}\n"
                f"🔗 {result.get('url', '')}"
            )

        # Telegram senden (M16: mit Feedback-Buttons)
        action_id = result.get("url", "") or str(id(result))
        try:
            from utils.telegram_notify import send_with_feedback
            await send_with_feedback(
                raw_msg,
                action_id=action_id,
                hook_names=["curiosity_push", topics[0] if topics else "curiosity"],
                context={
                    "source": "curiosity_push",
                    "topic": topics[0] if topics else "curiosity",
                    "url": result.get("url", ""),
                    "title": result.get("title", "")[:160],
                },
                feedback_targets=[
                    {"namespace": "curiosity_topic", "key": topics[0] if topics else "curiosity"},
                ],
            )
            log.info("Curiosity: Telegram-Nachricht mit Feedback-Buttons gesendet")
        except Exception as e:
            log.warning("Curiosity: Telegram-Push fehlgeschlagen: %s", e)

        return raw_msg

    # ---------------------------------------------------------------
    # M16: Topic-Score Management (Feedback-adaptive)
    # ---------------------------------------------------------------

    def update_topic_score(self, topic: str, signal: str) -> None:
        """
        Aktualisiert den Score eines Topics basierend auf Feedback.

        positive → score += 0.1
        negative → score -= 0.1
        neutral  → kein Effekt

        Score wird in [0.1, 3.0] geclamped.

        post[self._topic_scores]: not (topic in self._topic_scores) or (0.1 <= self._topic_scores.get(topic, 1.0) <= 3.0)
        """
        if signal not in {"positive", "negative", "neutral"}:
            return

        current = self._topic_scores.get(topic, 1.0)
        if signal == "positive":
            self._topic_scores[topic] = max(0.1, min(3.0, current + 0.1))
        elif signal == "negative":
            self._topic_scores[topic] = max(0.1, min(3.0, current - 0.1))

        self._topic_last_feedback[topic] = datetime.now().isoformat()

    def get_topic_score(self, topic: str) -> float:
        """Gibt den aktuellen Score eines Topics zurück (default: 1.0)."""
        local_score = self._topic_scores.get(topic, 1.0)
        try:
            from orchestration.feedback_engine import get_feedback_engine

            target_score = get_feedback_engine().get_effective_target_score("curiosity_topic", topic, default=1.0)
        except Exception:
            target_score = 1.0
        return max(0.1, min(3.0, local_score * target_score))

    def _decay_stale_topic_scores(self) -> None:
        """
        Reduziert Scores für Topics ohne Feedback seit > 7 Tagen.
        Score × 0.9 (Richtung 1.0).
        """
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        for topic in list(self._topic_scores.keys()):
            last_fb = self._topic_last_feedback.get(topic)
            if last_fb and last_fb < cutoff:
                current = self._topic_scores[topic]
                if current > 1.0:
                    self._topic_scores[topic] = max(1.0, current * 0.9)
                elif current < 1.0:
                    self._topic_scores[topic] = min(1.0, current / 0.9)

    def _load_topic_scores_from_feedback(self) -> None:
        """
        Initialisiert topic_scores aus FeedbackEngine-History.
        Wird beim Start aufgerufen.
        """
        try:
            from orchestration.feedback_engine import get_feedback_engine
            engine = get_feedback_engine()
            events = engine.get_recent_events(limit=100)
            for event in events:
                topic = event.context.get("topic")
                if topic and event.signal in {"positive", "negative"}:
                    self.update_topic_score(topic, event.signal)
        except Exception as e:
            log.debug("_load_topic_scores_from_feedback: %s", e)

    # ---------------------------------------------------------------
    # Anti-Spam / Duplicate Prevention
    # ---------------------------------------------------------------

    def _is_daily_limit_reached(self) -> bool:
        """Prüft ob das Tageslimit bereits erreicht ist."""
        try:
            with sqlite3.connect(MEMORY_DB_PATH) as con:
                row = con.execute(
                    "SELECT COUNT(*) FROM curiosity_sent WHERE sent_at > date('now')"
                ).fetchone()
                return (row[0] if row else 0) >= MAX_PER_DAY
        except Exception as e:
            log.debug("_is_daily_limit_reached: %s", e)
            return False

    def _is_duplicate(self, url: str) -> bool:
        """Prüft ob die URL in den letzten 14 Tagen bereits gesendet wurde."""
        try:
            with sqlite3.connect(MEMORY_DB_PATH) as con:
                row = con.execute(
                    "SELECT 1 FROM curiosity_sent WHERE url=? AND sent_at > date('now','-14 days')",
                    (url,),
                ).fetchone()
                return row is not None
        except Exception as e:
            log.debug("_is_duplicate: %s", e)
            return False

    def _log_sent(self, topic: str, url: str, title: str, score: int) -> None:
        """Schreibt einen gesendeten Artikel in curiosity_sent."""
        try:
            with sqlite3.connect(MEMORY_DB_PATH) as con:
                con.execute(
                    "INSERT OR IGNORE INTO curiosity_sent (topic, url, title, score) VALUES (?, ?, ?, ?)",
                    (topic, url, title, score),
                )
        except Exception as e:
            log.warning("_log_sent fehlgeschlagen: %s", e)

    # ---------------------------------------------------------------
    # LLM-Helfer
    # ---------------------------------------------------------------

    async def _llm_call(
        self,
        prompt: str,
        max_tokens: int = 200,
        temperature: float = 0.5,
    ) -> Optional[str]:
        """
        Führt einen LLM-API-Call durch.
        Reihenfolge: Reflection-Engine → Anthropic (FAST_MODEL) → OpenAI Fallback.
        """
        # --- Versuch 1: Reflection Engine Client ---
        try:
            from memory.reflection_engine import get_reflection_engine
            engine = get_reflection_engine()
            if engine.llm:
                client = engine._resolve_chat_client()
                if client:
                    from utils.openai_compat import prepare_openai_params
                    model = os.getenv("REFLECTION_MODEL", "gpt-4o-mini")
                    resp = await asyncio.to_thread(
                        client.chat.completions.create,
                        **prepare_openai_params({
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                        })
                    )
                    return resp.choices[0].message.content
        except Exception as e:
            log.debug("Curiosity: Reflection-Client fehlgeschlagen (%s), versuche Anthropic", e)

        # --- Versuch 2: Anthropic (FAST_MODEL) ---
        try:
            anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
            fast_model = os.getenv("FAST_MODEL", "claude-haiku-4-5-20251001")
            fast_provider = os.getenv("FAST_MODEL_PROVIDER", "anthropic").lower()
            if anthropic_key and fast_provider == "anthropic":
                from anthropic import Anthropic
                client_a = Anthropic(api_key=anthropic_key)
                resp = await asyncio.to_thread(
                    client_a.messages.create,
                    model=fast_model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text
        except Exception as e:
            log.debug("Curiosity: Anthropic-Fallback fehlgeschlagen (%s), versuche OpenAI", e)

        # --- Versuch 3: direkter OpenAI-Call ---
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                log.warning("Curiosity: Kein LLM-Provider verfügbar (kein OPENAI_API_KEY)")
                return None
            client = OpenAI(api_key=api_key)
            from utils.openai_compat import prepare_openai_params
            model = os.getenv("REFLECTION_MODEL", "gpt-4o-mini")
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                **prepare_openai_params({
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                })
            )
            return resp.choices[0].message.content
        except Exception as e:
            log.warning("Curiosity: LLM-Call fehlgeschlagen (alle Provider): %s", e)
            return None

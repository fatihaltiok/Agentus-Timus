"""
gateway/rss_poller.py

Überwacht RSS-Feeds periodisch und löst Tasks aus bei neuen Artikeln.
Bereits gesehene Artikel werden in einer SQLite-DB gespeichert (keine Duplikate).

Konfiguration (.env):
    RSS_FEEDS          = kommagetrennte URLs
    RSS_POLL_INTERVAL  = Intervall in Minuten (default: 30)

Beispiel .env:
    RSS_FEEDS=https://www.heise.de/rss/heise-atom.xml,https://feeds.arstechnica.com/arstechnica/index
    RSS_POLL_INTERVAL=30
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

log = logging.getLogger("RSSPoller")

SEEN_DB = Path(__file__).parent.parent / "data" / "rss_seen.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_items (
    item_hash  TEXT PRIMARY KEY,
    feed_url   TEXT NOT NULL,
    title      TEXT,
    link       TEXT,
    first_seen TEXT NOT NULL
);
"""


# ──────────────────────────────────────────────────────────────────
# Seen-Items DB
# ──────────────────────────────────────────────────────────────────

@contextmanager
def _db() -> Generator[sqlite3.Connection, None, None]:
    SEEN_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SEEN_DB, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _item_hash(feed_url: str, item_id: str) -> str:
    return hashlib.sha256(f"{feed_url}::{item_id}".encode()).hexdigest()[:32]


def _is_seen(feed_url: str, item_id: str) -> bool:
    h = _item_hash(feed_url, item_id)
    with _db() as conn:
        return conn.execute(
            "SELECT 1 FROM seen_items WHERE item_hash=?", (h,)
        ).fetchone() is not None


def _mark_seen(feed_url: str, item_id: str, title: str, link: str) -> None:
    h = _item_hash(feed_url, item_id)
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_items VALUES (?,?,?,?,?)",
            (h, feed_url, title[:200], link[:500], datetime.now().isoformat()),
        )


# ──────────────────────────────────────────────────────────────────
# Feed-Verarbeitung
# ──────────────────────────────────────────────────────────────────

async def _fetch_new_items(feed_url: str) -> List[dict]:
    """Holt neue (noch nicht gesehene) Artikel aus einem RSS-Feed."""
    import feedparser

    loop = asyncio.get_event_loop()
    try:
        feed = await loop.run_in_executor(None, feedparser.parse, feed_url)
    except Exception as e:
        log.warning(f"Feed-Fehler ({feed_url[:50]}): {e}")
        return []

    new_items = []
    feed_title = feed.feed.get("title", feed_url[:40])

    for entry in feed.entries[:10]:  # Max 10 neueste Einträge prüfen
        item_id = entry.get("id") or entry.get("link") or entry.get("title", "")
        if not item_id:
            continue

        if _is_seen(feed_url, item_id):
            continue

        title = entry.get("title", "(kein Titel)")
        link = entry.get("link", "")
        summary = entry.get("summary", "")[:300]

        _mark_seen(feed_url, item_id, title, link)
        new_items.append({
            "feed_title": feed_title,
            "feed_url": feed_url,
            "title": title,
            "link": link,
            "summary": summary,
        })

    if new_items:
        log.info(f"RSS [{feed_title[:30]}]: {len(new_items)} neue Artikel")

    return new_items


# ──────────────────────────────────────────────────────────────────
# RSSPoller
# ──────────────────────────────────────────────────────────────────

class RSSPoller:
    """Überwacht RSS-Feeds und erstellt Tasks für neue Artikel."""

    def __init__(self, interval_minutes: int = 30):
        self.interval_minutes = interval_minutes
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _get_feeds(self) -> List[str]:
        raw = os.getenv("RSS_FEEDS", "").strip()
        if not raw:
            return []
        return [u.strip() for u in raw.split(",") if u.strip()]

    async def start(self) -> None:
        feeds = self._get_feeds()
        if not feeds:
            log.info("RSS_FEEDS nicht konfiguriert — Poller inaktiv")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="rss-poller")
        log.info(
            f"✅ RSS-Poller aktiv: {len(feeds)} Feed(s), "
            f"Intervall: {self.interval_minutes} min"
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
        log.info("RSS-Poller gestoppt")

    async def _loop(self) -> None:
        # Beim ersten Start direkt prüfen
        await self._poll_all()
        while self._running:
            await asyncio.sleep(self.interval_minutes * 60)
            if self._running:
                await self._poll_all()

    async def _poll_all(self) -> None:
        feeds = self._get_feeds()
        for feed_url in feeds:
            try:
                new_items = await _fetch_new_items(feed_url)
                for item in new_items:
                    await self._create_task_for_item(item)
            except Exception as e:
                log.error(f"Poller-Fehler für {feed_url[:50]}: {e}")

    async def _create_task_for_item(self, item: dict) -> None:
        """Erstellt einen Research-Task für einen neuen RSS-Artikel."""
        try:
            from gateway.event_router import route_event
            from gateway.webhook_gateway import EventType

            await route_event(
                event_type=EventType.RSS_NEW_ITEM,
                source=item["feed_url"],
                payload=item,
            )
        except Exception as e:
            log.error(f"Task-Erstellung fehlgeschlagen: {e}")

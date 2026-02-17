"""
Persistent Browser Context Manager - Session-Isolierung mit Cookie-Persistence.

Ansatz: new_context() + storage_state() (Firefox-kompatibel)
NICHT launch_persistent_context() (nur Chromium stabil).

Features:
- Pro-Session isolierte Browser-Contexts
- Persistent Storage (Cookies, LocalStorage) via storage_state JSON
- Context-Pooling mit MAX_CONTEXTS Limit
- Automatisches Cleanup nach Session-Timeout
- Retry-Integration für Network-Fehler

USAGE:
    from tools.browser_tool.persistent_context import PersistentContextManager

    manager = PersistentContextManager()
    await manager.initialize()

    # Session mit persistentem State
    session = await manager.get_or_create_context("user_123")
    page = session.page

    # Nach Session-Ende
    await manager.save_context_state("user_123")
    await manager.close_context("user_123")

AUTOR: Timus Development
DATUM: Februar 2026
"""

import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
)

log = logging.getLogger("PersistentContextManager")

# Konfiguration
MAX_CONTEXTS = 5
SESSION_TIMEOUT_MINUTES = 60
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) "
    "Gecko/20100101 Firefox/115.0"
)


@dataclass
class SessionContext:
    """Isolierte Browser-Session mit persistentem State."""
    session_id: str
    context: BrowserContext
    page: Page
    storage_path: Path
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    request_count: int = 0


class PersistentContextManager:
    """
    Verwaltet isolierte, persistente Browser-Contexts.

    Bietet Session-Isolierung mit Cookie/LocalStorage Persistence
    für deterministisches Browser-Verhalten über mehrere Runs hinweg.
    """

    def __init__(
        self,
        base_storage_dir: Optional[Path] = None,
        headless: bool = True,
        user_agent: str = DEFAULT_USER_AGENT
    ):
        """
        Initialisiert den Context Manager.

        Args:
            base_storage_dir: Verzeichnis für Storage-State Files
            headless: Browser im Hintergrund starten
            user_agent: User-Agent String
        """
        self.base_storage_dir = base_storage_dir or Path("data/browser_contexts")
        self.base_storage_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.user_agent = user_agent

        self.contexts: Dict[str, SessionContext] = {}
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Startet Playwright und Browser (einmalig).

        Returns:
            True wenn erfolgreich initialisiert
        """
        if self._initialized:
            return True

        try:
            self._playwright = await async_playwright().start()

            # Firefox starten (headless)
            try:
                self._browser = await self._playwright.firefox.launch(
                    headless=self.headless
                )
            except Exception as e:
                # Auto-Repair falls Browser nicht installiert
                if "ENOENT" in str(e) or "no such file" in str(e).lower():
                    log.warning("Browser nicht gefunden. Starte 'playwright install firefox'...")
                    process = await asyncio.create_subprocess_exec(
                        "playwright", "install", "firefox"
                    )
                    await process.wait()
                    if process.returncode == 0:
                        self._browser = await self._playwright.firefox.launch(
                            headless=self.headless
                        )
                    else:
                        raise RuntimeError("Playwright-Installation fehlgeschlagen")
                else:
                    raise

            self._initialized = True
            log.info(
                f"✅ PersistentContextManager initialisiert "
                f"(headless={self.headless}, max_contexts={MAX_CONTEXTS})"
            )
            return True

        except Exception as e:
            log.error(f"❌ Browser-Initialisierung fehlgeschlagen: {e}")
            return False

    async def get_or_create_context(
        self,
        session_id: str = "default"
    ) -> SessionContext:
        """
        Holt existierenden oder erstellt neuen Context.

        Args:
            session_id: Eindeutige Session-ID

        Returns:
            SessionContext mit Page und Context
        """
        if not self._initialized:
            await self.initialize()

        # Existierenden Context zurückgeben
        if session_id in self.contexts:
            ctx = self.contexts[session_id]
            ctx.last_used = datetime.now()
            ctx.request_count += 1
            log.debug(f"Session '{session_id}' wiederverwendet (requests: {ctx.request_count})")
            return ctx

        # Context-Limit prüfen, ältesten evicten
        if len(self.contexts) >= MAX_CONTEXTS:
            await self._evict_oldest_context()

        # Storage-Pfad vorbereiten
        storage_dir = self.base_storage_dir / session_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_file = storage_dir / "storage.json"

        # Context erstellen
        context_kwargs = {
            "user_agent": self.user_agent,
            "accept_downloads": False,
        }

        # Gespeicherten State laden falls vorhanden
        if storage_file.exists():
            try:
                context_kwargs["storage_state"] = str(storage_file)
                log.info(f"Session '{session_id}': Lade gespeicherten State")
            except Exception as e:
                log.warning(f"Konnte Storage-State nicht laden: {e}")

        context = await self._browser.new_context(**context_kwargs)
        page = await context.new_page()

        session = SessionContext(
            session_id=session_id,
            context=context,
            page=page,
            storage_path=storage_dir
        )
        self.contexts[session_id] = session

        log.info(
            f"Session '{session_id}': Neuer Context erstellt "
            f"(active: {len(self.contexts)}/{MAX_CONTEXTS})"
        )
        return session

    def get_page(self, session_id: str = "default") -> Optional[Page]:
        """
        Holt die Page für eine Session (schnell, ohne Create).

        Returns None falls Session nicht existiert.
        """
        if session_id in self.contexts:
            return self.contexts[session_id].page
        return None

    async def save_context_state(self, session_id: str) -> bool:
        """
        Speichert Cookies/LocalStorage für spätere Wiederherstellung.

        Args:
            session_id: Die zu speichernde Session

        Returns:
            True wenn erfolgreich gespeichert
        """
        if session_id not in self.contexts:
            return False

        ctx = self.contexts[session_id]
        storage_file = ctx.storage_path / "storage.json"

        try:
            await ctx.context.storage_state(path=str(storage_file))
            log.info(f"Session '{session_id}': State gespeichert ({storage_file.stat().st_size} bytes)")
            return True
        except Exception as e:
            log.warning(f"State-Save fehlgeschlagen für '{session_id}': {e}")
            return False

    async def close_context(
        self,
        session_id: str,
        save_state: bool = True
    ) -> bool:
        """
        Schließt einen Context und speichert optional den State.

        Args:
            session_id: Die zu schließende Session
            save_state: Ob State gespeichert werden soll

        Returns:
            True wenn erfolgreich geschlossen
        """
        if session_id not in self.contexts:
            return False

        ctx = self.contexts[session_id]

        try:
            if save_state:
                await self.save_context_state(session_id)

            await ctx.context.close()
            del self.contexts[session_id]

            log.info(f"Session '{session_id}': Context geschlossen")
            return True

        except Exception as e:
            log.warning(f"Context-Close fehlgeschlagen für '{session_id}': {e}")
            # Trotzdem aus der Map entfernen
            if session_id in self.contexts:
                del self.contexts[session_id]
            return False

    async def _evict_oldest_context(self) -> Optional[str]:
        """
        Entfernt den ältesten ungenutzten Context (LRU Eviction).

        Default-Session wird nie evicted.
        """
        if not self.contexts:
            return None

        # Älteste nicht-default Session finden
        candidates = [
            (sid, ctx) for sid, ctx in self.contexts.items()
            if sid != "default"
        ]

        if not candidates:
            log.warning("Keine evictbaren Contexts (nur 'default' aktiv)")
            return None

        oldest_id = min(candidates, key=lambda x: x[1].last_used)[0]
        await self.close_context(oldest_id, save_state=True)

        log.info(f"LRU Eviction: Session '{oldest_id}' entfernt")
        return oldest_id

    async def cleanup_expired(self) -> int:
        """
        Entfernt abgelaufene Sessions (Timeout).

        Returns:
            Anzahl entfernter Sessions
        """
        now = datetime.now()
        timeout = timedelta(minutes=SESSION_TIMEOUT_MINUTES)

        expired = [
            sid for sid, ctx in self.contexts.items()
            if (now - ctx.last_used) > timeout and sid != "default"
        ]

        for sid in expired:
            await self.close_context(sid, save_state=True)

        if expired:
            log.info(f"Cleanup: {len(expired)} abgelaufene Sessions entfernt")

        return len(expired)

    async def cleanup_all(self) -> int:
        """
        Schließt alle Contexts und speichert ihre States.

        Returns:
            Anzahl geschlossener Sessions
        """
        closed = 0
        for session_id in list(self.contexts.keys()):
            if await self.close_context(session_id, save_state=True):
                closed += 1
        return closed

    async def shutdown(self) -> None:
        """
        Speichert alle States und fährt herunter.
        """
        log.info("PersistentContextManager Shutdown...")

        # Alle Contexts schließen
        await self.cleanup_all()

        # Browser schließen
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                log.debug(f"Browser-Close Fehler: {e}")

        # Playwright stoppen
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                log.debug(f"Playwright-Stop Fehler: {e}")

        self._initialized = False
        log.info("✅ PersistentContextManager heruntergefahren")

    def get_status(self) -> Dict[str, Any]:
        """Gibt Status aller aktiven Sessions zurück."""
        return {
            "initialized": self._initialized,
            "headless": self.headless,
            "active_contexts": len(self.contexts),
            "max_contexts": MAX_CONTEXTS,
            "session_timeout_minutes": SESSION_TIMEOUT_MINUTES,
            "storage_dir": str(self.base_storage_dir),
            "sessions": {
                sid: {
                    "created_at": ctx.created_at.isoformat(),
                    "last_used": ctx.last_used.isoformat(),
                    "request_count": ctx.request_count,
                    "has_saved_state": (ctx.storage_path / "storage.json").exists()
                }
                for sid, ctx in self.contexts.items()
            }
        }

    def is_available(self) -> bool:
        """Prüft ob Manager initialisiert und bereit ist."""
        return self._initialized and self._browser is not None


# Singleton für einfachen Zugriff
_manager: Optional[PersistentContextManager] = None


def get_context_manager() -> Optional[PersistentContextManager]:
    """Gibt den globalen Manager zurück."""
    return _manager


def set_context_manager(manager: PersistentContextManager) -> None:
    """Setzt den globalen Manager."""
    global _manager
    _manager = manager

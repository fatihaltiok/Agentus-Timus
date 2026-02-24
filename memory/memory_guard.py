"""
MemoryAccessGuard — Thread-sicherer Schreibschutz für parallele Worker.

Nutzt ContextVar statt Klassvariable, damit jeder asyncio-Task seinen
eigenen read_only-Status hat (kein globaler Zustand, keine Race Conditions).

Verwendung:
    MemoryAccessGuard.set_read_only(True)   # Worker-Modus aktivieren
    MemoryAccessGuard.check_write_permission()  # wirft PermissionError wenn read-only
    MemoryAccessGuard.set_read_only(False)  # nach Abschluss zurücksetzen
"""

import asyncio
from contextvars import ContextVar

# Pro asyncio-Task isolierter read-only Status (kein globaler Zustand)
_read_only_ctx: ContextVar[bool] = ContextVar("timus_read_only", default=False)

# Globaler Write-Lock für Single-Writer-Prinzip bei SQLite/ChromaDB
_write_lock: asyncio.Lock = asyncio.Lock()


class MemoryAccessGuard:
    """
    Schreibschutz-Guard für parallele Worker-Agenten.

    Jeder asyncio-Task hat seinen eigenen read_only-Status via ContextVar.
    Worker A und Worker B überschreiben sich gegenseitig nicht.
    """

    @staticmethod
    def set_read_only(enabled: bool) -> None:
        """Setzt read-only für den aktuellen asyncio-Task (nicht global)."""
        _read_only_ctx.set(enabled)

    @staticmethod
    def is_read_only() -> bool:
        """Gibt zurück ob der aktuelle Task im read-only Modus läuft."""
        return _read_only_ctx.get()

    @staticmethod
    def check_write_permission() -> None:
        """
        Wirft PermissionError wenn der aktuelle Task read-only ist.
        Muss vor jedem Schreibzugriff auf SQLite/ChromaDB aufgerufen werden.
        """
        if _read_only_ctx.get():
            raise PermissionError(
                "Paralleler Worker ist read-only. "
                "Ergebnisse nur via JSON-Return an den MetaAgenten zurückgeben, "
                "nicht direkt in Memory schreiben."
            )

    @staticmethod
    async def acquire_write_lock() -> None:
        """Erwirbt den globalen Write-Lock (Single-Writer-Prinzip)."""
        await _write_lock.acquire()

    @staticmethod
    def release_write_lock() -> None:
        """Gibt den globalen Write-Lock frei."""
        _write_lock.release()

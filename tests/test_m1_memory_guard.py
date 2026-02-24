"""
Tests für Meilenstein 1 — MemoryAccessGuard + WAL-Modus.

Phasen:
  T1 — MemoryAccessGuard Grundverhalten
  T2 — ContextVar-Isolation (kein globaler Zustand)
  T3 — Guard blockiert Schreiboperationen in PersistentMemory
  T4 — WAL-Modus in SQLite aktiv
  T5 — Normalbetrieb (kein read-only) weiterhin funktioniert
"""

import asyncio
import pytest
import tempfile
from pathlib import Path


# ── T1: MemoryAccessGuard Grundverhalten ─────────────────────────────────────

class TestMemoryGuardBasic:

    def test_default_nicht_readonly(self):
        """Standard: kein read-only."""
        from memory.memory_guard import MemoryAccessGuard
        MemoryAccessGuard.set_read_only(False)
        assert MemoryAccessGuard.is_read_only() is False

    def test_set_readonly_true(self):
        from memory.memory_guard import MemoryAccessGuard
        MemoryAccessGuard.set_read_only(True)
        assert MemoryAccessGuard.is_read_only() is True
        MemoryAccessGuard.set_read_only(False)  # cleanup

    def test_check_write_permission_erlaubt(self):
        """Kein PermissionError wenn nicht read-only."""
        from memory.memory_guard import MemoryAccessGuard
        MemoryAccessGuard.set_read_only(False)
        MemoryAccessGuard.check_write_permission()  # darf nicht werfen

    def test_check_write_permission_blockiert(self):
        """PermissionError wenn read-only."""
        from memory.memory_guard import MemoryAccessGuard
        MemoryAccessGuard.set_read_only(True)
        with pytest.raises(PermissionError, match="read-only"):
            MemoryAccessGuard.check_write_permission()
        MemoryAccessGuard.set_read_only(False)  # cleanup

    def test_set_readonly_toggle(self):
        """Mehrfaches Umschalten funktioniert."""
        from memory.memory_guard import MemoryAccessGuard
        MemoryAccessGuard.set_read_only(True)
        assert MemoryAccessGuard.is_read_only() is True
        MemoryAccessGuard.set_read_only(False)
        assert MemoryAccessGuard.is_read_only() is False


# ── T2: ContextVar-Isolation ─────────────────────────────────────────────────

class TestContextVarIsolation:

    def test_task_isolation(self):
        """
        Zwei asyncio-Tasks haben unabhängige read-only Status.
        Worker A = True darf Worker B = False nicht überschreiben.
        """
        from memory.memory_guard import MemoryAccessGuard

        results = {}

        async def worker_a():
            MemoryAccessGuard.set_read_only(True)
            await asyncio.sleep(0.05)  # Worker B läuft inzwischen
            results["a"] = MemoryAccessGuard.is_read_only()

        async def worker_b():
            MemoryAccessGuard.set_read_only(False)
            await asyncio.sleep(0.01)
            results["b"] = MemoryAccessGuard.is_read_only()

        async def run():
            await asyncio.gather(worker_a(), worker_b())

        asyncio.run(run())

        assert results["a"] is True,  "Worker A muss read-only=True behalten"
        assert results["b"] is False, "Worker B muss read-only=False behalten"

    def test_exception_setzt_flag_nicht_global(self):
        """
        Wenn Worker A eine Exception wirft bevor set_read_only(False),
        bleibt Worker B unbeeinträchtigt.
        """
        from memory.memory_guard import MemoryAccessGuard

        b_status = {}

        async def failing_worker():
            MemoryAccessGuard.set_read_only(True)
            raise RuntimeError("Simulierter Fehler")

        async def normal_worker():
            await asyncio.sleep(0.02)
            b_status["readonly"] = MemoryAccessGuard.is_read_only()

        async def run():
            results = await asyncio.gather(
                failing_worker(), normal_worker(),
                return_exceptions=True
            )
            return results

        asyncio.run(run())
        assert b_status["readonly"] is False, "Normaler Worker bleibt unbeeinträchtigt"


# ── T3: Guard blockiert PersistentMemory-Schreiboperationen ──────────────────

class TestGuardBlocksPersistentMemory:

    def _make_persistent_memory(self, tmp_path):
        """Erstellt eine PersistentMemory-Instanz mit Temp-DB."""
        from memory.memory_system import PersistentMemory
        db_path = tmp_path / "test_memory.db"
        return PersistentMemory(db_path=db_path)  # Path-Objekt, kein str

    def test_store_fact_blockiert_bei_readonly(self, tmp_path):
        from memory.memory_guard import MemoryAccessGuard
        from memory.memory_system import Fact

        pm = self._make_persistent_memory(tmp_path)
        MemoryAccessGuard.set_read_only(True)

        fact = Fact(category="test", key="k", value="v")
        with pytest.raises(PermissionError):
            pm.store_fact(fact)

        MemoryAccessGuard.set_read_only(False)

    def test_store_memory_item_blockiert_bei_readonly(self, tmp_path):
        from memory.memory_guard import MemoryAccessGuard
        from memory.memory_system import MemoryItem

        pm = self._make_persistent_memory(tmp_path)
        MemoryAccessGuard.set_read_only(True)

        item = MemoryItem(category="test", key="k", value={"x": 1})
        with pytest.raises(PermissionError):
            pm.store_memory_item(item)

        MemoryAccessGuard.set_read_only(False)

    def test_store_summary_blockiert_bei_readonly(self, tmp_path):
        from memory.memory_guard import MemoryAccessGuard
        from memory.memory_system import ConversationSummary

        pm = self._make_persistent_memory(tmp_path)
        MemoryAccessGuard.set_read_only(True)

        summary = ConversationSummary(summary="test", topics=[], facts_extracted=[], message_count=1)
        with pytest.raises(PermissionError):
            pm.store_summary(summary)

        MemoryAccessGuard.set_read_only(False)

    def test_store_conversation_blockiert_bei_readonly(self, tmp_path):
        from memory.memory_guard import MemoryAccessGuard

        pm = self._make_persistent_memory(tmp_path)
        MemoryAccessGuard.set_read_only(True)

        with pytest.raises(PermissionError):
            pm.store_conversation("session-1", [])

        MemoryAccessGuard.set_read_only(False)


# ── T4: WAL-Modus aktiv ──────────────────────────────────────────────────────

class TestWALMode:

    def test_wal_mode_aktiviert(self, tmp_path):
        """Nach _init_db() muss WAL-Modus in der SQLite-DB aktiv sein."""
        import sqlite3
        from memory.memory_system import PersistentMemory

        db_path = tmp_path / "wal_test.db"
        PersistentMemory(db_path=db_path)  # _init_db() wird aufgerufen

        with sqlite3.connect(str(db_path)) as conn:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]

        assert mode == "wal", f"Erwartet 'wal', bekommen: '{mode}'"


# ── T5: Normalbetrieb weiterhin funktioniert ─────────────────────────────────

class TestNormalOperationUnaffected:

    def test_store_und_get_fact_ohne_readonly(self, tmp_path):
        """store_fact + get_fact funktioniert normal wenn nicht read-only."""
        from memory.memory_guard import MemoryAccessGuard
        from memory.memory_system import PersistentMemory, Fact

        MemoryAccessGuard.set_read_only(False)
        db_path = tmp_path / "normal_test.db"
        pm = PersistentMemory(db_path=db_path)

        fact = Fact(category="pref", key="sprache", value="deutsch")
        pm.store_fact(fact)

        retrieved = pm.get_fact("pref", "sprache")
        assert retrieved is not None
        assert retrieved.value == "deutsch"

    def test_store_und_get_memory_item_ohne_readonly(self, tmp_path):
        from memory.memory_guard import MemoryAccessGuard
        from memory.memory_system import PersistentMemory, MemoryItem

        MemoryAccessGuard.set_read_only(False)
        db_path = tmp_path / "normal_item_test.db"
        pm = PersistentMemory(db_path=db_path)

        item = MemoryItem(category="facts", key="hauptstadt", value={"city": "Berlin"})
        pm.store_memory_item(item)

        items = pm.get_memory_items("facts")
        assert len(items) == 1
        assert items[0].key == "hauptstadt"

    def test_lesende_operationen_funktionieren_bei_readonly(self, tmp_path):
        """get_fact() darf auch im read-only Modus funktionieren."""
        from memory.memory_guard import MemoryAccessGuard
        from memory.memory_system import PersistentMemory, Fact

        db_path = tmp_path / "read_test.db"
        pm = PersistentMemory(db_path=db_path)

        # Erst schreiben (nicht read-only)
        MemoryAccessGuard.set_read_only(False)
        pm.store_fact(Fact(category="test", key="x", value="42"))

        # Dann lesen im read-only Modus
        MemoryAccessGuard.set_read_only(True)
        result = pm.get_fact("test", "x")
        assert result is not None
        assert result.value == "42"

        MemoryAccessGuard.set_read_only(False)

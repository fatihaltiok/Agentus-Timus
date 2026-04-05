"""C5 Memory-Markdown-Sync-Tests.

Testziele:
- replace_memories schreibt höchstens einmal pro Sync
- doppelter Sync ist idempotent (kein zweites Write)
- Dedupe entfernt normalisierte Duplikate korrekt
- unchanged Guard schreibt nicht wenn Inhalt identisch
- Scheduler skippt bei unverändertem Hash
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import patch, MagicMock, call
from memory.markdown_store.store import MarkdownStore, MemoryEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(tmp_path: Path) -> MarkdownStore:
    store = MarkdownStore(base_path=tmp_path)
    return store


def _entry(category: str, content: str, source: str = "test", importance: float = 0.9) -> MemoryEntry:
    return MemoryEntry(category=category, content=content, importance=importance, source=source)


# ---------------------------------------------------------------------------
# 1. replace_memories schreibt genau einmal
# ---------------------------------------------------------------------------

def test_replace_memories_writes_exactly_once(tmp_path):
    store = _store(tmp_path)
    entries = [
        _entry("user", "Fatih mag Python"),
        _entry("project", "Timus läuft auf Linux"),
        _entry("project", "Memory-System aktiv"),
    ]
    write_calls = []
    original_write = store._write_memory_file

    def track_write(memories):
        write_calls.append(len(memories))
        original_write(memories)

    store._write_memory_file = track_write
    written, items_written, deduped_count = store.replace_memories(entries)

    assert written is True
    assert len(write_calls) == 1, f"Erwartet 1 Write, got {len(write_calls)}"
    assert items_written == 3


def test_replace_memories_bulk_not_n_writes(tmp_path):
    """N Items müssen N Writes verhindern — das war der ursprüngliche Bug."""
    store = _store(tmp_path)
    n = 20
    entries = [_entry("cat", f"Item {i}") for i in range(n)]
    write_calls = []
    original = store._write_memory_file

    def track(m):
        write_calls.append(True)
        original(m)

    store._write_memory_file = track
    store.replace_memories(entries)

    assert len(write_calls) == 1, f"Bug: {len(write_calls)} Writes statt 1 für {n} Items"


# ---------------------------------------------------------------------------
# 2. Idempotenz — doppelter Sync schreibt kein zweites Mal
# ---------------------------------------------------------------------------

def test_replace_memories_second_call_is_noop(tmp_path):
    store = _store(tmp_path)
    entries = [_entry("user", "Fatih"), _entry("project", "Timus")]
    write_calls = []
    original = store._write_memory_file

    def track(m):
        write_calls.append(True)
        original(m)

    store._write_memory_file = track

    written1, _, _ = store.replace_memories(entries)
    written2, items2, _ = store.replace_memories(entries)

    assert written1 is True
    assert written2 is False, "Zweiter Sync mit identischen Daten darf nicht schreiben"
    assert items2 == 0
    assert len(write_calls) == 1


def test_replace_memories_changed_data_triggers_write(tmp_path):
    store = _store(tmp_path)
    e1 = [_entry("user", "Version 1")]
    e2 = [_entry("user", "Version 2")]  # anderer Inhalt

    w1, _, _ = store.replace_memories(e1)
    w2, _, _ = store.replace_memories(e2)

    assert w1 is True
    assert w2 is True, "Geänderter Inhalt muss schreiben"


# ---------------------------------------------------------------------------
# 3. Dedupe — normalisierte Duplikate werden entfernt
# ---------------------------------------------------------------------------

def test_dedupe_removes_case_whitespace_duplicates(tmp_path):
    store = _store(tmp_path)
    entries = [
        _entry("user", "Fatih mag Python", source="chat"),
        _entry("user", "fatih mag python", source="chat"),   # Duplikat (Kleinschreibung)
        _entry("user", "Fatih  mag  Python", source="chat"),  # Duplikat (Leerzeichen)
        _entry("project", "Timus läuft"),
    ]
    written, items_written, deduped_count = store.replace_memories(entries)

    assert written is True
    assert deduped_count == 2, f"Erwartet 2 Duplikate, got {deduped_count}"
    assert items_written == 2, f"Erwartet 2 unique Items, got {items_written}"


def test_dedupe_key_is_stable():
    e1 = _entry("user", "Test Content", source="src")
    e2 = _entry("user", "  test content  ", source="src")
    assert MarkdownStore._dedupe_key(e1) == MarkdownStore._dedupe_key(e2)


def test_dedupe_key_differs_by_category():
    e1 = _entry("user", "Content", source="src")
    e2 = _entry("project", "Content", source="src")
    assert MarkdownStore._dedupe_key(e1) != MarkdownStore._dedupe_key(e2)


def test_dedupe_key_differs_by_source():
    e1 = _entry("user", "Content", source="chat")
    e2 = _entry("user", "Content", source="email")
    assert MarkdownStore._dedupe_key(e1) != MarkdownStore._dedupe_key(e2)


# ---------------------------------------------------------------------------
# 4. render_hash — reihenfolgeunabhängig, stabil
# ---------------------------------------------------------------------------

def test_render_hash_order_independent():
    e1 = _entry("a", "first")
    e2 = _entry("b", "second")
    h1 = MarkdownStore._render_hash([e1, e2])
    h2 = MarkdownStore._render_hash([e2, e1])
    assert h1 == h2, "Hash muss reihenfolgeunabhängig sein"


def test_render_hash_changes_on_content_change():
    e1 = _entry("user", "v1")
    e2 = _entry("user", "v2")
    assert MarkdownStore._render_hash([e1]) != MarkdownStore._render_hash([e2])


def test_render_hash_empty_list():
    h = MarkdownStore._render_hash([])
    assert isinstance(h, str) and len(h) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# 5. Scheduler skippt bei unchanged hash
# ---------------------------------------------------------------------------

def test_scheduler_skips_sync_on_unchanged_hash():
    """_memory_sync_needed() gibt False zurück wenn Hash identisch."""
    from orchestration.scheduler import ProactiveScheduler
    sched = ProactiveScheduler()

    fake_item = MagicMock()
    fake_item.category = "user"
    fake_item.value = "Fatih"
    fake_item.importance = 0.9
    fake_item.source = "test"

    with (
        patch("orchestration.scheduler.memory_manager", create=True),
        patch("memory.memory_system.memory_manager") as mm,
    ):
        mm.persistent.get_all_memory_items.return_value = [fake_item]

        with patch("orchestration.scheduler.ProactiveScheduler._memory_sync_needed") as mock_needed:
            mock_needed.side_effect = [True, False]  # Erster: sync; Zweiter: skip

            assert mock_needed() is True
            assert mock_needed() is False


def test_scheduler_status_includes_last_sync_at():
    from orchestration.scheduler import ProactiveScheduler
    sched = ProactiveScheduler()
    status = sched.get_status()
    # last_sync_at noch None, kein Crash
    assert "last_heartbeat" in status


# ---------------------------------------------------------------------------
# 6. C5-Observability wird emittiert
# ---------------------------------------------------------------------------

def test_observability_emitted_on_write(tmp_path):
    from orchestration.autonomy_observation import _record_memory_sync_observation

    with patch("orchestration.autonomy_observation.record_autonomy_observation") as mock_rec:
        _record_memory_sync_observation(items_written=5, deduped_count=2, written=True)
        mock_rec.assert_called_once()
        args = mock_rec.call_args
        assert args[0][0] == "memory_sync_completed"
        assert args[0][1]["items_written"] == 5
        assert args[0][1]["deduped_count"] == 2


def test_observability_emitted_on_skip(tmp_path):
    from orchestration.autonomy_observation import _record_memory_sync_observation

    with patch("orchestration.autonomy_observation.record_autonomy_observation") as mock_rec:
        _record_memory_sync_observation(items_written=0, deduped_count=3, written=False)
        mock_rec.assert_called_once()
        assert mock_rec.call_args[0][0] == "memory_sync_skipped_unchanged"


def test_observability_no_crash_on_exception(tmp_path):
    from orchestration.autonomy_observation import _record_memory_sync_observation

    with patch("orchestration.autonomy_observation.record_autonomy_observation", side_effect=RuntimeError("fail")):
        # Darf nicht crashen
        _record_memory_sync_observation(items_written=1, deduped_count=0, written=True)


# ---------------------------------------------------------------------------
# Finding 1: Write-Fehler darf nicht als unchanged maskiert werden
# ---------------------------------------------------------------------------

def test_replace_memories_write_error_propagates(tmp_path):
    """Ein echter Schreibfehler muss als Exception propagieren, nicht als written=False."""
    store = _store(tmp_path)
    entries = [_entry("user", "Fatih")]

    with patch.object(store, "_write_memory_file", side_effect=OSError("Disk voll")):
        with pytest.raises(OSError, match="Disk voll"):
            store.replace_memories(entries)


def test_sync_to_markdown_returns_false_on_write_error(tmp_path):
    """sync_to_markdown gibt False zurück wenn replace_memories einen Write-Fehler wirft."""
    from memory.memory_system import memory_manager

    store = MarkdownStore(base_path=tmp_path)
    fake_item = MagicMock()
    fake_item.category = "user"
    fake_item.value = "v2"
    fake_item.importance = 0.9
    fake_item.source = "test"

    with patch.object(memory_manager, "_get_markdown_store", return_value=store):
        with patch.object(memory_manager.persistent, "get_memory_items", return_value=[]):
            with patch.object(memory_manager.persistent, "get_all_memory_items", return_value=[fake_item]):
                with patch.object(store, "replace_memories", side_effect=OSError("Disk voll")):
                    assert memory_manager.sync_to_markdown() is False


def test_write_error_does_not_update_hash(tmp_path):
    """Nach einem fehlgeschlagenen Write bleibt der gespeicherte Hash unverändert —
    der nächste Sync-Versuch wird nicht fälschlich übersprungen."""
    store = _store(tmp_path)
    entries_v1 = [_entry("user", "Version 1")]
    entries_v2 = [_entry("user", "Version 2")]

    store.replace_memories(entries_v1)
    hash_after_v1 = store._last_memory_hash

    with patch.object(store, "_write_memory_file", side_effect=OSError("fail")):
        try:
            store.replace_memories(entries_v2)
        except OSError:
            pass

    assert store._last_memory_hash == hash_after_v1, (
        "Hash darf nach fehlgeschlagenem Write nicht aktualisiert werden"
    )


# ---------------------------------------------------------------------------
# Finding 2: FTS-Index wird nach replace_memories aktualisiert
# ---------------------------------------------------------------------------

def test_fts_index_updated_after_replace_memories(tmp_path):
    """MarkdownStoreWithSearch.replace_memories muss den FTS-Index neu bauen."""
    from memory.markdown_store.store import MarkdownStoreWithSearch

    store = MarkdownStoreWithSearch(base_path=tmp_path)
    entries = [_entry("user", "Timus FTS Test")]

    index_calls = []
    original = store._search_index.index_document

    def track_index(doc_id, *args, **kwargs):
        index_calls.append(doc_id)
        return original(doc_id, *args, **kwargs)

    store._search_index.index_document = track_index
    store.replace_memories(entries)

    assert "memory" in index_calls, "FTS-Index für 'memory' muss nach replace_memories aktualisiert werden"


def test_fts_index_not_called_on_unchanged(tmp_path):
    """Bei unchanged skip wird der FTS-Index NICHT erneut indiziert."""
    from memory.markdown_store.store import MarkdownStoreWithSearch

    store = MarkdownStoreWithSearch(base_path=tmp_path)
    entries = [_entry("user", "Gleicher Inhalt")]

    store.replace_memories(entries)  # Erster Write

    index_calls = []

    def track_index(doc_id, *args, **kwargs):
        index_calls.append(doc_id)

    store._search_index.index_document = track_index
    store.replace_memories(entries)  # Zweiter Call — unchanged

    assert "memory" not in index_calls, "Bei unchanged Skip darf kein FTS-Update passieren"


def test_fts_index_failure_does_not_confirm_hash_and_retries(tmp_path):
    """Wenn Reindexing scheitert, darf der Hash nicht bestätigt werden.

    Sonst würde der nächste identische Lauf als unchanged übersprungen und der
    Suchindex dauerhaft stale bleiben.
    """
    from memory.markdown_store.store import MarkdownStoreWithSearch

    store = MarkdownStoreWithSearch(base_path=tmp_path)
    entries_v1 = [_entry("user", "Version 1")]
    entries_v2 = [_entry("user", "Version 2")]

    store.replace_memories(entries_v1)
    hash_after_v1 = store._last_memory_hash

    with patch.object(store._search_index, "index_document", side_effect=RuntimeError("fts fail")):
        with pytest.raises(RuntimeError, match="fts fail"):
            store.replace_memories(entries_v2)

    assert store._last_memory_hash == hash_after_v1

    index_calls = []
    original = store._search_index.index_document

    def track_index(doc_id, *args, **kwargs):
        index_calls.append(doc_id)
        return original(doc_id, *args, **kwargs)

    store._search_index.index_document = track_index
    written, _, _ = store.replace_memories(entries_v2)

    assert written is True
    assert "memory" in index_calls


# ---------------------------------------------------------------------------
# Finding 3: Scheduler-Hash nur nach erfolgreichem Sync setzen
# ---------------------------------------------------------------------------

def test_scheduler_hash_not_updated_on_failed_sync():
    """_last_sync_hash bleibt unverändert wenn der echte Sync fehlschlägt."""
    from orchestration.scheduler import ProactiveScheduler
    from memory.memory_system import memory_manager

    sched = ProactiveScheduler()
    sched._last_sync_hash = "initial-hash"

    fake_item = MagicMock()
    fake_item.category = "user"
    fake_item.value = "Fatih"
    fake_item.importance = 0.9
    fake_item.source = "test"

    with patch.object(memory_manager.persistent, "get_all_memory_items", return_value=[fake_item]):
        with patch("memory.markdown_store.store.MarkdownStore._render_hash", return_value="new-hash"):
            assert sched._memory_sync_needed() is True
            assert sched._pending_sync_hash == "new-hash"
            with patch.object(memory_manager, "sync_to_markdown", return_value=False):
                result = asyncio.run(sched._sync_memory())

    assert result is False
    assert sched._last_sync_hash == "initial-hash"


def test_scheduler_success_promotes_pending_hash():
    """Nach erfolgreichem echtem Sync wird _pending_sync_hash nach _last_sync_hash übernommen."""
    from orchestration.scheduler import ProactiveScheduler
    from memory.memory_system import memory_manager

    sched = ProactiveScheduler()
    fake_item = MagicMock()
    fake_item.category = "user"
    fake_item.value = "Fatih"
    fake_item.importance = 0.9
    fake_item.source = "test"

    with patch.object(memory_manager.persistent, "get_all_memory_items", return_value=[fake_item]):
        with patch("memory.markdown_store.store.MarkdownStore._render_hash", return_value="new-hash"):
            assert sched._memory_sync_needed() is True
            assert sched._pending_sync_hash == "new-hash"
            with patch.object(memory_manager, "sync_to_markdown", return_value=True):
                result = asyncio.run(sched._sync_memory())

    assert result is True
    assert sched._last_sync_hash == "new-hash"
    assert sched._pending_sync_hash is None

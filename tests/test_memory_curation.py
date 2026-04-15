from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from memory.memory_system import MemoryItem, PersistentMemory
from orchestration.memory_curation import (
    ARCHIVE_CATEGORY_PREFIX,
    SUMMARY_CATEGORY,
    _build_semantic_sync_plan,
    build_memory_curation_candidates,
    build_memory_curation_metrics,
    get_memory_curation_status,
    rollback_memory_curation,
    run_memory_curation_mvp,
)


class _FakeSemanticStore:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, str]] = []
        self.deletes: list[tuple[str, str]] = []

    def is_available(self) -> bool:
        return True

    def store_embedding(self, item: MemoryItem) -> str:
        self.upserts.append((item.category, item.key))
        return f"{item.category}:{item.key}"

    def delete_embedding(self, category: str, key: str) -> bool:
        self.deletes.append((category, key))
        return True


@dataclass
class _FakeManager:
    persistent: PersistentMemory
    semantic_store: _FakeSemanticStore
    working_stats: dict

    def get_last_working_memory_stats(self) -> dict:
        return dict(self.working_stats)


def _make_manager(tmp_path: Path) -> _FakeManager:
    persistent = PersistentMemory(db_path=tmp_path / "memory_curation.db")
    return _FakeManager(
        persistent=persistent,
        semantic_store=_FakeSemanticStore(),
        working_stats={"related_selected": 6, "context_chars": 900},
    )


def _item(
    *,
    category: str,
    key: str,
    value: object,
    created_days_ago: int,
    last_used_days_ago: int,
    importance: float = 0.5,
    confidence: float = 0.8,
    source: str = "user_message",
    reason: str = "",
) -> MemoryItem:
    now = datetime.now()
    return MemoryItem(
        category=category,
        key=key,
        value=value,
        importance=importance,
        confidence=confidence,
        reason=reason,
        source=source,
        created_at=now - timedelta(days=created_days_ago),
        last_used=now - timedelta(days=last_used_days_ago),
    )


def _seed_items(manager: _FakeManager) -> None:
    for item in [
        _item(
            category="extracted",
            key="extract_a",
            value="Die letzte Diskussion ueber Robotik drehte sich um Greifer und Safety.",
            created_days_ago=80,
            last_used_days_ago=55,
            importance=0.62,
        ),
        _item(
            category="extracted",
            key="extract_b",
            value="Robotik-Thema: bei mobilen Plattformen war SLAM wiederkehrend relevant.",
            created_days_ago=70,
            last_used_days_ago=48,
            importance=0.58,
        ),
        _item(
            category="working_memory",
            key="scratch_old",
            value="Temporäre Notiz für einen alten Versuchslauf",
            created_days_ago=65,
            last_used_days_ago=61,
            importance=0.32,
            confidence=0.62,
        ),
        _item(
            category="patterns",
            key="pattern_old",
            value="Der Nutzer springt bei offenen Fragen oft zwischen Strategie und Umsetzung.",
            created_days_ago=45,
            last_used_days_ago=39,
            importance=0.64,
            confidence=0.78,
        ),
        _item(
            category="user_profile",
            key="name",
            value="Fatih",
            created_days_ago=20,
            last_used_days_ago=1,
            importance=0.95,
            confidence=0.95,
            source="markdown_sync",
        ),
    ]:
        manager.persistent.store_memory_item(item)


def test_build_memory_curation_candidates_detects_summarize_archive_and_devalue(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    _seed_items(manager)

    candidates = build_memory_curation_candidates(manager=manager, stale_days=30, max_candidates=12)
    actions = {candidate["action"] for candidate in candidates}

    assert "summarize" in actions
    assert "archive" in actions
    assert "devalue" in actions
    summarize = next(candidate for candidate in candidates if candidate["action"] == "summarize")
    assert summarize["category"] == "extracted"
    assert summarize["item_count"] >= 2


def test_run_memory_curation_mvp_applies_actions_and_creates_snapshot(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    _seed_items(manager)

    result = run_memory_curation_mvp(manager=manager, stale_days=30, max_actions=12, dry_run=False)

    assert result["status"] == "complete"
    assert result["snapshot_id"]
    assert result["verification"]["passed"] is True
    assert result["actions_applied"]
    assert result["metrics_after"]["stale_active_items"] < result["metrics_before"]["stale_active_items"]

    items_after = manager.persistent.get_all_memory_items()
    categories_after = {item.category for item in items_after}
    assert SUMMARY_CATEGORY in categories_after
    assert f"{ARCHIVE_CATEGORY_PREFIX}extracted" in categories_after
    assert f"{ARCHIVE_CATEGORY_PREFIX}working_memory" in categories_after

    pattern_item = next(item for item in items_after if item.category == "patterns" and item.key == "pattern_old")
    assert pattern_item.importance < 0.64
    assert "memory_curation_devalue" in pattern_item.reason

    snapshot = manager.persistent.get_memory_curation_snapshot(result["snapshot_id"])
    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert len(snapshot["before_items"]) == 5
    assert len(snapshot["after_items"]) >= 5
    assert ("extracted", "extract_a") in manager.semantic_store.deletes
    assert any(category == SUMMARY_CATEGORY for category, _ in manager.semantic_store.upserts)
    assert ("patterns", "pattern_old") in manager.semantic_store.upserts


def test_run_memory_curation_mvp_dry_run_preserves_state(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    _seed_items(manager)

    before_refs = {(item.category, item.key) for item in manager.persistent.get_all_memory_items()}
    result = run_memory_curation_mvp(manager=manager, stale_days=30, max_actions=12, dry_run=True)

    assert result["status"] == "dry_run"
    assert result["snapshot_id"] == ""
    assert result["actions_applied"] == []
    assert result["candidate_count"] >= 1
    after_refs = {(item.category, item.key) for item in manager.persistent.get_all_memory_items()}
    assert after_refs == before_refs


def test_run_memory_curation_mvp_returns_no_candidates_for_recent_memories(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.persistent.store_memory_item(
        _item(
            category="working_memory",
            key="fresh_note",
            value="Aktuelle Session-Notiz",
            created_days_ago=1,
            last_used_days_ago=1,
            importance=0.3,
            confidence=0.7,
        )
    )

    result = run_memory_curation_mvp(manager=manager, stale_days=30, max_actions=12, dry_run=False)

    assert result["status"] == "no_candidates"
    assert result["snapshot_id"] == ""
    assert result["candidate_count"] == 0
    assert result["verification"]["passed"] is True


def test_build_memory_curation_metrics_distinguishes_active_archived_and_stale(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    _seed_items(manager)
    manager.persistent.store_memory_item(
        _item(
            category=f"{ARCHIVE_CATEGORY_PREFIX}working_memory",
            key="old_archive",
            value={"original_key": "scratch_old"},
            created_days_ago=90,
            last_used_days_ago=90,
            importance=0.2,
            confidence=0.6,
            source="memory_curation",
        )
    )

    metrics = build_memory_curation_metrics(manager.persistent.get_all_memory_items(), manager=manager, stale_days=30)

    assert metrics["active_items"] == 5
    assert metrics["archived_items"] == 1
    assert metrics["stable_active_items"] == 1
    assert metrics["stale_active_items"] >= 3
    assert metrics["working_memory_last_stats"]["related_selected"] == 6


def test_run_memory_curation_mvp_surfaces_verification_failures_honestly(tmp_path: Path, monkeypatch) -> None:
    manager = _make_manager(tmp_path)
    _seed_items(manager)
    monkeypatch.setattr("orchestration.memory_curation.verify_memory_curation_outcome", lambda **_: False)

    result = run_memory_curation_mvp(manager=manager, stale_days=30, max_actions=12, dry_run=False)

    assert result["status"] == "verification_failed"
    assert result["verification"]["passed"] is False
    snapshot = manager.persistent.get_memory_curation_snapshot(result["snapshot_id"])
    assert snapshot is not None
    assert snapshot["status"] == "verification_failed"


def test_build_semantic_sync_plan_only_touches_changed_active_items(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    _seed_items(manager)

    run_result = run_memory_curation_mvp(manager=manager, stale_days=30, max_actions=12, dry_run=False)
    current_items = manager.persistent.get_all_memory_items()
    snapshot = manager.persistent.get_memory_curation_snapshot(run_result["snapshot_id"])
    assert snapshot is not None

    delete_refs, upsert_items = _build_semantic_sync_plan(
        previous_items=current_items,
        restored_items=list(snapshot["before_items"]),
    )

    assert delete_refs == [(SUMMARY_CATEGORY, next(item.key for item in current_items if item.category == SUMMARY_CATEGORY))]
    assert {(item.category, item.key) for item in upsert_items} == {
        ("extracted", "extract_a"),
        ("extracted", "extract_b"),
        ("working_memory", "scratch_old"),
        ("patterns", "pattern_old"),
    }


def test_rollback_memory_curation_restores_original_memory_items(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    _seed_items(manager)
    before_refs = {(item.category, item.key) for item in manager.persistent.get_all_memory_items()}

    run_result = run_memory_curation_mvp(manager=manager, stale_days=30, max_actions=12, dry_run=False)
    manager.semantic_store.upserts.clear()
    manager.semantic_store.deletes.clear()
    rollback_result = rollback_memory_curation(run_result["snapshot_id"], manager=manager)

    assert rollback_result["status"] == "rolled_back"
    restored_refs = {(item.category, item.key) for item in manager.persistent.get_all_memory_items()}
    assert restored_refs == before_refs
    assert SUMMARY_CATEGORY not in {category for category, _ in restored_refs}
    assert ("working_memory", "scratch_old") in restored_refs

    snapshot = manager.persistent.get_memory_curation_snapshot(run_result["snapshot_id"])
    assert snapshot is not None
    assert snapshot["status"] == "rolled_back"
    assert rollback_result["semantic_sync"]["delete_count"] == 1
    assert rollback_result["semantic_sync"]["upsert_count"] == 4
    assert rollback_result["semantic_sync"]["chunk_count"] == 2
    assert snapshot["metadata"]["semantic_sync"]["delete_count"] == 1
    assert snapshot["metadata"]["semantic_sync"]["upsert_count"] == 4
    assert ("extracted", "extract_a") in manager.semantic_store.upserts
    assert ("user_profile", "name") not in manager.semantic_store.upserts
    assert (SUMMARY_CATEGORY, next(item.key for item in snapshot["after_items"] if item.category == SUMMARY_CATEGORY)) in manager.semantic_store.deletes


def test_rollback_memory_curation_returns_missing_snapshot_for_unknown_id(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)

    result = rollback_memory_curation("missing-snapshot", manager=manager)

    assert result["status"] == "missing_snapshot"
    assert result["snapshot_id"] == "missing-snapshot"


def test_get_memory_curation_status_reports_metrics_candidates_and_snapshots(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    _seed_items(manager)
    run_result = run_memory_curation_mvp(manager=manager, stale_days=30, max_actions=12, dry_run=False)

    status = get_memory_curation_status(manager=manager, stale_days=30, limit=5)

    assert status["status"] == "ok"
    assert status["current_metrics"]["archived_items"] >= 1
    assert status["last_snapshots"][0]["snapshot_id"] == run_result["snapshot_id"]
    assert "working_memory_last_stats" in status["current_metrics"]
    assert isinstance(status["pending_candidates"], list)

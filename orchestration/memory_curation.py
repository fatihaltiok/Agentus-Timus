from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Iterable, Mapping, Protocol, TypeVar
import uuid

from memory.memory_system import MemoryItem, memory_manager
from orchestration.autonomy_observation import record_autonomy_observation
from utils.stable_hash import stable_text_digest


ARCHIVE_CATEGORY_PREFIX = "archived::"
SUMMARY_CATEGORY = "summarized_memory"
_SUMMARY_SOURCE = "memory_curation"
_STABLE_CATEGORIES = {"user_profile", "relationships", "self_model", "preference_memory"}
_TOPIC_BOUND_CATEGORIES = {"patterns", "decisions", "extracted", "summarized", SUMMARY_CATEGORY}
_EPHEMERAL_CATEGORIES = {"working_memory", "scratchpad", "session_memory"}
_ROLLBACK_SEMANTIC_SYNC_CHUNK_SIZE = 64
_T = TypeVar("_T")


class MemoryCurationManagerLike(Protocol):
    persistent: Any
    semantic_store: Any

    def get_last_working_memory_stats(self) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class MemoryCurationCandidate:
    candidate_id: str
    action: str
    tier: str
    category: str
    source: str
    reason: str
    item_keys: tuple[str, ...]
    item_count: int
    last_used_age_days: int
    average_importance: float


def _normalize_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _normalize_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _now() -> datetime:
    return datetime.now()


def _days_since(value: datetime, now: datetime) -> int:
    return max(0, int((now - value).days))


def _value_preview(value: Any, *, limit: int = 120) -> str:
    if isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def classify_memory_curation_tier(
    category: str,
    importance: float,
    confidence: float,
    source: str = "",
) -> str:
    normalized_category = str(category or "").strip().lower()
    normalized_source = str(source or "").strip().lower()
    normalized_importance = max(0.0, min(1.0, _normalize_float(importance, default=0.5)))
    normalized_confidence = max(0.0, min(1.0, _normalize_float(confidence, default=1.0)))

    if normalized_category.startswith(ARCHIVE_CATEGORY_PREFIX):
        return "archived"
    if normalized_category in _STABLE_CATEGORIES or normalized_source in {"self_model", "meta_preference_memory"}:
        return "stable"
    if normalized_category in _EPHEMERAL_CATEGORIES:
        return "ephemeral"
    if normalized_category in _TOPIC_BOUND_CATEGORIES:
        return "topic_bound"
    if normalized_importance >= 0.88 and normalized_confidence >= 0.85:
        return "stable"
    if normalized_importance <= 0.45 and normalized_confidence <= 0.75:
        return "ephemeral"
    return "topic_bound"


def decide_memory_curation_action(
    tier: str,
    *,
    last_used_age_days: int,
    importance: float,
    group_size: int,
) -> str:
    normalized_tier = str(tier or "").strip().lower()
    safe_age = max(0, _normalize_int(last_used_age_days))
    normalized_importance = max(0.0, min(1.0, _normalize_float(importance, default=0.5)))
    safe_group_size = max(0, _normalize_int(group_size))

    if normalized_tier in {"stable", "archived"}:
        return "keep"
    if safe_group_size >= 2 and safe_age >= 14:
        return "summarize"
    if normalized_tier == "ephemeral" and safe_age >= 30 and normalized_importance <= 0.55:
        return "archive"
    if normalized_tier == "topic_bound" and safe_age >= 30 and normalized_importance <= 0.75:
        return "devalue"
    return "keep"


def verify_memory_curation_outcome(
    *,
    before_active_items: int,
    after_active_items: int,
    before_stale_active_items: int,
    after_stale_active_items: int,
    before_stable_items: int,
    after_stable_items: int,
) -> bool:
    return (
        after_stale_active_items <= before_stale_active_items
        and after_stable_items >= before_stable_items
        and after_active_items <= (before_active_items + 1)
    )


def _manager(manager: MemoryCurationManagerLike | None = None) -> MemoryCurationManagerLike:
    return manager or memory_manager


def _active_items(items: Iterable[MemoryItem]) -> list[MemoryItem]:
    return [item for item in items if not str(item.category or "").startswith(ARCHIVE_CATEGORY_PREFIX)]


def _active_average_importance(items: Iterable[MemoryItem]) -> float:
    materialized = list(items)
    if not materialized:
        return 0.0
    return round(sum(float(item.importance or 0.0) for item in materialized) / len(materialized), 3)


def build_memory_curation_metrics(
    items: Iterable[MemoryItem],
    *,
    manager: MemoryCurationManagerLike | None = None,
    stale_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _now()
    safe_stale_days = max(1, _normalize_int(stale_days, default=30))
    all_items = list(items)
    active_items = _active_items(all_items)
    archived_items = [item for item in all_items if str(item.category or "").startswith(ARCHIVE_CATEGORY_PREFIX)]
    summary_items = [item for item in active_items if str(item.category or "") == SUMMARY_CATEGORY]

    tier_counts: dict[str, int] = {"stable": 0, "topic_bound": 0, "ephemeral": 0, "archived": 0}
    stale_active_items = 0
    stable_active_items = 0
    for item in all_items:
        tier = classify_memory_curation_tier(item.category, item.importance, item.confidence, item.source)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if tier == "stable" and not str(item.category or "").startswith(ARCHIVE_CATEGORY_PREFIX):
            stable_active_items += 1
        if tier not in {"stable", "archived"} and not str(item.category or "").startswith(ARCHIVE_CATEGORY_PREFIX):
            if _days_since(item.last_used, current) >= safe_stale_days:
                stale_active_items += 1

    working_stats = {}
    if manager is not None:
        try:
            working_stats = dict(manager.get_last_working_memory_stats() or {})
        except Exception:
            working_stats = {}

    return {
        "total_items": len(all_items),
        "active_items": len(active_items),
        "archived_items": len(archived_items),
        "summary_items": len(summary_items),
        "stale_active_items": stale_active_items,
        "stable_active_items": stable_active_items,
        "active_average_importance": _active_average_importance(active_items),
        "tier_counts": tier_counts,
        "working_memory_last_stats": working_stats,
        "stale_days": safe_stale_days,
    }


def build_memory_curation_candidates(
    *,
    manager: MemoryCurationManagerLike | None = None,
    stale_days: int = 30,
    max_candidates: int = 12,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    active_manager = _manager(manager)
    current = now or _now()
    safe_limit = max(1, _normalize_int(max_candidates, default=12))
    safe_stale_days = max(1, _normalize_int(stale_days, default=30))
    items = active_manager.persistent.get_all_memory_items()

    group_map: dict[tuple[str, str, str], list[tuple[MemoryItem, int]]] = {}
    consumed_ids: set[tuple[str, str]] = set()
    candidates: list[MemoryCurationCandidate] = []

    for item in items:
        tier = classify_memory_curation_tier(item.category, item.importance, item.confidence, item.source)
        if tier in {"stable", "archived"}:
            continue
        if str(item.category or "") == SUMMARY_CATEGORY:
            continue
        age = _days_since(item.last_used, current)
        if age < max(14, safe_stale_days // 2):
            continue
        key = (tier, str(item.category or ""), str(item.source or ""))
        group_map.setdefault(key, []).append((item, age))

    for (tier, category, source), grouped_items in group_map.items():
        if len(grouped_items) < 2:
            continue
        grouped_items.sort(key=lambda entry: (-entry[1], str(entry[0].key or "")))
        items_only = [entry[0] for entry in grouped_items[:5]]
        avg_importance = round(
            sum(float(item.importance or 0.0) for item in items_only) / max(1, len(items_only)),
            3,
        )
        max_age = max(_days_since(item.last_used, current) for item in items_only)
        digest = stable_text_digest("|".join(f"{item.category}:{item.key}" for item in items_only), hex_chars=10)
        candidates.append(
            MemoryCurationCandidate(
                candidate_id=f"summarize:{category}:{digest}",
                action="summarize",
                tier=tier,
                category=category,
                source=source,
                reason=f"group:{category}:{source or 'unknown'}",
                item_keys=tuple(item.key for item in items_only),
                item_count=len(items_only),
                last_used_age_days=max_age,
                average_importance=avg_importance,
            )
        )
        consumed_ids.update((item.category, item.key) for item in items_only)

    for item in items:
        item_ref = (item.category, item.key)
        if item_ref in consumed_ids:
            continue
        tier = classify_memory_curation_tier(item.category, item.importance, item.confidence, item.source)
        age = _days_since(item.last_used, current)
        action = decide_memory_curation_action(
            tier,
            last_used_age_days=age,
            importance=float(item.importance or 0.0),
            group_size=1,
        )
        if action == "keep":
            continue
        candidates.append(
            MemoryCurationCandidate(
                candidate_id=f"{action}:{item.category}:{item.key}",
                action=action,
                tier=tier,
                category=item.category,
                source=item.source,
                reason=f"stale:{age}d",
                item_keys=(item.key,),
                item_count=1,
                last_used_age_days=age,
                average_importance=round(float(item.importance or 0.0), 3),
            )
        )

    action_priority = {"summarize": 0, "archive": 1, "devalue": 2}
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            action_priority.get(candidate.action, 9),
            -candidate.item_count,
            -candidate.last_used_age_days,
            candidate.candidate_id,
        ),
    )

    result: list[dict[str, Any]] = []
    for candidate in ordered[:safe_limit]:
        result.append(
            {
                "candidate_id": candidate.candidate_id,
                "action": candidate.action,
                "tier": candidate.tier,
                "category": candidate.category,
                "source": candidate.source,
                "reason": candidate.reason,
                "item_keys": list(candidate.item_keys),
                "item_count": candidate.item_count,
                "last_used_age_days": candidate.last_used_age_days,
                "average_importance": candidate.average_importance,
            }
        )
    return result


def _store_active_item(manager: MemoryCurationManagerLike, item: MemoryItem) -> None:
    manager.persistent.store_memory_item(item)
    semantic_store = getattr(manager, "semantic_store", None)
    if semantic_store and hasattr(semantic_store, "is_available") and semantic_store.is_available():
        semantic_store.store_embedding(item)


def _delete_active_item(manager: MemoryCurationManagerLike, category: str, key: str) -> None:
    manager.persistent.delete_memory_item(category, key)
    semantic_store = getattr(manager, "semantic_store", None)
    if semantic_store and hasattr(semantic_store, "is_available") and semantic_store.is_available():
        semantic_store.delete_embedding(category, key)


def _archive_item(
    manager: MemoryCurationManagerLike,
    item: MemoryItem,
    *,
    archived_at: datetime,
    reason: str,
) -> MemoryItem:
    archived_item = MemoryItem(
        category=f"{ARCHIVE_CATEGORY_PREFIX}{item.category}",
        key=item.key,
        value={
            "original_category": item.category,
            "original_key": item.key,
            "original_value": item.value,
            "archived_at": archived_at.isoformat(),
            "archived_reason": reason,
            "original_importance": item.importance,
            "original_confidence": item.confidence,
            "original_source": item.source,
        },
        importance=item.importance,
        confidence=item.confidence,
        reason=f"memory_curation_archive:{reason}",
        source=_SUMMARY_SOURCE,
        created_at=item.created_at,
        last_used=archived_at,
    )
    manager.persistent.store_memory_item(archived_item)
    _delete_active_item(manager, item.category, item.key)
    return archived_item


def _apply_devalue_item(
    manager: MemoryCurationManagerLike,
    item: MemoryItem,
    *,
    reason: str,
) -> MemoryItem:
    devalued_item = MemoryItem(
        category=item.category,
        key=item.key,
        value=item.value,
        importance=max(0.1, round(float(item.importance or 0.0) - 0.2, 3)),
        confidence=max(0.1, round(float(item.confidence or 0.0) - 0.1, 3)),
        reason=f"{item.reason}; memory_curation_devalue:{reason}".strip("; "),
        source=item.source,
        created_at=item.created_at,
        last_used=item.last_used,
    )
    _store_active_item(manager, devalued_item)
    return devalued_item


def _build_summary_item(
    items: list[MemoryItem],
    *,
    category: str,
    source: str,
    now: datetime,
) -> MemoryItem:
    previews = [_value_preview(item.value, limit=90) for item in items]
    summary_text = " | ".join(preview for preview in previews if preview)[:320]
    digest = stable_text_digest("|".join(f"{item.category}:{item.key}" for item in items), hex_chars=10)
    return MemoryItem(
        category=SUMMARY_CATEGORY,
        key=f"summary_{digest}",
        value={
            "summary": summary_text,
            "source_category": category,
            "source": source,
            "source_keys": [item.key for item in items],
            "original_count": len(items),
        },
        importance=max(0.55, round(sum(float(item.importance or 0.0) for item in items) / max(1, len(items)), 3)),
        confidence=max(0.6, round(sum(float(item.confidence or 0.0) for item in items) / max(1, len(items)), 3)),
        reason="memory_curation_summary",
        source=_SUMMARY_SOURCE,
        created_at=now,
        last_used=now,
    )


def _iter_chunks(values: list[_T], chunk_size: int) -> Iterable[list[_T]]:
    safe_chunk_size = max(1, _normalize_int(chunk_size, default=_ROLLBACK_SEMANTIC_SYNC_CHUNK_SIZE))
    for index in range(0, len(values), safe_chunk_size):
        yield values[index:index + safe_chunk_size]


def _semantic_item_signature(item: MemoryItem) -> str:
    payload = {
        "category": item.category,
        "key": item.key,
        "value": item.value,
        "importance": round(float(item.importance or 0.0), 6),
        "confidence": round(float(item.confidence or 0.0), 6),
        "reason": str(item.reason or ""),
        "source": str(item.source or ""),
        "created_at": item.created_at.isoformat(),
    }
    return stable_text_digest(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str), hex_chars=16)


def _build_active_item_map(items: Iterable[MemoryItem]) -> dict[tuple[str, str], MemoryItem]:
    return {
        (item.category, item.key): item
        for item in items
        if not str(item.category or "").startswith(ARCHIVE_CATEGORY_PREFIX)
    }


def _build_semantic_sync_plan(
    *,
    previous_items: list[MemoryItem],
    restored_items: list[MemoryItem],
) -> tuple[list[tuple[str, str]], list[MemoryItem]]:
    previous_active = _build_active_item_map(previous_items)
    restored_active = _build_active_item_map(restored_items)

    delete_refs = sorted(previous_active.keys() - restored_active.keys())
    upsert_items: list[MemoryItem] = []
    for ref, item in restored_active.items():
        previous_item = previous_active.get(ref)
        if previous_item is None or _semantic_item_signature(previous_item) != _semantic_item_signature(item):
            upsert_items.append(item)
    return delete_refs, upsert_items


def _record_memory_curation_progress(
    event_type: str,
    *,
    snapshot_id: str,
    stage: str,
    processed: int,
    total: int,
    chunk_size: int,
) -> None:
    try:
        record_autonomy_observation(
            event_type,
            {
                "snapshot_id": snapshot_id,
                "stage": stage,
                "processed": processed,
                "total": total,
                "chunk_size": chunk_size,
            },
        )
    except Exception:
        pass


def _sync_semantic_store_diff(
    manager: MemoryCurationManagerLike,
    *,
    previous_items: list[MemoryItem],
    restored_items: list[MemoryItem],
    snapshot_id: str,
    chunk_size: int = _ROLLBACK_SEMANTIC_SYNC_CHUNK_SIZE,
) -> dict[str, int]:
    semantic_store = getattr(manager, "semantic_store", None)
    if not semantic_store or not hasattr(semantic_store, "is_available") or not semantic_store.is_available():
        return {"delete_count": 0, "upsert_count": 0, "chunk_count": 0}

    delete_refs, upsert_items = _build_semantic_sync_plan(
        previous_items=previous_items,
        restored_items=restored_items,
    )
    safe_chunk_size = max(1, _normalize_int(chunk_size, default=_ROLLBACK_SEMANTIC_SYNC_CHUNK_SIZE))
    total_operations = len(delete_refs) + len(upsert_items)
    processed = 0
    chunk_count = 0

    if total_operations:
        _record_memory_curation_progress(
            "memory_curation_rollback_progress",
            snapshot_id=snapshot_id,
            stage="semantic_sync_started",
            processed=0,
            total=total_operations,
            chunk_size=safe_chunk_size,
        )

    for chunk in _iter_chunks(delete_refs, safe_chunk_size):
        for category, key in chunk:
            semantic_store.delete_embedding(category, key)
        processed += len(chunk)
        chunk_count += 1
        _record_memory_curation_progress(
            "memory_curation_rollback_progress",
            snapshot_id=snapshot_id,
            stage="semantic_delete",
            processed=processed,
            total=total_operations,
            chunk_size=safe_chunk_size,
        )

    for chunk in _iter_chunks(upsert_items, safe_chunk_size):
        for item in chunk:
            semantic_store.store_embedding(item)
        processed += len(chunk)
        chunk_count += 1
        _record_memory_curation_progress(
            "memory_curation_rollback_progress",
            snapshot_id=snapshot_id,
            stage="semantic_upsert",
            processed=processed,
            total=total_operations,
            chunk_size=safe_chunk_size,
        )

    if total_operations:
        _record_memory_curation_progress(
            "memory_curation_rollback_progress",
            snapshot_id=snapshot_id,
            stage="semantic_sync_completed",
            processed=processed,
            total=total_operations,
            chunk_size=safe_chunk_size,
        )
    return {
        "delete_count": len(delete_refs),
        "upsert_count": len(upsert_items),
        "chunk_count": chunk_count,
    }


def get_memory_curation_status(
    *,
    manager: MemoryCurationManagerLike | None = None,
    stale_days: int = 30,
    limit: int = 5,
) -> dict[str, Any]:
    active_manager = _manager(manager)
    items = active_manager.persistent.get_all_memory_items()
    return {
        "status": "ok",
        "current_metrics": build_memory_curation_metrics(
            items,
            manager=active_manager,
            stale_days=stale_days,
        ),
        "last_snapshots": active_manager.persistent.list_memory_curation_snapshots(limit=limit),
        "pending_candidates": build_memory_curation_candidates(
            manager=active_manager,
            stale_days=stale_days,
            max_candidates=limit,
        ),
    }


def run_memory_curation_mvp(
    *,
    manager: MemoryCurationManagerLike | None = None,
    stale_days: int = 30,
    max_actions: int = 12,
    dry_run: bool = False,
) -> dict[str, Any]:
    active_manager = _manager(manager)
    current = _now()
    safe_stale_days = max(1, _normalize_int(stale_days, default=30))
    safe_max_actions = max(1, _normalize_int(max_actions, default=12))

    before_items = active_manager.persistent.get_all_memory_items()
    metrics_before = build_memory_curation_metrics(
        before_items,
        manager=active_manager,
        stale_days=safe_stale_days,
        now=current,
    )
    candidates = build_memory_curation_candidates(
        manager=active_manager,
        stale_days=safe_stale_days,
        max_candidates=safe_max_actions,
        now=current,
    )

    if dry_run or not candidates:
        return {
            "status": "dry_run" if dry_run else "no_candidates",
            "dry_run": bool(dry_run),
            "snapshot_id": "",
            "candidate_count": len(candidates),
            "candidates": candidates,
            "metrics_before": metrics_before,
            "metrics_after": metrics_before,
            "verification": {
                "passed": True,
                "reason": "no_mutation",
            },
            "actions_applied": [],
        }

    snapshot_id = uuid.uuid4().hex[:12]
    active_manager.persistent.store_memory_curation_snapshot(
        snapshot_id=snapshot_id,
        status="started",
        before_items=before_items,
        metrics_before=metrics_before,
        metadata={
            "stale_days": safe_stale_days,
            "max_actions": safe_max_actions,
            "candidate_count": len(candidates),
        },
    )
    try:
        record_autonomy_observation(
            "memory_curation_started",
            {
                "snapshot_id": snapshot_id,
                "candidate_count": len(candidates),
                "stale_days": safe_stale_days,
                "max_actions": safe_max_actions,
            },
        )
    except Exception:
        pass

    actions_applied: list[dict[str, Any]] = []
    items_by_ref = {(item.category, item.key): item for item in before_items}

    for candidate in candidates[:safe_max_actions]:
        action = str(candidate.get("action") or "")
        keys = [str(key) for key in (candidate.get("item_keys") or []) if str(key)]
        category = str(candidate.get("category") or "")
        source = str(candidate.get("source") or "")
        reason = str(candidate.get("reason") or "")
        if action == "summarize":
            grouped_items = [
                items_by_ref[(category, key)]
                for key in keys
                if (category, key) in items_by_ref
            ]
            if len(grouped_items) < 2:
                continue
            summary_item = _build_summary_item(grouped_items, category=category, source=source, now=current)
            _store_active_item(active_manager, summary_item)
            for item in grouped_items:
                _archive_item(active_manager, item, archived_at=current, reason=reason)
            actions_applied.append(
                {
                    "action": "summarize",
                    "summary_key": summary_item.key,
                    "source_category": category,
                    "source_keys": keys,
                    "archived_count": len(grouped_items),
                }
            )
            try:
                record_autonomy_observation(
                    "memory_summarized",
                    {
                        "snapshot_id": snapshot_id,
                        "summary_key": summary_item.key,
                        "source_category": category,
                        "source_count": len(grouped_items),
                    },
                )
            except Exception:
                pass
        elif action == "archive" and len(keys) == 1:
            item = items_by_ref.get((category, keys[0]))
            if not item:
                continue
            archived_item = _archive_item(active_manager, item, archived_at=current, reason=reason)
            actions_applied.append(
                {
                    "action": "archive",
                    "archived_key": archived_item.key,
                    "source_category": category,
                }
            )
            try:
                record_autonomy_observation(
                    "memory_archived",
                    {
                        "snapshot_id": snapshot_id,
                        "archived_category": archived_item.category,
                        "archived_key": archived_item.key,
                        "source_category": category,
                    },
                )
            except Exception:
                pass
        elif action == "devalue" and len(keys) == 1:
            item = items_by_ref.get((category, keys[0]))
            if not item:
                continue
            devalued = _apply_devalue_item(active_manager, item, reason=reason)
            actions_applied.append(
                {
                    "action": "devalue",
                    "key": devalued.key,
                    "category": devalued.category,
                    "importance": devalued.importance,
                    "confidence": devalued.confidence,
                }
            )
            try:
                record_autonomy_observation(
                    "memory_devalued",
                    {
                        "snapshot_id": snapshot_id,
                        "category": devalued.category,
                        "key": devalued.key,
                        "importance": devalued.importance,
                        "confidence": devalued.confidence,
                    },
                )
            except Exception:
                pass

    after_items = active_manager.persistent.get_all_memory_items()
    metrics_after = build_memory_curation_metrics(
        after_items,
        manager=active_manager,
        stale_days=safe_stale_days,
        now=current,
    )
    verification_passed = verify_memory_curation_outcome(
        before_active_items=int(metrics_before.get("active_items") or 0),
        after_active_items=int(metrics_after.get("active_items") or 0),
        before_stale_active_items=int(metrics_before.get("stale_active_items") or 0),
        after_stale_active_items=int(metrics_after.get("stale_active_items") or 0),
        before_stable_items=int(metrics_before.get("stable_active_items") or 0),
        after_stable_items=int(metrics_after.get("stable_active_items") or 0),
    )
    verification = {
        "passed": verification_passed,
        "reason": "metrics_improved_or_stable" if verification_passed else "stale_or_stable_regression",
    }

    active_manager.persistent.store_memory_curation_snapshot(
        snapshot_id=snapshot_id,
        status="completed" if verification_passed else "verification_failed",
        before_items=before_items,
        metrics_before=metrics_before,
        metadata={
            "stale_days": safe_stale_days,
            "max_actions": safe_max_actions,
            "candidate_count": len(candidates),
            "actions_applied": actions_applied,
        },
        after_items=after_items,
        metrics_after=metrics_after,
    )
    try:
        record_autonomy_observation(
            "memory_curation_completed",
            {
                "snapshot_id": snapshot_id,
                "actions_applied": len(actions_applied),
                "verification_passed": verification_passed,
            },
        )
    except Exception:
        pass

    return {
        "status": "complete" if verification_passed else "verification_failed",
        "dry_run": False,
        "snapshot_id": snapshot_id,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "actions_applied": actions_applied,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "verification": verification,
    }


def rollback_memory_curation(
    snapshot_id: str,
    *,
    manager: MemoryCurationManagerLike | None = None,
) -> dict[str, Any]:
    active_manager = _manager(manager)
    snapshot = active_manager.persistent.get_memory_curation_snapshot(snapshot_id)
    if not snapshot:
        return {
            "status": "missing_snapshot",
            "snapshot_id": snapshot_id,
        }

    before_items = list(snapshot.get("before_items") or [])
    current_items = active_manager.persistent.get_all_memory_items()
    current_metrics = build_memory_curation_metrics(
        current_items,
        manager=active_manager,
        stale_days=int((snapshot.get("metrics_before") or {}).get("stale_days") or 30),
    )
    active_manager.persistent.store_memory_curation_snapshot(
        snapshot_id=snapshot_id,
        status="rolling_back",
        before_items=before_items,
        metrics_before=dict(snapshot.get("metrics_before") or {}),
        metadata={
            **dict(snapshot.get("metadata") or {}),
            "rollback_started_at": _now().isoformat(),
        },
        after_items=current_items,
        metrics_after=current_metrics,
    )
    _record_memory_curation_progress(
        "memory_curation_rollback_started",
        snapshot_id=snapshot_id,
        stage="rollback_started",
        processed=0,
        total=max(1, len(current_items)),
        chunk_size=_ROLLBACK_SEMANTIC_SYNC_CHUNK_SIZE,
    )
    active_manager.persistent.replace_all_memory_items(before_items)
    semantic_sync = _sync_semantic_store_diff(
        active_manager,
        previous_items=current_items,
        restored_items=before_items,
        snapshot_id=snapshot_id,
    )

    metrics_after = build_memory_curation_metrics(
        before_items,
        manager=active_manager,
        stale_days=int((snapshot.get("metrics_before") or {}).get("stale_days") or 30),
    )
    active_manager.persistent.store_memory_curation_snapshot(
        snapshot_id=snapshot_id,
        status="rolled_back",
        before_items=before_items,
        metrics_before=dict(snapshot.get("metrics_before") or {}),
        metadata={
            **dict(snapshot.get("metadata") or {}),
            "rollback_started_at": dict(snapshot.get("metadata") or {}).get("rollback_started_at", ""),
            "semantic_sync": semantic_sync,
        },
        after_items=current_items,
        metrics_after=metrics_after,
    )
    try:
        record_autonomy_observation(
            "memory_curation_rollback",
            {
                "snapshot_id": snapshot_id,
                "restored_items": len(before_items),
                "semantic_sync": semantic_sync,
            },
        )
    except Exception:
        pass
    return {
        "status": "rolled_back",
        "snapshot_id": snapshot_id,
        "restored_items": len(before_items),
        "metrics_after": metrics_after,
        "semantic_sync": semantic_sync,
    }

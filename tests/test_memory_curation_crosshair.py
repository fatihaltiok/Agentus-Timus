from __future__ import annotations

from datetime import datetime

import deal

from orchestration.memory_curation import (
    ARCHIVE_CATEGORY_PREFIX,
    SUMMARY_CATEGORY,
    _build_semantic_sync_plan,
    classify_memory_curation_tier,
    decide_memory_curation_action,
    filter_memory_curation_candidates,
    verify_memory_curation_outcome,
)
from memory.memory_system import MemoryItem


@deal.post(lambda r: r is True)
def _contract_archived_prefix_classifies_as_archived() -> bool:
    return classify_memory_curation_tier(f"{ARCHIVE_CATEGORY_PREFIX}patterns", 0.4, 0.4, "x") == "archived"


@deal.post(lambda r: r is True)
def _contract_stable_tier_never_archives() -> bool:
    return decide_memory_curation_action("stable", last_used_age_days=120, importance=0.1, group_size=6) == "keep"


@deal.post(lambda r: r is True)
def _contract_old_ephemeral_low_importance_archives() -> bool:
    return decide_memory_curation_action("ephemeral", last_used_age_days=45, importance=0.2, group_size=1) == "archive"


@deal.post(lambda r: r is True)
def _contract_multi_item_topic_groups_prioritize_summary() -> bool:
    return decide_memory_curation_action("topic_bound", last_used_age_days=21, importance=0.9, group_size=3) == "summarize"


@deal.post(lambda r: r is True)
def _contract_non_regressive_verification_passes() -> bool:
    return verify_memory_curation_outcome(
        before_active_items=10,
        after_active_items=9,
        before_stale_active_items=4,
        after_stale_active_items=2,
        before_stable_items=3,
        after_stable_items=3,
    )


@deal.post(lambda r: r is True)
def _contract_stale_regression_fails_verification() -> bool:
    return not verify_memory_curation_outcome(
        before_active_items=10,
        after_active_items=12,
        before_stale_active_items=2,
        after_stale_active_items=3,
        before_stable_items=4,
        after_stable_items=3,
    )


@deal.post(lambda r: r is True)
def _contract_semantic_sync_plan_only_touches_active_diff() -> bool:
    now = datetime(2026, 4, 15, 10, 0, 0)
    unchanged = MemoryItem(
        category="user_profile",
        key="name",
        value="Fatih",
        importance=0.95,
        confidence=0.95,
        source="markdown_sync",
        created_at=now,
        last_used=now,
    )
    summary = MemoryItem(
        category=SUMMARY_CATEGORY,
        key="summary_x",
        value={"summary": "old grouped memory"},
        importance=0.7,
        confidence=0.8,
        source="memory_curation",
        created_at=now,
        last_used=now,
    )
    restored = MemoryItem(
        category="working_memory",
        key="scratch_old",
        value="tmp",
        importance=0.3,
        confidence=0.7,
        source="user_message",
        created_at=now,
        last_used=now,
    )
    delete_refs, upsert_items = _build_semantic_sync_plan(
        previous_items=[unchanged, summary],
        restored_items=[unchanged, restored],
    )
    return delete_refs == [(SUMMARY_CATEGORY, "summary_x")] and [
        (item.category, item.key) for item in upsert_items
    ] == [("working_memory", "scratch_old")]


@deal.post(lambda r: r is True)
def _contract_candidate_filter_respects_limit_and_allowlists() -> bool:
    candidates = [
        {"candidate_id": "c1", "action": "summarize", "category": "decisions"},
        {"candidate_id": "c2", "action": "archive", "category": "working_memory"},
        {"candidate_id": "c3", "action": "devalue", "category": "patterns"},
    ]
    filtered = filter_memory_curation_candidates(
        candidates,
        allowed_actions=["summarize", "devalue"],
        allowed_categories=["decisions", "patterns"],
        limit=2,
    )
    return len(filtered) <= 2 and [
        (item["action"], item["category"]) for item in filtered
    ] == [("summarize", "decisions"), ("devalue", "patterns")]

from __future__ import annotations

import deal

from orchestration.memory_curation import (
    ARCHIVE_CATEGORY_PREFIX,
    classify_memory_curation_tier,
    decide_memory_curation_action,
    verify_memory_curation_outcome,
)


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

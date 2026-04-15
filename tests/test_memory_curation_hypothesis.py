from __future__ import annotations

from hypothesis import given, strategies as st

from orchestration.memory_curation import (
    ARCHIVE_CATEGORY_PREFIX,
    classify_memory_curation_tier,
    decide_memory_curation_action,
    filter_memory_curation_candidates,
    should_block_memory_curation_retrieval_backpressure,
    verify_memory_curation_retrieval_quality,
    verify_memory_curation_outcome,
)


@given(
    category=st.sampled_from(["user_profile", "relationships", "self_model", "preference_memory"]),
    importance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    source=st.text(max_size=20),
)
def test_hypothesis_stable_categories_remain_stable(
    category: str,
    importance: float,
    confidence: float,
    source: str,
) -> None:
    assert classify_memory_curation_tier(category, importance, confidence, source) == "stable"


@given(
    suffix=st.text(min_size=1, max_size=20),
    importance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_archived_prefix_always_classifies_as_archived(
    suffix: str,
    importance: float,
    confidence: float,
) -> None:
    assert classify_memory_curation_tier(f"{ARCHIVE_CATEGORY_PREFIX}{suffix}", importance, confidence, "x") == "archived"


@given(
    age_days=st.integers(min_value=0, max_value=180),
    importance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_stable_and_archived_items_never_produce_mutating_actions(
    age_days: int,
    importance: float,
) -> None:
    assert decide_memory_curation_action("stable", last_used_age_days=age_days, importance=importance, group_size=4) == "keep"
    assert decide_memory_curation_action("archived", last_used_age_days=age_days, importance=importance, group_size=4) == "keep"


@given(
    age_days=st.integers(min_value=14, max_value=365),
    group_size=st.integers(min_value=2, max_value=12),
    importance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_old_multi_item_groups_are_summarized_before_other_actions(
    age_days: int,
    group_size: int,
    importance: float,
) -> None:
    assert decide_memory_curation_action(
        "topic_bound",
        last_used_age_days=age_days,
        importance=importance,
        group_size=group_size,
    ) == "summarize"


@given(
    age_days=st.integers(min_value=30, max_value=365),
    importance=st.floats(min_value=0.0, max_value=0.55, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_old_low_importance_ephemeral_items_archive(
    age_days: int,
    importance: float,
) -> None:
    assert decide_memory_curation_action(
        "ephemeral",
        last_used_age_days=age_days,
        importance=importance,
        group_size=1,
    ) == "archive"


@given(
    before_active=st.integers(min_value=1, max_value=200),
    before_stale=st.integers(min_value=0, max_value=50),
    before_stable=st.integers(min_value=0, max_value=50),
)
def test_hypothesis_verification_accepts_non_regressive_outcomes(
    before_active: int,
    before_stale: int,
    before_stable: int,
) -> None:
    after_stale = 0 if before_stale == 0 else before_stale - 1
    after_active = max(0, before_active - 1)
    after_stable = before_stable
    assert verify_memory_curation_outcome(
        before_active_items=before_active,
        after_active_items=after_active,
        before_stale_active_items=before_stale,
        after_stale_active_items=after_stale,
        before_stable_items=before_stable,
        after_stable_items=after_stable,
    )


@given(
    before_active=st.integers(min_value=1, max_value=200),
    before_stale=st.integers(min_value=0, max_value=50),
    before_stable=st.integers(min_value=0, max_value=50),
)
def test_hypothesis_verification_rejects_stale_or_stable_regression(
    before_active: int,
    before_stale: int,
    before_stable: int,
) -> None:
    assert not verify_memory_curation_outcome(
        before_active_items=before_active,
        after_active_items=before_active + 2,
        before_stale_active_items=before_stale,
        after_stale_active_items=before_stale + 1,
        before_stable_items=before_stable,
        after_stable_items=max(0, before_stable - 1),
    )


@given(
    candidates=st.lists(
        st.fixed_dictionaries(
            {
                "action": st.sampled_from(["summarize", "archive", "devalue", "keep"]),
                "category": st.sampled_from(["decisions", "patterns", "working_memory", "extracted", "user_profile"]),
                "candidate_id": st.text(max_size=12),
            }
        ),
        max_size=20,
    ),
    allowed_actions=st.lists(
        st.sampled_from(["summarize", "archive", "devalue", "keep"]),
        unique=True,
        max_size=4,
    ),
    allowed_categories=st.lists(
        st.sampled_from(["decisions", "patterns", "working_memory", "extracted", "user_profile"]),
        unique=True,
        max_size=5,
    ),
    limit=st.integers(min_value=1, max_value=8),
)
def test_hypothesis_filter_memory_curation_candidates_respects_allowlists_and_limit(
    candidates: list[dict[str, str]],
    allowed_actions: list[str],
    allowed_categories: list[str],
    limit: int,
) -> None:
    filtered = filter_memory_curation_candidates(
        candidates,
        allowed_actions=allowed_actions,
        allowed_categories=allowed_categories,
        limit=limit,
    )

    assert len(filtered) <= limit
    if allowed_actions:
        assert {str(item["action"]) for item in filtered} <= set(allowed_actions)
    if allowed_categories:
        assert {str(item["category"]) for item in filtered} <= set(allowed_categories)


@given(
    avg_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    hit_rate_at_3=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    useful_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    wrong_top1_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    forbidden_top1_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_retrieval_quality_accepts_equal_or_better_outcomes(
    avg_score: float,
    hit_rate_at_3: float,
    useful_rate: float,
    wrong_top1_rate: float,
    forbidden_top1_rate: float,
) -> None:
    before = {
        "total_cases": 3,
        "avg_score": avg_score,
        "hit_rate_at_3": hit_rate_at_3,
        "useful_rate": useful_rate,
        "wrong_top1_rate": wrong_top1_rate,
        "forbidden_top1_rate": forbidden_top1_rate,
    }
    after = {
        "total_cases": 3,
        "avg_score": min(1.0, avg_score + 0.05),
        "hit_rate_at_3": min(1.0, hit_rate_at_3 + 0.05),
        "useful_rate": min(1.0, useful_rate + 0.05),
        "wrong_top1_rate": max(0.0, wrong_top1_rate - 0.05),
        "forbidden_top1_rate": max(0.0, forbidden_top1_rate - 0.05),
    }

    assert verify_memory_curation_retrieval_quality(before_summary=before, after_summary=after)


@given(
    avg_score=st.floats(min_value=0.2, max_value=1.0, allow_nan=False, allow_infinity=False),
    hit_rate_at_3=st.floats(min_value=0.2, max_value=1.0, allow_nan=False, allow_infinity=False),
    useful_rate=st.floats(min_value=0.2, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_retrieval_quality_rejects_clear_score_and_hit_regressions(
    avg_score: float,
    hit_rate_at_3: float,
    useful_rate: float,
) -> None:
    before = {
        "total_cases": 4,
        "avg_score": avg_score,
        "hit_rate_at_3": hit_rate_at_3,
        "useful_rate": useful_rate,
        "wrong_top1_rate": 0.0,
        "forbidden_top1_rate": 0.0,
    }
    after = {
        "total_cases": 4,
        "avg_score": max(0.0, avg_score - 0.3),
        "hit_rate_at_3": max(0.0, hit_rate_at_3 - 0.4),
        "useful_rate": max(0.0, useful_rate - 0.4),
        "wrong_top1_rate": 0.6,
        "forbidden_top1_rate": 0.3,
    }

    assert not verify_memory_curation_retrieval_quality(before_summary=before, after_summary=after)


@given(
    evaluated_runs=st.integers(min_value=0, max_value=2),
    pass_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    failed_runs=st.integers(min_value=0, max_value=5),
    rolled_back_runs=st.integers(min_value=0, max_value=5),
)
def test_hypothesis_retrieval_backpressure_never_blocks_before_minimum_history(
    evaluated_runs: int,
    pass_rate: float,
    failed_runs: int,
    rolled_back_runs: int,
) -> None:
    assert not should_block_memory_curation_retrieval_backpressure(
        evaluated_runs=evaluated_runs,
        pass_rate=pass_rate,
        failed_runs=failed_runs,
        rolled_back_runs=rolled_back_runs,
        min_evaluated_runs=3,
        min_pass_rate=0.67,
        max_failed_runs=1,
        max_rolled_back_runs=1,
    )


@given(
    pass_rate=st.floats(min_value=0.0, max_value=0.66, allow_nan=False, allow_infinity=False),
    failed_runs=st.integers(min_value=2, max_value=5),
    rolled_back_runs=st.integers(min_value=2, max_value=5),
)
def test_hypothesis_retrieval_backpressure_blocks_after_enough_bad_recent_runs(
    pass_rate: float,
    failed_runs: int,
    rolled_back_runs: int,
) -> None:
    assert should_block_memory_curation_retrieval_backpressure(
        evaluated_runs=3,
        pass_rate=pass_rate,
        failed_runs=failed_runs,
        rolled_back_runs=rolled_back_runs,
        min_evaluated_runs=3,
        min_pass_rate=0.67,
        max_failed_runs=1,
        max_rolled_back_runs=1,
    )

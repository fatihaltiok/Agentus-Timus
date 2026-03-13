import deal

from orchestration.self_modifier_engine import SelfModificationChangeMemorySummary


@deal.pre(lambda total, success, rolled_back, rollback_count, regression_count: total >= 0)
@deal.pre(lambda total, success, rolled_back, rollback_count, regression_count: success >= 0)
@deal.pre(lambda total, success, rolled_back, rollback_count, regression_count: rolled_back >= 0)
@deal.pre(lambda total, success, rolled_back, rollback_count, regression_count: rollback_count >= 0)
@deal.pre(lambda total, success, rolled_back, rollback_count, regression_count: regression_count >= 0)
@deal.post(lambda r: r.total >= 0)
@deal.post(lambda r: r.success_count >= 0)
@deal.post(lambda r: r.rolled_back_count >= 0)
@deal.post(lambda r: r.rollback_count >= 0)
@deal.post(lambda r: r.regression_count >= 0)
def _memory_summary(
    total: int,
    success: int,
    rolled_back: int,
    rollback_count: int,
    regression_count: int,
) -> SelfModificationChangeMemorySummary:
    return SelfModificationChangeMemorySummary(
        total=total,
        success_count=success,
        rolled_back_count=rolled_back,
        rollback_count=rollback_count,
        regression_count=regression_count,
    )


def test_memory_summary_contract_counts_non_negative() -> None:
    summary = _memory_summary(3, 1, 1, 1, 1)
    assert summary.total == 3

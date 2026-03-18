from __future__ import annotations

import deal


@deal.pre(lambda successes, total: total >= 0)
@deal.pre(lambda successes, total: 0 <= successes <= total)
@deal.post(lambda r: 0.0 <= r <= 1.0)
def routing_success_rate_contract(successes: int, total: int) -> float:
    return round(successes / total, 3) if total > 0 else 0.0


@deal.pre(lambda outcome_score, router_confidence: 0.0 <= outcome_score <= 1.0)
@deal.pre(lambda outcome_score, router_confidence: router_confidence is None or 0.0 <= router_confidence <= 1.0)
@deal.post(lambda r: r is None or 0.0 <= r <= 1.0)
def effective_routing_confidence_contract(
    outcome_score: float,
    router_confidence: float | None,
) -> float | None:
    return router_confidence if router_confidence is not None else outcome_score


def test_routing_success_rate_contract_bounds():
    assert routing_success_rate_contract(1, 2) == 0.5
    assert routing_success_rate_contract(0, 0) == 0.0


def test_effective_routing_confidence_prefers_router_confidence():
    assert effective_routing_confidence_contract(0.4, 0.9) == 0.9
    assert effective_routing_confidence_contract(0.4, None) == 0.4

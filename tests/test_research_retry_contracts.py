from __future__ import annotations

import deal


def _retryable_provider_error_text(text: str) -> bool:
    text = str(text or "").strip().lower()
    if not text:
        return False
    return any(
        needle in text
        for needle in (
            "timeout",
            "timed out",
            "rate limit",
            "429",
            "502",
            "503",
            "504",
            "connection error",
            "connection reset",
            "temporary failure",
            "name resolution",
            "service unavailable",
        )
    )


@deal.post(lambda r: isinstance(r, bool))
def retryable_result_contract(result: str) -> bool:
    text = str(result or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered.startswith("error:"):
        if _retryable_provider_error_text(lowered):
            return True
        return "empty result" in lowered or "leeres ergebnis" in lowered
    return "empty result" in lowered or "leeres ergebnis" in lowered


@deal.pre(lambda attempt, base_seconds: attempt >= 1 and base_seconds > 0)
@deal.post(lambda r: r > 0)
def retry_backoff_contract(attempt: int, base_seconds: float) -> float:
    return round(max(0.1, float(base_seconds)) * (2 ** (max(1, int(attempt)) - 1)), 2)


def test_retryable_result_contract_known_cases():
    assert retryable_result_contract("") is True
    assert retryable_result_contract("Error: timeout from provider") is True
    assert retryable_result_contract("Error: invalid api key") is False


def test_retry_backoff_contract_grows_monotonically():
    first = retry_backoff_contract(1, 0.5)
    second = retry_backoff_contract(2, 0.5)
    third = retry_backoff_contract(3, 0.5)

    assert first == 0.5
    assert second == 1.0
    assert third == 2.0
